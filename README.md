# VersionPilot

AI-driven dependency health and migration assistant. Goes beyond "you are outdated" to answer:
**"what will break in your code, where, and here is the exact migration path."**

Portfolio project demonstrating agentic AI orchestration with real evaluation metrics and MLOps practices.

---

## What It Does

Most tools tell you *that* you are outdated. VersionPilot tells you:

- What is the health score of this repository's dependencies?
- Which deprecated APIs are you actively calling, and on which line?
- What breaking changes are in the release notes of your dependencies?
- What are the exact migration steps to upgrade safely?

---

## Architecture

### Two modes

```bash
# Deterministic V1 pipeline — fast, no LLM
python -m app.main https://github.com/owner/repo --mode basic --json

# LangGraph multi-agent system — full analysis with LLM synthesis
python -m app.main https://github.com/owner/repo --mode agent --json
```

### LangGraph graph (agent mode)

```
START → planner_node → evidence_node → scoring_node → critic_node
                                            ↑               ↓
                                       recovery_node   [pass/fail]
                                                            ↓
                                                       report_node → END
```

| Node | Type | Responsibility |
|------|------|---------------|
| `planner_node` | LLM | Decides analysis strategy (full vs lightweight) |
| `evidence_node` | Deterministic | Runs all tools, auto-clones repo, tracks provenance |
| `scoring_node` | Deterministic | Computes health score from collected signals |
| `critic_node` | LLM | Validates consistency, flags suspicious results |
| `recovery_node` | Deterministic | Degrades confidence, increments retry count |
| `report_node` | LLM | Synthesizes grounded final report (no hallucination) |

---

## Project Structure

```
app/
├── core/               V1 pipeline foundations
│   ├── pipeline.py         orchestrates GitHub → deps → freshness → OSV → score
│   ├── risk_scoring.py     weighted scoring (activity 30% / deps 40% / security 30%)
│   ├── models.py           frozen dataclasses (RepoMetrics, DependencyMetrics, etc.)
│   ├── github_client.py    GitHub API calls
│   ├── dependency_parser.py  requirements.txt / pyproject.toml parser
│   ├── dependency_freshness.py  version-aware outdated detection
│   ├── vulnerability_scanner.py  OSV batch security scan
│   └── retry.py            exponential backoff with jitter
├── analysis/           Phase 2 differentiator tools
│   ├── deprecated_api_scanner.py  AST scanner for deprecated symbols
│   ├── changelog_analyzer.py      regex parser for breaking changes
│   ├── release_notes_fetcher.py   fetch GitHub releases or PyPI descriptions
│   └── migration_planner.py       ordered migration steps from findings
├── agents/             LangGraph multi-agent system
│   ├── graph.py             StateGraph + conditional edges + run_graph()
│   ├── state.py             VersionPilotState TypedDict
│   ├── planner_node.py
│   ├── evidence_node.py
│   ├── scoring_node.py
│   ├── critic_node.py
│   ├── recovery_node.py
│   ├── report_node.py
│   └── llm_client.py        OpenAI Responses API wrapper
├── tools/              LangGraph tool wrappers
│   ├── tool_registry.py     wraps all modules as callable tools + clone_repo
│   └── rules_extractor.py   LLM extracts deprecation rules from release notes
└── main.py             CLI entry point

config/
  scoring_v1.yaml       scoring weights and thresholds

data/
  deprecation_rules.json  static fallback deprecation rules
  benchmark_repos.txt     legacy batch-run repository list

eval/
  run_eval.py             current batch evaluation runner
  EVAL_REPORT.md          planned published evaluation results

tests/
  unit/                 26 test files
  integration/
```

---

## How To Run

### Setup

```bash
python -m venv vpilot
source vpilot/bin/activate
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in:

```
GITHUB_TOKEN=...             # required for all modes
OPENAI_API_KEY=...           # required for agent mode and rules extraction evals
OPENAI_MODEL=gpt-5.4-nano    # optional override; defaults to gpt-5.4-nano
```

### Basic mode (no LLM required)

```bash
python -m app.main https://github.com/psf/requests --mode basic --json
```

### Agent mode (LangGraph + LLM)

```bash
# Auto-clones the repo for deprecated API scanning
python -m app.main https://github.com/psf/requests --mode agent --json

# Or provide a local path to skip the clone
python -m app.main https://github.com/psf/requests --mode agent --repo-path /path/to/requests --json
```

### Other options

```bash
--config config/scoring_v1.yaml   # scoring config (default)
--output report.json              # save to file (default: artifacts/<run_id>.json)
--force                           # recompute even if artifact exists
--json                            # print JSON to stdout
```

### Evaluation

```bash
# Existing batch runner
python -m eval.run_eval --repos-file data/benchmark_repos.txt --output eval/eval_report.json
```

The focused portfolio evaluation plan is documented in [Eval.md](Eval.md). It measures:

- Deprecated API scanner precision, recall, F1, and source-line accuracy
- Scoring behavioral correctness
- Controlled migration outcomes
- Reliability under simulated API and LLM failures

The completed metrics and limitations will be published in
`eval/EVAL_REPORT.md`.

---

## Testing

```bash
vpilot/bin/python -m pytest tests/ -v        # all tests
vpilot/bin/python -m pytest tests/unit/ -v   # unit only
```

---

## LLM Configuration

OpenAI is accessed through the Responses API.

Default model in `app/agents/llm_client.py`:

```text
gpt-5.4-nano
```

All LLM nodes have deterministic fallbacks — agent mode degrades gracefully when credentials are unavailable.

---

## Health Report Output

```json
{
  "summary": "...",
  "health_score": 78.4,
  "risk_level": "medium",
  "key_findings": [
    {"finding": "...", "evidence": "...", "severity": "high"}
  ],
  "migration_recommendations": [
    {"action": "...", "priority": "high", "reason": "..."}
  ],
  "data_quality": {
    "completeness": 0.95,
    "confidence": 0.88,
    "failed_steps": []
  }
}
```

---

## Known Limitations

- `dependency_parser` only handles `requirements.txt` and `pyproject.toml`. Repos using `setup.py`/`setup.cfg` will have 0 dependencies parsed.
- Release notes are fetched for the **latest PyPI version**, not the version pinned in requirements. Deprecation findings may include symbols not relevant until the user actually upgrades.
- Auto-clone uses `--depth=1` (sufficient for AST scanning, no full git history).
- npm / non-Python ecosystems not yet supported.
