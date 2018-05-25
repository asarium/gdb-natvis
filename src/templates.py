import re
from typing import List, Tuple


class TemplateException(Exception):

    def __init__(self, input: str, pos: int, message: str) -> None:
        super().__init__('"{}":{}: {}'.format(input, pos, message))
        self.input = input
        self.pos = pos


class TemplateType:
    args: List['TemplateType']

    def __init__(self, name: str, args=None) -> None:
        super().__init__()

        if args is None:
            args = []
        self.name = name
        self.args = args

    @property
    def is_wildcard(self):
        return self.name == "*"

    def __repr__(self) -> str:
        return '<{}: {!r} [{}]>'.format(self.__class__.__name__, self.name, ",".join(repr(x) for x in self.args))

    def __str__(self) -> str:
        if len(self.args) <= 0:
            return self.name
        else:
            return '{}<{}>'.format(self.name, ", ".join(str(x) for x in self.args))

    def matches(self, other: 'TemplateType', matched_args: List[str] = None) -> bool:
        if self.is_wildcard:
            # All names match with wildcards
            if matched_args is not None:
                matched_args.append(other.name)
            return True

        if len(self.args) != len(other.args):
            return False

        for left, right in zip(self.args, other.args):
            if not left.matches(right, matched_args):
                return False

        return self.name == other.name


TEMPLATE_LIST_REGEX = re.compile("[<>,]")


def _skip_whitespace(input: str, start: int) -> int:
    while start < len(input) and input[start].isspace():
        start += 1
    return start


# This pretty much implements a recursive descent parser without all the nice things a parser generator provides
# Maybe this could be improved with a "real" parser generator...

def _template_type_parse_runner(input: str, start: int) -> Tuple[TemplateType, int]:
    match = TEMPLATE_LIST_REGEX.search(input, start)
    if match is None:
        # No terminating character found
        return TemplateType(input[start:].rstrip()), len(input)
    name_end = match.start(0)
    if name_end == -1:
        # main match group not found but we still got a matcher?
        return TemplateType(input[start:].rstrip()), len(input)

    char = match.group(0)
    if char == ">" or char == ",":
        # The next template character is the end so we do not have a template argument list
        return TemplateType(input[start:name_end].rstrip()), name_end

    assert char == "<"  # The regex should not match anything else
    # We have a template list so we need to parse that before we can return our type
    arg_start = _skip_whitespace(input, match.end(0))
    args = []
    while arg_start < len(input) and input[arg_start] != ">":
        arg_type, arg_end = _template_type_parse_runner(input, arg_start)
        args.append(arg_type)
        arg_start = _skip_whitespace(input, arg_end)

        if input[arg_start] == ",":
            # Skip over the comma
            arg_start = _skip_whitespace(input, arg_start + 1)

            if input[arg_start] == "<" or input[arg_start] == ">" or input[arg_start] == ",":
                raise TemplateException(input, arg_start + 1,
                                        'Expected a type name, got "{}" instead.'.format(input[arg_start]))
    if len(args) <= 0:
        raise TemplateException(input, arg_start + 1, 'Found type with template list but no parameters!')

    if arg_start >= len(input) or input[arg_start] != ">":
        raise TemplateException(input, arg_start + 1, 'Expected ">" but found "{}" instead!'
                                .format("<EOF>" if arg_start >= len(input) else input[arg_start]))
    arg_start += 1  # Consume the '>'

    return TemplateType(input[start:name_end], args), arg_start


def parse_template_type(input: str) -> TemplateType:
    type, end = _template_type_parse_runner(input, 0)
    if end < len(input):
        raise TemplateException(input, end + 1,
                                'Input remained after reading entire type! Additional string: {}'.format(input[end:]))
    return type
