"""Document rendering contracts and adapters."""

from .context import ExampleContextProvider, GenerationContext, JobContextProvider
from .contracts import (
    DocumentRenderer,
    DocumentRenderError,
    DocumentRenderRequest,
    DocumentRenderResult,
    RenderDiagnostic,
)
from .expression_context import (
    ExpressionContextError,
    build_expression_catalog,
    build_expression_reference,
    referenced_context,
    slugify_reference,
)
from .function_runtime import (
    FunctionExecutionResult,
    FunctionRuntime,
    FunctionRuntimeError,
    compile_function_source,
)
from .latex import escape_latex, latex_environment, latex_raw, render_latex_template
from .tectonic import TectonicRenderer, find_tectonic
from .text_generation import (
    DEFAULT_OLLAMA_MODEL,
    ProviderTextGenerator,
    StructuredTextGenerationRequest,
    StructuredTextGenerationResult,
    TextGenerationRequest,
    TextGenerationResult,
    TextGenerator,
)

__all__ = [
    "DEFAULT_OLLAMA_MODEL",
    "DocumentRenderError",
    "DocumentRenderer",
    "DocumentRenderRequest",
    "DocumentRenderResult",
    "ExampleContextProvider",
    "ExpressionContextError",
    "FunctionExecutionResult",
    "FunctionRuntime",
    "FunctionRuntimeError",
    "GenerationContext",
    "JobContextProvider",
    "ProviderTextGenerator",
    "RenderDiagnostic",
    "StructuredTextGenerationRequest",
    "StructuredTextGenerationResult",
    "TectonicRenderer",
    "TextGenerationRequest",
    "TextGenerationResult",
    "TextGenerator",
    "build_expression_catalog",
    "build_expression_reference",
    "compile_function_source",
    "escape_latex",
    "find_tectonic",
    "latex_environment",
    "latex_raw",
    "referenced_context",
    "render_latex_template",
    "slugify_reference",
]
