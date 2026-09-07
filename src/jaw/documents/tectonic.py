"""Safe adapter for the self-contained Tectonic TeX engine."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from .contracts import (
    DocumentRenderError,
    DocumentRenderRequest,
    DocumentRenderResult,
    RenderDiagnostic,
)
from .latex import render_latex_template

_SAFE_OUTPUT_NAME = re.compile(r"[^A-Za-z0-9._-]+")
_DEFAULT_SEARCH_PATH = Path(__file__).resolve().parent.parent / "resources" / "fonts"
_FONT_SUFFIXES = {".otf", ".ttc", ".ttf"}


def find_tectonic(configured_path: str | Path | None = None) -> Path | None:
    """Find Tectonic by explicit configuration, ``PATH``, or user install."""

    configured = configured_path or os.environ.get("JAW_TECTONIC_PATH")
    candidates: list[Path] = []
    if configured:
        expanded = os.path.expandvars(str(configured))
        candidate = Path(expanded).expanduser()
        if candidate.is_dir():
            candidate /= "tectonic.exe" if os.name == "nt" else "tectonic"
        candidates.append(candidate)

    from_path = shutil.which("tectonic")
    if from_path:
        candidates.append(Path(from_path))

    executable_name = "tectonic.exe" if os.name == "nt" else "tectonic"
    candidates.append(Path.home() / ".local" / "bin" / executable_name)

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def find_tectonic_search_path(
    configured_path: str | Path | None = None,
) -> Path | None:
    """Find the approved local font directory staged into render sandboxes."""

    configured = configured_path or os.environ.get("JAW_TECTONIC_SEARCH_PATH")
    if configured:
        expanded = os.path.expandvars(str(configured))
        candidate = Path(expanded).expanduser()
        return candidate.resolve() if candidate.is_dir() else None
    return _DEFAULT_SEARCH_PATH.resolve() if _DEFAULT_SEARCH_PATH.is_dir() else None


class TectonicRenderer:
    """Render sandboxed Jinja/LaTeX through Tectonic's untrusted mode."""

    name = "tectonic"

    def __init__(
        self,
        executable: str | Path | None = None,
        *,
        search_path: str | Path | None = None,
        timeout: int = 180,
    ) -> None:
        self._configured_executable = executable
        self._configured_search_path = search_path
        self.timeout = timeout

    @property
    def executable(self) -> Path | None:
        return find_tectonic(self._configured_executable)

    @property
    def search_path(self) -> Path | None:
        return find_tectonic_search_path(self._configured_search_path)

    @property
    def available(self) -> bool:
        return self.executable is not None

    def version(self) -> str:
        executable = self._require_executable()
        completed = self._run_process([str(executable), "--version"], timeout=15)
        if completed.returncode != 0:
            diagnostics = self._diagnostics(completed)
            raise DocumentRenderError(
                "Could not read the Tectonic version",
                diagnostics=diagnostics,
            )
        return (completed.stdout or completed.stderr).strip()

    def render(self, request: DocumentRenderRequest) -> DocumentRenderResult:
        executable = self._require_executable()
        rendered_source = render_latex_template(
            request.template_source,
            request.context,
            autoescape_text=request.autoescape_text,
        )
        output_name = self._output_name(request.output_name)
        started = time.perf_counter()

        with tempfile.TemporaryDirectory(prefix="jaw-document-") as temporary:
            working_directory = Path(temporary)
            source_path = working_directory / f"{output_name}.tex"
            output_directory = working_directory / "output"
            output_directory.mkdir()
            self._stage_local_fonts(working_directory)
            source_path.write_text(rendered_source, encoding="utf-8")

            command = [
                str(executable),
                "--untrusted",
                "--color",
                "never",
                "--outdir",
                str(output_directory),
            ]
            if request.only_cached:
                command.append("--only-cached")
            command.append(str(source_path))

            try:
                completed = self._run_process(
                    command,
                    timeout=self.timeout,
                    cwd=working_directory,
                )
            except subprocess.TimeoutExpired as error:
                diagnostic = RenderDiagnostic(
                    "error",
                    f"Tectonic exceeded the {self.timeout}-second timeout",
                    "tectonic",
                )
                raise DocumentRenderError(
                    diagnostic.message,
                    rendered_source=rendered_source,
                    diagnostics=(diagnostic,),
                ) from error
            except OSError as error:
                diagnostic = RenderDiagnostic("error", str(error), "tectonic")
                raise DocumentRenderError(
                    f"Could not start Tectonic: {error}",
                    rendered_source=rendered_source,
                    diagnostics=(diagnostic,),
                ) from error

            diagnostics = self._diagnostics(completed)
            if completed.returncode != 0:
                raise DocumentRenderError(
                    "Tectonic could not render the document",
                    rendered_source=rendered_source,
                    diagnostics=diagnostics,
                )

            pdf_path = output_directory / f"{output_name}.pdf"
            if not pdf_path.is_file():
                diagnostic = RenderDiagnostic(
                    "error",
                    "Tectonic completed without producing a PDF",
                    "tectonic",
                )
                raise DocumentRenderError(
                    diagnostic.message,
                    rendered_source=rendered_source,
                    diagnostics=(*diagnostics, diagnostic),
                )

            elapsed = round((time.perf_counter() - started) * 1000)
            return DocumentRenderResult(
                pdf_bytes=pdf_path.read_bytes(),
                rendered_source=rendered_source,
                diagnostics=diagnostics,
                renderer=self.name,
                command=tuple(command),
                duration_ms=elapsed,
            )

    def _stage_local_fonts(self, working_directory: Path) -> None:
        search_path = self.search_path
        if search_path is None:
            return
        for source in search_path.iterdir():
            if source.is_file() and source.suffix.lower() in _FONT_SUFFIXES:
                shutil.copy2(source, working_directory / source.name)

    def _require_executable(self) -> Path:
        executable = self.executable
        if executable is None:
            raise DocumentRenderError(
                "Tectonic was not found. Configure its path or install it in "
                "%USERPROFILE%\\.local\\bin."
            )
        return executable

    @staticmethod
    def _output_name(value: str) -> str:
        name = _SAFE_OUTPUT_NAME.sub("-", value.strip()).strip(".-")
        return name or "document"

    @staticmethod
    def _diagnostics(
        completed: subprocess.CompletedProcess[str],
    ) -> tuple[RenderDiagnostic, ...]:
        diagnostics: list[RenderDiagnostic] = []
        for level, source, content in (
            ("info", "tectonic.stdout", completed.stdout),
            (
                "error" if completed.returncode else "warning",
                "tectonic.stderr",
                completed.stderr,
            ),
        ):
            message = (content or "").strip()
            if message:
                diagnostics.append(RenderDiagnostic(level, message, source))
        return tuple(diagnostics)

    @staticmethod
    def _run_process(
        command: list[str],
        *,
        timeout: int,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["TECTONIC_UNTRUSTED_MODE"] = "1"
        creation_flags = 0
        if os.name == "nt" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            creation_flags = subprocess.CREATE_NO_WINDOW
        return subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
            creationflags=creation_flags,
        )