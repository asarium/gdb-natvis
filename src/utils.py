from typing import Optional

import gdb


def get_basic_type(type_: gdb.Type) -> gdb.Type:
    """Return the "basic" type of a type.

    Arguments:
        type_: The type to reduce to its basic type.

    Returns:
        type_ with const/volatile is stripped away,
        and typedefs/references converted to the underlying type.
    """

    while (type_.code == gdb.TYPE_CODE_REF or
           type_.code == gdb.TYPE_CODE_RVALUE_REF or
           type_.code == gdb.TYPE_CODE_TYPEDEF or
           type_.code == gdb.TYPE_CODE_PTR):
        if (type_.code == gdb.TYPE_CODE_REF or
                type_.code == gdb.TYPE_CODE_RVALUE_REF or type_.code == gdb.TYPE_CODE_PTR):
            type_ = type_.target()
        else:
            type_ = type_.strip_typedefs()
    return type_.unqualified()


def get_struct_type(t: gdb.Type) -> Optional[gdb.Type]:
    """Return the "basic" type of a type.

    Arguments:
        type_: The type to reduce to its basic type.

    Returns:
        type_ with const/volatile is stripped away,
        and typedefs/references converted to the underlying type.
    """
    t = t.strip_typedefs()
    while True:
        if t.code == gdb.TYPE_CODE_PTR or t.code == gdb.TYPE_CODE_REF or t.code == gdb.TYPE_CODE_RVALUE_REF:
            t = t.target()
        elif t.code == gdb.TYPE_CODE_ARRAY:
            t = t.target()
        elif t.code == gdb.TYPE_CODE_TYPEDEF:
            t = t.target()
        else:
            break

    if t.code != gdb.TYPE_CODE_STRUCT and t.code != gdb.TYPE_CODE_UNION:
        return None
    else:
        return t

    while (type_.code == gdb.TYPE_CODE_REF or
           type_.code == gdb.TYPE_CODE_RVALUE_REF or
           type_.code == gdb.TYPE_CODE_TYPEDEF or
           type_.code == gdb.TYPE_CODE_PTR):
        if (type_.code == gdb.TYPE_CODE_REF or
                type_.code == gdb.TYPE_CODE_RVALUE_REF or type_.code == gdb.TYPE_CODE_PTR):
            type_ = type_.target()
        else:
            type_ = type_.strip_typedefs()
    return type_.unqualified()


def get_type_name_or_tag(t: gdb.Type) -> Optional[str]:
    if t.name is not None:
        return t.name
    if t.tag is not None:
        return t.tag
    return None


def is_pointer(t: gdb.Type) -> bool:
    return t.code == gdb.TYPE_CODE_PTR
