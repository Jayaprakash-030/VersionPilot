# VersionPilot Evaluation Plan

## Purpose

VersionPilot is evaluated as a portfolio-scale AI engineering system, not as an
academic benchmark. The evaluation is designed to support concrete claims about
accuracy, migration usefulness, reproducibility, and failure behavior.

The published baseline results are recorded in `eval/EVAL_REPORT.md`.

## Claims Under Test

1. Deprecated API findings identify affected Python source code and line
   numbers accurately.
2. The LLM can extract structured deprecation rules from controlled release
   notes.
3. Deterministic scoring behaves consistently under controlled evidence.
4. Migration recommendations connect detected issues to useful code changes.
5. External API, repository, and LLM failures do not produce misleading healthy
   reports.

## Evaluation Areas

| Area | Dataset | Primary Metrics |
|---|---:|---|
| Deprecated API scanner | 30 controlled fixtures | Precision, recall, F1, line accuracy |
| Rules extraction | 16 release-note fixtures, 3 runs each | Symbol F1, schema validity, consistency |
| Scoring behavior | 15 invariant checks | Monotonicity, determinism, trust behavior |
| Controlled migrations | 3 representative cases | Detection, location, recommendation, tests |
| Reliability | 10 failure scenarios | Correct fallback, misleading result count |
| Smoke runs | 5 basic, 1 agent | Completion and schema sanity |

## Deprecated API Scanner

Scanner fixtures live under:

```text
eval/fixtures/deprecated_api/
```

Each fixture contains:

- source code
- deprecation rules
- expected findings

A finding is correct when the normalized symbol and source line match the
expected result. The scanner evaluation intentionally separates scanner accuracy
from live LLM rules extraction by using manually verified rules.

Measured outputs:

- true positives
- false positives
- false negatives
- precision
- recall
- F1
- exact line-location accuracy

Known difficult cases should remain visible in the report instead of being
hidden. The current known limitation is wildcard import handling.

## Rules Extraction

Rules extraction fixtures live under:

```text
eval/fixtures/rules_extractor/
```

Each fixture contains:

- `metadata.json`
- `release_notes.txt`
- `expected.json`

The live LLM evaluation runs each fixture multiple times and compares normalized
structured fields rather than exact JSON text.

Measured outputs:

- valid schema rate
- correct empty-result rate
- symbol precision, recall, and F1
- replacement accuracy
- severity accuracy
- run-to-run consistency

`note` wording is not scored by exact text match.

## Scoring Behavior

Scoring has no independent external ground truth saying a repository should
score exactly `73.4`. It is therefore evaluated with behavioral invariants over
controlled evidence.

Checks include:

- negative signals must not improve the score
- healthier evidence should dominate weaker evidence
- repeated runs over the same evidence and config should be deterministic
- critical missing evidence should produce `Unknown`, not verified `Low`
- critic-rejected output should produce `Unverified`

## Controlled Migrations

Controlled migration fixtures live under:

```text
eval/fixtures/migration_cases/
```

Each case contains:

- old source code using a deprecated or removed API
- release notes
- expected findings
- expected migration action
- migrated project code
- post-migration pytest checks

Measured outputs:

- issue detected
- correct file and line
- useful recommendation
- tests pass after applying the expected migration

Current cases:

- Flask removed `flask.escape`
- Requests vendored `urllib3` import path
- NumPy deprecated `np.bool` alias

## Reliability

Reliability tests simulate failure modes that are common in AI-assisted
developer tools:

- rules extractor unavailable
- malformed LLM JSON
- invalid report-LLM output
- critic rejection
- GitHub metadata failure
- dependency parser failure
- dependency freshness failure
- vulnerability scanner failure
- V1 pipeline failure
- repository clone failure

Primary safety requirements:

- incomplete migration analysis must not be reported as successful
- critical missing evidence must not become verified `Low` risk
- invalid LLM output must fall back to deterministic reporting
- failed evidence steps must remain visible

## Smoke Runs

Smoke runs are executed against real public repositories to demonstrate that the
pipeline completes on live inputs. They are not labeled accuracy benchmarks.

Stable assertions:

- the run completes or fails clearly
- output is schema-valid
- data completeness remains in `[0, 1]`
- critical missing evidence is reported as `Unknown`

## Excluded Work

The following are intentionally excluded from the current portfolio baseline:

| Excluded Work | Reason |
|---|---|
| Risk-tier F1 for live repositories | No independent non-circular ground truth |
| ECE or Brier score | Health score is not a calibrated probability |
| Large repository benchmark | High effort with limited portfolio value |
| Exact expected risk tiers for live repos | Live repo and API state changes over time |
| Report fluency scoring | Subjective and difficult to defend |

## Updating The Baseline

When prompts, scoring weights, model configuration, scanner behavior, or
migration logic change:

1. regenerate the affected evaluation artifacts
2. update `eval/EVAL_REPORT.md`
3. update `config/model_registry.json` if the approved baseline changes
4. run `vpilot/bin/python -m pipelines.promote_model`
5. update `MODEL_CARD.md` if metrics or limitations changed
