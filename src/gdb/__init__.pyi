from enum import Enum, auto
from typing import Optional, Any, overload, Tuple, Iterable, Union


class CodeEnum(Enum):
    TYPE_CODE_PTR = auto()
    TYPE_CODE_ARRAY = auto()
    TYPE_CODE_STRUCT = auto()
    TYPE_CODE_UNION = auto()
    TYPE_CODE_ENUM = auto()
    TYPE_CODE_FLAGS = auto()
    TYPE_CODE_FUNC = auto()
    TYPE_CODE_FLT = auto()
    TYPE_CODE_INT = auto()
    TYPE_CODE_VOID = auto()
    TYPE_CODE_SET = auto()
    TYPE_CODE_RANGE = auto()
    TYPE_CODE_STRING = auto()
    TYPE_CODE_BITSTRING = auto()
    TYPE_CODE_ERROR = auto()
    TYPE_CODE_METHOD = auto()
    TYPE_CODE_METHODPTR = auto()
    TYPE_CODE_MEMBERPTR = auto()
    TYPE_CODE_REF = auto()
    TYPE_CODE_RVALUE_REF = auto()
    TYPE_CODE_CHAR = auto()
    TYPE_CODE_BOOL = auto()
    TYPE_CODE_COMPLEX = auto()
    TYPE_CODE_TYPEDEF = auto()
    TYPE_CODE_NAMESPACE = auto()
    TYPE_CODE_DECFLOAT = auto()
    TYPE_CODE_INTERNAL_FUNCTION = auto()


TYPE_CODE_PTR = CodeEnum.TYPE_CODE_PTR
TYPE_CODE_ARRAY = CodeEnum.TYPE_CODE_ARRAY
TYPE_CODE_STRUCT = CodeEnum.TYPE_CODE_STRUCT
TYPE_CODE_UNION = CodeEnum.TYPE_CODE_UNION
TYPE_CODE_ENUM = CodeEnum.TYPE_CODE_ENUM
TYPE_CODE_FLAGS = CodeEnum.TYPE_CODE_FLAGS
TYPE_CODE_FUNC = CodeEnum.TYPE_CODE_FUNC
TYPE_CODE_FLT = CodeEnum.TYPE_CODE_FLT
TYPE_CODE_INT = CodeEnum.TYPE_CODE_INT
TYPE_CODE_VOID = CodeEnum.TYPE_CODE_VOID
TYPE_CODE_SET = CodeEnum.TYPE_CODE_SET
TYPE_CODE_RANGE = CodeEnum.TYPE_CODE_RANGE
TYPE_CODE_STRING = CodeEnum.TYPE_CODE_STRING
TYPE_CODE_BITSTRING = CodeEnum.TYPE_CODE_BITSTRING
TYPE_CODE_ERROR = CodeEnum.TYPE_CODE_ERROR
TYPE_CODE_METHOD = CodeEnum.TYPE_CODE_METHOD
TYPE_CODE_METHODPTR = CodeEnum.TYPE_CODE_METHODPTR
TYPE_CODE_MEMBERPTR = CodeEnum.TYPE_CODE_MEMBERPTR
TYPE_CODE_REF = CodeEnum.TYPE_CODE_REF
TYPE_CODE_RVALUE_REF = CodeEnum.TYPE_CODE_RVALUE_REF
TYPE_CODE_CHAR = CodeEnum.TYPE_CODE_CHAR
TYPE_CODE_BOOL = CodeEnum.TYPE_CODE_BOOL
TYPE_CODE_COMPLEX = CodeEnum.TYPE_CODE_COMPLEX
TYPE_CODE_TYPEDEF = CodeEnum.TYPE_CODE_TYPEDEF
TYPE_CODE_NAMESPACE = CodeEnum.TYPE_CODE_NAMESPACE
TYPE_CODE_DECFLOAT = CodeEnum.TYPE_CODE_DECFLOAT
TYPE_CODE_INTERNAL_FUNCTION = CodeEnum.TYPE_CODE_INTERNAL_FUNCTION


class Field:
    bitpos: int
    enumval: int
    name: Optional[str]
    artificial: bool
    is_base_class: bool
    bitsize: int
    type: Type
    parent_type: Type


class Type:
    code: CodeEnum
    name: Optional[str]
    sizeof: int
    tag: Optional[str]

    def fields(self) -> Iterable[Field]:

    @overload
    def array(self, n1: int) -> Type: ...

    @overload
    def array(self, n1: int, n2: int) -> Type: ...

    @overload
    def vector(self, n1: int) -> Type: ...

    @overload
    def vector(self, n1: int, n2: int) -> Type: ...

    def volatile(self) -> Type: ...

    def unqualified(self) -> Type: ...

    def range(self) -> Tuple[int, int]: ...

    def reference(self) -> Type: ...

    def pointer(self) -> Type: ...

    def strip_typedefs(self) -> Type: ...

    def target(self) -> Type: ...

    def template_argument(self, n: int, block: Any = None) -> Type: ...

    def optimized_out(self) -> bool: ...


def lookup_type(name: str, block: Any = None) -> Type: ...


class LazyString:
    address: Value
    length: int
    encoding: str
    type: Type

    def value(self) -> Value: ...


class Value:
    address: Value
    is_optimized_out: bool
    type: Type
    dynamic_type: Type
    is_lazy: bool

    def __init__(self, val: Union[bool, int, float, str, Value, LazyString]): ...

    def cast(self, type: Type) -> Value: ...

    def dereference(self) -> Value: ...

    def referenced_value(self) -> Value: ...

    def reference_value(self) -> Value: ...

    def const_value(self) -> Value: ...

    def dynamic_cast(self, type: Type) -> Value: ...

    def reinterpret_cast(self, type: Type) -> Value: ...

    def string(self, encoding: str = None, errors: str = None, length: int = None) -> str: ...

    def lazy_string(self, encoding: str = None, length: int = None) -> LazyString: ...

    def fetch_lazy(self) -> None: ...
