(() => {
  const page = document.getElementById('documentsPage');
  if (!page || page.querySelector('.wb-shell')) return;

  page.querySelector('.document-shell')?.setAttribute('hidden', '');
  page.querySelector('.document-v2-shell')?.remove();

  const KINDS = ['template', 'section', 'function'];
  const LAYOUT_KEY = 'jaw.workbench.layout.v3';
  const OPERATION_PATHS = {
    checkpoint: '/api/workbench/checkpoint',
    save: '/api/workbench/save',
    meta: '/api/workbench/meta',
    link: '/api/workbench/link',
    delete: '/api/workbench/delete',
    'rename-symbol': '/api/workbench/rename-symbol',
    generate: '/api/workbench/generate',
    'open-output': '/api/workbench/open-output'
  };

  const sideHead = (key, title) => `
    <div class="wb-side-head" data-wb-side-head="${key}">
      <button class="wb-side-chevron" type="button" data-wb-side-toggle="${key}" aria-label="Toggle ${title}">▾</button>
      <span>${title}</span>
    </div>`;

  const shell = document.createElement('div');
  shell.className = 'wb-shell';
  shell.innerHTML = `
    <header class="wb-topbar">
      <div class="wb-top-left"><button class="wb-button primary" id="wbNewDocument">+ New Document</button></div>
      <div class="wb-document-tabs" id="wbDocumentTabs"></div>
      <div class="wb-top-right"><button class="wb-button" id="wbPreview" disabled>Preview</button><button class="wb-button primary" id="wbGenerate" disabled>Generate</button></div>
    </header>
    <div class="wb-layout">
      <aside class="wb-left" data-wb-side="left">
        <section class="wb-side-pane" data-wb-side-pane="explorer">${sideHead('explorer', 'EXPLORER')}<div class="wb-explorer" id="wbExplorer"></div></section>
        <section class="wb-side-pane" data-wb-side-pane="global-templates">${sideHead('global-templates', 'GLOBAL TEMPLATES')}<div class="wb-palette" id="wbGlobalTemplates"></div></section>
        <section class="wb-side-pane" data-wb-side-pane="inspector">${sideHead('inspector', 'INSPECTOR')}<div class="wb-inspector" id="wbInspector"></div></section>
        <section class="wb-side-pane" data-wb-side-pane="relationships">${sideHead('relationships', 'RELATIONSHIPS')}<div class="wb-side-content" id="wbRelationships"></div></section>
        <section class="wb-side-pane" data-wb-side-pane="metadata">${sideHead('metadata', 'METADATA')}<div class="wb-side-content" id="wbMetadata"></div></section>
      </aside>
      <main class="wb-center" id="wbCenter">
        ${KINDS.map(kind => `
          <section class="wb-editor-pane" data-wb-pane="${kind}">
            <div class="wb-pane-head">
              <button class="wb-pane-toggle" data-wb-toggle="${kind}" aria-label="Toggle ${kind}">▾</button>
              <span class="wb-pane-title">${kind === 'section' ? 'SECTIONS' : kind === 'function' ? 'FUNCTIONS' : 'TEMPLATE'}</span>
              <div class="wb-pane-tabs" data-wb-tabs="${kind}"></div>
            </div>
            <div class="wb-editor-body" data-wb-body="${kind}">
              <textarea class="wb-editor" data-wb-editor="${kind}" spellcheck="false"></textarea>
              <div class="wb-drop-caret" data-wb-drop-caret="${kind}" hidden></div>
            </div>
          </section>`).join('')}
      </main>
      <aside class="wb-right" data-wb-side="right">
        <section class="wb-right-pane" data-wb-side-pane="jaw">${sideHead('jaw', 'JAW OBJECTS')}<input class="wb-filter" id="wbJawFilter" placeholder="Search objects" autocomplete="off"><div class="wb-palette" id="wbJawObjects"></div></section>
        <section class="wb-right-pane" data-wb-side-pane="global-sections">${sideHead('global-sections', 'GLOBAL SECTIONS')}<input class="wb-filter" id="wbSectionFilter" placeholder="Search sections" autocomplete="off"><div class="wb-palette" id="wbGlobalSections"></div></section>
        <section class="wb-right-pane" data-wb-side-pane="global-functions">${sideHead('global-functions', 'GLOBAL FUNCTIONS')}<input class="wb-filter" id="wbFunctionFilter" placeholder="Search functions" autocomplete="off"><div class="wb-palette" id="wbGlobalFunctions"></div></section>
        <section class="wb-right-pane" data-wb-side-pane="orphans">${sideHead('orphans', 'ORPHANS')}<div class="wb-palette" id="wbOrphans"></div></section>
      </aside>
    </div>
    <footer class="wb-statusbar"><span class="wb-status" id="wbStatus"></span><div class="wb-status-actions"><button class="wb-status-button wb-status-output" id="wbStatusOutput" type="button"></button><button class="wb-status-button" id="wbStatusWrap" type="button">Wrap</button></div></footer>
    <div class="wb-quick" id="wbQuick" hidden><div class="wb-quick-box"><div class="wb-quick-title" id="wbQuickTitle"></div><input class="wb-quick-input" id="wbQuickInput" autocomplete="off" spellcheck="false"><div class="wb-quick-results" id="wbQuickResults"></div><div class="wb-quick-hint">↑↓ navigate · Enter select · Esc close</div></div></div>`;
  page.appendChild(shell);

  const els = {
    documentTabs: document.getElementById('wbDocumentTabs'), explorer: document.getElementById('wbExplorer'),
    globalTemplates: document.getElementById('wbGlobalTemplates'), inspector: document.getElementById('wbInspector'),
    relationships: document.getElementById('wbRelationships'), metadata: document.getElementById('wbMetadata'),
    status: document.getElementById('wbStatus'), statusOutput: document.getElementById('wbStatusOutput'),
    statusWrap: document.getElementById('wbStatusWrap'), center: document.getElementById('wbCenter'),
    left: shell.querySelector('.wb-left'), right: shell.querySelector('.wb-right'),
    jaw: document.getElementById('wbJawObjects'), globalSections: document.getElementById('wbGlobalSections'),
    globalFunctions: document.getElementById('wbGlobalFunctions'), orphans: document.getElementById('wbOrphans'),
    jawFilter: document.getElementById('wbJawFilter'), sectionFilter: document.getElementById('wbSectionFilter'),
    functionFilter: document.getElementById('wbFunctionFilter'), quick: document.getElementById('wbQuick'),
    quickTitle: document.getElementById('wbQuickTitle'), quickInput: document.getElementById('wbQuickInput'),
    quickResults: document.getElementById('wbQuickResults')
  };

  let state = { documents: [], resources: [], templates: [], relationships: {} };
  let activeDocumentId = null;
  let selectedResourceId = null;
  let selectedJawPath = null;
  let focusedEditorId = null;
  let openDocuments = [];
  const openTabs = { template: [], section: [], function: [] };
  const activeTabs = { template: null, section: null, function: null };
  const displayed = { template: null, section: null, function: null };
  const localBuffers = new Map();
  const checkpointTimers = new Map();
  const expanded = new Set();
  const collapsed = { template: false, section: false, function: false };
  const paneSizes = { template: 50, section: 25, function: 25 };
  const sideCollapsed = { explorer: false, 'global-templates': false, inspector: false, relationships: true, metadata: true, jaw: false, 'global-sections': false, 'global-functions': false, orphans: false };
  const sideSizes = { left: { explorer: 40, 'global-templates': 14, inspector: 24, relationships: 12, metadata: 10 }, right: { jaw: 37, 'global-sections': 21, 'global-functions': 21, orphans: 21 } };
  const sideWidths = { left: 245, right: 280 };
  const settings = { wordWrap: localStorage.getItem('jaw.workbench.wordWrap') !== 'false', outputDirectory: localStorage.getItem('jaw.workbench.outputDirectory') || '' };
  let resizing = null;
  let resizePending = null;
  let suppressCtrlClick = false;
  let dragGhost = null;
  let quickMode = null;
  let quickItems = [];
  let quickFiltered = [];
  let quickIndex = 0;
  let loading = null;
  const subscribers = new Set();

  const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
  const lower = value => String(value ?? '').trim().toLowerCase();
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

  async function request(path, body) {
    const options = body === undefined ? { cache: 'no-store' } : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
    const response = await fetch(path, options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
    return payload;
  }

  function payloadState(payload) { return payload?.state || payload?.workbench || null; }
  function documents() { return state.documents || []; }
  function resources() { return state.resources || []; }
  function documentById(id) { return documents().find(item => item.id === id) || null; }
  function resourceById(id) { return resources().find(item => item.id === id) || null; }
  function currentResource(kind) { return resourceById(activeTabs[kind]); }
  function editorContent(resource) { return localBuffers.has(resource?.id) ? localBuffers.get(resource.id) : String(resource?.editor_content ?? resource?.content ?? ''); }
  function isDirty(resource) { return Boolean(resource && (localBuffers.has(resource.id) || resource.dirty)); }
  function resourceTitle(resource) {
    if (!resource) return '';
    if (resource.kind === 'section' || resource.kind === 'function') {
      return String(resource.reference_symbol || resource.symbol || resource.kind);
    }
    return String(resource.name || resource.symbol || resource.kind);
  }

  function publicSnapshot() {
    return { state, activeDocumentId, selectedResourceId, activeTabs: { ...activeTabs }, openTabs: { template: [...openTabs.template], section: [...openTabs.section], function: [...openTabs.function] } };
  }

  function publish(reason = 'state') {
    const snapshot = publicSnapshot();
    for (const subscriber of [...subscribers]) {
      try { subscriber(snapshot, reason); } catch (error) { console.error(error); }
    }
    window.dispatchEvent(new CustomEvent('jaw:workbench-state', { detail: { snapshot, reason } }));
  }
  function subscribe(callback) { subscribers.add(callback); return () => subscribers.delete(callback); }
  function setStatus(text = '', kind = '') { els.status.textContent = text; els.status.className = `wb-status ${kind}`; }
  function outputDirectoryLabel() { return settings.outputDirectory || 'Downloads'; }

  function applySettings() {
    shell.classList.toggle('wb-word-wrap', settings.wordWrap);
    shell.querySelectorAll('.wb-editor').forEach(editor => { editor.wrap = settings.wordWrap ? 'soft' : 'off'; });
    els.statusWrap.classList.toggle('active', settings.wordWrap);
    els.statusWrap.textContent = settings.wordWrap ? 'Wrap: On' : 'Wrap: Off';
    els.statusOutput.textContent = `Output: ${outputDirectoryLabel()}`;
    els.statusOutput.title = outputDirectoryLabel();
  }

  function syncActiveTemplate() {
    const document = documentById(activeDocumentId);
    const templateId = document?.template_id || document?.template?.id || null;
    openTabs.template = templateId ? [templateId] : [];
    activeTabs.template = templateId;
  }

  function applyState(next, { reason = 'state' } = {}) {
    if (!next) return;
    state = next;
    const valid = new Set(resources().map(item => item.id));
    for (const id of [...localBuffers.keys()]) if (!valid.has(id)) localBuffers.delete(id);
    openDocuments = openDocuments.filter(id => documentById(id));
    if (activeDocumentId && !documentById(activeDocumentId)) activeDocumentId = null;
    for (const kind of KINDS) {
      openTabs[kind] = openTabs[kind].filter(id => valid.has(id));
      if (activeTabs[kind] && !valid.has(activeTabs[kind])) activeTabs[kind] = null;
      if (displayed[kind] && !valid.has(displayed[kind])) displayed[kind] = null;
    }
    if (activeDocumentId) syncActiveTemplate();
    renderChrome();
    publish(reason);
  }

  async function load() {
    if (loading) return loading;
    loading = (async () => {
      try {
        setStatus('Loading…');
        const payload = await request('/api/workbench/state');
        applyState(payload.workbench || { documents: [], resources: [], templates: [], relationships: {} }, { reason: 'load' });
        setStatus('');
        return state;
      } catch (error) {
        setStatus(error.message, 'error');
        els.explorer.innerHTML = `<div class="wb-empty error">${esc(error.message)}</div>`;
        throw error;
      } finally { loading = null; }
    })();
    return loading;
  }

  function openDocument(id, { render = true } = {}) {
    const document = documentById(id);
    if (!document) return;
    const changedDocument = activeDocumentId !== id;
    activeDocumentId = id;
    selectedJawPath = null;
    selectedResourceId = id;
    if (!openDocuments.includes(id)) openDocuments.push(id);
    expanded.add(id);
    syncActiveTemplate();
    if (changedDocument) {
      openTabs.section = [];
      openTabs.function = [];
      activeTabs.section = null;
      activeTabs.function = null;
      displayed.section = null;
      displayed.function = null;
    }
    collapsed.template = false;
    if (render) renderChrome();
    publish('document-selected');
  }

  function openResource(id, { render = true, focus = true } = {}) {
    const resource = resourceById(id);
    if (!resource) return;
    if (resource.kind === 'document') { openDocument(id, { render }); return; }
    if (resource.kind === 'template') {
      const document = documents().find(item => item.template_id === id);
      if (document && document.id !== activeDocumentId) openDocument(document.id, { render: false });
    }
    if (!openTabs[resource.kind]) return;
    if (!openTabs[resource.kind].includes(id)) openTabs[resource.kind].push(id);
    activeTabs[resource.kind] = id;
    collapsed[resource.kind] = false;
    selectedJawPath = null;
    selectedResourceId = id;
    if (render) renderChrome();
    publish('resource-selected');
    if (focus) requestAnimationFrame(() => shell.querySelector(`[data-wb-editor="${resource.kind}"]`)?.focus());
  }

  function inspectResource(id, { reason = 'resource-inspected' } = {}) {
    const resource = documentById(id) || resourceById(id);
    if (!resource) return;
    selectedJawPath = null;
    selectedResourceId = resource.id;
    renderExplorer();
    renderGlobalTemplates();
    renderSelectionPanels();
    publish(reason);
  }

  function closeDocument(id) {
    openDocuments = openDocuments.filter(item => item !== id);
    if (activeDocumentId === id) {
      activeDocumentId = openDocuments.at(-1) || null;
      selectedResourceId = activeDocumentId;
      openTabs.section = []; openTabs.function = [];
      activeTabs.section = null; activeTabs.function = null;
      displayed.section = null; displayed.function = null;
      if (activeDocumentId) syncActiveTemplate();
      else { openTabs.template = []; activeTabs.template = null; displayed.template = null; }
    }
    renderChrome(); publish('document-closed');
  }

  function closeResourceTab(kind, id) {
    openTabs[kind] = openTabs[kind].filter(item => item !== id);
    if (activeTabs[kind] === id) activeTabs[kind] = openTabs[kind].at(-1) || null;
    renderChrome(); publish('resource-closed');
  }

  function documentDirty(document) {
    if (isDirty(document.template)) return true;
    return (document.sections || []).some(section => isDirty(section) || (section.functions || []).some(isDirty));
  }

  function renderChrome() {
    renderDocumentTabs(); renderExplorer(); renderGlobalTemplates(); renderSelectionPanels();
    renderPaneTabs(); renderPalettes(); applyPaneLayout(); applySideLayout(); applySettings();
  }

  function renderDocumentTabs() {
    els.documentTabs.innerHTML = openDocuments.map(id => {
      const document = documentById(id);
      if (!document) return '';
      return `<button class="wb-doc-tab ${id === activeDocumentId ? 'active' : ''}" data-wb-doc-tab="${esc(id)}" title="${esc(document.name)}"><span>${esc(document.name || 'Document')}</span>${documentDirty(document) ? '<i class="wb-dirty">●</i>' : ''}<b data-wb-close-doc="${esc(id)}">×</b></button>`;
    }).join('');
  }

  function renderExplorer() {
    if (!documents().length) { els.explorer.innerHTML = '<div class="wb-empty">No Documents. Use + New Document.</div>'; return; }
    els.explorer.innerHTML = documents().map(renderDocumentTree).join('');
  }

  function renderDocumentTree(document) {
    const isOpen = expanded.has(document.id);
    const sections = document.sections || [];
    const orphanSections = (state.orphans || []).filter(item => item.kind === 'section' && item.owner_id === document.id);
    const sectionKey = `${document.id}:sections`;
    const orphanKey = `${document.id}:orphans`;
    return `<div class="wb-tree-document ${document.id === activeDocumentId ? 'active-doc' : ''}">
      <div class="wb-tree-row depth0 ${selectedResourceId === document.id ? 'selected' : ''}" data-wb-open-doc="${esc(document.id)}"><button class="wb-chevron" data-wb-expand="${esc(document.id)}">${isOpen ? '⌄' : '›'}</button><span class="wb-kind-dot document"></span><span class="wb-tree-label">${esc(document.name || 'Document')}</span>${documentDirty(document) ? '<i class="wb-dirty">●</i>' : ''}</div>
      ${isOpen ? `<div class="wb-tree-children">${document.template ? renderResourceRow(document.template, 1, 'Template') : ''}<div class="wb-tree-row depth1 folder"><button class="wb-chevron" data-wb-expand="${esc(sectionKey)}">${expanded.has(sectionKey) ? '⌄' : '›'}</button><span class="wb-tree-label">Sections</span><span class="wb-count">${sections.length}</span></div>${expanded.has(sectionKey) ? `<div class="wb-tree-children guide">${sections.map(renderSectionTree).join('') || '<div class="wb-tree-empty depth2">Empty</div>'}</div>` : ''}${orphanSections.length ? `<div class="wb-tree-row depth1 folder"><button class="wb-chevron" data-wb-expand="${esc(orphanKey)}">${expanded.has(orphanKey) ? '⌄' : '›'}</button><span class="wb-tree-label orphan-text">Orphans</span><span class="wb-count">${orphanSections.length}</span></div>${expanded.has(orphanKey) ? `<div class="wb-tree-children guide">${orphanSections.map(item => renderResourceRow(item, 2)).join('')}</div>` : ''}` : ''}</div>` : ''}
    </div>`;
  }

  function renderSectionTree(section) {
    const functions = section.functions || [];
    const key = `${section.id}:functions`;
    const leading = functions.length ? `<button class="wb-chevron" data-wb-expand="${esc(key)}">${expanded.has(key) ? '⌄' : '›'}</button>` : '<span class="wb-chevron placeholder"></span>';
    return `<div>${renderResourceRow(section, 2, null, leading)}${expanded.has(key) ? `<div class="wb-tree-children guide">${functions.map(fn => renderResourceRow(fn, 3)).join('')}</div>` : ''}</div>`;
  }

  function renderResourceRow(resource, depth, prefix = null, leading = null) {
    const classes = [resource.visibility === 'global' ? 'global' : 'private', resource.state === 'orphaned' ? 'orphan' : '', selectedResourceId === resource.id ? 'selected' : ''].filter(Boolean).join(' ');
    return `<div class="wb-tree-row depth${depth} ${classes}" data-wb-open-resource="${esc(resource.id)}">${leading ?? '<span class="wb-chevron placeholder"></span>'}<span class="wb-kind-dot ${esc(resource.kind)}"></span><span class="wb-tree-label">${prefix ? `${esc(prefix)} · ` : ''}${esc(resourceTitle(resource))}</span>${isDirty(resource) ? '<i class="wb-dirty">●</i>' : ''}</div>`;
  }

  function renderGlobalTemplates() {
    const templates = (state.templates || []).filter(item => item.visibility === 'global' && !item.settings?.system_template);
    els.globalTemplates.innerHTML = templates.map(template => {
      const usage = documents().filter(item => item.template_id === template.id).length;
      return `<div class="wb-palette-item template ${selectedResourceId === template.id ? 'selected' : ''}" data-wb-select-resource="${esc(template.id)}"><span>${esc(template.name || 'Template')}</span><small>${usage}</small></div>`;
    }).join('') || '<div class="wb-empty compact">Empty</div>';
  }

  function selectedResource() { return documentById(selectedResourceId) || resourceById(selectedResourceId); }

  function renderSelectionPanels() { renderInspector(); renderRelationshipsPanel(); renderMetadataPanel(); }

  function renderInspector() {
    if (selectedJawPath) { els.inspector.innerHTML = `<div class="wb-inspector-kind">JAW object</div><code class="wb-object-code">${esc(selectedJawPath)}</code>`; return; }
    const resource = selectedResource();
    if (!resource) { els.inspector.innerHTML = '<div class="wb-empty">Select a resource.</div>'; return; }
    const document = resource.kind === 'document' ? documentById(resource.id) : null;
    const shape = resource.settings?.content_shape || 'paragraphs';
    const templateUsageCount = resource.kind === 'template' ? documents().filter(item => item.template_id === resource.id).length : 0;
    const namedResource = resource.kind === 'document' || resource.kind === 'template';
    els.inspector.innerHTML = `
      <div class="wb-inspector-kind">${resource.kind === 'template' && resource.visibility === 'global' ? 'Global Template' : esc(resource.kind)}</div>
      ${namedResource ? `<label class="wb-field"><span>Name</span><input id="wbInspectorName" value="${esc(resource.name || '')}"></label>` : `<div class="wb-field"><span>Symbol</span><div class="wb-inspector-value"><code>${esc(resource.symbol || '—')}</code></div></div>`}
      ${document ? `<label class="wb-field"><span>Output</span><input id="wbInspectorOutput" value="${esc(document.output_pattern || '')}"></label><label class="wb-field"><span>Template</span><select id="wbInspectorTemplate">${(state.templates || []).map(template => `<option value="${esc(template.id)}" ${template.id === document.template_id ? 'selected' : ''}>${esc(template.name || 'Template')}</option>`).join('')}</select></label>` : ''}
      ${resource.kind === 'template' ? `<div class="wb-field"><span>Visibility</span><div class="wb-inspector-value">${esc(resource.visibility || 'private')}</div></div><div class="wb-field"><span>Used by</span><div class="wb-inspector-value">${templateUsageCount} Document${templateUsageCount === 1 ? '' : 's'}</div></div>` : ''}
      ${resource.kind === 'section' ? `<div class="wb-field"><span>Visibility</span><div class="wb-radio-row"><label><input type="radio" name="wbVisibility" value="private" ${resource.visibility === 'private' ? 'checked' : ''}> Private</label><label><input type="radio" name="wbVisibility" value="global" ${resource.visibility === 'global' ? 'checked' : ''}> Global</label></div></div><label class="wb-field"><span>Content Shape</span><select id="wbContentShape"><option value="paragraphs" ${shape === 'paragraphs' ? 'selected' : ''}>Paragraphs</option><option value="list" ${shape === 'list' ? 'selected' : ''}>List</option></select></label>` : ''}
      ${resource.kind === 'function' ? `<div class="wb-field"><span>Visibility</span><div class="wb-radio-row"><label><input type="radio" name="wbVisibility" value="private" ${resource.visibility === 'private' ? 'checked' : ''}> Private</label><label><input type="radio" name="wbVisibility" value="global" ${resource.visibility === 'global' ? 'checked' : ''}> Global</label></div></div>` : ''}`;
  }

  function resourceLabel(id) {
    const document = documentById(id);
    if (document) return document.name || id;
    const resource = resourceById(id);
    return resource ? resourceTitle(resource) : id;
  }
  function renderRelationshipsPanel() {
    const resource = selectedResource();
    if (!resource || selectedJawPath) { els.relationships.innerHTML = '<div class="wb-empty compact">No relationships</div>'; return; }
    const relation = state.relationships?.[resource.id] || { inbound: [], outbound: [] };
    const rows = [];
    for (const edge of relation.inbound || []) rows.push(`<div><span>Used by</span><code>${esc(edge.symbol)}</code><small>${esc(resourceLabel(edge.parent_id))}</small></div>`);
    for (const edge of relation.outbound || []) rows.push(`<div><span>Contains</span><code>${esc(edge.symbol)}</code><small>${esc(resourceLabel(edge.child_id))}</small></div>`);
    els.relationships.innerHTML = rows.length ? `<div class="wb-relations">${rows.join('')}</div>` : '<div class="wb-empty compact">No relationships</div>';
  }
  function renderMetadataPanel() {
    const resource = selectedResource();
    if (!resource || selectedJawPath) { els.metadata.innerHTML = selectedJawPath ? `<div class="wb-meta"><span>Path</span><code>${esc(selectedJawPath)}</code></div>` : '<div class="wb-empty compact">No metadata</div>'; return; }
    els.metadata.innerHTML = `<div class="wb-meta"><span>Symbol</span><code>${esc(resource.symbol || '—')}</code><span>Created</span><span>${esc(resource.created_at || '—')}</span><span>JID</span><code>${esc(resource.id)}</code></div>`;
  }

  function renderPaneTabs() { for (const kind of KINDS) renderPane(kind); }
  function renderPane(kind) {
    const pane = shell.querySelector(`[data-wb-pane="${kind}"]`);
    const tabs = pane?.querySelector(`[data-wb-tabs="${kind}"]`);
    const body = pane?.querySelector(`[data-wb-body="${kind}"]`);
    const editor = pane?.querySelector(`[data-wb-editor="${kind}"]`);
    const toggle = pane?.querySelector(`[data-wb-toggle="${kind}"]`);
    if (!pane || !tabs || !body || !editor || !toggle) return;
    tabs.innerHTML = openTabs[kind].map(id => {
      const resource = resourceById(id);
      if (!resource) return '';
      const title = resourceTitle(resource);
      return `<button class="wb-resource-tab ${id === activeTabs[kind] ? 'active' : ''}" data-wb-resource-tab="${esc(id)}" title="${esc(title)}"><span>${esc(title || kind)}</span>${isDirty(resource) ? '<i class="wb-dirty">●</i>' : ''}${kind === 'template' ? '' : `<b data-wb-close-tab="${esc(id)}">×</b>`}</button>`;
    }).join('');
    toggle.textContent = collapsed[kind] ? '▸' : '▾';
    body.hidden = collapsed[kind];
    const resource = currentResource(kind);
    if (!resource) { editor.value = ''; editor.disabled = true; editor.placeholder = `Open a ${kind}.`; displayed[kind] = null; editor.removeAttribute('data-resource-id'); return; }
    editor.disabled = false; editor.placeholder = '';
    if (displayed[kind] !== resource.id || editor.value !== editorContent(resource)) {
      editor.value = editorContent(resource); displayed[kind] = resource.id;
      const start = Number(resource.cursor_start || 0); const end = Number(resource.cursor_end ?? start);
      requestAnimationFrame(() => { try { editor.setSelectionRange(Math.min(start, editor.value.length), Math.min(end, editor.value.length)); } catch (_) { /* noop */ } });
    }
    editor.dataset.resourceId = resource.id;
  }

  function applyPaneLayout() {
    for (const kind of KINDS) {
      const pane = shell.querySelector(`[data-wb-pane="${kind}"]`); if (!pane) continue;
      pane.classList.toggle('collapsed', collapsed[kind]);
      pane.style.flex = collapsed[kind] ? '0 0 27px' : `${paneSizes[kind]} 1 0px`;
    }
  }
  function applySideLayout() {
    shell.style.setProperty('--wb-left-width', `${sideWidths.left}px`); shell.style.setProperty('--wb-right-width', `${sideWidths.right}px`);
    for (const side of ['left', 'right']) {
      const root = side === 'left' ? els.left : els.right;
      for (const pane of root.querySelectorAll('[data-wb-side-pane]')) {
        const key = pane.dataset.wbSidePane; const isCollapsed = Boolean(sideCollapsed[key]);
        pane.classList.toggle('collapsed', isCollapsed); pane.style.flex = isCollapsed ? '0 0 25px' : `${sideSizes[side][key] || 10} 1 0px`;
        const chevron = pane.querySelector(`[data-wb-side-toggle="${CSS.escape(key)}"]`); if (chevron) chevron.textContent = isCollapsed ? '▸' : '▾';
      }
    }
  }

  function flattenObject(prefix, value, output) {
    if (value && typeof value === 'object' && !Array.isArray(value)) { const keys = Object.keys(value); if (!keys.length) output.push({ path: prefix, insert: prefix }); for (const key of keys) flattenObject(`${prefix}.${key}`, value[key], output); return; }
    output.push({ path: prefix, insert: prefix });
  }
  function flattenJawEntries() {
    const entries = []; const roots = state.jaw_objects || {};
    for (const root of ['user', 'job', 'capabilities', 'system']) flattenObject(root, roots[root], entries);
    for (const method of roots.methods || []) entries.push({ path: method.name, insert: method.insert, method: true });
    return entries;
  }
  function renderJawObjects() {
    const filter = lower(els.jawFilter.value); const visible = flattenJawEntries().filter(item => !filter || lower(item.path).includes(filter));
    els.jaw.innerHTML = visible.map(item => `<div class="wb-palette-item jaw" draggable="true" data-wb-jaw="${esc(item.insert || item.path)}" data-wb-select-jaw="${esc(item.path)}"><span>${esc(item.path)}</span></div>`).join('') || '<div class="wb-empty compact">No matches</div>';
  }
  function renderResourcePalette(container, items, filterValue, paletteKind) {
    const filter = lower(filterValue); const visible = items.filter(item => !filter || lower(`${resourceTitle(item)} ${item.symbol || ''}`).includes(filter));
    container.innerHTML = visible.map(item => `<div class="wb-palette-item ${paletteKind} ${item.kind}" draggable="true" data-wb-drag-resource="${esc(item.id)}" data-wb-select-resource="${esc(item.id)}"><span>${esc(resourceTitle(item))}</span><small>${esc(item.kind === 'section' ? (item.settings?.content_shape || 'paragraphs') : item.kind)}</small></div>`).join('') || '<div class="wb-empty compact">Empty</div>';
  }
  function renderPalettes() { renderJawObjects(); renderResourcePalette(els.globalSections, state.global_sections || [], els.sectionFilter.value, 'section'); renderResourcePalette(els.globalFunctions, state.global_functions || [], els.functionFilter.value, 'function'); renderResourcePalette(els.orphans, state.orphans || [], '', 'orphan'); }

  function toggleExpanded(key) { if (!key) return; if (expanded.has(key)) expanded.delete(key); else expanded.add(key); renderExplorer(); }
  function handleExplorerClick(event) {
    const expand = event.target.closest('[data-wb-expand]');
    if (expand) { event.preventDefault(); event.stopPropagation(); toggleExpanded(expand.dataset.wbExpand); return; }
    const row = event.target.closest('.wb-tree-row'); if (!row || !els.explorer.contains(row) || row.classList.contains('folder')) return;
    if (row.dataset.wbOpenDoc) { if (!expanded.has(row.dataset.wbOpenDoc)) expanded.add(row.dataset.wbOpenDoc); openDocument(row.dataset.wbOpenDoc); return; }
    if (row.dataset.wbOpenResource) openResource(row.dataset.wbOpenResource);
  }

  function handleShellClick(event) {
    const docClose = event.target.closest('[data-wb-close-doc]'); if (docClose) { event.preventDefault(); event.stopPropagation(); closeDocument(docClose.dataset.wbCloseDoc); return; }
    const docTab = event.target.closest('[data-wb-doc-tab]'); if (docTab) { openDocument(docTab.dataset.wbDocTab); return; }
    const tabClose = event.target.closest('[data-wb-close-tab]'); if (tabClose) { event.preventDefault(); event.stopPropagation(); const pane = tabClose.closest('[data-wb-pane]'); if (pane) closeResourceTab(pane.dataset.wbPane, tabClose.dataset.wbCloseTab); return; }
    const resourceTab = event.target.closest('[data-wb-resource-tab]'); if (resourceTab) { openResource(resourceTab.dataset.wbResourceTab); return; }
    const selectResource = event.target.closest('[data-wb-select-resource]'); if (selectResource) { inspectResource(selectResource.dataset.wbSelectResource); return; }
    const selectJaw = event.target.closest('[data-wb-select-jaw]'); if (selectJaw) { selectedResourceId = null; selectedJawPath = selectJaw.dataset.wbSelectJaw; renderSelectionPanels(); publish('jaw-inspected'); return; }
    const sideToggle = event.target.closest('[data-wb-side-toggle]'); if (sideToggle) { const key = sideToggle.dataset.wbSideToggle; sideCollapsed[key] = !sideCollapsed[key]; applySideLayout(); saveLayout(); return; }
    const paneToggle = event.target.closest('[data-wb-toggle]'); if (paneToggle) { const kind = paneToggle.dataset.wbToggle; collapsed[kind] = !collapsed[kind]; applyPaneLayout(); saveLayout(); }
  }

  async function mutate(operation, values) {
    const path = OPERATION_PATHS[operation];
    if (!path) throw new Error(`Unsupported Workbench operation: ${operation}`);
    const payload = await request(path, values);
    const next = payloadState(payload);
    if (next) applyState(next, { reason: operation });
    return payload;
  }

  function referenceBindings(kind, editor) {
    if (!['template', 'section'].includes(kind) || !editor) return [];
    return window.JawWorkbenchReferenceIds?.checkpointBindings(kind, editor) || [];
  }

  function editorChanged(kind, editor) {
    const id = editor.dataset.resourceId; if (!id) return;
    localBuffers.set(id, editor.value); selectedResourceId = id; selectedJawPath = null; focusedEditorId = id;
    renderDocumentTabs(); renderPaneTabs(); renderSelectionPanels(); publish('editor-input'); scheduleCheckpoint(kind, editor, id);
  }
  function scheduleCheckpoint(kind, editor, resourceId) {
    clearTimeout(checkpointTimers.get(resourceId));
    const content = editor.value; const cursorStart = editor.selectionStart; const cursorEnd = editor.selectionEnd;
    checkpointTimers.set(resourceId, setTimeout(async () => {
      try {
        const reference_bindings = referenceBindings(kind, editor);
        await mutate('checkpoint', { resource_id: resourceId, content, cursor_start: cursorStart, cursor_end: cursorEnd, document_id: kind === 'template' ? activeDocumentId : undefined, reference_bindings });
        setStatus('Recovered', 'muted'); setTimeout(() => { if (els.status.textContent === 'Recovered') setStatus(''); }, 800);
      } catch (error) { setStatus(error.message, 'error'); }
    }, 450));
  }
  async function saveResource(resourceId) {
    const resource = resourceById(resourceId); if (!resource) return;
    clearTimeout(checkpointTimers.get(resourceId)); const content = localBuffers.has(resourceId) ? localBuffers.get(resourceId) : editorContent(resource);
    const editor = ['template', 'section'].includes(resource.kind)
      ? shell.querySelector(`[data-wb-editor="${resource.kind}"][data-resource-id="${CSS.escape(resourceId)}"]`)
      : null;
    const reference_bindings = referenceBindings(resource.kind, editor);
    try {
      setStatus('Saving…'); await mutate('save', { resource_id: resourceId, content, document_id: resource.kind === 'template' ? activeDocumentId : undefined, reference_bindings });
      localBuffers.delete(resourceId);
      setStatus('Saved', 'ok'); setTimeout(() => { if (els.status.textContent === 'Saved') setStatus(''); }, 900);
    } catch (error) { setStatus(error.message, 'error'); }
  }
  async function updateMeta(resourceId, values) {
    try { const payload = await mutate('meta', { resource_id: resourceId, ...values }); setStatus('Updated', 'ok'); setTimeout(() => { if (els.status.textContent === 'Updated') setStatus(''); }, 700); return payload; }
    catch (error) { setStatus(error.message, 'error'); renderSelectionPanels(); throw error; }
  }

  function templateUsage(templateId) { return documents().filter(item => item.template_id === templateId); }
  function chooseAbandonedTemplate(template) {
    return new Promise(resolve => {
      const overlay = document.createElement('div'); overlay.className = 'wb-template-choice-overlay';
      overlay.innerHTML = `<div class="wb-template-choice-card"><h3>Unused private Template</h3><p><strong>${esc(template.name || 'Template')}</strong> will no longer be used by a Document.</p><p>Keep it as a reusable Global Template, delete it, or cancel the change.</p><div class="wb-template-choice-actions"><button type="button" data-choice="cancel">Cancel</button><button type="button" data-choice="keep">Keep Global</button><button type="button" class="danger" data-choice="delete">Delete Template</button></div></div>`;
      shell.appendChild(overlay); overlay.querySelectorAll('[data-choice]').forEach(button => button.addEventListener('click', () => { const choice = button.dataset.choice; overlay.remove(); resolve(choice); }));
    });
  }
  async function changeDocumentTemplate(select) {
    const document = documentById(activeDocumentId); if (!document) return;
    const oldTemplate = resourceById(document.template_id); const nextTemplateId = String(select.value || ''); if (!nextTemplateId || nextTemplateId === document.template_id) return;
    let action = 'none';
    if (oldTemplate && oldTemplate.visibility === 'private' && templateUsage(oldTemplate.id).length === 1) { action = await chooseAbandonedTemplate(oldTemplate); if (action === 'cancel') { select.value = document.template_id; return; } }
    try {
      await updateMeta(document.id, { template_id: nextTemplateId });
      if (oldTemplate && action === 'keep') await mutate('meta', { resource_id: oldTemplate.id, visibility: 'global' });
      if (oldTemplate && action === 'delete') await mutate('delete', { resource_id: oldTemplate.id });
      syncActiveTemplate(); renderChrome();
    } catch (_) { select.value = document.template_id; }
  }
  function bindInspector() {
    els.inspector.addEventListener('change', event => {
      const resource = selectedResource(); if (!resource) return;
      if (event.target.id === 'wbInspectorName' && (resource.kind === 'document' || resource.kind === 'template')) updateMeta(resource.id, { name: event.target.value });
      else if (event.target.id === 'wbInspectorOutput') updateMeta(resource.id, { output_pattern: event.target.value });
      else if (event.target.id === 'wbInspectorTemplate') changeDocumentTemplate(event.target);
      else if (event.target.id === 'wbContentShape') updateMeta(resource.id, { content_shape: event.target.value });
      else if (event.target.name === 'wbVisibility' && event.target.checked) { const owner = resource.kind === 'section' ? activeDocumentId : activeTabs.section; updateMeta(resource.id, { visibility: event.target.value, owner_id: owner }); }
    });
  }

  function setDrag(event, payload, label = '') {
    event.dataTransfer.effectAllowed = 'copyMove'; event.dataTransfer.setData('application/x-jaw-workbench', JSON.stringify(payload));
    dragGhost?.remove(); dragGhost = document.createElement('div'); dragGhost.className = 'wb-drag-ghost'; dragGhost.textContent = String(label || payload.expression || 'JAW').trim(); document.body.appendChild(dragGhost);
    try { event.dataTransfer.setDragImage(dragGhost, 8, 0); } catch (_) { /* default */ }
    setTimeout(() => { dragGhost?.remove(); dragGhost = null; }, 0);
  }
  function parseDrag(event) { try { return JSON.parse(event.dataTransfer.getData('application/x-jaw-workbench') || '{}'); } catch (_) { return {}; } }
  async function handleDrop(kind, editor, event) {
    event.preventDefault();
    const drag = parseDrag(event); if (!drag.source) return;
    const cursor = editor.selectionStart;
    const oldSource = editor.value;
    let expression = '';
    let linkedReference = null;
    try {
      if (drag.source === 'jaw') expression = drag.expression;
      else if (drag.source === 'resource') {
        const child = resourceById(drag.resource_id); if (!child) return;
        if (kind === 'template' && child.kind !== 'section') throw new Error('Only Sections can be dropped into a Template');
        if (kind === 'section' && child.kind !== 'function') throw new Error('Only Functions can be dropped into a Section');
        if (kind === 'function') throw new Error('Functions are leaf resources; use JAW objects inside Functions');
        const parentId = kind === 'template' ? activeDocumentId : editor.dataset.resourceId;
        const payload = await mutate('link', { parent_id: parentId, child_id: child.id });
        const symbol = payload.symbol || child.symbol;
        linkedReference = payload.reference_id ? { id: payload.reference_id, child_id: child.id, symbol } : null;
        expression = symbol;
        if (child.kind === 'function') expression = `${expression}()`;
      }
      if (!expression) return;
      const inline = insideJinja(oldSource, cursor);
      const insertion = inline ? expression : `{{ ${expression} }}`;
      editor.setRangeText(insertion, cursor, cursor, 'end');
      const symbol = linkedReference?.symbol || '';
      const symbolStart = symbol ? cursor + (inline ? 0 : 3) : null;
      window.JawWorkbenchReferenceIds?.applyProgrammaticEdit(kind, editor, {
        oldSource,
        start: cursor,
        end: cursor,
        newEnd: cursor + insertion.length,
        reference: linkedReference,
        symbol,
        symbolStart,
        symbolEnd: symbolStart === null ? null : symbolStart + symbol.length,
        resourceId: linkedReference?.child_id || '',
      });
      editor.dispatchEvent(new Event('input', { bubbles: true }));
    } catch (error) { setStatus(error.message, 'error'); }
  }
  function insideJinja(text, cursor) { const prefix = text.slice(0, cursor); const open = Math.max(prefix.lastIndexOf('{{'), prefix.lastIndexOf('{%')); const close = Math.max(prefix.lastIndexOf('}}'), prefix.lastIndexOf('%}')); return open > close; }
  function navigateEditorSymbol(kind, editor) {
    if (!['template', 'section'].includes(kind)) return;
    const edge = window.JawWorkbenchReferenceIds?.referenceAt(
      kind,
      editor,
      Number(editor.selectionStart || 0),
    )?.reference;
    if (edge?.child_id) openResource(edge.child_id);
  }
  function bindEditors() {
    for (const kind of KINDS) {
      const editor = shell.querySelector(`[data-wb-editor="${kind}"]`); if (!editor) continue;
      editor.addEventListener('focus', () => { focusedEditorId = editor.dataset.resourceId || null; });
      editor.addEventListener('input', () => editorChanged(kind, editor));
      editor.addEventListener('click', event => {
        if (suppressCtrlClick) { event.preventDefault(); event.stopPropagation(); return; }
        if (event.ctrlKey || event.metaKey) navigateEditorSymbol(kind, editor);
      });
      editor.addEventListener('dragover', event => { event.preventDefault(); event.dataTransfer.dropEffect = 'copy'; });
      editor.addEventListener('drop', event => handleDrop(kind, editor, event));
    }
    shell.addEventListener('dragstart', event => {
      const jaw = event.target.closest('[data-wb-jaw]'); if (jaw) setDrag(event, { source: 'jaw', expression: jaw.dataset.wbJaw }, jaw.textContent);
      const resource = event.target.closest('[data-wb-drag-resource]'); if (resource) setDrag(event, { source: 'resource', resource_id: resource.dataset.wbDragResource }, resource.textContent);
    });
  }

  async function createDocument() {
    const used = new Set(documents().map(item => lower(item.name))); let name = 'Document'; let index = 2; while (used.has(lower(name))) name = `Document ${index++}`;
    try {
      setStatus('Creating…'); const payload = await request('/api/workbench/documents/create', { name }); const next = payload.workbench;
      if (next) applyState(next, { reason: 'document-created' }); const created = payload.document || next?.documents?.find(item => item.name === name && !openDocuments.includes(item.id)) || next?.documents?.at(-1);
      if (created) openDocument(created.id); setStatus('');
    } catch (error) { setStatus(error.message, 'error'); }
  }
  function selectJaw(path) { selectedResourceId = null; selectedJawPath = path; renderSelectionPanels(); publish('jaw-inspected'); }

  function fuzzyScore(query, text) {
    const q = lower(query), t = lower(text); if (!q) return 0; const direct = t.indexOf(q); if (direct >= 0) return 1000 - direct * 2 - (t.length - q.length);
    let qi = 0, score = 0, last = -2; for (let ti = 0; ti < t.length && qi < q.length; ti += 1) { if (t[ti] !== q[qi]) continue; score += ti === last + 1 ? 10 : 3; last = ti; qi += 1; }
    return qi === q.length ? score - t.length * 0.01 : Number.NEGATIVE_INFINITY;
  }
  function quickResources() {
    const items = []; for (const document of documents()) items.push({ label: document.name || 'Document', detail: 'Document', type: 'document', id: document.id });
    for (const resource of resources()) if (resource.kind !== 'document') items.push({ label: resourceTitle(resource), detail: resource.kind, type: 'resource', id: resource.id });
    for (const jaw of flattenJawEntries()) items.push({ label: jaw.path, detail: 'JAW object', type: 'jaw', path: jaw.path }); return items;
  }
  function quickSettings() {
    return [
      { label: 'Go to Item', detail: 'Documents, resources, and JAW objects', action: 'go-to-item' },
      { label: 'Document Routing', detail: 'Job document rules and manual generation', action: 'document-routing' },
      { label: `Word Wrap: ${settings.wordWrap ? 'On' : 'Off'}`, detail: 'Toggle editor word wrapping', action: 'word-wrap' },
      { label: 'Output Directory', detail: outputDirectoryLabel(), action: 'output-directory' },
      { label: 'Reset Layout', detail: 'Reset Workbench panes', action: 'reset-layout' }
    ];
  }
  function openQuick(mode = 'settings') { quickMode = mode; quickItems = mode === 'items' ? quickResources() : quickSettings(); quickIndex = 0; els.quickTitle.textContent = mode === 'items' ? 'Go to Item' : 'Command Palette'; els.quickInput.value = ''; els.quick.hidden = false; renderQuick(); requestAnimationFrame(() => els.quickInput.focus()); }
  function closeQuick() { els.quick.hidden = true; quickMode = null; }
  function renderQuick() {
    const query = els.quickInput.value; quickFiltered = quickItems.map(item => ({ item, score: fuzzyScore(query, `${item.label} ${item.detail || ''}`) })).filter(entry => !query || Number.isFinite(entry.score)).sort((a, b) => b.score - a.score).slice(0, 40).map(entry => entry.item);
    quickIndex = clamp(quickIndex, 0, Math.max(0, quickFiltered.length - 1)); els.quickResults.innerHTML = quickFiltered.map((item, index) => `<button class="wb-quick-row ${index === quickIndex ? 'active' : ''}" data-wb-quick-index="${index}"><span>${esc(item.label)}</span><small>${esc(item.detail || '')}</small></button>`).join('') || '<div class="wb-empty compact">No matches</div>';
  }
  function chooseQuickRow() {
    const item = quickFiltered[quickIndex]; if (!item) return; const mode = quickMode; closeQuick();
    if (mode === 'settings') {
      if (item.action === 'go-to-item') openQuick('items');
      else if (item.action === 'document-routing') window.JawDocumentGeneration?.open?.();
      else if (item.action === 'word-wrap') { settings.wordWrap = !settings.wordWrap; localStorage.setItem('jaw.workbench.wordWrap', String(settings.wordWrap)); applySettings(); }
      else if (item.action === 'output-directory') changeOutputDirectory();
      else if (item.action === 'reset-layout') resetLayout();
      return;
    }
    if (item.type === 'document') openDocument(item.id); else if (item.type === 'resource') openResource(item.id); else if (item.type === 'jaw') selectJaw(item.path);
  }
  function changeOutputDirectory() {
    const value = window.prompt('Generated document output directory. Use Downloads for the default, or enter an absolute path.', outputDirectoryLabel()); if (value === null) return;
    const trimmed = String(value).trim(); settings.outputDirectory = !trimmed || lower(trimmed) === 'downloads' ? '' : trimmed;
    if (settings.outputDirectory) localStorage.setItem('jaw.workbench.outputDirectory', settings.outputDirectory); else localStorage.removeItem('jaw.workbench.outputDirectory'); applySettings();
  }

  function saveLayout() { try { localStorage.setItem(LAYOUT_KEY, JSON.stringify({ paneSizes, sideSizes, sideWidths, collapsed, sideCollapsed })); } catch (_) { /* noop */ } }
  function restoreLayout() {
    try {
      const saved = JSON.parse(localStorage.getItem(LAYOUT_KEY) || '{}'); if (saved.paneSizes) Object.assign(paneSizes, saved.paneSizes); if (saved.sideWidths) Object.assign(sideWidths, saved.sideWidths); if (saved.collapsed) Object.assign(collapsed, saved.collapsed); if (saved.sideCollapsed) Object.assign(sideCollapsed, saved.sideCollapsed);
      for (const side of ['left', 'right']) if (saved.sideSizes?.[side]) Object.assign(sideSizes[side], saved.sideSizes[side]);
    } catch (_) { /* noop */ }
  }
  function resetLayout() {
    Object.assign(paneSizes, { template: 50, section: 25, function: 25 }); Object.assign(sideWidths, { left: 245, right: 280 }); Object.assign(collapsed, { template: false, section: false, function: false });
    Object.assign(sideCollapsed, { explorer: false, 'global-templates': false, inspector: false, relationships: true, metadata: true, jaw: false, 'global-sections': false, 'global-functions': false, orphans: false });
    Object.assign(sideSizes.left, { explorer: 40, 'global-templates': 14, inspector: 24, relationships: 12, metadata: 10 }); Object.assign(sideSizes.right, { jaw: 37, 'global-sections': 21, 'global-functions': 21, orphans: 21 }); applyPaneLayout(); applySideLayout(); saveLayout();
  }

  function pointInside(rect, x, y, pad = 0) { return x >= rect.left - pad && x <= rect.right + pad && y >= rect.top - pad && y <= rect.bottom + pad; }
  function editorResizeZone(event) {
    if (!(event.ctrlKey || event.metaKey)) return null;
    const body = event.target.closest('.wb-editor-body');
    if (!body || !els.center.contains(body)) return null;
    const pane = body.closest('[data-wb-pane]');
    const kind = pane?.dataset.wbPane;
    if (!pane || !KINDS.includes(kind) || collapsed[kind]) return null;
    if (kind === 'template') {
      if (collapsed.section) return null;
      return { type: 'center', boundary: 'template-section', kind, cursor: 'ns-resize' };
    }
    if (kind === 'function') {
      if (collapsed.section) return null;
      return { type: 'center', boundary: 'section-function', kind, cursor: 'ns-resize' };
    }
    const rect = pane.getBoundingClientRect();
    const upperHalf = event.clientY < rect.top + rect.height / 2;
    if (upperHalf) {
      if (collapsed.template) return null;
      return { type: 'center', boundary: 'template-section', kind, cursor: 'ns-resize' };
    }
    if (collapsed.function) return null;
    return { type: 'center', boundary: 'section-function', kind, cursor: 'ns-resize' };
  }
  function detectResizeZone(event) {
    const editorZone = editorResizeZone(event);
    if (editorZone) return editorZone;
    const x = event.clientX, y = event.clientY, hit = 6;
    for (const side of ['left', 'right']) {
      const root = side === 'left' ? els.left : els.right, rect = root.getBoundingClientRect(); if (!pointInside(rect, x, y, hit)) continue;
      const widthEdge = side === 'left' ? rect.right : rect.left; if (Math.abs(x - widthEdge) <= hit) return { type: 'side-width', side, cursor: 'ew-resize' };
      const panes = [...root.querySelectorAll('[data-wb-side-pane]')]; for (let index = 0; index < panes.length - 1; index += 1) { const first = panes[index], second = panes[index + 1], firstKey = first.dataset.wbSidePane, secondKey = second.dataset.wbSidePane; if (sideCollapsed[firstKey] || sideCollapsed[secondKey]) continue; if (Math.abs(y - first.getBoundingClientRect().bottom) <= hit) return { type: 'side-height', side, firstKey, secondKey, cursor: 'ns-resize' }; }
    }
    return null;
  }
  function resizeSnapshot(zone, event) {
    const editor = zone.type === 'center' ? event.target.closest('.wb-editor') : null;
    return {
      ...zone,
      startX: event.clientX,
      startY: event.clientY,
      paneStart: { ...paneSizes },
      sideStart: zone.side ? { ...sideSizes[zone.side] } : null,
      widthStart: zone.side ? sideWidths[zone.side] : null,
      editor,
      selectionStart: editor?.selectionStart ?? null,
      selectionEnd: editor?.selectionEnd ?? null
    };
  }
  function activateResize(candidate) {
    resizing = candidate;
    if (resizing.editor && resizing.selectionStart !== null) {
      try { resizing.editor.setSelectionRange(resizing.selectionStart, resizing.selectionEnd ?? resizing.selectionStart); } catch (_) { /* noop */ }
    }
    document.body.classList.add('wb-resizing'); document.body.style.cursor = candidate.cursor;
  }
  function beginResize(event) {
    if (event.button !== 0 || event.target.closest('button,input,select,label')) return;
    const zone = detectResizeZone(event); if (!zone) return;
    const candidate = resizeSnapshot(zone, event);
    if (zone.type === 'center') { resizePending = candidate; return; }
    event.preventDefault(); activateResize(candidate);
  }
  function resizeMove(event) {
    if (resizePending) {
      if (!(event.buttons & 1)) { resizePending = null; return; }
      if (Math.hypot(event.clientX - resizePending.startX, event.clientY - resizePending.startY) < 4) return;
      const candidate = resizePending; resizePending = null; activateResize(candidate);
    }
    if (!resizing) return; event.preventDefault();
    if (resizing.type === 'center') {
      const height = Math.max(1, els.center.getBoundingClientRect().height), delta = (event.clientY - resizing.startY) / height * 100;
      if (resizing.boundary === 'template-section') { const total = resizing.paneStart.template + resizing.paneStart.section; paneSizes.template = clamp(resizing.paneStart.template + delta, 8, total - 8); paneSizes.section = total - paneSizes.template; }
      else { const total = resizing.paneStart.section + resizing.paneStart.function; paneSizes.section = clamp(resizing.paneStart.section + delta, 8, total - 8); paneSizes.function = total - paneSizes.section; } applyPaneLayout();
    } else if (resizing.type === 'side-width') { const delta = event.clientX - resizing.startX; sideWidths[resizing.side] = clamp(resizing.widthStart + delta * (resizing.side === 'left' ? 1 : -1), 170, 460); applySideLayout(); }
    else if (resizing.type === 'side-height') { const root = resizing.side === 'left' ? els.left : els.right, height = Math.max(1, root.getBoundingClientRect().height), delta = (event.clientY - resizing.startY) / height * 100, total = resizing.sideStart[resizing.firstKey] + resizing.sideStart[resizing.secondKey]; sideSizes[resizing.side][resizing.firstKey] = clamp(resizing.sideStart[resizing.firstKey] + delta, 6, total - 6); sideSizes[resizing.side][resizing.secondKey] = total - sideSizes[resizing.side][resizing.firstKey]; applySideLayout(); }
  }
  function endResize() {
    if (resizePending) { resizePending = null; return; }
    if (!resizing) return;
    const suppressClick = resizing.type === 'center';
    resizing = null; document.body.classList.remove('wb-resizing'); document.body.style.cursor = ''; saveLayout();
    if (suppressClick) { suppressCtrlClick = true; setTimeout(() => { suppressCtrlClick = false; }, 0); }
  }
  function updateVerticalResizeCue(event) { shell.classList.toggle('wb-vertical-resize-ready', Boolean(event.ctrlKey || event.metaKey)); }
  function clearVerticalResizeCue() { shell.classList.remove('wb-vertical-resize-ready'); resizePending = null; }

  function bind() {
    document.getElementById('wbNewDocument').addEventListener('click', createDocument); els.explorer.addEventListener('click', handleExplorerClick); shell.addEventListener('click', handleShellClick); bindInspector(); bindEditors();
    els.jawFilter.addEventListener('input', renderJawObjects); els.sectionFilter.addEventListener('input', renderPalettes); els.functionFilter.addEventListener('input', renderPalettes);
    els.statusWrap.addEventListener('click', () => { settings.wordWrap = !settings.wordWrap; localStorage.setItem('jaw.workbench.wordWrap', String(settings.wordWrap)); applySettings(); }); els.statusOutput.addEventListener('click', changeOutputDirectory);
    els.quickInput.addEventListener('input', () => { quickIndex = 0; renderQuick(); });
    els.quickInput.addEventListener('keydown', event => { if (event.key === 'ArrowDown') { event.preventDefault(); quickIndex = clamp(quickIndex + 1, 0, Math.max(0, quickFiltered.length - 1)); renderQuick(); } else if (event.key === 'ArrowUp') { event.preventDefault(); quickIndex = clamp(quickIndex - 1, 0, Math.max(0, quickFiltered.length - 1)); renderQuick(); } else if (event.key === 'Enter') { event.preventDefault(); chooseQuickRow(); } else if (event.key === 'Escape') { event.preventDefault(); closeQuick(); } });
    els.quickResults.addEventListener('mousedown', event => { const row = event.target.closest('[data-wb-quick-index]'); if (!row) return; event.preventDefault(); quickIndex = Number(row.dataset.wbQuickIndex || 0); chooseQuickRow(); }); els.quick.addEventListener('mousedown', event => { if (event.target === els.quick) closeQuick(); });
    document.addEventListener('keydown', event => { updateVerticalResizeCue(event); const command = event.ctrlKey || event.metaKey; if (event.key === 'Escape' && !els.quick.hidden) { event.preventDefault(); closeQuick(); return; } if (command && event.key.toLowerCase() === 's') { event.preventDefault(); const target = focusedEditorId && resourceById(focusedEditorId); if (target) saveResource(target.id); } });
    document.addEventListener('keyup', updateVerticalResizeCue); window.addEventListener('blur', clearVerticalResizeCue);
    shell.addEventListener('pointerdown', beginResize); window.addEventListener('pointermove', resizeMove); window.addEventListener('pointerup', endResize); window.addEventListener('pointercancel', endResize);
  }

  restoreLayout(); bind(); applyPaneLayout(); applySideLayout(); applySettings();

  window.JawWorkbenchStore = { getState: () => state, getSnapshot: publicSnapshot, getActiveDocumentId: () => activeDocumentId, getSelectedResourceId: () => selectedResourceId, subscribe, replace(next, reason = 'external') { applyState(next, { reason }); } };
  window.JawDocumentWorkbench = { load, openQuick, changeOutputDirectory, openDocument, openResource, inspectResource, mutate, applyPayload(payload, reason = 'external') { const next = payloadState(payload); if (next) applyState(next, { reason }); } };
  load().catch(() => {});
})();