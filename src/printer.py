import os
import sys
import traceback
from typing import Tuple, Iterable, Iterator, Optional

import gdb
import gdb.printing as gdb_printing
from gdb.printing import PrettyPrinter

import logger
import natvis
import parser
from templates import TemplateType
from type_mapping import TypeManager
from utils import get_type_name_or_tag, get_basic_type


class NatvisPrinter:
    def __init__(self, parent: 'NatvisPrettyPrinter', type: natvis.NatvisType, val):
        self.parent = parent
        self.val = val
        self.type = type
        self.c_type_name, self.c_type = self.parent.type_manager.get_type_string(self.val.type)

    def check_condition(self, cond: str) -> bool:
        if cond is None:
            return True

        return bool(self._get_value(cond))

    def _get_value(self, expression):
        val = parser.evaluate_expression(self.val, self.c_type_name, self.c_type, expression)
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
                value = self._get_value(item.expression.base_expression)
                yield item.name, value

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
        return get_type_name_or_tag(arg)
    else:
        return str(arg)


def get_template_args(type: gdb.Type) -> Iterable[TemplateType]:
    index = 0
    while True:
        try:
            yield gdb_to_template_type(type.template_argument(index))
        except:
            break

        index += 1


def gdb_to_template_type(type: gdb.Type):
    type_name = template_arg_to_string(type)
    template_index = type_name.find("<")
    if template_index != -1:
        type_name = type_name[:template_index]

    return TemplateType(type_name, list(get_template_args(type)))


def is_void_ptr(type: gdb.Type):
    if type.code != gdb.TYPE_CODE_PTR:
        return False

    target = type.target()

    return target.code == gdb.TYPE_CODE_VOID


def strip_references(val: gdb.Value) -> Tuple[Optional[gdb.Value], Optional[gdb.Type]]:
    """
    Removes all types of references off of val. The result is a value with a non-pointer or reference type and a value of
    the same type
    :param val: The value to process
    :return: The basic value, the unqualified type of that value
    """
    while val.type.code == gdb.TYPE_CODE_REF or val.type.code == gdb.TYPE_CODE_RVALUE_REF or val.type.code == gdb.TYPE_CODE_PTR:
        if is_void_ptr(val.type):
            return None, None
        val = val.referenced_value()
    return val, val.type.unqualified()


def find_valid_type(type_manager: TypeManager, iter: Iterator[natvis.NatvisType], value: gdb.Value):
    c_type_name, c_type = type_manager.get_type_string(value.type)

    for t in iter:
        valid = True
        for expression, required in t.enumerate_expressions():
            if required and not parser.check_expression(c_type_name, c_type, expression):
                valid = False
                break

        if valid:
            return t

    return None


class NatvisPrettyPrinter(PrettyPrinter):
    def __init__(self, name, subprinters=None):
        super().__init__(name, subprinters)
        self.manager = natvis.NatvisManager()
        self.type_manager = TypeManager()

    def __call__(self, val: gdb.Value):
        try:
            val, val_type = strip_references(val)
            if val is None:
                # Probably a void ptr
                return None

            val_type = val_type.strip_typedefs()
            if not val_type:
                return None

            val_type: gdb.Type = get_basic_type(val_type)

            if get_type_name_or_tag(val_type) is None:
                # We can't handle unnamed types
                return None

            if val_type.code != gdb.TYPE_CODE_UNION and val_type.code != gdb.TYPE_CODE_STRUCT:
                # Non-structs are not handled by this printer
                return None

            template_type = gdb_to_template_type(val_type)

            symbol = gdb.lookup_symbol(get_type_name_or_tag(val_type))

            if symbol is None or symbol[0] is None:
                # Hmm, basic type has no symbol table entry. Hopefully the type manager already loaded the right
                # document for this
                filename = None
            else:
                symbtab = symbol[0].symtab

                filename = symbtab.filename

            natvis_type = find_valid_type(self.type_manager, self.manager.lookup_types(template_type, filename), val)

            if natvis_type is None:
                return None

            return NatvisPrinter(self, natvis_type, val)
        except Exception as e:
            exc_type, exc_value, exc_tb = sys.exc_info()
            logger.log_message("".join(traceback.format_exception(type(e), e, exc_tb)))
            return None


def add_natvis_printers():
    if os.environ.get("GDB_NATVIS_DEBUG") is not None:
        import pydevd as pydevd
        pydevd.settrace('localhost', port=41879, stdoutToServer=True, stderrToServer=True, suspend=False)

    gdb_printing.register_pretty_printer(gdb.current_objfile(), NatvisPrettyPrinter("Natvis"))
