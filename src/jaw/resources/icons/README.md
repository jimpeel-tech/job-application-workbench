# JAW icon assets

"
    "| File | Use |
"
    "| --- | --- |
"
    "| `jaw_app.png` | Windows executable/taskbar application identity |
"
    "| `jaw_tray.png` | Windows notification-area icon; high-contrast small-size artwork |
"
    "| `jaw_titlebar.png` | Desktop window/title-bar icon |
"
    "| `jaw_favicon.png` | Local dashboard browser-tab favicon |

"
    "The committed PNGs are intentionally cropped tightly around visible artwork so the glyph fills Windows/Chrome 16–32 px icon slots. `tools/build_windows.py` derives the multi-size Windows `.ico` used by the executable from `jaw_app.png`; the generated `.ico` is a build artifact and is not committed.
"
    