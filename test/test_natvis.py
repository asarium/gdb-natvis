import os
import unittest

import parser
from natvis import NatvisDocument, DisplayStringParser, FormatSpecifiers, NatvisManager


class DisplayStringParserTestCase(unittest.TestCase):
    def test_simple(self):
        parser = DisplayStringParser("{x}")

        self.assertEqual("{0}", parser.template_string)

        self.assertEqual(1, len(parser.code_parts))

        self.assertEqual("x", parser.code_parts[0].base_expression)
        self.assertIsNone(parser.code_parts[0].formatspecs)

    def test_simple_with_text(self):
        parser = DisplayStringParser("{x}, {y}")

        self.assertEqual("{0}, {1}", parser.template_string)

        self.assertEqual(2, len(parser.code_parts))
        self.assertEqual("x", parser.code_parts[0].base_expression)
        self.assertEqual("y", parser.code_parts[1].base_expression)

        self.assertIsNone(parser.code_parts[0].formatspecs)
        self.assertIsNone(parser.code_parts[1].formatspecs)

    def test_simple_with_format(self):
        parser = DisplayStringParser("({x}, {y}, {z}), {w}")

        self.assertEqual("({0}, {1}, {2}), {3}", parser.template_string)

        self.assertEqual(4, len(parser.code_parts))
        self.assertEqual("x", parser.code_parts[0].base_expression)
        self.assertEqual("y", parser.code_parts[1].base_expression)
        self.assertEqual("z", parser.code_parts[2].base_expression)
        self.assertEqual("w", parser.code_parts[3].base_expression)

        self.assertIsNone(parser.code_parts[0].formatspecs)
        self.assertIsNone(parser.code_parts[1].formatspecs)
        self.assertIsNone(parser.code_parts[2].formatspecs)
        self.assertIsNone(parser.code_parts[3].formatspecs)

    def test_escape(self):
        parser = DisplayStringParser("{{({x}, {y}, {z}), {w}}}")

        self.assertEqual("{{({0}, {1}, {2}), {3}}}", parser.template_string)

        self.assertEqual(4, len(parser.code_parts))
        self.assertEqual("x", parser.code_parts[0].base_expression)
        self.assertEqual("y", parser.code_parts[1].base_expression)
        self.assertEqual("z", parser.code_parts[2].base_expression)
        self.assertEqual("w", parser.code_parts[3].base_expression)

        self.assertIsNone(parser.code_parts[0].formatspecs)
        self.assertIsNone(parser.code_parts[1].formatspecs)
        self.assertIsNone(parser.code_parts[2].formatspecs)
        self.assertIsNone(parser.code_parts[3].formatspecs)

    def test_format(self):
        parser = DisplayStringParser("{x,d}")

        self.assertEqual("{0}", parser.template_string)

        self.assertEqual(1, len(parser.code_parts))
        self.assertEqual("x", parser.code_parts[0].base_expression)

        self.assertEqual([FormatSpecifiers.DECIMAL_INT], parser.code_parts[0].formatspecs)


class NatvisTestCase(unittest.TestCase):
    def print_document(self, doc: NatvisDocument):
        for type in doc.types:
            print(type.name + ":")
            for parser in type.display_parsers:
                print("  " + repr(parser))

    def test_glm_parsing(self):
        path = os.path.join(os.path.dirname(__file__), "glm.natvis")

        doc = NatvisDocument.parse_file(path)

        self.assertEqual(len(doc.types), 6)

        self.print_document(doc)

    def test_gsl_parsing(self):
        path = os.path.join(os.path.dirname(__file__), "GSL.natvis")

        doc = NatvisDocument.parse_file(path)

        self.assertEqual(len(doc.types), 9)

        self.print_document(doc)

    def test_lua_parsing(self):
        path = os.path.join(os.path.dirname(__file__), "lua.natvis")

        doc = NatvisDocument.parse_file(path)

        self.assertEqual(len(doc.types), 10)

        self.print_document(doc)


class NatvisManagerTestCase(unittest.TestCase):
    def test_lookup_type(self):
        manager = NatvisManager()

        manager.load_natvis_file(os.path.join(os.path.dirname(__file__), "glm.natvis"))

        self.assertIsNotNone(manager.lookup_type("glm::tvec1<float>"))
        self.assertIsNotNone(manager.lookup_type("glm::tvec1<int>"))

        self.assertIsNotNone(manager.lookup_type("glm::tvec2<float>"))
        self.assertIsNotNone(manager.lookup_type("glm::tvec2<int>"))

        self.assertIsNotNone(manager.lookup_type("glm::tvec3<float>"))
        self.assertIsNotNone(manager.lookup_type("glm::tvec3<int>"))

        self.assertIsNotNone(manager.lookup_type("glm::tvec4<float>"))
        self.assertIsNotNone(manager.lookup_type("glm::tvec4<int>"))

        self.assertIsNone(manager.lookup_type("lua_State"))


class ParserTestCase(unittest.TestCase):
    def test_parser(self):
        manager = NatvisManager()

        manager.load_natvis_file(os.path.join(os.path.dirname(__file__), "lua.natvis"))

        for type in manager.loaded_types:
            for display in type.display_parsers:
                for part in display.parser.code_parts:
                    parser.evaluate_expression(part.base_expression)
