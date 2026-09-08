# Installation

JAW is a Windows-first desktop application. You can use a packaged `JAW.exe` or install it from source.

## Requirements

- Windows 10 or Windows 11
- Optional: [Ollama](ollama.md) for local generative AI
- Optional: [Tectonic](tectonic.md) for PDF document rendering
- Optional: Microsoft Outlook configuration for [Outlook sync](outlook-sync.md)
- Python 3.11+ and Git only when installing from source or building JAW yourself

## Install the Windows executable

For release builds, download `JAW.exe` from the matching GitHub Release and run it directly. Python and Git are not required on the target machine.

Current alpha executables are not code-signed, so Windows SmartScreen may show an **Unknown publisher** warning after download.

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

## Build an executable

See [Building JAW for Windows](building.md) for the local PyInstaller command and the automated GitHub Actions build/release workflow.

## Optional Chrome extension

JAW includes an optional unpacked Chrome extension that reuses the existing local JAW dashboard tab instead of opening duplicates. See [`chrome-extension/README.md`](../chrome-extension/README.md) for installation instructions.

## Next steps

- [Build JAW for Windows](building.md)
- [Configure Ollama](ollama.md)
- [Configure Tectonic](tectonic.md)
- [Configure Outlook sync](outlook-sync.md)
