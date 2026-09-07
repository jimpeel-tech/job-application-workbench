(() => {
  const shell = document.querySelector('.wb-shell');
  const store = window.JawWorkbenchStore;
  if (!shell || !store || window.JawWorkbenchReferenceIds) return;

  const KINDS = ['template', 'section'];
  const JINJA_BLOCK = /\{\{[\s\S]*?\}\}|\{%[\s\S]*?%\}/g;
  const IDENTIFIER = /\b[A-Za-z_][A-Za-z0-9_]*\b/g;
  // Keep this in sync with JAW_SYMBOLS in documents/workbench_symbols.py.
  // These names belong to the runtime language and can never be structural
  // Section/Function references, even when a stale edge happens to share a name.
  const JAW_SYMBOLS = new Set([
    'user',
    'job_ref',
    'work_exp',
    'cap',
    'system',
    'csv',
    'latex_raw',
    'dump',
    'describe',
  ]);
  const AUTHORITATIVE_REASONS = new Set([
    'load', 'meta', 'link', 'delete', 'rename-symbol',
    'document-created', 'external'
  ]);
  const bindingCache = new Map();
  const pendingInputs = new Map();

  function state() { return store.getState() || {}; }
  function resourceById(id) { return (state().resources || []).find(item => item.id === id) || null; }
  function editorFor(kind) { return shell.querySelector(`[data-wb-editor="${kind}"]`); }

  function parentJid(kind, editor) {
    if (kind === 'template') return store.getActiveDocumentId() || '';
    if (kind === 'section') return editor?.dataset.resourceId || '';
    return '';
  }

  function cacheKey(kind, editor) {
    const parentId = parentJid(kind, editor);
    return parentId ? `${kind}:${parentId}` : '';
  }

  function referencesFor(kind, editor = editorFor(kind)) {
    const parentId = parentJid(kind, editor);
    if (!parentId) return [];
    return [...(state().relationships?.[parentId]?.outbound || [])]
      .filter(reference => (
        reference?.id
        && reference?.child_id
        && reference?.symbol
        && !JAW_SYMBOLS.has(String(reference.symbol))
      ))
      .sort((left, right) => (
        Number(left.sort_order || 0) - Number(right.sort_order || 0)
        || String(left.created_at || '').localeCompare(String(right.created_at || ''))
        || String(left.id || '').localeCompare(String(right.id || ''))
      ));
  }

  function identifierTokens(block, absoluteStart) {
    const bodyStart = block.startsWith('{{') || block.startsWith('{%') ? 2 : 0;
    const bodyEnd = Math.max(bodyStart, block.length - 2);
    const body = block.slice(bodyStart, bodyEnd);
    let masked = '';
    let quote = '';
    let escaped = false;
    for (const character of body) {
      if (quote) {
        masked += ' ';
        if (escaped) { escaped = false; continue; }
        if (character === '\\') { escaped = true; continue; }
        if (character === quote) quote = '';
        continue;
      }
      if (character === '"' || character === "'") { quote = character; masked += ' '; continue; }
      masked += character;
    }

    const tokens = [];
    for (const match of masked.matchAll(IDENTIFIER)) {
      if (JAW_SYMBOLS.has(match[0])) continue;
      const before = masked.slice(0, match.index).trimEnd();
      if (before.endsWith('.') || before.endsWith('|')) continue;
      const start = absoluteStart + bodyStart + (match.index || 0);
      tokens.push({ symbol: match[0], start, end: start + match[0].length });
    }
    return tokens;
  }

  function sourceTokens(source) {
    const tokens = [];
    for (const construct of String(source || '').matchAll(JINJA_BLOCK)) {
      const constructStart = construct.index || 0;
      const constructEnd = constructStart + construct[0].length;
      for (const token of identifierTokens(construct[0], constructStart)) {
        tokens.push({ ...token, constructStart, constructEnd });
      }
    }
    return tokens;
  }

  function bindingValue(token, reference) {
    return {
      ...token,
      reference,
      referenceId: String(reference.id),
      resourceId: String(reference.child_id),
      resource: resourceById(reference.child_id),
    };
  }

  function authoritativeBindingsFor(kind, editor) {
    const queues = new Map();
    for (const reference of referencesFor(kind, editor)) {
      const symbol = String(reference.symbol || '');
      if (!queues.has(symbol)) queues.set(symbol, []);
      queues.get(symbol).push(reference);
    }
    const bindings = [];
    for (const token of sourceTokens(editor?.value || '')) {
      const queue = queues.get(token.symbol);
      if (!queue?.length) continue;
      bindings.push(bindingValue(token, queue.shift()));
    }
    return bindings;
  }

  function rememberBindings(kind, editor, bindings) {
    const key = cacheKey(kind, editor);
    if (!key) return;
    bindingCache.set(key, {
      source: String(editor?.value || ''),
      bindings: bindings.map(binding => ({
        symbol: binding.symbol,
        start: binding.start,
        end: binding.end,
        constructStart: binding.constructStart,
        constructEnd: binding.constructEnd,
        referenceId: binding.referenceId,
        resourceId: binding.resourceId,
      })),
    });
  }

  function bindingsFor(kind, editor = editorFor(kind)) {
    if (!editor) return [];
    const key = cacheKey(kind, editor);
    const source = String(editor.value || '');
    const references = referencesFor(kind, editor);
    const referencesById = new Map(references.map(reference => [String(reference.id), reference]));
    const tokens = sourceTokens(source);
    const cached = key ? bindingCache.get(key) : null;

    if (!cached || cached.source !== source) {
      const authoritative = authoritativeBindingsFor(kind, editor);
      rememberBindings(kind, editor, authoritative);
      return authoritative;
    }

    const tokenBySpan = new Map(
      tokens.map(token => [`${token.start}:${token.end}:${token.symbol}`, token])
    );
    const occupiedSpans = new Set();
    const usedReferences = new Set();
    const bindings = [];

    for (const previous of cached.bindings || []) {
      const reference = referencesById.get(String(previous.referenceId || ''));
      if (!reference || String(reference.symbol || '') !== String(previous.symbol || '')) continue;
      const spanKey = `${previous.start}:${previous.end}:${previous.symbol}`;
      const token = tokenBySpan.get(spanKey);
      if (!token || usedReferences.has(String(reference.id))) continue;
      bindings.push(bindingValue(token, reference));
      occupiedSpans.add(spanKey);
      usedReferences.add(String(reference.id));
    }

    const available = new Map();
    for (const reference of references) {
      if (usedReferences.has(String(reference.id))) continue;
      const symbol = String(reference.symbol || '');
      if (!available.has(symbol)) available.set(symbol, []);
      available.get(symbol).push(reference);
    }
    for (const token of tokens) {
      const spanKey = `${token.start}:${token.end}:${token.symbol}`;
      if (occupiedSpans.has(spanKey)) continue;
      const queue = available.get(token.symbol);
      if (!queue?.length) continue;
      const reference = queue.shift();
      bindings.push(bindingValue(token, reference));
      occupiedSpans.add(spanKey);
      usedReferences.add(String(reference.id));
    }

    bindings.sort((left, right) => left.start - right.start || left.end - right.end);
    rememberBindings(kind, editor, bindings);
    return bindings;
  }

  function checkpointBindings(kind, editor = editorFor(kind)) {
    return bindingsFor(kind, editor).map(binding => ({
      reference_id: binding.referenceId,
      start: binding.start,
      end: binding.end,
      symbol: binding.symbol,
    }));
  }

  function referenceAt(kind, editor, cursor = editor?.selectionStart || 0) {
    const position = Number(cursor || 0);
    return bindingsFor(kind, editor).find(binding => (
      position >= binding.start && position < binding.end
    )) || null;
  }

  function referencesIntersecting(kind, editor, start, end) {
    const left = Math.min(Number(start || 0), Number(end || 0));
    const right = Math.max(Number(start || 0), Number(end || 0));
    if (left === right) {
      const bindings = bindingsFor(kind, editor);
      const binding = referenceAt(kind, editor, left)
        || bindings.find(item => item.end === left);
      return binding ? [binding] : [];
    }
    return bindingsFor(kind, editor).filter(binding => (
      binding.end > left && binding.start < right
    ));
  }

  function spanSymbol(span) {
    return String(span.textContent || '').split('.')[0].trim();
  }

  function decorate(kind) {
    const editor = editorFor(kind);
    const mirror = editor?.closest('.wb-editor-body')?.querySelector('.wb-editor-highlight');
    if (!editor || !mirror) return;

    const bindings = bindingsFor(kind, editor);
    const bindingBySpan = new Map(
      bindings.map(binding => [`${binding.start}:${binding.end}:${binding.symbol}`, binding])
    );
    const tokenQueues = new Map();
    for (const token of sourceTokens(editor.value || '')) {
      if (!tokenQueues.has(token.symbol)) tokenQueues.set(token.symbol, []);
      tokenQueues.get(token.symbol).push(token);
    }
    const referenceSymbols = new Set(referencesFor(kind, editor).map(item => String(item.symbol || '')));

    for (const span of mirror.querySelectorAll('[data-wb-syntax-symbol]')) {
      delete span.dataset.wbReferenceJid;
      delete span.dataset.wbResourceJid;
      const symbol = spanSymbol(span);
      if (symbol) span.dataset.wbSyntaxSymbol = symbol;
      const token = tokenQueues.get(symbol)?.shift();
      const binding = token
        ? bindingBySpan.get(`${token.start}:${token.end}:${token.symbol}`)
        : null;
      if (!binding) {
        if (referenceSymbols.has(symbol)) {
          span.classList.remove('wb-syn-private', 'wb-syn-global', 'wb-syn-orphan');
          span.classList.add('wb-syn-unresolved');
        }
        continue;
      }
      span.dataset.wbReferenceJid = binding.referenceId;
      span.dataset.wbResourceJid = binding.resourceId;
      span.classList.remove('wb-syn-private', 'wb-syn-global', 'wb-syn-orphan', 'wb-syn-unresolved');
      if (binding.resource?.state === 'orphaned') span.classList.add('wb-syn-orphan');
      else if (binding.resource?.visibility === 'global') span.classList.add('wb-syn-global');
      else span.classList.add('wb-syn-private');
    }
  }

  function editRange(before, after) {
    const oldSource = String(before.source || '');
    const newSource = String(after || '');
    let oldStart = Number(before.start || 0);
    let oldEnd = Number(before.end ?? oldStart);
    const delta = newSource.length - oldSource.length;
    let newEnd;

    if (oldEnd > oldStart) {
      const inserted = Math.max(0, newSource.length - (oldSource.length - (oldEnd - oldStart)));
      newEnd = oldStart + inserted;
    } else if (delta >= 0) {
      newEnd = oldStart + delta;
    } else {
      const deleted = -delta;
      const inputType = String(before.inputType || '');
      if (inputType.includes('Backward')) {
        oldStart = Math.max(0, oldStart - deleted);
        oldEnd = Number(before.start || 0);
        newEnd = oldStart;
      } else if (inputType.includes('Forward')) {
        oldEnd = Math.min(oldSource.length, oldStart + deleted);
        newEnd = oldStart;
      } else {
        let prefix = 0;
        const maxPrefix = Math.min(oldSource.length, newSource.length);
        while (prefix < maxPrefix && oldSource[prefix] === newSource[prefix]) prefix += 1;
        let suffix = 0;
        while (
          suffix < oldSource.length - prefix
          && suffix < newSource.length - prefix
          && oldSource[oldSource.length - 1 - suffix] === newSource[newSource.length - 1 - suffix]
        ) suffix += 1;
        oldStart = prefix;
        oldEnd = oldSource.length - suffix;
        newEnd = newSource.length - suffix;
      }
    }
    return { oldStart, oldEnd, newEnd };
  }

  function transformCachedBindings(bindings, range) {
    const shift = range.newEnd - range.oldEnd;
    const transformed = [];
    for (const binding of bindings || []) {
      if (binding.end <= range.oldStart) {
        transformed.push({ ...binding });
        continue;
      }
      if (binding.start >= range.oldEnd) {
        transformed.push({
          ...binding,
          start: binding.start + shift,
          end: binding.end + shift,
          constructStart: Number(binding.constructStart || 0) + shift,
          constructEnd: Number(binding.constructEnd || 0) + shift,
        });
      }
    }
    return transformed;
  }

  function captureBeforeInput(kind, editor, event) {
    const key = cacheKey(kind, editor);
    if (!key) return;
    const currentBindings = bindingsFor(kind, editor);
    pendingInputs.set(key, {
      source: String(editor.value || ''),
      start: Number(editor.selectionStart || 0),
      end: Number(editor.selectionEnd ?? editor.selectionStart ?? 0),
      inputType: String(event?.inputType || ''),
      bindings: currentBindings.map(binding => ({
        symbol: binding.symbol,
        start: binding.start,
        end: binding.end,
        constructStart: binding.constructStart,
        constructEnd: binding.constructEnd,
        referenceId: binding.referenceId,
        resourceId: binding.resourceId,
      })),
    });
  }

  function applyInputTransform(kind, editor) {
    const key = cacheKey(kind, editor);
    const before = key ? pendingInputs.get(key) : null;
    if (!key || !before) return;
    pendingInputs.delete(key);
    const source = String(editor.value || '');
    const range = editRange(before, source);
    bindingCache.set(key, {
      source,
      bindings: transformCachedBindings(before.bindings, range),
    });
  }

  function applyProgrammaticEdit(kind, editor, details = {}) {
    const key = cacheKey(kind, editor);
    if (!key) return;
    const oldSource = String(details.oldSource ?? '');
    let cached = bindingCache.get(key);
    if (!cached || cached.source !== oldSource) {
      const currentSource = String(editor.value || '');
      editor.value = oldSource;
      const seeded = authoritativeBindingsFor(kind, editor);
      editor.value = currentSource;
      cached = { source: oldSource, bindings: seeded.map(binding => ({
        symbol: binding.symbol,
        start: binding.start,
        end: binding.end,
        constructStart: binding.constructStart,
        constructEnd: binding.constructEnd,
        referenceId: binding.referenceId,
        resourceId: binding.resourceId,
      })) };
    }
    const range = {
      oldStart: Number(details.start || 0),
      oldEnd: Number(details.end ?? details.start ?? 0),
      newEnd: Number(details.newEnd ?? details.start ?? 0),
    };
    const transformed = transformCachedBindings(cached.bindings, range);
    if (details.reference?.id && details.symbol) {
      transformed.push({
        symbol: String(details.symbol),
        start: Number(details.symbolStart),
        end: Number(details.symbolEnd),
        constructStart: Number(details.constructStart ?? details.start ?? 0),
        constructEnd: Number(details.constructEnd ?? details.newEnd ?? details.symbolEnd),
        referenceId: String(details.reference.id),
        resourceId: String(details.reference.child_id || details.resourceId || ''),
      });
      transformed.sort((left, right) => left.start - right.start || left.end - right.end);
    }
    bindingCache.set(key, { source: String(editor.value || ''), bindings: transformed });
  }

  function queueByResource(items) {
    const queues = new Map();
    for (const item of items || []) {
      const resourceId = String(item?.id || '');
      if (!resourceId || !item?.reference_id) continue;
      if (!queues.has(resourceId)) queues.set(resourceId, []);
      queues.get(resourceId).push(item);
    }
    return queues;
  }

  function decorateExplorerFunctions(sectionRow, section) {
    const wrapper = sectionRow.parentElement;
    if (!wrapper) return;
    const functionRows = [...wrapper.querySelectorAll(
      ':scope > .wb-tree-children .wb-tree-row.depth3[data-wb-open-resource]'
    )];
    const queues = queueByResource(section?.functions || []);
    for (const row of functionRows) {
      delete row.dataset.wbReferenceJid;
      const queue = queues.get(String(row.dataset.wbOpenResource || ''));
      const fn = queue?.shift();
      if (fn?.reference_id) row.dataset.wbReferenceJid = String(fn.reference_id);
    }
  }

  function decorateExplorer() {
    const documents = new Map(
      (state().documents || []).map(document => [String(document.id), document])
    );
    for (const tree of shell.querySelectorAll('#wbExplorer .wb-tree-document')) {
      const documentId = String(
        tree.querySelector(':scope > .wb-tree-row[data-wb-open-doc]')?.dataset.wbOpenDoc || ''
      );
      const document = documents.get(documentId);
      if (!document) continue;

      const queues = queueByResource(document.sections || []);
      const sectionRows = [...tree.querySelectorAll('.wb-tree-row.depth2[data-wb-open-resource]')];
      for (const row of sectionRows) {
        delete row.dataset.wbReferenceJid;
        const queue = queues.get(String(row.dataset.wbOpenResource || ''));
        const section = queue?.shift();
        if (!section?.reference_id) continue;
        row.dataset.wbReferenceJid = String(section.reference_id);
        decorateExplorerFunctions(row, section);
      }
    }
  }

  function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, character => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[character]));
  }

  function flattenJawObject(prefix, value, output) {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      const keys = Object.keys(value);
      if (!keys.length) output.push({ path: prefix, insert: prefix });
      for (const key of keys) flattenJawObject(`${prefix}.${key}`, value[key], output);
      return;
    }
    output.push({ path: prefix, insert: prefix });
  }

  function jawEntries() {
    const context = state().generation_context || {};
    const entries = [];
    for (const root of ['user', 'job_ref', 'work_exp', 'cap', 'system']) {
      if (Object.hasOwn(context, root)) flattenJawObject(root, context[root], entries);
    }
    entries.push(
      { path: 'csv(...)', insert: 'csv()', method: true },
      { path: 'latex_raw(...)', insert: 'latex_raw()', method: true },
      { path: 'dump(...)', insert: 'dump()', method: true },
      { path: 'describe(...)', insert: 'describe()', method: true },
    );
    return entries;
  }

  function renderJawObjects() {
    const panel = shell.querySelector('#wbJawObjects');
    const filter = shell.querySelector('#wbJawFilter');
    if (!panel) return;
    const query = String(filter?.value || '').trim().toLowerCase();
    const visible = jawEntries().filter(item => !query || item.path.toLowerCase().includes(query));
    panel.innerHTML = visible.map(item => (
      `<div class="wb-palette-item jaw" draggable="true" data-wb-jaw="${escapeHtml(item.insert || item.path)}" data-wb-select-jaw="${escapeHtml(item.path)}"><span>${escapeHtml(item.path)}</span></div>`
    )).join('') || '<div class="wb-empty compact">No matches</div>';
  }

  function decorateAll() {
    for (const kind of KINDS) decorate(kind);
    decorateExplorer();
    renderJawObjects();
  }

  for (const kind of KINDS) {
    const editor = editorFor(kind);
    if (!editor) continue;
    editor.addEventListener('beforeinput', event => captureBeforeInput(kind, editor, event));
    editor.addEventListener('input', () => {
      applyInputTransform(kind, editor);
      requestAnimationFrame(() => decorate(kind));
    });
    editor.addEventListener('focus', () => requestAnimationFrame(() => decorate(kind)));
    editor.addEventListener('click', () => requestAnimationFrame(() => decorate(kind)));
  }

  const explorer = shell.querySelector('#wbExplorer');
  explorer?.addEventListener('click', () => requestAnimationFrame(decorateExplorer));
  shell.querySelector('#wbJawFilter')?.addEventListener('input', () => requestAnimationFrame(renderJawObjects));

  store.subscribe((_snapshot, reason) => {
    if (AUTHORITATIVE_REASONS.has(String(reason || ''))) {
      bindingCache.clear();
      pendingInputs.clear();
    }
    requestAnimationFrame(decorateAll);
  });
  requestAnimationFrame(decorateAll);

  window.JawWorkbenchReferenceIds = {
    applyProgrammaticEdit,
    bindingsFor,
    checkpointBindings,
    decorate,
    decorateAll,
    decorateExplorer,
    parentJid,
    referenceAt,
    referencesFor,
    referencesIntersecting,
  };
})();
