from eval.metrics import calculate_detection_metrics


def test_calculate_detection_metrics_for_partial_match():
    actual = [("flask.ext", 1), ("numpy.float", 7)]
    expected = [("flask.ext", 1), ("requests.packages.urllib3", 4)]

    metrics = calculate_detection_metrics(actual, expected)

    assert metrics == {
        "true_positives": 1,
        "false_positives": 1,
        "false_negatives": 1,
        "precision": 0.5,
        "recall": 0.5,
        "f1": 0.5,
        "exact_line_location_accuracy": 1.0,
    }


def test_calculate_detection_metrics_for_perfect_match():
    findings = [("flask.ext", 1), ("numpy.float", 7)]

    metrics = calculate_detection_metrics(findings, findings)

    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["f1"] == 1.0
    assert metrics["exact_line_location_accuracy"] == 1.0


def test_calculate_detection_metrics_for_empty_inputs():
    metrics = calculate_detection_metrics([], [])

    assert metrics["true_positives"] == 0
    assert metrics["false_positives"] == 0
    assert metrics["false_negatives"] == 0
    assert metrics["precision"] == 0.0
    assert metrics["recall"] == 0.0
    assert metrics["f1"] == 0.0
    assert metrics["exact_line_location_accuracy"] == 0.0


def test_calculate_detection_metrics_ignores_duplicate_findings():
    findings = [("flask.ext", 1), ("flask.ext", 1)]

    metrics = calculate_detection_metrics(findings, [("flask.ext", 1)])

    assert metrics["true_positives"] == 1
    assert metrics["false_positives"] == 0
    assert metrics["false_negatives"] == 0


def test_calculate_detection_metrics_measures_wrong_line_separately():
    metrics = calculate_detection_metrics(
        [("flask.escape", 4)],
        [("flask.escape", 3)],
    )

    assert metrics["recall"] == 0.0
    assert metrics["exact_line_location_accuracy"] == 0.0
