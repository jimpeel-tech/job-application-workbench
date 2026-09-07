(() => {
  const shell = document.querySelector('.wb-shell');
  const store = window.JawWorkbenchStore;
  const workbench = window.JawDocumentWorkbench;
  const referenceIds = window.JawWorkbenchReferenceIds;
  if (!shell || !store || !workbench || !referenceIds) return;

  const sessions = new WeakMap();
  const beforeInputs = new WeakMap();
  const bypassInputs = new WeakSet();
  const actionLayers = new WeakMap();
  const lastNormalInputs = new WeakMap();
  const CHECKPOINT_SETTLE_MS = 650;
  let removalModal = null;

  const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[character]));

  function state() { return store.getState() || {}; }
  function resourceById(id) {
    return (state().resources || []).find(item => item.id === id) || null;
  }
  function parentIdFor(editor) {
    if (editor.dataset.wbEditor === 'template') return store.getActiveDocumentId() || '';
    if (editor.dataset.wbEditor === 'section') return editor.dataset.resourceId || '';
    return '';
  }
  function setStatus(text = '', kind = '') {
    const status = document.getElementById('wbStatus');
    if (!status) return;
    status.textContent = text;
    status.className = `wb-status ${kind}`;
  }

  function safeAfterFor(editor) {
    const last = lastNormalInputs.get(editor);
    return last == null ? 0 : last + CHECKPOINT_SETTLE_MS;
  }

  async function settleQueuedCheckpoint(session) {
    const wait = Number(session.safeAfter || 0) - performance.now();
    if (wait > 0) await new Promise(resolve => setTimeout(resolve, wait));
  }

  function referenceSession(editor, start, end) {
    const parentId = parentIdFor(editor);
    const kind = editor.dataset.wbEditor || '';
    if (!parentId || !['template', 'section'].includes(kind)) return null;
    const bindings = referenceIds.referencesIntersecting(kind, editor, start, end);
    if (!bindings.length) return null;
    const binding = bindings[0];
    const edge = binding.reference;
    const child = binding.resource || resourceById(edge.child_id);
    if (!edge?.id || !child) return null;
    return {
      parentId,
      referenceId: String(edge.id),
      childId: String(edge.child_id),
      edge,
      child,
      originalSymbol: String(edge.symbol),
      originalConstruct: editor.value.slice(binding.constructStart, binding.constructEnd),
      construct: { start: binding.constructStart, end: binding.constructEnd },
      token: { start: binding.start, end: binding.end },
      currentSource: editor.value,
      currentStart: Number(editor.selectionStart || 0),
      currentEnd: Number(editor.selectionEnd ?? editor.selectionStart ?? 0),
      safeAfter: safeAfterFor(editor),
      pending: false,
      removed: false,
    };
  }

  function diffSpan(before, after) {
    let prefix = 0;
    while (prefix < before.length && prefix < after.length && before[prefix] === after[prefix]) {
      prefix += 1;
    }
    let suffix = 0;
    while (
      suffix < before.length - prefix
      && suffix < after.length - prefix
      && before[before.length - 1 - suffix] === after[after.length - 1 - suffix]
    ) {
      suffix += 1;
    }
    return {
      oldStart: prefix,
      oldEnd: before.length - suffix,
      newStart: prefix,
      newEnd: after.length - suffix,
    };
  }

  function transformRange(range, diff) {
    const delta = (diff.newEnd - diff.newStart) - (diff.oldEnd - diff.oldStart);
    if (diff.oldStart === diff.oldEnd) {
      if (diff.oldStart < range.start) {
        return { start: range.start + delta, end: range.end + delta };
      }
      if (diff.oldStart > range.end) return { ...range };
      return { start: range.start, end: Math.max(range.start, range.end + delta) };
    }
    if (diff.oldEnd <= range.start) {
      return { start: range.start + delta, end: range.end + delta };
    }
    if (diff.oldStart >= range.end) return { ...range };

    const mapStart = position => {
      if (position <= diff.oldStart) return position;
      if (position >= diff.oldEnd) return position + delta;
      return diff.newStart;
    };
    const mapEnd = position => {
      if (position <= diff.oldStart) return position;
      if (position >= diff.oldEnd) return position + delta;
      return diff.newEnd;
    };
    const start = mapStart(range.start);
    const end = mapEnd(range.end);
    return { start: Math.min(start, end), end: Math.max(start, end) };
  }

  function ensureActionLayer(editor) {
    let layer = actionLayers.get(editor);
    if (layer?.isConnected) return layer;
    layer = document.createElement('div');
    layer.className = 'wb-reference-actions';
    editor.closest('.wb-editor-body')?.appendChild(layer);
    actionLayers.set(editor, layer);
    return layer;
  }

  function clearActions(editor) {
    const layer = actionLayers.get(editor);
    if (layer) layer.innerHTML = '';
  }

  function syncPendingMirror(editor) {
    const mirror = editor.closest('.wb-editor-body')?.querySelector('.wb-editor-highlight');
    if (!mirror) return;
    mirror.textContent = editor.value || ' ';
    mirror.scrollTop = editor.scrollTop;
    mirror.scrollLeft = editor.scrollLeft;
  }

  function constructText(editor, session) {
    return editor.value.slice(session.construct.start, session.construct.end);
  }

  function symbolHint(editor, session) {
    return editor.value.slice(session.token.start, session.token.end).trim();
  }

  function renderActions(editor) {
    const session = sessions.get(editor);
    const layer = ensureActionLayer(editor);
    if (!session?.pending || session.removed) {
      layer.innerHTML = '';
      return;
    }

    const child = resourceById(session.childId) || session.child;
    const kindLabel = child?.kind === 'function' ? 'Function' : 'Section';
    const updateLabel = child?.visibility === 'global'
      ? 'Update Reference'
      : `Update ${kindLabel}`;
    const line = editor.value.slice(0, Math.max(0, session.construct.start)).split('\n').length - 1;
    const style = getComputedStyle(editor);
    const lineHeight = parseFloat(style.lineHeight) || 19.5;
    const top = (parseFloat(style.paddingTop) || 0) + line * lineHeight - editor.scrollTop;
    layer.style.top = `${Math.max(1, top)}px`;
    layer.innerHTML = `
      <button type="button" data-wb-reference-update>${esc(updateLabel)}</button>
      <button type="button" data-wb-reference-create>Create ${esc(kindLabel)}</button>
      <button type="button" data-wb-reference-cancel>Cancel</button>`;

    for (const button of layer.querySelectorAll('button')) {
      button.addEventListener('mousedown', event => event.preventDefault());
    }
    layer.querySelector('[data-wb-reference-update]')
      ?.addEventListener('click', () => commitUpdate(editor));
    layer.querySelector('[data-wb-reference-create]')
      ?.addEventListener('click', () => commitCreate(editor));
    layer.querySelector('[data-wb-reference-cancel]')
      ?.addEventListener('click', () => cancelPendingEdit(editor));
  }

  function beginInput(event) {
    const editor = event.currentTarget;
    if (bypassInputs.has(editor)) return;

    const snapshot = {
      value: editor.value,
      start: Number(editor.selectionStart || 0),
      end: Number(editor.selectionEnd ?? editor.selectionStart ?? 0),
      inputType: event.inputType || '',
    };
    const session = sessions.get(editor)
      || referenceSession(editor, snapshot.start, snapshot.end);

    beforeInputs.set(editor, {
      snapshot,
      session,
      construct: session ? { ...session.construct } : null,
      token: session ? { ...session.token } : null,
    });
  }

  function fallbackBeforeInput(editor, session) {
    return {
      snapshot: {
        value: String(session.currentSource ?? editor.value),
        start: Number(session.currentStart ?? editor.selectionStart ?? 0),
        end: Number(session.currentEnd ?? editor.selectionStart ?? 0),
        inputType: 'programmatic',
      },
      session,
      construct: { ...session.construct },
      token: { ...session.token },
    };
  }

  function afterInput(event) {
    const editor = event.currentTarget;
    if (bypassInputs.has(editor)) {
      bypassInputs.delete(editor);
      return;
    }

    let before = beforeInputs.get(editor);
    beforeInputs.delete(editor);
    if (!before?.session) {
      const existing = sessions.get(editor);
      if (!existing) {
        lastNormalInputs.set(editor, performance.now());
        return;
      }
      before = fallbackBeforeInput(editor, existing);
    }

    const session = before.session;
    const diff = diffSpan(before.snapshot.value, editor.value);
    session.lastBefore = {
      ...before.snapshot,
      construct: before.construct ? { ...before.construct } : null,
      token: before.token ? { ...before.token } : null,
    };
    session.construct = transformRange(session.construct, diff);
    session.token = transformRange(session.token, diff);
    session.currentSource = editor.value;
    session.currentStart = Number(editor.selectionStart || 0);
    session.currentEnd = Number(editor.selectionEnd ?? editor.selectionStart ?? 0);

    const currentConstruct = constructText(editor, session);
    session.removed = session.construct.end <= session.construct.start || !currentConstruct;
    if (session.removed) {
      sessions.set(editor, session);
      clearActions(editor);
      syncPendingMirror(editor);
      event.stopImmediatePropagation();
      openRemovalModal(editor, session, { mode: 'remove' });
      return;
    }

    // Reference identity belongs to the selected ref JID, not to its visible
    // text. Any change to this exact token therefore requires an explicit choice.
    session.pending = symbolHint(editor, session) !== session.originalSymbol;
    if (session.pending) {
      sessions.set(editor, session);
      syncPendingMirror(editor);
      renderActions(editor);
      event.stopImmediatePropagation();
      return;
    }

    sessions.delete(editor);
    clearActions(editor);
    lastNormalInputs.set(editor, performance.now());
  }

  function transitionPayload(editor, session, action, disposition = '') {
    return {
      action,
      reference_id: session.referenceId,
      parent_id: session.parentId,
      child_id: session.childId,
      symbol: symbolHint(editor, session),
      reference_start: session.token.start,
      reference_end: session.token.end,
      source_content: editor.value,
      cursor_start: Number(editor.selectionStart || 0),
      cursor_end: Number(editor.selectionEnd ?? editor.selectionStart ?? 0),
      disposition,
    };
  }

  function dispatchResolvedInput(editor, inputType = 'insertReplacementText') {
    lastNormalInputs.set(editor, performance.now());
    bypassInputs.add(editor);
    editor.dispatchEvent(new InputEvent('input', {
      bubbles: true,
      inputType,
      data: null,
    }));
  }

  function syncCommittedEditor(editor, source) {
    if (typeof source === 'string' && editor.value !== source) editor.value = source;
    sessions.delete(editor);
    clearActions(editor);
    dispatchResolvedInput(editor);
    requestAnimationFrame(() => editor.focus({ preventScroll: true }));
  }

  function cancelPendingEdit(editor) {
    const session = sessions.get(editor);
    if (!session?.pending || session.removed) return;

    const start = Math.max(0, Math.min(session.construct.start, editor.value.length));
    const end = Math.max(start, Math.min(session.construct.end, editor.value.length));
    editor.setRangeText(session.originalConstruct, start, end, 'end');
    sessions.delete(editor);
    clearActions(editor);
    dispatchResolvedInput(editor, 'historyUndo');
    setStatus('Reference edit cancelled', 'muted');
    requestAnimationFrame(() => editor.focus({ preventScroll: true }));
  }

  async function commitUpdate(editor) {
    const session = sessions.get(editor);
    if (!session?.pending) return;
    try {
      setStatus('Validating update…');
      await settleQueuedCheckpoint(session);
      const result = await workbench.mutate(
        'rename-symbol',
        transitionPayload(editor, session, 'update'),
      );
      syncCommittedEditor(editor, String(result.source_content ?? editor.value));
      setStatus(`Updated ${result.new_symbol || session.originalSymbol}`, 'ok');
    } catch (error) {
      setStatus(String(error.message || error), 'error');
      syncPendingMirror(editor);
      renderActions(editor);
    }
  }

  async function commitCreate(editor) {
    const session = sessions.get(editor);
    if (!session?.pending) return;
    try {
      setStatus('Validating new resource…');
      await settleQueuedCheckpoint(session);
      const preview = await workbench.mutate(
        'rename-symbol',
        transitionPayload(editor, session, 'create', 'preview'),
      );
      if (preview.requires_disposition) {
        openRemovalModal(editor, session, { mode: 'create', validation: preview });
        return;
      }
      const result = await workbench.mutate(
        'rename-symbol',
        transitionPayload(editor, session, 'create'),
      );
      syncCommittedEditor(editor, String(result.source_content ?? editor.value));
      setStatus(`Created ${result.new_symbol || 'new resource'}`, 'ok');
    } catch (error) {
      setStatus(String(error.message || error), 'error');
      syncPendingMirror(editor);
      renderActions(editor);
    }
  }

  function closeRemovalModal() {
    removalModal?.remove();
    removalModal = null;
  }

  function restoreRemoval(editor, session) {
    const before = session.lastBefore;
    closeRemovalModal();
    if (!before) return;

    editor.value = before.value;
    editor.setSelectionRange(
      Math.min(before.start, editor.value.length),
      Math.min(before.end, editor.value.length),
    );
    if (before.construct) session.construct = { ...before.construct };
    if (before.token) session.token = { ...before.token };
    session.currentSource = editor.value;
    session.currentStart = Number(editor.selectionStart || 0);
    session.currentEnd = Number(editor.selectionEnd ?? editor.selectionStart ?? 0);
    session.removed = false;
    session.pending = symbolHint(editor, session) !== session.originalSymbol;

    if (session.pending) {
      sessions.set(editor, session);
      syncPendingMirror(editor);
      renderActions(editor);
    } else {
      sessions.delete(editor);
      clearActions(editor);
      dispatchResolvedInput(editor, 'historyUndo');
    }
    requestAnimationFrame(() => editor.focus({ preventScroll: true }));
  }

  function cancelCreateDisposition(editor, session) {
    closeRemovalModal();
    session.removed = false;
    session.currentSource = editor.value;
    session.currentStart = Number(editor.selectionStart || 0);
    session.currentEnd = Number(editor.selectionEnd ?? editor.selectionStart ?? 0);
    sessions.set(editor, session);
    syncPendingMirror(editor);
    renderActions(editor);
    requestAnimationFrame(() => editor.focus({ preventScroll: true }));
  }

  function modalShell(mode, name) {
    const lead = mode === 'create'
      ? `<p>The edited reference creates a new resource. What should JAW do with <strong>${esc(name)}</strong>?</p>`
      : `<p>You removed the construct that references <strong>${esc(name)}</strong>.</p>`;
    return `
      <div class="wb-reference-card" role="dialog" aria-modal="true" aria-label="Resolve removed reference">
        <h3>${mode === 'create' ? 'Create new resource' : 'Remove reference'}</h3>
        ${lead}
        <div data-wb-reference-modal-body><p class="muted">Checking source and relationships…</p></div>
        <div class="wb-reference-modal-actions"><button type="button" data-choice="cancel">Cancel</button></div>
      </div>`;
  }

  function renderRemovalChoices(editor, session, mode, validation) {
    if (!removalModal) return;
    const child = resourceById(session.childId) || session.child;
    const name = child?.name || session.originalSymbol;
    const body = removalModal.querySelector('[data-wb-reference-modal-body]');
    const actions = removalModal.querySelector('.wb-reference-modal-actions');
    const stillReferenced = Boolean(validation?.old_still_referenced);
    const global = validation?.visibility === 'global' || child?.visibility === 'global';

    if (body) {
      body.innerHTML = stillReferenced
        ? '<p class="muted">The resource is still referenced elsewhere in this source, so the resource itself will be preserved.</p>'
        : global
          ? '<p class="muted">This is Global. Only this reference will be removed; the Global resource will be preserved.</p>'
          : '<p class="muted">Stage keeps the private resource and its children for reuse. Delete permanently removes its unreferenced private resource tree.</p>';
    }
    if (!actions) return;

    actions.innerHTML = stillReferenced || global
      ? '<button type="button" data-choice="cancel">Cancel</button><button type="button" class="primary" data-choice="remove">Remove Reference</button>'
      : '<button type="button" data-choice="cancel">Cancel</button><button type="button" data-choice="stage">Stage</button><button type="button" class="danger" data-choice="delete">Delete</button>';

    actions.querySelector('[data-choice="cancel"]')?.addEventListener('click', () => {
      if (mode === 'create') cancelCreateDisposition(editor, session);
      else restoreRemoval(editor, session);
    });
    actions.querySelectorAll('[data-choice]:not([data-choice="cancel"])').forEach(button => {
      button.addEventListener('click', async () => {
        const choice = button.dataset.choice || '';
        try {
          setStatus('Validating change…');
          await settleQueuedCheckpoint(session);
          const action = mode === 'create' ? 'create' : 'remove';
          const disposition = choice === 'remove' ? 'remove' : choice;
          const result = await workbench.mutate(
            'rename-symbol',
            transitionPayload(editor, session, action, disposition),
          );
          closeRemovalModal();
          syncCommittedEditor(editor, String(result.source_content ?? editor.value));
          setStatus(
            choice === 'stage'
              ? `${name} staged`
              : choice === 'delete'
                ? `${name} deleted`
                : 'Reference removed',
            'ok',
          );
        } catch (error) {
          setStatus(String(error.message || error), 'error');
        }
      });
    });
  }

  function renderRemovalError(editor, session, mode, error) {
    if (!removalModal) return;
    const body = removalModal.querySelector('[data-wb-reference-modal-body]');
    const actions = removalModal.querySelector('.wb-reference-modal-actions');
    if (body) body.innerHTML = `<p class="muted">${esc(String(error.message || error))}</p>`;
    if (!actions) return;
    actions.innerHTML = '<button type="button" data-choice="cancel">Cancel</button>';
    actions.querySelector('[data-choice="cancel"]')?.addEventListener('click', () => {
      if (mode === 'create') cancelCreateDisposition(editor, session);
      else restoreRemoval(editor, session);
    });
  }

  function openRemovalModal(editor, session, { mode, validation = null }) {
    if (removalModal) return;
    const child = resourceById(session.childId) || session.child;
    const name = child?.name || session.originalSymbol;
    removalModal = document.createElement('div');
    removalModal.className = 'wb-reference-modal';
    removalModal.innerHTML = modalShell(mode, name);
    shell.appendChild(removalModal);
    removalModal.querySelector('[data-choice="cancel"]')?.addEventListener('click', () => {
      if (mode === 'create') cancelCreateDisposition(editor, session);
      else restoreRemoval(editor, session);
    });

    if (validation) {
      renderRemovalChoices(editor, session, mode, validation);
      return;
    }

    void (async () => {
      try {
        await settleQueuedCheckpoint(session);
        const preview = await workbench.mutate(
          'rename-symbol',
          transitionPayload(
            editor,
            session,
            mode === 'create' ? 'create' : 'remove',
            'preview',
          ),
        );
        renderRemovalChoices(editor, session, mode, preview);
      } catch (error) {
        setStatus(String(error.message || error), 'error');
        renderRemovalError(editor, session, mode, error);
      }
    })();
  }

  function hasPending() {
    return [...shell.querySelectorAll('.wb-editor')].some(editor => {
      const session = sessions.get(editor);
      return Boolean(session?.pending || session?.removed);
    });
  }

  function blockPendingAction(event, message) {
    if (!hasPending()) return false;
    event?.preventDefault?.();
    event?.stopImmediatePropagation?.();
    setStatus(message || 'Resolve the pending reference edit first.', 'error');
    return true;
  }

  function relabelStaged() {
    const sideTitle = shell.querySelector('[data-wb-side-pane="orphans"] .wb-side-head span');
    if (sideTitle) sideTitle.textContent = 'STAGED';
    shell.querySelectorAll('.orphan-text').forEach(element => { element.textContent = 'Staged'; });
  }

  function restorePendingEditors() {
    for (const editor of shell.querySelectorAll(
      '.wb-editor[data-wb-editor="template"], .wb-editor[data-wb-editor="section"]',
    )) {
      const session = sessions.get(editor);
      if (!session?.pending && !session?.removed) continue;
      if (typeof session.currentSource === 'string' && editor.value !== session.currentSource) {
        editor.value = session.currentSource;
        try {
          editor.setSelectionRange(
            Math.min(Number(session.currentStart || 0), editor.value.length),
            Math.min(
              Number(session.currentEnd ?? session.currentStart ?? 0),
              editor.value.length,
            ),
          );
        } catch (_) { /* noop */ }
      }
      syncPendingMirror(editor);
      renderActions(editor);
    }
  }

  for (const editor of shell.querySelectorAll(
    '.wb-editor[data-wb-editor="template"], .wb-editor[data-wb-editor="section"]',
  )) {
    editor.addEventListener('beforeinput', beginInput, true);
    editor.addEventListener('input', afterInput, true);
    editor.addEventListener('scroll', () => renderActions(editor));
  }

  shell.addEventListener('click', event => {
    if (!hasPending()) return;
    if (event.target.closest('.wb-reference-actions,.wb-reference-modal')) return;
    if (event.target.closest(
      '#wbGenerate,#wbNewDocument,[data-wb-doc-tab],[data-wb-open-doc],'
      + '[data-wb-resource-tab],[data-wb-open-resource],[data-wb-close-doc],[data-wb-close-tab]'
    )) {
      blockPendingAction(event);
    }
  }, true);

  document.addEventListener('click', event => {
    if (!removalModal || removalModal.contains(event.target)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    setStatus('Choose an action in the reference dialog.', 'error');
  }, true);

  document.addEventListener('keydown', event => {
    if (removalModal && event.key === 'Escape') {
      event.preventDefault();
      event.stopImmediatePropagation();
      setStatus('Choose Cancel, Stage, Delete, or Remove Reference.', 'error');
      return;
    }
    const command = event.ctrlKey || event.metaKey;
    if (command && event.key.toLowerCase() === 's' && hasPending()) {
      blockPendingAction(event, 'Update/Create/Cancel the edited reference before saving.');
    }
  }, true);

  window.addEventListener('beforeunload', event => {
    if (!hasPending()) return;
    event.preventDefault();
    event.returnValue = '';
  });

  relabelStaged();
  store.subscribe(() => requestAnimationFrame(() => {
    relabelStaged();
    restorePendingEditors();
  }));

  window.JawWorkbenchTransitions = { hasPending };
})();