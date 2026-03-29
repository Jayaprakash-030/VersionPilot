from __future__ import annotations

import shutil
from datetime import datetime, timezone

from app.agents.state import VersionPilotState
from app.tools.rules_extractor import RulesExtractor
from app.tools.tool_registry import ToolRegistry


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def evidence_node(state: VersionPilotState) -> dict:
    """Deterministic node: runs all tools, populates state signals, tracks provenance."""
    registry = ToolRegistry()
    extractor = RulesExtractor()  # handles LLM unavailability internally

    provenance: list[dict] = list(state.get("provenance", []))
    failed_steps: list[str] = list(state.get("failed_steps", []))
    trace: list[dict] = list(state.get("agent_trace", []))

    # ------------------------------------------------------------------
    # Step 1: V1 pipeline (repo metrics, dependency counts, security)
    # ------------------------------------------------------------------
    config_version = state.get("config_version", "config/scoring_v1.yaml")
    pipeline_result = registry.run_v1_pipeline(state["repo_url"], config_version)
    provenance.append({
        "source": "v1_pipeline",
        "timestamp": _now_iso(),
        "status": pipeline_result.get("status", "ok"),
    })
    if pipeline_result.get("status") == "error":
        failed_steps.append("v1_pipeline")

    # Merge any failed steps reported by the V1 pipeline itself
    for step in pipeline_result.get("failed_steps", []):
        if step not in failed_steps:
            failed_steps.append(step)

    # ------------------------------------------------------------------
    # Step 2: Fetch dependency names for per-dependency release notes
    # ------------------------------------------------------------------
    dep_names_result = registry.fetch_dependency_names(state["repo_url"])
    provenance.append({
        "source": "fetch_dependency_names",
        "timestamp": _now_iso(),
        "status": dep_names_result.get("status", "ok"),
    })
    if dep_names_result.get("status") == "error":
        failed_steps.append("fetch_dependency_names")
    dependency_names: list[str] = dep_names_result.get("names", [])

    # ------------------------------------------------------------------
    # Step 3: Per-dependency release notes + LLM rule extraction + changelog analysis
    # ------------------------------------------------------------------
    combined_rules: dict = {}
    breaking_changes_list: list[dict] = []

    for pkg_name in dependency_names:
        notes_result = registry.fetch_dependency_release_notes(pkg_name)
        provenance.append({
            "source": f"release_notes:{pkg_name}",
            "timestamp": _now_iso(),
            "status": notes_result.get("status", "ok"),
        })

        notes_text = notes_result.get("notes_text", "")
        if not notes_text:
            continue

        # LLM extracts deprecation rules (silently no-ops if LLM unavailable)
        pkg_rules = extractor.build_rules_dict(pkg_name, notes_text)
        if pkg_rules:
            combined_rules.update(pkg_rules)

        # Deterministic changelog analysis for breaking changes
        changelog_result = registry.analyze_changelog(notes_text, pkg_name)
        provenance.append({
            "source": f"changelog:{pkg_name}",
            "timestamp": _now_iso(),
            "status": changelog_result.get("status", "ok"),
        })
        if changelog_result.get("status") == "ok":
            breaking_changes_list.append(changelog_result)

    # ------------------------------------------------------------------
    # Step 4: Deprecated API scan (auto-clone if repo_path not provided)
    # ------------------------------------------------------------------
    deprecated_findings: list[dict] = []
    repo_path: str = state.get("repo_path") or ""
    cloned_tmp: str | None = None

    if not repo_path:
        clone_result = registry.clone_repo(state["repo_url"])
        provenance.append({
            "source": "clone_repo",
            "timestamp": _now_iso(),
            "status": clone_result.get("status", "ok"),
        })
        if clone_result.get("status") == "ok":
            repo_path = clone_result["repo_path"]
            cloned_tmp = repo_path
        else:
            failed_steps.append("clone_repo")

    if repo_path:
        try:
            # Use LLM-extracted rules if available, else fall back to static rules file
            scan_result = registry.scan_deprecated_apis(
                repo_path,
                rules=combined_rules if combined_rules else None,
            )
            provenance.append({
                "source": "deprecated_api_scan",
                "timestamp": _now_iso(),
                "status": scan_result.get("status", "ok"),
            })
            if scan_result.get("status") == "ok":
                deprecated_findings = scan_result.get("findings", [])
            else:
                failed_steps.append("deprecated_api_scan")
        except Exception as exc:
            failed_steps.append("deprecated_api_scan")
            provenance.append({
                "source": "deprecated_api_scan",
                "timestamp": _now_iso(),
                "status": "error",
                "error": str(exc),
            })
        finally:
            if cloned_tmp:
                shutil.rmtree(cloned_tmp, ignore_errors=True)

    # ------------------------------------------------------------------
    # Step 5: Aggregate breaking change analysis
    # ------------------------------------------------------------------
    breaking_change_analysis = {
        "packages": breaking_changes_list,
        "total_packages_analyzed": len(breaking_changes_list),
    }

    # ------------------------------------------------------------------
    # Step 6: Migration plan
    # ------------------------------------------------------------------
    migration_result = registry.generate_migration_plan(deprecated_findings, breaking_change_analysis)
    provenance.append({
        "source": "migration_planner",
        "timestamp": _now_iso(),
        "status": migration_result.get("status", "ok"),
    })
    if migration_result.get("status") == "error":
        failed_steps.append("migration_planner")
    migration_plan = migration_result if migration_result.get("status") == "ok" else {}

    trace.append({
        "node": "evidence",
        "status": "complete",
        "tools_run": len(provenance),
        "deps_analyzed": len(dependency_names),
        "failed_steps": list(failed_steps),
    })

    return {
        "repo_metrics": pipeline_result.get("repo_metrics", {}),
        "dependency_metrics": pipeline_result.get("dependency_metrics", {}),
        "security_metrics": pipeline_result.get("security_metrics", {}),
        "deprecated_findings": deprecated_findings,
        "breaking_change_analysis": breaking_change_analysis,
        "migration_plan": migration_plan,
        "provenance": provenance,
        "failed_steps": failed_steps,
        "agent_trace": trace,
    }
