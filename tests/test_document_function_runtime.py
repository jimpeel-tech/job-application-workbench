from __future__ import annotations

from jaw.documents.function_runtime import (
    FunctionRuntime,
    FunctionRuntimeError,
    compile_function_source,
)
from jaw.documents.text_generation import StructuredTextGenerationResult


class _Generator:
    def __init__(self) -> None:
        self.requests = []

    def generate_structured(self, request):
        self.requests.append(request)
        if request.output_type == "list":
            value = ["Built platform", "Reduced toil"]
        else:
            value = "Generated summary"
        return StructuredTextGenerationResult(
            value=value,
            provider=request.provider,
            model=request.model,
        )


def test_function_executes_generation_blocks_top_down_with_native_list() -> None:
    generator = _Generator()
    runtime = FunctionRuntime(generator, provider="ollama", model="qwen3:14b")
    source = """{% set jobs = work_exp %}
<bullets:list>
Generate 2 concise bullets from:
{{ jobs }}
</>
{% for bullet in bullets %}
- {{ bullet }}
{% endfor %}
"""

    result = runtime.render(
        source,
        {
            "work_exp": [
                {"company": "Example", "title": "Engineer"}
            ]
        },
    )

    assert result.text.strip() == "- Built platform\n\n- Reduced toil"
    assert len(generator.requests) == 1
    request = generator.requests[0]
    assert request.variable_name == "bullets"
    assert request.output_type == "list"
    assert request.context == {
        "jobs": [{"company": "Example", "title": "Engineer"}]
    }
    assert result.generations[0]["context_keys"] == ["jobs"]


def test_function_text_generation_is_default_and_receives_structured_root() -> None:
    generator = _Generator()
    runtime = FunctionRuntime(generator, provider="openai", model="example-model")

    result = runtime.render(
        """<summary>
Write a short summary for {{ user.first_name }}.
</>
{{ summary }}""",
        {"user": {"first_name": "Jane", "last_name": "Engineer"}},
    )

    assert result.text.strip() == "Generated summary"
    request = generator.requests[0]
    assert request.output_type == "text"
    assert request.context == {
        "user": {"first_name": "Jane", "last_name": "Engineer"}
    }


def test_direct_work_exp_reference_is_structured_data() -> None:
    generator = _Generator()
    runtime = FunctionRuntime(generator, provider="ollama", model="qwen3:14b")

    runtime.render(
        """<bullets:list>
Use {{ work_exp }}.
</>
{% for bullet in bullets %}{{ bullet }}\n{% endfor %}""",
        {"work_exp": [{"company": "Oracle"}]},
    )

    assert generator.requests[0].context == {
        "work_exp": [{"company": "Oracle"}]
    }


def test_generation_blocks_reject_nesting_and_incomplete_tags() -> None:
    try:
        compile_function_source("<outer><inner>nope</></>")
    except FunctionRuntimeError as error:
        assert "cannot be nested" in str(error)
    else:
        raise AssertionError("nested generation block should fail")

    try:
        compile_function_source("<summary>unfinished")
    except FunctionRuntimeError as error:
        assert "incomplete" in str(error)
    else:
        raise AssertionError("incomplete generation block should fail")
