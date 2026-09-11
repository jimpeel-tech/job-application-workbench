# Fonts

JAW bundles open-source fonts used by its built-in document templates so PDF
rendering is reproducible across supported platforms.

Bundled font families:

- Montserrat — SIL Open Font License 1.1
- Open Sans — SIL Open Font License 1.1
- Qwitcher Grypen — SIL Open Font License 1.1

The applicable license texts are included under `licenses/`.

## Custom fonts

Do not add personal/custom fonts to this packaged resource directory. Source
checkouts and downloaded JAW executables have different application-resource
locations, and packaged resources are treated as read-only.

Put user-provided `.ttf`, `.otf`, or `.ttc` files in JAW's writable font folder:

- Installed Windows build: `%LOCALAPPDATA%\JAW\fonts`
- Source checkout: `<repository>\fonts`
- `JAW_HOME` override: `<JAW_HOME>\fonts`

JAW stages bundled fonts and user fonts together into each temporary Tectonic
render sandbox. Bundled filenames take precedence on collisions so a custom font
cannot accidentally replace a font required by a built-in template.

An additional external font directory may be supplied with
`JAW_TECTONIC_SEARCH_PATH`:

```powershell
$env:JAW_TECTONIC_SEARCH_PATH = "C:\Users\you\Fonts\jaw"
jaw
```

That directory supplements rather than replaces the bundled and JAW user-font
directories. Give custom fonts distinct filenames if they could collide with a
bundled font.

## Examples

```latex
% Main body font
\setmainfont{OpenSans-Regular.ttf}[
  BoldFont = OpenSans-Bold.ttf,
  ItalicFont = OpenSans-Italic.ttf,
  BoldItalicFont = OpenSans-BoldItalic.ttf,
  Numbers = {Lining, Monospaced}
]

% Header font
\newfontfamily\headerfont{Montserrat-Light.ttf}

% Signature font
\newfontfamily\signaturefont{QwitcherGrypen-Regular.ttf}

\signaturefont
\fontsize{15.5pt}{18pt}
\selectfont
\color{SignatureGray}
{{ user.full_name }}
```
