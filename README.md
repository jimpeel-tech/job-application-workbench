# Job Application Workbench

**JAW** is a Windows-first, local-first desktop application for reducing repetitive work during job applications. It combines reusable application data, keyboard-driven paste workflows, job capture and analysis, application tracking, capability matching, and document generation in one local workspace.

> **Project status:** JAW is preparing for its initial `v0.1.0` public release. It is currently distributed from source and primarily tested on Windows.

## What JAW does

- **Desktop application assistant** — configurable global hotkeys and iterators for profile data, work experience, skills, links, and reusable answers.
- **Smart Capture** — capture selected job-description text, parse important fields, and optionally verify/enrich the result with Ollama.
- **Job analysis** — compare a posting with your selected capabilities and work experience using the local analyzer or an explicitly configured AI provider.
- **Job Tracker** — local dashboard for jobs, statuses, captured application questions, analysis results, and application history.
- **User Data** — maintain profile fields, work experience, Q&A, capabilities, ratings, matching state, reusable capability sets, actions, and keybinds.
- **Document Workbench** — compose reusable Documents, Templates, Sections, and Functions with Jinja/LaTeX and job-aware generation.
- **PDF generation** — render documents with the standalone Tectonic TeX engine.
- **Optional Outlook sync** — classify job-related mail with local Ollama and reconcile it with tracked applications.
- **Optional Chrome helper** — reuse the existing JAW dashboard tab instead of opening duplicate tabs.

JAW stores its application data locally in SQLite. The default dashboard is served only through the local JAW process at `http://127.0.0.1:8765`.

## Quick start

### Requirements

- Windows 10 or Windows 11
- Python 3.11+
- Git

Open PowerShell:

```powershell
git clone https://github.com/jimpeel-tech/job-application-workbench.git
cd job-application-workbench

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install .

jaw
```

A normal installed copy stores writable state under:

```text
%LOCALAPPDATA%\JAW\
├── config.toml
└── data\
    └── jaw.db
```

JAW creates and normalizes its runtime configuration automatically. Set `JAW_HOME` if you want to use a different writable data directory.

See [Installation](docs/installation.md) for full setup and development-install details.

## Optional components

| Component | Purpose | Required? |
| --- | --- | --- |
| [Ollama](docs/ollama.md) | Local generative-AI verification and analysis | No |
| [Tectonic](docs/tectonic.md) | PDF document rendering | Only for PDF generation |
| [Outlook sync](docs/outlook-sync.md) | Reconcile job-related Outlook mail with Job Tracker | No; requires local Ollama when enabled |
| [Chrome extension](chrome-extension/README.md) | Reuse the current JAW dashboard tab | No |

JAW's default Ollama model is `qwen3:14b`. Ollama is not required for the deterministic local parser.

## Basic workflow

1. Start JAW with `jaw`.
2. Open the local **User Data** pages and add the profile, work-experience, Q&A, and capability data you want to reuse.
3. Use the desktop actions while filling an application form.
4. Use **Smart Capture** on selected job-description text.
5. Run **Analysis** when you want to persist/analyze the captured job and review it in **Job Tracker**.
6. Use the **Document Workbench** to generate job-aware application documents when needed.

The initial keybind set is configurable. Current defaults include:

```text
G    Smart Capture
4    Analysis
B    Job Tracker
F    Skills iterator
R    Work Experience iterator
```

Global hotkeys are disabled on startup by default and can be enabled from JAW when you are ready to use them.

## Analysis and privacy

A new JAW profile starts in local analysis mode.

- **Local analyzer** performs deterministic extraction and capability matching without sending the job description to a generative-AI provider.
- **Ollama** connects to the configured Ollama host. With the default localhost configuration, inference traffic stays on the computer running JAW.
- **OpenAI** is optional. When selected, JAW reads the API key from `OPENAI_API_KEY`; the key is not intended to be stored in JAW's SQLite database or runtime configuration.
- **Outlook sync** is disabled by default. When enabled, its email classification/matching path uses local Ollama rather than OpenAI.

If `OLLAMA_HOST` points to another machine, content sent for Ollama inference is transmitted to that host.

## Document generation

The Document Workbench uses a small composition model:

```text
Document
└── Template
    └── Section references
        └── Function references
```

Templates are normally LaTeX + Jinja. Sections hold document-facing content and can use JAW generation features; Functions provide reusable/extracted logic.

PDF rendering uses Tectonic. JAW does not bundle third-party font binaries; templates that require custom fonts can use `JAW_TECTONIC_SEARCH_PATH`.

See [Document Workbench](docs/document-workbench.md) and [Tectonic Setup](docs/tectonic.md).

## Outlook sync

Outlook synchronization is opt-in and disabled by default:

```toml
[behavior]
outlook_sync_enabled = false
```

When enabled, JAW uses Microsoft Graph device-code authentication with a public-client application and local Ollama for message classification/matching. See [Outlook Sync Configuration](docs/outlook-sync.md).

## Development

```powershell
git clone https://github.com/jimpeel-tech/job-application-workbench.git
cd job-application-workbench

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]

python -m pytest -q
python -m ruff check src tests
```

CI runs the test suite and Ruff on Windows, builds a wheel, verifies required runtime assets, and smoke-tests JAW from the installed wheel rather than relying only on an editable checkout.

## Documentation

- [Installation](docs/installation.md)
- [Ollama Setup](docs/ollama.md)
- [Tectonic Setup](docs/tectonic.md)
- [Document Workbench](docs/document-workbench.md)
- [Outlook Sync](docs/outlook-sync.md)

Contributor architecture notes:

- [Workbench Reference Identity](docs/workbench-reference-identity.md)
- [Shared Global Template Graph Semantics](docs/workbench-shared-template-graph.md)

## License

JAW is licensed under the [MIT License](LICENSE).
