(() => {
  const shell = document.querySelector('.wb-shell');
  const store = window.JawWorkbenchStore;
  const workbench = window.JawDocumentWorkbench;
  if (!shell || !store || !workbench || window.JawWorkbenchWorkspace) return;

  // Session-only workspace state. Deliberately not persisted to SQLite,
  // localStorage, or sessionStorage: each Document gets its own lower editor
  // tabs for the lifetime of this browser/JAW session only.
  const documentWorkspaces = new Map();
  const originalOpenDocument = workbench.openDocument.bind(workbench);
  const originalOpenResource = workbench.openResource.bind(workbench);
  const originalInspectResource = workbench.inspectResource.bind(workbench);
  let lastSnapshot = store.getSnapshot();
  let restoring = false;
  let pruning = false;
  let contextHint = null;

  function state() { return store.getState() || {}; }
  function documentById(id) {
    return (state().documents || []).find(item => item.id === id) || null;
  }
  function resourceById(id) {
    return (state().resources || []).find(item => item.id === id) || null;
  }

  function graphFor(documentId) {
    const document = documentById(documentId);
    const sectionIds = new Set();
    const functionIds = new Set();
    const functionParents = new Map();
    if (!document) {
      return { document: null, templateId: '', sectionIds, functionIds, functionParents };
    }

    for (const section of document.sections || []) {
      sectionIds.add(section.id);
      for (const fn of section.functions || []) {
        functionIds.add(fn.id);
        const parents = functionParents.get(fn.id) || [];
        parents.push(section.id);
        functionParents.set(fn.id, parents);
      }
    }
    return {
      document,
      templateId: document.template_id || document.template?.id || '',
      sectionIds,
      functionIds,
      functionParents,
    };
  }

  function emptyWorkspace() {
    return {
      sectionTabs: [],
      functionTabs: [],
      activeSection: null,
      activeFunction: null,
    };
  }

  function normalizedWorkspace(documentId, value) {
    const graph = graphFor(documentId);
    const workspace = value || emptyWorkspace();
    const sectionTabs = (workspace.sectionTabs || []).filter(id => graph.sectionIds.has(id));
    const functionTabs = (workspace.functionTabs || []).filter(id => graph.functionIds.has(id));
    const activeSection = sectionTabs.includes(workspace.activeSection)
      ? workspace.activeSection
      : sectionTabs.at(-1) || null;
    const activeFunction = functionTabs.includes(workspace.activeFunction)
      ? workspace.activeFunction
      : functionTabs.at(-1) || null;
    return { sectionTabs, functionTabs, activeSection, activeFunction };
  }

  function rememberSnapshot(snapshot) {
    const documentId = snapshot?.activeDocumentId;
    if (!documentId || !documentById(documentId)) return;
    documentWorkspaces.set(documentId, normalizedWorkspace(documentId, {
      sectionTabs: [...(snapshot.openTabs?.section || [])],
      functionTabs: [...(snapshot.openTabs?.function || [])],
      activeSection: snapshot.activeTabs?.section || null,
      activeFunction: snapshot.activeTabs?.function || null,
    }));
  }

  function reconcileWorkspaces() {
    const validDocuments = new Set((state().documents || []).map(item => item.id));
    for (const documentId of [...documentWorkspaces.keys()]) {
      if (!validDocuments.has(documentId)) {
        documentWorkspaces.delete(documentId);
        continue;
      }
      documentWorkspaces.set(
        documentId,
        normalizedWorkspace(documentId, documentWorkspaces.get(documentId)),
      );
    }
  }

  function contextsFor(resourceId) {
    const resource = resourceById(resourceId);
    if (!resource) return [];
    const contexts = [];
    for (const document of state().documents || []) {
      const graph = graphFor(document.id);
      if (resource.kind === 'template' && graph.templateId === resourceId) {
        contexts.push({ documentId: document.id, sectionId: null });
        continue;
      }
      if (resource.kind === 'section' && graph.sectionIds.has(resourceId)) {
        contexts.push({ documentId: document.id, sectionId: resourceId });
        continue;
      }
      if (resource.kind === 'function' && graph.functionIds.has(resourceId)) {
        for (const sectionId of graph.functionParents.get(resourceId) || []) {
          contexts.push({ documentId: document.id, sectionId });
        }
      }
    }
    return contexts;
  }

  function openDocumentIds() {
    return [...shell.querySelectorAll('[data-wb-doc-tab]')]
      .map(tab => tab.dataset.wbDocTab)
      .filter(Boolean);
  }

  function resolveContext(resourceId, options = {}) {
    const contexts = contextsFor(resourceId);
    if (!contexts.length) return null;

    const explicitDocumentId = String(options.documentId || '').trim();
    const explicitSectionId = String(options.sectionId || '').trim();
    if (explicitDocumentId) {
      const exact = contexts.find(context => (
        context.documentId === explicitDocumentId
        && (!explicitSectionId || context.sectionId === explicitSectionId)
      ));
      if (exact) return exact;
      const sameDocument = contexts.find(context => context.documentId === explicitDocumentId);
      // Explicit Explorer context must never fall through to a different Document.
      return sameDocument || null;
    }

    if (contextHint?.resourceId === resourceId) {
      const hinted = contexts.find(context => (
        context.documentId === contextHint.documentId
        && (!contextHint.sectionId || context.sectionId === contextHint.sectionId)
      ));
      contextHint = null;
      if (hinted) return hinted;
    }

    const snapshot = store.getSnapshot();
    const activeDocumentId = snapshot.activeDocumentId || '';
    const activeSectionId = snapshot.activeTabs?.section || '';
    const exactActive = contexts.find(context => (
      context.documentId === activeDocumentId
      && (!context.sectionId || context.sectionId === activeSectionId)
    ));
    if (exactActive) return exactActive;

    const sameActiveDocument = contexts.find(context => context.documentId === activeDocumentId);
    if (sameActiveDocument) return sameActiveDocument;

    for (const documentId of openDocumentIds()) {
      const openContext = contexts.find(context => context.documentId === documentId);
      if (openContext) return openContext;
    }
    return contexts[0];
  }

  function closeTab(kind, resourceId) {
    const close = shell.querySelector(
      `[data-wb-pane="${kind}"] [data-wb-close-tab="${CSS.escape(String(resourceId))}"]`
    );
    if (!close) return false;
    close.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    return true;
  }

  function pruneCurrentWorkspace(snapshot) {
    const documentId = snapshot?.activeDocumentId;
    if (!documentId) return;
    const graph = graphFor(documentId);
    const invalidFunctions = (snapshot.openTabs?.function || [])
      .filter(id => !graph.functionIds.has(id));
    const invalidSections = (snapshot.openTabs?.section || [])
      .filter(id => !graph.sectionIds.has(id));
    if (!invalidFunctions.length && !invalidSections.length) return;

    pruning = true;
    try {
      // Children first keeps the visual ripple aligned with the graph branch.
      for (const id of invalidFunctions) closeTab('function', id);
      for (const id of invalidSections) closeTab('section', id);
    } finally {
      pruning = false;
    }
    rememberSnapshot(store.getSnapshot());
  }

  function restoreWorkspace(documentId) {
    const workspace = documentWorkspaces.get(documentId);
    if (!workspace || store.getActiveDocumentId() !== documentId) return;
    const normalized = normalizedWorkspace(documentId, workspace);
    documentWorkspaces.set(documentId, normalized);
    if (!normalized.sectionTabs.length && !normalized.functionTabs.length) return;

    restoring = true;
    try {
      const snapshot = store.getSnapshot();
      const currentSections = new Set(snapshot.openTabs?.section || []);
      const currentFunctions = new Set(snapshot.openTabs?.function || []);

      for (const id of normalized.sectionTabs) {
        if (!currentSections.has(id)) {
          originalOpenResource(id, { render: false, focus: false });
          currentSections.add(id);
        }
      }
      for (const id of normalized.functionTabs) {
        if (!currentFunctions.has(id)) {
          originalOpenResource(id, { render: false, focus: false });
          currentFunctions.add(id);
        }
      }

      if (normalized.activeSection) {
        originalOpenResource(normalized.activeSection, { render: false, focus: false });
      }
      if (normalized.activeFunction) {
        originalOpenResource(normalized.activeFunction, { render: true, focus: false });
      } else if (normalized.activeSection) {
        originalOpenResource(normalized.activeSection, { render: true, focus: false });
      } else if (normalized.functionTabs.length) {
        originalOpenResource(normalized.functionTabs.at(-1), { render: true, focus: false });
      }
    } finally {
      restoring = false;
    }
    rememberSnapshot(store.getSnapshot());
  }

  function openDocument(documentId, options = {}) {
    rememberSnapshot(store.getSnapshot());
    return originalOpenDocument(documentId, options);
  }

  function focusEditor(kind, focus = true) {
    if (!focus) return;
    requestAnimationFrame(() => {
      shell.querySelector(`[data-wb-editor="${kind}"]`)?.focus({ preventScroll: true });
    });
  }

  function openResource(resourceId, options = {}) {
    const resource = resourceById(resourceId);
    if (!resource) return originalOpenResource(resourceId, options);
    if (resource.kind === 'document') return openDocument(resourceId, options);

    const context = resolveContext(resourceId, options);
    if (!context) {
      // Staged/unattached resources are inspectable but are not part of a
      // Document workspace until the graph reference is restored.
      originalInspectResource(resourceId, { reason: 'workspace-resource-inspected' });
      return;
    }

    if (store.getActiveDocumentId() !== context.documentId) {
      rememberSnapshot(store.getSnapshot());
      originalOpenDocument(context.documentId, { render: true });
    }

    if (resource.kind === 'template') {
      // A Global Template may be shared by several Documents. The Template ID
      // alone is therefore not enough context; keep the explicitly/currently
      // resolved Document active and inspect its already-synchronized Template.
      originalInspectResource(resourceId, { reason: 'workspace-template-selected' });
      focusEditor('template', options.focus !== false);
      return;
    }

    if (resource.kind === 'function' && context.sectionId) {
      originalOpenResource(context.sectionId, { render: false, focus: false });
    }
    return originalOpenResource(resourceId, options);
  }

  function explorerContext(row, resource) {
    const tree = row.closest('.wb-tree-document');
    const documentRow = tree?.querySelector(':scope > .wb-tree-row[data-wb-open-doc]');
    const documentId = documentRow?.dataset.wbOpenDoc || '';
    let sectionId = '';
    if (resource?.kind === 'function') {
      const functionGroup = row.parentElement;
      const sectionContainer = functionGroup?.parentElement;
      const sectionRow = sectionContainer?.querySelector(
        ':scope > .wb-tree-row.depth2[data-wb-open-resource]'
      );
      sectionId = sectionRow?.dataset.wbOpenResource || '';
    }
    return { documentId, sectionId };
  }

  shell.addEventListener('click', event => {
    const row = event.target.closest?.('#wbExplorer .wb-tree-row[data-wb-open-resource]');
    if (!row || event.target.closest?.('[data-wb-expand]')) return;
    const resourceId = row.dataset.wbOpenResource || '';
    const resource = resourceById(resourceId);
    if (!resource) return;
    const context = explorerContext(row, resource);

    event.preventDefault();
    event.stopImmediatePropagation();
    if (resource.state === 'orphaned' || !resolveContext(resourceId, context)) {
      originalInspectResource(resourceId, { reason: 'workspace-staged-inspected' });
      return;
    }
    openResource(resourceId, context);
  }, true);

  shell.addEventListener('contextmenu', event => {
    const row = event.target.closest?.('#wbExplorer .wb-tree-row[data-wb-open-resource]');
    if (!row) return;
    const resourceId = row.dataset.wbOpenResource || '';
    const resource = resourceById(resourceId);
    if (!resource) return;
    contextHint = { resourceId, ...explorerContext(row, resource) };
  }, true);

  store.subscribe(snapshot => {
    if (restoring || pruning) {
      lastSnapshot = snapshot;
      return;
    }

    const previous = lastSnapshot;
    const switched = Boolean(
      previous?.activeDocumentId
      && previous.activeDocumentId !== snapshot.activeDocumentId
    );
    if (switched) rememberSnapshot(previous);
    else rememberSnapshot(snapshot);

    reconcileWorkspaces();
    if (switched && snapshot.activeDocumentId) restoreWorkspace(snapshot.activeDocumentId);
    else pruneCurrentWorkspace(snapshot);
    lastSnapshot = store.getSnapshot();
  });

  workbench.openDocument = openDocument;
  workbench.openResource = openResource;

  window.JawWorkbenchWorkspace = {
    graphFor,
    resolveContext,
    get(documentId) {
      const value = documentWorkspaces.get(documentId);
      return value ? { ...value, sectionTabs: [...value.sectionTabs], functionTabs: [...value.functionTabs] } : null;
    },
  };
})();
