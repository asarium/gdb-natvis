import os
import re
from enum import Enum
from typing import Iterator, Tuple, Optional, List
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

import logger
import templates


class NatvisException(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


def lookahead_iter(content: str, lookahead: int) -> Iterator[Tuple[str, str]]:
    for i in range(0, len(content)):
        substr = content[i:i + lookahead + 1]
        yield substr[0], substr[1:]


class FormatSpecifiers(Enum):
    DECIMAL_INT = "d",
    OCTAL_INT = "o",
    HEX_INT = "x", "h", "hr", "wc", "wm"
    HEX_INT_UPPER = "X", "H"
    CHARACTER = "c",
    STRING = "s", "sa"
    STRING_NO_QUOTES = "sb", "s8b"
    WIDE_STRING = "su", "bstr"
    WIDE_STRING_NO_QUOTES = "sub",
    UTF32_STRING = "s32",
    UTF32_STRING_NO_QUOTES = "s32b",
    ENUM = "en",
    HEAP_VARIABLE = "hv",
    NO_ADDRESS = "na",
    NO_DERIVED = "nd",


def parse_format_specifier(spec: str) -> Iterator[FormatSpecifiers]:
    pos = 0
    while pos < len(spec):
        current_match = None
        current_length = 0
        for format_spec in FormatSpecifiers:
            for name in format_spec.value:
                substr = spec[pos:pos + len(name)]
                if substr == name:
                    if current_match is None or len(substr) > current_length:
                        # Found a new match
                        current_match = format_spec
                        current_length = len(substr)
        if current_match is None:
            # Found an invalid format specifier. Try to skip over it
            pos += 1
        else:
            yield current_match
            pos += current_length


ARRAY_LENGTH_REGEX = re.compile("^(?:\[(.*)\])?(.*)$")


class FormatExpression:

    def __init__(self, expression: str) -> None:
        super().__init__()

        parts = expression.rsplit(",", 1)

        self.base_expression = parts[0]
        self.formatspecs = None
        self.array_length = None
        if len(parts) == 2:
            format = parts[1].lstrip().rstrip()
            match = ARRAY_LENGTH_REGEX.match(format)
            self.array_length = match.group(1)
            self.formatspecs = list(parse_format_specifier(match.group(2)))

    def __str__(self):
        return self.base_expression + ", " + self.array_length or "(no array)" + " (" + ", ".join(
            x.name for x in self.formatspecs or []) + ")"

    def __repr__(self):
        return "<{}: {!r},{!r},{!r}>".format(self.__class__.__name__, self.base_expression, self.array_length,
                                             self.formatspecs)


class DisplayStringParser:
    def __init__(self, string) -> None:
        super().__init__()

        self.code_parts = []

        # TODO: This looks a lot like a state machine, maybe it should be written like one
        in_code = False
        skip_next = False
        current_code = None
        self.template_string = ""

        for c, next in lookahead_iter(string, 1):
            if skip_next:
                skip_next = False
                continue

            if in_code:
                if c == "}":
                    in_code = False
                    self.code_parts.append(FormatExpression(current_code))
                    current_code = None
                else:
                    current_code += c
            else:
                if c == "{" and next == "{":
                    # Found an escaped {
                    skip_next = True
                    self.template_string += "{{"
                elif c == "}" and next == "}":
                    skip_next = True
                    self.template_string += "}}"
                elif c == "{":
                    # Saw the start of a code block
                    in_code = True
                    current_code = ""
                    self.template_string += "{{{}}}".format(len(self.code_parts))
                else:
                    self.template_string += c

    def __str__(self) -> str:
        return '"' + self.template_string + '" (' + ", ".join((str(x) for x in self.code_parts)) + ")"

    def __repr__(self) -> str:
        return "<{}: \"{}\" ({})>".format(self.__class__.__name__, self.template_string,
                                          ",".join((repr(x) for x in self.code_parts)))


class DisplayString:

    def __init__(self, parser: DisplayStringParser, condition: str) -> None:
        super().__init__()
        self.condition = condition
        self.parser = parser

    def __str__(self) -> str:
        return 'if ({}) -> "{}"'.format(self.condition, self.parser)

    def __repr__(self) -> str:
        return "<{}: if ({!r}) {!r}>".format(self.__class__.__name__, self.condition, self.parser)


class ExpandElement:
    pass


class ExpandItem(ExpandElement):
    def __init__(self, name: str, expression: FormatExpression, condition: str):
        self.name = name
        self.expression = expression
        self.condition = condition


class ExpandIndexListItems(ExpandElement):

    def __init__(self, condition: str, size_expr: str, value_node: str) -> None:
        super().__init__()
        self.condition = condition
        self.value_node = value_node
        self.size_expr = size_expr


class NatvisType:
    expand_items: List[ExpandElement]

    def __init__(self, element: Element) -> None:
        super().__init__()

        name = element.get("Name")
        self.template_type = templates.parse_template_type(name)

        self.display_parsers = []
        self.expand_items = None

        for child in element:
            if child.tag == "DisplayString":
                condition = child.get("Condition", None)

                self.display_parsers.append(DisplayString(DisplayStringParser(child.text.lstrip().rstrip()), condition))
            elif child.tag == "Expand":
                self.expand_items = []

                self._process_expand(child)

    def _parse_item_element(self, element):
        name = element.get("Name")
        condition = element.get("Condition", None)
        expression = FormatExpression(element.text.lstrip().rstrip())
        self.expand_items.append(ExpandItem(name, expression, condition))

    def _parse_index_list_items_element(self, element: Element):
        size_el = element.find("Size")
        value_node_el = element.find("ValueNode")

        if size_el is None or value_node_el is None:
            return

        self.expand_items.append(ExpandIndexListItems(element.get("Condition", None), size_el.text.lstrip().rstrip(),
                                                      value_node_el.text.lstrip().rstrip()))

    def _process_expand(self, element):
        for child in element:
            if child.tag == "Item":
                self._parse_item_element(child)
            elif child.tag == "IndexListItems":
                self._parse_index_list_items_element(child)

    def typename_matches(self, typename: templates.TemplateType, template_args: List[str] = None) -> bool:
        if template_args is None:
            template_args = []
        return self.template_type.matches(typename, template_args)

    def enumerate_expressions(self) -> Iterator[Tuple[str, bool]]:
        for parser in self.display_parsers:
            if parser.condition is not None:
                yield parser.condition, True

            for code in parser.parser.code_parts:
                yield code.base_expression, True

        if self.expand_items is None:
            return

        for expand in self.expand_items:
            if isinstance(expand, ExpandItem):
                if expand.condition is not None:
                    yield expand.condition, True

                yield expand.expression.base_expression, True
            elif isinstance(expand, ExpandIndexListItems):
                if expand.condition is not None:
                    yield expand.condition, True

                yield expand.size_expr, True
                yield expand.value_node, True


def remove_namespace(doc, namespace):
    """Remove namespace in the passed document in place."""
    ns = u'{%s}' % namespace
    nsl = len(ns)
    for elem in doc.getiterator():
        if elem.tag.startswith(ns):
            elem.tag = elem.tag[nsl:]


class NatvisDocument:
    def __init__(self, document: ElementTree) -> None:
        super().__init__()

        self.types = []

        root = document.getroot()

        remove_namespace(root, "http://schemas.microsoft.com/vstudio/debugger/natvis/2010")

        for child in root:
            if child.tag == "Type":
                self.types.append(NatvisType(child))

    @classmethod
    def parse_file(cls, path):
        logger.log_message("Parsing natvis document '" + path + "'")
        return NatvisDocument(ElementTree.parse(path))


def _find_natvis(filename: str) -> Iterator[str]:
    dir = filename
    if not os.path.isdir(dir):
        dir = os.path.dirname(dir)

    while os.path.dirname(dir) != dir:  # Search until we find the root dir
        for child in os.listdir(dir):
            path = os.path.join(dir, child)

            if not os.path.isfile(path):
                continue

            if path.endswith(".natvis"):
                yield path

        dir = os.path.dirname(dir)


class NatvisTypeInstance:
    VAR_REGEX = re.compile("\$([\d\w])+")

    def __init__(self, type: NatvisType, template_args: List[str]) -> None:
        super().__init__()
        self.template_args = template_args
        self.type = type

    def replace_vars(self, expression: str, **kwargs: str) -> str:
        format = NatvisTypeInstance.VAR_REGEX.sub(r"{\1}", expression)

        args = {}
        for i, arg in enumerate(self.template_args):
            args["T" + str(i + 1)] = arg

        args.update(kwargs)

        return format.format(**args)

    @staticmethod
    def match_type(typename: templates.TemplateType, type: NatvisType) -> Optional['NatvisTypeInstance']:
        args = []
        if not type.template_type.matches(typename, args):
            return None
        return NatvisTypeInstance(type, args)


class NatvisManager:
    loaded_types: List[NatvisType]

    def __init__(self) -> None:
        super().__init__()

        self.loaded_types = []
        self.loaded_files = set()

    def load_natvis_file(self, path):
        if path in self.loaded_files:
            return  # Avoid loading the same file more than once
        self.loaded_files.add(path)

        doc = NatvisDocument.parse_file(path)
        if doc is None:
            return

        for type in doc.types:
            self.loaded_types.append(type)

    def lookup_types(self, typename: templates.TemplateType, filename: str = None) -> Iterator[NatvisTypeInstance]:
        for loaded in self.loaded_types:
            instance = NatvisTypeInstance.match_type(typename, loaded)
            if instance is not None:
                yield instance

        if filename is not None:
            self._load_natvis_files(filename)

            # Try again with the new files
            for loaded in self.loaded_types:
                instance = NatvisTypeInstance.match_type(typename, loaded)
                if instance is not None:
                    yield instance

    def lookup_type(self, typename: templates.TemplateType, filename: str = None) -> Optional[NatvisType]:
        return next(self.lookup_types(typename, filename), None)

    def _load_natvis_files(self, filename):
        for natvis in _find_natvis(filename):
            self.load_natvis_file(natvis)
