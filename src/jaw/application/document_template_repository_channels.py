"""Channel-aware downloads for the Template Repository.

Release downloads remain immutable tagged snapshots. The development channel pulls
``jaw-templates/dev`` into the same examples directory so Dev users can exercise
repository changes before they are promoted and tagged.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from importlib.resources import files
from pathlib import Path
from typing import Any

from .document_template_repository import (
    _MAX_ARCHIVE_BYTES,
    OFFICIAL_REPOSITORY,
)
from .document_template_repository import (
    TemplateRepository as _BaseTemplateRepository,
)

_INSTALL_METADATA = ".jaw-install.json"
_LOCAL_DEFAULTS_METADATA = ".jaw-local-defaults.json"
_LOCAL_DEFAULTS_VERSION = 1
_QUICK_REFERENCE_ID = "quick-reference"
_DEV_BRANCH = "dev"


class TemplateRepository(_BaseTemplateRepository):
    """Add release/dev channels plus one-time Local template defaults."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._ensure_directories()

    def catalog(self) -> dict[str, Any]:
        value = super().catalog()
        repository = dict(value.get("repository") or {})
        installed_version = str(repository.get("installed_version") or "")
        metadata = self._install_metadata()
        channel = str(metadata.get("channel") or "").strip().casefold()
        reference = str(metadata.get("reference") or "").strip()

        if channel not in {"release", "dev"}:
            channel = "release" if installed_version else ""
        if not reference and channel == "release" and installed_version:
            reference = f"v{installed_version}"
        if not reference and channel == "dev":
            reference = _DEV_BRANCH

        repository["installed_channel"] = channel
        repository["installed_reference"] = reference
        return {**value, "repository": repository}

    def download(
        self,
        version: str | None = None,
        *,
        channel: str = "release",
    ) -> dict[str, Any]:
        channel_key = str(channel or "release").strip().casefold()
        if channel_key == "release":
            result = super().download(version)
            installed_version = str(result.get("version") or "")
            reference = str(result.get("reference") or f"v{installed_version}")
            template_api = int(result.get("template_api") or 0)
            self._write_install_metadata(
                channel="release",
                reference=reference,
                repo_version=installed_version,
                template_api=template_api,
            )
            return {
                **result,
                "channel": "release",
                "catalog": self.catalog(),
            }
        if channel_key == "dev":
            return self._download_dev()
        raise ValueError("Template repository channel must be release or dev")

    def _ensure_directories(self) -> None:
        super()._ensure_directories()
        self._seed_local_defaults()

    def _seed_local_defaults(self) -> None:
        metadata_path = self.root / _LOCAL_DEFAULTS_METADATA
        metadata = self._read_optional_json(metadata_path)
        if int(metadata.get("version") or 0) >= _LOCAL_DEFAULTS_VERSION:
            return

        target = self.local_root / _QUICK_REFERENCE_ID
        if not target.exists():
            source = (
                files("jaw")
                .joinpath("resources")
                .joinpath("documents")
                .joinpath("quick_reference.tex.j2")
                .read_text(encoding="utf-8")
            )
            with tempfile.TemporaryDirectory(
                prefix=".jaw-local-defaults-",
                dir=self.root,
            ) as temporary:
                package = Path(temporary) / _QUICK_REFERENCE_ID
                package.mkdir()
                manifest = {
                    "format_version": 1,
                    "id": _QUICK_REFERENCE_ID,
                    "name": "Quick Reference",
                    "description": (
                        "JAW Documents runtime schema and Jinja/LaTeX quick reference."
                    ),
                    "output_pattern": "{{ user.full_name }} - JAW Quick Reference.pdf",
                    "template": {
                        "name": "Quick Reference",
                        "file": "template.jinja",
                    },
                    "sections": [],
                }
                (package / "template.json").write_text(
                    json.dumps(manifest, indent=2) + "\n",
                    encoding="utf-8",
                )
                (package / "template.jinja").write_text(source, encoding="utf-8")
                self._load_package(package, "local")
                try:
                    package.rename(target)
                except FileExistsError:
                    pass

        self._write_local_defaults_metadata(metadata_path)

    @staticmethod
    def _read_optional_json(path: Path) -> dict[str, Any]:
        if not path.is_file():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return {}
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _write_local_defaults_metadata(path: Path) -> None:
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps({"version": _LOCAL_DEFAULTS_VERSION}, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    def _download_dev(self) -> dict[str, Any]:
        self._ensure_directories()
        url = (
            f"https://codeload.github.com/{OFFICIAL_REPOSITORY}/zip/refs/heads/{_DEV_BRANCH}"
        )
        archive_bytes = self._downloader(url)
        if not archive_bytes:
            raise ValueError("Downloaded template repository archive was empty")
        if len(archive_bytes) > _MAX_ARCHIVE_BYTES:
            raise ValueError("Template repository archive is too large")

        with tempfile.TemporaryDirectory(prefix="jaw-template-repo-dev-") as temporary:
            temporary_root = Path(temporary)
            extracted = temporary_root / "archive"
            extracted.mkdir()
            self._extract_archive(archive_bytes, extracted)
            source_root = self._archive_repository_root(extracted)
            manifest = self._read_json(source_root / "repo.json")
            repo_version = str(manifest.get("repo_version") or "").strip()
            if not repo_version:
                raise ValueError("Development template repository is missing repo_version")
            self._validate_repository(source_root, repo_version)
            template_api = int(manifest.get("template_api") or 1)

            stage = self.root / ".examples-download"
            backup = self.root / ".examples-backup"
            shutil.rmtree(stage, ignore_errors=True)
            shutil.rmtree(backup, ignore_errors=True)
            shutil.copytree(source_root, stage)
            self._validate_repository(stage, repo_version)
            self._write_install_metadata_to(
                stage,
                channel="dev",
                reference=_DEV_BRANCH,
                repo_version=repo_version,
                template_api=template_api,
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
            "channel": "dev",
            "version": repo_version,
            "template_api": template_api,
            "catalog": self.catalog(),
        }

    def _install_metadata(self) -> dict[str, Any]:
        path = self.examples_root / _INSTALL_METADATA
        if not path.is_file():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}
        return dict(value) if isinstance(value, dict) else {}

    def _write_install_metadata(
        self,
        *,
        channel: str,
        reference: str,
        repo_version: str,
        template_api: int = 0,
    ) -> None:
        self._write_install_metadata_to(
            self.examples_root,
            channel=channel,
            reference=reference,
            repo_version=repo_version,
            template_api=template_api,
        )

    @staticmethod
    def _write_install_metadata_to(
        root: Path,
        *,
        channel: str,
        reference: str,
        repo_version: str,
        template_api: int = 0,
    ) -> None:
        root.mkdir(parents=True, exist_ok=True)
        metadata = {
            "channel": channel,
            "reference": reference,
            "repo_version": repo_version,
        }
        if template_api > 0:
            metadata["template_api"] = template_api
        (root / _INSTALL_METADATA).write_text(
            json.dumps(metadata, indent=2) + "\n",
            encoding="utf-8",
        )


__all__ = ["TemplateRepository"]
