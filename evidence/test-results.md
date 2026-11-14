# Current test results - steward fix

Run on 2026-11-14 in the project virtual environment.

- Platform: Windows; Python 3.12.10
- pytest: 9.2.0
- genlayer-test: 0.29.2
- Command: `.venv\Scripts\gltest.exe tests/ --tb=short`
- Result: **94 passed in 7.49s**; zero failures, errors, skips or xfails.
- Source commit: `326456583fc4e0c9640eb8e705b96ef216854d26`

All original test groups remain covered. Forty additional cases cover:

- Forged averages, including deviations inside the old overall tolerance.
- Grade/criterion consistency and exact deterministic integer averages.
- Grade boundaries at 39/40 and 74/75; no-gap floor at zero, 10 and 39.
- Parsed gap lists, exact gap counts, negative counts, non-string/empty entries and malformed JSON.
- Exact integer fields; numeric strings and booleans are rejected.
- All-zero UNASSESSABLE results and rejection of nonzero scores/confidence/gaps.
- Valid independent scoring tolerance (85 versus 80 accepted, 86 rejected).
- Invalid leader payloads are rejected before further web or LLM calls.

The existing test that used to accept an invented overall of 85 for five scores of 80 now correctly expects rejection. Criterion-tolerance fixtures now carry internally consistent averages and JSON gap strings. No tests were removed. These are direct-mode tests with mocked evidence, plus explicit execution of captured validators. Deployment consensus and on-chain source matching are recorded separately in deployment.json.

## Historical baseline

# Test results

Run on 2026-11-02 in a newly created project virtual environment.

- Platform: Windows; Python 3.12.10
- pytest: 9.2.0
- genlayer-test: 0.29.2 (fresh wheel)
- Command: `.venv\Scripts\gltest.exe tests/ --tb=short`
- Result: **54 passed in 4.61s**; zero failures, errors, skips or xfails.

All 25 original test groups remain covered. Additional cases execute the captured validator to verify exact grade agreement, overall tolerance, all five criterion tolerances, confidence bands, missing-gap rejection, and leader-error rejection. Missing IDs and a local mocked worked example are also exercised. Web and LLM responses are mocked; this is not a live multi-validator assessment run.

A missing optional gltest.config.yaml warning uses the default localnet configuration. These tests use direct_vm and do not contact a local node. Windows temporary-file sharing behavior is handled in conftest.py; all web mock responses use the supported dictionary structure. No tests were deleted to resolve environment failures.
