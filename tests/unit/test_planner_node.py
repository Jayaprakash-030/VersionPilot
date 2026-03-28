from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from app.agents.planner_node import planner_node


def _base_state(**overrides) -> dict:
    state = {
        "repo_url": "https://github.com/test/repo",
        "repo_path": "",
        "agent_trace": [],
    }
    state.update(overrides)
    return state


# ---------------------------------------------------------------------------
# Fallback (LLM unavailable)
# ---------------------------------------------------------------------------

def test_fallback_no_repo_path_gives_lightweight():
    with patch("app.agents.planner_node.LLMClient.is_available", return_value=False):
        result = planner_node(_base_state(repo_path=""))
    assert result["agent_plan"]["strategy"] == "lightweight"
    assert "deprecated_api_scan" in result["agent_plan"]["skip_steps"]


def test_fallback_with_repo_path_gives_full():
    with patch("app.agents.planner_node.LLMClient.is_available", return_value=False):
        result = planner_node(_base_state(repo_path="/some/local/path"))
    assert result["agent_plan"]["strategy"] == "full"
    assert result["agent_plan"]["skip_steps"] == []


def test_fallback_trace_records_fallback_status():
    with patch("app.agents.planner_node.LLMClient.is_available", return_value=False):
        result = planner_node(_base_state())
    last_trace = result["agent_trace"][-1]
    assert last_trace["node"] == "planner"
    assert last_trace["status"] == "fallback"


# ---------------------------------------------------------------------------
# LLM path (mocked)
# ---------------------------------------------------------------------------

def test_llm_plan_written_to_state():
    mock_plan = {"strategy": "full", "skip_steps": []}
    mock_llm = MagicMock()
    mock_llm.call.return_value = json.dumps(mock_plan)

    with patch("app.agents.planner_node.LLMClient.is_available", return_value=True), \
         patch("app.agents.planner_node.LLMClient", return_value=mock_llm):
        result = planner_node(_base_state(repo_path="/some/path"))

    assert result["agent_plan"] == mock_plan


def test_llm_trace_records_complete_status():
    mock_llm = MagicMock()
    mock_llm.call.return_value = json.dumps({"strategy": "lightweight", "skip_steps": ["deprecated_api_scan"]})

    with patch("app.agents.planner_node.LLMClient.is_available", return_value=True), \
         patch("app.agents.planner_node.LLMClient", return_value=mock_llm):
        result = planner_node(_base_state())

    assert result["agent_trace"][-1]["status"] == "complete"


def test_llm_failure_falls_back_to_default():
    mock_llm = MagicMock()
    mock_llm.call.side_effect = RuntimeError("LLM error")

    with patch("app.agents.planner_node.LLMClient.is_available", return_value=True), \
         patch("app.agents.planner_node.LLMClient", return_value=mock_llm):
        result = planner_node(_base_state(repo_path=""))

    assert result["agent_plan"]["strategy"] == "lightweight"
    assert result["agent_trace"][-1]["status"] == "fallback"


def test_llm_bad_json_falls_back_to_default():
    mock_llm = MagicMock()
    mock_llm.call.return_value = "not valid json"

    with patch("app.agents.planner_node.LLMClient.is_available", return_value=True), \
         patch("app.agents.planner_node.LLMClient", return_value=mock_llm):
        result = planner_node(_base_state(repo_path="/some/path"))

    assert result["agent_plan"]["strategy"] == "full"
    assert result["agent_trace"][-1]["status"] == "fallback"


# ---------------------------------------------------------------------------
# General
# ---------------------------------------------------------------------------

def test_agent_plan_always_present():
    with patch("app.agents.planner_node.LLMClient.is_available", return_value=False):
        result = planner_node(_base_state())
    assert "agent_plan" in result
    assert "strategy" in result["agent_plan"]
    assert "skip_steps" in result["agent_plan"]


def test_prior_trace_entries_preserved():
    prior = [{"node": "some_prior", "status": "ok"}]
    with patch("app.agents.planner_node.LLMClient.is_available", return_value=False):
        result = planner_node(_base_state(agent_trace=prior))
    assert result["agent_trace"][0]["node"] == "some_prior"
    assert len(result["agent_trace"]) == 2
