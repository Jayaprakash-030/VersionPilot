import unittest

from app.dependency_parser import parse_pyproject_text, parse_requirements_text


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

    def test_parse_pyproject_text_extracts_project_and_poetry_dependencies(self) -> None:
        text = """
[project]
dependencies = ["fastapi>=0.110", "uvicorn==0.30.0"]

[tool.poetry.dependencies]
python = "^3.11"
requests = "^2.31.0"
"""
        deps = parse_pyproject_text(text)
        self.assertEqual(deps, ["fastapi", "uvicorn", "requests"])


if __name__ == "__main__":
    unittest.main()
