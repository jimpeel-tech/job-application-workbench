(() => {
  const providers = new Map();
  let documentPalette = null;
  let documentPaletteMode = '';
  let documentPaletteItems = [];
  let documentPaletteFiltered = [];
  let documentPaletteIndex = 0;
  let trackerHelpPopover = null;
  let trackerHelpObserver = null;

  function activePageId() {
    return document.querySelector('.page.active')?.id || '';
  }

  function toast(message) {
    const element = document.getElementById('toast');
    if (!element) return;
    element.textContent = message;
    element.style.display = 'block';
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { element.style.display = 'none'; }, 1400);
  }

  function ensureTrackerHelpStyle() {
    if (document.getElementById('trackerHelpStyle')) return;
    const style = document.createElement('style');
    style.id = 'trackerHelpStyle';
    style.textContent = `
      .tracker-help-button {
        min-width: 36px;
        padding-left: 10px;
        padding-right: 10px;
        font-weight: 750;
      }
      .tracker-help-popover[popover] {
        position: fixed;
        inset: auto;
        width: 360px;
        max-width: calc(100vw - 24px);
        max-height: calc(100vh - 24px);
        margin: 0;
        padding: 0;
        overflow: auto;
        background: var(--panel);
        color: var(--text);
        border: 1px solid var(--line);
        border-radius: 8px;
        box-shadow: 0 14px 40px #0009;
        z-index: 500;
      }
      .tracker-help-head {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 14px 14px 10px;
        border-bottom: 1px solid var(--line);
      }
      .tracker-help-head strong { font-size: 15px; }
      .tracker-help-close {
        margin-left: auto;
        padding: 2px 6px;
        border: 0;
        background: transparent;
        color: var(--muted);
        font-size: 20px;
        line-height: 1;
        cursor: pointer;
      }
      .tracker-help-close:hover { color: var(--text); }
      .tracker-help-body { padding: 4px 14px; }
      .tracker-help-row {
        display: grid;
        grid-template-columns: minmax(110px, auto) 1fr;
        gap: 14px;
        align-items: start;
        padding: 11px 0;
      }
      .tracker-help-row + .tracker-help-row { border-top: 1px solid var(--line); }
      .tracker-help-key { color: var(--text); font-weight: 650; }
      .tracker-help-copy { color: var(--muted); line-height: 1.45; }
      .tracker-help-popover kbd {
        display: inline-block;
        min-width: 24px;
        padding: 2px 5px;
        border: 1px solid #4a515d;
        border-bottom-color: #626b78;
        border-radius: 4px;
        background: #171a1f;
        color: var(--text);
        font: 600 12px/1.35 Consolas, monospace;
        text-align: center;
      }
      .tracker-help-actions {
        display: flex;
        justify-content: flex-end;
        padding: 10px 14px 13px;
        border-top: 1px solid var(--line);
      }
      .tracker-help-route {
        padding: 5px 0;
        border: 0;
        background: transparent;
        color: #7eb8ed;
        font-weight: 650;
        cursor: pointer;
      }
      .tracker-help-route:hover { text-decoration: underline; }
      @media (max-width: 680px) {
        .tracker-help-row { grid-template-columns: 1fr; gap: 5px; }
      }
    `;
    document.head.appendChild(style);
  }

  function positionTrackerHelp(button, popover) {
    const rect = button.getBoundingClientRect();
    const width = Math.min(360, Math.max(240, window.innerWidth - 24));
    const left = Math.max(12, Math.min(rect.right - width, window.innerWidth - width - 12));
    popover.style.width = `${width}px`;
    popover.style.left = `${left}px`;
    popover.style.top = `${Math.min(rect.bottom + 8, window.innerHeight - 12)}px`;
  }

  function ensureTrackerHelpPopover() {
    if (trackerHelpPopover?.isConnected) return trackerHelpPopover;
    ensureTrackerHelpStyle();
    trackerHelpPopover = document.createElement('div');
    trackerHelpPopover.id = 'trackerHelpPopover';
    trackerHelpPopover.className = 'tracker-help-popover';
    trackerHelpPopover.setAttribute('popover', 'auto');
    trackerHelpPopover.setAttribute('role', 'dialog');
    trackerHelpPopover.setAttribute('aria-label', 'Job Tracker help');
    trackerHelpPopover.innerHTML = `
      <div class="tracker-help-head">
        <strong>Job Tracker Help</strong>
        <button class="tracker-help-close" type="button" aria-label="Close help">×</button>
      </div>
      <div class="tracker-help-body">
        <div class="tracker-help-row">
          <div class="tracker-help-key"><kbd>Ctrl</kbd> + <kbd>P</kbd></div>
          <div class="tracker-help-copy">Open Document Routing for the current Tracker job. Use <b>⌘ P</b> on macOS.</div>
        </div>
        <div class="tracker-help-row">
          <div class="tracker-help-key">Generate Document</div>
          <div class="tracker-help-copy">Generate the configured output Documents for this job using the first matching title rule, then the fallback route.</div>
        </div>
        <div class="tracker-help-row">
          <div class="tracker-help-key">Document Routing</div>
          <div class="tracker-help-copy">Control title rules and fallback outputs used when generating documents from Job Tracker.</div>
        </div>
      </div>
      <div class="tracker-help-actions">
        <button class="tracker-help-route" type="button">Manage Document Routing →</button>
      </div>`;
    document.body.appendChild(trackerHelpPopover);
    trackerHelpPopover.querySelector('.tracker-help-close').addEventListener('click', () => {
      trackerHelpPopover.hidePopover();
    });
    trackerHelpPopover.querySelector('.tracker-help-route').addEventListener('click', () => {
      trackerHelpPopover.hidePopover();
      if (window.JawDocumentGeneration?.open) {
        window.JawDocumentGeneration.open();
      } else {
        open('settings');
      }
    });
    trackerHelpPopover.addEventListener('toggle', () => {
      const button = document.querySelector('[data-tracker-help]');
      if (button) button.setAttribute('aria-expanded', trackerHelpPopover.matches(':popover-open') ? 'true' : 'false');
    });
    return trackerHelpPopover;
  }

  function openTrackerHelp(button) {
    const popover = ensureTrackerHelpPopover();
    if (popover.matches(':popover-open')) {
      popover.hidePopover();
      return;
    }
    positionTrackerHelp(button, popover);
    popover.showPopover();
  }

  function installTrackerHelpButton() {
    const actions = document.querySelector('#jobsPage .tracker-header-actions');
    if (!actions || actions.querySelector('[data-tracker-help]')) return;
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'btn tracker-help-button';
    button.dataset.trackerHelp = '';
    button.textContent = '?';
    button.title = 'Job Tracker help';
    button.setAttribute('aria-label', 'Job Tracker help');
    button.setAttribute('aria-haspopup', 'dialog');
    button.setAttribute('aria-controls', 'trackerHelpPopover');
    button.setAttribute('aria-expanded', 'false');
    button.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      openTrackerHelp(button);
    });
    const divider = actions.querySelector('.tracker-action-divider');
    const deleteButton = actions.querySelector('.tracker-danger-link');
    actions.insertBefore(button, divider || deleteButton || null);
  }

  function installTrackerHelp() {
    const detail = document.getElementById('detail');
    if (!detail) return;
    ensureTrackerHelpPopover();
    installTrackerHelpButton();
    if (!trackerHelpObserver) {
      trackerHelpObserver = new MutationObserver(installTrackerHelpButton);
      trackerHelpObserver.observe(detail, { childList: true, subtree: true });
    }
    const syncPosition = () => {
      if (!trackerHelpPopover?.matches(':popover-open')) return;
      const button = document.querySelector('[data-tracker-help]');
      if (button) positionTrackerHelp(button, trackerHelpPopover);
    };
    window.addEventListener('resize', syncPosition);
    document.addEventListener('scroll', syncPosition, true);
  }

  function open(mode = 'settings') {
    const pageId = activePageId();
    const provider = providers.get(pageId);
    if (provider) {
      provider(mode);
      return true;
    }
    window.dispatchEvent(new CustomEvent('jaw:command-palette', {
      detail: { pageId, mode }
    }));
    toast('No command palette is registered for this page yet.');
    return false;
  }

  window.JawCommands = {
    register(pageId, provider) {
      const key = String(pageId || '').trim();
      if (!key || typeof provider !== 'function') return () => {};
      providers.set(key, provider);
      return () => {
        if (providers.get(key) === provider) providers.delete(key);
      };
    },
    open,
    activePageId
  };

  async function requestJson(path, body) {
    const options = body === undefined
      ? { cache: 'no-store' }
      : {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body)
        };
    const response = await fetch(path, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
    return payload;
  }

  async function refreshDocumentWorkbench() {
    await window.JawWorkbenchLoader?.ensureLoaded?.();
    const payload = await requestJson('/api/workbench/state');
    window.JawDocumentWorkbench?.applyPayload?.(payload, 'generation-context-refresh');
    return payload.workbench || {};
  }

  function currentGenerationInfo(state = null) {
    const workbench = state || window.JawWorkbenchStore?.getState?.() || {};
    return workbench.generation_context_info || {};
  }

  function ensureGenerationContextIndicator() {
    const actions = document.querySelector('#documentsPage .wb-status-actions');
    if (!actions) return null;
    let button = document.getElementById('wbGenerationContextStatus');
    if (button) return button;
    button = document.createElement('button');
    button.id = 'wbGenerationContextStatus';
    button.type = 'button';
    button.className = 'wb-status-button';
    button.addEventListener('click', () => openGenerationContextPicker());
    actions.prepend(button);
    return button;
  }

  function renderGenerationContextIndicator(state = null) {
    const info = currentGenerationInfo(state);
    if (!info.mode) return;
    const button = ensureGenerationContextIndicator();
    if (!button) return;
    button.textContent = `Context: ${info.label || info.mode}`;
    button.title = info.error || 'Click to change the Documents Generation Context';
    button.dataset.contextMode = info.mode;
  }

  function ensureDocumentPalette() {
    if (documentPalette?.isConnected) return documentPalette;
    const shell = document.querySelector('#documentsPage .wb-shell');
    if (!shell) return null;
    documentPalette = document.createElement('div');
    documentPalette.className = 'wb-quick';
    documentPalette.id = 'wbDocumentCommandPalette';
    documentPalette.hidden = true;
    documentPalette.innerHTML = `
      <div class="wb-quick-box">
        <div class="wb-quick-title" data-document-palette-title></div>
        <input class="wb-quick-input" data-document-palette-input autocomplete="off" spellcheck="false">
        <div class="wb-quick-results" data-document-palette-results></div>
        <div class="wb-quick-hint">↑↓ navigate · Enter select · Esc close</div>
      </div>`;
    shell.appendChild(documentPalette);
    const input = documentPalette.querySelector('[data-document-palette-input]');
    input.addEventListener('input', () => {
      documentPaletteIndex = 0;
      renderDocumentPalette();
    });
    input.addEventListener('keydown', event => {
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        documentPaletteIndex = Math.min(
          documentPaletteIndex + 1,
          Math.max(0, documentPaletteFiltered.length - 1)
        );
        renderDocumentPalette();
      } else if (event.key === 'ArrowUp') {
        event.preventDefault();
        documentPaletteIndex = Math.max(0, documentPaletteIndex - 1);
        renderDocumentPalette();
      } else if (event.key === 'Enter') {
        event.preventDefault();
        chooseDocumentPaletteRow();
      } else if (event.key === 'Escape') {
        event.preventDefault();
        closeDocumentPalette();
      }
    });
    documentPalette.querySelector('[data-document-palette-results]').addEventListener('mousedown', event => {
      const row = event.target.closest('[data-document-palette-index]');
      if (!row) return;
      event.preventDefault();
      documentPaletteIndex = Number(row.dataset.documentPaletteIndex || 0);
      chooseDocumentPaletteRow();
    });
    documentPalette.addEventListener('mousedown', event => {
      if (event.target === documentPalette) closeDocumentPalette();
    });
    return documentPalette;
  }

  function openDocumentPalette(mode, title, items) {
    const palette = ensureDocumentPalette();
    if (!palette) return;
    documentPaletteMode = mode;
    documentPaletteItems = items;
    documentPaletteFiltered = items;
    documentPaletteIndex = 0;
    palette.querySelector('[data-document-palette-title]').textContent = title;
    const input = palette.querySelector('[data-document-palette-input]');
    input.value = '';
    palette.hidden = false;
    renderDocumentPalette();
    requestAnimationFrame(() => input.focus());
  }

  function closeDocumentPalette() {
    if (documentPalette) documentPalette.hidden = true;
    documentPaletteMode = '';
  }

  function renderDocumentPalette() {
    if (!documentPalette) return;
    const input = documentPalette.querySelector('[data-document-palette-input]');
    const query = String(input.value || '').trim().toLocaleLowerCase();
    documentPaletteFiltered = documentPaletteItems.filter(item => {
      if (!query) return true;
      return `${item.label || ''} ${item.detail || ''}`.toLocaleLowerCase().includes(query);
    });
    documentPaletteIndex = Math.min(
      documentPaletteIndex,
      Math.max(0, documentPaletteFiltered.length - 1)
    );
    const results = documentPalette.querySelector('[data-document-palette-results]');
    results.innerHTML = documentPaletteFiltered.length
      ? documentPaletteFiltered.map((item, index) => `
          <button class="wb-quick-row ${index === documentPaletteIndex ? 'active' : ''}"
                  type="button" data-document-palette-index="${index}">
            <span>${escapeHtml(item.label)}</span><small>${escapeHtml(item.detail || '')}</small>
          </button>`).join('')
      : '<div class="wb-empty compact">No matches</div>';
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, character => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[character]));
  }

  function nativeWorkbenchCommand(label) {
    window.JawDocumentWorkbench?.openQuick?.('settings');
    requestAnimationFrame(() => {
      const input = document.getElementById('wbQuickInput');
      if (!input) return;
      input.value = label;
      input.dispatchEvent(new Event('input', { bubbles: true }));
      input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    });
  }

  async function chooseDocumentPaletteRow() {
    const item = documentPaletteFiltered[documentPaletteIndex];
    if (!item) return;
    const mode = documentPaletteMode;
    closeDocumentPalette();

    if (mode === 'generation-context') {
      try {
        const payload = await requestJson('/api/workbench/routing/save', {
          generation_context: item.selection
        });
        window.JawDocumentWorkbench?.applyPayload?.(payload, 'generation-context');
        const info = currentGenerationInfo(payload.workbench);
        renderGenerationContextIndicator(payload.workbench);
        toast(`Generation Context · ${info.label || item.label}`);
      } catch (error) {
        toast(error.message);
      }
      return;
    }

    if (item.action === 'generation-context') {
      await openGenerationContextPicker();
    } else if (item.action === 'go-to-item') {
      window.JawDocumentWorkbench?.openQuick?.('items');
    } else if (item.action === 'document-routing') {
      window.JawDocumentGeneration?.open?.();
    } else if (item.action === 'word-wrap') {
      document.getElementById('wbStatusWrap')?.click();
    } else if (item.action === 'output-directory') {
      window.JawDocumentWorkbench?.changeOutputDirectory?.();
    } else if (item.action === 'reset-layout') {
      nativeWorkbenchCommand('Reset Layout');
    }
  }

  async function openGenerationContextPicker() {
    try {
      const state = await refreshDocumentWorkbench();
      const info = currentGenerationInfo(state);
      const jobs = Array.isArray(info.available_jobs) ? info.available_jobs : [];
      const currentMode = String(info.mode || 'auto');
      const currentJobId = Number(info.job_id || 0);
      const items = [
        {
          label: `${currentMode === 'auto' ? '✓ ' : ''}Automatic — Latest tracked job`,
          detail: info.mode === 'auto' ? (info.job ? `${info.job.company || 'Unknown Company'} · ${info.job.title || 'Untitled Job'}` : 'No tracked jobs') : 'Use the newest tracked job',
          selection: { mode: 'auto' }
        },
        {
          label: `${currentMode === 'example' ? '✓ ' : ''}Example Data`,
          detail: 'Example Company · Example Title',
          selection: { mode: 'example' }
        },
        ...jobs.map(job => ({
          label: `${currentMode === 'selected' && Number(job.id) === currentJobId ? '✓ ' : ''}${job.company || 'Unknown Company'} — ${job.title || 'Untitled Job'}`,
          detail: 'Selected Job',
          selection: { mode: 'selected', job_id: Number(job.id) }
        }))
      ];
      openDocumentPalette('generation-context', 'Documents · Generation Context', items);
    } catch (error) {
      toast(error.message);
    }
  }

  async function openDocumentsCommands(mode = 'settings') {
    if (mode === 'items') {
      await window.JawWorkbenchLoader?.ensureLoaded?.();
      window.JawDocumentWorkbench?.openQuick?.('items');
      return;
    }
    try {
      const state = await refreshDocumentWorkbench();
      const info = currentGenerationInfo(state);
      renderGenerationContextIndicator(state);
      openDocumentPalette('commands', 'Command Palette', [
        {
          label: 'Documents: Set Generation Context…',
          detail: info.label || 'Automatic — Latest tracked job',
          action: 'generation-context'
        },
        { label: 'Go to Item', detail: 'Documents, resources, and JAW objects', action: 'go-to-item' },
        { label: 'Document Routing', detail: 'Job document rules and manual generation', action: 'document-routing' },
        { label: 'Word Wrap', detail: 'Toggle editor word wrapping', action: 'word-wrap' },
        { label: 'Output Directory', detail: 'Generated PDF destination', action: 'output-directory' },
        { label: 'Reset Layout', detail: 'Reset Workbench panes', action: 'reset-layout' }
      ]);
    } catch (error) {
      toast(error.message);
    }
  }

  window.JawCommands.register('documentsPage', openDocumentsCommands);
  window.addEventListener('jaw:workbench-state', event => {
    renderGenerationContextIndicator(event.detail?.snapshot?.state || null);
  });
  setTimeout(() => renderGenerationContextIndicator(), 0);
  installTrackerHelp();

  document.addEventListener('keydown', event => {
    const command = event.ctrlKey || event.metaKey;
    if (!command || event.key.toLowerCase() !== 'p') return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const mode = event.shiftKey ? 'items' : 'settings';

    if (providers.has(activePageId())) {
      open(mode);
      return;
    }
    if (activePageId() === 'documentsPage' && window.JawDocumentWorkbench?.openQuick) {
      window.JawDocumentWorkbench.openQuick(mode);
      return;
    }
    open(mode);
  }, true);
})();