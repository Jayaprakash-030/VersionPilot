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
                {
                    "category": "breaking_change",
                    "text": "BREAKING: Removed old hook",
                    "severity": "high",
                    "package": "urllib3",
                    "from_version": "1.26",
                    "to_version": "2.7.0",
                    "confidence": "regex_heuristic",
                },
                {"category": "deprecation", "text": "Deprecated config key", "severity": "medium"},
            ]
        }

        plan = planner.generate_plan(deprecated_findings, breaking_change_analysis)
        self.assertEqual(plan["total_steps"], 2)
        self.assertEqual(plan["effort_level"], "low")
        step_types = [s["type"] for s in plan["steps"]]
        self.assertIn("deprecated_api_replacement", step_types)
        self.assertIn("breaking_change_review", step_types)

        breaking = next(s for s in plan["steps"] if s["type"] == "breaking_change_review")
        self.assertEqual(breaking["package"], "urllib3")
        self.assertEqual(breaking["version_span"], "1.26→2.7.0")
        self.assertEqual(breaking["confidence"], "regex_heuristic")

    def test_dedupes_and_caps_breaking_steps_per_package(self) -> None:
        planner = MigrationPlanner()
        findings = [
            {
                "category": "breaking_change",
                "text": f"Removed API surface item number {i} from public package",
                "severity": "high",
                "package": "urllib3",
            }
            for i in range(6)
        ]
        findings.append(
            {
                "category": "breaking_change",
                "text": "Removed API surface item number 1 from public package",
                "severity": "high",
                "package": "urllib3",
            }
        )
        plan = planner.generate_plan([], {"findings": findings})
        breaking = [s for s in plan["steps"] if s["type"] == "breaking_change_review"]
        self.assertEqual(len(breaking), 3)


if __name__ == "__main__":
    unittest.main()
