# VersionPilot Evaluation Plan

## Goal

This is a portfolio-scale evaluation, not an academic benchmark.

The evaluation should provide credible evidence for four claims:

1. The deprecated API scanner accurately locates affected source code.
2. The deterministic health score behaves consistently and safely.
3. VersionPilot produces useful guidance for representative migrations.
4. External API and LLM failures do not produce misleading healthy reports.

The final output is a committed `eval/EVAL_REPORT.md` containing measured
results, example failures, and known limitations.

---

## Scope

| Evaluation | Target Size | Primary Result |
|---|---:|---|
| Deprecated API scanner fixtures | 30-40 cases | Precision, recall, F1, location accuracy |
| Scoring behavior checks | 10-15 cases | Passed invariants |
| Controlled migration cases | 3-5 cases | Detection and recommendation usefulness |
| Reliability scenarios | 8-10 cases | Correct fallback and trust behavior |

This scope is achievable by one person and directly supports the project's
resume claims.

---

## Evaluation 1: Deprecated API Scanner Accuracy

### Purpose

The scanner is VersionPilot's main differentiator. It should detect deprecated
symbols that are actually used in source code while avoiding false positives.

### Dataset

Create 30-40 synthetic Python cases under:

```text
eval/fixtures/deprecated_api/
```

Each case contains:

- Python source
- Dynamic deprecation rules using the scanner's actual schema
- Expected findings containing symbol and line number

Example rule:

```json
{
  "flask": {
    "deprecated_symbols": {
      "flask.escape": {
        "replacement": "markupsafe.escape",
        "severity": "high",
        "note": "Removed from Flask"
      }
    }
  }
}
```

### Cases To Include

- Direct imports
- `from package import symbol`
- Module attribute access
- Nested attribute access
- Multiple deprecated symbols in one file
- Multiple packages in one file
- Valid modern API usage
- Strings and comments containing deprecated names
- Aliased imports
- Syntax-error files
- Duplicate or repeated usage

Some difficult cases may expose current scanner limitations. Those failures
should remain visible in the report rather than being hidden.

### Ground Truth

A finding is correct only when its normalized tuple matches an expected tuple:

```text
(symbol, line)
```

Optionally include the file path when evaluating repository-level scans.

### Metrics

- Precision
- Recall
- F1
- Exact line-location accuracy
- False positives
- False negatives

### Target

Do not define an arbitrary target before the first run. Record the real
baseline, inspect failures, improve the scanner, and publish the final measured
result.

---

## Evaluation 2: Scoring Behavioral Correctness

### Purpose

There is no objective external ground truth stating that a repository should
score exactly `73.4`. The scoring function should therefore be evaluated using
controlled behavioral properties.

Use frozen metric objects and configuration files. Do not use live API calls
for these checks.

### Monotonicity

Adding a negative signal must not improve the score.

Test independently:

- Adding critical/high vulnerabilities
- Increasing outdated dependencies while total dependencies stays fixed
- Increasing commit age
- Increasing open issues while other activity signals stay fixed
- Adding failed collection steps reduces confidence

### Dominance

If state A is at least as healthy as state B on every scoring dimension and
strictly healthier on one or more dimensions, A must score higher than B.

### Determinism

The same frozen evidence and scoring configuration must always produce the same:

- Health score
- Risk level
- Component breakdown
- Data completeness
- Confidence

### Trust And Failure Policies

Verify:

- Critical evidence failures produce `Unknown`, not verified `Low`
- Unresolved critic failures produce `Unverified`
- A valid zero-dependency repository is not automatically treated as a parser
  failure
- Confidence can decrease without incorrectly reducing evidence completeness

### Output

Report the number of passed behavioral checks:

```text
Scoring behavioral checks: 14 / 14 passed
Misleading verified-Low results under failure: 0
```

---

## Evaluation 3: Controlled Migration Cases

### Purpose

This is the most important product-level evaluation.

VersionPilot claims it can connect dependency changes to affected source code
and produce migration guidance. Controlled migration cases test that claim more
directly than repository risk-tier benchmarks.

### Scope

Build 3-5 small repositories or fixture projects containing representative old
API usage.

Suggested cases:

- Flask removed API
- Requests vendored urllib3 import
- NumPy removed alias
- Pydantic v1 to v2 usage
- SQLAlchemy 1.x to 2.x usage

Choose cases supported by the current scanner and migration architecture.
Document unsupported cases honestly.

### Procedure

For each migration:

1. Start with a small project using an old or deprecated API.
2. Include tests demonstrating the project's original behavior.
3. Run VersionPilot.
4. Compare findings with manually recorded expected findings.
5. Review the migration recommendation.
6. Apply the recommendation manually or through a documented patch.
7. Run the project's tests after migration.

### Results Table

| Case | Issue Detected | Correct File/Line | Useful Recommendation | Tests Pass After Fix | Unsupported Claims |
|---|---:|---:|---:|---:|---:|
| Flask removed API | Yes/No | Yes/No | Yes/Partial/No | Yes/No | Count |

### Evaluation Rules

- `Issue Detected` and `Correct File/Line` are objective.
- `Tests Pass After Fix` is objective.
- `Useful Recommendation` is a limited human judgment and must include a short
  written justification.
- Unsupported claims must be counted and shown.

This section should include at least one failure or limitation if one is found.

---

## Evaluation 4: Reliability And Trust Behavior

### Purpose

VersionPilot depends on GitHub, PyPI, OSV, repository cloning, Claude, and
Gemini. A trustworthy system must degrade clearly when those dependencies fail.

### Automated Scenarios

Implement 8-10 mocked end-to-end scenarios:

1. GitHub metadata collection fails
2. Dependency parser fails
3. Dependency freshness lookup fails
4. OSV vulnerability scan fails
5. Repository clone fails
6. Claude fails and Gemini succeeds
7. Claude and Gemini both fail
8. LLM returns invalid or incomplete JSON
9. Critic repeatedly fails
10. Repository has zero verified dependencies

### Required Assertions

- The pipeline still produces a report when graceful fallback is expected.
- Critical missing evidence produces `Unknown`.
- Unresolved critic failure produces `Unverified`.
- No incomplete run is published as verified `Low`.
- Data completeness represents evidence availability.
- Final reports contain all required keys.
- Factual fields cannot be changed by the LLM.

### Metrics

- Scenarios passed / total
- Successful report-generation rate
- Correct fallback rate
- Misleading verified-healthy result count

Primary reliability target:

```text
0 incomplete or critic-rejected runs reported as verified Low risk
```

---

## Optional Operational Measurements

Measure these during a small run across approximately five repositories:

- Average runtime
- Average LLM calls per repository
- Input/output token usage when available
- Approximate cost per repository

These are useful resume numbers, but they are secondary to correctness and
reliability. Do not delay the core evaluation to build complex cost tracking.

---

## What Is Intentionally Excluded

| Excluded Work | Reason |
|---|---|
| ECE and Brier score | VersionPilot does not output a calibrated probability tied to an independently observed outcome |
| Risk-tier precision/recall/F1 | No independent, non-circular risk-tier ground truth exists |
| Spearman ranking benchmark | Ranking derived from scoring inputs mainly tests the configured rules |
| `derive_labels.py` and `ground_truth.csv` | Automatically derived labels are not independent ground truth |
| Large repository benchmark | High effort with limited portfolio value |
| Exact risk-tier assertions for live repos | Repository state and external API results change over time |
| Report fluency scoring | Subjective and difficult to defend |
| Full planner-strategy evaluation | No clear ground truth for the optimal strategy |

---

## Real-Repository Smoke Runs

Run VersionPilot against approximately five real repositories as a demonstration,
not as labeled accuracy evaluation.

Record:

- Run date
- Run status
- Risk level
- Data completeness
- Number of dependencies
- Deprecated findings
- Migration recommendations
- Runtime

Do not assert that a live repository must always be `Low` or `High`. Instead,
assert stable properties:

- The run completes or fails clearly.
- Risk is `Unknown` when critical evidence is unavailable.
- Data completeness is within `[0, 1]`.
- Reports satisfy the required schema.

---

## File Structure

```text
eval/
├── fixtures/
│   ├── deprecated_api/
│   └── migration_cases/
├── metrics.py
├── evaluate_scanner.py
├── evaluate_migrations.py
├── evaluate_reliability.py
├── run_eval.py
└── EVAL_REPORT.md

tests/
├── behavioral/
│   └── test_scoring_behavior.py
└── reliability/
    └── test_failure_scenarios.py
```

Use pytest for pass/fail regression behavior. Use evaluation scripts for metrics
and report generation.

### Deferred Environment Check

The focused evaluation tests pass under the current system Python. The full unit
suite must be rerun later from the project virtual environment after installing
all requirements; collection currently stops because `anthropic` and
`langgraph` are unavailable in the system Python environment.

---

## Build Order

| Step | Deliverable | Estimated Effort |
|---|---|---:|
| 1 | Deprecated API fixtures, metrics, and baseline | 1 day |
| 2 | Scoring behavioral tests | 0.5 day |
| 3 | Reliability scenarios | 1 day |
| 4 | Three controlled migration cases | 1.5-2 days |
| 5 | Real-repository smoke runs and operational measurements | 0.5 day |
| 6 | Publish `EVAL_REPORT.md` | 0.5 day |

Expected total: approximately 4.5-5 days of focused work.

---

## EVAL_REPORT.md Template

```markdown
# VersionPilot Evaluation Report

Evaluation date: YYYY-MM-DD
Version: scoring_v1

## Deprecated API Scanner

| Metric | Result |
|---|---:|
| Cases | ... |
| Precision | ... |
| Recall | ... |
| F1 | ... |
| Exact line-location accuracy | ... |

## Scoring Behavior

- Behavioral checks passed: ... / ...
- Misleading verified-Low results under failure: ...

## Controlled Migrations

| Case | Detected | Correct Location | Recommendation | Tests Pass |
|---|---:|---:|---:|---:|
| ... | ... | ... | ... | ... |

## Reliability

- Scenarios passed: ... / ...
- Successful report generation: ...%
- Correct fallback behavior: ...%
- Misleading verified-healthy reports: ...

## Operational Measurements

- Average runtime: ...
- Average LLM calls: ...
- Approximate cost per repository: ...

## Known Failures And Limitations

- ...
```

---

## Resume-Quality Claims

Only use numbers produced by the committed evaluation report.

Examples:

- Achieved `X%` precision and `Y%` recall for deprecated API detection across
  `N` controlled fixtures.
- Correctly located affected source lines in `X/N` migration cases.
- Validated `X/N` migration recommendations by applying changes and running
  tests.
- Correctly handled `X/N` simulated API and LLM failure scenarios with zero
  incomplete runs reported as verified healthy.
