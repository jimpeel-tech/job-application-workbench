(() => {
  const JOB_KEY = 'jaw.currentJobId';

  // Legacy built-in examples were manager, director, architect. Routing is user-defined now.
  // Lead” is intentionally not treated as management by code; users can encode that rule.

  let commandDialog = null;
  let resultDialog = null;
  let commandState = null;
  let commandNotice = '';
  let pickerSequence = 0;
  let lastGenerated = [];
  let generating = false;

  const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[character]));

  function toast(message) {
    const element = document.getElementById('toast');
    if (!element) return;
    element.textContent = message;
    element.style.display = 'block';
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { element.style.display = 'none'; }, 1800);
  }

  async function getJson(path) {
    const response = await fetch(path, { cache: 'no-store' });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
    return payload;
  }

  async function postJson(path, body = {}) {
    const response = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
    return payload;
  }

  function routeJobId() {
    const match = location.hash.match(/^#\/?tracker\/job\/(\d+)/i);
    return match ? Number(match[1]) : 0;
  }

  function rememberJob(jobId) {
    const id = Number(jobId || 0);
    if (id > 0) sessionStorage.setItem(JOB_KEY, String(id));
    return id;
  }

  function currentJobId() {
    return rememberJob(routeJobId()) || Number(sessionStorage.getItem(JOB_KEY) || 0);
  }

  function installJobTracking() {
    rememberJob(routeJobId());
    const previousShowJob = window.showJob;
    if (typeof previousShowJob === 'function' && !previousShowJob.__jawDocumentJobTracking) {
      const tracked = async function (id, ...args) {
        rememberJob(id);
        return previousShowJob.call(this, id, ...args);
      };
      tracked.__jawDocumentJobTracking = true;
      window.showJob = tracked;
    }
    window.addEventListener('hashchange', () => rememberJob(routeJobId()));
    document.getElementById('userSelector')?.addEventListener('change', () => {
      sessionStorage.removeItem(JOB_KEY);
    });
  }

  function ensureResultDialog() {
    if (resultDialog) return resultDialog;
    resultDialog = document.createElement('dialog');
    resultDialog.className = 'jaw-doc-result-dialog';
    document.body.appendChild(resultDialog);
    resultDialog.addEventListener('click', event => {
      if (event.target === resultDialog) resultDialog.close();
    });
    return resultDialog;
  }

  function generatedItems(generated) {
    if (Array.isArray(generated?.generated_documents)) return generated.generated_documents;
    return generated ? [generated] : [];
  }

  function showGenerationError(message) {
    const dialog = ensureResultDialog();
    dialog.innerHTML = `
      <div class="jaw-doc-dialog-shell">
        <div class="jaw-doc-dialog-head">
          <strong>Document Generation Failed</strong><span class="spacer"></span>
          <button class="jaw-doc-x" type="button" data-result-close aria-label="Close">×</button>
        </div>
        <div class="jaw-doc-result-body">
          <div class="jaw-doc-generation-error">${esc(message)}</div>
        </div>
        <div class="jaw-doc-dialog-actions">
          <button class="jaw-doc-button" type="button" data-error-routing>Open Routing</button>
          <span class="spacer"></span>
          <button class="jaw-doc-button" type="button" data-result-close>Close</button>
        </div>
      </div>`;
    dialog.querySelectorAll('[data-result-close]').forEach(button => {
      button.addEventListener('click', () => dialog.close());
    });
    dialog.querySelector('[data-error-routing]')?.addEventListener('click', async () => {
      dialog.close();
      await openCommandDialog({ notice: message });
    });
    if (!dialog.open) dialog.showModal();
  }

  function showResult(generated) {
    const items = generatedItems(generated);
    lastGenerated = items;
    const dialog = ensureResultDialog();
    const route = generated?.route?.label || items[0]?.route?.label || '';
    const plural = items.length !== 1;
    dialog.innerHTML = `
      <div class="jaw-doc-dialog-shell">
        <div class="jaw-doc-dialog-head">
          <strong>${plural ? 'Documents Generated' : 'Document Generated'}</strong>
          ${route ? `<small>${esc(route)}</small>` : ''}
          <span class="spacer"></span>
          <button class="jaw-doc-x" type="button" data-result-close aria-label="Close">×</button>
        </div>
        <div class="jaw-doc-result-body">
          ${items.map((item, index) => `
            <div class="jaw-doc-result-card">
              <div class="jaw-doc-result-main">
                <div class="jaw-doc-result-file">${esc(item.filename || 'PDF')}</div>
                <div class="jaw-doc-result-meta">${esc(item.document_name || 'Document')}</div>
                <div class="jaw-doc-result-path">${esc(item.output_path || '')}</div>
                ${item.warning ? `<div class="jaw-doc-result-warning">${esc(item.warning)}</div>` : ''}
              </div>
              <div class="jaw-doc-result-card-actions">
                <button class="jaw-doc-button primary" type="button" data-result-open="${index}" ${item.output_written && item.output_path ? '' : 'disabled'}>Open</button>
                <button class="jaw-doc-button" type="button" data-result-location="${index}" ${item.output_path ? '' : 'disabled'}>Location</button>
              </div>
            </div>`).join('')}
        </div>
        <div class="jaw-doc-dialog-actions">
          <span class="spacer"></span>
          <button class="jaw-doc-button" type="button" data-result-close>Close</button>
        </div>
      </div>`;
    dialog.querySelectorAll('[data-result-close]').forEach(button => {
      button.addEventListener('click', () => dialog.close());
    });
    dialog.querySelectorAll('[data-result-open]').forEach(button => {
      button.addEventListener('click', () => openGenerated(Number(button.dataset.resultOpen), 'file'));
    });
    dialog.querySelectorAll('[data-result-location]').forEach(button => {
      button.addEventListener('click', () => openGenerated(Number(button.dataset.resultLocation), 'location'));
    });
    if (!dialog.open) dialog.showModal();
  }

  async function openGenerated(index, target) {
    const generated = lastGenerated[index];
    if (!generated?.output_path) return;
    try {
      await postJson('/api/workbench/open-output', {
        path: generated.output_path,
        target
      });
    } catch (error) {
      toast(error.message);
    }
  }

  async function generateForJob(jobId, documentId = '') {
    if (generating) return null;
    const id = rememberJob(jobId || currentJobId());
    if (!id) {
      toast('Select a job in Job Tracker first');
      return null;
    }

    generating = true;
    const trackerButton = document.querySelector('.tracker-document-action');
    if (trackerButton) trackerButton.disabled = true;
    try {
      const generated = await postJson('/api/workbench/generate-job', {
        job_id: id,
        document_id: documentId || '',
        output_directory: localStorage.getItem('jaw.workbench.outputDirectory') || ''
      });
      const items = generatedItems(generated);
      if (!items.length || items.some(item => !item.filename)) {
        throw new Error('Document generation returned no output');
      }
      showResult(generated);
      toast(items.length === 1 ? `Generated ${items[0].filename}` : `Generated ${items.length} documents`);
      return generated;
    } catch (error) {
      const message = String(error?.message || error);
      if (message.includes('No automatic Document is configured')) {
        await openCommandDialog({ notice: message });
      } else {
        showGenerationError(message);
        toast('Document generation failed');
      }
      return null;
    } finally {
      generating = false;
      if (trackerButton) trackerButton.disabled = false;
    }
  }

  function documentIds(raw, pluralKey, legacyKey) {
    const plural = raw?.[pluralKey];
    const values = Array.isArray(plural) ? plural : (raw?.[legacyKey] ? [raw[legacyKey]] : []);
    return [...new Set(values.map(value => String(value || '').trim()).filter(Boolean))];
  }

  function routingForDialog(raw = {}) {
    const rules = (Array.isArray(raw.rules) ? raw.rules : [])
      .filter(rule => rule?.id)
      .map(rule => ({
        id: String(rule.id),
        label: String(rule.label || rule.id),
        priority: Number(rule.priority || 100),
        keywords: Array.isArray(rule.keywords) ? rule.keywords.map(String) : [],
        document_ids: documentIds(rule, 'document_ids', 'document_id')
      }))
      .sort((a, b) => Number(a.priority) - Number(b.priority) || a.id.localeCompare(b.id));
    return {
      rules,
      default_document_ids: documentIds(raw, 'default_document_ids', 'default_document_id')
    };
  }

  function splitKeywords(value) {
    const seen = new Set();
    return String(value || '')
      .split(/[\n,;|]+/)
      .map(item => item.trim().toLocaleLowerCase())
      .filter(item => item && !seen.has(item) && seen.add(item));
  }

  function escapeRegex(value) {
    return String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }

  function keywordMatch(title, keyword) {
    const normalizedTitle = String(title || '').toLocaleLowerCase().replace(/\s+/g, ' ').trim();
    const normalizedKeyword = String(keyword || '').toLocaleLowerCase().replace(/\s+/g, ' ').trim();
    if (!normalizedTitle || !normalizedKeyword) return false;
    return new RegExp(`(^|[^a-z0-9])${escapeRegex(normalizedKeyword)}($|[^a-z0-9])`, 'i').test(normalizedTitle);
  }

  function selectedDocumentNames(ids, documents) {
    const byId = new Map(documents.map(document => [String(document.id), document]));
    return ids.map(id => byId.get(String(id)))
      .filter(Boolean)
      .map(document => document.name || 'Document');
  }

  function prediction(job, routing, documents) {
    if (!job) {
      return { text: 'Select a Tracker job to preview routing and generate.', warning: false, count: 0 };
    }
    for (const rule of routing.rules) {
      const keyword = (rule.keywords || []).find(item => keywordMatch(job.title, item));
      if (!keyword) continue;
      const names = selectedDocumentNames(rule.document_ids || [], documents);
      if (!names.length) {
        return {
          text: `${rule.label} matched “${keyword}”, but has no output Documents.`,
          warning: true,
          count: 0
        };
      }
      return {
        text: `${rule.label} → ${names.join(' + ')} · matched “${keyword}”`,
        warning: false,
        count: names.length
      };
    }
    const names = selectedDocumentNames(routing.default_document_ids || [], documents);
    if (!names.length) {
      return { text: 'No rule matched and no fallback Documents are assigned.', warning: true, count: 0 };
    }
    return { text: `Fallback → ${names.join(' + ')}`, warning: false, count: names.length };
  }

  function pickerSummary(ids, documents) {
    const names = selectedDocumentNames(ids, documents);
    if (!names.length) return 'Choose output…';
    if (names.length === 1) return names[0];
    return `${names[0]} +${names.length - 1}`;
  }

  function documentPicker(documents, selectedIds, { fallback = false } = {}) {
    const selected = new Set((selectedIds || []).map(String));
    const attribute = fallback ? 'data-route-default' : 'data-route-document';
    const popoverId = `jaw-doc-output-menu-${++pickerSequence}`;
    return `
      <div class="jaw-doc-output-picker">
        <button class="jaw-doc-output-summary" type="button" data-output-summary popovertarget="${popoverId}">${esc(pickerSummary([...selected], documents))}</button>
        <div class="jaw-doc-output-menu" id="${popoverId}" popover="auto">
          ${documents.length ? documents.map(document => `
            <label>
              <input type="checkbox" ${attribute} data-document-id="${esc(document.id)}" ${selected.has(String(document.id)) ? 'checked' : ''}>
              <span>${esc(document.name || 'Document')}</span>
            </label>`).join('') : '<div class="jaw-doc-empty compact">No Documents</div>'}
        </div>
      </div>`;
  }

  function ensureCommandDialog() {
    if (commandDialog) return commandDialog;
    commandDialog = document.createElement('dialog');
    commandDialog.className = 'jaw-doc-command-dialog';
    document.body.appendChild(commandDialog);
    commandDialog.addEventListener('click', event => {
      if (event.target === commandDialog) commandDialog.close();
    });
    return commandDialog;
  }

  function readRoutingFromDialog() {
    const dialog = ensureCommandDialog();
    if (!commandState) return { rules: [], default_document_ids: [] };
    const rows = [...dialog.querySelectorAll('[data-route-rule]')];
    const rules = rows.map((row, index) => ({
      id: row.dataset.routeRule,
      label: row.querySelector('[data-route-label]')?.value.trim() || `Rule ${index + 1}`,
      priority: (index + 1) * 10,
      keywords: splitKeywords(row.querySelector('[data-route-keywords]')?.value),
      document_ids: [...row.querySelectorAll('[data-route-document]:checked')]
        .map(input => input.dataset.documentId)
        .filter(Boolean)
    }));
    const defaultDocumentIds = [...dialog.querySelectorAll('[data-route-default]:checked')]
      .map(input => input.dataset.documentId)
      .filter(Boolean);
    return { rules, default_document_ids: defaultDocumentIds };
  }

  function commitDialogDraft() {
    if (!commandState) return;
    commandState.routing = readRoutingFromDialog();
  }

  function newRuleId() {
    const existing = new Set(commandState?.routing?.rules?.map(rule => rule.id) || []);
    const suffix = Date.now().toString(36);
    let id = `rule_${suffix}`;
    let counter = 1;
    while (existing.has(id)) id = `rule_${suffix}_${counter++}`;
    return id;
  }

  function addRule() {
    commitDialogDraft();
    commandState.routing.rules.push({
      id: newRuleId(),
      label: 'New Rule',
      priority: (commandState.routing.rules.length + 1) * 10,
      keywords: [],
      document_ids: []
    });
    renderCommandDialog();
    const rows = ensureCommandDialog().querySelectorAll('[data-route-rule]');
    rows[rows.length - 1]?.querySelector('[data-route-label]')?.select();
  }

  function deleteRule(ruleId) {
    commitDialogDraft();
    commandState.routing.rules = commandState.routing.rules.filter(rule => rule.id !== ruleId);
    renderCommandDialog();
  }

  function moveRule(ruleId, direction) {
    commitDialogDraft();
    const rules = commandState.routing.rules;
    const index = rules.findIndex(rule => rule.id === ruleId);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= rules.length) return;
    [rules[index], rules[target]] = [rules[target], rules[index]];
    rules.forEach((rule, ruleIndex) => { rule.priority = (ruleIndex + 1) * 10; });
    renderCommandDialog();
  }

  function updatePickerSummary(picker) {
    if (!picker || !commandState) return;
    const ids = [...picker.querySelectorAll('[data-document-id]:checked')]
      .map(input => input.dataset.documentId)
      .filter(Boolean);
    const summary = picker.querySelector('[data-output-summary]');
    if (summary) summary.textContent = pickerSummary(ids, commandState.documents);
  }

  function positionOutputMenu(menu) {
    const picker = menu?.closest('.jaw-doc-output-picker');
    const summary = picker?.querySelector('[data-output-summary]');
    if (!menu || !summary) return;
    const rect = summary.getBoundingClientRect();
    const width = Math.min(Math.max(rect.width, 230), Math.max(230, window.innerWidth - 16));
    menu.style.width = `${width}px`;
    const menuRect = menu.getBoundingClientRect();
    const left = Math.max(8, Math.min(rect.left, window.innerWidth - menuRect.width - 8));
    const below = rect.bottom + 3;
    const top = below + menuRect.height <= window.innerHeight - 8
      ? below
      : Math.max(8, rect.top - menuRect.height - 3);
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
  }

  function refreshPrediction() {
    if (!commandState) return;
    const routing = readRoutingFromDialog();
    const value = prediction(commandState.job, routing, commandState.documents);
    const element = ensureCommandDialog().querySelector('[data-route-prediction]');
    if (element) {
      element.textContent = value.text;
      element.classList.toggle('warning', value.warning);
    }
    const auto = ensureCommandDialog().querySelector('[data-command-auto]');
    if (auto) auto.textContent = value.count > 1 ? `Generate Auto · ${value.count}` : 'Generate Auto';
  }

  function renderCommandDialog() {
    const dialog = ensureCommandDialog();
    const state = commandState;
    if (!state) {
      dialog.innerHTML = '<div class="jaw-doc-dialog-body">Loading Document routing…</div>';
      return;
    }
    const { documents, routing, job } = state;
    const jobLabel = job
      ? `${job.title || 'Untitled job'} · ${job.company || 'Unknown company'}`
      : 'No current job. Select a job in Job Tracker first.';
    const predicted = prediction(job, routing, documents);
    pickerSequence = 0;

    dialog.innerHTML = `
      <div class="jaw-doc-dialog-shell">
        <div class="jaw-doc-dialog-head">
          <strong>Document Routing</strong><small>Title rules → one or more outputs</small><span class="spacer"></span>
          <button class="jaw-doc-x" type="button" data-command-close aria-label="Close">×</button>
        </div>
        <div class="jaw-doc-dialog-body">
          <div class="jaw-doc-current-job"><span>Current job</span><b>${esc(jobLabel)}</b></div>
          ${commandNotice ? `<div class="jaw-doc-command-notice">${esc(commandNotice)}</div>` : ''}

          <div class="jaw-doc-section-head compact">
            <div><h3>Rules</h3><span>First title match wins · top to bottom</span></div>
            <span class="spacer"></span>
            <button class="jaw-doc-button small" type="button" data-add-rule>+ Rule</button>
          </div>

          <div class="jaw-doc-rules-wrap">
            <div class="jaw-doc-routing-header">
              <div></div><div>Rule</div><div>Title keywords</div><div>Outputs</div><div></div>
            </div>
            ${routing.rules.length ? routing.rules.map((rule, index) => `
              <div class="jaw-doc-routing-rule" data-route-rule="${esc(rule.id)}">
                <div class="jaw-doc-rule-order">
                  <button type="button" title="Move up" data-move-rule="-1" data-rule-id="${esc(rule.id)}" ${index === 0 ? 'disabled' : ''}>↑</button>
                  <button type="button" title="Move down" data-move-rule="1" data-rule-id="${esc(rule.id)}" ${index === routing.rules.length - 1 ? 'disabled' : ''}>↓</button>
                </div>
                <input data-route-label value="${esc(rule.label)}" aria-label="Rule name" placeholder="Rule name">
                <input data-route-keywords value="${esc((rule.keywords || []).join(', '))}" aria-label="${esc(rule.label)} title keywords" placeholder="manager, director, vp">
                ${documentPicker(documents, rule.document_ids)}
                <div class="jaw-doc-rule-delete"><button type="button" data-delete-rule="${esc(rule.id)}" title="Delete rule">×</button></div>
              </div>`).join('') : '<div class="jaw-doc-no-rules">No rules yet. Add one, or use only the fallback.</div>'}
          </div>

          <div class="jaw-doc-fallback-row">
            <div class="jaw-doc-fallback-label"><b>Fallback</b><small>Used when no rule matches</small></div>
            ${documentPicker(documents, routing.default_document_ids, { fallback: true })}
          </div>

          <div class="jaw-doc-routing-note">Rules are deterministic and use the captured job title. Outputs can include both a resume and cover letter.</div>
          <div class="jaw-doc-prediction${predicted.warning ? ' warning' : ''}" data-route-prediction>${esc(predicted.text)}</div>

          <div class="jaw-doc-section-head compact manual"><div><h3>Generate specific</h3><span>Current Tracker job</span></div></div>
          <div class="jaw-doc-manual-grid">
            ${documents.length ? documents.map(document => `
              <button class="jaw-doc-manual-chip" type="button" data-generate-document="${esc(document.id)}" ${job ? '' : 'disabled'}>${esc(document.name || 'Document')}</button>`).join('') : '<div class="jaw-doc-empty">No Workbench Documents yet. Create one in Documents first.</div>'}
          </div>
        </div>
        <div class="jaw-doc-dialog-actions">
          <button class="jaw-doc-button" type="button" data-command-auto ${job ? '' : 'disabled'}>${predicted.count > 1 ? `Generate Auto · ${predicted.count}` : 'Generate Auto'}</button>
          <span class="spacer"></span>
          <button class="jaw-doc-button primary" type="button" data-command-save ${documents.length ? '' : 'disabled'}>Save Rules</button>
          <button class="jaw-doc-button" type="button" data-command-close>Close</button>
        </div>
      </div>`;

    dialog.querySelectorAll('[data-command-close]').forEach(button => button.addEventListener('click', () => dialog.close()));
    dialog.querySelector('[data-add-rule]')?.addEventListener('click', addRule);
    dialog.querySelectorAll('[data-delete-rule]').forEach(button => {
      button.addEventListener('click', () => deleteRule(button.dataset.deleteRule));
    });
    dialog.querySelectorAll('[data-move-rule]').forEach(button => {
      button.addEventListener('click', () => moveRule(button.dataset.ruleId, Number(button.dataset.moveRule)));
    });
    dialog.querySelectorAll('.jaw-doc-output-picker input[type="checkbox"]').forEach(input => {
      input.addEventListener('change', () => {
        updatePickerSummary(input.closest('.jaw-doc-output-picker'));
        refreshPrediction();
      });
    });
    dialog.querySelectorAll('.jaw-doc-output-menu').forEach(menu => {
      menu.addEventListener('toggle', () => {
        if (menu.matches(':popover-open')) positionOutputMenu(menu);
      });
    });
    dialog.querySelectorAll('[data-route-label],[data-route-keywords]').forEach(input => {
      input.addEventListener('input', refreshPrediction);
    });
    dialog.querySelector('[data-command-save]')?.addEventListener('click', () => saveCommandRouting());
    dialog.querySelector('[data-command-auto]')?.addEventListener('click', async () => {
      const saved = await saveCommandRouting({ rerender: false, silent: true });
      if (!saved) return;
      dialog.close();
      await generateForJob(state.job?.id || currentJobId());
    });
    dialog.querySelectorAll('[data-generate-document]').forEach(button => button.addEventListener('click', async () => {
      const documentId = button.dataset.generateDocument;
      dialog.close();
      await generateForJob(state.job?.id || currentJobId(), documentId);
    }));
  }

  async function saveCommandRouting({ rerender = true, silent = false } = {}) {
    if (!commandState) return false;
    const routing = readRoutingFromDialog();
    for (const [index, rule] of routing.rules.entries()) {
      if (!rule.keywords.length) {
        const row = ensureCommandDialog().querySelector(`[data-route-rule="${CSS.escape(rule.id)}"]`);
        row?.querySelector('[data-route-keywords]')?.focus();
        toast(`Rule ${index + 1} needs at least one title keyword`);
        return false;
      }
    }
    try {
      const payload = await postJson('/api/workbench/routing/save', {
        rules: routing.rules,
        default_document_ids: routing.default_document_ids
      });
      commandState.documents = payload.workbench?.documents || commandState.documents;
      commandState.routing = routingForDialog(payload.routing || routing);
      commandNotice = '';
      if (rerender) renderCommandDialog();
      if (!silent) toast('Document routing saved');
      return true;
    } catch (error) {
      toast(error.message);
      return false;
    }
  }

  async function openCommandDialog({ notice = '' } = {}) {
    const dialog = ensureCommandDialog();
    commandNotice = String(notice || '');
    commandState = null;
    renderCommandDialog();
    if (!dialog.open) dialog.showModal();
    try {
      const jobId = currentJobId();
      const statePromise = getJson('/api/workbench/state');
      const routingPromise = getJson('/api/workbench/routing');
      const jobPromise = jobId ? getJson(`/api/jobs/${jobId}`).catch(() => null) : Promise.resolve(null);
      const [payload, rawRouting, job] = await Promise.all([statePromise, routingPromise, jobPromise]);
      const documents = payload.workbench?.documents || [];
      if (!job && jobId) sessionStorage.removeItem(JOB_KEY);
      commandState = {
        documents,
        routing: routingForDialog(rawRouting),
        job
      };
      renderCommandDialog();
    } catch (error) {
      dialog.innerHTML = `<div class="jaw-doc-dialog-shell"><div class="jaw-doc-dialog-head"><strong>Document Routing</strong><span class="spacer"></span><button class="jaw-doc-x" type="button" data-command-close>×</button></div><div class="jaw-doc-dialog-body"><div class="jaw-doc-empty">${esc(error.message)}</div></div></div>`;
      dialog.querySelector('[data-command-close]')?.addEventListener('click', () => dialog.close());
    }
  }

  function registerCommandProviders() {
    if (!window.JawCommands?.register) return;
    window.JawCommands.register('jobsPage', () => openCommandDialog());
  }

  installJobTracking();
  registerCommandProviders();

  window.openTrackerDocuments = jobId => generateForJob(jobId);
  window.JawDocumentGeneration = {
    open: openCommandDialog,
    generateForJob,
    currentJobId
  };
})();
