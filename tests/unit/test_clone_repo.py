"""Tests for ToolRegistry.clone_repo and evidence_node auto-clone behaviour."""
from __future__ import annotations

import shutil
from subprocess import CompletedProcess
from unittest.mock import MagicMock, call, patch

import pytest

from app.agents.state import create_initial_state
from app.tools.tool_registry import ToolRegistry


# ---------------------------------------------------------------------------
# ToolRegistry.clone_repo
# ---------------------------------------------------------------------------

class TestCloneRepo:
    def _registry(self):
        return ToolRegistry()

    @patch("app.tools.tool_registry.tempfile.mkdtemp", return_value="/tmp/versionpilot-abc")
    @patch("app.tools.tool_registry.subprocess.run")
    def test_success_returns_ok_and_repo_path(self, mock_run, mock_mkdtemp):
        mock_run.return_value = CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        result = self._registry().clone_repo("https://github.com/org/repo")
        assert result["status"] == "ok"
        assert result["repo_path"] == "/tmp/versionpilot-abc"

    @patch("app.tools.tool_registry.tempfile.mkdtemp", return_value="/tmp/versionpilot-abc")
    @patch("app.tools.tool_registry.subprocess.run")
    def test_uses_shallow_clone_flag(self, mock_run, mock_mkdtemp):
        mock_run.return_value = CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        self._registry().clone_repo("https://github.com/org/repo")
        cmd = mock_run.call_args[0][0]
        assert "--depth=1" in cmd

    @patch("app.tools.tool_registry.tempfile.mkdtemp", return_value="/tmp/versionpilot-abc")
    @patch("app.tools.tool_registry.subprocess.run")
    def test_git_error_returns_error_status(self, mock_run, mock_mkdtemp):
        mock_run.return_value = CompletedProcess(
            args=[], returncode=128, stdout="", stderr="fatal: repository not found"
        )
        result = self._registry().clone_repo("https://github.com/org/missing")
        assert result["status"] == "error"
        assert "repository not found" in result["error"]

    @patch("app.tools.tool_registry.tempfile.mkdtemp", return_value="/tmp/versionpilot-abc")
    @patch("app.tools.tool_registry.subprocess.run", side_effect=TimeoutError("timed out"))
    def test_exception_returns_error_status(self, mock_run, mock_mkdtemp):
        result = self._registry().clone_repo("https://github.com/org/repo")
        assert result["status"] == "error"
        assert "timed out" in result["error"]


# ---------------------------------------------------------------------------
# evidence_node auto-clone behaviour
# ---------------------------------------------------------------------------

def _base_state(**kwargs):
    s = create_initial_state("https://github.com/org/repo", "", "config/scoring_v1.yaml")
    s.update(kwargs)
    return s


def _noop_registry():
    """Registry where all tools return success with empty results."""
    r = MagicMock()
    r.run_v1_pipeline.return_value = {"status": "ok", "repo_metrics": {}, "dependency_metrics": {},
                                       "security_metrics": {}, "breakdown": {}, "failed_steps": [],
                                       "data_completeness": 1.0, "confidence_score": 1.0}
    r.fetch_dependency_names.return_value = {"status": "ok", "names": []}
    r.scan_deprecated_apis.return_value = {"status": "ok", "findings": []}
    r.generate_migration_plan.return_value = {"status": "ok", "steps": [], "total_steps": 0, "effort_level": "low"}
    r.clone_repo.return_value = {"status": "ok", "repo_path": "/tmp/versionpilot-test"}
    return r


class TestEvidenceNodeAutoClone:
    def _run(self, state, registry):
        from app.agents.evidence_node import evidence_node
        with patch("app.agents.evidence_node.ToolRegistry", return_value=registry), \
             patch("app.agents.evidence_node.RulesExtractor") as MockExtractor, \
             patch("app.agents.evidence_node.shutil.rmtree") as mock_rmtree:
            MockExtractor.return_value.build_rules_dict.return_value = {}
            result = evidence_node(state)
        return result, registry, mock_rmtree

    def test_clone_called_when_no_repo_path(self):
        state = _base_state(repo_path="")
        registry = _noop_registry()
        self._run(state, registry)
        registry.clone_repo.assert_called_once_with("https://github.com/org/repo")

    def test_clone_not_called_when_repo_path_provided(self):
        state = _base_state(repo_path="/existing/local/repo")
        registry = _noop_registry()
        self._run(state, registry)
        registry.clone_repo.assert_not_called()

    def test_cloned_path_passed_to_scanner(self):
        state = _base_state(repo_path="")
        registry = _noop_registry()
        self._run(state, registry)
        registry.scan_deprecated_apis.assert_called_once()
        call_path = registry.scan_deprecated_apis.call_args[0][0]
        assert call_path == "/tmp/versionpilot-test"

    def test_temp_dir_cleaned_up_after_scan(self):
        state = _base_state(repo_path="")
        registry = _noop_registry()
        _, _, mock_rmtree = self._run(state, registry)
        mock_rmtree.assert_called_once_with("/tmp/versionpilot-test", ignore_errors=True)

    def test_temp_dir_cleaned_up_even_when_scan_fails(self):
        state = _base_state(repo_path="")
        registry = _noop_registry()
        registry.scan_deprecated_apis.side_effect = RuntimeError("scan crashed")
        _, _, mock_rmtree = self._run(state, registry)
        mock_rmtree.assert_called_once_with("/tmp/versionpilot-test", ignore_errors=True)

    def test_clone_failure_recorded_in_failed_steps(self):
        state = _base_state(repo_path="")
        registry = _noop_registry()
        registry.clone_repo.return_value = {"status": "error", "error": "network error"}
        result, _, _ = self._run(state, registry)
        assert "clone_repo" in result["failed_steps"]

    def test_no_cleanup_when_repo_path_was_provided(self):
        state = _base_state(repo_path="/existing/local/repo")
        registry = _noop_registry()
        _, _, mock_rmtree = self._run(state, registry)
        mock_rmtree.assert_not_called()
