from __future__ import annotations

import json

from app.agents.state import VersionPilotState
from app.agents.llm_client import LLMClient

_SYSTEM_PROMPT = """\
You are a dependency analysis planner. Given a repository URL and an optional local path,
decide the analysis strategy. Return JSON only — no explanation.

Output format:
{
  "strategy": "full" or "lightweight",
  "skip_steps": []
}

Rules:
- Use "full" when a local repo path is provided (deprecated API scan is possible).
- Use "lightweight" when no local path is given (skip deprecated_api_scan).
- "skip_steps" lists any tool names to skip (e.g. ["deprecated_api_scan"]).
"""


def _default_plan(repo_path: str) -> dict:
    if repo_path:
        return {"strategy": "full", "skip_steps": []}
    return {"strategy": "lightweight", "skip_steps": ["deprecated_api_scan"]}


def planner_node(state: VersionPilotState) -> dict:
    """LLM node: decides analysis strategy. Falls back to deterministic default."""
    trace = list(state.get("agent_trace", []))
    repo_url = state.get("repo_url", "")
    repo_path = state.get("repo_path", "")

    agent_plan = None

    if LLMClient.is_available():
        try:
            llm = LLMClient()
            user_prompt = f"Repository URL: {repo_url}\nLocal path: {repo_path or '(not provided)'}"
            raw = llm.call(_SYSTEM_PROMPT, user_prompt, max_tokens=256)
            agent_plan = json.loads(raw)
        except Exception:
            agent_plan = None  # fall through to default

    if agent_plan is None:
        agent_plan = _default_plan(repo_path)
        trace.append({"node": "planner", "status": "fallback", "plan": agent_plan})
    else:
        trace.append({"node": "planner", "status": "complete", "plan": agent_plan})

    return {"agent_plan": agent_plan, "agent_trace": trace}
