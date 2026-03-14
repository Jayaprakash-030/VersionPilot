# VersionPilot

VersionPilot is an AI-driven dependency health and migration assistant project.

Current status:
- **V1 foundation is implemented** (deterministic health analysis pipeline).
- **V2 agentic mode has started** (orchestrator skeleton wired into CLI).

The goal is to evolve from basic dependency health scoring to a differentiated system that answers:
- What is risky?
- What will break if we upgrade?
- How do we migrate safely?

## Vision

Most tools say: "you are outdated".
VersionPilot aims to say: "what will break, where, and how to fix it."

### Product direction
1. Analyze dependencies and repository health.
2. Detect deprecated API usage in real code.
3. Analyze upgrade breakage risk.
4. Generate actionable migration roadmaps.
5. Use agentic orchestration to adapt analysis strategy and produce contextual reports.

## Architecture

## V1 (implemented)
- CLI entrypoint: `app/main.py` (`--mode basic`)
- Deterministic pipeline: `app/pipeline.py`
- Signals:
  - GitHub activity (`app/github_client.py`)
  - Dependency parsing (`app/dependency_parser.py`)
  - Dependency freshness (`app/dependency_freshness.py`)
  - Security scan via OSV (`app/vulnerability_scanner.py`)
- Scoring config: `config/scoring_v1.yaml`
- Reliability:
  - retries (`app/retry.py`)
  - `failed_steps` + `failed_reasons`
  - `data_completeness` + `confidence_score`
- Evaluation runner: `eval/run_eval.py`

## V2 (started)
- Agent orchestrator skeleton: `app/agent_orchestrator.py`
- CLI support for agent mode: `--mode agent`
- Agent mode currently wraps existing V1 pipeline and emits:
  - `agent_plan`
  - `agent_trace`
  - nested `report`

## What Is Implemented (Detailed)

### CLI capabilities
- `--mode basic|agent`
- `--config`
- `--output`
- artifact reuse by default
- `--force` to recompute
- `--json` for JSON stdout

### Health report fields
- `health_score`, `risk_level`, `breakdown`
- `repo_metrics`, `dependency_metrics`, `security_metrics`
- `failed_steps`, `failed_reasons`
- `data_completeness`, `confidence_score`

### Activity scoring inputs
- commit recency
- release recency
- open issue penalty
- issue resolution bonus

### Dependency freshness
- version-aware comparison using `packaging.version`
- policy-controlled outdated counting (`major/minor/patch` gap levels)

### Security scanning
- OSV batch query
- version-aware dependency query when version is known
- highest severity per dependency aggregation

## What We Want To Implement Next

### Phase 2: Differentiator features
1. **Deprecated API Scanner**
- Scan Python code AST for deprecated symbols usage.
- Output file/line-level findings with replacement hints.

2. **Breaking Change Analyzer**
- Analyze changelogs/releases between current and target versions.
- Identify likely breaking changes and map to code findings.

3. **Migration Planner**
- Generate ordered upgrade steps.
- Include impacted files/symbols and effort estimates.

### Phase 3: Full agentic orchestration
- Orchestrator delegates to specialist agents:
  - code analysis agent
  - deprecation detective agent
  - migration planner agent
  - risk assessment/critic agent
- Agentic report synthesis with reasoning + evidence trace.

## Project Structure

```text
app/
  main.py
  pipeline.py
  agent_orchestrator.py
  models.py
  risk_scoring.py
  github_client.py
  dependency_parser.py
  dependency_freshness.py
  vulnerability_scanner.py
  retry.py

config/
  scoring_v1.yaml

data/
  benchmark_repos.txt

eval/
  run_eval.py
  eval_report.json

tests/
  unit/
  integration/
```

## How To Run

### Basic deterministic mode

```bash
python -m app.main https://github.com/owner/repo --mode basic --force
```

### Agent mode (current skeleton)

```bash
python -m app.main https://github.com/owner/repo --mode agent --force --json
```

### Batch evaluation

```bash
python -m eval.run_eval --repos-file data/benchmark_repos.txt --output eval/eval_report.json
```

## Testing

```bash
python -m unittest discover -s tests/unit -p "test_*.py"
python -m unittest discover -s tests/integration -p "test_*.py"
```

## Current Limitations

- npm ecosystem support not implemented yet.
- Deprecated API scanner not implemented yet.
- Breaking-change analyzer not implemented yet.
- Migration planner not implemented yet.
- Agent mode is currently a skeleton over V1 signals.
- External API failures can reduce completeness/confidence (expected fallback behavior).
