# Manual Validation: OMLX vs GPT-5 Nano REAL_BUG Disagreements

We sampled 1 of the 56 disputed tests and manually inspected the raw CI log to determine ground truth.

## Test: tests/test_tutorial/test_testing/test_tutorial003.py::test_main

### Model verdicts

| Model | Verdict | Evidence |
|---|---|---|
| GPT-5 Nano | **REAL_BUG** | "All 14 executions failed with identical empty error signature, indicating a consistent failure." |
| OMLX | **INFRA** | "The error signature hash corresponds to an empty string, indicating infrastructure issues." |

### Raw log evidence

```
FAILED tests/test_tutorial/test_testing/test_tutorial003.py::test_main
  - Failed: DID NOT WARN. No warnings of type (DeprecationWarning,) were emitted.
```

The same line appears **14 times** across 14 runs — identical error every time.

### Ground truth: REAL_BUG ✅

The test expects a `DeprecationWarning` to be emitted by the code under test. The warning is not being emitted. This is a **deterministic, reproducible failure** — the definition of a REAL_BUG. GPT-5 Nano was correct.

OMLX said INFRA because the error signature hash was empty (the test framework didn't capture the error message in the cross-run context metadata, even though the raw log clearly shows it). This is a **data pipeline issue** — the error message was available in the raw log but wasn't carried through to the classification prompt.

### Implication

If this pattern holds for the remaining 55 disputed tests, then **GPT-5 Nano's 56 REAL_BUG classifications are likely all correct**, and OMLX's FLAKY/INFRA classifications were wrong due to:
1. Missing error messages in the cross-run context (empty error signature)
2. Conservative OMLX bias toward FLAKY default
3. OMLX being a smaller model less able to infer from metadata alone

**Full validation of all 56 samples is needed for a definitive conclusion.**
