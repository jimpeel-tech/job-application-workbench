"""Provider-neutral job analysis package.

The package keeps analysis contracts, candidate context construction, matching
rules, provider transports, and orchestration in separate modules.  The legacy
``jaw.analyzer`` module remains the public compatibility facade.
"""

from .context import (
    build_analysis_request,
    candidate_context,
    candidate_context_data,
)
from .contracts import AnalysisProvider, AnalysisRequest
from .providers.deterministic import DeterministicAnalysisProvider
from .providers.ollama import OllamaAnalysisProvider
from .providers.openai import OpenAIAnalysisProvider
from .schema import JOB_SCHEMA
from .service import JobAnalyzer

__all__ = [
    "AnalysisProvider",
    "AnalysisRequest",
    "DeterministicAnalysisProvider",
    "JOB_SCHEMA",
    "JobAnalyzer",
    "OpenAIAnalysisProvider",
    "OllamaAnalysisProvider",
    "build_analysis_request",
    "candidate_context",
    "candidate_context_data",
]
