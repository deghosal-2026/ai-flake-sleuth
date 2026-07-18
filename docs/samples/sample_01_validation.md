# Sample 1: tests/test_tutorial/test_testing/test_tutorial003.py::test_main

## Model Verdicts

| Model | Verdict | Evidence |
|---|---|---|
| GPT-5 Nano | **REAL_BUG** | "All 14 executions failed with identical empty error signature, indicating a consistent failure." |
| OMLX | **INFRA** | "The error signature hash 'e3b0c44298fc1c14' corresponds to an empty string, indicating infrastructure issues." |
| **Ground truth** | **REAL_BUG** | ✅ GPT-5 Nano was correct. See raw log below. |

## Raw Log (actual test output)

```
2026-07-17T17:23:47.3032785Z FAILED tests/test_tutorial/test_testing/test_tutorial003.py::test_main - Failed: DID NOT WARN. No warnings of type (<class 'DeprecationWarning'>,) were emitted.
```

## Why GPT-5 Nano was right

The test expects `DeprecationWarning` to be emitted. It wasn't. Every run (14/14) fails identically. This is deterministic — a REAL_BUG.

OMLX said INFRA because the error message was not captured in the cross-run context metadata (the "error signature hash" was empty), even though the raw log clearly shows the error. This is a **data pipeline gap**: the log parser extracts the error message but it wasn't passed correctly to the LLM.
