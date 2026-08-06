from __future__ import annotations

import shutil
from datetime import datetime, timezone

from app.agents.state import VersionPilotState
from app.agents.llm_client import merge_llm_usage
from app.tools.rules_extractor import RulesExtractor
from app.tools.tool_registry import ToolRegistry


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 timestamp string."""
    return datetime.now(timezone.utc).isoformat()


def evidence_node(state: VersionPilotState) -> dict:
    """Deterministic node: runs all tools, populates state signals, tracks provenance."""
    registry = ToolRegistry()
    extractor = RulesExtractor()  # handles LLM unavailability internally

    provenance: list[dict] = list(state.get("provenance", []))
    failed_steps: list[str] = list(state.get("failed_steps", []))
    migration_failed_steps: list[str] = list(state.get("migration_analysis_failed_steps", []))
    migration_checks_total = 0
    migration_checks_complete = 0
    trace: list[dict] = list(state.get("agent_trace", []))
    telemetry = dict(state.get("telemetry") or {})

    def record_migration_check(step: str, status: str) -> None:
        """Track migration-analysis step outcomes for completeness scoring."""
        nonlocal migration_checks_total, migration_checks_complete
        if status == "skipped":
            return
        migration_checks_total += 1
        if status == "ok":
            migration_checks_complete += 1
        elif step not in migration_failed_steps:
            migration_failed_steps.append(step)

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
    record_migration_check("fetch_dependency_names", dep_names_result.get("status", "ok"))
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
        record_migration_check(f"release_notes:{pkg_name}", notes_result.get("status", "ok"))

        notes_text = notes_result.get("notes_text", "")
        if not notes_text:
            continue

        # LLM extracts deprecation rules and exposes whether an empty result was verified.
        pkg_rules = extractor.build_rules_dict(pkg_name, notes_text)
        extraction_status = extractor.last_extraction_status
        if extraction_status not in {"ok", "unavailable", "error", "skipped"}:
            extraction_status = "ok"
        provenance.append({
            "source": f"rules_extraction:{pkg_name}",
            "timestamp": _now_iso(),
            "status": extraction_status,
        })
        record_migration_check(f"rules_extraction:{pkg_name}", extraction_status)
        if pkg_rules:
            combined_rules.update(pkg_rules)

        # Deterministic changelog analysis for breaking changes
        changelog_result = registry.analyze_changelog(notes_text, pkg_name)
        provenance.append({
            "source": f"changelog:{pkg_name}",
            "timestamp": _now_iso(),
            "status": changelog_result.get("status", "ok"),
        })
        record_migration_check(f"changelog:{pkg_name}", changelog_result.get("status", "ok"))
        if changelog_result.get("status") == "ok":
            breaking_changes_list.append(changelog_result)

    # ------------------------------------------------------------------
    # Step 4: Deprecated API scan (auto-clone if repo_path not provided)
    # ------------------------------------------------------------------
    deprecated_findings: list[dict] = []
    repo_path: str = state.get("repo_path") or ""
    cloned_tmp: str | None = None

    skip_steps: list[str] = (state.get("agent_plan") or {}).get("skip_steps", [])

    if "deprecated_api_scan" in skip_steps:
        provenance.append({
            "source": "deprecated_api_scan",
            "timestamp": _now_iso(),
            "status": "skipped",
        })
        record_migration_check("deprecated_api_scan", "skipped")
    elif not repo_path:
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
            record_migration_check("deprecated_api_scan", "error")

    if repo_path and "deprecated_api_scan" not in skip_steps:
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
                "rules_source": scan_result.get("rules_source", "unknown"),
            })
            if scan_result.get("status") == "ok":
                deprecated_findings = scan_result.get("findings", [])
            else:
                failed_steps.append("deprecated_api_scan")
            record_migration_check("deprecated_api_scan", scan_result.get("status", "ok"))
        except Exception as exc:
            failed_steps.append("deprecated_api_scan")
            record_migration_check("deprecated_api_scan", "error")
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
        "findings": [
            {**finding, "package": pkg_result.get("package", "unknown")}
            for pkg_result in breaking_changes_list
            for finding in pkg_result.get("findings", [])
        ],
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
    record_migration_check("migration_planner", migration_result.get("status", "ok"))
    migration_plan = migration_result if migration_result.get("status") == "ok" else {}
    migration_completeness = (
        round(migration_checks_complete / migration_checks_total, 2)
        if migration_checks_total
        else 1.0
    )

    trace.append({
        "node": "evidence",
        "status": "complete",
        "tools_run": len(provenance),
        "deps_analyzed": len(dependency_names),
        "failed_steps": list(failed_steps),
        "migration_analysis_completeness": migration_completeness,
        "migration_analysis_failed_steps": list(migration_failed_steps),
    })

    # One shared RulesExtractor client may make many calls — merge its totals once.
    if extractor.llm is not None:
        telemetry = merge_llm_usage(telemetry, extractor.llm)

    return {
        "repo_metrics": pipeline_result.get("repo_metrics", {}),
        "dependency_metrics": pipeline_result.get("dependency_metrics", {}),
        "security_metrics": pipeline_result.get("security_metrics", {}),
        "deprecated_findings": deprecated_findings,
        "breaking_change_analysis": breaking_change_analysis,
        "migration_plan": migration_plan,
        "migration_analysis_completeness": migration_completeness,
        "migration_analysis_failed_steps": migration_failed_steps,
        "provenance": provenance,
        "failed_steps": failed_steps,
        "agent_trace": trace,
        "telemetry": telemetry,
    }
