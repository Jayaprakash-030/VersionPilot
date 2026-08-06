from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.agents.critic_node import critic_node
from app.agents.graph import with_timing
from app.agents.llm_client import LLMClient, merge_llm_usage
from app.agents.planner_node import planner_node
from app.agents.report_node import report_node
from app.agents.state import create_initial_state


def test_estimate_cost_usd_one_million_tokens_each():
    assert LLMClient.estimate_cost_usd(1_000_000, 1_000_000) == 1.45


def test_merge_llm_usage_adds_tokens_once_and_recomputes_cost():
    llm = MagicMock()
    llm.total_input_tokens = 1_000
    llm.total_output_tokens = 500
    llm.last_model_used = "gpt-5.4-nano"
    llm.model = "gpt-5.4-nano"

    telemetry = merge_llm_usage(
        {
            "input_tokens": 2_000,
            "output_tokens": 100,
            "estimated_cost_usd": 0.0,
            "model": "",
        },
        llm,
    )

    assert telemetry["input_tokens"] == 3_000
    assert telemetry["output_tokens"] == 600
    assert telemetry["model"] == "gpt-5.4-nano"
    assert telemetry["estimated_cost_usd"] == LLMClient.estimate_cost_usd(3_000, 600)


def test_planner_fallback_returns_zero_token_telemetry():
    state = create_initial_state("https://github.com/psf/requests")
    with patch("app.agents.planner_node.LLMClient.is_available", return_value=False):
        result = planner_node(state)

    telemetry = result["telemetry"]
    assert telemetry["input_tokens"] == 0
    assert telemetry["output_tokens"] == 0
    assert telemetry["estimated_cost_usd"] == 0.0


def test_critic_fallback_returns_zero_token_telemetry():
    state = create_initial_state("https://github.com/psf/requests")
    with patch("app.agents.critic_node.LLMClient.is_available", return_value=False):
        result = critic_node(state)

    telemetry = result["telemetry"]
    assert telemetry["input_tokens"] == 0
    assert telemetry["output_tokens"] == 0
    assert telemetry["estimated_cost_usd"] == 0.0


def test_report_embeds_telemetry_on_final_report():
    state = create_initial_state("https://github.com/psf/requests")
    state["telemetry"] = {
        "model": "",
        "node_timings_ms": {"planner": 1.0},
        "total_wall_ms": 0.0,
        "input_tokens": 0,
        "output_tokens": 0,
        "estimated_cost_usd": 0.0,
    }
    with patch("app.agents.report_node.LLMClient.is_available", return_value=False):
        result = report_node(state)

    assert "telemetry" in result["final_report"]
    assert result["final_report"]["telemetry"]["input_tokens"] == 0
    assert result["final_report"]["telemetry"] is result["telemetry"]


def test_with_timing_records_node_timings_ms():
    def fake_node(state):
        return {"agent_plan": {"strategy": "full"}}

    wrapped = with_timing("planner", fake_node)
    state = create_initial_state("https://github.com/psf/requests")
    result = wrapped(state)

    timings = result["telemetry"]["node_timings_ms"]
    assert "planner" in timings
    assert timings["planner"] >= 0.0
