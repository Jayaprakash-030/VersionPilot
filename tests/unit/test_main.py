import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.main import parse_args, resolve_output_path


class TestMainOutputPath(unittest.TestCase):
    def test_resolve_output_path_uses_custom_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            custom = Path(tmpdir) / "reports" / "result.json"
            path = resolve_output_path("abcd1234", str(custom), mode="basic")
            self.assertEqual(path, custom)
            self.assertTrue(path.parent.exists())

    def test_parse_args_supports_json_flag(self) -> None:
        argv = ["prog", "https://github.com/org/repo", "--json"]
        with patch.object(sys, "argv", argv):
            args = parse_args()
        self.assertTrue(args.json)

    def test_parse_args_supports_agent_mode(self) -> None:
        argv = ["prog", "https://github.com/org/repo", "--mode", "agent"]
        with patch.object(sys, "argv", argv):
            args = parse_args()
        self.assertEqual(args.mode, "agent")

    def test_parse_args_supports_repo_path(self) -> None:
        argv = ["prog", "https://github.com/org/repo", "--repo-path", "/tmp/sample-repo"]
        with patch.object(sys, "argv", argv):
            args = parse_args()
        self.assertEqual(args.repo_path, "/tmp/sample-repo")

    def test_parse_args_supports_notes_file(self) -> None:
        argv = ["prog", "https://github.com/org/repo", "--notes-file", "/tmp/release_notes.txt"]
        with patch.object(sys, "argv", argv):
            args = parse_args()
        self.assertEqual(args.notes_file, "/tmp/release_notes.txt")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_config(version="v1"):
    cfg = MagicMock()
    cfg.version = version
    return cfg


def _mock_pipeline_report(health_score=72.0, risk_level="medium"):
    report = MagicMock()
    report.health_score = health_score
    report.risk_level = risk_level
    report.to_dict.return_value = {"health_score": health_score, "risk_level": risk_level}
    return report


# ---------------------------------------------------------------------------
# main() — agent mode with run_graph
# ---------------------------------------------------------------------------

class TestMainAgentMode(unittest.TestCase):
    def _run_main_agent(self, run_graph_return, tmpdir, extra_argv=None):
        """Helper: run main() in agent mode with a mocked run_graph."""
        argv = ["prog", "https://github.com/org/repo", "--mode", "agent",
                "--output", str(Path(tmpdir) / "out.json")]
        if extra_argv:
            argv += extra_argv

        with patch.object(sys, "argv", argv), \
             patch("app.main.load_scoring_config", return_value=_mock_config()), \
             patch("app.main.build_run_id", return_value="run123"), \
             patch("app.main.run_graph", return_value=run_graph_return):
            from app.main import main
            main()

    def test_agent_mode_writes_final_report_to_file(self):
        fake_state = {"final_report": {"health_score": 80.0, "risk_level": "low",
                                       "summary": "All good."}}
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "out.json"
            self._run_main_agent(fake_state, tmpdir)
            written = json.loads(out.read_text())
            self.assertEqual(written["health_score"], 80.0)
            self.assertEqual(written["risk_level"], "low")

    def test_agent_mode_passes_repo_path_to_run_graph(self):
        fake_state = {"final_report": {"health_score": 70.0, "risk_level": "medium"}}
        with tempfile.TemporaryDirectory() as tmpdir:
            argv = ["prog", "https://github.com/org/repo", "--mode", "agent",
                    "--repo-path", "/tmp/myrepo", "--output", str(Path(tmpdir) / "out.json")]
            with patch.object(sys, "argv", argv), \
                 patch("app.main.load_scoring_config", return_value=_mock_config()), \
                 patch("app.main.build_run_id", return_value="run123"), \
                 patch("app.main.run_graph", return_value=fake_state) as mock_rg:
                from app.main import main
                main()
        mock_rg.assert_called_once()
        call_kwargs = mock_rg.call_args[1]
        self.assertEqual(call_kwargs.get("repo_path"), "/tmp/myrepo")


# ---------------------------------------------------------------------------
# main() — agent mode fallback when run_graph raises
# ---------------------------------------------------------------------------

class TestMainAgentModeFallback(unittest.TestCase):
    def test_fallback_to_basic_pipeline_on_exception(self):
        mock_report = _mock_pipeline_report(health_score=55.0, risk_level="high")
        with tempfile.TemporaryDirectory() as tmpdir:
            argv = ["prog", "https://github.com/org/repo", "--mode", "agent",
                    "--output", str(Path(tmpdir) / "out.json")]
            with patch.object(sys, "argv", argv), \
                 patch("app.main.load_scoring_config", return_value=_mock_config()), \
                 patch("app.main.build_run_id", return_value="run123"), \
                 patch("app.main.run_graph", side_effect=RuntimeError("graph failed")), \
                 patch("app.main.run_pipeline", return_value=mock_report) as mock_pipe:
                from app.main import main
                main()

        mock_pipe.assert_called_once_with(
            repo_url="https://github.com/org/repo",
            config_path="config/scoring_v1.yaml",
        )

    def test_fallback_output_contains_pipeline_data(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = Path(tmpdir) / "out.json"
            argv = ["prog", "https://github.com/org/repo", "--mode", "agent",
                    "--output", str(out)]
            mock_report = _mock_pipeline_report(health_score=55.0, risk_level="high")

            with patch.object(sys, "argv", argv), \
                 patch("app.main.load_scoring_config", return_value=_mock_config()), \
                 patch("app.main.build_run_id", return_value="run123"), \
                 patch("app.main.run_graph", side_effect=RuntimeError("graph failed")), \
                 patch("app.main.run_pipeline", return_value=mock_report):
                from app.main import main
                main()

            written = json.loads(out.read_text())
            self.assertEqual(written["health_score"], 55.0)
            self.assertEqual(written["risk_level"], "high")


if __name__ == "__main__":
    unittest.main()
