from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.agents.llm_client import LLMClient
from app.agents.migration_filter import filter_migration_plan


def _plan() -> dict:
    return {
        "total_steps": 4,
        "effort_level": "medium",
        "steps": [
            {
                "type": "deprecated_api_replacement",
                "action": "Replace flask.ext usage",
                "package": "flask",
                "severity": "high",
                "confidence": "ast_scan",
            },
            {
                "type": "breaking_change_review",
                "action": "Removed smoke-test flag from CI matrix",
                "package": "celery",
                "severity": "high",
                "confidence": "regex_heuristic",
                "version_span": "5.0→5.6",
            },
            {
                "type": "breaking_change_review",
                "action": "Removed the `HTTPResponse.getheaders()` method in favor of `HTTPResponse.headers`.",
                "package": "urllib3",
                "severity": "high",
                "confidence": "regex_heuristic",
                "version_span": "1.26→2.7.0",
            },
            {
                "type": "breaking_change_review",
                "action": "This is the Click 8.4.1 fix release, which does not otherwise change behavior.",
                "package": "click",
                "severity": "high",
                "confidence": "regex_heuristic",
                "version_span": "8.1.3→8.4.2",
            },
        ],
    }


def _telemetry() -> dict:
    return {
        "model": "",
        "node_timings_ms": {},
        "total_wall_ms": 0.0,
        "input_tokens": 10,
        "output_tokens": 2,
        "estimated_cost_usd": LLMClient.estimate_cost_usd(10, 2),
    }


@patch("app.agents.migration_filter.LLMClient.is_available", return_value=False)
def test_skips_when_llm_unavailable(_mock_avail):
    result = filter_migration_plan(
        "https://github.com/example/repo",
        _plan(),
        _telemetry(),
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "llm_unavailable"
    assert result["migration_plan"]["steps"] == _plan()["steps"]


@patch("app.agents.migration_filter.LLMClient.is_available", return_value=True)
@patch("app.agents.migration_filter.LLMClient")
def test_filters_only_selected_heuristic_steps(MockLLM, _mock_avail):
    llm = MagicMock()
    llm.call.return_value = json.dumps(
        {
            "keep_ids": ["step-3"],
            "drop_ids": ["step-2", "step-4"],
            "rationale": "Keep API removals; drop CI and fix-release boilerplate.",
        }
    )
    llm.total_input_tokens = 100
    llm.total_output_tokens = 20
    llm.last_model_used = "gpt-5.4-nano"
    llm.model = "gpt-5.4-nano"
    MockLLM.return_value = llm

    result = filter_migration_plan(
        "https://github.com/example/repo",
        _plan(),
        _telemetry(),
    )

    assert result["status"] == "ok"
    actions = [step["action"] for step in result["migration_plan"]["steps"]]
    assert "Replace flask.ext usage" in actions
    assert any("getheaders" in action for action in actions)
    assert not any("smoke-test" in action for action in actions)
    assert not any("fix release" in action for action in actions)
    assert result["migration_plan"]["llm_filter"]["kept_ids"] == ["step-3"]
    assert result["telemetry"]["input_tokens"] == 110
    assert result["telemetry"]["output_tokens"] == 22


@patch("app.agents.migration_filter.LLMClient.is_available", return_value=True)
@patch("app.agents.migration_filter.LLMClient")
def test_invalid_filter_response_falls_back_to_original_steps(MockLLM, _mock_avail):
    llm = MagicMock()
    llm.call.return_value = json.dumps({"unexpected": True})
    llm.total_input_tokens = 20
    llm.total_output_tokens = 5
    llm.last_model_used = "gpt-5.4-nano"
    llm.model = "gpt-5.4-nano"
    MockLLM.return_value = llm

    original = _plan()
    result = filter_migration_plan(
        "https://github.com/example/repo",
        original,
        _telemetry(),
    )

    assert result["status"] == "error"
    assert result["migration_plan"]["steps"] == original["steps"]
    assert result["migration_plan"]["llm_filter"]["status"] == "fallback"


@patch("app.agents.migration_filter.LLMClient.is_available", return_value=True)
@patch("app.agents.migration_filter.LLMClient")
def test_allow_dropping_all_heuristic_steps(MockLLM, _mock_avail):
    llm = MagicMock()
    llm.call.return_value = json.dumps(
        {
            "keep_ids": [],
            "drop_ids": ["step-2", "step-3", "step-4"],
            "rationale": "All heuristic steps are noise.",
        }
    )
    llm.total_input_tokens = 10
    llm.total_output_tokens = 5
    llm.last_model_used = "gpt-5.4-nano"
    llm.model = "gpt-5.4-nano"
    MockLLM.return_value = llm

    result = filter_migration_plan(
        "https://github.com/example/repo",
        _plan(),
        _telemetry(),
    )

    assert result["status"] == "ok"
    assert len(result["migration_plan"]["steps"]) == 1
    assert result["migration_plan"]["steps"][0]["type"] == "deprecated_api_replacement"
