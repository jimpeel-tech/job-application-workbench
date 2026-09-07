(() => {
  const shell = document.querySelector('.wb-shell');
  const newDocument = document.getElementById('wbNewDocument');
  const workbench = window.JawDocumentWorkbench;
  if (!shell || !newDocument || !workbench || document.getElementById('wbTemplateRepo')) return;

  let overlay = null;
  let catalog = null;
  let selectedKey = '';
  let busy = false;

  const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[character]));

  async function request(path, body) {
    const options = body === undefined
      ? { cache: 'no-store' }
      : {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        };
    const response = await fetch(path, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
    return payload;
  }

  function selectedTemplate() {
    return (catalog?.templates || []).find(
      item => `${item.source}:${item.id}` === selectedKey
    ) || null;
  }

  function setMessage(text = '', kind = '') {
    const message = overlay?.querySelector('[data-wb-repository-message]');
    if (!message) return;
    message.textContent = text;
    message.className = `wb-repository-message ${kind}`;
  }

  function setBusy(value) {
    busy = Boolean(value);
    overlay?.querySelectorAll('button').forEach(button => {
      if (button.dataset.wbRepositoryClose !== undefined) return;
      button.disabled = busy;
    });
    const clone = overlay?.querySelector('[data-wb-repository-clone]');
    if (clone) clone.disabled = busy || !selectedTemplate()?.valid;
  }

  function renderDetails() {
    const details = overlay?.querySelector('[data-wb-repository-details]');
    const clone = overlay?.querySelector('[data-wb-repository-clone]');
    if (!details || !clone) return;
    const item = selectedTemplate();
    clone.disabled = busy || !item?.valid;
    if (!item) {
      details.innerHTML = '<div class="wb-repository-empty">Select a template.</div>';
      return;
    }
    details.innerHTML = `
      <div class="wb-repository-detail-head">
        <h3>${esc(item.name)}</h3>
        <span class="wb-repository-badge">${item.source === 'local' ? 'Local' : 'Example'}</span>
      </div>
      <p>${esc(item.description || 'No description provided.')}</p>
      <dl class="wb-repository-meta">
        <dt>Package</dt><dd><code>${esc(item.id)}</code></dd>
        <dt>Format</dt><dd>${esc(item.format_version)}</dd>
        ${item.repo_version ? `<dt>Repo</dt><dd>v${esc(item.repo_version)}</dd>` : ''}
      </dl>
      ${item.valid ? '' : `<div class="wb-repository-error">${esc(item.error || 'Invalid template package')}</div>`}`;
  }

  function renderCatalog(nextCatalog) {
    catalog = nextCatalog || { templates: [] };
    const list = overlay?.querySelector('[data-wb-repository-list]');
    const version = overlay?.querySelector('[data-wb-repository-version]');
    const downloadDev = overlay?.querySelector('[data-wb-repository-download-dev]');
    if (!list || !version) return;

    const repo = catalog.repository || {};
    if (downloadDev) downloadDev.hidden = !repo.can_download_dev;
    if (repo.installed_channel === 'dev') {
      version.textContent = `Installed Dev${repo.installed_version ? ` · repo v${repo.installed_version}` : ''} · Release v${repo.available_version || '—'} available`;
    } else {
      version.textContent = repo.installed_version
        ? `Installed v${repo.installed_version} · Available v${repo.available_version || '—'}`
        : `Not downloaded · Available v${repo.available_version || '—'}`;
    }

    const items = catalog.templates || [];
    if (!items.length) {
      selectedKey = '';
      list.innerHTML = `
        <div class="wb-repository-empty">
          No templates installed.<br>
          Download official examples or add a package under <code>local/</code>.
        </div>`;
      renderDetails();
      return;
    }

    if (!items.some(item => `${item.source}:${item.id}` === selectedKey)) {
      const preferred = items.find(item => item.valid) || items[0];
      selectedKey = `${preferred.source}:${preferred.id}`;
    }
    list.innerHTML = items.map(item => {
      const key = `${item.source}:${item.id}`;
      return `<button type="button" class="wb-repository-row ${key === selectedKey ? 'selected' : ''} ${item.valid ? '' : 'invalid'}" data-wb-repository-template="${esc(key)}">
        <span>${esc(item.name)}</span>
        <small>${item.source === 'local' ? 'Local' : 'Example'}</small>
      </button>`;
    }).join('');
    renderDetails();
  }

  async function refreshCatalog() {
    setMessage('Loading…');
    const next = await request('/api/workbench/repository');
    renderCatalog(next);
    setMessage('');
  }

  function closeRepository() {
    overlay?.remove();
    overlay = null;
    catalog = null;
    selectedKey = '';
    busy = false;
  }

  async function downloadExamples(channel = 'release') {
    if (busy) return;
    const development = channel === 'dev';
    try {
      setBusy(true);
      setMessage(development ? 'Downloading development templates…' : 'Downloading official templates…');
      const result = await request('/api/workbench/repository/download', development
        ? { channel: 'dev' }
        : {
            channel: 'release',
            version: catalog?.repository?.available_version || '',
          });
      renderCatalog(result.catalog);
      setMessage(
        development ? `Downloaded Dev · repo v${result.version}` : `Downloaded v${result.version}`,
        'ok'
      );
    } catch (error) {
      setMessage(String(error.message || error), 'error');
    } finally {
      setBusy(false);
    }
  }

  async function openLocal() {
    if (busy) return;
    try {
      setBusy(true);
      const result = await request('/api/workbench/repository/open-local', {});
      setMessage(`Opened ${result.opened}`, 'ok');
    } catch (error) {
      setMessage(String(error.message || error), 'error');
    } finally {
      setBusy(false);
    }
  }

  async function cloneSelected() {
    if (busy) return;
    if (window.JawWorkbenchTransitions?.hasPending?.()) {
      setMessage('Resolve the pending reference edit before cloning a Document.', 'error');
      return;
    }
    const item = selectedTemplate();
    if (!item?.valid) return;
    try {
      setBusy(true);
      setMessage(`Cloning ${item.name}…`);
      const result = await request('/api/workbench/repository/clone', {
        template_id: item.id,
        source: item.source,
      });
      workbench.applyPayload?.({ state: result.state }, 'repository-clone');
      if (result.document_id) workbench.openDocument(result.document_id);
      closeRepository();
    } catch (error) {
      setMessage(String(error.message || error), 'error');
      setBusy(false);
    }
  }

  function openRepository() {
    if (overlay) return;
    overlay = document.createElement('div');
    overlay.className = 'wb-repository-overlay';
    overlay.innerHTML = `
      <section class="wb-repository-dialog" role="dialog" aria-modal="true" aria-label="Template Repository">
        <header class="wb-repository-head">
          <div>
            <strong>Template Repository</strong>
            <small data-wb-repository-version></small>
          </div>
          <div class="wb-repository-head-actions">
            <button type="button" data-wb-repository-download>Download</button>
            <button type="button" class="dev" data-wb-repository-download-dev hidden>Download Dev</button>
            <button type="button" data-wb-repository-open-local>Open Local</button>
            <button type="button" class="wb-repository-x" data-wb-repository-close aria-label="Close">×</button>
          </div>
        </header>
        <div class="wb-repository-body">
          <div class="wb-repository-list" data-wb-repository-list></div>
          <div class="wb-repository-details" data-wb-repository-details></div>
        </div>
        <footer class="wb-repository-footer">
          <div class="wb-repository-message" data-wb-repository-message></div>
          <button type="button" data-wb-repository-close>Close</button>
          <button type="button" class="primary" data-wb-repository-clone disabled>Clone</button>
        </footer>
      </section>`;
    shell.appendChild(overlay);

    overlay.querySelector('[data-wb-repository-download]')?.addEventListener(
      'click', () => downloadExamples('release')
    );
    overlay.querySelector('[data-wb-repository-download-dev]')?.addEventListener(
      'click', () => downloadExamples('dev')
    );
    overlay.querySelector('[data-wb-repository-open-local]')?.addEventListener('click', openLocal);
    overlay.querySelector('[data-wb-repository-clone]')?.addEventListener('click', cloneSelected);
    overlay.querySelectorAll('[data-wb-repository-close]').forEach(
      button => button.addEventListener('click', closeRepository)
    );
    overlay.querySelector('[data-wb-repository-list]')?.addEventListener('click', event => {
      const row = event.target.closest('[data-wb-repository-template]');
      if (!row || busy) return;
      selectedKey = row.dataset.wbRepositoryTemplate || '';
      renderCatalog(catalog);
    });
    overlay.addEventListener('mousedown', event => {
      if (event.target === overlay && !busy) closeRepository();
    });
    refreshCatalog().catch(error => setMessage(String(error.message || error), 'error'));
  }

  const button = document.createElement('button');
  button.type = 'button';
  button.id = 'wbTemplateRepo';
  button.className = 'wb-button';
  button.textContent = '+ Template Repo';
  newDocument.insertAdjacentElement('afterend', button);
  button.addEventListener('click', openRepository);

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && overlay && !busy) {
      event.preventDefault();
      closeRepository();
    }
  });
})();
