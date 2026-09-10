# Fonts

JAW bundles open-source fonts used by its built-in document templates so PDF
rendering is reproducible across supported platforms.

Bundled font families:

- Montserrat — SIL Open Font License 1.1
- Open Sans — SIL Open Font License 1.1
- Qwitcher Grypen — SIL Open Font License 1.1

The applicable license texts are included under `licenses/`.

## Custom fonts

Users may additionally provide `.ttf`, `.otf`, or `.ttc` files by setting
`JAW_TECTONIC_SEARCH_PATH`.

JAW stages supported fonts from that directory into the temporary Tectonic
render sandbox alongside the bundled font resources.

```powershell
$env:JAW_TECTONIC_SEARCH_PATH = "C:\Users\you\Fonts\jaw"
jaw
```

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
