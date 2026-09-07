(() => {
  const shell = document.querySelector('.wb-shell');
  const store = window.JawWorkbenchStore;
  const workbench = window.JawDocumentWorkbench;
  const referenceIds = window.JawWorkbenchReferenceIds;
  if (!shell || !store || !workbench || !referenceIds) return;

  let menu = null;
  let menuScrollCloseReady = false;
  let renameDialog = null;
  let deleteDialog = null;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[character]));

  function state() { return store.getState() || {}; }
  function resourceById(id) { return (state().resources || []).find(item => item.id === id) || null; }
  function relationshipsFor(id) { return state().relationships?.[id] || { inbound: [], outbound: [] }; }
  function templateUsage(id) { return (state().documents || []).filter(document => document.template_id === id); }
  function resourceTitle(resource, edge = null) {
    if (!resource) return 'Resource';
    if (resource.kind === 'section' || resource.kind === 'function') {
      return String(edge?.symbol || resource.symbol || resource.kind);
    }
    return String(resource.name || resource.symbol || resource.kind || 'Resource');
  }
  function templatePrivateOwner(resource) {
    if (resource?.kind !== 'template') return null;
    const usage = templateUsage(resource.id);
    const activeDocumentId = String(store.getSnapshot()?.activeDocumentId || '');
    return usage.find(document => document.id === activeDocumentId) || (usage.length === 1 ? usage[0] : null);
  }

  function setStatus(text = '', kind = '') {
    const status = document.getElementById('wbStatus');
    if (!status) return;
    status.textContent = text;
    status.className = `wb-status ${kind}`;
  }

  function targetFromElement(element) {
    const target = element?.closest?.(
      '[data-wb-open-resource],[data-wb-resource-tab],[data-wb-select-resource],'
      + '[data-wb-drag-resource],[data-wb-open-doc],[data-wb-doc-tab]'
    );
    if (!target) return null;
    const id = target.dataset.wbOpenResource || target.dataset.wbResourceTab
      || target.dataset.wbSelectResource || target.dataset.wbDragResource
      || target.dataset.wbOpenDoc || target.dataset.wbDocTab || '';
    return id ? {
      id,
      referenceId: String(target.dataset.wbReferenceJid || ''),
      element: target,
    } : null;
  }

  function activeReference(resource, preferredReferenceId = '') {
    const inbound = relationshipsFor(resource.id).inbound || [];
    if (!inbound.length) return null;
    if (preferredReferenceId) {
      const exact = inbound.find(item => String(item.id || '') === preferredReferenceId);
      if (exact) return exact;
    }
    const snapshot = store.getSnapshot();
    if (resource.kind === 'section') {
      const matches = inbound.filter(item => item.parent_id === snapshot.activeDocumentId);
      if (matches.length === 1) return matches[0];
      if (matches.length > 1) return null;
    }
    if (resource.kind === 'function') {
      const sectionId = snapshot.activeTabs?.section || '';
      const matches = inbound.filter(item => item.parent_id === sectionId);
      if (matches.length === 1) return matches[0];
      if (matches.length > 1) return null;
    }
    return inbound.length === 1 ? inbound[0] : null;
  }

  function referencedEdge(kind, editor, cursor) {
    if (!['template', 'section'].includes(kind)) return null;
    return referenceIds.referenceAt(kind, editor, Number(cursor || 0))?.reference || null;
  }

  function openResourceKeepingCaret(editor, resourceId) {
    const selection = {
      start: Number(editor.selectionStart || 0),
      end: Number(editor.selectionEnd ?? editor.selectionStart ?? 0),
      direction: editor.selectionDirection || 'none',
      scrollTop: editor.scrollTop,
      scrollLeft: editor.scrollLeft,
    };
    workbench.openResource(resourceId, { focus: false });

    requestAnimationFrame(() => {
      if (!editor.isConnected) return;
      const start = Math.min(selection.start, editor.value.length);
      const end = Math.min(selection.end, editor.value.length);
      try { editor.setSelectionRange(start, end, selection.direction); } catch (_) { /* noop */ }
      editor.scrollTop = selection.scrollTop;
      editor.scrollLeft = selection.scrollLeft;
      if (document.activeElement !== editor) editor.focus({ preventScroll: true });
    });
  }

  function navigateEditorClick(event) {
    const editor = event.target.closest?.('.wb-editor');
    if (!editor) return;

    const collapsedSelection = editor.selectionStart === editor.selectionEnd;
    const edge = collapsedSelection
      ? referencedEdge(
          editor.dataset.wbEditor,
          editor,
          Number(editor.selectionStart || 0),
        )
      : null;

    if (edge) {
      event.stopPropagation();
      openResourceKeepingCaret(editor, edge.child_id);
      return;
    }

    const resourceId = editor.dataset.resourceId || '';
    if (!resourceId || !resourceById(resourceId)) return;
    workbench.inspectResource?.(resourceId, { reason: 'editor-resource-selected' });
  }

  function closeMenu() {
    menu?.remove();
    menu = null;
    menuScrollCloseReady = false;
  }
  function closeRenameDialog() { renameDialog?.remove(); renameDialog = null; }
  function closeDeleteDialog() { deleteDialog?.remove(); deleteDialog = null; }
  function menuItem(label, action, { disabled = false, danger = false, hint = '' } = {}) {
    if (label === '-') return '<div class="wb-context-separator"></div>';
    return `<button type="button" class="wb-context-item ${danger ? 'danger' : ''}" data-wb-context-action="${esc(action)}" ${disabled ? 'disabled' : ''}><span>${esc(label)}</span>${hint ? `<small>${esc(hint)}</small>` : ''}</button>`;
  }
  function canOpen(resource) { return resource.kind === 'document' || resource.kind === 'template' || ['section', 'function'].includes(resource.kind); }
  function openTarget(resource) { if (resource.kind === 'document') workbench.openDocument(resource.id); else workbench.openResource(resource.id); }

  function syncRenamedSource(result) {
    if (!result?.source_dirty || !result.source_resource_id) return;
    const editor = shell.querySelector(
      `.wb-editor[data-resource-id="${CSS.escape(String(result.source_resource_id))}"]`
    );
    if (!editor) return;
    const rewritten = String(result.source_content ?? '');
    if (editor.value === rewritten) return;
    editor.value = rewritten;
    editor.dispatchEvent(new InputEvent('input', {
      bubbles: true,
      inputType: 'insertReplacementText',
      data: null,
    }));
  }

  function requestRename(resource, edge) {
    return new Promise(resolve => {
      closeRenameDialog();
      const globalReference = resource.visibility === 'global';
      renameDialog = document.createElement('div');
      renameDialog.className = 'wb-template-choice-overlay';
      renameDialog.innerHTML = `
        <form class="wb-template-choice-card" data-wb-rename-form>
          <h3>${globalReference ? 'Rename Reference' : 'Rename Symbol'}</h3>
          <p>${globalReference
            ? 'Change this reference symbol. The shared Global resource keeps its canonical symbol.'
            : 'Change this symbol while preserving the resource JID, content, and relationships.'}</p>
          <label class="wb-field"><span>Symbol</span><input class="wb-filter" data-wb-rename-input autocomplete="off" spellcheck="false" value="${esc(edge.symbol || resource.symbol || '')}"></label>
          <div class="wb-template-choice-actions"><button type="button" data-wb-rename-cancel>Cancel</button><button type="submit" data-wb-rename-accept>Rename</button></div>
        </form>`;
      shell.appendChild(renameDialog);
      const input = renameDialog.querySelector('[data-wb-rename-input]');
      const finish = value => {
        closeRenameDialog();
        resolve(value);
      };
      renameDialog.querySelector('[data-wb-rename-cancel]')?.addEventListener('click', () => finish(null));
      renameDialog.querySelector('[data-wb-rename-form]')?.addEventListener('submit', event => {
        event.preventDefault();
        finish(String(input?.value || '').trim());
      });
      renameDialog.addEventListener('keydown', event => {
        if (event.key === 'Escape') {
          event.preventDefault();
          finish(null);
        }
      });
      requestAnimationFrame(() => { input?.focus(); input?.select(); });
    });
  }

  async function renameSymbol(resource, edge) {
    if (!edge) return;
    const value = await requestRename(resource, edge);
    if (value === null) return;
    const symbol = String(value).trim();
    if (!symbol || symbol === String(edge.symbol || '')) return;
    setStatus('Renaming…');
    const result = await workbench.mutate('rename-symbol', {
      reference_id: edge.id,
      resource_id: resource.id,
      child_id: resource.id,
      parent_id: edge.parent_id,
      symbol,
    });
    syncRenamedSource(result);
    setStatus(`Renamed to ${result.new_symbol || symbol}`, 'ok');
  }

  async function makeGlobal(resource) {
    setStatus('Making Global…');
    await workbench.mutate('meta', { resource_id: resource.id, visibility: 'global' });
    setStatus(`${resourceTitle(resource)} is Global`, 'ok');
  }

  async function makePrivate(resource, edge) {
    let ownerId = edge?.parent_id || '';
    if (resource.kind === 'template') ownerId = templatePrivateOwner(resource)?.id || '';
    if (!ownerId) return;
    setStatus('Making Private…');
    const result = await workbench.mutate('meta', {
      resource_id: resource.id,
      visibility: 'private',
      owner_id: ownerId,
    });
    const detached = result?.template_detached;
    if (detached) {
      setStatus(`${resourceTitle(resource)} detached as a Private Template`, 'ok');
      return;
    }
    setStatus(`${resourceTitle(resource, edge)} is Private`, 'ok');
  }

  function documentDeleteMessage(resource) {
    const document = (state().documents || []).find(item => item.id === resource.id);
    if (!document) return `Delete "${resource.name || 'Document'}"?`;
    const sections = document.sections || [];
    const functions = sections.flatMap(section => section.functions || []);
    const privateSections = sections.filter(item => item.visibility !== 'global').length;
    const privateFunctions = functions.filter(item => item.visibility !== 'global').length;
    const template = resourceById(document.template_id);
    const templateDeleted = template && template.visibility !== 'global' && templateUsage(template.id).length <= 1;
    const lines = [`Delete "${resource.name || 'Document'}"?`, '', 'This permanently deletes:', '  1 Document'];
    if (templateDeleted) lines.push('  1 private Template');
    if (privateSections) lines.push(`  ${privateSections} private Section${privateSections === 1 ? '' : 's'}`);
    if (privateFunctions) lines.push(`  ${privateFunctions} private Function${privateFunctions === 1 ? '' : 's'}`);
    lines.push('', 'Global/shared resources are preserved.');
    return lines.join('\n');
  }

  function requestDelete(resource, message, displayTitle = '') {
    return new Promise(resolve => {
      closeDeleteDialog();
      const kindLabel = `${String(resource.kind || 'resource').charAt(0).toUpperCase()}${String(resource.kind || 'resource').slice(1)}`;
      const name = displayTitle || resourceTitle(resource);
      const lines = String(message || '').split('\n');
      const impactIndex = lines.findIndex(line => line.trim() === 'This permanently deletes:');
      const impacts = [];
      const extras = [];
      let note = '';

      if (impactIndex >= 0) {
        let afterImpact = false;
        for (const raw of lines.slice(impactIndex + 1)) {
          const line = raw.trim();
          if (!line) { afterImpact = true; continue; }
          if (!afterImpact) {
            const match = line.match(/^(\d+)\s+(.+)$/);
            if (match) impacts.push({ count: match[1], label: match[2] });
            else impacts.push({ count: '', label: line });
          } else note = note ? `${note} ${line}` : line;
        }
      } else {
        for (const raw of lines.slice(1)) {
          const line = raw.trim();
          if (line) extras.push(line);
        }
      }

      deleteDialog = document.createElement('div');
      deleteDialog.className = 'wb-delete-overlay';
      deleteDialog.innerHTML = `
        <section class="wb-delete-card" role="dialog" aria-modal="true" aria-labelledby="wbDeleteTitle">
          <header class="wb-delete-head">
            <span class="wb-delete-icon" aria-hidden="true">!</span>
            <h3 id="wbDeleteTitle">Delete ${esc(kindLabel)}?</h3>
          </header>
          <div class="wb-delete-body">
            <div class="wb-delete-name">${esc(name)}</div>
            <p class="wb-delete-warning">This action cannot be undone.</p>
            ${impacts.length ? `
              <div class="wb-delete-impact-title">Permanently deletes</div>
              <ul class="wb-delete-impact">${impacts.map(item => `<li><strong>${esc(item.count)}</strong><span>${esc(item.label)}</span></li>`).join('')}</ul>` : ''}
            ${extras.map(item => `<p class="wb-delete-extra">${esc(item)}</p>`).join('')}
            ${note ? `<p class="wb-delete-note">${esc(note)}</p>` : ''}
          </div>
          <footer class="wb-delete-actions">
            <button type="button" data-wb-delete-cancel>Cancel</button>
            <button type="button" class="danger" data-wb-delete-accept>Delete ${esc(kindLabel)}</button>
          </footer>
        </section>`;
      shell.appendChild(deleteDialog);

      const finish = accepted => {
        closeDeleteDialog();
        resolve(Boolean(accepted));
      };
      const cancel = deleteDialog.querySelector('[data-wb-delete-cancel]');
      deleteDialog.querySelector('[data-wb-delete-accept]')?.addEventListener('click', () => finish(true));
      cancel?.addEventListener('click', () => finish(false));
      deleteDialog.addEventListener('mousedown', event => {
        if (event.target === deleteDialog) finish(false);
      });
      deleteDialog.addEventListener('keydown', event => {
        if (event.key === 'Escape') {
          event.preventDefault();
          finish(false);
        }
      });
      requestAnimationFrame(() => cancel?.focus());
    });
  }

  async function deleteResource(resource) {
    const relation = relationshipsFor(resource.id);
    const title = resourceTitle(resource);
    let message = `Delete "${title}"?`;
    if (resource.kind === 'document') message = documentDeleteMessage(resource);
    else if (resource.kind === 'template') {
      const usage = templateUsage(resource.id);
      if (usage.length) throw new Error(`Template is used by ${usage.length} Document${usage.length === 1 ? '' : 's'}`);
    } else if ((relation.inbound || []).length) throw new Error('Resource is still referenced');
    else {
      const childCount = (relation.outbound || []).length;
      if (childCount) message = `Delete "${title}"?\n\nIts ${childCount} private child resource${childCount === 1 ? '' : 's'} will also be deleted. Global children are preserved.`;
    }
    if (!await requestDelete(resource, message, title)) return;
    setStatus('Deleting…');
    const result = await workbench.mutate('delete', { resource_id: resource.id });
    const count = result.deleted?.length || 1;
    setStatus(`Deleted ${count} resource${count === 1 ? '' : 's'}`, 'ok');
  }

  async function copyReference(edge) {
    if (!edge) return;
    const text = `{{ ${edge.symbol} }}`;
    try { await navigator.clipboard.writeText(text); }
    catch (_) {
      const area = document.createElement('textarea'); area.value = text; area.style.position = 'fixed'; area.style.left = '-10000px';
      document.body.appendChild(area); area.select(); document.execCommand('copy'); area.remove();
    }
    setStatus(`Copied ${text}`, 'ok');
  }

  async function perform(action, resource, edge) {
    closeMenu();
    try {
      if (action === 'open') openTarget(resource);
      else if (action === 'rename-symbol') await renameSymbol(resource, edge);
      else if (action === 'copy-reference') await copyReference(edge);
      else if (action === 'make-global') await makeGlobal(resource);
      else if (action === 'make-private') await makePrivate(resource, edge);
      else if (action === 'delete') await deleteResource(resource);
    } catch (error) { setStatus(String(error.message || error), 'error'); }
  }

  function showMenu(event, resource, forcedEdge = null) {
    closeMenu();
    const relation = relationshipsFor(resource.id);
    const edge = forcedEdge || activeReference(resource);
    const inbound = relation.inbound || [];
    const sectionOrFunction = ['section', 'function'].includes(resource.kind);
    const isTemplate = resource.kind === 'template';
    const isDocument = resource.kind === 'document';
    const privateOwner = inbound.length === 1 ? inbound[0] : null;
    const usage = isTemplate ? templateUsage(resource.id) : [];
    const templateOwner = isTemplate ? templatePrivateOwner(resource) : null;
    const rows = [];
    if (canOpen(resource)) rows.push(menuItem('Open', 'open'));
    if (edge) {
      rows.push(menuItem(resource.visibility === 'global' ? 'Rename Reference…' : 'Rename Symbol…', 'rename-symbol'));
      rows.push(menuItem('Copy Reference', 'copy-reference', { hint: `{{ ${edge.symbol} }}` }));
    }
    if (sectionOrFunction || isTemplate) {
      if (rows.length) rows.push(menuItem('-'));
      if (resource.visibility === 'global') {
        if (sectionOrFunction) rows.push(menuItem('Make Private', 'make-private', {
          disabled: !privateOwner,
          hint: inbound.length > 1 ? 'Used in multiple places' : !privateOwner ? 'No owner reference' : ''
        }));
        else rows.push(menuItem('Make Private', 'make-private', {
          disabled: !templateOwner,
          hint: !templateOwner
            ? 'Open a Document using this Template'
            : usage.length > 1
              ? `Detach ${templateOwner.name || 'active Document'}`
              : templateOwner.name || ''
        }));
      } else rows.push(menuItem('Make Global', 'make-global'));
    }
    const deletable = isDocument
      || (isTemplate && usage.length === 0)
      || (sectionOrFunction && inbound.length === 0);
    if (deletable) { if (rows.length) rows.push(menuItem('-')); rows.push(menuItem('Delete', 'delete', { danger: true })); }

    menu = document.createElement('div'); menu.className = 'wb-context-menu'; menu.setAttribute('role', 'menu');
    const templateHint = isTemplate && usage.length ? ` · used by ${usage.length}` : '';
    menu.innerHTML = `<div class="wb-context-title"><span>${esc(resourceTitle(resource, edge))}</span><small>${esc(resource.kind)}${resource.state === 'orphaned' ? ' · staged' : resource.visibility ? ` · ${resource.visibility}` : ''}${esc(templateHint)}</small></div>${rows.join('')}`;
    document.body.appendChild(menu);
    const openedMenu = menu;
    menuScrollCloseReady = false;
    // A right-click can finish scrolling its target into view just after the
    // contextmenu event. Let that opening gesture settle before a scroll is
    // allowed to dismiss the menu.
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (menu === openedMenu) menuScrollCloseReady = true;
      });
    });
    const rect = menu.getBoundingClientRect();
    menu.style.left = `${Math.max(4, Math.min(event.clientX, window.innerWidth - rect.width - 6))}px`;
    menu.style.top = `${Math.max(4, Math.min(event.clientY, window.innerHeight - rect.height - 6))}px`;
    menu.querySelectorAll('[data-wb-context-action]').forEach(button => button.addEventListener('click', () => perform(button.dataset.wbContextAction, resource, edge || privateOwner)));
  }

  function contextMenu(event) {
    if (window.JawWorkbenchTransitions?.hasPending?.()) {
      event.preventDefault();
      event.stopPropagation();
      setStatus('Resolve the pending reference edit first.', 'error');
      return;
    }

    const editor = event.target.closest?.('.wb-editor');
    if (editor && editor.selectionStart === editor.selectionEnd) {
      const edge = referencedEdge(
        editor.dataset.wbEditor,
        editor,
        Number(editor.selectionStart || 0),
      );
      if (edge) {
        const resource = resourceById(edge.child_id);
        if (!resource) return;
        event.preventDefault();
        event.stopPropagation();
        openResourceKeepingCaret(editor, edge.child_id);
        showMenu(event, resource, edge);
        return;
      }
    }

    const target = targetFromElement(event.target); if (!target) return;
    const resource = resourceById(target.id) || (state().documents || []).find(item => item.id === target.id); if (!resource) return;
    const forcedEdge = target.referenceId
      ? activeReference(resource, target.referenceId)
      : null;
    event.preventDefault(); event.stopPropagation(); showMenu(event, resource, forcedEdge);
  }

  shell.addEventListener('click', navigateEditorClick, true);
  shell.addEventListener('contextmenu', contextMenu);
  document.addEventListener('pointerdown', event => { if (menu && !menu.contains(event.target)) closeMenu(); }, true);
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && menu) { event.preventDefault(); closeMenu(); }
  });
  window.addEventListener('blur', closeMenu);
  window.addEventListener('resize', closeMenu);
  shell.addEventListener('scroll', () => {
    if (menu && menuScrollCloseReady) closeMenu();
  }, true);
})();