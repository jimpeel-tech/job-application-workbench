from __future__ import annotations

import pytest

from jaw.documents.function_runtime import FunctionRuntime, FunctionRuntimeError


class _FailingGenerator:
    def generate_structured(self, request):
        raise RuntimeError("provider unavailable")


class _UnusedGenerator:
    def generate_structured(self, request):
        raise AssertionError("generation should not be called")


def test_generation_provider_failure_is_wrapped_with_block_name() -> None:
    runtime = FunctionRuntime(
        _FailingGenerator(),
        provider="ollama",
        model="qwen3:14b",
    )

    with pytest.raises(
        FunctionRuntimeError,
        match="Generation block 'summary' failed: provider unavailable",
    ):
        runtime.render(
            """<summary>
Write a summary from {{ user }}.
</>
{{ summary }}""",
            {"user": {"full_name": "Example User"}},
        )


def test_undefined_runtime_value_is_wrapped_with_resource_label() -> None:
    runtime = FunctionRuntime(
        _UnusedGenerator(),
        provider="ollama",
        model="qwen3:14b",
    )

    with pytest.raises(
        FunctionRuntimeError,
        match="Could not render Section Experience:.*missing.*undefined",
    ):
        runtime.render(
            "{{ missing }}",
            {},
            label="Section Experience",
        )
