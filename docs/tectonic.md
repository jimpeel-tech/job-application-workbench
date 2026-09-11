# Tectonic Setup

Tectonic is optional unless you want JAW to render PDF documents. JAW uses Tectonic as its LaTeX engine and invokes it in untrusted mode inside a temporary render sandbox.

## When Tectonic is required

Tectonic is used by **Documents** whenever JAW compiles a PDF:

- **Preview** renders the current working buffers through Tectonic and opens the PDF preview without writing the normal output file.
- **Generate** runs the same render pipeline and also writes the PDF to the configured output directory.
- Job Tracker document generation also uses the same Documents/Tectonic render path.

Tectonic is **not** required for Smart Capture, Job Description Analysis, Job Tracker, Capabilities, the Application Assistant, or authoring/editing Document resources before you preview/generate them.

Tectonic is independent of Ollama/OpenAI: Tectonic compiles LaTeX to PDF; AI providers are used only by optional generative workflows.

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

After JAW starts, a quick functional test is to open **Documents**, choose **Example Data** as the Generation Context, and run **Preview** on a valid Document. That verifies both Tectonic discovery and JAW's PDF render path.

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

The corresponding license texts are distributed with JAW under the packaged `resources/fonts/licenses/` directory. During rendering, JAW stages bundled fonts into the temporary Tectonic render sandbox so built-in templates can reference exact filenames with `fontspec`.

Packaged application resources should be treated as read-only. In particular, users of a downloaded `JAW.exe` should not try to add fonts to an internal `src/jaw/resources/fonts` path; that source-tree path does not exist as a writable application directory in an installed one-file build.

### User fonts

JAW has a separate writable font directory for user-provided `.ttf`, `.otf`, and `.ttc` files:

```text
%LOCALAPPDATA%\JAW\fonts
```

For a source checkout, the equivalent directory is:

```text
<repository>\fonts
```

If `JAW_HOME` is set, the directory is:

```text
<JAW_HOME>\fonts
```

JAW creates the user-font directory when a document render needs it. You can also create it yourself and copy font files there:

```powershell
$fontDir = Join-Path $env:LOCALAPPDATA "JAW\fonts"
New-Item -ItemType Directory -Force $fontDir | Out-Null
Copy-Item "C:\Users\you\Downloads\MyFont-Regular.ttf" $fontDir
```

No environment variable is required for fonts stored in the JAW user-font directory.

### Additional external font directory

`JAW_TECTONIC_SEARCH_PATH` may point to one additional directory you control:

```powershell
$env:JAW_TECTONIC_SEARCH_PATH = "C:\Users\you\Fonts\jaw"
jaw
```

This directory supplements rather than replaces JAW's bundled and user-font directories.

At render time JAW stages fonts in this precedence order:

1. bundled JAW fonts;
2. JAW user fonts;
3. the optional `JAW_TECTONIC_SEARCH_PATH` directory.

If two directories contain the same filename, the earlier source wins. This protects bundled templates from accidentally receiving a different font with the same filename. Give custom fonts distinct filenames when possible.

Templates can reference the exact staged filename with `fontspec`:

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

Check the JAW user-font directory first:

```powershell
Get-ChildItem (Join-Path $env:LOCALAPPDATA "JAW\fonts")
```

If you use an additional search directory, confirm it exists and the environment variable is visible to the process that launches JAW:

```powershell
$env:JAW_TECTONIC_SEARCH_PATH
Get-ChildItem $env:JAW_TECTONIC_SEARCH_PATH
```

The template must reference the actual staged filename.

### First render needs network access

Tectonic may need to download TeX support files that are not yet cached. Retry with network access available. Later renders can reuse Tectonic's local cache.

### Preview works but Generate cannot replace the PDF

The target PDF may be open in another application. Close the file and run **Generate** again. Preview can still succeed because it does not need to overwrite the normal output file.
