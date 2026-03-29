import unittest

from app.analysis.migration_planner import MigrationPlanner


class TestMigrationPlanner(unittest.TestCase):
    def test_generate_plan_combines_deprecated_and_breaking_inputs(self) -> None:
        planner = MigrationPlanner()
        deprecated_findings = [
            {
                "package": "flask",
                "symbol": "flask.ext",
                "file_path": "app.py",
                "line": 10,
                "replacement": "Use flask_sqlalchemy",
                "severity": "high",
            }
        ]
        breaking_change_analysis = {
            "findings": [
                {"category": "breaking_change", "text": "BREAKING: Removed old hook", "severity": "high"},
                {"category": "deprecation", "text": "Deprecated config key", "severity": "medium"},
            ]
        }

        plan = planner.generate_plan(deprecated_findings, breaking_change_analysis)
        self.assertEqual(plan["total_steps"], 2)
        self.assertEqual(plan["effort_level"], "low")
        step_types = [s["type"] for s in plan["steps"]]
        self.assertIn("deprecated_api_replacement", step_types)
        self.assertIn("breaking_change_review", step_types)


if __name__ == "__main__":
    unittest.main()
