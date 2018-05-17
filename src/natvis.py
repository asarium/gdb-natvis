import os
import re
from enum import Enum
from typing import Iterator, Tuple, Optional, List
from xml.etree import ElementTree
from xml.etree.ElementTree import Element

import logger


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


class ExpandItem:
    def __init__(self, name: str, expression: FormatExpression, condition: str):
        self.name = name
        self.expression = expression
        self.condition = condition


class NatvisType:
    expand_items: List[ExpandItem]

    def __init__(self, element: Element) -> None:
        super().__init__()

        self.name = element.get("Name")
        self.name_regex = re.compile("^" + re.escape(self.name).replace("\\*", ".+") + "$")
        self.display_parsers = []
        self.expand_items = None

        for child in element:
            if child.tag == "DisplayString":
                condition = child.get("Condition", None)

                self.display_parsers.append(DisplayString(DisplayStringParser(child.text), condition))
            elif child.tag == "Expand":
                self.expand_items = []

                self._process_expand(child)

    def _parse_item_element(self, element):
        name = element.get("Name")
        condition = element.get("Condition", None)
        expression = FormatExpression(element.text)
        self.expand_items.append(ExpandItem(name, expression, condition))

    def _process_expand(self, element):
        for child in element:
            if child.tag == "Item":
                self._parse_item_element(child)

    def typename_matches(self, typename) -> bool:
        if self.name_regex.match(typename):
            return True
        else:
            return False


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
    def parse_file(self, path):
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


class NatvisManager:
    loaded_types: List[NatvisType]

    def __init__(self) -> None:
        super().__init__()

        self.loaded_types = []
        self.loaded_files = set()
        self.unknown_types = set()  # This stores all types of which the lookup failed

    def load_natvis_file(self, path):
        if path in self.loaded_files:
            return  # Avoid loading the same file more than once
        self.loaded_files.add(path)

        doc = NatvisDocument.parse_file(path)
        if doc is None:
            return

        for type in doc.types:
            self.loaded_types.append(type)

    def lookup_type(self, typename: str, filename: str = None) -> Optional[NatvisType]:
        if typename in self.unknown_types:
            # Quickly return if we know we won't find this type
            return None

        for loaded in self.loaded_types:
            if loaded.typename_matches(typename):
                return loaded

        if filename is not None:
            self._load_natvis_files(filename)

            # Try again with the new files
            for loaded in self.loaded_types:
                if loaded.typename_matches(typename):
                    return loaded

        # Type not found
        self.unknown_types.add(typename)
        return None

    def _load_natvis_files(self, filename):
        for natvis in _find_natvis(filename):
            self.load_natvis_file(natvis)
