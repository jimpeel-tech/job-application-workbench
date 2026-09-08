from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .application.capability_service import SYSTEM_SET_ALL_ID, CapabilityService
from .application.document_workbench_application import DocumentWorkbenchApplication
from .config import (
    BUILTIN_ACTION_LABELS,
    BUILTIN_PROFILE_FIELDS,
    DEFAULT_MATRIX_BASE,
    DEFAULT_MATRIX_LAYER2,
    DEFAULT_MATRIX_LAYER3,
)
from .database import JobDatabase
from .icons import ICON_LABELS, ICON_SVGS
from .integrations.outlook import OutlookSyncService
from .integrations.outlook.web import OutlookWebController
from .keyboard_layouts import (
    BUILTIN_KEYBOARD_LAYOUT_LABELS,
    BUILTIN_KEYBOARD_LAYOUTS,
    DEFAULT_KEYBOARD_LAYOUT,
)
from .userdata import UserDataStore, empty_keybinds
from .web.assets import (
    DASHBOARD_PAGE,
    JOB_ANALYSIS_HELP_PAGE,
    send_asset,
    static_asset_for,
)
from .web.security import LocalRequestGuardMixin, require_loopback_bind


class DashboardServer:
    def __init__(
        self,
        database: JobDatabase,
        host: str = "127.0.0.1",
        port: int = 8765,
        user_data_path: Path | None = None,
    ):
        require_loopback_bind(host)
        self.database = database
        self.host = host
        self.port = port
        self.user_data = UserDataStore(user_data_path or database.path)
        self.httpd: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> None:
        database = self.database
        user_data = self.user_data
        capabilities = CapabilityService(user_data)
        workbench = DocumentWorkbenchApplication(database, user_data)
        outlook = OutlookWebController(OutlookSyncService(database))

        class Handler(LocalRequestGuardMixin, BaseHTTPRequestHandler):
            def write_body(self, body: bytes) -> None:
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
                    pass

            def send_json(self, value, status=200):
                body = json.dumps(value, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.write_body(body)

            def send_download(self, value, filename):
                body = json.dumps(value, ensure_ascii=False, indent=2).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.write_body(body)

            def active_user_id(self) -> int:
                return int(user_data.read()["active_user_id"])

            def do_GET(self):
                parsed = urlparse(self.path)
                static_asset = static_asset_for(parsed.path)
                if static_asset is not None:
                    send_asset(self, static_asset)
                    return
                if parsed.path == "/":
                    send_asset(self, DASHBOARD_PAGE)
                    return
                if parsed.path == "/help/job-description-analysis":
                    send_asset(self, JOB_ANALYSIS_HELP_PAGE)
                    return
                outlook_response = outlook.get(parsed.path, self.active_user_id())
                if outlook_response is not None:
                    value, status = outlook_response
                    self.send_json(value, status)
                    return
                if parsed.path == "/api/jobs":
                    query = parse_qs(parsed.query)
                    self.send_json(
                        database.list_jobs(
                            search=query.get("q", [""])[0],
                            sort=query.get("sort", ["created_at"])[0],
                            order=query.get("order", ["desc"])[0],
                            status=query.get("status", [""])[0],
                            remote=query.get("remote", [""])[0],
                            user_id=self.active_user_id(),
                        )
                    )
                    return
                if parsed.path == "/api/capabilities":
                    self.send_json(capabilities.state())
                    return
                if parsed.path == "/api/capabilities/schema":
                    self.send_json(capabilities.schema)
                    return
                if parsed.path == "/api/user-data":
                    self.send_json(user_data.read())
                    return
                if parsed.path == "/api/workbench/state":
                    self.send_json({"workbench": workbench.state(self.active_user_id())})
                    return
                if parsed.path == "/api/workbench/repository":
                    self.send_json(workbench.repository_catalog())
                    return
                if parsed.path == "/api/workbench/routing":
                    self.send_json(workbench.routing(self.active_user_id()))
                    return
                if parsed.path == "/api/keybinds":
                    stored = user_data.read().get("keybinds", {})
                    configured = bool(stored.get("configured"))
                    base = stored.get("base", {}) if configured else DEFAULT_MATRIX_BASE
                    layer2 = stored.get("layer2", {}) if configured else DEFAULT_MATRIX_LAYER2
                    layer3 = stored.get("layer3", {}) if configured else DEFAULT_MATRIX_LAYER3
                    labels = dict(BUILTIN_ACTION_LABELS)
                    for binding in [*base.values(), *layer2.values(), *layer3.values()]:
                        action, separator, label = str(binding).partition("|")
                        if separator and label.strip():
                            labels.setdefault(action.strip(), label.strip())
                    for field in BUILTIN_PROFILE_FIELDS:
                        if field.get("id") and field.get("label"):
                            labels.setdefault(str(field["id"]), str(field["label"]))
                    active_data = user_data.read()
                    for action in active_data.get("custom_actions", []):
                        if action.get("id") and action.get("label"):
                            labels[str(action["id"])] = str(action["label"])
                    single_action_ids = {
                        str(field["id"]) for field in BUILTIN_PROFILE_FIELDS if field.get("id")
                    }
                    single_action_ids.update(
                        str(action["id"])
                        for action in active_data.get("custom_actions", [])
                        if action.get("id") and action.get("type", "single") == "single"
                    )
                    labels.setdefault("full_name", "Full Name")
                    labels.setdefault("layer2", "Layer 2")
                    self.send_json(
                        {
                            "binding_model": stored.get(
                                "binding_model", "physical-v1"
                            ),
                            "base": {
                                str(key).upper(): str(value).partition("|")[0]
                                for key, value in base.items()
                            },
                            "layer2": {
                                str(key).upper(): str(value).partition("|")[0]
                                for key, value in layer2.items()
                            },
                            "layer3": {
                                str(key).upper(): str(value).partition("|")[0]
                                for key, value in layer3.items()
                            },
                            "hotkey_settings": stored.get(
                                "hotkey_settings", empty_keybinds()["hotkey_settings"]
                            ),
                            "action_labels": labels,
                            "custom_action_ids": [
                                str(action["id"])
                                for action in active_data.get("custom_actions", [])
                                if action.get("id")
                            ],
                            "single_action_ids": sorted(single_action_ids),
                            "action_displays": stored.get("action_displays", {}),
                            "icon_library": {
                                name: {"label": ICON_LABELS[name], "svg": svg}
                                for name, svg in ICON_SVGS.items()
                            },
                            "builtin_layouts": {
                                name: [list(row) for row in rows]
                                for name, rows in BUILTIN_KEYBOARD_LAYOUTS.items()
                            },
                            "builtin_layout_labels": dict(
                                BUILTIN_KEYBOARD_LAYOUT_LABELS
                            ),
                            "default_layout": DEFAULT_KEYBOARD_LAYOUT,
                            "keyboard_layout": active_data.get(
                                "keyboard_layout", DEFAULT_KEYBOARD_LAYOUT
                            ),
                            "custom_layouts": stored.get("custom_layouts", {}),
                        }
                    )
                    return
                if parsed.path == "/api/user-data/export":
                    exported = user_data.export_data()
                    exported["version"] = 6
                    self.send_download(exported, "jaw-user-data.json")
                    return
                if parsed.path == "/api/user-data/template":
                    template = user_data.template_data()
                    template["version"] = 6
                    self.send_download(template, "jaw-user-data-template.json")
                    return
                if parsed.path.startswith("/api/jobs/"):
                    try:
                        job_id = int(parsed.path.rsplit("/", 1)[1])
                    except ValueError:
                        self.send_json({"error": "Invalid job ID"}, 400)
                        return
                    job = database.get_job(job_id, self.active_user_id())
                    self.send_json(job or {"error": "Not found"}, 200 if job else 404)
                    return
                self.send_error(404)

            def do_POST(self):
                parsed = urlparse(self.path)
                parts = parsed.path.strip("/").split("/")
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    payload = json.loads(self.rfile.read(length) or b"{}")
                except (ValueError, json.JSONDecodeError):
                    self.send_json({"error": "Invalid request"}, 400)
                    return
                try:
                    active_user_id = self.active_user_id()
                    outlook_response = outlook.post(parsed.path, dict(payload), active_user_id)
                    if outlook_response is not None:
                        value, status = outlook_response
                        self.send_json(value, status)
                        return
                    if parsed.path == "/api/workbench/documents/create":
                        result = workbench.create_document(active_user_id, dict(payload))
                        self.send_json(
                            {"document": result, "workbench": workbench.state(active_user_id)}
                        )
                        return
                    if parsed.path == "/api/workbench/repository/download":
                        self.send_json(workbench.repository_download(dict(payload)))
                        return
                    if parsed.path == "/api/workbench/repository/open-local":
                        self.send_json(workbench.repository_open_local())
                        return
                    if parsed.path == "/api/workbench/repository/clone":
                        self.send_json(workbench.repository_clone(active_user_id, dict(payload)))
                        return
                    if parsed.path == "/api/workbench/checkpoint":
                        self.send_json(workbench.checkpoint(active_user_id, dict(payload)))
                        return
                    if parsed.path == "/api/workbench/save":
                        self.send_json(workbench.save(active_user_id, dict(payload)))
                        return
                    if parsed.path == "/api/workbench/meta":
                        self.send_json(workbench.update_resource(active_user_id, dict(payload)))
                        return
                    if parsed.path == "/api/workbench/link":
                        self.send_json(workbench.link(active_user_id, dict(payload)))
                        return
                    if parsed.path == "/api/workbench/delete":
                        self.send_json(workbench.delete(active_user_id, dict(payload)))
                        return
                    if parsed.path == "/api/workbench/rename-symbol":
                        self.send_json(workbench.rename_symbol(active_user_id, dict(payload)))
                        return
                    if parsed.path == "/api/workbench/generate":
                        self.send_json(workbench.generate(active_user_id, dict(payload)))
                        return
                    if parsed.path == "/api/workbench/open-output":
                        self.send_json(workbench.open_output(dict(payload)))
                        return
                    if parsed.path == "/api/workbench/routing/save":
                        routing = workbench.save_routing(active_user_id, dict(payload))
                        self.send_json(
                            {"routing": routing, "workbench": workbench.state(active_user_id)}
                        )
                        return
                    if parsed.path == "/api/workbench/generate-job":
                        self.send_json(workbench.generate_job(active_user_id, dict(payload)))
                        return

                    if (
                        len(parts) == 4
                        and parts[:2] == ["api", "jobs"]
                        and parts[3] == "identity"
                    ):
                        try:
                            job_id = int(parts[2])
                        except ValueError:
                            self.send_json({"error": "Invalid job ID"}, 400)
                            return
                        updated = database.update_identity(
                            job_id,
                            str(payload.get("company", "")),
                            str(payload.get("title", "")),
                            active_user_id,
                        )
                        if not updated:
                            self.send_json({"error": "Not found"}, 404)
                            return
                        self.send_json(
                            {
                                "ok": True,
                                "job": database.get_job(job_id, active_user_id),
                            }
                        )
                        return

                    if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "questions":
                        try:
                            job_id = int(parts[2])
                        except ValueError:
                            self.send_json({"error": "Invalid job ID"}, 400)
                            return
                        if database.get_job(job_id, active_user_id) is None:
                            self.send_json({"error": "Not found"}, 404)
                            return
                        question_id = database.add_question(
                            job_id,
                            str(payload.get("question", "")),
                            str(payload.get("suggested_answer", "")),
                            str(payload.get("answer", "")),
                        )
                        self.send_json(
                            {
                                "ok": True,
                                "question_id": question_id,
                                "job": database.get_job(job_id, active_user_id),
                            }
                        )
                        return
                    if len(parts) == 5 and parts[:2] == ["api", "jobs"] and parts[3] == "questions":
                        try:
                            job_id = int(parts[2])
                            question_id = int(parts[4])
                        except ValueError:
                            self.send_json({"error": "Invalid question"}, 400)
                            return
                        if database.get_job(job_id, active_user_id) is None:
                            self.send_json({"error": "Not found"}, 404)
                            return
                        updated = database.update_question(
                            job_id,
                            question_id,
                            str(payload.get("question", "")),
                            str(payload.get("answer", "")),
                        )
                        if not updated:
                            self.send_json({"error": "Question not found"}, 404)
                            return
                        self.send_json(
                            {
                                "ok": True,
                                "job": database.get_job(job_id, active_user_id),
                            }
                        )
                        return
                    if parsed.path == "/api/capabilities/entities/upsert":
                        entity = capabilities.upsert_entity(dict(payload.get("entity", payload)))
                        self.send_json(
                            {
                                "ok": True,
                                "entity": entity,
                                "capabilities": capabilities.state(),
                            }
                        )
                        return
                    if parsed.path == "/api/capabilities/entities/delete":
                        entity_ids = payload.get("entity_ids") or [payload.get("entity_id", "")]
                        capabilities.delete_entities(entity_ids)
                        self.send_json({"ok": True, "capabilities": capabilities.state()})
                        return
                    if parsed.path == "/api/capabilities/rating":
                        entity_ids = payload.get("entity_ids") or [payload.get("entity_id", "")]
                        capabilities.update_flags(entity_ids, rating=int(payload.get("rating", 0)))
                        self.send_json({"ok": True, "capabilities": capabilities.state()})
                        return
                    if parsed.path == "/api/capabilities/match":
                        entity_ids = payload.get("entity_ids") or [payload.get("entity_id", "")]
                        capabilities.update_flags(
                            entity_ids,
                            match_enabled=bool(payload.get("enabled", True)),
                        )
                        self.send_json({"ok": True, "capabilities": capabilities.state()})
                        return
                    if parsed.path == "/api/capabilities/iterator":
                        entity_ids = payload.get("entity_ids") or [payload.get("entity_id", "")]
                        capabilities.update_flags(
                            entity_ids,
                            iterator_enabled=bool(payload.get("enabled", True)),
                        )
                        self.send_json({"ok": True, "capabilities": capabilities.state()})
                        return
                    if parsed.path == "/api/capabilities/relationships":
                        capabilities.save_relationships(
                            list(payload.get("relationships", [])),
                            replace=bool(payload.get("replace", False)),
                        )
                        self.send_json({"ok": True, "capabilities": capabilities.state()})
                        return
                    if parsed.path == "/api/capabilities/view-preferences":
                        capabilities.save_view_preferences(
                            dict(payload.get("view_preferences", payload))
                        )
                        self.send_json({"ok": True, "capabilities": capabilities.state()})
                        return
                    if parsed.path == "/api/capabilities/sets/save":
                        set_id = str(payload.get("set_id", "")).strip()
                        name = str(payload.get("name", "")).strip()
                        capability_ids = [
                            str(value).strip()
                            for value in payload.get("capability_ids", [])
                            if str(value).strip()
                        ]
                        document_enabled = (
                            bool(payload["document_enabled"])
                            if "document_enabled" in payload
                            else None
                        )
                        paste_enabled = (
                            bool(payload["paste_enabled"]) if "paste_enabled" in payload else None
                        )
                        set_id = capabilities.save_set(
                            set_id,
                            name,
                            capability_ids,
                            document_enabled=document_enabled,
                            paste_enabled=paste_enabled,
                        )
                        self.send_json(
                            {
                                "ok": True,
                                "set_id": set_id,
                                "capabilities": capabilities.state(),
                            }
                        )
                        return
                    if parsed.path == "/api/capabilities/sets/delete":
                        capabilities.delete_set(str(payload.get("set_id", "")).strip())
                        self.send_json({"ok": True, "capabilities": capabilities.state()})
                        return
                    if parsed.path == "/api/capabilities/sets/active":
                        set_id = str(payload.get("set_id", SYSTEM_SET_ALL_ID)).strip()
                        capabilities.set_active_set(set_id)
                        self.send_json({"ok": True, "capabilities": capabilities.state()})
                        return
                    if parsed.path == "/api/capabilities/smart-add/apply":
                        self.send_json(
                            capabilities.apply_smart_add(dict(payload.get("data", payload)))
                        )
                        return
                    if parsed.path == "/api/capabilities/clear":
                        capabilities.clear(confirm=bool(payload.get("confirm", False)))
                        self.send_json({"ok": True, "capabilities": capabilities.state()})
                        return

                    if parsed.path == "/api/user/save":
                        user_data.save_user(payload)
                        self.send_json({"ok": True})
                        return
                    if parsed.path == "/api/user/custom-fields":
                        user_data.save_custom_fields(list(payload.get("fields", [])))
                        self.send_json({"ok": True})
                        return
                    if parsed.path == "/api/user/custom-actions":
                        reserved_labels = set(BUILTIN_ACTION_LABELS.values())
                        user_data.save_custom_actions(
                            list(payload.get("actions", [])), reserved_labels
                        )
                        self.send_json({"ok": True})
                        return
                    if parsed.path == "/api/user/work-history":
                        user_data.save_work_history(list(payload.get("entries", [])))
                        self.send_json({"ok": True})
                        return
                    if parsed.path == "/api/user/answers":
                        user_data.save_answers(list(payload.get("answers", [])))
                        self.send_json({"ok": True})
                        return
                    if parsed.path == "/api/user/keyboard-layout":
                        user_data.set_keyboard_layout(str(payload.get("layout", "")))
                        self.send_json({"ok": True})
                        return
                    if parsed.path == "/api/keybinds":
                        user_data.save_keybinds(payload)
                        self.send_json({"ok": True})
                        return
                    if parsed.path == "/api/users/create":
                        user_id = user_data.create_user(
                            str(payload.get("name", "")), bool(payload.get("clone", False))
                        )
                        self.send_json({"ok": True, "id": user_id})
                        return
                    if parsed.path == "/api/users/switch":
                        user_data.switch_user(int(payload.get("id", 0)))
                        self.send_json({"ok": True})
                        return
                    if parsed.path == "/api/users/delete":
                        user_data.delete_user(int(payload.get("id", 0)))
                        self.send_json({"ok": True})
                        return
                    if parsed.path == "/api/user-data/import":
                        incoming = dict(payload.get("data", {}))
                        user_data.import_data(incoming, str(payload.get("mode", "merge")))
                        self.send_json({"ok": True})
                        return
                except (ValueError, KeyError, StopIteration) as error:
                    self.send_json({"error": str(error)}, 400)
                    return

                if len(parts) == 4 and parts[:2] == ["api", "jobs"] and parts[3] == "status":
                    try:
                        job_id = int(parts[2])
                        status = str(payload["status"])
                    except (ValueError, KeyError, json.JSONDecodeError):
                        self.send_json({"error": "Invalid request"}, 400)
                        return
                    allowed_statuses = {
                        "Captured",
                        "Reviewing",
                        "Interested",
                        "Applying",
                        "Applied",
                        "Recruiter Screen",
                        "Interviewing",
                        "Offer",
                        "Rejected",
                        "Withdrawn",
                        "Archived",
                    }
                    if status not in allowed_statuses:
                        self.send_json({"error": "Invalid job status"}, 400)
                        return
                    active_user_id = self.active_user_id()
                    if database.get_job(job_id, active_user_id) is None:
                        self.send_json({"error": "Not found"}, 404)
                        return
                    database.set_status(job_id, status, active_user_id)
                    self.send_json(
                        {
                            "ok": True,
                            "job": database.get_job(job_id, active_user_id),
                        }
                    )
                    return
                self.send_error(404)

            def do_DELETE(self):
                parsed = urlparse(self.path)
                parts = parsed.path.strip("/").split("/")
                if len(parts) == 5 and parts[:2] == ["api", "jobs"] and parts[3] == "questions":
                    try:
                        job_id = int(parts[2])
                        question_id = int(parts[4])
                    except ValueError:
                        self.send_json({"error": "Invalid question"}, 400)
                        return
                    active_user_id = self.active_user_id()
                    if database.get_job(job_id, active_user_id) is None:
                        self.send_json({"error": "Not found"}, 404)
                        return
                    deleted = database.delete_question(job_id, question_id)
                    self.send_json(
                        {"ok": True, "job": database.get_job(job_id, active_user_id)}
                        if deleted
                        else {"error": "Question not found"},
                        200 if deleted else 404,
                    )
                    return
                if len(parts) == 3 and parts[:2] == ["api", "jobs"]:
                    try:
                        job_id = int(parts[2])
                    except ValueError:
                        self.send_json({"error": "Invalid job ID"}, 400)
                        return
                    active_user_id = self.active_user_id()
                    deleted = database.delete_job(job_id, active_user_id)
                    self.send_json(
                        {"ok": deleted} if deleted else {"error": "Not found"},
                        200 if deleted else 404,
                    )
                    return
                self.send_error(404)

            def log_message(self, _format, *_args):
                return

        self.httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self.port = int(self.httpd.server_address[1])
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None