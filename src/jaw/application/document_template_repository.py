"""Filesystem-backed package repository for the JAW Documents."""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote

from ..documents.workbench_symbols import referenced_occurrences
from ..paths import app_home
from ..persistence.document_workbench import DocumentWorkbenchRepository
from .document_workbench_service import DocumentWorkbenchService
from .template_release_compat import (
    JAW_VERSION,
    SUPPORTED_TEMPLATE_APIS,
    TEMPLATE_PACKAGE_FORMAT_VERSION,
    select_compatible_release,
)

OFFICIAL_REPOSITORY = "jimpeel-tech/jaw-templates"
RELEASE_REGISTRY_BRANCH = "main"
PACKAGE_FORMAT_VERSION = TEMPLATE_PACKAGE_FORMAT_VERSION
_MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
_MAX_EXTRACTED_BYTES = 40 * 1024 * 1024
_MAX_RELEASE_REGISTRY_BYTES = 256 * 1024
_SYMBOL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

Downloader = Callable[[str], bytes]


def template_repository_root() -> Path:
    override = os.environ.get("JAW_TEMPLATE_REPO")
    if override:
        return Path(override).expanduser().resolve()
    return app_home() / "JAWTemplateRepo"


class TemplateRepository:
    """Manage downloaded examples, user-local packages, and Workbench cloning."""

    def __init__(
        self,
        repository: DocumentWorkbenchRepository,
        service: DocumentWorkbenchService,
        *,
        root: Path | None = None,
        downloader: Downloader | None = None,
    ) -> None:
        self.repository = repository
        self.service = service
        self.root = (root or template_repository_root()).expanduser().resolve()
        self.examples_root = self.root / "examples"
        self.local_root = self.root / "local"
        self._downloader = downloader or self._download_bytes
        self._resolved_release: dict[str, Any] | None = None

    def catalog(self) -> dict[str, Any]:
        self._ensure_directories()
        templates = [
            *self._catalog_source(self.examples_root, "example"),
            *self._catalog_source(self.local_root, "local"),
        ]
        templates.sort(key=lambda item: (str(item["source"]), str(item["name"]).casefold()))
        installed_version = ""
        installed_template_api = 0
        repo_manifest = self.examples_root / "repo.json"
        if repo_manifest.is_file():
            try:
                installed = self._read_json(repo_manifest)
                installed_version = str(installed.get("repo_version") or "")
                installed_template_api = int(installed.get("template_api") or 1)
            except (TypeError, ValueError):
                installed_version = ""
                installed_template_api = 0
        available_version = str((self._resolved_release or {}).get("version") or "")
        return {
            "repository": {
                "name": "Template Repository",
                "github": OFFICIAL_REPOSITORY,
                "available_version": available_version,
                "release_resolution": "compatible",
                "installed_version": installed_version,
                "installed_template_api": installed_template_api,
                "format_version": PACKAGE_FORMAT_VERSION,
                "jaw_version": JAW_VERSION,
                "supported_template_apis": sorted(SUPPORTED_TEMPLATE_APIS),
            },
            "root": str(self.root),
            "examples_path": str(self.examples_root),
            "local_path": str(self.local_root),
            "templates": templates,
        }

    def download(self, version: str | None = None) -> dict[str, Any]:
        release = self._resolve_release(version)
        requested = str(release["version"])
        reference = str(release["ref"])
        template_api = int(release["template_api"])

        self._ensure_directories()
        url = (
            f"https://codeload.github.com/{OFFICIAL_REPOSITORY}/zip/refs/tags/"
            f"{quote(reference, safe='')}"
        )
        archive_bytes = self._downloader(url)
        if not archive_bytes:
            raise ValueError("Downloaded template repository archive was empty")
        if len(archive_bytes) > _MAX_ARCHIVE_BYTES:
            raise ValueError("Template repository archive is too large")

        with tempfile.TemporaryDirectory(prefix="jaw-template-repo-") as temporary:
            temporary_root = Path(temporary)
            extracted = temporary_root / "archive"
            extracted.mkdir()
            self._extract_archive(archive_bytes, extracted)
            source_root = self._archive_repository_root(extracted)
            repo_manifest = self._validate_repository(
                source_root,
                requested,
                expected_template_api=template_api,
            )

            stage = self.root / ".examples-download"
            backup = self.root / ".examples-backup"
            shutil.rmtree(stage, ignore_errors=True)
            shutil.rmtree(backup, ignore_errors=True)
            shutil.copytree(source_root, stage)
            self._validate_repository(
                stage,
                requested,
                expected_template_api=template_api,
            )

            moved_existing = False
            try:
                if self.examples_root.exists():
                    self.examples_root.rename(backup)
                    moved_existing = True
                stage.rename(self.examples_root)
                shutil.rmtree(backup, ignore_errors=True)
            except Exception:
                shutil.rmtree(self.examples_root, ignore_errors=True)
                if moved_existing and backup.exists():
                    backup.rename(self.examples_root)
                raise
            finally:
                shutil.rmtree(stage, ignore_errors=True)
                shutil.rmtree(backup, ignore_errors=True)

        return {
            "downloaded": True,
            "version": str(repo_manifest["repo_version"]),
            "reference": reference,
            "template_api": template_api,
            "catalog": self.catalog(),
        }

    def _release_registry_url(self) -> str:
        return (
            f"https://raw.githubusercontent.com/{OFFICIAL_REPOSITORY}/"
            f"{RELEASE_REGISTRY_BRANCH}/releases.json"
        )

    def _release_registry(self) -> dict[str, Any]:
        data = self._downloader(self._release_registry_url())
        if not data:
            raise ValueError("Official template release registry was empty")
        if len(data) > _MAX_RELEASE_REGISTRY_BYTES:
            raise ValueError("Official template release registry is too large")
        try:
            value = json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("Official template release registry is invalid JSON") from error
        if not isinstance(value, dict):
            raise ValueError("Official template release registry must contain a JSON object")
        return value

    def _resolve_release(self, version: str | None = None) -> dict[str, Any]:
        release = select_compatible_release(
            self._release_registry(),
            jaw_version=JAW_VERSION,
            requested_version=version,
            supported_template_apis=SUPPORTED_TEMPLATE_APIS,
            package_format=PACKAGE_FORMAT_VERSION,
        )
        self._resolved_release = dict(release)
        return dict(release)

    def open_local(self) -> dict[str, Any]:
        self._ensure_directories()
        path = self.local_root
        if sys.platform == "win32":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])  # noqa: S603,S607
        else:
            subprocess.Popen(["xdg-open", str(path)])  # noqa: S603,S607
        return {"opened": str(path)}

    def clone(
        self,
        user_id: int,
        *,
        template_id: str,
        source: str,
    ) -> dict[str, Any]:
        source_key = str(source or "").strip().casefold()
        if source_key not in {"example", "local"}:
            raise ValueError("Template source must be example or local")
        requested_id = str(template_id or "").strip()
        if not requested_id:
            raise ValueError("template_id is required")

        entry = next(
            (
                item
                for item in self.catalog()["templates"]
                if item["source"] == source_key and item["id"] == requested_id
            ),
            None,
        )
        if entry is None:
            raise ValueError("Template package was not found")
        if not entry.get("valid", False):
            raise ValueError(str(entry.get("error") or "Template package is invalid"))

        package = self._load_package(Path(str(entry["path"])), source_key)
        document_name = self._unique_document_name(user_id, str(package["name"]))
        created_ids: list[str] = []
        try:
            template_spec = package["template"]
            template = self.repository.create_resource(
                user_id,
                "template",
                name=str(template_spec["name"]),
                symbol="template",
                visibility="private",
                content=str(template_spec["content"]),
                settings=self._resource_settings(package, source_key, "template", template_spec),
            )
            created_ids.append(template["id"])

            document = self.repository.create_document(
                user_id,
                document_name,
                template["id"],
                output_pattern=str(package["output_pattern"]),
            )
            created_ids.append(document["id"])
            self.repository.update_resource(user_id, template["id"], owner_id=document["id"])

            for section_order, section_spec in enumerate(package["sections"]):
                section = self.repository.create_resource(
                    user_id,
                    "section",
                    symbol=str(section_spec["symbol"]),
                    visibility="private",
                    owner_id=document["id"],
                    content=str(section_spec["content"]),
                    settings=self._resource_settings(
                        package, source_key, "section", section_spec
                    ),
                )
                created_ids.append(section["id"])
                self.repository.link(
                    user_id,
                    document["id"],
                    section["id"],
                    edge_kind="section",
                    symbol=str(section_spec["symbol"]),
                    sort_order=section_order,
                )

                for function_order, function_spec in enumerate(section_spec["functions"]):
                    function = self.repository.create_resource(
                        user_id,
                        "function",
                        symbol=str(function_spec["symbol"]),
                        visibility="private",
                        owner_id=section["id"],
                        content=str(function_spec["content"]),
                        settings=self._resource_settings(
                            package, source_key, "function", function_spec
                        ),
                    )
                    created_ids.append(function["id"])
                    self.repository.link(
                        user_id,
                        section["id"],
                        function["id"],
                        edge_kind="function",
                        symbol=str(function_spec["symbol"]),
                        sort_order=function_order,
                    )
        except Exception:
            for resource_id in reversed(created_ids):
                if self.repository.get_resource(user_id, resource_id) is None:
                    continue
                try:
                    self.repository.delete_resource(user_id, resource_id)
                except Exception:
                    pass
            raise

        return {
            "document_id": document["id"],
            "template_id": template["id"],
            "package": {
                "id": package["id"],
                "name": package["name"],
                "source": source_key,
            },
            "state": self.service.state(user_id),
        }

    def _catalog_source(self, root: Path, source: str) -> list[dict[str, Any]]:
        values: list[dict[str, Any]] = []
        if not root.exists():
            return values
        for manifest_path in sorted(root.rglob("template.json")):
            package_root = manifest_path.parent
            try:
                package = self._load_package(package_root, source)
                values.append(
                    {
                        "id": package["id"],
                        "name": package["name"],
                        "description": package["description"],
                        "source": source,
                        "path": str(package_root),
                        "format_version": package["format_version"],
                        "repo_version": package.get("repo_version", ""),
                        "valid": True,
                        "error": "",
                    }
                )
            except ValueError as error:
                values.append(
                    {
                        "id": package_root.name,
                        "name": package_root.name,
                        "description": "",
                        "source": source,
                        "path": str(package_root),
                        "format_version": 0,
                        "repo_version": "",
                        "valid": False,
                        "error": str(error),
                    }
                )
        return values

    def _load_package(self, package_root: Path, source: str) -> dict[str, Any]:
        manifest = self._read_json(package_root / "template.json")
        format_version = int(manifest.get("format_version") or 0)
        if format_version != PACKAGE_FORMAT_VERSION:
            raise ValueError(
                f"Unsupported template package format {format_version}; "
                f"expected {PACKAGE_FORMAT_VERSION}"
            )
        package_id = str(manifest.get("id") or "").strip()
        name = str(manifest.get("name") or "").strip()
        description = str(manifest.get("description") or "").strip()
        if not package_id or not name:
            raise ValueError("Template package requires id and name")

        template_manifest = manifest.get("template")
        if not isinstance(template_manifest, Mapping):
            raise ValueError("Template package requires a template object")
        template = self._load_resource_spec(package_root, template_manifest, "template")
        self.service._validate_language({"kind": "template"}, str(template["content"]))

        section_values: list[dict[str, Any]] = []
        raw_sections = manifest.get("sections") or []
        if not isinstance(raw_sections, list):
            raise ValueError("Template package sections must be a list")
        section_symbols: list[str] = []
        for raw_section in raw_sections:
            if not isinstance(raw_section, Mapping):
                raise ValueError("Each Section package entry must be an object")
            section = self._load_resource_spec(package_root, raw_section, "section")
            section_symbols.append(str(section["symbol"]))
            raw_functions = raw_section.get("functions") or []
            if not isinstance(raw_functions, list):
                raise ValueError("Section functions must be a list")
            functions: list[dict[str, Any]] = []
            function_symbols: list[str] = []
            for raw_function in raw_functions:
                if not isinstance(raw_function, Mapping):
                    raise ValueError("Each Function package entry must be an object")
                function = self._load_resource_spec(package_root, raw_function, "function")
                function_symbols.append(str(function["symbol"]))
                function_refs = [
                    occurrence.symbol
                    for occurrence in referenced_occurrences(str(function["content"]))
                ]
                if function_refs:
                    raise ValueError(
                        f"Function {function['symbol']} contains Workbench child references: "
                        + ", ".join(function_refs)
                    )
                functions.append(function)
            self._require_exact_references(
                str(section["content"]), function_symbols, f"Section {section['symbol']}"
            )
            section["functions"] = functions
            section_values.append(section)

        self._require_exact_references(
            str(template["content"]), section_symbols, f"Template {template['name']}"
        )
        return {
            "format_version": format_version,
            "repo_version": str(manifest.get("repo_version") or ""),
            "id": package_id,
            "name": name,
            "description": description,
            "output_pattern": str(
                manifest.get("output_pattern") or f"{{{{ user.full_name }}}} - {name}.pdf"
            ),
            "source": source,
            "root": str(package_root),
            "template": template,
            "sections": section_values,
        }

    def _load_resource_spec(
        self,
        package_root: Path,
        manifest: Mapping[str, Any],
        kind: str,
    ) -> dict[str, Any]:
        if kind == "template":
            name = str(manifest.get("name") or "Template").strip() or "Template"
            symbol = "template"
            label = f"Template {name}"
        else:
            # Section and Function package identity is symbol-only. A historical
            # name field, if present in a local/dev package, is ignored rather than
            # becoming a second resource label.
            symbol = str(manifest.get("symbol") or "").strip()
            if not _SYMBOL.fullmatch(symbol):
                raise ValueError(f"{kind.title()} requires a valid Jinja identifier symbol")
            name = ""
            label = f"{kind.title()} {symbol}"

        relative = str(manifest.get("file") or "").strip()
        if not relative:
            raise ValueError(f"{label} requires a source file")
        content = self._read_package_text(package_root, relative)
        settings = manifest.get("settings") or {}
        if not isinstance(settings, Mapping):
            raise ValueError(f"{label} settings must be an object")
        result = {
            "symbol": symbol,
            "file": relative,
            "content": content,
            "settings": dict(settings),
        }
        if kind == "template":
            result["name"] = name
        return result

    @staticmethod
    def _require_exact_references(content: str, expected: list[str], label: str) -> None:
        actual = [occurrence.symbol for occurrence in referenced_occurrences(content)]
        if actual != expected:
            raise ValueError(
                f"{label} Workbench references do not match its package children "
                f"(source: {', '.join(actual) or 'none'}; package: {', '.join(expected) or 'none'})"
            )

    def _resource_settings(
        self,
        package: Mapping[str, Any],
        source: str,
        kind: str,
        spec: Mapping[str, Any],
    ) -> dict[str, Any]:
        settings = dict(spec.get("settings") or {})
        if kind == "template":
            settings.setdefault("renderer", "tectonic")
            settings.setdefault("format", "latex_jinja")
        if kind == "section":
            settings.setdefault("content_shape", "paragraphs")
        settings["repository_package"] = {
            "source": source,
            "id": str(package["id"]),
            "repo_version": str(package.get("repo_version") or ""),
            "format_version": int(package["format_version"]),
        }
        return settings

    def _unique_document_name(self, user_id: int, requested: str) -> str:
        base = requested.strip() or "Document"
        used = {
            str(item.get("name") or "").casefold()
            for item in self.repository.list_documents(user_id)
        }
        if base.casefold() not in used:
            return base
        index = 2
        while f"{base} {index}".casefold() in used:
            index += 1
        return f"{base} {index}"

    def _validate_repository(
        self,
        root: Path,
        expected_version: str,
        *,
        expected_template_api: int | None = None,
    ) -> dict[str, Any]:
        manifest = self._read_json(root / "repo.json")
        if int(manifest.get("format_version") or 0) != PACKAGE_FORMAT_VERSION:
            raise ValueError("Official template repository format is not supported")
        template_api = int(manifest.get("template_api") or 1)
        if template_api not in SUPPORTED_TEMPLATE_APIS:
            raise ValueError(f"Template API {template_api} is not supported by this JAW release")
        if expected_template_api is not None and template_api != expected_template_api:
            raise ValueError("Downloaded template repository API did not match release registry")
        if str(manifest.get("repo_version") or "") != expected_version:
            raise ValueError("Downloaded template repository version did not match request")

        minimum_jaw_version = str(manifest.get("minimum_jaw_version") or "").strip()
        if minimum_jaw_version:
            from .template_release_compat import version_tuple

            if version_tuple(JAW_VERSION) < version_tuple(minimum_jaw_version):
                raise ValueError(
                    f"Template repository requires JAW {minimum_jaw_version} or newer"
                )

        templates = manifest.get("templates") or []
        if not isinstance(templates, list) or not templates:
            raise ValueError("Official template repository does not contain templates")
        for item in templates:
            if not isinstance(item, Mapping):
                raise ValueError("Invalid official template repository index")
            relative = str(item.get("path") or "").strip()
            if not relative:
                raise ValueError("Official template index entry is missing path")
            package_root = self._safe_child(root, relative)
            package = self._load_package(package_root, "example")
            package_version = str(package.get("repo_version") or "")
            if package_version and package_version != expected_version:
                raise ValueError(
                    f"Template package {package['id']} repo_version does not match repository"
                )
        return manifest

    def _archive_repository_root(self, extracted: Path) -> Path:
        candidates = [path.parent for path in extracted.rglob("repo.json")]
        if len(candidates) != 1:
            raise ValueError("Downloaded archive must contain exactly one repo.json")
        return candidates[0]

    @staticmethod
    def _extract_archive(data: bytes, destination: Path) -> None:
        try:
            archive = zipfile.ZipFile(io.BytesIO(data))
        except zipfile.BadZipFile as error:
            raise ValueError("Downloaded template repository was not a valid ZIP archive") from error
        total = 0
        destination_resolved = destination.resolve()
        with archive:
            for member in archive.infolist():
                total += int(member.file_size)
                if total > _MAX_EXTRACTED_BYTES:
                    raise ValueError("Template repository expands beyond the allowed size")
                target = (destination / member.filename).resolve()
                try:
                    target.relative_to(destination_resolved)
                except ValueError as error:
                    raise ValueError("Template repository archive contains an unsafe path") from error
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)

    @staticmethod
    def _download_bytes(url: str) -> bytes:
        request = urllib.request.Request(url, headers={"User-Agent": f"JAW/{JAW_VERSION}"})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
                data = response.read(_MAX_ARCHIVE_BYTES + 1)
        except OSError as error:
            raise ValueError(f"Could not download official JAW templates: {error}") from error
        if len(data) > _MAX_ARCHIVE_BYTES:
            raise ValueError("Template repository download is too large")
        return data

    def _ensure_directories(self) -> None:
        self.examples_root.mkdir(parents=True, exist_ok=True)
        self.local_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _read_json(path: Path) -> dict[str, Any]:
        if not path.is_file():
            raise ValueError(f"Missing {path.name}")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"Invalid JSON in {path.name}: {error}") from error
        if not isinstance(value, dict):
            raise ValueError(f"{path.name} must contain a JSON object")
        return value

    def _read_package_text(self, root: Path, relative: str) -> str:
        path = self._safe_child(root, relative)
        if not path.is_file():
            raise ValueError(f"Missing package source file: {relative}")
        try:
            return path.read_text(encoding="utf-8")
        except OSError as error:
            raise ValueError(f"Could not read package source file: {relative}") from error

    @staticmethod
    def _safe_child(root: Path, relative: str) -> Path:
        root_resolved = root.resolve()
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root_resolved)
        except ValueError as error:
            raise ValueError(f"Package path escapes its template directory: {relative}") from error
        return candidate


__all__ = [
    "TemplateRepository",
    "JAW_VERSION",
    "OFFICIAL_REPOSITORY",
    "PACKAGE_FORMAT_VERSION",
    "RELEASE_REGISTRY_BRANCH",
    "SUPPORTED_TEMPLATE_APIS",
    "template_repository_root",
]
