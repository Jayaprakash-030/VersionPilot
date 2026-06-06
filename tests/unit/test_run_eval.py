from eval.run_eval import summarize


def test_empty_summary_includes_unknown_risk_bucket():
    assert summarize([])["risk_distribution"]["Unknown"] == 0


def test_summary_preserves_unknown_and_unexpected_risks():
    results = [
        {"health_score": 80, "risk_level": "Low", "failed_steps": []},
        {"health_score": 0, "risk_level": "Unknown", "failed_steps": ["dependency_parser"]},
        {"health_score": 50, "risk_level": "Unverified", "failed_steps": []},
    ]

    distribution = summarize(results)["risk_distribution"]

    assert distribution["Low"] == 1
    assert distribution["Unknown"] == 1
    assert distribution["Other"] == 1
