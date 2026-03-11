import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from app.dependency_parser import (
    DependencyParserError,
    fetch_dependencies,
    parse_pyproject_specs,
    parse_pyproject_text,
    parse_requirements_specs,
    parse_requirements_text,
)


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

    def test_parse_pyproject_text_includes_optional_dependencies(self) -> None:
        text = """
[project]
dependencies = ["fastapi>=0.110"]

[project.optional-dependencies]
dev = ["pytest>=8.0", "ruff==0.5.0"]
docs = ["mkdocs>=1.6", "pytest>=8.0"]
"""
        deps = parse_pyproject_text(text)
        self.assertEqual(deps, ["fastapi", "pytest", "ruff", "mkdocs"])

    def test_parse_pyproject_text_raises_for_invalid_toml(self) -> None:
        invalid_text = """
[project
dependencies = ["fastapi"]
"""
        with self.assertRaises(DependencyParserError):
            parse_pyproject_text(invalid_text)

    def test_parse_requirements_specs_extracts_version_when_present(self) -> None:
        text = "requests==2.31.0\nnumpy>=1.26\nflask\n"
        specs = parse_requirements_specs(text)
        self.assertEqual(specs[0].name, "requests")
        self.assertEqual(specs[0].version, "2.31.0")
        self.assertEqual(specs[1].name, "numpy")
        self.assertEqual(specs[1].version, "1.26")
        self.assertEqual(specs[2].name, "flask")
        self.assertIsNone(specs[2].version)

    def test_parse_pyproject_specs_extracts_poetry_version(self) -> None:
        text = """
[tool.poetry.dependencies]
python = "^3.11"
requests = "^2.31.0"
"""
        specs = parse_pyproject_specs(text)
        self.assertEqual(specs[0].name, "requests")
        self.assertEqual(specs[0].version, "^2.31.0")

    def test_fetch_dependencies_uses_available_source_when_other_fails(self) -> None:
        def fake_fetch(_repo_url: str, path: str, timeout_seconds: int = 8) -> str:
            if path == "requirements.txt":
                raise HTTPError(url="", code=500, msg="server error", hdrs=None, fp=None)
            if path == "pyproject.toml":
                return """
[project]
dependencies = ["fastapi>=0.110", "uvicorn==0.30.0"]
"""
            return ""

        with patch("app.dependency_parser._fetch_file_content", side_effect=fake_fetch):
            deps = fetch_dependencies("https://github.com/org/repo")

        self.assertEqual([d.name for d in deps], ["fastapi", "uvicorn"])


if __name__ == "__main__":
    unittest.main()
