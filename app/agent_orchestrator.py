from __future__ import annotations

from typing import Any, Dict, List

from .pipeline import run_pipeline


class AgentOrchestrator:
    """Minimal V2 orchestrator skeleton that wraps existing V1 pipeline tools."""

    def analyze_repository(self, repo_url: str, config_path: str = "config/scoring_v1.yaml") -> Dict[str, Any]:
        agent_trace: List[Dict[str, str]] = [
            {"agent": "orchestrator", "action": "plan_analysis"},
            {"agent": "repo_agent", "action": "collect_repo_signals"},
            {"agent": "dependency_agent", "action": "collect_dependency_signals"},
            {"agent": "security_agent", "action": "collect_security_signals"},
            {"agent": "scoring_agent", "action": "compute_health_score"},
            {"agent": "report_agent", "action": "assemble_report"},
        ]

        report = run_pipeline(repo_url=repo_url, config_path=config_path)

        return {
            "mode": "agent",
            "agent_plan": {
                "strategy": "sequential_tool_orchestration",
                "version": "v2_skeleton",
            },
            "agent_trace": agent_trace,
            "report": report.to_dict(),
        }
