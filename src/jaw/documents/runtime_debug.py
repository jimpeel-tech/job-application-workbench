"""Small renderer-neutral debug helpers for the Documents runtime."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any


class _RuntimeDebug:
    def __init__(
        self,
        *,
        user: Mapping[str, Any],
        job_ref: Mapping[str, Any],
        work_exp: Sequence[Mapping[str, Any]],
        cap: Mapping[str, Any],
        system: Mapping[str, Any],
        csv: Callable[[Any], str],
        latex_raw: Callable[[Any], Any],
    ) -> None:
        self.roots: dict[str, Any] = {
            "user": user,
            "job_ref": job_ref,
            "work_exp": work_exp,
            "cap": cap,
            "system": system,
        }
        self.helpers: dict[str, Callable[..., Any]] = {
            "csv": csv,
            "latex_raw": latex_raw,
        }

    def dump(self, value: Any) -> str:
        """Pretty JSON for runtime values without exposing Python internals."""
        return json.dumps(
            self._json_safe(value),
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )

    def describe(self, value: Any = None) -> str:
        """Describe the supported runtime or one known runtime value."""
        if value is None:
            return self._overview()

        name = self._known_name(value)
        if isinstance(value, Mapping):
            return self._describe_mapping(name or "mapping", value)
        if self._is_sequence(value):
            return self._describe_sequence(name or "sequence", value)
        if callable(value):
            helper_name = name or "function"
            return f"{helper_name}\ntype: function"
        return f"{name or 'value'}\ntype: {self._type_name(value)}"

    def _overview(self) -> str:
        lines = ["JAW runtime", "objects:"]
        for name, value in self.roots.items():
            if isinstance(value, Mapping):
                lines.append(f"  {name}: mapping")
            elif self._is_sequence(value):
                lines.append(
                    f"  {name}: {self._sequence_type(value)} ({len(value)} records)"
                )
            else:
                lines.append(f"  {name}: {self._type_name(value)}")
        lines.extend(
            [
                "helpers:",
                "  csv(items)",
                "  latex_raw(value)",
                "  dump(value): pretty JSON",
                "  describe([value]): runtime schema",
            ]
        )
        return "\n".join(lines)

    def _describe_mapping(self, name: str, value: Mapping[str, Any]) -> str:
        lines = [name, "type: mapping", "fields:"]
        for key in sorted(value, key=lambda item: str(item).casefold()):
            lines.append(f"  {key}: {self._shape(value[key])}")
        return "\n".join(lines)

    def _describe_sequence(self, name: str, value: Sequence[Any]) -> str:
        lines = [name, f"type: {self._sequence_type(value)}", f"records: {len(value)}"]
        sample = next((item for item in value if isinstance(item, Mapping)), None)
        if sample is not None:
            lines.append("fields:")
            for key in sorted(sample, key=lambda item: str(item).casefold()):
                lines.append(f"  {key}: {self._shape(sample[key])}")
        return "\n".join(lines)

    def _known_name(self, value: Any) -> str:
        for name, known in self.roots.items():
            if value is known:
                return name
        for name, known in self.helpers.items():
            if value is known:
                return name
        if value is self.dump:
            return "dump"
        if value is self.describe:
            return "describe"
        return ""

    @classmethod
    def _shape(cls, value: Any) -> str:
        if isinstance(value, Mapping):
            return "mapping"
        if cls._is_sequence(value):
            return cls._sequence_type(value)
        return cls._type_name(value)

    @classmethod
    def _sequence_type(cls, value: Sequence[Any]) -> str:
        if not value:
            return "list"
        if all(isinstance(item, Mapping) for item in value):
            return "list[mapping]"
        types = {cls._type_name(item) for item in value}
        if len(types) == 1:
            return f"list[{next(iter(types))}]"
        return "list[mixed]"

    @staticmethod
    def _is_sequence(value: Any) -> bool:
        return isinstance(value, (list, tuple))

    @staticmethod
    def _type_name(value: Any) -> str:
        if value is None:
            return "null"
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int):
            return "int"
        if isinstance(value, float):
            return "float"
        if isinstance(value, str):
            return "str"
        return type(value).__name__

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): cls._json_safe(item) for key, item in value.items()}
        if cls._is_sequence(value):
            return [cls._json_safe(item) for item in value]
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if callable(value):
            return f"<{getattr(value, '__name__', 'function')}>"
        return str(value)


def build_runtime_debug_helpers(
    *,
    user: Mapping[str, Any],
    job_ref: Mapping[str, Any],
    work_exp: Sequence[Mapping[str, Any]],
    cap: Mapping[str, Any],
    system: Mapping[str, Any],
    csv: Callable[[Any], str],
    latex_raw: Callable[[Any], Any],
) -> tuple[Callable[[Any], str], Callable[[Any], str]]:
    runtime = _RuntimeDebug(
        user=user,
        job_ref=job_ref,
        work_exp=work_exp,
        cap=cap,
        system=system,
        csv=csv,
        latex_raw=latex_raw,
    )
    return runtime.dump, runtime.describe


__all__ = ["build_runtime_debug_helpers"]
