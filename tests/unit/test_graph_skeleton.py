"""Graph topology tests — all external calls mocked, no network or LLM required."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.agents.graph import run_graph


_PIPELINE_RESULT = {
    "status": "ok",
    "repo_metrics": {"stars": 10, "forks": 2, "last_commit_days": 5, "open_issues": 1, "closed_issues": 10},
    "dependency_metrics": {"total_dependencies": 3, "outdated_dependencies": 1},
    "security_metrics": {"critical": 0, "high": 0, "medium": 0, "low": 0},
}

_DEP_NAMES_RESULT = {"status": "ok", "dependencies": ["requests", "flask"]}

_RELEASE_NOTES_RESULT = {"status": "ok", "notes": "No breaking changes."}

_SCAN_RESULT = {"status": "ok", "findings": [], "summary": {}}

_CHANGELOG_RESULT = {"status": "ok", "breaking_changes": [], "deprecations": []}

_MIGRATION_RESULT = {"status": "ok", "steps": []}


def _mock_registry():
    registry = MagicMock()
    registry.run_v1_pipeline.return_value = _PIPELINE_RESULT
    registry.fetch_dependency_names.return_value = _DEP_NAMES_RESULT
    registry.fetch_dependency_release_notes.return_value = _RELEASE_NOTES_RESULT
    registry.scan_deprecated_apis.return_value = _SCAN_RESULT
    registry.analyze_changelog.return_value = _CHANGELOG_RESULT
    registry.generate_migration_plan.return_value = _MIGRATION_RESULT
    registry.clone_repo.return_value = {"status": "ok", "repo_path": "/tmp/mock-clone"}
    return registry


@pytest.fixture(autouse=True)
def mock_externals(monkeypatch):
    """Patch all external calls for every test in this module."""
    with (
        patch("app.agents.evidence_node.ToolRegistry", return_value=_mock_registry()),
        patch("app.agents.evidence_node.RulesExtractor", return_value=MagicMock(build_rules_dict=MagicMock(return_value={}))),
        patch("app.agents.planner_node.LLMClient.is_available", return_value=False),
        patch("app.agents.critic_node.LLMClient.is_available", return_value=False),
    ):
        yield


def test_all_nodes_logged_to_trace():
    result = run_graph("https://github.com/psf/requests")
    nodes = [entry["node"] for entry in result["agent_trace"]]
    assert "planner" in nodes
    assert "evidence" in nodes
    assert "scoring" in nodes
    assert "critic" in nodes
    assert "report" in nodes


def test_critic_passed_is_true():
    result = run_graph("https://github.com/psf/requests")
    assert result["critic_passed"] is True


def test_final_report_is_not_none():
    result = run_graph("https://github.com/psf/requests")
    assert result["final_report"] is not None


def test_no_recovery_in_happy_path():
    result = run_graph("https://github.com/psf/requests")
    nodes = [entry["node"] for entry in result["agent_trace"]]
    assert "recovery" not in nodes


def test_run_id_preserved_in_output():
    result = run_graph("https://github.com/psf/requests")
    assert isinstance(result["run_id"], str) and len(result["run_id"]) > 0
