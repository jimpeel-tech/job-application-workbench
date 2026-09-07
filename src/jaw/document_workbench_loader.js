(() => {
  const page = document.getElementById('documentsPage');
  if (!page) return;
  const shell = page.querySelector('.wb-shell');
  if (shell) shell.hidden = true;

  const scripts = [
    '/document-workbench.js',
    '/document-workbench-workspace.js',
    '/document-workbench-intelligence.js',
    '/document-workbench-reference-ids.js',
    '/document-workbench-multi-reference.js',
    '/document-workbench-resources.js',
    '/document-workbench-editor.js',
    '/document-workbench-transitions.js',
    '/document-workbench-repository.js',
    '/document-workbench-preview.js'
  ];
  let loading = null;
  let loaded = false;
  let explorerDecorationInstalled = false;
  let relationshipDecorationInstalled = false;
  let dragDropPolishInstalled = false;

  function active() {
    return page.classList.contains('active');
  }

  function normalizeTopbarControls() {
    const topbar = page.querySelector('.wb-topbar');
    const tabs = document.getElementById('wbDocumentTabs');
    const actions = page.querySelector('.wb-template-actions')
      || page.querySelector('.wb-top-right');
    if (!topbar || !tabs || !actions) return;

    tabs.classList.remove('wb-template-document-tabs');
    actions.classList.remove('wb-template-actions');
    actions.classList.add('wb-top-right');

    if (tabs.parentElement !== topbar) {
      topbar.insertBefore(tabs, actions.parentElement === topbar ? actions : null);
    }
    if (actions.parentElement !== topbar) topbar.appendChild(actions);
  }

  function normalizeExplorer() {
    const explorer = document.getElementById('wbExplorer');
    if (!explorer) return;

    const kindLabels = {
      document: 'Doc',
      template: 'Temp',
      section: 'Sect',
      function: 'Func',
    };

    for (const row of explorer.querySelectorAll('.wb-tree-row')) {
      for (const toggle of row.querySelectorAll(':scope > .wb-chevron')) {
        const value = String(toggle.textContent || '').trim();
        if (value === '⌄') toggle.textContent = '▾';
        else if (value === '›') toggle.textContent = '▸';
      }

      if (row.classList.contains('folder')) continue;

      let kind = row.dataset.wbOpenDoc ? 'document' : '';
      if (!kind) {
        const marker = row.querySelector(':scope > .wb-kind-dot');
        if (marker) {
          kind = Object.keys(kindLabels).find(name => marker.classList.contains(name)) || '';
        }
      }
      if (!kind) continue;

      const label = row.querySelector(':scope > .wb-tree-label');
      if (kind === 'template' && label) {
        label.textContent = String(label.textContent || '').replace(/^Template\s*·\s*/i, '');
      }

      let type = row.querySelector(':scope > .wb-tree-kind');
      if (!type) {
        type = document.createElement('span');
        type.className = 'wb-tree-kind';
        row.appendChild(type);
      }
      if (type.textContent !== kindLabels[kind]) type.textContent = kindLabels[kind];
    }
  }

  function scheduleExplorerNormalization() {
    requestAnimationFrame(normalizeExplorer);
  }

  function installExplorerDecoration() {
    if (explorerDecorationInstalled) return;
    const explorer = document.getElementById('wbExplorer');
    const store = window.JawWorkbenchStore;
    if (!explorer || !store) return;

    explorerDecorationInstalled = true;
    explorer.addEventListener('click', scheduleExplorerNormalization);
    store.subscribe(scheduleExplorerNormalization);
    normalizeExplorer();
  }

  function decorateRelationships() {
    const relationships = document.getElementById('wbRelationships');
    const store = window.JawWorkbenchStore;
    if (!relationships || !store) return;

    const selectedResourceId = String(store.getSelectedResourceId?.() || '');
    const relation = store.getState()?.relationships?.[selectedResourceId]
      || { inbound: [], outbound: [] };
    const inbound = relation.inbound || [];
    const outbound = relation.outbound || [];
    const targets = [
      ...inbound.map(edge => ({
        edge,
        resourceId: String(edge.child_id || selectedResourceId),
        direction: 'inbound',
      })),
      ...outbound.map(edge => ({
        edge,
        resourceId: String(edge.child_id || ''),
        direction: 'outbound',
      })),
    ];
    const rows = [...relationships.querySelectorAll('.wb-relations > div')];

    for (const [index, row] of rows.entries()) {
      delete row.dataset.wbReferenceJid;
      delete row.dataset.wbSelectResource;
      delete row.dataset.wbRelationshipDirection;
      const target = targets[index];
      if (!target?.edge?.id || !target.resourceId) continue;
      row.dataset.wbReferenceJid = String(target.edge.id);
      row.dataset.wbSelectResource = target.resourceId;
      row.dataset.wbRelationshipDirection = target.direction;
    }
  }

  function scheduleRelationshipDecoration() {
    requestAnimationFrame(decorateRelationships);
  }

  function installRelationshipDecoration() {
    if (relationshipDecorationInstalled) return;
    const relationships = document.getElementById('wbRelationships');
    const store = window.JawWorkbenchStore;
    if (!relationships || !store) return;

    relationshipDecorationInstalled = true;
    store.subscribe(scheduleRelationshipDecoration);
    decorateRelationships();
  }

  function integrateMultiReferencePending() {
    const multi = window.JawWorkbenchMultiReference;
    const transitions = window.JawWorkbenchTransitions;
    if (!multi || !transitions || transitions.__jawMultiReferenceWrapped) return;
    const baseHasPending = transitions.hasPending;
    transitions.hasPending = () => Boolean(multi.hasPending?.()) || Boolean(baseHasPending?.());
    transitions.__jawMultiReferenceWrapped = true;
  }

  function hideDropCarets() {
    page.querySelectorAll('[data-wb-drop-caret]').forEach(caret => {
      caret.hidden = true;
    });
    page.querySelectorAll('.wb-editor').forEach(editor => {
      delete editor.dataset.wbDropPosition;
    });
  }

  function caretRangeAtPoint(clientX, clientY) {
    if (typeof document.caretRangeFromPoint === 'function') {
      return document.caretRangeFromPoint(clientX, clientY);
    }
    if (typeof document.caretPositionFromPoint !== 'function') return null;
    const position = document.caretPositionFromPoint(clientX, clientY);
    if (!position?.offsetNode) return null;
    const range = document.createRange();
    range.setStart(position.offsetNode, position.offset);
    range.collapse(true);
    return range;
  }

  function mirrorCaretRect(textNode, offset, mirror, lineHeight) {
    const collapsed = document.createRange();
    collapsed.setStart(textNode, Math.min(offset, textNode.length));
    collapsed.collapse(true);
    const direct = collapsed.getBoundingClientRect();
    if (direct.height) return direct;

    if (textNode.length) {
      const probe = document.createRange();
      if (offset < textNode.length) {
        probe.setStart(textNode, offset);
        probe.setEnd(textNode, offset + 1);
        const next = probe.getBoundingClientRect();
        if (next.height) {
          return {
            left: next.left,
            top: next.top,
            right: next.left,
            bottom: next.bottom,
            width: 0,
            height: next.height,
          };
        }
      } else {
        probe.setStart(textNode, textNode.length - 1);
        probe.setEnd(textNode, textNode.length);
        const previous = probe.getBoundingClientRect();
        if (previous.height) {
          return {
            left: previous.right,
            top: previous.top,
            right: previous.right,
            bottom: previous.bottom,
            width: 0,
            height: previous.height,
          };
        }
      }
    }

    const mirrorRect = mirror.getBoundingClientRect();
    return {
      left: mirrorRect.left,
      top: mirrorRect.top,
      right: mirrorRect.left,
      bottom: mirrorRect.top + lineHeight,
      width: 0,
      height: lineHeight,
    };
  }

  function mirrorDropPoint(editor, event) {
    const body = editor.closest('.wb-editor-body');
    if (!body) return null;

    const style = getComputedStyle(editor);
    const editorRect = editor.getBoundingClientRect();
    const bodyRect = body.getBoundingClientRect();
    const paddingTop = parseFloat(style.paddingTop) || 0;
    const paddingRight = parseFloat(style.paddingRight) || 0;
    const paddingBottom = parseFloat(style.paddingBottom) || 0;
    const paddingLeft = parseFloat(style.paddingLeft) || 0;
    const lineHeight = parseFloat(style.lineHeight) || 19.5;
    const contentWidth = Math.max(1, editor.clientWidth - paddingLeft - paddingRight);
    const contentHeight = Math.max(
      lineHeight,
      editor.scrollHeight - paddingTop - paddingBottom,
      editor.clientHeight - paddingTop - paddingBottom
    );

    const mirror = document.createElement('div');
    mirror.setAttribute('aria-hidden', 'true');
    Object.assign(mirror.style, {
      position: 'fixed',
      left: `${editorRect.left + paddingLeft - editor.scrollLeft}px`,
      top: `${editorRect.top + paddingTop - editor.scrollTop}px`,
      width: `${contentWidth}px`,
      height: `${contentHeight}px`,
      margin: '0',
      padding: '0',
      border: '0',
      boxSizing: 'content-box',
      fontFamily: style.fontFamily,
      fontSize: style.fontSize,
      fontStyle: style.fontStyle,
      fontWeight: style.fontWeight,
      fontStretch: style.fontStretch,
      fontVariant: style.fontVariant,
      lineHeight: style.lineHeight,
      letterSpacing: style.letterSpacing,
      textAlign: style.textAlign,
      textIndent: style.textIndent,
      textTransform: style.textTransform,
      tabSize: style.tabSize,
      whiteSpace: style.whiteSpace,
      overflowWrap: style.overflowWrap,
      wordBreak: style.wordBreak,
      direction: style.direction,
      unicodeBidi: style.unicodeBidi,
      color: 'transparent',
      background: 'transparent',
      overflow: 'visible',
      pointerEvents: 'auto',
      zIndex: '2147483647',
    });

    const source = editor.value;
    const textNode = document.createTextNode(source || '\u200b');
    mirror.appendChild(textNode);
    document.body.appendChild(mirror);

    try {
      const hit = caretRangeAtPoint(event.clientX, event.clientY);
      if (!hit || !mirror.contains(hit.startContainer)) return null;

      let offset = 0;
      if (hit.startContainer === textNode) {
        offset = hit.startOffset;
      } else if (hit.startContainer === mirror) {
        offset = hit.startOffset > 0 ? source.length : 0;
      } else {
        const prefix = document.createRange();
        prefix.setStart(textNode, 0);
        prefix.setEnd(hit.startContainer, hit.startOffset);
        offset = prefix.toString().length;
      }
      offset = Math.max(0, Math.min(source.length, offset));

      const visual = mirrorCaretRect(textNode, offset, mirror, lineHeight);
      const minLeft = editorRect.left + paddingLeft - bodyRect.left;
      const maxLeft = editorRect.right - paddingRight - bodyRect.left;
      return {
        position: offset,
        left: Math.max(minLeft, Math.min(maxLeft, visual.left - bodyRect.left)),
        top: visual.top - bodyRect.top,
        height: visual.height || lineHeight,
      };
    } finally {
      mirror.remove();
    }
  }

  function updateDropCaret(editor, event) {
    const caret = editor.closest('.wb-editor-body')?.querySelector('[data-wb-drop-caret]');
    if (!caret) return;

    hideDropCarets();
    const point = mirrorDropPoint(editor, event);
    if (!point) return;

    editor.dataset.wbDropPosition = String(point.position);
    caret.style.left = `${point.left}px`;
    caret.style.top = `${point.top}px`;
    caret.style.height = `${point.height}px`;
    caret.hidden = false;
  }

  function installDragDropPolish() {
    if (dragDropPolishInstalled) return;
    const shell = page.querySelector('.wb-shell');
    if (!shell) return;
    dragDropPolishInstalled = true;

    shell.addEventListener('dragstart', event => {
      const item = event.target.closest?.('[data-wb-jaw],[data-wb-drag-resource]');
      if (!item || !event.dataTransfer) return;

      const payload = item.dataset.wbJaw
        ? { source: 'jaw', expression: item.dataset.wbJaw }
        : { source: 'resource', resource_id: item.dataset.wbDragResource };
      event.dataTransfer.effectAllowed = 'copyMove';
      event.dataTransfer.setData('application/x-jaw-workbench', JSON.stringify(payload));

      const ghost = document.createElement('div');
      ghost.className = 'wb-drag-ghost';
      ghost.textContent = String(item.textContent || '').trim();
      document.body.appendChild(ghost);
      try { event.dataTransfer.setDragImage(ghost, 8, -6); }
      catch (_) { event.dataTransfer.setDragImage(ghost, 8, 0); }
      requestAnimationFrame(() => ghost.remove());
    });

    for (const editor of shell.querySelectorAll('.wb-editor')) {
      editor.addEventListener('dragover', event => {
        const types = [...(event.dataTransfer?.types || [])];
        if (!types.includes('application/x-jaw-workbench')) return;
        event.preventDefault();
        event.dataTransfer.dropEffect = 'copy';
        updateDropCaret(editor, event);
      });
      editor.addEventListener('dragleave', event => {
        const body = editor.closest('.wb-editor-body');
        if (!body?.contains(event.relatedTarget)) hideDropCarets();
      });
      editor.addEventListener('drop', () => {
        const raw = editor.dataset.wbDropPosition;
        if (raw === undefined) return;
        const position = Math.max(0, Math.min(editor.value.length, Number(raw) || 0));
        try { editor.setSelectionRange(position, position); } catch (_) { /* noop */ }
      }, true);
      editor.addEventListener('drop', hideDropCarets);
    }

    shell.addEventListener('dragend', hideDropCarets);
    window.addEventListener('drop', hideDropCarets);
    window.addEventListener('blur', hideDropCarets);
  }

  function loadScriptAttempt(src) {
  return new Promise((resolve, reject) => {
    const loaded = [...document.scripts].find(script => (
      script.dataset.jawWorkbenchSrc === src
      && script.dataset.jawWorkbenchLoaded === 'true'
    ));
    if (loaded) {
      resolve();
      return;
    }
    for (const stale of document.querySelectorAll('script[data-jaw-workbench-src]')) {
      if (stale.dataset.jawWorkbenchSrc === src) stale.remove();
    }
    const script = document.createElement('script');
    script.src = src;
    script.async = false;
    script.dataset.jawWorkbenchSrc = src;
    script.addEventListener('load', () => {
      script.dataset.jawWorkbenchLoaded = 'true';
      resolve();
    }, { once: true });
    script.addEventListener('error', () => {
      script.remove();
      reject(new Error(`Failed to load ${src}`));
    }, { once: true });
    document.body.appendChild(script);
  });
}

async function loadScript(src) {
  try {
    await loadScriptAttempt(src);
  } catch (firstError) {
    console.warn(`Retrying Workbench module ${src}`, firstError);
    await loadScriptAttempt(src);
  }
}

  async function ensureLoaded() {
    if (!active()) return false;
    if (loaded) {
      normalizeTopbarControls();
      installExplorerDecoration();
      installRelationshipDecoration();
      installDragDropPolish();
      integrateMultiReferencePending();
      await window.JawDocumentWorkbench?.load?.();
      scheduleExplorerNormalization();
      scheduleRelationshipDecoration();
      if (shell) shell.hidden = false;
      return true;
    }
    if (loading) return loading;
    loading = (async () => {
      for (const src of scripts) {
        await loadScript(src);
        if (src === '/document-workbench.js') normalizeTopbarControls();
      }
      normalizeTopbarControls();
      installExplorerDecoration();
      installRelationshipDecoration();
      installDragDropPolish();
      integrateMultiReferencePending();
      scheduleExplorerNormalization();
      scheduleRelationshipDecoration();
      loaded = true;
      if (shell) shell.hidden = false;
      return true;
    })().catch(error => {
      console.error(error);
      if (shell) shell.hidden = false;
      const toast = document.getElementById('toast');
      if (toast) {
        toast.textContent = error.message;
        toast.style.display = 'block';
      }
      return false;
    }).finally(() => {
      loading = null;
    });
    return loading;
  }

  window.JawWorkbenchLoader = { ensureLoaded, isLoaded: () => loaded };

  // dashboard.js applies the initial hash before this lazy loader is defined.
  // If that initial route is Documents, mount once now. Future activation is
  // driven directly by the dashboard route handler and explicit user switches.
  if (active()) void ensureLoaded();
})();