# JAW icon assets

| File | Use |
| --- | --- |
| `jaw_app.png` | Windows executable and taskbar application identity |
| `jaw_titlebar.png` | Desktop window/title-bar icon; artwork is tightly zoomed for the native Windows slot |
| `jaw_favicon.png` | Local dashboard browser-tab favicon; artwork is aggressively zoomed for Chrome's small favicon slot |

JAW intentionally does not create a system-tray icon. Windows and Chrome control the physical size of title-bar and favicon slots, so the small-surface artwork is cropped/zoomed to use as much of those slots as possible.

`tools/build_windows.py` derives the multi-size Windows `.ico` used by the executable from `jaw_app.png`; the generated `.ico` is a build artifact and is not committed.
