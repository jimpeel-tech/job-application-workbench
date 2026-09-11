# Installation

JAW is a Windows-first desktop application. You can use a packaged `JAW.exe` or install it from source.

## Requirements

- Windows 10 or Windows 11
- Optional: [Ollama](ollama.md) for local generative AI workflows
- Optional: [Tectonic](tectonic.md) for Document PDF preview/generation
- Optional: Microsoft Outlook configuration for [Outlook sync](outlook-sync.md)
- Python 3.11+ and Git only when installing from source or building JAW yourself

JAW's default local job-analysis path does not require Ollama, OpenAI, or another AI provider.

## Install the Windows executable

For release builds, download `JAW.exe` from the matching GitHub Release and run it directly. Python and Git are not required on the target machine.

The executable contains JAW and its packaged runtime assets, but it does **not** bundle Ollama or Tectonic. Install those separately only if you want the workflows that use them. In particular, Tectonic is required before Documents can Preview or Generate PDFs.

Current alpha executables are not code-signed, so Windows SmartScreen may show an **Unknown publisher** warning after download.

If Windows SmartScreen shows **Windows protected your PC**:

1. Click **More info**.
2. Confirm the app is `JAW.exe`.
3. Click **Run anyway**.

JAW alpha builds are currently unsigned, so Windows may display **Publisher: Unknown publisher**. Download JAW only from the official GitHub Releases page and verify the published SHA-256 checksum if desired.

You can also create a build from the repository through GitHub Actions or locally. See [Building JAW for Windows](building.md).

## Install from the repository

Open PowerShell:

```powershell
git clone https://github.com/jimpeel-tech/job-application-workbench.git
cd job-application-workbench

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install .
```

If your default `python` is already Python 3.11 or newer, you can use `python -m venv .venv` instead of the Windows `py` launcher.

Start JAW with:

```powershell
jaw
```

The installed `jaw` command launches the Job Application Workbench desktop window and starts JAW's local dashboard as needed.

## First run

A fresh JAW data store is populated with a fictional demo user named **Ol Sarge** plus sample work history, capabilities, settings, and example jobs. The sample data is there so the interface is useful immediately; it is not intended to become your permanent profile.

Open **Manage User** in the upper-right corner, create your own user, and switch to it before entering real application data.

New users default to **Local** Job Description Analysis, so no AI service is required to begin capturing and analyzing jobs. Tectonic is needed only when you want Documents to compile PDF previews/output, and Ollama/OpenAI are optional for generative workflows.

See [First Run](first-run.md) for the recommended setup order and a first end-to-end workflow.

## Writable application data

A normal installed copy stores writable application state under:

```text
%LOCALAPPDATA%\JAW\
├── config.toml
├── data\
│   └── jaw.db
└── fonts\
```

JAW creates and normalizes `config.toml` automatically. Profile data, jobs, capabilities, keybinds, document resources, and other user data are stored in the local SQLite database. The `fonts` directory is the writable location for user-provided document fonts and may be created only when needed.

To place JAW's writable state somewhere else, set `JAW_HOME` before starting the application:

```powershell
$env:JAW_HOME = "D:\JAW"
jaw
```

To persist the override for your Windows user:

```powershell
[System.Environment]::SetEnvironmentVariable("JAW_HOME", "D:\JAW", "User")
```

Open a new terminal after setting a persistent environment variable.

## Development install

For development, use an editable install with the test dependencies:

```powershell
git clone https://github.com/jimpeel-tech/job-application-workbench.git
cd job-application-workbench

py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]

python -m pytest -q
python -m ruff check src tests
```

An editable checkout deliberately uses the repository root as JAW's application home, so development data is written to the checkout's ignored `config.toml`, `data/`, and `fonts/` paths. A normal installed copy uses `%LOCALAPPDATA%\JAW` instead.

## Build an executable

See [Building JAW for Windows](building.md) for the local PyInstaller command and the automated GitHub Actions build/release workflow.

## Optional Chrome extension

JAW includes an optional unpacked Chrome extension that reuses the existing local JAW dashboard tab instead of opening duplicates. See [`chrome-extension/README.md`](../chrome-extension/README.md) for installation instructions.

## Next steps

- [First Run](first-run.md)
- [Configure Ollama](ollama.md)
- [Configure Tectonic](tectonic.md)
- [Document Workbench](document-workbench.md)
- [Documents Runtime Objects](documents-runtime.md)
- [Configure Outlook sync](outlook-sync.md)
- [Build JAW for Windows](building.md)
