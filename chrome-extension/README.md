# JAW Dashboard Tab Reuse

This optional Chrome extension keeps JAW dashboard navigation in one browser tab. When JAW opens another dashboard URL, the extension focuses the oldest existing JAW dashboard tab, navigates it to the requested page/job, and closes the duplicate tab.

JAW does not require this extension to run.

## Install

1. Open `chrome://extensions` in Chrome.
2. Enable **Developer mode**.
3. Select **Load unpacked**.
4. Choose the repository's `chrome-extension` folder.

After editing the extension files, use the extension card's **Reload** button on `chrome://extensions`.

## Port limitation

The extension is intentionally scoped to JAW's default local dashboard URL:

```text
http://127.0.0.1:8765/*
```

If you configure JAW to use a different dashboard port, update the matching URL in `manifest.json` and `background.js`, then reload the unpacked extension.

The extension requests Chrome's `tabs` permission so it can find, focus, navigate, and close duplicate JAW dashboard tabs. Its host permission is limited to the local JAW dashboard URL above.
