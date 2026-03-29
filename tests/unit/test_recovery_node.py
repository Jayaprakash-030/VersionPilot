"""Unit tests for recovery_node: retry count, confidence degradation, trace logging."""
from __future__ import annotations

from app.agents.recovery_node import recovery_node
from app.agents.state import create_initial_state


def _state(**kwargs):
    s = create_initial_state("https://github.com/example/repo", "", "config/scoring_v1.yaml")
    s.update(kwargs)
    return s


class TestRetryCount:
    def test_increments_from_zero(self):
        state = _state(retry_count=0)
        result = recovery_node(state)
        assert result["retry_count"] == 1

    def test_increments_from_one(self):
        state = _state(retry_count=1)
        result = recovery_node(state)
        assert result["retry_count"] == 2

    def test_increments_when_missing(self):
        state = _state()
        state.pop("retry_count", None)
        result = recovery_node(state)
        assert result["retry_count"] == 1


class TestConfidenceDegradation:
    def test_confidence_decreases_by_0_2(self):
        state = _state(confidence_score=1.0)
        result = recovery_node(state)
        assert abs(result["confidence_score"] - 0.8) < 1e-9

    def test_confidence_clamped_at_zero(self):
        state = _state(confidence_score=0.1)
        result = recovery_node(state)
        assert result["confidence_score"] == 0.0

    def test_confidence_never_negative(self):
        state = _state(confidence_score=0.0)
        result = recovery_node(state)
        assert result["confidence_score"] == 0.0


class TestCompletenessDegradation:
    def test_completeness_decreases_by_0_15(self):
        state = _state(data_completeness=1.0)
        result = recovery_node(state)
        assert abs(result["data_completeness"] - 0.85) < 1e-9

    def test_completeness_clamped_at_zero(self):
        state = _state(data_completeness=0.1)
        result = recovery_node(state)
        assert result["data_completeness"] == 0.0


class TestTrace:
    def test_recovery_action_logged(self):
        state = _state(retry_count=0, confidence_score=1.0, data_completeness=1.0)
        result = recovery_node(state)
        critic_entries = [e for e in result["agent_trace"] if e.get("node") == "recovery"]
        assert len(critic_entries) == 1

    def test_trace_includes_retry_number(self):
        state = _state(retry_count=0)
        result = recovery_node(state)
        entry = next(e for e in result["agent_trace"] if e.get("node") == "recovery")
        assert "1" in entry["action"]

    def test_critic_feedback_preserved_in_trace(self):
        state = _state(critic_feedback="High score with failed steps")
        result = recovery_node(state)
        entry = next(e for e in result["agent_trace"] if e.get("node") == "recovery")
        assert entry["critic_feedback"] == "High score with failed steps"

    def test_empty_feedback_preserved(self):
        state = _state(critic_feedback="")
        result = recovery_node(state)
        entry = next(e for e in result["agent_trace"] if e.get("node") == "recovery")
        assert entry["critic_feedback"] == ""
