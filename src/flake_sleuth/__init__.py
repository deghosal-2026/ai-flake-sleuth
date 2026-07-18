"""ai-flake-sleuth: LangGraph agent that diagnoses flaky CI tests.

Exposes all public data structures so consumers can import from the
package root rather than reaching into submodules.
"""

try:
    from importlib.metadata import version as _v
    __version__ = _v("ai-flake-sleuth")
except Exception:
    __version__ = "0.0.0"

# Re-export every public type so callers can write:
#     from flake_sleuth import RunInfo, TestResult
from flake_sleuth.classifier import Classifier
from flake_sleuth.error_signature import ErrorSignatureNormalizer
from flake_sleuth.llm import LLMAdapter
from flake_sleuth.log_parser import LogParser
from flake_sleuth.types import (
    Classification,
    DataQuality,
    ErrorSignatureGroup,
    FailureCategory,
    FlakeSleuthReport,
    JobInfo,
    ReportSummary,
    RunInfo,
    TestResult,
    TestStats,
    TestStatus,
)

# Explicit __all__ tells static analysers and ``import *`` what is public.
__all__ = [
    "Classification",
    "__version__",
    "Classifier",
    "DataQuality",
    "ErrorSignatureGroup",
    "ErrorSignatureNormalizer",
    "FailureCategory",
    "FlakeSleuthReport",
    "JobInfo",
    "LLMAdapter",
    "LogParser",
    "ReportSummary",
    "RunInfo",
    "TestResult",
    "TestStats",
    "TestStatus",
]
