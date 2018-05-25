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
from utils import get_type_name_or_tag, get_basic_type, is_pointer

DEBUGGING = False


class GdbValueWrapper(object):
    """
    Wrapper class around a gdb.Value
    This overrides the __str__ method since that causes problems in the debugger when it tires to print a recursive data
    structure
    """

    def __init__(self, obj):
        '''
        Wrapper constructor.
        @param obj: object to wrap
        '''
        # wrap the object
        self._wrapped_obj = obj

    def __str__(self) -> str:
        return "Test"

    def __getitem__(self, item):
        return self._wrapped_obj[item]

    def __getattr__(self, attr):
        # see if this object has attr
        # NOTE do not use hasattr, it goes into
        # infinite recurrsion
        if attr in self.__dict__:
            # this object has it
            return getattr(self, attr)
        # proxy to the wrapped object
        return getattr(self._wrapped_obj, attr)


class NatvisPrinter:
    def __init__(self, parent: 'NatvisPrettyPrinter', instance: natvis.NatvisTypeInstance, val):
        self.instance = instance
        self.parent = parent
        self.val = val
        self.type = self.instance.type
        self.c_type_name, self.c_type = self.parent.type_manager.get_type_string(self.val.type)

    def check_condition(self, cond: str) -> bool:
        if cond is None:
            return True

        return bool(self._get_value(cond))

    def _get_value(self, expression, **kwargs: str):
        replaced = self.instance.replace_vars(expression, **kwargs)
        val = parser.evaluate_expression(self.val, self.c_type_name, self.c_type, replaced)
        if val is not None:
            return val
        else:
            # Return the expression as a string in case the execution failed
            return "{" + replaced + "}"

    def children(self):
        if self.type.expand_items is None:
            return

        for item in self.type.expand_items:
            if isinstance(item, natvis.ExpandItem):
                if self.check_condition(item.condition):
                    value = self._get_value(item.expression.base_expression)
                    yield item.name, value
            elif isinstance(item, natvis.ExpandIndexListItems):
                size = self._get_value(item.size_expr)
                for i in range(size):
                    val = self._get_value(item.value_node, i=str(i))
                    yield "[{}]".format(i), val

    def to_string(self):
        for string in self.type.display_parsers:
            if self.check_condition(string.condition):
                display_args = []
                for code in string.parser.code_parts:
                    code_val = self._get_value(code.base_expression)
                    visualizer = gdb.default_visualizer(code_val)
                    if visualizer is not None and isinstance(visualizer, NatvisPrinter):
                        # If this is again a natvis visualizer we can enforce the usage of the DisplayString option
                        display_args.append(visualizer.to_string())
                    else:
                        display_args.append(str(code_val))
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


def find_valid_type(type_manager: TypeManager, iter: Iterator[natvis.NatvisTypeInstance], value: gdb.Value):
    c_type_name, c_type = None, None

    for t in iter:
        if c_type_name is None and c_type is None:
            c_type_name, c_type = type_manager.get_type_string(value.type)

        valid = True
        for expression, required in t.type.enumerate_expressions():
            replaced = t.replace_vars(expression, i="int()")

            if required and not parser.check_expression(c_type_name, c_type, replaced):
                valid = False
                break

        if valid:
            return t

    return None


def is_natvis_taget(val: gdb.Value) -> bool:
    t = val.type.strip_typedefs()

    if is_pointer(t):
        target_t = t.target().strip_typedefs()
        if is_pointer(target_t):
            # We do not handle Pointer to pointer types since they probably are not meant to be used that way
            # The remaining code of the pretty printer would strip any pointer references away from the value so we need
            # to check for that here
            return False
        else:
            return True
    else:
        # Just assume that everything else is fine
        return True


class NatvisPrettyPrinter(PrettyPrinter):
    def __init__(self, name, subprinters=None):
        super().__init__(name, subprinters)
        self.manager = natvis.NatvisManager()
        self.type_manager = TypeManager()

    def __call__(self, val: gdb.Value):
        val = GdbValueWrapper(val) if DEBUGGING else val

        try:
            if not is_natvis_taget(val):
                return None

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

        global DEBUGGING
        DEBUGGING = True

    gdb_printing.register_pretty_printer(gdb.current_objfile(), NatvisPrettyPrinter("Natvis"))
