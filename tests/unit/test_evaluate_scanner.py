import json

from eval.evaluate_scanner import evaluate_fixture, evaluate_suite


def test_evaluate_fixture_reports_perfect_direct_import_result():
    result = evaluate_fixture("eval/fixtures/deprecated_api/direct_import")

    assert result["fixture"] == "direct_import"
    assert result["actual"] == [("requests.packages.urllib3", 1)]
    assert result["expected"] == [("requests.packages.urllib3", 1)]
    assert result["passed"] is True
    assert result["metrics"]["f1"] == 1.0


def test_evaluate_fixture_measures_incorrect_result(tmp_path):
    (tmp_path / "source.py").write_text("import requests\n", encoding="utf-8")
    (tmp_path / "rules.json").write_text(
        json.dumps(
            {
                "requests": {
                    "deprecated_symbols": {
                        "requests.packages.urllib3": {
                            "replacement": "urllib3",
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "expected.json").write_text(
        json.dumps([{"symbol": "requests.packages.urllib3", "line": 1}]),
        encoding="utf-8",
    )

    result = evaluate_fixture(tmp_path)

    assert result["actual"] == []
    assert result["passed"] is False
    assert result["metrics"]["true_positives"] == 0
    assert result["metrics"]["false_negatives"] == 1
    assert result["metrics"]["recall"] == 0.0


def test_evaluate_suite_aggregates_all_fixture_results():
    result = evaluate_suite("eval/fixtures/deprecated_api")

    assert result["fixture_count"] == 12
    assert result["passed_fixture_count"] == 12
    assert result["failed_fixtures"] == []
    assert len(result["fixtures"]) == 12
    assert result["metrics"]["true_positives"] > 0
    assert result["metrics"]["false_negatives"] == 0
