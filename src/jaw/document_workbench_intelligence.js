(() => {
  const shell = document.querySelector('.wb-shell');
  const store = window.JawWorkbenchStore;
  if (!shell || !store) return;

  const KINDS = ['template', 'section', 'function'];
  const JAW_ROOTS = new Set([
    'user', 'job_ref', 'work_exp', 'cap', 'system', 'csv', 'latex_raw', 'dump', 'describe'
  ]);
  const JINJA_KEYWORDS = new Set([
    'and', 'as', 'block', 'else', 'elif', 'endblock', 'endfilter', 'endfor', 'endif',
    'endmacro', 'endraw', 'endset', 'endwith', 'false', 'filter', 'for', 'if', 'in',
    'is', 'macro', 'none', 'not', 'or', 'raw', 'recursive', 'set', 'true', 'with'
  ]);

  const mirrors = new Map();
  const activeSymbols = new Map();
  const diagnostics = new Map();

  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[character]));
  const lower = value => String(value ?? '').trim().toLowerCase();

  function state() { return store.getState() || {}; }
  function editorFor(kind) { return shell.querySelector(`[data-wb-editor="${kind}"]`); }
  function resourceById(id) { return (state().resources || []).find(item => item.id === id) || null; }

  function parentIdFor(kind, editor) {
    if (kind === 'template') return store.getActiveDocumentId() || '';
    if (kind === 'section') return editor?.dataset.resourceId || '';
    return '';
  }

  function relationMap(kind, editor) {
    const parentId = parentIdFor(kind, editor);
    const map = new Map();
    if (!parentId) return map;
    for (const edge of state().relationships?.[parentId]?.outbound || []) {
      const child = resourceById(edge.child_id);
      if (child && !map.has(String(edge.symbol || ''))) {
        map.set(String(edge.symbol || ''), child);
      }
    }
    return map;
  }

  function blankPreservingLines(value) {
    return String(value).replace(/[^\n]/g, ' ');
  }

  function maskIgnoredRegions(source) {
    let masked = String(source || '');
    masked = masked.replace(/\{%\s*raw\s*%\}[\s\S]*?\{%\s*endraw\s*%\}/g, blankPreservingLines);
    masked = masked.replace(/\{#[\s\S]*?#\}/g, blankPreservingLines);
    return masked;
  }

  function sourceLocals(source) {
    const locals = new Set();
    const generated = new Set();
    const searchable = maskIgnoredRegions(source);
    for (const match of searchable.matchAll(/\{%\s*set\s+([A-Za-z_][A-Za-z0-9_]*)/g)) {
      locals.add(match[1]);
    }
    for (const match of searchable.matchAll(/\{%\s*for\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\b/g)) {
      locals.add(match[1]);
    }
    for (const match of searchable.matchAll(/<([A-Za-z_][A-Za-z0-9_]*)(?::(?:text|list))?>/g)) {
      generated.add(match[1]);
    }
    return { locals, generated };
  }

  function tokenClass(token, relationResources, locals, generated) {
    const root = String(token).split('.')[0];
    if (relationResources.has(root)) {
      const resource = relationResources.get(root);
      if (resource.state === 'orphaned') return 'wb-syn-orphan';
      return resource.visibility === 'global' ? 'wb-syn-global' : 'wb-syn-private';
    }
    if (JAW_ROOTS.has(root)) return 'wb-syn-jaw';
    if (generated.has(root)) return 'wb-syn-generated';
    if (locals.has(root)) return 'wb-syn-local';
    if (JINJA_KEYWORDS.has(root)) return 'wb-syn-keyword';
    return 'wb-syn-unresolved';
  }

  function highlightCode(code, context) {
    const expression = /\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*\b/g;
    let html = '';
    let cursor = 0;
    for (const match of code.matchAll(expression)) {
      html += escapeHtml(code.slice(cursor, match.index));
      const token = match[0];
      const root = token.split('.')[0];
      const classes = [tokenClass(token, context.relations, context.locals, context.generated)];
      if (activeSymbols.get(context.kind) === root) classes.push('wb-syn-active-ref');
      html += `<span class="${classes.filter(Boolean).join(' ')}" data-wb-syntax-symbol="${escapeHtml(root)}">${escapeHtml(token)}</span>`;
      cursor = (match.index || 0) + token.length;
    }
    html += escapeHtml(code.slice(cursor));
    return html;
  }

  function highlightSource(kind, editor) {
    const source = editor.value || '';
    const relations = relationMap(kind, editor);
    const { locals, generated } = sourceLocals(source);
    const context = { kind, relations, locals, generated };
    const tokenPattern = /(\{%\s*raw\s*%\}[\s\S]*?\{%\s*endraw\s*%\}|\{#[\s\S]*?#\}|\{\{[\s\S]*?\}\}|\{%[\s\S]*?%\}|<\/>|<[A-Za-z_][A-Za-z0-9_]*(?::(?:text|list))?>)/g;
    let html = '';
    let cursor = 0;
    for (const match of source.matchAll(tokenPattern)) {
      const token = match[0];
      html += escapeHtml(source.slice(cursor, match.index));
      if (/^\{%\s*raw\s*%\}/.test(token)) {
        html += escapeHtml(token);
      } else if (token.startsWith('{#')) {
        html += `<span class="wb-syn-comment">${escapeHtml(token)}</span>`;
      } else if (token.startsWith('{{')) {
        html += `<span class="wb-syn-delimiter">{{</span>${highlightCode(token.slice(2, -2), context)}<span class="wb-syn-delimiter">}}</span>`;
      } else if (token.startsWith('{%')) {
        html += `<span class="wb-syn-delimiter">{%</span>${highlightCode(token.slice(2, -2), context)}<span class="wb-syn-delimiter">%}</span>`;
      } else if (token === '</>') {
        html += '<span class="wb-syn-generation-tag">&lt;/&gt;</span>';
      } else {
        const open = token.match(/^<([A-Za-z_][A-Za-z0-9_]*)(?::(text|list))?>$/);
        const name = open?.[1] || '';
        const type = open?.[2] || '';
        const root = name;
        const active = activeSymbols.get(kind) === root ? ' wb-syn-active-ref' : '';
        html += `<span class="wb-syn-generation-tag">&lt;<span class="wb-syn-generated${active}" data-wb-syntax-symbol="${escapeHtml(root)}">${escapeHtml(name)}</span>${type ? `:<span class="wb-syn-generation-type">${escapeHtml(type)}</span>` : ''}&gt;</span>`;
      }
      cursor = (match.index || 0) + token.length;
    }
    html += escapeHtml(source.slice(cursor));
    return html || ' ';
  }

  function syncMirror(kind) {
    const editor = editorFor(kind);
    const mirror = mirrors.get(kind);
    if (!editor || !mirror) return;
    mirror.innerHTML = highlightSource(kind, editor);
    mirror.scrollTop = editor.scrollTop;
    mirror.scrollLeft = editor.scrollLeft;
    const wrapped = shell.classList.contains('wb-word-wrap');
    mirror.classList.toggle('wrapped', wrapped);
    mirror.classList.toggle('nowrap', !wrapped);
    editor.closest('.wb-editor-body')?.classList.add('wb-intelligence-ready');
  }

  function syncAllMirrors() {
    for (const kind of KINDS) syncMirror(kind);
  }

  function lineAt(source, index) {
    return source.slice(0, Math.max(0, index)).split('\n').length;
  }

  function openingDelimiterProblems(source, open, close, label) {
    const problems = [];
    let cursor = 0;
    while (cursor < source.length) {
      const start = source.indexOf(open, cursor);
      if (start < 0) break;
      const end = source.indexOf(close, start + open.length);
      if (end < 0) {
        problems.push({ index: start, message: `Missing ${close}` });
        break;
      }
      const nested = source.indexOf(open, start + open.length);
      if (nested >= 0 && nested < end) problems.push({ index: nested, message: `Nested ${label} delimiter` });
      cursor = end + close.length;
    }
    return problems;
  }

  function generationProblems(source, kind) {
    const problems = [];
    const searchable = maskIgnoredRegions(source);
    const tags = [...searchable.matchAll(/<([A-Za-z_][A-Za-z0-9_]*)(?::(?:text|list))?>|<\/>/g)];
    if (kind === 'template') {
      for (const match of tags) {
        problems.push({ index: match.index || 0, message: 'Generation blocks belong in Sections or Functions' });
      }
      return problems;
    }
    let open = null;
    for (const match of tags) {
      if (match[0] === '</>') {
        if (!open) problems.push({ index: match.index || 0, message: 'Generation block has no opening tag' });
        open = null;
        continue;
      }
      if (open) problems.push({ index: match.index || 0, message: 'Generation blocks cannot be nested' });
      open = { index: match.index || 0, name: match[1] };
    }
    if (open) problems.push({ index: open.index, message: `Generation block <${open.name}> is missing </>` });
    return problems;
  }

  function validateEditor(kind) {
    const editor = editorFor(kind);
    if (!editor || editor.disabled || !editor.dataset.resourceId) {
      diagnostics.set(kind, []);
      renderDiagnostic(kind);
      return [];
    }
    const source = editor.value || '';
    const searchable = maskIgnoredRegions(source);
    const problems = [
      ...openingDelimiterProblems(searchable, '{{', '}}', 'expression'),
      ...openingDelimiterProblems(searchable, '{%', '%}', 'statement'),
      ...openingDelimiterProblems(searchable, '{#', '#}', 'comment'),
      ...generationProblems(source, kind)
    ].sort((a, b) => a.index - b.index);
    for (const problem of problems) problem.line = lineAt(source, problem.index);
    diagnostics.set(kind, problems);
    renderDiagnostic(kind);
    return problems;
  }

  function ensureDiagnosticChip(kind) {
    const pane = shell.querySelector(`[data-wb-pane="${kind}"]`);
    const title = pane?.querySelector('.wb-pane-title');
    if (!pane || !title) return null;
    let chip = pane.querySelector(`[data-wb-syntax-status="${kind}"]`);
    if (!chip) {
      chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'wb-syntax-chip';
      chip.dataset.wbSyntaxStatus = kind;
      title.insertAdjacentElement('afterend', chip);
      chip.addEventListener('click', event => {
        event.stopPropagation();
        focusProblem(kind, diagnostics.get(kind)?.[0]);
      });
    }
    return chip;
  }

  function renderDiagnostic(kind) {
    const chip = ensureDiagnosticChip(kind);
    if (!chip) return;
    const problems = diagnostics.get(kind) || [];
    chip.classList.toggle('error', Boolean(problems.length));
    chip.textContent = problems.length ? `! ${problems.length}` : '✓';
    chip.title = problems.length
      ? problems.map(problem => `Line ${problem.line}: ${problem.message}`).join('\n')
      : 'Syntax check passed';
    renderStatusSyntax();
  }

  function ensureStatusSyntax() {
    const actions = shell.querySelector('.wb-status-actions');
    if (!actions) return null;
    let button = document.getElementById('wbStatusSyntax');
    if (!button) {
      button = document.createElement('button');
      button.type = 'button';
      button.id = 'wbStatusSyntax';
      button.className = 'wb-status-button wb-status-syntax';
      actions.prepend(button);
      button.addEventListener('click', () => {
        for (const kind of KINDS) {
          const problem = diagnostics.get(kind)?.[0];
          if (problem) { focusProblem(kind, problem); return; }
        }
      });
    }
    return button;
  }

  function renderStatusSyntax() {
    const button = ensureStatusSyntax();
    if (!button) return;
    const count = KINDS.reduce((total, kind) => total + (diagnostics.get(kind)?.length || 0), 0);
    button.classList.toggle('error', count > 0);
    button.classList.toggle('active', count === 0);
    button.textContent = count ? `Syntax: ${count}` : 'Syntax: ✓';
    button.title = count ? 'Click to jump to the first syntax issue' : 'Open editors passed syntax checks';
  }

  function validateAll() {
    const all = [];
    for (const kind of KINDS) for (const problem of validateEditor(kind)) all.push({ kind, ...problem });
    return all;
  }

  function focusProblem(kind, problem) {
    const editor = editorFor(kind);
    if (!editor || !problem) return;
    const pane = shell.querySelector(`[data-wb-pane="${kind}"]`);
    if (pane?.classList.contains('collapsed')) pane.querySelector(`[data-wb-toggle="${kind}"]`)?.click();
    requestAnimationFrame(() => {
      editor.focus();
      editor.setSelectionRange(problem.index, Math.min(editor.value.length, problem.index + 1));
      editor.scrollTop = Math.max(0, (problem.line - 2) * (parseFloat(getComputedStyle(editor).lineHeight) || 19));
      syncMirror(kind);
    });
  }

  function wordAt(source, cursor) {
    let start = cursor;
    let end = cursor;
    while (start > 0 && /[A-Za-z0-9_.]/.test(source[start - 1])) start -= 1;
    while (end < source.length && /[A-Za-z0-9_.]/.test(source[end])) end += 1;
    const token = source.slice(start, end).replace(/^\.+|\.+$/g, '');
    return /^[A-Za-z_][A-Za-z0-9_.]*$/.test(token) ? token : '';
  }

  function setActiveSymbol(kind, editor) {
    const token = wordAt(editor.value || '', editor.selectionStart || 0);
    const root = token.split('.')[0];
    activeSymbols.set(kind, root);
    syncMirror(kind);
    highlightReferenceTargets(kind, editor, root, token);
  }

  function clearReferenceTargetHighlights() {
    shell.querySelectorAll('.wb-intel-reference').forEach(element => element.classList.remove('wb-intel-reference'));
  }

  function highlightReferenceTargets(kind, editor, root, fullToken) {
    clearReferenceTargetHighlights();
    if (!root) return;
    const relation = relationMap(kind, editor).get(root);
    if (relation) {
      const selector = CSS.escape(relation.id);
      shell.querySelectorAll(`[data-wb-resource-tab="${selector}"],[data-wb-open-resource="${selector}"],[data-wb-select-resource="${selector}"]`).forEach(element => element.classList.add('wb-intel-reference'));
      return;
    }
    if (JAW_ROOTS.has(root)) {
      const exact = fullToken || root;
      [...shell.querySelectorAll('[data-wb-select-jaw]')].filter(element => {
        const path = lower(element.dataset.wbSelectJaw);
        return path === lower(exact) || (!exact.includes('.') && path.startsWith(`${lower(root)}.`));
      }).forEach(element => element.classList.add('wb-intel-reference'));
    }
  }

  function installMirror(kind) {
    const editor = editorFor(kind);
    const body = editor?.closest('.wb-editor-body');
    if (!editor || !body || mirrors.has(kind)) return;
    const mirror = document.createElement('pre');
    mirror.className = 'wb-editor-highlight';
    mirror.setAttribute('aria-hidden', 'true');
    body.insertBefore(mirror, editor);
    mirrors.set(kind, mirror);

    editor.addEventListener('input', () => {
      syncMirror(kind);
      validateEditor(kind);
    });
    editor.addEventListener('scroll', () => syncMirror(kind));
    editor.addEventListener('click', () => setActiveSymbol(kind, editor));
    editor.addEventListener('keyup', event => {
      if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End', 'PageUp', 'PageDown'].includes(event.key)) setActiveSymbol(kind, editor);
    });
    editor.addEventListener('focus', () => {
      syncMirror(kind);
      validateEditor(kind);
    });

    // Intelligence is deliberately decoupled from the controller's render code.
    // Watching only resource identity is an appropriate DOM-lifecycle use of
    // MutationObserver: the callback never mutates data-resource-id and therefore
    // cannot self-feed like the retired document-tab observer did.
    new MutationObserver(mutations => {
      if (mutations.some(mutation => mutation.attributeName === 'data-resource-id')) {
        activeSymbols.delete(kind);
        syncMirror(kind);
        validateEditor(kind);
      }
    }).observe(editor, { attributes: true, attributeFilter: ['data-resource-id'] });
  }

  function syncFromStore() {
    syncAllMirrors();
    validateAll();
  }

  for (const kind of KINDS) installMirror(kind);
  ensureStatusSyntax();
  store.subscribe(() => requestAnimationFrame(syncFromStore));
  window.addEventListener('resize', syncAllMirrors);
  window.addEventListener('pointerup', () => requestAnimationFrame(syncAllMirrors));

  shell.querySelector('#wbGenerate')?.addEventListener('click', event => {
    const problems = validateAll();
    if (!problems.length) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    focusProblem(problems[0].kind, problems[0]);
    const status = document.getElementById('wbStatus');
    if (status) {
      status.textContent = `Fix ${problems.length} syntax issue${problems.length === 1 ? '' : 's'} before generating`;
      status.className = 'wb-status error';
    }
  }, true);

  requestAnimationFrame(syncFromStore);
})();