import unittest

from app.dependency_parser import parse_requirements_text


class TestDependencyParser(unittest.TestCase):
    def test_parse_requirements_text_filters_and_extracts_packages(self) -> None:
        text = """
# comment
requests==2.31.0
numpy>=1.26
pandas; python_version >= '3.10'
-r extra.txt
--constraint constraints.txt

requests==2.31.0
"""
        deps = parse_requirements_text(text)
        self.assertEqual(deps, ["requests", "numpy", "pandas"])


if __name__ == "__main__":
    unittest.main()
