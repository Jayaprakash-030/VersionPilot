from __future__ import annotations

from app.analysis.deprecated_api_scanner import DeprecatedAPIScanner

DYNAMIC_RULES = {
    "requests": {
        "deprecated_symbols": {
            "requests.packages.urllib3": {
                "replacement": "urllib3",
                "severity": "high",
                "note": "Removed in requests 3.0",
            }
        }
    }
}

SOURCE_WITH_DEPRECATED = "import requests.packages.urllib3\n"
SOURCE_WITHOUT_DEPRECATED = "import requests\n"


# ---------------------------------------------------------------------------
# Dynamic rules skip file loading
# ---------------------------------------------------------------------------

def test_dynamic_rules_skips_file_loading():
    # No rules file exists at this path — should not raise
    scanner = DeprecatedAPIScanner(rules_path="nonexistent.json", rules=DYNAMIC_RULES)
    assert scanner.rules == DYNAMIC_RULES


def test_dynamic_rules_produce_findings():
    scanner = DeprecatedAPIScanner(rules=DYNAMIC_RULES)
    findings = scanner.scan_python_source(SOURCE_WITH_DEPRECATED)
    assert len(findings) == 1
    assert findings[0].symbol == "requests.packages.urllib3"
    assert findings[0].severity == "high"
    assert findings[0].package == "requests"


def test_dynamic_rules_no_findings_when_no_match():
    scanner = DeprecatedAPIScanner(rules=DYNAMIC_RULES)
    findings = scanner.scan_python_source(SOURCE_WITHOUT_DEPRECATED)
    assert findings == []


def test_empty_rules_dict_produces_no_findings():
    scanner = DeprecatedAPIScanner(rules={})
    findings = scanner.scan_python_source(SOURCE_WITH_DEPRECATED)
    assert findings == []


def test_module_alias_usage_produces_finding():
    rules = {
        "flask": {
            "deprecated_symbols": {
                "flask.escape": {
                    "replacement": "markupsafe.escape",
                    "severity": "high",
                    "note": "Removed from Flask",
                }
            }
        }
    }
    scanner = DeprecatedAPIScanner(rules=rules)

    findings = scanner.scan_python_source(
        "import flask as f\n\nescaped = f.escape('<p>')\n"
    )

    assert [(finding.symbol, finding.line) for finding in findings] == [
        ("flask.escape", 3)
    ]


def test_nested_attribute_usage_does_not_duplicate_finding():
    scanner = DeprecatedAPIScanner(rules=DYNAMIC_RULES)

    findings = scanner.scan_python_source(
        "import requests\n\nrequests.packages.urllib3.disable_warnings()\n"
    )

    assert [(finding.symbol, finding.line) for finding in findings] == [
        ("requests.packages.urllib3", 3)
    ]


def test_repeated_usage_on_different_lines_remains_separate():
    scanner = DeprecatedAPIScanner(rules=DYNAMIC_RULES)

    findings = scanner.scan_python_source(
        "import requests\n"
        "first = requests.packages.urllib3\n"
        "second = requests.packages.urllib3\n"
    )

    assert [(finding.symbol, finding.line) for finding in findings] == [
        ("requests.packages.urllib3", 2),
        ("requests.packages.urllib3", 3),
    ]


# ---------------------------------------------------------------------------
# Backward compatibility — file-based rules still work
# ---------------------------------------------------------------------------

def test_file_based_rules_still_work():
    scanner = DeprecatedAPIScanner(rules_path="data/deprecation_rules.json")
    assert isinstance(scanner.rules, dict)
