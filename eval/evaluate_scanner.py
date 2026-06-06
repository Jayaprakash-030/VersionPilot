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
        "metrics": calculate_detection_metrics(actual, expected),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate one deprecated API scanner fixture")
    parser.add_argument("fixture_path", help="Path to a scanner fixture directory")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = evaluate_fixture(args.fixture_path)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
