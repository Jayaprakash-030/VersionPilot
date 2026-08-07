"""Tests for report_node: LLM synthesis + template fallback."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.agents.report_node import _template_report, report_node
from app.agents.state import create_initial_state

_REQUIRED_KEYS = {"summary", "health_score", "risk_level", "key_findings",
                  "migration_recommendations", "upstream_breaking_change_hints", "data_quality"}


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
        "upstream_breaking_change_hints": [],
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
        assert "app.py:10" in report["key_findings"][0]["finding"]

    def test_migration_steps_become_recommendations(self):
        state = _state(migration_plan={
            "steps": [
                {"action": "Replace flask.ext", "type": "deprecated_api_replacement",
                 "package": "flask", "severity": "high", "confidence": "ast_scan"},
            ]
        })
        report = _template_report(state)
        assert len(report["migration_recommendations"]) == 1
        assert report["migration_recommendations"][0]["priority"] == "high"

    def test_release_note_only_steps_become_hints_not_recommendations(self):
        state = _state(migration_plan={
            "steps": [
                {"action": "Removed support for Python 3.9", "type": "breaking_change_review",
                 "package": "urllib3", "severity": "high", "confidence": "regex_heuristic",
                 "version_span": "1.26→2.7.0"},
            ]
        })
        report = _template_report(state)
        assert report["migration_recommendations"] == []
        assert len(report["upstream_breaking_change_hints"]) == 1
        assert "urllib3" in report["upstream_breaking_change_hints"][0]["reason"]

    def test_key_findings_are_deduped_by_package_and_symbol(self):
        state = _state(
            deprecated_findings=[
                {
                    "symbol": "fastparquet",
                    "file_path": "tests/io/test_parquet.py",
                    "line": 45,
                    "package": "fastparquet",
                    "severity": "high",
                },
                {
                    "symbol": "fastparquet",
                    "file_path": "tests/io/test_parquet.py",
                    "line": 48,
                    "package": "fastparquet",
                    "severity": "high",
                },
            ]
        )
        report = _template_report(state)
        assert len(report["key_findings"]) == 1
        assert "2 occurrences" in report["key_findings"][0]["finding"]

    def test_empty_findings_produce_empty_lists(self):
        state = _state(deprecated_findings=[], migration_plan={"steps": []})
        report = _template_report(state)
        assert report["key_findings"] == []
        assert report["migration_recommendations"] == []
        assert report["upstream_breaking_change_hints"] == []

    def test_data_quality_fields_present(self):
        state = _state(data_completeness=0.75, confidence_score=0.6,
                       failed_steps=["v1_pipeline"],
                       migration_analysis_completeness=0.5,
                       migration_analysis_failed_steps=["changelog:flask"])
        report = _template_report(state)
        dq = report["data_quality"]
        assert dq["completeness"] == 0.75
        assert dq["confidence"] == 0.6
        assert "v1_pipeline" in dq["failed_steps"]
        assert dq["migration_analysis_completeness"] == 0.5
        assert "changelog:flask" in dq["migration_analysis_failed_steps"]

    def test_none_fields_handled_gracefully(self):
        # deprecated_findings and migration_plan may be None in initial state
        state = _state(deprecated_findings=None, migration_plan=None)
        report = _template_report(state)
        assert report["key_findings"] == []
        assert report["migration_recommendations"] == []
        assert report["upstream_breaking_change_hints"] == []

    def test_no_rules_extracted_is_described_in_summary(self):
        state = _state(
            deprecated_findings=[],
            provenance=[
                {
                    "source": "deprecated_api_scan",
                    "status": "ok",
                    "rules_source": "no_rules_extracted",
                }
            ],
        )

        report = _template_report(state)

        assert "No deprecated-API rules were extracted" in report["summary"]
        assert report["data_quality"]["deprecated_api_rules_source"] == "no_rules_extracted"


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
        state = _state(health_score=44.0, risk_level="critical", critic_passed=True)
        result = report_node(state)
        assert result["final_report"]["health_score"] == 44.0
        assert result["final_report"]["risk_level"] == "critical"

    @patch("app.agents.report_node.LLMClient.is_available", return_value=False)
    def test_unresolved_critic_sets_unverified_risk(self, _mock):
        state = _state(health_score=94.0, risk_level="Low", critic_passed=False,
                       critic_feedback="High score with failed steps", retry_count=2)
        result = report_node(state)
        assert result["final_report"]["risk_level"] == "Unverified"
        assert result["final_report"]["critic"]["passed"] is False
        assert result["final_report"]["critic"]["retry_count"] == 2
        assert "High score" in result["final_report"]["critic"]["feedback"]
        assert "Unverified risk" in result["final_report"]["summary"]

    @patch("app.agents.report_node.LLMClient.is_available", return_value=False)
    def test_passing_critic_preserves_normal_risk(self, _mock):
        state = _state(health_score=80.0, risk_level="Low", critic_passed=True, retry_count=0)
        result = report_node(state)
        assert result["final_report"]["risk_level"] == "Low"
        assert result["final_report"]["critic"]["passed"] is True

    @patch("app.agents.report_node.LLMClient.is_available", return_value=False)
    def test_dynamic_rules_do_not_add_no_rules_notice(self, _mock):
        state = _state(
            deprecated_findings=[],
            provenance=[
                {
                    "source": "deprecated_api_scan",
                    "status": "ok",
                    "rules_source": "dynamic",
                }
            ],
        )

        result = report_node(state)

        assert "limited static fallback rules" not in result["final_report"]["summary"]
        assert result["final_report"]["data_quality"]["deprecated_api_rules_source"] == "dynamic"


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

        state = _state(health_score=72.0, risk_level="medium", critic_passed=True)
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
    def test_llm_empty_object_falls_back_to_template(self, MockLLM, _mock_avail):
        mock_instance = MagicMock()
        mock_instance.call.return_value = json.dumps({})
        MockLLM.return_value = mock_instance

        state = _state(health_score=50.0, risk_level="medium")
        result = report_node(state)

        assert _REQUIRED_KEYS.issubset(result["final_report"].keys())
        statuses = [e.get("status") for e in result["agent_trace"] if e.get("node") == "report"]
        assert "fallback" in statuses

    @patch("app.agents.report_node.LLMClient.is_available", return_value=True)
    @patch("app.agents.report_node.LLMClient")
    def test_llm_list_response_falls_back_to_template(self, MockLLM, _mock_avail):
        mock_instance = MagicMock()
        mock_instance.call.return_value = json.dumps([])
        MockLLM.return_value = mock_instance

        state = _state(health_score=50.0, risk_level="medium")
        result = report_node(state)

        assert _REQUIRED_KEYS.issubset(result["final_report"].keys())
        statuses = [e.get("status") for e in result["agent_trace"] if e.get("node") == "report"]
        assert "fallback" in statuses

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

    @patch("app.agents.report_node.LLMClient.is_available", return_value=True)
    @patch("app.agents.report_node.LLMClient")
    def test_no_rules_extracted_notice_is_added_to_llm_report(self, MockLLM, _mock_avail):
        mock_instance = MagicMock()
        mock_instance.call.return_value = json.dumps(_canned_report())
        MockLLM.return_value = mock_instance

        state = _state(
            deprecated_findings=[],
            provenance=[
                {
                    "source": "deprecated_api_scan",
                    "status": "ok",
                    "rules_source": "no_rules_extracted",
                }
            ],
        )

        result = report_node(state)

        assert "No deprecated-API rules were extracted" in result["final_report"]["summary"]
        assert (
            result["final_report"]["data_quality"]["deprecated_api_rules_source"]
            == "no_rules_extracted"
        )

    @patch("app.agents.report_node.LLMClient.is_available", return_value=True)
    @patch("app.agents.report_node.LLMClient")
    def test_llm_receives_unverified_effective_risk(self, MockLLM, _mock_avail):
        mock_instance = MagicMock()
        report = _canned_report(risk_level="Low")
        report["summary"] = "This repository is Low risk."
        mock_instance.call.return_value = json.dumps(report)
        MockLLM.return_value = mock_instance

        result = report_node(_state(risk_level="Low", critic_passed=False))

        user_prompt = mock_instance.call.call_args[0][1]
        assert "risk_level: Unverified" in user_prompt
        assert "Low risk" not in result["final_report"]["summary"]
        assert "Unverified risk" in result["final_report"]["summary"]

    @patch("app.agents.report_node.LLMClient.is_available", return_value=True)
    @patch("app.agents.report_node.LLMClient")
    def test_llm_migration_lists_are_overwritten_from_plan(self, MockLLM, _mock_avail):
        mock_instance = MagicMock()
        canned = _canned_report()
        canned["migration_recommendations"] = [
            {"action": "Invented recommendation", "priority": "high", "reason": "hallucinated"}
        ]
        canned["upstream_breaking_change_hints"] = []
        mock_instance.call.return_value = json.dumps(canned)
        MockLLM.return_value = mock_instance

        state = _state(
            critic_passed=True,
            migration_plan={
                "steps": [
                    {
                        "action": "Replace deprecated usage of `flask.ext` with `flask_sqlalchemy` (at app.py:10)",
                        "type": "deprecated_api_replacement",
                        "package": "flask",
                        "severity": "high",
                        "confidence": "ast_scan",
                        "occurrence_count": 1,
                    },
                    {
                        "action": "Removed support for Python 3.9",
                        "type": "breaking_change_review",
                        "package": "urllib3",
                        "severity": "high",
                        "confidence": "regex_heuristic",
                        "version_span": "1.26→2.7.0",
                    },
                ]
            },
        )
        result = report_node(state)
        recs = result["final_report"]["migration_recommendations"]
        hints = result["final_report"]["upstream_breaking_change_hints"]
        assert len(recs) == 1
        assert "flask.ext" in recs[0]["action"]
        assert "Invented recommendation" not in recs[0]["action"]
        assert len(hints) == 1
        assert "Python 3.9" in hints[0]["action"]
