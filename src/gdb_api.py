import os
import sys
from typing import Tuple

import gdb
import gdb.printing
import gdb.types
from gdb.printing import PrettyPrinter

import natvis
import parser


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


class NatvisPrettyPrinter(PrettyPrinter):
    def __init__(self, name, subprinters=None):
        super().__init__(name, subprinters)
        self.manager = natvis.NatvisManager()

    def __call__(self, val):
        type = gdb.types.get_basic_type(val.type)
        if not type:
            type = val.type
        if not type:
            return None
        if type.name is None:
            # We can't handle unnamed types
            return None

        symbol = gdb.lookup_symbol(type.name)

        if symbol is None:
            return None

        symbtab = symbol[0].symtab

        filename = symbtab.filename

        natvis_type = self.manager.lookup_type(type.name, filename)

        if natvis_type is None:
            return None

        return NatvisPrinter(natvis_type, val)


def add_natvis_printers():
    if os.environ.get("GDB_NATVIS_DEBUG") is not None:
        import pydevd as pydevd
        pydevd.settrace('localhost', port=41879, stdoutToServer=True, stderrToServer=True, suspend=False)

    gdb.printing.register_pretty_printer(gdb.current_objfile(), NatvisPrettyPrinter("Natvis"))
