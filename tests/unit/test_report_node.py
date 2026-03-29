"""Tests for report_node: LLM synthesis + template fallback."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.agents.report_node import _template_report, report_node
from app.agents.state import create_initial_state

_REQUIRED_KEYS = {"summary", "health_score", "risk_level", "key_findings",
                  "migration_recommendations", "data_quality"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state(**kwargs):
    s = create_initial_state("https://github.com/example/repo", "", "config/scoring_v1.yaml")
    s.update(kwargs)
    return s


def _canned_report(health_score=72.0, risk_level="medium"):
    return {
        "summary": "The repo is in reasonable health.",
        "health_score": health_score,
        "risk_level": risk_level,
        "key_findings": [
            {"finding": "One deprecated API found", "evidence": "flask.ext at app.py:10", "severity": "high"}
        ],
        "migration_recommendations": [
            {"action": "Replace flask.ext usage", "priority": "high", "reason": "symbol removed in Flask 1.0"}
        ],
        "data_quality": {"completeness": 1.0, "confidence": 0.9, "failed_steps": []},
    }


# ---------------------------------------------------------------------------
# Template fallback (_template_report)
# ---------------------------------------------------------------------------

class TestTemplateReport:
    def test_required_keys_present(self):
        state = _state(health_score=55.0, risk_level="high")
        report = _template_report(state)
        assert _REQUIRED_KEYS.issubset(report.keys())

    def test_health_score_and_risk_level_passed_through(self):
        state = _state(health_score=82.3, risk_level="low")
        report = _template_report(state)
        assert report["health_score"] == 82.3
        assert report["risk_level"] == "low"

    def test_deprecated_findings_become_key_findings(self):
        state = _state(deprecated_findings=[
            {"symbol": "flask.ext", "file_path": "app.py", "line": 10,
             "package": "flask", "severity": "high"},
        ])
        report = _template_report(state)
        assert len(report["key_findings"]) == 1
        assert "flask.ext" in report["key_findings"][0]["finding"]

    def test_migration_steps_become_recommendations(self):
        state = _state(migration_plan={
            "steps": [
                {"action": "Replace flask.ext", "type": "deprecated_api_replacement",
                 "package": "flask", "severity": "high"},
            ]
        })
        report = _template_report(state)
        assert len(report["migration_recommendations"]) == 1
        assert report["migration_recommendations"][0]["priority"] == "high"

    def test_empty_findings_produce_empty_lists(self):
        state = _state(deprecated_findings=[], migration_plan={"steps": []})
        report = _template_report(state)
        assert report["key_findings"] == []
        assert report["migration_recommendations"] == []

    def test_data_quality_fields_present(self):
        state = _state(data_completeness=0.75, confidence_score=0.6,
                       failed_steps=["v1_pipeline"])
        report = _template_report(state)
        dq = report["data_quality"]
        assert dq["completeness"] == 0.75
        assert dq["confidence"] == 0.6
        assert "v1_pipeline" in dq["failed_steps"]

    def test_none_fields_handled_gracefully(self):
        # deprecated_findings and migration_plan may be None in initial state
        state = _state(deprecated_findings=None, migration_plan=None)
        report = _template_report(state)
        assert report["key_findings"] == []
        assert report["migration_recommendations"] == []


# ---------------------------------------------------------------------------
# report_node — LLM unavailable path
# ---------------------------------------------------------------------------

class TestReportNodeFallback:
    @patch("app.agents.report_node.LLMClient.is_available", return_value=False)
    def test_fallback_produces_required_keys(self, _mock):
        state = _state(health_score=60.0, risk_level="medium")
        result = report_node(state)
        assert _REQUIRED_KEYS.issubset(result["final_report"].keys())

    @patch("app.agents.report_node.LLMClient.is_available", return_value=False)
    def test_fallback_trace_records_fallback(self, _mock):
        state = _state()
        result = report_node(state)
        statuses = [e.get("status") for e in result["agent_trace"] if e.get("node") == "report"]
        assert "fallback" in statuses

    @patch("app.agents.report_node.LLMClient.is_available", return_value=False)
    def test_fallback_passes_through_score_and_risk(self, _mock):
        state = _state(health_score=44.0, risk_level="critical")
        result = report_node(state)
        assert result["final_report"]["health_score"] == 44.0
        assert result["final_report"]["risk_level"] == "critical"


# ---------------------------------------------------------------------------
# report_node — LLM available path
# ---------------------------------------------------------------------------

class TestReportNodeLLM:
    @patch("app.agents.report_node.LLMClient.is_available", return_value=True)
    @patch("app.agents.report_node.LLMClient")
    def test_llm_report_used_when_valid(self, MockLLM, _mock_avail):
        mock_instance = MagicMock()
        mock_instance.call.return_value = json.dumps(_canned_report())
        MockLLM.return_value = mock_instance

        state = _state(health_score=72.0, risk_level="medium")
        result = report_node(state)

        assert result["final_report"]["summary"] == "The repo is in reasonable health."
        assert result["final_report"]["health_score"] == 72.0

    @patch("app.agents.report_node.LLMClient.is_available", return_value=True)
    @patch("app.agents.report_node.LLMClient")
    def test_llm_report_has_required_keys(self, MockLLM, _mock_avail):
        mock_instance = MagicMock()
        mock_instance.call.return_value = json.dumps(_canned_report())
        MockLLM.return_value = mock_instance

        state = _state()
        result = report_node(state)
        assert _REQUIRED_KEYS.issubset(result["final_report"].keys())

    @patch("app.agents.report_node.LLMClient.is_available", return_value=True)
    @patch("app.agents.report_node.LLMClient")
    def test_llm_trace_records_complete(self, MockLLM, _mock_avail):
        mock_instance = MagicMock()
        mock_instance.call.return_value = json.dumps(_canned_report())
        MockLLM.return_value = mock_instance

        state = _state()
        result = report_node(state)
        statuses = [e.get("status") for e in result["agent_trace"] if e.get("node") == "report"]
        assert "complete" in statuses

    @patch("app.agents.report_node.LLMClient.is_available", return_value=True)
    @patch("app.agents.report_node.LLMClient")
    def test_llm_bad_json_falls_back_to_template(self, MockLLM, _mock_avail):
        mock_instance = MagicMock()
        mock_instance.call.return_value = "not valid json {{{"
        MockLLM.return_value = mock_instance

        state = _state(health_score=50.0, risk_level="medium")
        result = report_node(state)

        assert _REQUIRED_KEYS.issubset(result["final_report"].keys())
        statuses = [e.get("status") for e in result["agent_trace"] if e.get("node") == "report"]
        assert "fallback" in statuses

    @patch("app.agents.report_node.LLMClient.is_available", return_value=True)
    @patch("app.agents.report_node.LLMClient")
    def test_llm_receives_all_signals(self, MockLLM, _mock_avail):
        """Verify the user prompt contains key state fields."""
        mock_instance = MagicMock()
        mock_instance.call.return_value = json.dumps(_canned_report())
        MockLLM.return_value = mock_instance

        state = _state(
            health_score=65.0,
            risk_level="medium",
            deprecated_findings=[{"symbol": "old.api"}],
            failed_steps=["changelog_analysis"],
            critic_feedback="Score looks low given data",
        )
        report_node(state)

        call_args = mock_instance.call.call_args
        user_prompt = call_args[0][1]
        assert "health_score" in user_prompt
        assert "deprecated_findings" in user_prompt
        assert "failed_steps" in user_prompt
        assert "critic_feedback" in user_prompt
