# Building JAW for Windows

JAW can be packaged as a standalone Windows executable with PyInstaller. The default build is a single `JAW.exe`; Python is not required on the target machine.

Ollama and Tectonic are optional external programs and are not embedded in the executable.

## Release distribution

Normal users should download `JAW.exe` from the repository's **Releases** page. They do not need a GitHub account, Python, Git, or access to GitHub Actions. Each tagged `v*` build automatically creates or updates the matching GitHub Release and attaches:

```text
JAW.exe
JAW.exe.sha256
```

## Maintainer / development builds with GitHub Actions

The repository also includes **Build Windows executable** under GitHub Actions. Manual workflow runs are intended for maintainers and testers who want an ad-hoc build before creating a release:

1. Open the repository's **Actions** tab.
2. Select **Build Windows executable**.
3. Choose **Run workflow** on `main`.
4. Download the `JAW-windows-x64` artifact when the job completes.

The Actions artifact contains the same executable and checksum, but it is not the normal public installation path.

## Build locally

From PowerShell in the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[build]"

python tools\build_windows.py
```

Output:

```text
dist\JAW.exe
```

To build a directory distribution instead:

```powershell
python tools\build_windows.py --onedir
```

Output:

```text
dist\JAW\
```

## Runtime data

A packaged executable uses the normal installed-data location rather than the repository:

```text
%LOCALAPPDATA%\JAW\
├── config.toml
└── data\
    └── jaw.db
```

`JAW_HOME` can still override this location.

## Branding assets

The executable icon is generated at build time from `src/jaw/resources/icons/jaw_app.png`. The desktop window uses the packaged `jaw_titlebar.png`, and the local web dashboard serves `jaw_favicon.png` as its browser favicon. JAW does not create a system-tray icon.

## Windows signing

Current alpha builds are not code-signed. Windows SmartScreen may therefore show an **Unknown publisher** warning on a freshly downloaded executable. Code signing can be added to the build workflow later without changing the PyInstaller packaging model.
