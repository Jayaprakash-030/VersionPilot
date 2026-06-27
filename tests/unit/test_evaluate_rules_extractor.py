from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from app.tools.rules_extractor import RulesExtractor
from eval.evaluate_rules_extractor import evaluate_fixture, evaluate_suite


def _mock_extractor(response_text: str) -> RulesExtractor:
    llm = MagicMock()
    llm.call.return_value = response_text
    return RulesExtractor(llm_client=llm)


def _write_fixture(
    root: Path,
    name: str,
    expected: list[dict[str, str]],
    package: str = "examplelib",
) -> Path:
    fixture = root / name
    fixture.mkdir()
    (fixture / "metadata.json").write_text(
        json.dumps({"package": package}),
        encoding="utf-8",
    )
    (fixture / "release_notes.txt").write_text(
        "examplelib.LegacySession is deprecated; use examplelib.Session.",
        encoding="utf-8",
    )
    (fixture / "expected.json").write_text(json.dumps(expected), encoding="utf-8")
    return fixture


def test_evaluate_fixture_reports_perfect_rules_extraction_match(tmp_path):
    expected = [
        {
            "symbol": "examplelib.LegacySession",
            "replacement": "examplelib.Session",
            "severity": "medium",
        }
    ]
    fixture = _write_fixture(tmp_path, "deprecated_class", expected)
    extractor = _mock_extractor(json.dumps(expected))

    result = evaluate_fixture(fixture, extractor=extractor)

    assert result["fixture"] == "deprecated_class"
    assert result["valid_schema"] is True
    assert result["passed"] is True
    assert result["metrics"]["precision"] == 1.0
    assert result["metrics"]["recall"] == 1.0
    assert result["replacement_accuracy"] == 1.0
    assert result["severity_accuracy"] == 1.0


def test_evaluate_fixture_measures_wrong_llm_symbol(tmp_path):
    expected = [
        {
            "symbol": "examplelib.LegacySession",
            "replacement": "examplelib.Session",
            "severity": "medium",
        }
    ]
    actual = [
        {
            "symbol": "examplelib.OtherSession",
            "replacement": "examplelib.Session",
            "severity": "medium",
        }
    ]
    fixture = _write_fixture(tmp_path, "wrong_symbol", expected)
    extractor = _mock_extractor(json.dumps(actual))

    result = evaluate_fixture(fixture, extractor=extractor)

    assert result["passed"] is False
    assert result["metrics"]["true_positives"] == 0
    assert result["metrics"]["false_positives"] == 1
    assert result["metrics"]["false_negatives"] == 1


def test_evaluate_fixture_marks_malformed_llm_output_invalid(tmp_path):
    fixture = _write_fixture(
        tmp_path,
        "malformed",
        [
            {
                "symbol": "examplelib.LegacySession",
                "replacement": "examplelib.Session",
                "severity": "medium",
            }
        ],
    )
    extractor = _mock_extractor("not valid json")

    result = evaluate_fixture(fixture, extractor=extractor)

    assert result["status"] == "error"
    assert result["valid_schema"] is False
    assert result["actual"] == []
    assert result["metrics"]["false_negatives"] == 1


def test_evaluate_suite_aggregates_rules_extractor_metrics(tmp_path):
    first = [
        {
            "symbol": "examplelib.LegacySession",
            "replacement": "examplelib.Session",
            "severity": "medium",
        }
    ]
    second: list[dict[str, str]] = []
    _write_fixture(tmp_path, "deprecated_class", first)
    _write_fixture(tmp_path, "no_deprecations", second)

    llm = MagicMock()
    llm.call.side_effect = [json.dumps(first), json.dumps(second)]
    extractor = RulesExtractor(llm_client=llm)

    result = evaluate_suite(tmp_path, extractor=extractor)

    assert result["fixture_count"] == 2
    assert result["passed_fixture_count"] == 2
    assert result["failed_fixtures"] == []
    assert result["metrics"]["f1"] == 1.0
    assert result["valid_schema_rate"] == 1.0
    assert result["correct_empty_result_rate"] == 1.0
