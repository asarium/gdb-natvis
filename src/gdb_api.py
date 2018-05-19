import os
from typing import Tuple, Iterable

import gdb
import gdb.printing
import gdb.types
from gdb.printing import PrettyPrinter

import natvis
import parser
from templates import TemplateType


def format_type(type, force_name: str = None) -> Tuple[str, str]:
    if type.code == gdb.TYPE_CODE_PTR:
        target_pre, target_post = format_type(type.target())
        return target_pre + "*", target_post
    elif type.code == gdb.TYPE_CODE_ARRAY:
        base = type.target()
        size = int(type.sizeof / base.sizeof)

        target_pre, target_post = format_type(type.target())

        return target_pre, target_post + "[" + str(size) + "]"
    elif type.code == gdb.TYPE_CODE_STRUCT or type.code == gdb.TYPE_CODE_UNION:
        if type.code == gdb.TYPE_CODE_STRUCT:
            out = "struct"
        else:
            out = "union"

        if force_name is not None:
            out += " " + force_name

        out += " {\n"
        for f in type.fields():
            pre, post = format_type(f.type)
            out += "\n".join("  " + x for x in pre.splitlines())

            out += (" " + f.name if f.name is not None else "") + post + ";\n"
        out += "}"

        return out, ""
    elif type.code == gdb.TYPE_CODE_TYPEDEF:
        return format_type(type.target(), force_name)
    else:
        return type.name or "", ""


def stringify_type(type, type_name: str = None):
    pre, post = format_type(type, type_name)

    return pre + post + ";"


class NatvisPrinter:
    def __init__(self, type: natvis.NatvisType, val):
        self.val = val
        self.type = type
        self.c_type = stringify_type(self.val.type, "val_type")

    def check_condition(self, cond: str) -> bool:
        if cond is None:
            return True

        return bool(self._get_value(cond))

    def _get_value(self, expression):
        val = parser.evaluate_expression(self.val, self.c_type, expression)
        if val is not None:
            return val
        else:
            # Return the expression as a string in case the execution failed
            return "{" + expression + "}"

    def children(self):
        if self.type.expand_items is None:
            return

        for item in self.type.expand_items:
            if self.check_condition(item.condition):
                yield item.name, self._get_value(item.expression.base_expression)

    def to_string(self):
        for string in self.type.display_parsers:
            if self.check_condition(string.condition):
                display_args = []
                for code in string.parser.code_parts:
                    display_args.append(str(self._get_value(code.base_expression)))
                return string.parser.template_string.format(*display_args)

        return "No visualizer available"


def template_arg_to_string(arg) -> str:
    if isinstance(arg, gdb.Type):
        return arg.name
    else:
        return str(arg)


def get_template_args(type) -> Iterable[TemplateType]:
    index = 0
    while True:
        try:
            yield gdb_to_template_type(type.template_argument(index))
        except:
            break

        index += 1


def gdb_to_template_type(type):
    type_name = template_arg_to_string(type)
    template_index = type_name.find("<")
    if template_index != -1:
        type_name = type_name[:template_index]

    return TemplateType(type_name, list(get_template_args(type)))


def strip_references(val):
    """
    Removes all types of references off of val. The result is a value with a non-pointer or reference type and a value of
    the same type
    :param val: The value to process
    :return: The basic value, the unqualified type of that value
    """
    while val.type.code == gdb.TYPE_CODE_REF or val.type.code == gdb.TYPE_CODE_RVALUE_REF or val.type.code == gdb.TYPE_CODE_PTR:
        val = val.referenced_value()
    return val, val.type.unqualified()


def strip_typedefs(type):
    """
    Strips typedefs off the type until the basic type is found or until the target has no name
    This is needed since natvis operates on type names.
    :param type: The type to strip typedefs off of
    :return: The basic type
    """
    while type.code == gdb.TYPE_CODE_TYPEDEF and type.target().name is not None:
        type = type.target()
    return type


class NatvisPrettyPrinter(PrettyPrinter):
    def __init__(self, name, subprinters=None):
        super().__init__(name, subprinters)
        self.manager = natvis.NatvisManager()

    def __call__(self, val):
        val, val_type = strip_references(val)
        val_type = strip_typedefs(val_type)
        if not val_type:
            return None
        if val_type.name is None:
            # We can't handle unnamed types
            return None

        val_type = gdb.types.get_basic_type(val_type)

        symbol = gdb.lookup_symbol(val_type.name)

        if symbol is None:
            return None

        template_type = gdb_to_template_type(val_type)

        symbtab = symbol[0].symtab

        filename = symbtab.filename

        natvis_type = self.manager.lookup_type(template_type, filename)

        if natvis_type is None:
            return None

        return NatvisPrinter(natvis_type, val)


def add_natvis_printers():
    if os.environ.get("GDB_NATVIS_DEBUG") is not None:
        import pydevd as pydevd
        pydevd.settrace('localhost', port=41879, stdoutToServer=True, stderrToServer=True, suspend=False)

    gdb.printing.register_pretty_printer(gdb.current_objfile(), NatvisPrettyPrinter("Natvis"))
