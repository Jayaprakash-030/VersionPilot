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

        deprecated = next(s for s in plan["steps"] if s["type"] == "deprecated_api_replacement")
        self.assertIn("Use flask_sqlalchemy", deprecated["action"])
        self.assertIn("app.py:10", deprecated["action"])

        breaking = next(s for s in plan["steps"] if s["type"] == "breaking_change_review")
        self.assertEqual(breaking["package"], "urllib3")
        self.assertEqual(breaking["version_span"], "1.26→2.7.0")
        self.assertEqual(breaking["confidence"], "regex_heuristic")

    def test_deprecated_api_empty_replacement_creates_deterministic_action(self) -> None:
        planner = MigrationPlanner()
        deprecated_findings = [
            {
                "package": "pandas",
                "symbol": "fastparquet",
                "file_path": "pandas/tests/io/test_parquet.py",
                "line": 45,
                "replacement": "",
                "severity": "high",
            }
        ]
        plan = planner.generate_plan(deprecated_findings, {"findings": []})
        self.assertEqual(plan["total_steps"], 1)
        step = plan["steps"][0]
        self.assertEqual(step["type"], "deprecated_api_replacement")
        self.assertIn("`fastparquet`", step["action"])
        self.assertIn("test_parquet.py:45", step["action"])
        self.assertIn("no replacement", step["action"])

    def test_bare_symbol_replacement_is_polished_into_sentence(self) -> None:
        planner = MigrationPlanner()
        plan = planner.generate_plan(
            [
                {
                    "package": "typing-extensions",
                    "symbol": "typing_extensions.Sentinel",
                    "file_path": "tests/test_annotated.py",
                    "line": 11,
                    "replacement": "typing_extensions.sentinel",
                    "severity": "medium",
                }
            ],
            {"findings": []},
        )
        action = plan["steps"][0]["action"]
        self.assertIn("Replace deprecated usage of `typing_extensions.Sentinel`", action)
        self.assertIn("with `typing_extensions.sentinel`", action)
        self.assertIn("test_annotated.py:11", action)

    def test_dedupes_repeated_deprecated_findings(self) -> None:
        planner = MigrationPlanner()
        findings = [
            {
                "package": "fastparquet",
                "symbol": "fastparquet",
                "file_path": f"/tmp/versionpilot-xyz/pandas/tests/io/test_parquet.py",
                "line": line,
                "replacement": "",
                "severity": "high",
            }
            for line in (45, 48, 49, 345)
        ]
        plan = planner.generate_plan(findings, {"findings": []})
        self.assertEqual(plan["total_steps"], 1)
        step = plan["steps"][0]
        self.assertEqual(step["occurrence_count"], 4)
        self.assertIn("4 occurrences", step["action"])
        self.assertIn("io/test_parquet.py", step["action"])

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
