import re
import sys
import traceback
from typing import Optional, Union

import gdb

import logger


class ParserError(Exception):

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)


try:
    from clang import cindex
    from clang.cindex import TranslationUnit, Cursor, CursorKind, Diagnostic, Config, SourceRange, TypeKind


    def print_cursor(cursor: Cursor, level: int = 0):
        print("  " * level, cursor.kind, cursor.spelling)
        for child in cursor.get_children():
            print_cursor(child, level + 1)


    def find_test_method(cursor):
        for child in cursor.get_children():
            if child.kind == CursorKind.STRUCT_DECL:
                if child.spelling == "_GdbNatvisType":
                    for method in child.get_children():
                        if method.kind == CursorKind.CXX_METHOD:
                            if method.spelling == "_GdbNatvisTestFunc":
                                return method
        return None


    def get_first_statement(cursor):
        for child in cursor.get_children():
            if child.kind.is_statement():
                return child

        return None


    def convert_clang_to_gdb_type(t: cindex.Type) -> gdb.Type:
        if t.kind == TypeKind.POINTER:
            return convert_clang_to_gdb_type(t.get_pointee()).pointer()
        if t.kind == TypeKind.CHAR_S:
            return gdb.lookup_type("char")
        else:
            raise ParserError("Unhandled pointer type!", t.kind, t.spelling)


    class ClangExpressionEvaluator:
        def __init__(self, this_val: gdb.Value, content: str):
            self.content = content

            if this_val.type.code != gdb.TYPE_CODE_PTR:
                # this must always be a pointer
                self.this_val = this_val.address
            else:
                self.this_val = this_val

        def get_binary_op(self, binary_cursor: Cursor):
            # libclang does not expose the binary operation in the C API. There is a patch for that
            # (https://reviews.llvm.org/D10833?id=39158) but that has been stuck in "code review" for three years...
            children = binary_cursor.get_children()
            left: Cursor = next(children)
            right: Cursor = next(children)

            left_ext: SourceRange = left.extent
            right_ext: SourceRange = right.extent

            op_text = self.content[left_ext.end.offset:right_ext.start.offset].lstrip().rstrip()

            return op_text

        def get_unary_op(self, cursor: Cursor):
            # libclang does not expose the unary operation in the C API...
            arg: Cursor = next(cursor.get_children())

            ext: SourceRange = arg.extent

            op_text = self.content[cursor.extent.start.offset:ext.start.offset].lstrip().rstrip()

            return op_text

        def get_cursor_text(self, cursor: Cursor) -> str:
            ext = cursor.extent
            return self.content[ext.start.offset:ext.end.offset]

        def get_value(self, expr_cursor: Cursor) -> Optional[Union[gdb.Value, bool, str, int, float]]:
            if expr_cursor.kind == CursorKind.UNEXPOSED_EXPR:
                # Unexposed expression found, let's hope it's not something serious...
                children = list(expr_cursor.get_children())
                if len(children) <= 0:
                    return None
                # Just assume that the first child is the important one. It's not like we have any way of making a
                # better decision here...
                return self.get_value(children[0])
            elif expr_cursor.kind == CursorKind.CXX_THIS_EXPR:
                return self.this_val
            elif expr_cursor.kind == CursorKind.MEMBER_REF_EXPR:
                base_ref = next(expr_cursor.get_children(), None)

                if base_ref is None:
                    # Some times clang inserts a "this"-expression if there is none and some times it doesn't.
                    # If the member ref does not have a child we just assume that it is a reference to an instance field
                    base_val = self.this_val
                else:
                    base_val = self.get_value(base_ref)

                return base_val[expr_cursor.spelling]
            elif expr_cursor.kind == CursorKind.BINARY_OPERATOR:
                children = expr_cursor.get_children()
                left = next(children)
                right = next(children)

                op = self.get_binary_op(expr_cursor)
                left_val = self.get_value(left)
                right_val = self.get_value(right)
                if op == "==":
                    return left_val == right_val
                elif op == "!=":
                    return left_val != right_val
                elif op == "<":
                    return left_val < right_val
                elif op == "<=":
                    return left_val <= right_val
                elif op == ">":
                    return left_val > right_val
                elif op == ">=":
                    return left_val >= right_val
                elif op == "&&":
                    return left_val and right_val
                elif op == "||":
                    return left_val or right_val
                elif op == "-":
                    return left_val - right_val
                elif op == "+":
                    return left_val + right_val
                elif op == "*":
                    return left_val * right_val
                elif op == "/":
                    if isinstance(left_val, int) and isinstance(right_val, int):
                        return left_val // right_val
                    return left_val / right_val
                elif op == "<<":
                    return left_val << right_val
                elif op == ">>":
                    return left_val << right_val
                else:
                    raise ParserError("Unhandled binary operator!", op)
            elif expr_cursor.kind == CursorKind.UNARY_OPERATOR or expr_cursor.kind == CursorKind.CXX_UNARY_EXPR:
                op = self.get_unary_op(expr_cursor)
                arg = next(expr_cursor.get_children())
                val = self.get_value(arg)

                if op == "!":
                    return not val
                elif op == "&":
                    return val.address
                elif op == "*":
                    return val.dereference()
                elif op == "sizeof":
                    return val.type.sizeof
                else:
                    raise ParserError("Unhandled unary operator!", op)
            elif expr_cursor.kind == CursorKind.CXX_BOOL_LITERAL_EXPR:
                return self.get_cursor_text(expr_cursor) == "true"
            elif expr_cursor.kind == CursorKind.FLOATING_LITERAL:
                val = self.get_cursor_text(expr_cursor)
                if val[-1] == "f":
                    # Strip the f suffix
                    val = val[0:-1]
                return float(val)
            elif expr_cursor.kind == CursorKind.INTEGER_LITERAL:
                val = self.get_cursor_text(expr_cursor)
                return int(val)
            elif expr_cursor.kind == CursorKind.ARRAY_SUBSCRIPT_EXPR:
                children = expr_cursor.get_children()
                base = next(children)
                index = next(children)

                base_val = self.get_value(base)
                index_val = self.get_value(index)

                ptr_val = base_val.cast(gdb.lookup_type("intptr_t"))

                base_size = base_val.type.target().sizeof

                result_ptr = ptr_val + index_val * base_size
                result_val = result_ptr.cast(base_val.type).dereference()

                return result_val
            elif expr_cursor.kind == CursorKind.CSTYLE_CAST_EXPR:
                gdb_t = convert_clang_to_gdb_type(expr_cursor.type.get_canonical())
                target_val_expr = next(expr_cursor.get_children())
                target_val = self.get_value(target_val_expr)
                return target_val.cast(gdb_t)
            elif expr_cursor.kind == CursorKind.PAREN_EXPR:
                return self.get_value(next(expr_cursor.get_children()))
            else:
                raise ParserError("Unhandled expression kind!", expr_cursor.kind, expr_cursor.spelling)


    def _get_content(c_type_name: str, c_type: str, expr: str) -> str:
        template = """
{base}

struct _GdbNatvisType : {type_name} {{
void _GdbNatvisTestFunc() {{
{expr};
}}
}};
"""
        return template.format(type_name=c_type_name, base=c_type, expr=expr)


    def _prepare_clang(content: str) -> Optional[TranslationUnit]:
        index = cindex.Index.create()
        tu = index.parse("/tmp/file.cpp", unsaved_files=[("/tmp/file.cpp", content)])

        for diag in tu.diagnostics:
            if diag.severity >= Diagnostic.Error:
                # Parsing failed
                raise ParserError(diag.format())
        return tu


    def check_expression(c_type_name: str, c_type: str, expr: str) -> bool:
        try:
            _prepare_clang(_get_content(c_type_name, c_type, expr))
            return True
        except ParserError:
            return False


    def evaluate_expression(this_val: gdb.Value, c_type_name: str, c_type: str, expr: str):
        try:
            content = _get_content(c_type_name, c_type, expr)
            tu = _prepare_clang(content)

            test_method = find_test_method(tu.cursor)

            if test_method is None:
                return None

            statement = get_first_statement(test_method)

            if statement is None:
                return None

            return ClangExpressionEvaluator(this_val, content).get_value(next(statement.get_children()))
        except gdb.MemoryError as e:
            return str(e)
        except ParserError as e:
            logger.log_message(
                "Failed to evaluate '{}': {}".format(expr, "".join(traceback.format_exception_only(type(e), e))))
            raise
        except Exception as e:
            exc_type, exc_value, exc_tb = sys.exc_info()
            logger.log_message(
                "Failed to evaluate '{}': {}".format(expr, "".join(traceback.format_exception(type(e), e, exc_tb))))
            return None

except ImportError:
    SPLIT_REGEX = re.compile("\.|->")


    def check_expression(c_type_name: str, c_type: str, expr: str) -> bool:
        # Can't do much type checking here...
        return True


    def evaluate_expression(this_val: gdb.Value, c_type_name: str, c_type: str, expr: str):
        try:
            current_val = this_val
            for ident in SPLIT_REGEX.split(expr):
                current_val = current_val[ident]
            return current_val
        except:
            # If the expression was too complicated for this parser it will likely result in an exception
            # TODO: Add actual logging for errors
            return None
