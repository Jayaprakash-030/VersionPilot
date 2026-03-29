"""Graph retry loop tests — critic fail/pass cycles, max retry cap."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.agents.graph import build_graph
from app.agents.state import create_initial_state


# ---------------------------------------------------------------------------
# Shared mock data (same as test_graph_skeleton)
# ---------------------------------------------------------------------------

_PIPELINE_RESULT = {
    "status": "ok",
    "repo_metrics": {"stars": 10, "forks": 2, "last_commit_days": 5, "open_issues": 1, "closed_issues": 10},
    "dependency_metrics": {"total_dependencies": 3, "outdated_dependencies": 1},
    "security_metrics": {"critical": 0, "high": 0, "medium": 0, "low": 0},
}


def _mock_registry():
    registry = MagicMock()
    registry.run_v1_pipeline.return_value = _PIPELINE_RESULT
    registry.fetch_dependency_names.return_value = {"status": "ok", "dependencies": []}
    registry.fetch_dependency_release_notes.return_value = {"status": "ok", "notes": ""}
    registry.scan_deprecated_apis.return_value = {"status": "ok", "findings": [], "summary": {}}
    registry.analyze_changelog.return_value = {"status": "ok", "breaking_changes": [], "deprecations": []}
    registry.generate_migration_plan.return_value = {"status": "ok", "steps": []}
    return registry


@pytest.fixture(autouse=True)
def mock_externals():
    with (
        patch("app.agents.evidence_node.ToolRegistry", return_value=_mock_registry()),
        patch("app.agents.evidence_node.RulesExtractor", return_value=MagicMock(build_rules_dict=MagicMock(return_value={}))),
        patch("app.agents.planner_node.LLMClient.is_available", return_value=False),
        patch("app.agents.critic_node.LLMClient.is_available", return_value=False),
    ):
        yield


def _initial_state():
    return create_initial_state("https://github.com/example/repo", "", "config/scoring_v1.yaml")


# ---------------------------------------------------------------------------
# Helper: build a mock critic that fails N times then passes
# ---------------------------------------------------------------------------

def _make_critic(fail_times: int):
    call_count = {"n": 0}

    def mock_critic(state):
        call_count["n"] += 1
        trace = list(state.get("agent_trace", []))
        if call_count["n"] <= fail_times:
            trace.append({"node": "critic", "status": "complete", "passed": False})
            return {"critic_passed": False, "critic_feedback": "mock: suspicious result", "agent_trace": trace}
        trace.append({"node": "critic", "status": "complete", "passed": True})
        return {"critic_passed": True, "critic_feedback": "", "agent_trace": trace}

    return mock_critic


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRetryThenPass:
    def test_retry_count_is_1_after_one_failure(self):
        with patch("app.agents.graph.critic_node", _make_critic(fail_times=1)):
            graph = build_graph()
            result = graph.invoke(_initial_state())
        assert result["retry_count"] == 1

    def test_recovery_appears_in_trace(self):
        with patch("app.agents.graph.critic_node", _make_critic(fail_times=1)):
            graph = build_graph()
            result = graph.invoke(_initial_state())
        nodes = [e["node"] for e in result["agent_trace"]]
        assert "recovery" in nodes

    def test_graph_reaches_report_after_retry(self):
        with patch("app.agents.graph.critic_node", _make_critic(fail_times=1)):
            graph = build_graph()
            result = graph.invoke(_initial_state())
        nodes = [e["node"] for e in result["agent_trace"]]
        assert "report" in nodes
        assert result["final_report"] is not None


class TestMaxRetries:
    def test_graph_reaches_report_when_critic_always_fails(self):
        with patch("app.agents.graph.critic_node", _make_critic(fail_times=99)):
            graph = build_graph()
            result = graph.invoke(_initial_state())
        nodes = [e["node"] for e in result["agent_trace"]]
        assert "report" in nodes

    def test_retry_count_capped_at_2(self):
        with patch("app.agents.graph.critic_node", _make_critic(fail_times=99)):
            graph = build_graph()
            result = graph.invoke(_initial_state())
        assert result["retry_count"] == 2

    def test_confidence_degraded_after_two_retries(self):
        with patch("app.agents.graph.critic_node", _make_critic(fail_times=99)):
            graph = build_graph()
            result = graph.invoke(_initial_state())
        # Two recovery passes: 1.0 → 0.8 → 0.6 (but scoring_node recomputes from failed_steps)
        # With no failed_steps, scoring_node sets confidence to 1.0 each time,
        # then recovery drops it. After 2 recoveries the last recovery set it to 0.6.
        assert result["confidence_score"] < 1.0


class TestHappyPathNoRecovery:
    def test_no_recovery_when_critic_passes_first_time(self):
        # Default mocked critic (LLM unavailable, clean state) should pass
        graph = build_graph()
        result = graph.invoke(_initial_state())
        nodes = [e["node"] for e in result["agent_trace"]]
        assert "recovery" not in nodes
        assert result["retry_count"] == 0
