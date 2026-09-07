"""Execute Workbench Functions as Jinja plus JAW generation blocks.

A Function is read top-to-bottom. ``<name>...</>`` creates a text variable and
``<name:list>...</>`` creates ``list[str]``. The generation block itself emits no
text; normal Jinja after it can use the generated native value.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from jinja2 import StrictUndefined, TemplateError, Undefined, meta, pass_context
from jinja2.sandbox import SandboxedEnvironment

from .latex import latex_raw
from .text_generation import (
    StructuredTextGenerationRequest,
    TextGenerator,
)

_BLOCK_RE = re.compile(
    r"<([A-Za-z_][A-Za-z0-9_]*)(?::(text|list))?>(.*?)</>",
    re.DOTALL,
)
_OPEN_RE = re.compile(r"<([A-Za-z_][A-Za-z0-9_]*)(?::(?:text|list))?>")
_SKIP = object()


class FunctionRuntimeError(ValueError):
    """A Function syntax or generation error safe to show in the Workbench."""


@dataclass(frozen=True)
class FunctionExecutionResult:
    """Rendered Function text plus generation provenance."""

    text: str
    generations: tuple[dict[str, Any], ...] = ()


def compile_function_source(source: str) -> str:
    """Translate JAW generation blocks into ordinary top-down Jinja statements."""

    matches = list(_BLOCK_RE.finditer(source))
    if not matches:
        if _OPEN_RE.search(source) or "</>" in source:
            raise FunctionRuntimeError("Function has an incomplete generation block")
        return source

    masked = list(source)
    parts: list[str] = []
    cursor = 0
    for index, match in enumerate(matches):
        body = match.group(3)
        if _OPEN_RE.search(body):
            raise FunctionRuntimeError("Generation blocks cannot be nested")
        references = _referenced_names(body)
        variable = match.group(1)
        output_type = match.group(2) or "text"
        prompt_variable = f"__jaw_prompt_{index}"
        parts.append(source[cursor : match.start()])
        parts.append(
            f"{{% set {prompt_variable} %}}{body}{{% endset %}}"
            f"{{% set {variable} = jaw_generate("
            f"{json.dumps(variable)}, {json.dumps(output_type)}, "
            f"{prompt_variable}, {json.dumps(references)}) %}}"
        )
        cursor = match.end()
        for position in range(match.start(), match.end()):
            masked[position] = " "
    parts.append(source[cursor:])

    remainder = "".join(masked)
    if _OPEN_RE.search(remainder) or "</>" in remainder:
        raise FunctionRuntimeError("Function has an incomplete generation block")
    return "".join(parts)


def _referenced_names(source: str) -> list[str]:
    environment = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False)
    environment.globals["latex_raw"] = latex_raw
    try:
        parsed = environment.parse(source)
    except TemplateError as error:
        raise FunctionRuntimeError(f"Could not parse generation instructions: {error}") from error
    return sorted(meta.find_undeclared_variables(parsed))


class FunctionRuntime:
    """Render one Function with schema-constrained generation calls."""

    def __init__(
        self,
        generator: TextGenerator,
        *,
        provider: str,
        model: str,
    ) -> None:
        self.generator = generator
        self.provider = provider
        self.model = model

    def render(
        self,
        source: str,
        context: Mapping[str, Any],
        *,
        label: str = "Function",
    ) -> FunctionExecutionResult:
        compiled = compile_function_source(source)
        generations: list[dict[str, Any]] = []
        environment = SandboxedEnvironment(undefined=StrictUndefined, autoescape=False)
        environment.globals["latex_raw"] = latex_raw

        @pass_context
        def jaw_generate(
            jinja_context: Any,
            variable_name: str,
            output_type: str,
            instructions: object,
            references: object,
        ) -> str | list[str]:
            reference_names = [
                str(item)
                for item in references
                if isinstance(item, str)
            ] if isinstance(references, (list, tuple)) else []
            selected: dict[str, Any] = {}
            for name in reference_names:
                value = jinja_context.resolve(name)
                if isinstance(value, Undefined):
                    continue
                structured = _structured_reference(value)
                if structured is _SKIP:
                    continue
                selected[name] = structured
            try:
                result = self.generator.generate_structured(
                    StructuredTextGenerationRequest(
                        variable_name=str(variable_name),
                        instructions=str(instructions).strip(),
                        context=selected,
                        provider=self.provider,
                        model=self.model,
                        output_type=str(output_type),
                    )
                )
            except RuntimeError as error:
                raise FunctionRuntimeError(
                    f"Generation block '{variable_name}' failed: {error}"
                ) from error
            generations.append(
                {
                    "variable": str(variable_name),
                    "output_type": str(output_type),
                    "provider": result.provider,
                    "model": result.model,
                    "context_keys": sorted(selected),
                }
            )
            return result.value

        environment.globals["jaw_generate"] = jaw_generate
        try:
            text = environment.from_string(compiled).render(dict(context))
        except FunctionRuntimeError:
            raise
        except TemplateError as error:
            raise FunctionRuntimeError(f"Could not render {label}: {error}") from error
        return FunctionExecutionResult(text=text, generations=tuple(generations))


def _structured_reference(value: Any) -> Any:
    """Return a JSON-safe structured value for one referenced Jinja root."""
    if callable(value):
        return _SKIP
    return _json_safe(value)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return str(value)


__all__ = [
    "FunctionExecutionResult",
    "FunctionRuntime",
    "FunctionRuntimeError",
    "compile_function_source",
]
