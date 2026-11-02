# Test results

Run on 2026-11-02 in a newly created project virtual environment.

- Platform: Windows; Python 3.12.10
- pytest: 9.2.0
- genlayer-test: 0.29.2 (fresh wheel)
- Command: `.venv\Scripts\gltest.exe tests/ --tb=short`
- Result: **54 passed in 4.61s**; zero failures, errors, skips or xfails.

All 25 original test groups remain covered. Additional cases execute the captured validator to verify exact grade agreement, overall tolerance, all five criterion tolerances, confidence bands, missing-gap rejection, and leader-error rejection. Missing IDs and a local mocked worked example are also exercised. Web and LLM responses are mocked; this is not a live multi-validator assessment run.

A missing optional gltest.config.yaml warning uses the default localnet configuration. These tests use direct_vm and do not contact a local node. Windows temporary-file sharing behavior is handled in conftest.py; all web mock responses use the supported dictionary structure. No tests were deleted to resolve environment failures.
