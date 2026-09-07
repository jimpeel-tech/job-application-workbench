# Changelog

All notable public changes to JAW will be documented in this file.

JAW follows semantic versioning. The initial public release is `0.1.0` and should be treated as alpha software: workflows and persisted data formats may still change before `1.0.0`.

## 0.1.0 — Initial public release

### Desktop workflow

- Windows desktop assistant with configurable global hotkeys and keyboard-driven paste actions.
- Reusable profile, contact, work-experience, answer, capability, and custom-action data.
- Smart Capture workflow for collecting and reviewing job-posting information.
- Configurable capability sets, ratings, matching state, and iterator behavior.

### Job analysis and tracking

- Local deterministic job-description parsing and capability matching.
- Optional Ollama and OpenAI analysis providers.
- Local Job Tracker dashboard with application status, analysis, questions, and history.
- Per-user local SQLite storage.

### Documents

- Native Document Workbench with Documents, Templates, Sections, and Functions.
- Private and Global reusable-resource model with durable reference identity.
- Working-source checkpoints and explicit structural transitions.
- Jinja/LaTeX runtime with `user`, `job_ref`, `work_exp`, `cap`, and `system` objects.
- Optional Ollama/OpenAI generation blocks inside Sections and Functions.
- Tectonic PDF preview and generation.
- Generation Context selection and Job Tracker document routing.
- Template Repository support.

### Integrations

- Optional Outlook synchronization through Microsoft Graph device-code authentication.
- Local Ollama classification/matching for Outlook job-search email.
- Optional Chrome extension for reusing the existing local JAW dashboard tab.

### Packaging and safety

- Source and wheel installation support on Python 3.11+.
- Runtime web assets included and smoke-tested from an installed wheel.
- Dashboard bound to loopback by default with loopback Host and mutation-Origin validation.
- No third-party font binaries bundled with JAW; custom fonts can be staged with `JAW_TECTONIC_SEARCH_PATH`.
- Personal databases, configuration, exports, token caches, environment files, and private regression fixtures excluded from version control.

### Documentation

- Installation guide.
- Ollama setup guide.
- Tectonic setup guide.
- Document Workbench guide.
- Outlook sync guide.
- Workbench reference-identity and shared-template architecture notes.
