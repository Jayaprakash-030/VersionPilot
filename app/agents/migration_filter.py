from __future__ import annotations

import json
from typing import Any

from app.agents.llm_client import LLMClient, merge_llm_usage

_SYSTEM_PROMPT = """\
You are filtering candidate dependency migration recommendations.

You must decide which existing candidate steps are worth showing to the user.
Do NOT invent new recommendations. Do NOT rewrite the steps. Only decide which
candidate IDs to keep.

Keep items that look like:
- API removals or renamed/removed methods/classes/functions
- runtime or platform support removals likely to affect adopters
- dependency/runtime behavior changes that may require code changes

Drop items that look like:
- CI, smoke test, benchmark, docs, packaging, release-process, or contributor changes
- "fix release" boilerplate that explicitly says behavior does not change
- restores/reverts that reduce breakage instead of introducing it
- cosmetic/UI changes and low-signal housekeeping

Return JSON only with this exact schema:
{
  "keep_ids": ["step-1", "step-2"],
  "drop_ids": ["step-3"],
  "rationale": "short sentence"
}
"""


def _estimate_effort(step_count: int) -> str:
    """Keep effort buckets aligned with the deterministic planner."""
    if step_count <= 2:
        return "low"
    if step_count <= 6:
        return "medium"
    return "high"


def filter_migration_plan(
    repo_url: str,
    migration_plan: dict[str, Any],
    telemetry: dict[str, Any],
) -> dict[str, Any]:
    """Filter heuristic migration steps with an LLM, preserving deterministic fallback."""
    steps = list((migration_plan or {}).get("steps") or [])
    heuristic_candidates: list[tuple[int, dict[str, Any], str]] = []
    for idx, step in enumerate(steps):
        if (
            step.get("type") == "breaking_change_review"
            and step.get("confidence") == "regex_heuristic"
        ):
            heuristic_candidates.append((idx, step, f"step-{idx + 1}"))

    if not heuristic_candidates:
        return {
            "status": "skipped",
            "reason": "no_heuristic_candidates",
            "migration_plan": migration_plan,
            "telemetry": telemetry,
            "kept_count": 0,
            "dropped_count": 0,
            "candidate_count": 0,
        }

    if not LLMClient.is_available():
        return {
            "status": "skipped",
            "reason": "llm_unavailable",
            "migration_plan": migration_plan,
            "telemetry": telemetry,
            "kept_count": len(heuristic_candidates),
            "dropped_count": 0,
            "candidate_count": len(heuristic_candidates),
        }

    llm = LLMClient()
    candidates_payload = [
        {
            "id": candidate_id,
            "package": step.get("package", "unknown"),
            "action": step.get("action", ""),
            "severity": step.get("severity", "high"),
            "version_span": step.get("version_span"),
            "confidence": step.get("confidence", "unknown"),
        }
        for _, step, candidate_id in heuristic_candidates
    ]
    user_prompt = (
        f"repo_url: {repo_url}\n"
        "candidate_steps:\n"
        f"{json.dumps(candidates_payload)}"
    )

    try:
        raw = llm.call(_SYSTEM_PROMPT, user_prompt, max_tokens=512)
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("filter response must be a JSON object")
        keep_ids = parsed.get("keep_ids")
        if not isinstance(keep_ids, list) or not all(
            isinstance(item, str) for item in keep_ids
        ):
            raise ValueError("filter response missing valid keep_ids")
        valid_ids = {candidate_id for _, _, candidate_id in heuristic_candidates}
        keep_id_set = {item for item in keep_ids if item in valid_ids}

        filtered_steps: list[dict[str, Any]] = []
        dropped_ids: list[str] = []
        for idx, step in enumerate(steps):
            matched_id = next(
                (candidate_id for cand_idx, _, candidate_id in heuristic_candidates if cand_idx == idx),
                None,
            )
            if matched_id is None:
                filtered_steps.append(step)
                continue
            if matched_id in keep_id_set:
                filtered_steps.append(step)
            else:
                dropped_ids.append(matched_id)

        updated_plan = dict(migration_plan)
        updated_plan["steps"] = filtered_steps
        updated_plan["total_steps"] = len(filtered_steps)
        updated_plan["effort_level"] = _estimate_effort(len(filtered_steps))
        updated_plan["llm_filter"] = {
            "status": "ok",
            "candidate_count": len(heuristic_candidates),
            "kept_ids": sorted(keep_id_set),
            "dropped_ids": dropped_ids,
            "rationale": parsed.get("rationale", ""),
        }
        return {
            "status": "ok",
            "reason": "filtered",
            "migration_plan": updated_plan,
            "telemetry": merge_llm_usage(telemetry, llm),
            "kept_count": len(keep_id_set),
            "dropped_count": len(dropped_ids),
            "candidate_count": len(heuristic_candidates),
        }
    except Exception as exc:
        updated_plan = dict(migration_plan)
        updated_plan["llm_filter"] = {
            "status": "fallback",
            "error": str(exc),
            "candidate_count": len(heuristic_candidates),
        }
        return {
            "status": "error",
            "reason": str(exc),
            "migration_plan": updated_plan,
            "telemetry": merge_llm_usage(telemetry, llm),
            "kept_count": len(heuristic_candidates),
            "dropped_count": 0,
            "candidate_count": len(heuristic_candidates),
        }
