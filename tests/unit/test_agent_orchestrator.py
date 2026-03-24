import tempfile
import unittest
from pathlib import Path

from app.agent_orchestrator import AgentOrchestrator


class TestAgentOrchestrator(unittest.TestCase):
    def test_agent_mode_includes_deprecated_api_findings_when_repo_path_provided(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = Path(tmpdir)
            (repo_path / "sample.py").write_text(
                "from flask.ext import sqlalchemy\n",
                encoding="utf-8",
            )

            orchestrator = AgentOrchestrator()
            result = orchestrator.analyze_repository(
                repo_url="https://github.com/org/repo",
                repo_path=str(repo_path),
            )

            self.assertEqual(result["mode"], "agent")
            self.assertEqual(result["deprecation_scan_status"], "ok")
            self.assertGreaterEqual(len(result["deprecated_api_findings"]), 1)
            summary = result["deprecated_risk_summary"]
            self.assertEqual(summary["total_findings"], len(result["deprecated_api_findings"]))
            self.assertEqual(summary["severity_counts"]["high"], 1)
            self.assertGreaterEqual(len(summary["top_symbols"]), 1)
            self.assertIn("report", result)


if __name__ == "__main__":
    unittest.main()
