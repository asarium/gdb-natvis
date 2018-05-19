import re

try:
    from clang import cindex
    from clang.cindex import TranslationUnit, Cursor, CursorKind, Diagnostic, Config, SourceRange


    def find_test_method(cursor):
        for child in cursor.get_children():
            if child.kind == CursorKind.STRUCT_DECL:
                if child.spelling == "deriv":
                    for method in child.get_children():
                        if method.kind == CursorKind.CXX_METHOD:
                            if method.spelling == "test":
                                return method
        return None


    def get_first_statement(cursor):
        for child in cursor.get_children():
            if child.kind.is_statement():
                return child

        return None


    class ClangExpressionEvaluator:
        def __init__(self, this_val, content: str):
            self.content = content
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

        def get_cursor_text(self, cursor: Cursor) -> str:
            ext = cursor.extent
            return self.content[ext.start.offset:ext.end.offset]

        def get_value(self, expr_cursor: Cursor):
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
                base_ref = next(expr_cursor.get_children())
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
                else:
                    return None
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
            else:
                return None


    def evaluate_expression(this_val, c_type: str, expr: str):
        index = cindex.Index.create()

        template = """
{base}

struct deriv : val_type {{
void test() {{
{expr};
}}
}};
"""
        content = template.format(base=c_type, expr=expr)

        tu = index.parse("/tmp/file.cpp", unsaved_files=[("/tmp/file.cpp", content)])

        for diag in tu.diagnostics:
            if diag.severity >= Diagnostic.Error:
                # Parsing failed
                return None

        test_method = find_test_method(tu.cursor)

        if test_method is None:
            return None

        statement = get_first_statement(test_method)

        if statement is None:
            return None

        try:
            return ClangExpressionEvaluator(this_val, content).get_value(next(statement.get_children()))
        except:
            return None

except ImportError:
    SPLIT_REGEX = re.compile("\.|->")


    def evaluate_expression(this_val, c_type: str, expr: str):
        try:
            current_val = this_val
            for ident in SPLIT_REGEX.split(expr):
                current_val = current_val[ident]
            return current_val
        except:
            # If the expression was too complicated for this parser it will likely result in an exception
            # TODO: Add actual logging for errors
            return None
