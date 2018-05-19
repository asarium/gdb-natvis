import unittest

import templates
from templates import TemplateException


class TemplateParserTestCase(unittest.TestCase):
    def test_non_template(self):
        template_type = templates.parse_template_type("test::non_template_class")

        self.assertEqual("test::non_template_class", template_type.name)

        self.assertEqual(0, len(template_type.args))

    def test_simple_list(self):
        template_type = templates.parse_template_type("test::template_class<float>")

        self.assertEqual("test::template_class", template_type.name)

        self.assertEqual(1, len(template_type.args))

        self.assertEqual("float", template_type.args[0].name)
        self.assertEqual(0, len(template_type.args[0].args))

    def test_multiple_args(self):
        template_type = templates.parse_template_type("test::template_class<float, test, const char*>")

        self.assertEqual("test::template_class", template_type.name)

        self.assertEqual(3, len(template_type.args))

        self.assertEqual("float", template_type.args[0].name)
        self.assertEqual(0, len(template_type.args[0].args))

        self.assertEqual("test", template_type.args[1].name)
        self.assertEqual(0, len(template_type.args[1].args))

        self.assertEqual("const char*", template_type.args[2].name)
        self.assertEqual(0, len(template_type.args[2].args))

    def test_nested_args(self):
        template_type = templates.parse_template_type("test::template_class<vector<test>>")

        self.assertEqual("test::template_class", template_type.name)

        self.assertEqual(1, len(template_type.args))

        vector_type = template_type.args[0]
        self.assertEqual("vector", vector_type.name)
        self.assertEqual(1, len(vector_type.args))

        self.assertEqual("test", vector_type.args[0].name)
        self.assertEqual(0, len(vector_type.args[0].args))

    def test_wildcard(self):
        template_type = templates.parse_template_type("test::template_class<*>")

        self.assertEqual("test::template_class", template_type.name)

        self.assertEqual(1, len(template_type.args))

        self.assertTrue(template_type.args[0].is_wildcard)
        self.assertEqual(0, len(template_type.args[0].args))

    def test_nested_wildcard(self):
        template_type = templates.parse_template_type("test::template_class<vector<*>>")

        self.assertEqual("test::template_class", template_type.name)

        self.assertEqual(1, len(template_type.args))

        vector_type = template_type.args[0]
        self.assertEqual("vector", vector_type.name)
        self.assertEqual(1, len(vector_type.args))

        self.assertTrue(vector_type.args[0].is_wildcard)
        self.assertEqual(0, len(vector_type.args[0].args))

    def test_missing_closing_brance(self):
        with self.assertRaises(TemplateException):
            templates.parse_template_type("test::template_class<")

    def test_missing_opening_brance(self):
        with self.assertRaises(TemplateException):
            templates.parse_template_type("test::template_class>")

    def test_empty_arg(self):
        with self.assertRaises(TemplateException):
            templates.parse_template_type("test::template_class<>")

    def test_empty_comma_arg(self):
        with self.assertRaises(TemplateException):
            templates.parse_template_type("test::template_class<float,>")

    def test_empty_comma_comma_arg(self):
        with self.assertRaises(TemplateException):
            templates.parse_template_type("test::template_class<float,,>")
