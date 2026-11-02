# ContractAuditVerdict

ContractAuditVerdict dies without GenLayer: no EVM contract can read an audit report and the audited source code together, judge whether the findings cover the real attack surface, and produce a multi-validator consensus quality score - only GenLayer's AI validators can review audit quality during consensus and publish a tamper-proof record DAOs can require before trusting an audit.

## Problem

"Audited" is treated as a safety signal regardless of report quality. A superficial checklist can receive the same public recognition as a detailed review with reproducible findings and verified fixes.

## Solution

A single GenLayer Intelligent Contract reads an audit report and audited source on-chain, scores five report-quality criteria through AI validators, and records the assessment. Contract and auditor names are labels; scores rely on fetched evidence, not firm reputation. This assesses the auditor's work, not whether the audited contract is safe.

## How it works

1. Call `submit_review(contract_name, audit_firm, report_url, source_url)` to receive a sequential string ID starting at `"1"`. Names must contain text and be at most 100 characters; URLs must use HTTP(S) and differ.
2. Anyone can call `assess_audit(review_id)` once while the review is PENDING. Both URLs are fetched inside the nondeterministic execution boundary.
3. Read `get_assessment(review_id)` for the grade, criteria, confidence, reasoning, and coverage gaps. `get_review(review_id)` also exposes the submitter and URLs.
4. Call `lookup_by_report(report_url)` for the latest submission using that exact URL. Earlier submissions remain accessible by ID. Unknown URLs return `{"found": false}`.

The deployer can invalidate PENDING reviews, recording UNASSESSABLE with the reason `Invalidated by admin`. Assessed reviews cannot be overwritten or invalidated. `get_count()` returns a native integer. Other views return JSON strings; `list_reviews(grade_filter)` returns `{"reviews": [...]}` in submission order. Use an empty filter for all reviews, PENDING for pending status, or a grade for assessed results. Unknown filters return an empty list. `missing_coverage` is itself a JSON array string in both review views.

## Five criteria

| Criterion | Measures |
| --- | --- |
| Coverage | Attack surface visible in source: public functions, access control, external calls, token flows, upgrade paths |
| Findings | Specific code references and proof of concept or reproduction steps |
| Severity | Ratings justified by impact and likelihood |
| Remediation | Actionable fixes and fix verification or re-review |
| Methodology | Scope, commit hash, tooling, manual effort, and auditor team disclosure |

Each criterion is scored from 0 to 100.

## Deterministic derivations and grades

The contract computes `overall_score = sum(five criteria) // 5` with integer division. The LLM never decides the grade directly; any supplied grade or overall score is ignored.

| Grade | Overall score |
| --- | --- |
| THOROUGH | 75-100 |
| ADEQUATE | 40-74 |
| SUPERFICIAL | 0-39, with at least one recorded gap |
| UNASSESSABLE | Unreadable report or unusable model response; scores are zero |

The required consistency exception promotes SUPERFICIAL with no gaps to ADEQUATE and floors the overall score at 40. Criterion scores remain unchanged, so the stored overall can differ from their average in that case.

## Consensus design

Validators independently repeat fetching and scoring. They accept a leader only when the grade matches exactly, overall differs by at most 5, and every criterion differs by at most 10. SUPERFICIAL requires at least one missing-coverage area on both sides. Confidence must fall in the same band: 0-34, 35-79, or 80-100. This agrees on the MEANING of the decision, not JSON format: a different headline grade is rejected even when both responses have valid JSON and identical keys. Numeric tolerances allow limited scoring variation within the same decision. Reasoning and gap text need not match word for word; the validator does not establish semantic agreement on individual gap descriptions or the source_readable flag. Direct-mode tests explicitly execute captured validator callbacks; direct execution alone is not a hosted multi-validator deployment test.

## Edge cases

- An unreadable report returns UNASSESSABLE before any LLM call. Source fetching still occurs.
- An unreadable source caps coverage at 50 and adds an explicit unverifiable-coverage gap.
- Missing or unconvertible criteria produce UNASSESSABLE, never guessed scores. Parsing uses the prompt's `int(...)` conversion pattern, including acceptance of numeric strings.
- Out-of-range criteria and confidence are clamped to 0-100. Invalid confidence defaults to zero.
- Raw JSON, dictionary responses, and fenced JSON are supported. Non-list gap values become an empty list; empty entries are discarded.
- Fetch exceptions, malformed JSON, and LLM provider exceptions produce safe results instead of aborting assessment.
- Report/source evidence is limited to 6,000/4,000 characters. The prompt tells reviewers not to penalize truncation itself. URL prefix validation does not guarantee that a page contains the claimed report or source.

## Difference from BountyVerdict

This reviews the quality of an auditor's report. BountyVerdict judges a hacker's vulnerability claim for a payout. ContractAuditVerdict has no payout, escrow, or token transfer logic.

## Use cases

DAOs can use assessments as an audit acceptance gate. Protocol reviewers can compare report quality during due diligence. Historical reviews can inform auditor reputation tracking while retaining the original evidence URLs and submitter labels.

## Deploy in GenLayer Studio (studionet)

1. Open [GenLayer Studio](https://studio.genlayer.com/), the stable Studionet environment.
2. In Contracts, choose New Contract / Add From File and upload `contracts/contract_audit_verdict.py`.
3. Preserve the exact dependency header. The constructor has no arguments. Select the deploying account, fund it using the Studio faucet if needed, and deploy.
4. Wait for finalization and verify successful execution. Record the deployed address, then submit a review and call `assess_audit` in a separate transaction.
5. Inspect `get_assessment` and `lookup_by_report` after the assessment transaction succeeds.

See the official [Studio guide](https://docs.genlayer.com/developers/intelligent-contracts/tools/genlayer-studio), [file loading instructions](https://docs.genlayer.com/developers/intelligent-contracts/tools/genlayer-studio/loading-contract), and [deployment guide](https://docs.genlayer.com/developers/intelligent-contracts/deploying).

## Deployment

```text
CONTRACT_ADDRESS = 0x695f6609d680A5cF1A0a2b283f63aB6176879206
NETWORK          = studionet
```

Verified by read-only RPC on 2026-11-02 at `https://studio.genlayer.com/api`: chain ID `61999` (`0xf22f`), the deployed schema exposes all eight expected methods, `get_count()` returned `0`, and `list_reviews("")` returned `{"reviews": []}`. These are live read results; no assessment transaction was submitted. See [deployment evidence](evidence/deployment.json).

The contract at this address was deployed by the project owner. The local file now uses the requested compact dependency header, line-3 wildcard import, and class name `Contract`; these changes preserve the public methods and assessment behavior. Byte-for-byte equality with deployed code has not been verified. Per the owner's explicit choice, score fields retain the original `u256` schema; only `next_id` uses `bigint`. This is a documented exception to the later bigint-only preference, avoiding an unapproved storage-schema migration.

### Illustrative worked example: executed locally with mocked evidence

This is a real direct-mode execution result with deterministic test mocks, NOT a live Studionet verdict or a claim about an actual audit firm. The URLs are illustrative fixture labels. The mocked report describes scope `Treasury.sol` at commit `abc123`, Slither and Foundry, three weeks of manual review by four auditors, a withdraw reentrancy PoC, and fix re-review. The source mock exposes withdraw and setOwner.

```python
review_id = contract.submit_review(
    "Treasury v2", "ExampleSec",
    "https://github.com/examplesec/audits/blob/main/treasury-v2.md",
    "https://github.com/dao/treasury/blob/main/Treasury.sol",
)
contract.assess_audit(review_id)
assessment = json.loads(contract.get_assessment(review_id))
```

Mocked AI criteria were 90/85/80/75/95, confidence 88, with `upgrade path not discussed` as the gap. The contract computed `(90 + 85 + 80 + 75 + 95) // 5 = 85` and derived THOROUGH. The executed result is in [illustrative-example.json](evidence/illustrative-example.json).

```json
{"review_id":"1","contract_name":"Treasury v2","audit_firm":"ExampleSec","grade":"THOROUGH","overall_score":85,"criteria":{"coverage":90,"findings":85,"severity":80,"remediation":75,"methodology":95},"confidence":88,"reasoning":"Report covers withdraw and setOwner with PoC and discloses scope, commit, tools and team.","missing_coverage":"[\"upgrade path not discussed\"]","gap_count":1,"source_readable":true,"status":"ASSESSED"}
```

## Portal readiness review

- **Meaning-based validator:** independently re-fetches and re-scores evidence, requires exactly the same grade, bounded overall and every criterion, gap existence for SUPERFICIAL, and the same confidence band. It is not a format-only check. Explanation/gap wording is not semantically compared.
- **Structured state:** string-keyed TreeMaps and an allow_storage dataclass define explicit PENDING -> ASSESSED/UNASSESSABLE transitions. Only the deployer can invalidate a PENDING entry. The retained u256 exception is documented above; arrays/dicts used in calculations are transient, not stored containers.
- **Edge cases:** bad labels/URLs, absent IDs, double assessment, pending reads and unauthorized invalidation raise UserError. Unreadable evidence and web/LLM failures deliberately store an UNASSESSABLE result instead of raising; this distinguishes unavailable evidence from invalid transactions.
- **Reusable primitive:** a shared assessment/lookup API can support DAO audit acceptance, protocol due diligence, and auditor reputation histories. No frontend, escrow or payout code is included.

Minimal future behavior changes were identified but not applied to this deployment: enforce exact integer types instead of int coercion; verify leader arithmetic/grade/gap-count consistency (including non-negative gap counts); optionally require agreement on source readability; and harden the model prompt against instructions embedded in fetched pages. These change acceptance or verdict behavior and should be approved and tested before a fresh deployment. Current numeric tolerances can admit a leader with a slightly inconsistent average; raw reasoning and gap descriptions are retained as the leader's explanation, not independently verified claims.

Evidence is truncated, URLs can change, labels are not authenticated, and a THOROUGH report-quality grade is not a contract-safety guarantee. The no-gap promotion to ADEQUATE follows the original requested policy; changing that policy would require approval.

## Run tests

Use Python 3.12 or newer with the genlayer-test direct-mode SDK available:

```sh
python -m pip install -r requirements-dev.txt
gltest tests/
# Or: python -m pytest tests/test_contract_audit_verdict.py -v
```

Tests use `direct_vm`, `direct_deploy`, `direct_alice`, and `direct_bob`, with mocked report/source fetches and model responses. `genlayer-test` automatically registers these fixtures. The fresh 0.29.2 wheel requires dictionary-shaped web mock responses. `tests/conftest.py` defers deletion of the SDK stdin backing file only for Windows sharing-violation error 32, then removes it after VM teardown; unrelated errors still propagate. No installed package edits are required. The clean-venv run on Windows with Python 3.12.10, pytest 9.2.0 and genlayer-test 0.29.2 passed all 54 tests, including explicit captured-validator execution. See [test results](evidence/test-results.md).
