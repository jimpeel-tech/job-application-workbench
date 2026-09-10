# Tectonic Setup

Tectonic is optional unless you want JAW to render PDF documents. JAW uses Tectonic as its LaTeX engine and invokes it in untrusted mode inside a temporary render sandbox.

## 1. Install Tectonic

Tectonic is distributed as a standalone executable. JAW searches for it in this order:

1. `JAW_TECTONIC_PATH`
2. `tectonic` on the normal system `PATH`
3. `%USERPROFILE%\.local\bin\tectonic.exe`

For Windows, the third option is convenient because JAW checks it automatically.

Open PowerShell and run:

```powershell
$tectonicDir = Join-Path $HOME ".local\bin"
New-Item -ItemType Directory -Force $tectonicDir | Out-Null
Push-Location $tectonicDir

[System.Net.ServicePointManager]::SecurityProtocol = `
    [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString(
    'https://drop-ps1.fullyjustified.net'
))

Pop-Location
```

This uses Tectonic's official Windows download script and leaves `tectonic.exe` in the directory where the script is run.

Official installation documentation:

- https://tectonic-typesetting.github.io/book/latest/installation/

## 2. Verify Tectonic

Because JAW checks `%USERPROFILE%\.local\bin` directly, verify the executable there:

```powershell
& "$HOME\.local\bin\tectonic.exe" --version
```

If you instead installed Tectonic on `PATH`, use:

```powershell
tectonic --version
```

## Custom executable location

Set `JAW_TECTONIC_PATH` when Tectonic is installed elsewhere.

The value may point directly to `tectonic.exe`:

```powershell
$env:JAW_TECTONIC_PATH = "C:\Tools\Tectonic\tectonic.exe"
jaw
```

Or it may point to the containing directory:

```powershell
$env:JAW_TECTONIC_PATH = "C:\Tools\Tectonic"
jaw
```

When a directory is supplied, JAW appends `tectonic.exe` on Windows.

To persist the value for your Windows user:

```powershell
[System.Environment]::SetEnvironmentVariable(
    "JAW_TECTONIC_PATH",
    "C:\Tools\Tectonic\tectonic.exe",
    "User"
)
```

Open a new terminal after changing persistent environment variables.

## TeX packages and first render

Tectonic is self-contained as an executable and can download the TeX support files it needs on demand. The first render of a template may therefore require network access and take longer than later renders.

JAW runs Tectonic with:

```text
--untrusted
--color never
--outdir <temporary directory>
```

and sets:

```text
TECTONIC_UNTRUSTED_MODE=1
```

JAW does not invoke an external MiKTeX, TeX Live, `latex`, or `xelatex` executable.

## Fonts

JAW bundles the open-source font families used by its built-in document templates:

- Montserrat — SIL Open Font License 1.1
- Open Sans — SIL Open Font License 1.1
- Qwitcher Grypen — SIL Open Font License 1.1

The corresponding license texts are distributed with JAW under the packaged `resources/fonts/licenses/` directory. During rendering, JAW stages these bundled fonts into the temporary Tectonic render sandbox so built-in templates can reference their exact filenames with `fontspec`.

### Additional custom fonts

If a document template requires another local `.ttf`, `.otf`, or `.ttc` file, place it in a directory you control and set `JAW_TECTONIC_SEARCH_PATH` before starting JAW:

```powershell
$env:JAW_TECTONIC_SEARCH_PATH = "C:\Users\you\Fonts\jaw"
jaw
```

JAW stages supported font files from that directory into each temporary Tectonic render sandbox alongside the bundled resources. Templates can then reference the exact staged filename with `fontspec`.

Example:

```latex
\setmainfont{MyFont-Regular.ttf}[
  BoldFont = MyFont-Bold.ttf
]
```

Only use additional fonts whose licenses permit your intended use and distribution.

## Troubleshooting

### `Tectonic was not found`

Check the locations JAW searches:

```powershell
$env:JAW_TECTONIC_PATH
Get-Command tectonic -ErrorAction SilentlyContinue
Test-Path "$HOME\.local\bin\tectonic.exe"
```

Then verify the executable directly:

```powershell
& "$HOME\.local\bin\tectonic.exe" --version
```

### Template cannot find a custom font

Confirm the font directory exists and the environment variable is visible in the same terminal used to launch JAW:

```powershell
$env:JAW_TECTONIC_SEARCH_PATH
Get-ChildItem $env:JAW_TECTONIC_SEARCH_PATH
```

The template must reference the actual staged filename.

### First render needs network access

Tectonic may need to download TeX support files that are not yet cached. Retry with network access available. Later renders can reuse Tectonic's local cache.
