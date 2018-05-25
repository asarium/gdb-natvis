from typing import Tuple, Union, Iterator, List, Set, Dict

import gdb

import utils


class TypeWrapper:
    referencing_types: Set['TypeWrapper']
    referenced_types: Set['TypeWrapper']

    def __init__(self, type: gdb.Type) -> None:
        super().__init__()

        self.type = type
        self.referenced_types = set()
        self.referencing_types = set()

    def __eq__(self, o: 'TypeWrapper') -> bool:
        left_str = self.name or str(self.type)
        right_str = o.name or str(o.type)

        return left_str == right_str

    def __hash__(self) -> int:
        val = self.name or str(self.type)
        return hash(val)

    def __str__(self) -> str:
        return str(self.type)

    def __repr__(self) -> str:
        return "<{}: {!r}>".format(self.__class__.__name__, str(self.type))

    @property
    def name(self):
        if self.type.name is not None:
            return self.type.name
        if self.type.tag is not None:
            return self.type.tag
        return None

    def add_type_reference(self, t: 'TypeWrapper'):
        self.referenced_types.add(t)
        t.referencing_types.add(self)


class TypeWrapperList:

    def __init__(self) -> None:
        super().__init__()

        self.type_wrapper_lookup = {}

    def __contains__(self, item: Union[gdb.Type, TypeWrapper]):
        if isinstance(item, TypeWrapper):
            return item in self.type_wrapper_lookup
        else:
            return TypeWrapper(item) in self

    def __iter__(self) -> Iterator[TypeWrapper]:
        return iter(self.type_wrapper_lookup)

    def __len__(self):
        return len(self.type_wrapper_lookup)

    def add_type(self, type: gdb.Type) -> TypeWrapper:
        if type in self:
            return self.type_wrapper_lookup[TypeWrapper(type)]

        wrapper = TypeWrapper(type)
        self.type_wrapper_lookup[wrapper] = wrapper
        return wrapper


class TypeAggregator:
    type_list: TypeWrapperList

    def __init__(self) -> None:
        super().__init__()

        self.type_list = TypeWrapperList()
        self.work_list = []

    def add_type(self, t: gdb.Type) -> TypeWrapper:
        return self.type_list.add_type(t)

    def add_work_item(self, t: gdb.Type) -> TypeWrapper:
        if t in self.type_list:
            return self.add_type(t)

        wrapper = self.add_type(t)
        self.work_list.append(wrapper)

        return wrapper

    def has_work(self) -> bool:
        return len(self.work_list) > 0

    def get_work(self) -> TypeWrapper:
        return self.work_list.pop(0)

    def add_type_reference(self, parent: TypeWrapper, type: TypeWrapper):
        parent.referenced_types.add(type)
        type.referencing_types.add(parent)

    def remove_type_reference(self, parent: TypeWrapper, type: TypeWrapper):
        parent.referenced_types.remove(type)
        type.referencing_types.remove(parent)


class GdbTypeFormatter:
    def __init__(self) -> None:
        super().__init__()

        self.type_name_mapping = {}

    def get_type_name(self, name: str) -> str:
        if name in self.type_name_mapping:
            return self.type_name_mapping[name]

        mapped_name = "_GdbType_{}".format(len(self.type_name_mapping))
        self.type_name_mapping[name] = mapped_name
        return mapped_name

    def _process_type(self, parent_type: TypeWrapper, t: gdb.Type, agg: TypeAggregator, process_fields: bool):
        t = t.strip_typedefs()

        if t.code == gdb.TYPE_CODE_PTR or t.code == gdb.TYPE_CODE_REF:
            basic = utils.get_basic_type(t)

            if basic.code == gdb.TYPE_CODE_FUNC:
                self._process_type(parent_type, basic.target(), agg, False)
                self._process_type_fields(parent_type, basic, agg)
            else:
                basic = utils.get_struct_type(t)
                if basic is not None:
                    agg.add_work_item(basic)
            return

        t = utils.get_struct_type(t)

        if t is None:
            # Not a struct type
            return

        if process_fields or utils.get_type_name_or_tag(t) is None:
            # Unnamed types are not added to the type graph
            self._process_type_fields(parent_type, t, agg)
        else:
            field_wrapper = agg.add_work_item(t)
            agg.add_type_reference(field_wrapper, parent_type)

    def _process_type_fields(self, parent_type: TypeWrapper, t: gdb.Type, agg: TypeAggregator):
        for f in t.fields():
            field_t: gdb.Type = f.type

            self._process_type(parent_type, field_t, agg, f.name is None)

    def _build_type_graph(self, agg: TypeAggregator):
        while agg.has_work():
            wrapper = agg.get_work()
            t = wrapper.type

            self._process_type_fields(wrapper, t, agg)

    def _topological_sort(self, agg: TypeAggregator) -> List[TypeWrapper]:
        L = []
        S = set(x for x in agg.type_list if len(x.referencing_types) <= 0)
        while len(S) > 0:
            n = S.pop()
            L.append(n)
            for m in list(n.referenced_types):
                agg.remove_type_reference(n, m)

                if len(m.referencing_types) <= 0:
                    S.add(m)

        assert not any(x for x in agg.type_list if len(x.referenced_types) > 0)

        return L  # Since the program was compilable there shouldn't be any cycles...

    def _get_type_declaration(self, t: gdb.Type):
        if t.code == gdb.TYPE_CODE_UNION or t.code == gdb.TYPE_CODE_STRUCT:
            # Unions are always written as structs
            return "struct " + self.get_type_name(utils.get_type_name_or_tag(t)) \
                   + "; // " + utils.get_type_name_or_tag(t)
        else:
            return str(t) + ";"

    def get_type_string(self, t: gdb.Type) -> Tuple[str, str]:
        t = utils.get_basic_type(t)

        agg = TypeAggregator()
        agg.add_work_item(t)

        self._build_type_graph(agg)

        sorted_types = self._topological_sort(agg)

        forward_decls = "\n".join(self._get_type_declaration(x.type) for x in sorted_types)

        decls = "\n\n".join(self._get_type_string(x.type) for x in sorted_types)

        return self.get_type_name(utils.get_type_name_or_tag(t)), forward_decls + "\n\n" + decls

    def _get_type_string(self, t: gdb.Type) -> str:
        pre, post = self._format_type(t, self.get_type_name(utils.get_type_name_or_tag(t)))

        type_text = "// " + utils.get_type_name_or_tag(t) + "\n" + pre + post + ";"

        return type_text

    def _format_struct(self, type: gdb.Type, force_name: str = None) -> Tuple[str, str]:
        if utils.get_type_name_or_tag(type) is not None and force_name is None:
            # Named types are not expanded since they are declared before this type
            return self.get_type_name(utils.get_type_name_or_tag(type)), ""
        else:
            if force_name is not None:
                # Named types are always written as structs since they need to be subclassable
                out = "struct"
            else:
                if type.code == gdb.TYPE_CODE_UNION:
                    out = "union"
                else:
                    out = "struct"

            if force_name is not None:
                out += " " + force_name

            out += " {\n"
            for f in type.fields():
                pre, post = self._format_type(f.type)
                out += "\n".join("  " + x for x in pre.splitlines())

                out += (" " + f.name if f.name is not None else "") + post + ";\n"
            out += "}"

            return out, ""

    def _format_type(self, type: gdb.Type, force_name: str = None) -> Tuple[str, str]:
        if type.code == gdb.TYPE_CODE_PTR:
            target_pre, target_post = self._format_type(type.target())
            return target_pre + "*", target_post
        elif type.code == gdb.TYPE_CODE_ARRAY:
            base = type.target()
            size = int(type.sizeof / base.sizeof)

            target_pre, target_post = self._format_type(type.target())

            return target_pre, target_post + "[" + str(size) + "]"
        elif type.code == gdb.TYPE_CODE_STRUCT or type.code == gdb.TYPE_CODE_UNION:
            return self._format_struct(type, force_name)
        elif type.code == gdb.TYPE_CODE_TYPEDEF:
            return self._format_type(type.target(), force_name)
        elif type.code == gdb.TYPE_CODE_FUNC:
            pre = "".join(self._format_type(type.target())) + "("
            arglist = type.fields()
            arglist_str = ", ".join("".join(self._format_type(x.type)) for x in arglist)
            return pre, ")(" + arglist_str + ")"
        else:
            return str(type), ""


class TypeManager:
    cached_types: Dict[TypeWrapper, Tuple[str, str]]

    def __init__(self) -> None:
        super().__init__()

        self.cached_types = {}

    def get_type_string(self, t: gdb.Type):
        wrapper = TypeWrapper(t)

        if wrapper in self.cached_types:
            return self.cached_types[wrapper]

        formatter = GdbTypeFormatter()
        type_name, decl = formatter.get_type_string(t)

        self.cached_types[wrapper] = (type_name, decl)

        return type_name, decl
