# Installation

JAW is currently a Windows-first desktop application distributed from source. Python 3.11 or newer is required.

## Requirements

- Windows 10 or Windows 11
- Python 3.11+
- Git
- Optional: [Ollama](ollama.md) for local generative AI
- Optional: [Tectonic](tectonic.md) for PDF document rendering
- Optional: Microsoft Outlook configuration for [Outlook sync](outlook-sync.md)

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

## First-run data

A normal installed copy stores writable application state under:

```text
%LOCALAPPDATA%\JAW\
├── config.toml
└── data\
    └── jaw.db
```

JAW creates and normalizes `config.toml` automatically. Profile data, jobs, capabilities, keybinds, document resources, and other user data are stored in the local SQLite database.

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

An editable checkout deliberately uses the repository root as JAW's application home, so development data is written to the checkout's ignored `config.toml` and `data/` paths. A normal installed copy uses `%LOCALAPPDATA%\JAW` instead.

## Optional Chrome extension

JAW includes an optional unpacked Chrome extension that reuses the existing local JAW dashboard tab instead of opening duplicates. See [`chrome-extension/README.md`](../chrome-extension/README.md) for installation instructions.

## Next steps

- [Configure Ollama](ollama.md)
- [Configure Tectonic](tectonic.md)
- [Configure Outlook sync](outlook-sync.md)
