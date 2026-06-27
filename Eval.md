# VersionPilot Evaluation Plan

## Goal

This is a portfolio-scale evaluation, not an academic benchmark.

The evaluation should provide credible evidence for five claims:

1. The deprecated API scanner accurately locates affected source code.
2. The LLM extracts accurate deprecation rules from release notes.
3. The deterministic health score behaves consistently and safely.
4. VersionPilot produces useful guidance for representative migrations.
5. External API and LLM failures do not produce misleading healthy reports.

The final output is a committed `eval/EVAL_REPORT.md` containing measured
results, example failures, and known limitations.

---

## Scope

| Evaluation | Target Size | Primary Result |
|---|---:|---|
| Deprecated API scanner fixtures | 30-40 cases | Precision, recall, F1, location accuracy |
| Rules extraction fixtures | 15-20 cases | Symbol F1, replacement/severity accuracy, valid response rate |
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
Scoring behavioral checks: 15 / 15 passed
Misleading verified-Low results under failure: 0
```

---

## Evaluation 3: Rules Extraction Quality

### Purpose

The scanner and migration planner depend on the deprecation rules produced by
`RulesExtractor`. This evaluation measures whether the configured LLM converts
release notes into accurate, usable structured rules.

Keep this evaluation separate from scanner accuracy. Scanner fixtures use
manually verified rules so scanner failures are not confused with extraction
failures.

### Dataset

Create 15-20 controlled release-note cases under:

```text
eval/fixtures/rules_extractor/
```

Each case contains:

```text
metadata.json       package name and optional case metadata
release_notes.txt   controlled release-note input
expected.json       manually verified expected rules
```

Example `metadata.json`:

```json
{
  "package": "flask"
}
```

Example `expected.json`:

```json
[
  {
    "symbol": "flask.escape",
    "replacement": "markupsafe.escape",
    "severity": "high"
  }
]
```

### Cases To Include

- Single deprecated symbol
- Removed symbol
- Multiple deprecated or removed symbols
- Explicit replacement
- No replacement provided
- Import-path migration
- Function and class deprecations
- No deprecations
- Breaking change that is not an API deprecation
- Historical deprecation mentioned without a new deprecation
- Ambiguous wording
- Long or noisy release notes

### Metrics

- Symbol precision, recall, and F1
- Replacement accuracy for correctly detected symbols
- Severity accuracy for correctly detected symbols
- Valid JSON and schema rate
- Correct empty-result rate
- Run-to-run consistency

Do not score `note` wording by exact text match. Notes may be useful while using
different wording.

### Evaluation Layers

#### Deterministic Contract Evaluation

Use mocked LLM responses to verify:

- Valid JSON parsing and schema conversion
- Invalid JSON handling
- Non-list response handling
- Missing-field handling
- Empty-result handling
- LLM-unavailable behavior

These checks validate implementation reliability, not live extraction quality.

#### Live LLM Quality Evaluation

Run the configured live LLM against every fixture multiple times:

```bash
vpilot/bin/python -m eval.evaluate_rules_extractor \
  --runs-per-fixture 3 \
  --output eval/rules_extractor_report.json
```

Live evaluation requires configured credentials and must record the model,
evaluation date, run count, and any unavailable or failed calls. Compare
normalized structured fields rather than exact JSON text.

### Known Release-Note Coverage Limitation

The current production fetcher usually passes the complete latest GitHub release
body to `RulesExtractor`, with a PyPI description or summary as fallback. It
does not fetch the full release-note history between the dependency version
pinned by the analyzed repository and the latest available version.

This can miss deprecations announced or removals completed in intermediate
releases. Fetching only the pinned version's notes would also be insufficient,
because those notes do not describe later changes.

The future production flow should:

1. Parse the repository's pinned or minimum dependency version.
2. Determine the latest available version.
3. Fetch changelog or release-note entries across that version range.
4. Combine the entries in version order.
5. Extract rules relevant to the complete upgrade path.

The initial live rules-extraction evaluation measures the current latest-release
behavior. Version-range release-note collection should be evaluated separately
after it is implemented.

### Post-Evaluation Feature: Compatible Upgrade-Path Planning

After completing the current evaluation plan, VersionPilot should determine a
compatible target version set before analyzing release notes and recommending
migrations. The latest available version of one dependency may conflict with
constraints imposed by other direct or transitive dependencies.

VersionPilot should use an existing package resolver, such as `pip --dry-run`
with a structured report or `uv`, rather than implementing dependency resolution
itself. VersionPilot's responsibility would be to orchestrate and interpret the
resolver output:

1. Parse the repository's current dependency constraints and Python version.
2. Propose candidate target versions.
3. Ask the resolver whether the proposed version set is installable.
4. Identify conflicts and required coordinated dependency upgrades.
5. Fetch release notes across each validated upgrade range.
6. Connect those changes to affected source code and migration guidance.
7. Report whether the migration is compatible, blocked, or requires coordinated
   upgrades.

This feature requires its own controlled evaluation cases for compatible
upgrades, resolvable coordinated upgrades, and unsatisfiable dependency
conflicts. It is intentionally deferred until the current scanner, scoring,
rules-extraction, reliability, and migration evaluations are complete.

### Output

Report deterministic contract results separately from live quality results:

```text
Rules extraction contract checks: X / X passed
Live valid-response rate: ...%
Live symbol precision / recall / F1: ... / ... / ...
Replacement accuracy: ...%
Severity accuracy: ...%
```

---

## Evaluation 4: Controlled Migration Cases

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

## Evaluation 5: Reliability And Trust Behavior

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
│   ├── rules_extractor/
│   └── migration_cases/
├── metrics.py
├── evaluate_scanner.py
├── evaluate_scoring.py
├── evaluate_rules_extractor.py
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

### Test Environment

Run the full suite from the project virtual environment because the system
Python does not include all project dependencies. The current full unit suite
passes with `vpilot/bin/python -m pytest tests/unit`.

---

## Build Order

| Step | Deliverable | Estimated Effort |
|---|---|---:|
| 1 | Deprecated API fixtures, metrics, and baseline | 1 day |
| 2 | Scoring behavioral tests | 0.5 day |
| 3 | Rules extraction fixtures, contract checks, and live baseline | 1-1.5 days |
| 4 | Reliability scenarios | 1 day |
| 5 | Three controlled migration cases | 1.5-2 days |
| 6 | Real-repository smoke runs and operational measurements | 0.5 day |
| 7 | Publish `EVAL_REPORT.md` | 0.5 day |

Expected total: approximately 5.5-6.5 days of focused work.

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

## Rules Extraction

| Metric | Result |
|---|---:|
| Contract checks passed | ... / ... |
| Live valid-response rate | ... |
| Symbol precision | ... |
| Symbol recall | ... |
| Symbol F1 | ... |
| Replacement accuracy | ... |
| Severity accuracy | ... |

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
- Achieved `X%` symbol F1 and `Y%` replacement accuracy for live deprecation-rule
  extraction across `N` controlled release-note fixtures.
- Correctly located affected source lines in `X/N` migration cases.
- Validated `X/N` migration recommendations by applying changes and running
  tests.
- Correctly handled `X/N` simulated API and LLM failure scenarios with zero
  incomplete runs reported as verified healthy.
