import unittest

from app.risk_scoring import compute_health_score, load_scoring_config


class TestRiskScoring(unittest.TestCase):
    def test_compute_health_score_is_deterministic_and_weighted(self) -> None:
        config = load_scoring_config("config/scoring_v1.yaml")

        score1, _ = compute_health_score(80.0, 70.0, 60.0, config)
        score2, _ = compute_health_score(80.0, 70.0, 60.0, config)

        self.assertEqual(score1, score2)
        self.assertEqual(score1, 70.0)


if __name__ == "__main__":
    unittest.main()
