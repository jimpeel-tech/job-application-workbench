"""Compatibility facade for JAW's modular analysis package.

New code should import focused components from :mod:`jaw.analysis`. Existing
callers can continue importing the original names from this module unchanged.
"""

from .analysis import context as _context
from .analysis import graph_matching as _graph_matching
from .analysis import normalization as _normalization
from .analysis.context import (
    build_analysis_request,
    candidate_context,
    candidate_context_data,
)
from .analysis.contracts import AnalysisProvider, AnalysisRequest
from .analysis.graph_matching import TRANSFER_RELATIONSHIPS
from .analysis.providers.deterministic import DeterministicAnalysisProvider
from .analysis.providers.ollama import (
    OllamaAnalysisProvider,
    build_ollama_request_body,
)
from .analysis.providers.openai import (
    OpenAIAnalysisProvider,
    build_openai_request_body,
)
from .analysis.schema import JOB_SCHEMA
from .analysis.service import JobAnalyzer

_capability_payload = _context.capability_payload
_relationship_payload = _context.relationship_payload
_capability_terms = _graph_matching.capability_terms
_local_capability_score = _graph_matching.local_capability_score
_mentioned_capabilities = _graph_matching.mentioned_capabilities
_term_pattern = _graph_matching.term_pattern
_term_present = _graph_matching.term_present
_transfer_candidates = _graph_matching.transfer_candidates
_dedupe_strings = _normalization.dedupe_strings
_normalize_remote_status = _normalization.normalize_remote_status
_normalize_result = _normalization.normalize_result
_number = _normalization.number

__all__ = [
    "AnalysisProvider",
    "AnalysisRequest",
    "DeterministicAnalysisProvider",
    "JOB_SCHEMA",
    "JobAnalyzer",
    "OllamaAnalysisProvider",
    "OpenAIAnalysisProvider",
    "TRANSFER_RELATIONSHIPS",
    "build_analysis_request",
    "build_openai_request_body",
    "build_ollama_request_body",
    "candidate_context",
    "candidate_context_data",
]
