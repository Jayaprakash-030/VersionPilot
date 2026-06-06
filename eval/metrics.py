from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

FindingKey = tuple[str, int]


def calculate_detection_metrics(
    actual: Iterable[FindingKey],
    expected: Iterable[FindingKey],
) -> dict[str, int | float]:
    """Calculate exact-match detection metrics for normalized finding keys."""
    actual_set = set(actual)
    expected_set = set(expected)

    true_positives = len(actual_set & expected_set)
    false_positives = len(actual_set - expected_set)
    false_negatives = len(expected_set - actual_set)
    actual_symbols = Counter(symbol for symbol, _line in actual_set)
    expected_symbols = Counter(symbol for symbol, _line in expected_set)
    symbol_matches = sum(
        min(count, expected_symbols[symbol])
        for symbol, count in actual_symbols.items()
    )

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
    exact_line_location_accuracy = (
        true_positives / symbol_matches if symbol_matches else 0.0
    )

    return {
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "exact_line_location_accuracy": exact_line_location_accuracy,
    }
