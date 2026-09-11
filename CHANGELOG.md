# Changelog

All notable public changes to JAW will be documented in this file.

JAW follows semantic versioning. The project is still alpha software: workflows and persisted data formats may continue to change before `1.0.0`.

## 0.1.1 — Unreleased

### Defaults and analysis

- New users now default to deterministic **Local** Job Description Analysis, so the core capture/analyze workflow does not require Ollama or another AI provider.
- Hardened analysis-provider failure handling so optional AI failures do not silently replace deterministic results or leave ambiguous workflow state.
- Improved deterministic Smart Capture extraction and state handling, including regression coverage for provider failures and concurrent capture/update paths.

### Data integrity and capabilities

- Added the `jaw-integrity-audit` command for checking SQLite integrity, required schema, foreign keys, JSON state, user-state invariants, and Document Workbench semantic integrity.
- Preserved capability matching/rating semantics while tightening first-run and release regression coverage.

### Documents

- Standardized the Documents runtime contract across Automatic, Selected Job, Example Data, and no-job contexts.
- `work_exp[*].highlights` is now consistently exposed to Documents as `list[str]` while the user's stored Highlights text remains unchanged.
- Hardened Template, Section, Function, output-filename, and provider error boundaries with clearer Workbench failures.
- Preview remains available when PDF output-directory creation or file replacement fails after a successful render.
- Added writable user-font discovery for installed builds at `%LOCALAPPDATA%\JAW\fonts`, source checkouts at `<repository>\fonts`, and `JAW_HOME\fonts` overrides.
- Tectonic now stages bundled fonts, JAW user fonts, and the optional `JAW_TECTONIC_SEARCH_PATH` together with deterministic filename precedence.
- Added Job Tracker help for Documents routing and the Documents `Ctrl+P` command workflow.
- JAW `0.1.1` supports both Template API 1 and Template API 2 so the immutable `0.1.0` official template release remains compatible while the current runtime contract can move forward.

### Documentation and release preparation

- Refreshed installation and first-run guidance for the fictional **Ol Sarge** seed profile, local-first defaults, writable application data, and optional components.
- Documented Ollama's current optional role in Smart Capture verification, generative analysis, Documents generation blocks, and Outlook classification.
- Expanded Tectonic setup, executable discovery, untrusted rendering, user-font locations, and troubleshooting guidance.
- Expanded Document Workbench/runtime documentation for Generation Context, JAW Objects, capability sets, Highlights lists, helpers, generation blocks, routing, preview, and output behavior.
- Synchronized package/runtime version metadata for `0.1.1`.

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
- Open-source Montserrat, Open Sans, and Qwitcher Grypen font families bundled for reproducible built-in document rendering, with their license texts included in distributions.
- Additional custom fonts can be staged with `JAW_TECTONIC_SEARCH_PATH`.
- Personal databases, configuration, exports, token caches, environment files, and private regression fixtures excluded from version control.

### Documentation

- Installation guide.
- Ollama setup guide.
- Tectonic setup guide.
- Document Workbench guide.
- Outlook sync guide.
- Workbench reference-identity and shared-template architecture notes.
