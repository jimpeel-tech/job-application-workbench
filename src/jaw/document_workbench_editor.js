(() => {
  const page = document.getElementById('documentsPage');
  const shell = page?.querySelector('.wb-shell');
  const store = window.JawWorkbenchStore;
  if (!page || !shell || !store) return;

  const INDENT = '  ';
  const KINDS = ['template', 'section', 'function'];
  const histories = new Map();
  const working = new Map();
  const pendingInputType = new WeakMap();
  const editorIdentity = new WeakMap();
  const gutters = new Map();
  const measures = new Map();
  let changesOverlay = null;

  const esc = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[character]));

  function state() { return store.getState() || {}; }
  function resourceById(id) {
    return (state().resources || []).find(item => item.id === id) || null;
  }
  function editorFor(kind) { return shell.querySelector(`[data-wb-editor="${kind}"]`); }
  function activeResource(kind) {
    const editor = editorFor(kind);
    return editor?.dataset.resourceId ? resourceById(editor.dataset.resourceId) : null;
  }
  function savedContent(resource) { return String(resource?.content ?? ''); }
  function stateWorkingContent(resource) {
    return String(resource?.editor_content ?? resource?.content ?? '');
  }
  function workingContent(resource) {
    if (!resource) return '';
    return working.has(resource.id) ? working.get(resource.id) : stateWorkingContent(resource);
  }
  function isDirty(resource) {
    return Boolean(resource && workingContent(resource) !== savedContent(resource));
  }

  function lineStart(value, position) {
    return value.lastIndexOf('\n', Math.max(0, position - 1)) + 1;
  }

  function lineEnd(value, position) {
    const next = value.indexOf('\n', position);
    return next < 0 ? value.length : next;
  }

  function outdentLength(line) {
    if (line.startsWith('\t')) return 1;
    if (line.startsWith('  ')) return 2;
    if (line.startsWith(' ')) return 1;
    return 0;
  }

  function notifyInput(editor) {
    editor.dispatchEvent(new Event('input', { bubbles: true }));
  }

  function indentSelection(editor, shiftKey) {
    const value = editor.value;
    const start = editor.selectionStart;
    const end = editor.selectionEnd;

    if (!shiftKey && start === end) {
      editor.setRangeText(INDENT, start, end, 'end');
      notifyInput(editor);
      return;
    }

    const blockStart = lineStart(value, start);
    const effectiveEnd = end > start && value[end - 1] === '\n' ? end - 1 : end;
    const blockEnd = lineEnd(value, effectiveEnd);
    const block = value.slice(blockStart, blockEnd);
    const lines = block.split('\n');

    if (!shiftKey) {
      const replacement = lines.map(line => `${INDENT}${line}`).join('\n');
      editor.setRangeText(replacement, blockStart, blockEnd, 'preserve');
      const addedBeforeStart = start >= blockStart ? INDENT.length : 0;
      const addedBeforeEnd = INDENT.length * lines.length;
      editor.setSelectionRange(start + addedBeforeStart, end + addedBeforeEnd);
      notifyInput(editor);
      return;
    }

    const removals = lines.map(outdentLength);
    if (!removals.some(Boolean)) return;
    const replacement = lines
      .map((line, index) => line.slice(removals[index]))
      .join('\n');

    const lineStarts = [];
    let cursor = blockStart;
    for (const line of lines) {
      lineStarts.push(cursor);
      cursor += line.length + 1;
    }
    const removedBefore = position => removals.reduce(
      (total, amount, index) => total + (lineStarts[index] < position ? amount : 0),
      0
    );

    editor.setRangeText(replacement, blockStart, blockEnd, 'preserve');
    editor.setSelectionRange(
      Math.max(blockStart, start - removedBefore(start)),
      Math.max(blockStart, end - removedBefore(end))
    );
    notifyInput(editor);
  }

  function snapshot(editor) {
    return {
      value: editor.value,
      start: Number(editor.selectionStart || 0),
      end: Number(editor.selectionEnd ?? editor.selectionStart ?? 0),
    };
  }

  function historyFor(editor) {
    const id = editor.dataset.resourceId;
    if (!id) return null;
    let history = histories.get(id);
    if (!history) {
      history = {
        undo: [],
        redo: [],
        current: snapshot(editor),
        applying: false,
        lastType: '',
        lastAt: 0,
      };
      histories.set(id, history);
    }
    return history;
  }

  function identityFor(editor, resource, value = editor.value) {
    return {
      id: editor.dataset.resourceId || '',
      kind: resource?.kind || '',
      system: Boolean(resource?.settings?.system_template),
      value,
    };
  }

  function resetCurrentSnapshot(editor) {
    const id = editor.dataset.resourceId;
    if (!id) return;
    const resource = resourceById(id);
    const previous = editorIdentity.get(editor);
    const cloneReplacement = Boolean(
      previous
      && previous.id
      && previous.id !== id
      && previous.kind === 'template'
      && previous.system
      && resource?.kind === 'template'
      && resource.visibility === 'private'
      && previous.value === editor.value
    );

    if (cloneReplacement) {
      if (histories.has(previous.id) && !histories.has(id)) {
        histories.set(id, histories.get(previous.id));
        histories.delete(previous.id);
      }
      if (working.has(previous.id)) {
        working.set(id, working.get(previous.id));
        working.delete(previous.id);
      }
    }

    editorIdentity.set(editor, identityFor(editor, resource));
    working.set(id, editor.value);
    const history = historyFor(editor);
    if (history && !history.applying) history.current = snapshot(editor);
  }

  function coalesces(inputType) {
    return inputType === 'insertText'
      || inputType === 'deleteContentBackward'
      || inputType === 'deleteContentForward';
  }

  function recordInput(editor, event) {
    const id = editor.dataset.resourceId;
    if (!id) return;
    const history = historyFor(editor);
    if (!history) return;
    const next = snapshot(editor);
    working.set(id, next.value);
    editorIdentity.set(editor, identityFor(editor, resourceById(id), next.value));

    if (history.applying) {
      history.applying = false;
      history.current = next;
      history.lastType = '';
      history.lastAt = 0;
      return;
    }

    const previous = history.current;
    if (previous.value === next.value) {
      history.current = next;
      return;
    }

    const inputType = event.inputType || pendingInputType.get(editor) || 'programmatic';
    pendingInputType.delete(editor);
    const now = Date.now();
    const merge = coalesces(inputType)
      && history.lastType === inputType
      && now - history.lastAt < 700;
    if (!merge) history.undo.push(previous);
    if (history.undo.length > 300) history.undo.splice(0, history.undo.length - 300);
    history.redo = [];
    history.current = next;
    history.lastType = inputType;
    history.lastAt = now;
  }

  function applySnapshot(editor, next, history) {
    if (!next || !history) return;
    history.applying = true;
    editor.value = next.value;
    const start = Math.min(next.start, next.value.length);
    const end = Math.min(next.end, next.value.length);
    editor.setSelectionRange(start, end);
    working.set(editor.dataset.resourceId, next.value);
    notifyInput(editor);
    requestAnimationFrame(() => editor.focus());
  }

  function undo(editor) {
    const history = historyFor(editor);
    if (!history?.undo.length) return false;
    history.redo.push(snapshot(editor));
    const next = history.undo.pop();
    applySnapshot(editor, next, history);
    return true;
  }

  function redo(editor) {
    const history = historyFor(editor);
    if (!history?.redo.length) return false;
    history.undo.push(snapshot(editor));
    const next = history.redo.pop();
    applySnapshot(editor, next, history);
    return true;
  }

  function splitLines(value) {
    return String(value).split('\n');
  }

  function lineOperations(saved, current) {
    const before = splitLines(saved);
    const after = splitLines(current);
    const n = before.length;
    const m = after.length;

    if (n * m > 400000) {
      const operations = [];
      before.forEach((text, index) => operations.push({ type: 'delete', text, oldNo: index + 1, newNo: null }));
      after.forEach((text, index) => operations.push({ type: 'add', text, oldNo: null, newNo: index + 1 }));
      return operations;
    }

    const table = Array.from({ length: n + 1 }, () => new Uint32Array(m + 1));
    for (let i = n - 1; i >= 0; i -= 1) {
      for (let j = m - 1; j >= 0; j -= 1) {
        table[i][j] = before[i] === after[j]
          ? table[i + 1][j + 1] + 1
          : Math.max(table[i + 1][j], table[i][j + 1]);
      }
    }

    const operations = [];
    let i = 0;
    let j = 0;
    while (i < n || j < m) {
      if (i < n && j < m && before[i] === after[j]) {
        operations.push({ type: 'equal', text: before[i], oldNo: i + 1, newNo: j + 1 });
        i += 1;
        j += 1;
      } else if (j < m && (i >= n || table[i][j + 1] >= table[i + 1][j])) {
        operations.push({ type: 'add', text: after[j], oldNo: null, newNo: j + 1 });
        j += 1;
      } else {
        operations.push({ type: 'delete', text: before[i], oldNo: i + 1, newNo: null });
        i += 1;
      }
    }
    return operations;
  }

  function changeModel(saved, current) {
    const operations = lineOperations(saved, current);
    const markers = new Map();
    const deletedBefore = new Set();
    let deletedAfterLast = false;

    for (let cursor = 0; cursor < operations.length;) {
      if (operations[cursor].type === 'equal') {
        cursor += 1;
        continue;
      }
      const start = cursor;
      while (cursor < operations.length && operations[cursor].type !== 'equal') cursor += 1;
      const group = operations.slice(start, cursor);
      const deleted = group.filter(item => item.type === 'delete');
      const added = group.filter(item => item.type === 'add');
      const paired = Math.min(deleted.length, added.length);
      for (let index = 0; index < paired; index += 1) markers.set(added[index].newNo, 'modified');
      for (let index = paired; index < added.length; index += 1) markers.set(added[index].newNo, 'added');
      if (deleted.length > paired) {
        const next = operations.slice(cursor).find(item => item.type === 'equal');
        if (next?.newNo) deletedBefore.add(next.newNo);
        else deletedAfterLast = true;
      }
    }

    return { operations, markers, deletedBefore, deletedAfterLast };
  }

  function ensureGutter(kind) {
    if (gutters.has(kind)) return gutters.get(kind);
    const editor = editorFor(kind);
    const body = editor?.closest('.wb-editor-body');
    if (!editor || !body) return null;
    body.classList.add('wb-has-gutter');

    const gutter = document.createElement('div');
    gutter.className = 'wb-editor-gutter';
    gutter.setAttribute('aria-hidden', 'true');
    gutter.innerHTML = '<div class="wb-editor-gutter-content"></div>';
    body.appendChild(gutter);

    const measure = document.createElement('div');
    measure.className = 'wb-editor-line-measure';
    measure.setAttribute('aria-hidden', 'true');
    body.appendChild(measure);

    const value = { gutter, content: gutter.firstElementChild, measure };
    gutters.set(kind, value);
    measures.set(kind, measure);
    return value;
  }

  function lineHeights(kind, editor, lines) {
    const computed = getComputedStyle(editor);
    const lineHeight = parseFloat(computed.lineHeight) || 19.5;
    if (!shell.classList.contains('wb-word-wrap')) return lines.map(() => lineHeight);

    const measure = measures.get(kind);
    if (!measure) return lines.map(() => lineHeight);
    const left = parseFloat(computed.paddingLeft) || 0;
    const right = parseFloat(computed.paddingRight) || 0;
    measure.style.width = `${Math.max(1, editor.clientWidth - left - right)}px`;
    measure.innerHTML = '';
    const fragment = document.createDocumentFragment();
    for (const line of lines) {
      const row = document.createElement('div');
      row.textContent = line || '\u00a0';
      fragment.appendChild(row);
    }
    measure.appendChild(fragment);
    return [...measure.children].map(row => Math.max(lineHeight, row.getBoundingClientRect().height));
  }

  function renderGutter(kind) {
    const editor = editorFor(kind);
    const resource = activeResource(kind);
    const parts = ensureGutter(kind);
    if (!editor || !parts) return;
    if (!resource || editor.disabled || !editor.dataset.resourceId) {
      parts.content.innerHTML = '';
      return;
    }

    working.set(resource.id, editor.value);
    const lines = splitLines(editor.value);
    const model = changeModel(savedContent(resource), editor.value);
    const digits = Math.max(2, String(lines.length).length);
    editor.closest('.wb-editor-body')?.style.setProperty('--wb-gutter-width', `${28 + digits * 8}px`);
    const heights = lineHeights(kind, editor, lines);

    parts.content.innerHTML = lines.map((_, index) => {
      const line = index + 1;
      const marker = model.markers.get(line) || '';
      const deleted = model.deletedBefore.has(line) ? ' deleted-before' : '';
      const trailing = model.deletedAfterLast && line === lines.length ? ' deleted-after' : '';
      return `<div class="wb-gutter-line ${marker}${deleted}${trailing}" style="height:${heights[index]}px"><span class="wb-gutter-change"></span><span class="wb-gutter-number">${line}</span></div>`;
    }).join('');
    parts.content.style.transform = `translateY(${-editor.scrollTop}px)`;
  }

  function setDirtyMarker(element, dirty) {
    if (!element) return;
    let marker = [...element.children].find(child => child.classList?.contains('wb-dirty')) || null;
    if (dirty && !marker) {
      marker = document.createElement('i');
      marker.className = 'wb-dirty';
      marker.textContent = '●';
      const close = [...element.children].find(child => child.matches?.('[data-wb-close-doc],[data-wb-close-tab]'));
      element.insertBefore(marker, close || null);
    } else if (!dirty && marker) {
      marker.remove();
    }
  }

  function documentDirty(document) {
    const template = resourceById(document.template_id || document.template?.id);
    if (isDirty(template)) return true;
    for (const section of document.sections || []) {
      const sectionResource = resourceById(section.id) || section;
      if (isDirty(sectionResource)) return true;
      for (const fn of section.functions || []) {
        if (isDirty(resourceById(fn.id) || fn)) return true;
      }
    }
    return false;
  }

  function syncDirtyIndicators() {
    const next = state();
    for (const resource of next.resources || []) {
      if (resource.kind === 'document') continue;
      const dirty = isDirty(resource);
      const id = CSS.escape(resource.id);
      shell.querySelectorAll(`[data-wb-resource-tab="${id}"],[data-wb-open-resource="${id}"]`)
        .forEach(element => setDirtyMarker(element, dirty));
    }
    for (const document of next.documents || []) {
      const dirty = documentDirty(document);
      const id = CSS.escape(document.id);
      shell.querySelectorAll(`[data-wb-doc-tab="${id}"],[data-wb-open-doc="${id}"]`)
        .forEach(element => setDirtyMarker(element, dirty));
    }
    renderChangesButtons();
  }

  function ensureChangesButton(kind) {
    const pane = shell.querySelector(`[data-wb-pane="${kind}"]`);
    const tabs = pane?.querySelector(`[data-wb-tabs="${kind}"]`);
    if (!pane || !tabs) return null;
    let button = pane.querySelector(`[data-wb-changes="${kind}"]`);
    if (!button) {
      button = document.createElement('button');
      button.type = 'button';
      button.className = 'wb-pane-changes';
      button.dataset.wbChanges = kind;
      button.textContent = 'Changes';
      button.addEventListener('click', event => {
        event.stopPropagation();
        openChanges(kind);
      });
      tabs.insertAdjacentElement('afterend', button);
    }
    return button;
  }

  function renderChangesButtons() {
    for (const kind of KINDS) {
      const button = ensureChangesButton(kind);
      if (!button) continue;
      const resource = activeResource(kind);
      const dirty = isDirty(resource);
      button.hidden = !resource;
      button.disabled = !dirty;
      button.classList.toggle('active', dirty);
      button.title = dirty ? 'Compare Saved and Working content' : 'No unsaved changes';
    }
  }

  function diffRanges(operations, context = 3) {
    const changed = [];
    operations.forEach((operation, index) => {
      if (operation.type !== 'equal') changed.push(index);
    });
    if (!changed.length) return [];
    const ranges = [];
    for (const index of changed) {
      const start = Math.max(0, index - context);
      const end = Math.min(operations.length - 1, index + context);
      const previous = ranges.at(-1);
      if (previous && start <= previous.end + 1) previous.end = Math.max(previous.end, end);
      else ranges.push({ start, end });
    }
    return ranges;
  }

  function diffHtml(saved, current) {
    const operations = lineOperations(saved, current);
    const ranges = diffRanges(operations);
    if (!ranges.length) return '<div class="wb-changes-empty">Working content matches Saved content.</div>';
    return ranges.map(range => {
      const rows = operations.slice(range.start, range.end + 1);
      const firstOld = rows.find(item => item.oldNo)?.oldNo || 0;
      const firstNew = rows.find(item => item.newNo)?.newNo || 0;
      const body = rows.map(item => {
        const prefix = item.type === 'add' ? '+' : item.type === 'delete' ? '-' : ' ';
        return `<div class="wb-diff-line ${item.type}"><span class="wb-diff-old">${item.oldNo || ''}</span><span class="wb-diff-new">${item.newNo || ''}</span><span class="wb-diff-prefix">${prefix}</span><code>${esc(item.text)}</code></div>`;
      }).join('');
      return `<div class="wb-diff-hunk"><div class="wb-diff-header">@@ -${firstOld} +${firstNew} @@</div>${body}</div>`;
    }).join('');
  }

  function closeChanges() {
    changesOverlay?.remove();
    changesOverlay = null;
  }

  function revertAll(kind) {
    const editor = editorFor(kind);
    const resource = activeResource(kind);
    if (!editor || !resource) return;
    const cursor = Math.min(editor.selectionStart || 0, savedContent(resource).length);
    editor.value = savedContent(resource);
    editor.setSelectionRange(cursor, cursor);
    notifyInput(editor);
    closeChanges();
    requestAnimationFrame(() => editor.focus());
  }

  function openChanges(kind) {
    const editor = editorFor(kind);
    const resource = activeResource(kind);
    if (!editor || !resource) return;
    closeChanges();
    changesOverlay = document.createElement('div');
    changesOverlay.className = 'wb-changes-overlay';
    changesOverlay.innerHTML = `
      <div class="wb-changes-card" role="dialog" aria-modal="true" aria-label="Changes for ${esc(resource.name || resource.symbol || kind)}">
        <div class="wb-changes-head"><div><strong>${esc(resource.name || resource.symbol || kind)}</strong><span>Saved ↔ Working</span></div><button type="button" data-wb-changes-close aria-label="Close">×</button></div>
        <div class="wb-changes-diff">${diffHtml(savedContent(resource), editor.value)}</div>
        <div class="wb-changes-actions"><button type="button" data-wb-changes-revert ${isDirty(resource) ? '' : 'disabled'}>Revert All</button><button type="button" data-wb-changes-close>Close</button></div>
      </div>`;
    shell.appendChild(changesOverlay);
    changesOverlay.addEventListener('mousedown', event => {
      if (event.target === changesOverlay) closeChanges();
    });
    changesOverlay.querySelectorAll('[data-wb-changes-close]').forEach(button => button.addEventListener('click', closeChanges));
    changesOverlay.querySelector('[data-wb-changes-revert]')?.addEventListener('click', () => revertAll(kind));
  }

  function renderEditorState(kind) {
    renderGutter(kind);
    syncDirtyIndicators();
  }

  function syncFromStore(_snapshot, reason = '') {
    const displayedIds = new Set();
    for (const kind of KINDS) {
      const editor = editorFor(kind);
      const id = editor?.dataset.resourceId;
      if (!editor || !id) continue;
      displayedIds.add(id);
      const identity = editorIdentity.get(editor);
      if (!identity || identity.id !== id) {
        resetCurrentSnapshot(editor);
        continue;
      }
      working.set(id, editor.value);
      if (reason !== 'editor-input') {
        const history = historyFor(editor);
        if (history && history.current.value !== editor.value && !history.applying) {
          history.current = snapshot(editor);
          history.lastType = '';
        }
      }
    }

    if (!['editor-input', 'resource-selected', 'document-selected'].includes(reason)) {
      for (const resource of state().resources || []) {
        if (!displayedIds.has(resource.id)) working.set(resource.id, stateWorkingContent(resource));
      }
    }
    const valid = new Set((state().resources || []).map(item => item.id));
    for (const id of [...working.keys()]) if (!valid.has(id)) working.delete(id);
    for (const id of [...histories.keys()]) if (!valid.has(id)) histories.delete(id);

    requestAnimationFrame(() => {
      for (const kind of KINDS) renderEditorState(kind);
    });
  }

  function installEditor(kind) {
    const editor = editorFor(kind);
    if (!editor) return;
    ensureGutter(kind);
    ensureChangesButton(kind);
    resetCurrentSnapshot(editor);

    editor.addEventListener('beforeinput', event => {
      pendingInputType.set(editor, event.inputType || 'programmatic');
    });
    // Capture the edit before the Workbench controller's bubbling input listener
    // publishes state. Otherwise a synchronous store render can advance the
    // history baseline to the new value before we have recorded the old value.
    editor.addEventListener('input', event => {
      recordInput(editor, event);
      requestAnimationFrame(() => renderEditorState(kind));
    }, true);
    editor.addEventListener('scroll', () => {
      const parts = gutters.get(kind);
      if (parts) parts.content.style.transform = `translateY(${-editor.scrollTop}px)`;
    });
    editor.addEventListener('focus', () => resetCurrentSnapshot(editor));

    new MutationObserver(mutations => {
      if (!mutations.some(mutation => mutation.attributeName === 'data-resource-id')) return;
      resetCurrentSnapshot(editor);
      requestAnimationFrame(() => renderEditorState(kind));
    }).observe(editor, { attributes: true, attributeFilter: ['data-resource-id'] });
  }

  page.addEventListener('keydown', event => {
    if (event.key === 'Escape' && changesOverlay) {
      event.preventDefault();
      closeChanges();
      return;
    }
    const editor = event.target.closest?.('.wb-shell .wb-editor');
    if (!editor) return;
    const command = event.ctrlKey || event.metaKey;
    const key = event.key.toLowerCase();
    if (command && key === 'z') {
      event.preventDefault();
      if (event.shiftKey) redo(editor);
      else undo(editor);
      return;
    }
    if (command && key === 'y') {
      event.preventDefault();
      redo(editor);
      return;
    }
    if (event.key !== 'Tab' || command || event.altKey) return;
    event.preventDefault();
    indentSelection(editor, event.shiftKey);
  });

  for (const kind of KINDS) installEditor(kind);
  store.subscribe(syncFromStore);
  window.addEventListener('resize', () => requestAnimationFrame(() => KINDS.forEach(renderGutter)));
  window.addEventListener('pointerup', () => requestAnimationFrame(() => KINDS.forEach(renderGutter)));
  requestAnimationFrame(() => KINDS.forEach(renderEditorState));
})();
