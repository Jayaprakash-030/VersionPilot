from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from app.tools.rules_extractor import RulesExtractor

RuleKey = str


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_rule(rule: dict[str, Any]) -> dict[str, str]:
    return {
        "symbol": str(rule.get("symbol", "")).strip(),
        "replacement": str(rule.get("replacement", "")).strip(),
        "severity": str(rule.get("severity", "")).strip().lower(),
    }


def _normalize_rules(rules: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        normalized
        for rule in rules
        if isinstance(rule, dict)
        for normalized in [_normalize_rule(rule)]
        if normalized["symbol"]
    ]


def _symbol_metrics(
    actual: Iterable[dict[str, str]],
    expected: Iterable[dict[str, str]],
) -> dict[str, int | float]:
    actual_symbols = {rule["symbol"] for rule in actual}
    expected_symbols = {rule["symbol"] for rule in expected}

    true_positives = len(actual_symbols & expected_symbols)
    false_positives = len(actual_symbols - expected_symbols)
    false_negatives = len(expected_symbols - actual_symbols)

    precision = (
        true_positives / (true_positives + false_positives)
        if true_positives + false_positives
        else 0.0
    )
    recall = (
        true_positives / (true_positives + false_negatives)
        if true_positives + false_negatives
        else 0.0
    )
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    return {
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _field_accuracy(
    actual: Iterable[dict[str, str]],
    expected: Iterable[dict[str, str]],
    field: str,
) -> float:
    actual_by_symbol = {rule["symbol"]: rule for rule in actual}
    expected_by_symbol = {rule["symbol"]: rule for rule in expected}
    matched_symbols = set(actual_by_symbol) & set(expected_by_symbol)
    if not matched_symbols:
        return 0.0

    correct = sum(
        actual_by_symbol[symbol].get(field, "") == expected_by_symbol[symbol].get(field, "")
        for symbol in matched_symbols
    )
    return correct / len(matched_symbols)


def _is_valid_rule_list(raw_rules: object) -> bool:
    if not isinstance(raw_rules, list):
        return False
    return all(
        isinstance(rule, dict)
        and isinstance(rule.get("symbol"), str)
        and isinstance(rule.get("replacement", ""), str)
        and isinstance(rule.get("severity", ""), str)
        for rule in raw_rules
    )


def evaluate_fixture(
    fixture_path: str | Path,
    extractor: RulesExtractor | None = None,
) -> dict[str, object]:
    """Run RulesExtractor against one release-note fixture."""
    fixture = Path(fixture_path)
    metadata = _load_json(fixture / "metadata.json")
    package_name = metadata["package"]
    notes_text = (fixture / "release_notes.txt").read_text(encoding="utf-8")
    expected_raw = _load_json(fixture / "expected.json")

    extractor = extractor or RulesExtractor()
    actual_raw = extractor.extract_rules(package_name, notes_text)
    actual = _normalize_rules(actual_raw)
    expected = _normalize_rules(expected_raw)
    metrics = _symbol_metrics(actual, expected)

    valid_schema = extractor.last_extraction_status == "ok" and _is_valid_rule_list(actual_raw)

    return {
        "fixture": fixture.name,
        "package": package_name,
        "status": extractor.last_extraction_status,
        "error": extractor.last_extraction_error,
        "valid_schema": valid_schema,
        "correct_empty_result": not actual and not expected,
        "actual": actual,
        "expected": expected,
        "passed": set(rule["symbol"] for rule in actual)
        == set(rule["symbol"] for rule in expected)
        and _field_accuracy(actual, expected, "replacement") == (1.0 if expected else 0.0)
        and _field_accuracy(actual, expected, "severity") == (1.0 if expected else 0.0),
        "metrics": metrics,
        "replacement_accuracy": _field_accuracy(actual, expected, "replacement"),
        "severity_accuracy": _field_accuracy(actual, expected, "severity"),
    }


def evaluate_suite(
    fixtures_path: str | Path,
    extractor: RulesExtractor | None = None,
) -> dict[str, object]:
    """Evaluate every rules-extractor fixture and return aggregate metrics."""
    root = Path(fixtures_path)
    results = [
        evaluate_fixture(fixture, extractor=extractor)
        for fixture in sorted(root.iterdir())
        if fixture.is_dir()
    ]

    actual: list[dict[str, str]] = []
    expected: list[dict[str, str]] = []
    for result in results:
        fixture_name = str(result["fixture"])
        actual.extend(
            {**rule, "symbol": f"{fixture_name}/{rule['symbol']}"}
            for rule in result["actual"]  # type: ignore[index]
        )
        expected.extend(
            {**rule, "symbol": f"{fixture_name}/{rule['symbol']}"}
            for rule in result["expected"]  # type: ignore[index]
        )

    matched_results = [
        result
        for result in results
        if result["metrics"]["true_positives"]  # type: ignore[index]
    ]
    replacement_accuracies = [
        float(result["replacement_accuracy"]) for result in matched_results
    ]
    severity_accuracies = [
        float(result["severity_accuracy"]) for result in matched_results
    ]

    return {
        "fixture_count": len(results),
        "passed_fixture_count": sum(bool(result["passed"]) for result in results),
        "failed_fixtures": [
            result["fixture"] for result in results if not result["passed"]
        ],
        "valid_schema_rate": (
            sum(bool(result["valid_schema"]) for result in results) / len(results)
            if results
            else 0.0
        ),
        "correct_empty_result_rate": (
            sum(bool(result["correct_empty_result"]) for result in results)
            / sum(not result["expected"] for result in results)
            if any(not result["expected"] for result in results)
            else 0.0
        ),
        "metrics": _symbol_metrics(actual, expected),
        "replacement_accuracy": (
            sum(replacement_accuracies) / len(replacement_accuracies)
            if replacement_accuracies
            else 0.0
        ),
        "severity_accuracy": (
            sum(severity_accuracies) / len(severity_accuracies)
            if severity_accuracies
            else 0.0
        ),
        "fixtures": results,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate rules-extractor fixtures")
    parser.add_argument("fixtures_path", help="Path to one fixture or a fixture root")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path = Path(args.fixtures_path)
    result = (
        evaluate_fixture(path)
        if (path / "release_notes.txt").exists()
        else evaluate_suite(path)
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
