# Custom fonts

JAW does not bundle third-party font binaries.

Tectonic rendering runs in `--untrusted` mode. If a document template requires local `.ttf`, `.otf`, or `.ttc` files, place them in a directory you control and set `JAW_TECTONIC_SEARCH_PATH` to that directory before starting JAW.

JAW stages supported font files from that directory into each temporary render sandbox so templates can reference exact filenames with `fontspec`.

Example:

```powershell
$env:JAW_TECTONIC_SEARCH_PATH = "C:\Users\you\Fonts\jaw"
jaw
```

A template can then reference a staged font by filename:

```latex
\setmainfont{MyFont-Regular.ttf}[
  BoldFont = MyFont-Bold.ttf
]
```

Only use fonts whose licenses permit your intended use and distribution.
