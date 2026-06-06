import json

from eval.evaluate_scanner import evaluate_fixture


def test_evaluate_fixture_reports_perfect_direct_import_result():
    result = evaluate_fixture("eval/fixtures/deprecated_api/direct_import")

    assert result["fixture"] == "direct_import"
    assert result["actual"] == [("requests.packages.urllib3", 1)]
    assert result["expected"] == [("requests.packages.urllib3", 1)]
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
    assert result["metrics"]["true_positives"] == 0
    assert result["metrics"]["false_negatives"] == 1
    assert result["metrics"]["recall"] == 0.0
