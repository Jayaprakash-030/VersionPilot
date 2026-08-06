from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.analysis.deprecated_api_scanner import DeprecatedAPIScanner
from eval.metrics import FindingKey, calculate_detection_metrics


def evaluate_fixture(fixture_path: str | Path) -> dict[str, object]:
    """Run the scanner against one fixture directory and return its metrics."""
    fixture = Path(fixture_path)
    rules = json.loads((fixture / "rules.json").read_text(encoding="utf-8"))
    expected_data = json.loads((fixture / "expected.json").read_text(encoding="utf-8"))

    scanner = DeprecatedAPIScanner(rules=rules)
    findings = scanner.scan_python_file(str(fixture / "source.py"))

    actual: list[FindingKey] = [(finding.symbol, finding.line) for finding in findings]
    expected: list[FindingKey] = [
        (item["symbol"], item["line"]) for item in expected_data
    ]

    return {
        "fixture": fixture.name,
        "actual": actual,
        "expected": expected,
        "passed": set(actual) == set(expected),
        "metrics": calculate_detection_metrics(actual, expected),
    }


def evaluate_suite(fixtures_path: str | Path) -> dict[str, object]:
    """Evaluate every fixture directory and return aggregate metrics."""
    root = Path(fixtures_path)
    results = [
        evaluate_fixture(fixture)
        for fixture in sorted(root.iterdir())
        if fixture.is_dir()
    ]

    actual: list[FindingKey] = []
    expected: list[FindingKey] = []
    for result in results:
        fixture_name = str(result["fixture"])
        actual.extend(
            (f"{fixture_name}/{symbol}", line)
            for symbol, line in result["actual"]
        )
        expected.extend(
            (f"{fixture_name}/{symbol}", line)
            for symbol, line in result["expected"]
        )

    return {
        "fixture_count": len(results),
        "passed_fixture_count": sum(bool(result["passed"]) for result in results),
        "failed_fixtures": [
            result["fixture"] for result in results if not result["passed"]
        ],
        "metrics": calculate_detection_metrics(actual, expected),
        "fixtures": results,
    }


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for the deprecated API scanner evaluator."""
    parser = argparse.ArgumentParser(description="Evaluate deprecated API scanner fixtures")
    parser.add_argument("fixtures_path", help="Path to one fixture or a fixture root")
    return parser.parse_args()


def main() -> None:
    """Run scanner evaluation for a fixture or fixture suite and print JSON."""
    args = parse_args()
    path = Path(args.fixtures_path)
    result = (
        evaluate_fixture(path)
        if (path / "source.py").exists()
        else evaluate_suite(path)
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
