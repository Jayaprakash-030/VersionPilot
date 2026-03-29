"""Tests for critic_node: LLM validation + deterministic fallback + routing."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.agents.critic_node import _deterministic_check, critic_node
from app.agents.graph import should_retry_or_report
from app.agents.state import create_initial_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state(**kwargs):
    s = create_initial_state("https://github.com/example/repo", "", "config/scoring_v1.yaml")
    s.update(kwargs)
    return s


# ---------------------------------------------------------------------------
# Deterministic fallback checks
# ---------------------------------------------------------------------------

class TestDeterministicCheck:
    def test_clean_state_passes(self):
        state = _state(health_score=75.0, failed_steps=[], risk_level="medium")
        passed, feedback = _deterministic_check(state)
        assert passed is True
        assert feedback == ""

    def test_high_score_with_failed_steps_fails(self):
        state = _state(health_score=90.0, failed_steps=["v1_pipeline"])
        passed, feedback = _deterministic_check(state)
        assert passed is False
        assert "failed" in feedback.lower() or "90" in feedback

    def test_high_score_threshold_is_exclusive(self):
        # Exactly 80 should NOT trigger the failed_steps check
        state = _state(health_score=80.0, failed_steps=["v1_pipeline"])
        passed, _ = _deterministic_check(state)
        assert passed is True

    def test_zero_deps_with_perfect_dep_score_fails(self):
        state = _state(
            dependency_metrics={"total_dependencies": 0, "outdated_dependencies": 0},
            breakdown={"dependency_score": 100},
            health_score=50.0,
        )
        passed, feedback = _deterministic_check(state)
        assert passed is False
        assert "zero" in feedback.lower() or "dependencies" in feedback.lower()

    def test_low_risk_with_critical_vulns_fails(self):
        state = _state(
            security_metrics={"critical": 2, "high": 0, "medium": 0, "low": 0},
            risk_level="low",
            health_score=50.0,
        )
        passed, feedback = _deterministic_check(state)
        assert passed is False
        assert "critical" in feedback.lower() or "risk" in feedback.lower()

    def test_low_risk_with_high_vulns_fails(self):
        state = _state(
            security_metrics={"critical": 0, "high": 3, "medium": 0, "low": 0},
            risk_level="healthy",
            health_score=50.0,
        )
        passed, feedback = _deterministic_check(state)
        assert passed is False


# ---------------------------------------------------------------------------
# critic_node — LLM unavailable path
# ---------------------------------------------------------------------------

class TestCriticNodeFallback:
    @patch("app.agents.critic_node.LLMClient.is_available", return_value=False)
    def test_fallback_clean_state(self, _mock):
        state = _state(health_score=70.0, failed_steps=[], risk_level="medium")
        result = critic_node(state)
        assert result["critic_passed"] is True
        assert result["critic_feedback"] == ""
        trace_nodes = [e["node"] for e in result["agent_trace"]]
        assert "critic" in trace_nodes

    @patch("app.agents.critic_node.LLMClient.is_available", return_value=False)
    def test_fallback_suspicious_state_fails(self, _mock):
        state = _state(health_score=95.0, failed_steps=["github_data_collector"])
        result = critic_node(state)
        assert result["critic_passed"] is False
        assert result["critic_feedback"] != ""


# ---------------------------------------------------------------------------
# critic_node — LLM available path
# ---------------------------------------------------------------------------

class TestCriticNodeLLM:
    @patch("app.agents.critic_node.LLMClient.is_available", return_value=True)
    @patch("app.agents.critic_node.LLMClient")
    def test_llm_pass(self, MockLLM, _mock_avail):
        mock_instance = MagicMock()
        mock_instance.call.return_value = json.dumps({"passed": True, "feedback": ""})
        MockLLM.return_value = mock_instance

        state = _state(health_score=70.0, risk_level="medium")
        result = critic_node(state)
        assert result["critic_passed"] is True
        assert result["critic_feedback"] == ""

    @patch("app.agents.critic_node.LLMClient.is_available", return_value=True)
    @patch("app.agents.critic_node.LLMClient")
    def test_llm_fail(self, MockLLM, _mock_avail):
        mock_instance = MagicMock()
        mock_instance.call.return_value = json.dumps({
            "passed": False,
            "feedback": "High score with failed steps",
        })
        MockLLM.return_value = mock_instance

        state = _state(health_score=92.0, failed_steps=["v1_pipeline"])
        result = critic_node(state)
        assert result["critic_passed"] is False
        assert "failed" in result["critic_feedback"].lower()

    @patch("app.agents.critic_node.LLMClient.is_available", return_value=True)
    @patch("app.agents.critic_node.LLMClient")
    def test_llm_bad_json_falls_back_to_deterministic(self, MockLLM, _mock_avail):
        mock_instance = MagicMock()
        mock_instance.call.return_value = "not valid json {{{"
        MockLLM.return_value = mock_instance

        # Clean state → deterministic check passes even after LLM error
        state = _state(health_score=60.0, failed_steps=[], risk_level="medium")
        result = critic_node(state)
        assert result["critic_passed"] is True
        trace_statuses = [e.get("status") for e in result["agent_trace"] if e.get("node") == "critic"]
        assert "fallback" in trace_statuses


# ---------------------------------------------------------------------------
# should_retry_or_report routing function
# ---------------------------------------------------------------------------

class TestShouldRetryOrReport:
    def test_passes_goes_to_report(self):
        state = _state(critic_passed=True, retry_count=0)
        assert should_retry_or_report(state) == "report"

    def test_fails_goes_to_recovery(self):
        state = _state(critic_passed=False, retry_count=0)
        assert should_retry_or_report(state) == "recovery"

    def test_max_retries_goes_to_report(self):
        state = _state(critic_passed=False, retry_count=2)
        assert should_retry_or_report(state) == "report"

    def test_one_retry_still_goes_to_recovery(self):
        state = _state(critic_passed=False, retry_count=1)
        assert should_retry_or_report(state) == "recovery"
