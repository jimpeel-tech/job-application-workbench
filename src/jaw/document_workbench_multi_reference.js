(() => {
  const shell = document.querySelector('.wb-shell');
  const store = window.JawWorkbenchStore;
  const workbench = window.JawDocumentWorkbench;
  const referenceIds = window.JawWorkbenchReferenceIds;
  if (!shell || !store || !workbench || !referenceIds || window.JawWorkbenchMultiReference) return;

  const sessions = new WeakMap();
  const bypassInputs = new WeakSet();
  const SETTLE_MS = 650;
  let removalModal = null;

  const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[character]));

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

  function completeSelectedBindings(editor, start, end) {
    const kind = editor.dataset.wbEditor || '';
    if (!['template', 'section'].includes(kind)) return [];
    const left = Math.min(Number(start || 0), Number(end || 0));
    const right = Math.max(Number(start || 0), Number(end || 0));
    if (left === right) return [];
    return referenceIds.referencesIntersecting(kind, editor, left, right).filter(binding => (
      Number(binding.constructStart) >= left
      && Number(binding.constructEnd) <= right
      && binding.reference?.id
      && binding.reference?.child_id
    ));
  }

  function beginInput(event) {
    const editor = event.currentTarget;
    if (bypassInputs.has(editor) || removalModal) return;
    if (!String(event.inputType || '').startsWith('delete')) return;

    const start = Number(editor.selectionStart || 0);
    const end = Number(editor.selectionEnd ?? start);
    const bindings = completeSelectedBindings(editor, start, end);
    if (bindings.length < 2) return;

    sessions.set(editor, {
      kind: editor.dataset.wbEditor || '',
      parentId: parentIdFor(editor),
      beforeValue: String(editor.value || ''),
      beforeStart: start,
      beforeEnd: end,
      bindings: bindings.map(binding => ({
        referenceId: String(binding.reference.id),
        childId: String(binding.reference.child_id),
        symbol: String(binding.reference.symbol || binding.symbol || ''),
        constructStart: Number(binding.constructStart),
        constructEnd: Number(binding.constructEnd),
        tokenStart: Number(binding.start),
        tokenEnd: Number(binding.end),
        kind: String(binding.resource?.kind || ''),
        visibility: String(binding.resource?.visibility || ''),
      })),
    });
    event.stopImmediatePropagation();
  }

  function afterInput(event) {
    const editor = event.currentTarget;
    if (bypassInputs.has(editor)) {
      bypassInputs.delete(editor);
      return;
    }
    const session = sessions.get(editor);
    if (!session) return;

    event.stopImmediatePropagation();
    session.currentSource = String(editor.value || '');
    session.currentStart = Number(editor.selectionStart || 0);
    session.currentEnd = Number(editor.selectionEnd ?? editor.selectionStart ?? 0);
    openRemovalModal(editor, session);
  }

  function transitionPayload(editor, session, binding, disposition) {
    return {
      action: 'remove',
      reference_id: binding.referenceId,
      parent_id: session.parentId,
      child_id: binding.childId,
      symbol: binding.symbol,
      reference_start: binding.tokenStart,
      reference_end: binding.tokenEnd,
      source_content: String(session.currentSource ?? editor.value ?? ''),
      cursor_start: Number(session.currentStart ?? editor.selectionStart ?? 0),
      cursor_end: Number(session.currentEnd ?? editor.selectionEnd ?? editor.selectionStart ?? 0),
      disposition,
    };
  }

  function closeModal() {
    removalModal?.remove();
    removalModal = null;
  }

  function dispatchResolvedInput(editor, inputType) {
    bypassInputs.add(editor);
    editor.dispatchEvent(new InputEvent('input', {
      bubbles: true,
      inputType,
      data: null,
    }));
  }

  function restoreSessionEditor(editor, session) {
    if (typeof session.currentSource !== 'string') return;
    if (editor.value !== session.currentSource) editor.value = session.currentSource;
    try {
      editor.setSelectionRange(
        Math.min(Number(session.currentStart || 0), editor.value.length),
        Math.min(Number(session.currentEnd ?? session.currentStart ?? 0), editor.value.length),
      );
    } catch (_) { /* noop */ }
  }

  function cancelRemoval(editor, session) {
    closeModal();
    editor.value = session.beforeValue;
    editor.setSelectionRange(
      Math.min(session.beforeStart, editor.value.length),
      Math.min(session.beforeEnd, editor.value.length),
    );
    sessions.delete(editor);
    dispatchResolvedInput(editor, 'historyUndo');
    setStatus('Reference removal cancelled', 'muted');
    requestAnimationFrame(() => editor.focus({ preventScroll: true }));
  }

  function resourceKindLabel(session) {
    const kind = session.bindings[0]?.kind
      || (session.kind === 'section' ? 'function' : 'section');
    return kind === 'function' ? 'Function' : 'Section';
  }

  function modalShell(session) {
    const count = session.bindings.length;
    return `
      <div class="wb-reference-card" role="dialog" aria-modal="true" aria-label="Resolve removed references">
        <h3>Remove references</h3>
        <p>You removed <strong>${count} ${esc(resourceKindLabel(session))} references</strong> from the source.</p>
        <div data-wb-multi-reference-body><p class="muted">Checking source and relationships…</p></div>
        <div class="wb-reference-modal-actions"><button type="button" data-choice="cancel">Cancel</button></div>
      </div>`;
  }

  async function previewSelections(editor, session) {
    const previews = [];
    for (const binding of session.bindings) {
      previews.push(await workbench.mutate(
        'rename-symbol',
        transitionPayload(editor, session, binding, 'preview'),
      ));
    }
    return previews;
  }

  function renderChoices(editor, session, previews) {
    if (!removalModal) return;
    const body = removalModal.querySelector('[data-wb-multi-reference-body]');
    const actions = removalModal.querySelector('.wb-reference-modal-actions');
    const privateDispositionCount = previews.filter(
      item => item?.requires_disposition === 'stage-delete'
    ).length;
    const count = session.bindings.length;

    if (body) {
      body.innerHTML = privateDispositionCount
        ? `<p class="muted">Stage keeps the selected private resource${privateDispositionCount === 1 ? '' : 's'} and children for reuse. Delete permanently removes unreferenced private resource trees. Global/shared references are only unlinked.</p>`
        : `<p class="muted">The ${count === 1 ? 'reference' : 'references'} will be removed while shared or still-used resources are preserved.</p>`;
    }
    if (!actions) return;

    actions.innerHTML = privateDispositionCount
      ? '<button type="button" data-choice="cancel">Cancel</button><button type="button" data-choice="stage">Stage</button><button type="button" class="danger" data-choice="delete">Delete</button>'
      : '<button type="button" data-choice="cancel">Cancel</button><button type="button" class="primary" data-choice="remove">Remove References</button>';

    actions.querySelector('[data-choice="cancel"]')?.addEventListener(
      'click',
      () => cancelRemoval(editor, session),
    );
    actions.querySelectorAll('[data-choice]:not([data-choice="cancel"])').forEach(button => {
      button.addEventListener('click', async () => {
        const choice = button.dataset.choice || 'remove';
        try {
          setStatus('Applying reference changes…');
          for (let index = 0; index < session.bindings.length; index += 1) {
            const binding = session.bindings[index];
            const preview = previews[index] || {};
            const disposition = preview.requires_disposition === 'stage-delete'
              ? choice
              : 'remove';
            await workbench.mutate(
              'rename-symbol',
              transitionPayload(editor, session, binding, disposition),
            );
            // Each structural mutation applies a full Workbench state. While this
            // decision is pending, the normal editor input path is suppressed, so
            // Workbench's local buffer can still contain the pre-delete source.
            // Restore the user's resolved source synchronously before the next
            // transition so stale local text can never become authoritative again.
            restoreSessionEditor(editor, session);
          }
          restoreSessionEditor(editor, session);
          closeModal();
          sessions.delete(editor);
          dispatchResolvedInput(editor, 'deleteByCut');
          setStatus(
            choice === 'stage'
              ? `${privateDispositionCount} resource${privateDispositionCount === 1 ? '' : 's'} staged`
              : choice === 'delete'
                ? `${privateDispositionCount} resource${privateDispositionCount === 1 ? '' : 's'} deleted`
                : `${count} reference${count === 1 ? '' : 's'} removed`,
            'ok',
          );
          requestAnimationFrame(() => editor.focus({ preventScroll: true }));
        } catch (error) {
          setStatus(String(error.message || error), 'error');
        }
      });
    });
  }

  function renderError(editor, session, error) {
    if (!removalModal) return;
    const body = removalModal.querySelector('[data-wb-multi-reference-body]');
    const actions = removalModal.querySelector('.wb-reference-modal-actions');
    if (body) body.innerHTML = `<p class="muted">${esc(String(error.message || error))}</p>`;
    if (!actions) return;
    actions.innerHTML = '<button type="button" data-choice="cancel">Cancel</button>';
    actions.querySelector('[data-choice="cancel"]')?.addEventListener(
      'click',
      () => cancelRemoval(editor, session),
    );
  }

  function openRemovalModal(editor, session) {
    if (removalModal) return;
    removalModal = document.createElement('div');
    removalModal.className = 'wb-reference-modal';
    removalModal.innerHTML = modalShell(session);
    shell.appendChild(removalModal);
    removalModal.querySelector('[data-choice="cancel"]')?.addEventListener(
      'click',
      () => cancelRemoval(editor, session),
    );

    void (async () => {
      try {
        await new Promise(resolve => setTimeout(resolve, SETTLE_MS));
        const previews = await previewSelections(editor, session);
        renderChoices(editor, session, previews);
      } catch (error) {
        setStatus(String(error.message || error), 'error');
        renderError(editor, session, error);
      }
    })();
  }

  function restorePendingEditors() {
    for (const editor of shell.querySelectorAll(
      '.wb-editor[data-wb-editor="template"], .wb-editor[data-wb-editor="section"]',
    )) {
      const session = sessions.get(editor);
      if (!session) continue;
      restoreSessionEditor(editor, session);
    }
  }

  function hasPending() {
    return Boolean(removalModal) || [...shell.querySelectorAll('.wb-editor')].some(
      editor => sessions.has(editor)
    );
  }

  for (const editor of shell.querySelectorAll(
    '.wb-editor[data-wb-editor="template"], .wb-editor[data-wb-editor="section"]',
  )) {
    editor.addEventListener('beforeinput', beginInput, true);
    editor.addEventListener('input', afterInput, true);
  }

  document.addEventListener('click', event => {
    if (!removalModal || removalModal.contains(event.target)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    setStatus('Choose an action in the reference dialog.', 'error');
  }, true);

  document.addEventListener('contextmenu', event => {
    if (!removalModal) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    setStatus('Choose an action in the reference dialog.', 'error');
  }, true);

  document.addEventListener('keydown', event => {
    if (!removalModal || event.key !== 'Escape') return;
    event.preventDefault();
    event.stopImmediatePropagation();
    setStatus('Choose Cancel, Stage, Delete, or Remove References.', 'error');
  }, true);

  window.addEventListener('beforeunload', event => {
    if (!hasPending()) return;
    event.preventDefault();
    event.returnValue = '';
  });

  store.subscribe(() => requestAnimationFrame(restorePendingEditors));
  window.JawWorkbenchMultiReference = { hasPending };
})();