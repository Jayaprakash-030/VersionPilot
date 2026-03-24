import unittest

from app.deprecated_api_scanner import DeprecatedAPIScanner


class TestDeprecatedApiScanner(unittest.TestCase):
    def test_scan_python_source_detects_flask_ext_usage(self) -> None:
        source = """
from flask.ext import sqlalchemy

app = object()
"""
        scanner = DeprecatedAPIScanner("data/deprecation_rules.json")
        findings = scanner.scan_python_source(source, file_path="sample.py")

        self.assertEqual(len(findings), 1)
        finding = findings[0]
        self.assertEqual(finding.package, "flask")
        self.assertEqual(finding.symbol, "flask.ext")
        self.assertEqual(finding.file_path, "sample.py")
        self.assertEqual(finding.severity, "high")
        self.assertTrue(finding.replacement)


if __name__ == "__main__":
    unittest.main()
