(() => {
  'use strict';

  const dataTab = $('customDataTab');
  const actionTab = $('customActionsTab');
  const dataView = $('customDataView');
  const legacyFields = $('customFields');
  if (!dataTab || !actionTab || !dataView || !legacyFields) return;

  dataTab.textContent = 'Custom';
  actionTab.hidden = true;
  dataView.querySelector('.toolbar')?.classList.add('custom-legacy-surface');
  legacyFields.classList.add('custom-legacy-surface');

  const workspace = document.createElement('div');
  workspace.id = 'customWorkspace';
  workspace.className = 'custom-workspace';
  workspace.innerHTML = `
    <aside class="custom-sidebar">
      <div class="custom-sidebar-head">
        <div class="custom-sidebar-title">
          <h2>Custom Items</h2>
          <button class="btn primary" id="customNewItem" type="button">+ Item</button>
        </div>
        <input class="custom-search" id="customItemSearch" placeholder="Search names or values…">
        <div class="custom-filter-row" role="group" aria-label="Custom item filters">
          <button class="custom-filter active" type="button" data-custom-filter="all">All</button>
          <button class="custom-filter" type="button" data-custom-filter="actions">Actions</button>
          <button class="custom-filter" type="button" data-custom-filter="data">Data only</button>
          <button class="custom-filter" type="button" data-custom-filter="unbound">Unbound</button>
        </div>
      </div>
      <div class="custom-item-list" id="customItemList"></div>
    </aside>
    <main class="custom-editor" id="customItemEditor"></main>`;
  dataView.append(workspace);

  let selectedKey = '';
  let filterMode = 'all';
  let searchTerm = '';
  let saveTimer = 0;
  let saveChain = Promise.resolve();
  let keybindState = null;
  let bindingUserId = null;
  let draft = null;
  let dragFieldId = '';

  const newId = prefix => `${prefix}_${crypto.randomUUID().replaceAll('-', '')}`;
  const fields = () => userData.custom_fields ??= [];
  const actions = () => userData.custom_actions ??= [];
  const fieldById = id => fields().find(field => String(field.id) === String(id)) || null;
  const actionById = id => actions().find(action => String(action.id) === String(id)) || null;
  const normalized = value => String(value || '').trim().toLocaleLowerCase();
  const typeLabel = type => type === 'list' ? 'List' : type === 'multi' ? 'Multi-line' : 'Single value';

  function referenceCount(fieldId, excludedActionId = '') {
    return actions().filter(action => String(action.id) !== String(excludedActionId)
      && (action.field_ids || []).map(String).includes(String(fieldId))).length;
  }

  function bindingLabels(actionId) {
    if (!keybindState || !actionId) return [];
    const result = [];
    for (const [layer, label] of [['base', 'Base'], ['layer2', 'Layer 2'], ['layer3', 'Layer 3']]) {
      for (const [key, action] of Object.entries(keybindState[layer] || {})) {
        if (String(action) === String(actionId)) result.push(`${label} · ${key}`);
      }
    }
    return result;
  }

  function reservedActionLabels() {
    if (!keybindState) return new Set();
    const customIds = new Set(actions().map(action => String(action.id)));
    return new Set(Object.entries(keybindState.action_labels || {})
      .filter(([id]) => !customIds.has(String(id)))
      .map(([, label]) => normalized(label))
      .filter(Boolean));
  }

  function uniqueFieldLabel(base, ignoreId = '') {
    const used = new Set(fields()
      .filter(field => String(field.id) !== String(ignoreId))
      .map(field => normalized(field.label))
      .filter(Boolean));
    const stem = String(base || '').trim() || 'Custom Value';
    if (!used.has(normalized(stem))) return stem;
    let index = 2;
    while (used.has(normalized(`${stem} ${index}`))) index += 1;
    return `${stem} ${index}`;
  }

  function uniqueActionLabel(base, ignoreId = '') {
    const used = new Set(actions()
      .filter(action => String(action.id) !== String(ignoreId))
      .map(action => normalized(action.label))
      .filter(Boolean));
    for (const label of reservedActionLabels()) used.add(label);
    const stem = String(base || '').trim() || 'Custom Action';
    if (!used.has(normalized(stem))) return stem;
    let index = 2;
    while (used.has(normalized(`${stem} ${index}`))) index += 1;
    return `${stem} ${index}`;
  }

  function projectedItems() {
    const byId = new Map(fields().map(field => [String(field.id), field]));
    const referenced = new Set();
    const result = actions().map(action => {
      const itemFields = (action.field_ids || []).map(id => byId.get(String(id))).filter(Boolean);
      for (const field of itemFields) referenced.add(String(field.id));
      const itemType = action.type === 'iterator'
        ? 'list'
        : itemFields[0]?.type === 'multi' ? 'multi' : 'single';
      const binds = bindingLabels(action.id);
      return {
        key: `action:${action.id}`,
        kind: 'action',
        label: String(action.label || ''),
        type: itemType,
        action,
        fields: itemFields,
        actionEnabled: true,
        autoReturn: Boolean(action.auto_return),
        bindings: binds,
        shared: itemFields.some(field => referenceCount(field.id) > 1),
      };
    });
    for (const field of fields()) {
      if (referenced.has(String(field.id))) continue;
      result.push({
        key: `field:${field.id}`,
        kind: 'field',
        label: String(field.label || ''),
        type: field.type === 'multi' ? 'multi' : 'single',
        field,
        fields: [field],
        actionEnabled: false,
        autoReturn: false,
        bindings: [],
        shared: false,
      });
    }
    if (draft) {
      result.unshift({
        key: 'draft',
        kind: 'draft',
        label: draft.label,
        type: draft.type,
        fields: [],
        actionEnabled: Boolean(draft.actionEnabled || draft.type === 'list'),
        autoReturn: Boolean(draft.autoReturn),
        bindings: [],
        shared: false,
      });
    }
    return result;
  }

  function itemValues(item) {
    if (item.kind === 'draft') return item.type === 'list'
      ? draft.values.map(value => value.value)
      : [draft.value];
    return item.fields.map(field => String(field.value || ''));
  }

  function visibleItems() {
    const query = normalized(searchTerm);
    return projectedItems().filter(item => {
      const matchesFilter = filterMode === 'all'
        || (filterMode === 'actions' && item.actionEnabled)
        || (filterMode === 'data' && !item.actionEnabled)
        || (filterMode === 'unbound' && item.actionEnabled && item.bindings.length === 0);
      if (!matchesFilter) return false;
      if (!query) return true;
      return normalized([item.label, ...itemValues(item)].join(' ')).includes(query);
    });
  }

  function itemByKey(key) {
    return projectedItems().find(item => item.key === key) || null;
  }

  function renderList() {
    const host = $('customItemList');
    if (!host) return;
    const items = visibleItems();
    host.innerHTML = items.length ? items.map(item => {
      const meta = [typeLabel(item.type)];
      if (item.actionEnabled) meta.push(item.bindings.length ? item.bindings.join(', ') : 'Unbound');
      else meta.push('Data only');
      return `<button class="custom-item-row ${item.key === selectedKey ? 'active' : ''}" type="button" data-custom-item-key="${esc(item.key)}">
        <span class="custom-item-row-top"><span class="custom-item-name">${esc(item.label || 'New Custom Item')}</span><span class="custom-item-badge">${item.actionEnabled ? (item.type === 'list' ? 'Iterator' : 'Action') : 'Data'}</span></span>
        <span class="custom-item-meta">${meta.map(value => `<span>${esc(value)}</span>`).join('')}</span>
      </button>`;
    }).join('') : '<div class="custom-empty">No Custom Items match this view.</div>';
  }

  function bindingMarkup(item) {
    if (!item.actionEnabled) return '<span class="custom-binding-pill unbound">Not exposed as an action</span>';
    if (!item.bindings.length) return '<span class="custom-binding-pill unbound">Unbound</span>';
    return item.bindings.map(label => `<span class="custom-binding-pill">${esc(label)}</span>`).join('');
  }

  function listRows(item) {
    const itemFields = item.kind === 'draft' ? draft.values : item.fields;
    return itemFields.map((field, index) => {
      const id = item.kind === 'draft' ? `draft-${index}` : String(field.id);
      const value = item.kind === 'draft' ? field.value : field.value;
      return `<div class="custom-value-row" draggable="true" data-custom-list-field="${esc(id)}">
        <span class="custom-drag" title="Drag to reorder">⋮⋮</span>
        <textarea data-custom-list-value="${esc(id)}" rows="1" placeholder="Value ${index + 1}">${esc(value || '')}</textarea>
        <button class="btn custom-danger" type="button" data-custom-remove-value="${esc(id)}" aria-label="Remove value">×</button>
      </div>`;
    }).join('');
  }

  function renderEditor() {
    const host = $('customItemEditor');
    if (!host) return;
    let item = itemByKey(selectedKey);
    if (!item) {
      const first = visibleItems()[0] || projectedItems()[0];
      if (first) {
        selectedKey = first.key;
        item = first;
      }
    }
    if (!item) {
      host.innerHTML = '<div class="custom-editor-empty"><div><b>No Custom Items yet.</b><br>Create one value and JAW can optionally expose it directly to Keybinds.</div></div>';
      return;
    }

    const values = itemValues(item);
    const primaryValue = values[0] || '';
    const actionLocked = item.type === 'list';
    const exposed = item.actionEnabled || actionLocked;
    const sharedCount = item.kind === 'action'
      ? item.fields.filter(field => referenceCount(field.id) > 1).length
      : 0;
    const valueEditor = item.type === 'list'
      ? `<div class="custom-list-editor"><span class="custom-field-label">Values · drag to reorder</span>${listRows(item)}<div class="custom-list-footer"><button class="btn" id="customAddListValue" type="button">+ Value</button><span class="custom-help">Iterator pastes these values in order.</span></div></div>`
      : `<div class="custom-field wide"><label>Value</label>${item.type === 'multi'
        ? `<textarea id="customItemValue" placeholder="Paste or type the reusable value">${esc(primaryValue)}</textarea>`
        : `<input id="customItemValue" value="${esc(primaryValue)}" placeholder="Reusable value">`}</div>`;

    host.innerHTML = `
      <div class="custom-editor-head">
        <div><div class="custom-eyebrow">Custom Item</div><h2>${esc(item.label || 'New Custom Item')}</h2></div>
        <div class="custom-editor-actions">
          <button class="btn" id="customCopyItem" type="button">Copy</button>
          <button class="btn" id="customDuplicateItem" type="button">Duplicate</button>
          <button class="btn custom-danger" id="customDeleteItem" type="button">Delete</button>
        </div>
      </div>
      <div class="custom-form">
        <div class="custom-field"><label>Name</label><input id="customItemName" value="${esc(item.label)}" placeholder="Work Authorization"></div>
        <div class="custom-field"><label>Value type</label><select id="customItemType"><option value="single" ${item.type === 'single' ? 'selected' : ''}>Single value</option><option value="multi" ${item.type === 'multi' ? 'selected' : ''}>Multi-line</option><option value="list" ${item.type === 'list' ? 'selected' : ''}>List / iterator</option></select></div>
        ${valueEditor}
        ${sharedCount ? `<div class="custom-shared-note">${sharedCount} underlying value${sharedCount === 1 ? ' is' : 's are'} shared with another Custom Action. Editing the value updates every action that uses it.</div>` : ''}
        <div class="custom-action-box ${exposed ? '' : 'disabled'}">
          <div class="custom-field"><label>Expose as Action</label><label class="custom-toggle-row"><input id="customExposeAction" type="checkbox" ${exposed ? 'checked' : ''} ${actionLocked ? 'disabled' : ''}><span>${actionLocked ? 'Required for lists' : 'Available in Keybinds'}</span></label></div>
          <div class="custom-field"><label>Paste behavior</label><div class="custom-toggle-row"><strong>${item.type === 'list' ? 'Iterator' : 'Single Paste'}</strong></div></div>
          <div class="custom-field"><label>Options</label><label class="custom-toggle-row"><input id="customAutoReturn" type="checkbox" ${item.autoReturn ? 'checked' : ''} ${exposed ? '' : 'disabled'}><span>Auto Return</span></label></div>
          <div class="custom-field wide"><label>Key bindings</label><div class="custom-binding-line" id="customBindingLine">${bindingMarkup(item)}<button class="btn" id="customManageKeybinds" type="button" ${exposed ? '' : 'disabled'}>Manage in Keybinds</button></div></div>
        </div>
      </div>
      <div class="custom-status" id="customSaveStatus">Changes save automatically</div>`;
  }

  function render() {
    renderList();
    renderEditor();
  }

  function setStatus(message, tone = '') {
    const status = $('customSaveStatus');
    if (!status) return;
    status.className = `custom-status ${tone}`.trim();
    status.textContent = message;
  }

  async function refreshBindings(force = false) {
    const userId = Number(userData.active_user_id || 0);
    if (!force && keybindState && bindingUserId === userId) return;
    try {
      const response = await fetch('/api/keybinds', { cache: 'no-store' });
      if (!response.ok) throw new Error(`Keybind request failed (${response.status})`);
      keybindState = await response.json();
      bindingUserId = userId;
      renderList();
      const item = itemByKey(selectedKey);
      const line = $('customBindingLine');
      if (item && line) line.innerHTML = `${bindingMarkup(item)}<button class="btn" id="customManageKeybinds" type="button" ${item.actionEnabled ? '' : 'disabled'}>Manage in Keybinds</button>`;
    } catch (error) {
      console.error(error);
    }
  }

  function validateState() {
    const fieldLabels = new Set();
    for (const field of fields()) {
      const label = String(field.label || '').trim();
      if (!label) return 'Every Custom Item value needs a name.';
      const key = normalized(label);
      if (fieldLabels.has(key)) return `Data label “${label}” is already in use.`;
      fieldLabels.add(key);
    }
    const actionLabels = new Set();
    const reserved = reservedActionLabels();
    for (const action of actions()) {
      const label = String(action.label || '').trim();
      if (!label) return 'Every exposed action needs a name.';
      const key = normalized(label);
      if (actionLabels.has(key)) return `Action name “${label}” is already in use.`;
      if (reserved.has(key)) return `“${label}” is reserved by a built-in action.`;
      actionLabels.add(key);
    }
    return '';
  }

  function materializeDraft() {
    if (!draft) return true;
    const label = String(draft.label || '').trim();
    if (!label) {
      setStatus('Name is required before this item can be saved.', 'error');
      return false;
    }
    if (draft.type === 'list') {
      const actionId = newId('custom_action');
      const values = draft.values.length ? draft.values : [{ value: '' }];
      const ids = values.map((entry, index) => {
        const field = { id: newId('custom'), label: uniqueFieldLabel(`${label} ${index + 1}`), value: String(entry.value || ''), type: 'single' };
        fields().push(field);
        return field.id;
      });
      actions().push({ id: actionId, label: uniqueActionLabel(label), type: 'iterator', field_ids: ids, auto_return: Boolean(draft.autoReturn) });
      selectedKey = `action:${actionId}`;
    } else {
      const field = { id: newId('custom'), label: uniqueFieldLabel(label), value: String(draft.value || ''), type: draft.type === 'multi' ? 'multi' : 'single' };
      fields().push(field);
      if (draft.actionEnabled) {
        const actionId = newId('custom_action');
        actions().push({ id: actionId, label: uniqueActionLabel(label), type: 'single', field_ids: [field.id], auto_return: Boolean(draft.autoReturn) });
        selectedKey = `action:${actionId}`;
      } else {
        selectedKey = `field:${field.id}`;
      }
    }
    draft = null;
    return true;
  }

  async function saveNow() {
    clearTimeout(saveTimer);
    const hadDraft = Boolean(draft);
    if (!materializeDraft()) return;
    if (hadDraft) renderList();
    const validation = validateState();
    if (validation) {
      setStatus(validation, 'error');
      return;
    }
    const fieldSnapshot = structuredClone(fields());
    const actionSnapshot = structuredClone(actions());
    setStatus('Saving…', 'saving');
    const request = saveChain.catch(() => {}).then(async () => {
      await api('/api/user/custom-fields', { fields: fieldSnapshot });
      await api('/api/user/custom-actions', { actions: actionSnapshot });
      await refreshBindings(true);
    });
    saveChain = request;
    try {
      await request;
      setStatus('Saved', 'saved');
      renderList();
    } catch (error) {
      console.error(error);
      setStatus(error.message || 'Save failed', 'error');
    }
  }

  function queueSave() {
    clearTimeout(saveTimer);
    setStatus('Unsaved changes', '');
    saveTimer = setTimeout(saveNow, 350);
  }

  function createFieldForAction(action, value = '') {
    const field = {
      id: newId('custom'),
      label: uniqueFieldLabel(`${action.label || 'Custom Item'} ${(action.field_ids || []).length + 1}`),
      value: String(value || ''),
      type: 'single',
    };
    fields().push(field);
    action.field_ids ??= [];
    action.field_ids.push(field.id);
    return field;
  }

  function removeOrphanField(fieldId, excludedActionId = '') {
    if (referenceCount(fieldId, excludedActionId) > 0) return;
    const index = fields().findIndex(field => String(field.id) === String(fieldId));
    if (index >= 0) fields().splice(index, 1);
  }

  function setItemType(item, nextType) {
    if (!['single', 'multi', 'list'].includes(nextType)) return;
    if (item.kind === 'draft') {
      draft.type = nextType;
      if (nextType === 'list') {
        draft.actionEnabled = true;
        if (!draft.values.length) draft.values.push({ value: draft.value || '' });
      } else if (draft.values.length) {
        draft.value = draft.values[0].value || '';
      }
      render();
      if (draft.label.trim()) queueSave();
      return;
    }
    if (item.kind === 'field') {
      if (nextType === 'list') {
        const actionId = newId('custom_action');
        const action = { id: actionId, label: uniqueActionLabel(item.field.label), type: 'iterator', field_ids: [item.field.id], auto_return: false };
        actions().push(action);
        item.field.type = 'single';
        selectedKey = `action:${actionId}`;
      } else {
        item.field.type = nextType === 'multi' ? 'multi' : 'single';
      }
      render();
      queueSave();
      return;
    }
    const action = item.action;
    if (nextType === 'list') {
      action.type = 'iterator';
      if (!(action.field_ids || []).length) createFieldForAction(action);
    } else {
      const oldIds = [...(action.field_ids || [])];
      let primary = oldIds.length ? fieldById(oldIds[0]) : null;
      if (!primary) primary = createFieldForAction(action);
      primary.type = nextType === 'multi' ? 'multi' : 'single';
      action.type = 'single';
      action.field_ids = [primary.id];
      for (const fieldId of oldIds.slice(1)) removeOrphanField(fieldId, action.id);
    }
    render();
    queueSave();
  }

  function toggleAction(item, enabled) {
    if (item.kind === 'draft') {
      draft.actionEnabled = Boolean(enabled || draft.type === 'list');
      renderEditor();
      if (draft.label.trim()) queueSave();
      return;
    }
    if (item.kind === 'field' && enabled) {
      const id = newId('custom_action');
      actions().push({ id, label: uniqueActionLabel(item.field.label), type: 'single', field_ids: [item.field.id], auto_return: false });
      selectedKey = `action:${id}`;
      render();
      queueSave();
      return;
    }
    if (item.kind === 'action' && !enabled && item.type !== 'list') {
      const primary = item.fields[0] || null;
      const index = actions().findIndex(action => String(action.id) === String(item.action.id));
      if (index >= 0) actions().splice(index, 1);
      selectedKey = primary ? `field:${primary.id}` : '';
      render();
      queueSave();
    }
  }

  function duplicateItem(item) {
    if (item.kind === 'draft') return;
    if (item.kind === 'field') {
      const copy = { ...item.field, id: newId('custom'), label: uniqueFieldLabel(`${item.field.label} Copy`) };
      fields().push(copy);
      selectedKey = `field:${copy.id}`;
    } else {
      const newFieldIds = item.fields.map((field, index) => {
        const copy = { ...field, id: newId('custom'), label: uniqueFieldLabel(`${item.action.label} Copy ${index + 1}`) };
        fields().push(copy);
        return copy.id;
      });
      if (!newFieldIds.length) {
        const placeholder = { id: newId('custom'), label: uniqueFieldLabel(`${item.action.label} Copy 1`), value: '', type: 'single' };
        fields().push(placeholder);
        newFieldIds.push(placeholder.id);
      }
      const copy = { ...item.action, id: newId('custom_action'), label: uniqueActionLabel(`${item.action.label} Copy`), field_ids: newFieldIds };
      actions().push(copy);
      selectedKey = `action:${copy.id}`;
    }
    render();
    queueSave();
  }

  function deleteItem(item) {
    if (item.kind === 'draft') {
      draft = null;
      selectedKey = '';
      render();
      return;
    }
    if (!confirm(`Delete “${item.label || 'this Custom Item'}”?`)) return;
    if (item.kind === 'field') {
      const index = fields().findIndex(field => String(field.id) === String(item.field.id));
      if (index >= 0) fields().splice(index, 1);
    } else {
      const fieldIds = [...(item.action.field_ids || [])];
      const index = actions().findIndex(action => String(action.id) === String(item.action.id));
      if (index >= 0) actions().splice(index, 1);
      for (const fieldId of fieldIds) removeOrphanField(fieldId);
    }
    selectedKey = '';
    render();
    queueSave();
  }

  async function copyItem(item) {
    const text = itemValues(item).join(item.type === 'list' ? '\n' : '');
    try {
      await navigator.clipboard.writeText(text);
      toast(item.type === 'list' ? 'List copied' : 'Value copied');
    } catch (error) {
      console.error(error);
      toast('Copy failed');
    }
  }

  function addListValue(item) {
    if (item.kind === 'draft') {
      draft.values.push({ value: '' });
      renderEditor();
      return;
    }
    if (item.kind !== 'action' || item.type !== 'list') return;
    createFieldForAction(item.action);
    renderEditor();
    queueSave();
  }

  function removeListValue(item, fieldId) {
    if (item.kind === 'draft') {
      const index = Number(String(fieldId).replace('draft-', ''));
      if (draft.values.length <= 1) draft.values[0].value = '';
      else if (index >= 0) draft.values.splice(index, 1);
      renderEditor();
      return;
    }
    if (item.kind !== 'action') return;
    const ids = item.action.field_ids || [];
    if (ids.length <= 1) {
      const field = fieldById(ids[0]);
      if (field) field.value = '';
    } else {
      item.action.field_ids = ids.filter(id => String(id) !== String(fieldId));
      removeOrphanField(fieldId, item.action.id);
    }
    renderEditor();
    queueSave();
  }

  function moveListValue(item, sourceId, targetId) {
    if (sourceId === targetId) return;
    if (item.kind === 'draft') {
      const source = Number(String(sourceId).replace('draft-', ''));
      const target = Number(String(targetId).replace('draft-', ''));
      if (!Number.isInteger(source) || !Number.isInteger(target) || source < 0 || target < 0) return;
      const [entry] = draft.values.splice(source, 1);
      draft.values.splice(target, 0, entry);
      renderEditor();
      if (draft.label.trim()) queueSave();
      return;
    }
    if (item.kind !== 'action') return;
    const ids = [...(item.action.field_ids || [])];
    const source = ids.findIndex(id => String(id) === String(sourceId));
    const target = ids.findIndex(id => String(id) === String(targetId));
    if (source < 0 || target < 0) return;
    const [id] = ids.splice(source, 1);
    ids.splice(target, 0, id);
    item.action.field_ids = ids;
    renderEditor();
    queueSave();
  }

  $('customNewItem').onclick = () => {
    draft = { label: '', type: 'single', value: '', values: [{ value: '' }], actionEnabled: true, autoReturn: false };
    selectedKey = 'draft';
    render();
    queueMicrotask(() => $('customItemName')?.focus());
  };

  $('customItemSearch').addEventListener('input', event => {
    searchTerm = event.target.value;
    renderList();
  });

  workspace.addEventListener('click', event => {
    const itemButton = event.target.closest('[data-custom-item-key]');
    if (itemButton) {
      selectedKey = itemButton.dataset.customItemKey;
      render();
      return;
    }
    const filterButton = event.target.closest('[data-custom-filter]');
    if (filterButton) {
      filterMode = filterButton.dataset.customFilter;
      document.querySelectorAll('[data-custom-filter]').forEach(button => button.classList.toggle('active', button === filterButton));
      renderList();
      renderEditor();
      return;
    }
    const item = itemByKey(selectedKey);
    if (!item) return;
    if (event.target.closest('#customDuplicateItem')) duplicateItem(item);
    else if (event.target.closest('#customDeleteItem')) deleteItem(item);
    else if (event.target.closest('#customCopyItem')) void copyItem(item);
    else if (event.target.closest('#customAddListValue')) addListValue(item);
    else if (event.target.closest('[data-custom-remove-value]')) removeListValue(item, event.target.closest('[data-custom-remove-value]').dataset.customRemoveValue);
    else if (event.target.closest('#customManageKeybinds')) navigateHash('keybinds');
  });

  workspace.addEventListener('input', event => {
    const item = itemByKey(selectedKey);
    if (!item) return;
    if (event.target.id === 'customItemName') {
      const value = event.target.value;
      if (item.kind === 'draft') draft.label = value;
      else if (item.kind === 'field') item.field.label = value;
      else {
        const oldLabel = String(item.action.label || '');
        item.action.label = value;
        if (item.fields.length === 1 && referenceCount(item.fields[0].id) === 1 && String(item.fields[0].label || '') === oldLabel) item.fields[0].label = value;
      }
      const title = workspace.querySelector('.custom-editor-head h2');
      if (title) title.textContent = value || 'New Custom Item';
      renderList();
      if (item.kind !== 'draft' || value.trim()) queueSave();
      return;
    }
    if (event.target.id === 'customItemValue') {
      if (item.kind === 'draft') draft.value = event.target.value;
      else if (item.fields[0]) item.fields[0].value = event.target.value;
      renderList();
      if (item.kind !== 'draft' || draft.label.trim()) queueSave();
      return;
    }
    if (event.target.matches('[data-custom-list-value]')) {
      const id = event.target.dataset.customListValue;
      if (item.kind === 'draft') {
        const index = Number(String(id).replace('draft-', ''));
        if (draft.values[index]) draft.values[index].value = event.target.value;
      } else {
        const field = fieldById(id);
        if (field) field.value = event.target.value;
      }
      renderList();
      if (item.kind !== 'draft' || draft.label.trim()) queueSave();
    }
  });

  workspace.addEventListener('change', event => {
    const item = itemByKey(selectedKey);
    if (!item) return;
    if (event.target.id === 'customItemType') setItemType(item, event.target.value);
    else if (event.target.id === 'customExposeAction') toggleAction(item, event.target.checked);
    else if (event.target.id === 'customAutoReturn') {
      if (item.kind === 'draft') draft.autoReturn = event.target.checked;
      else if (item.kind === 'action') item.action.auto_return = event.target.checked;
      queueSave();
    }
  });

  workspace.addEventListener('dragstart', event => {
    const row = event.target.closest('[data-custom-list-field]');
    if (!row) return;
    dragFieldId = row.dataset.customListField;
    row.classList.add('dragging');
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', dragFieldId);
  });
  workspace.addEventListener('dragover', event => {
    const row = event.target.closest('[data-custom-list-field]');
    if (!row || !dragFieldId) return;
    event.preventDefault();
    workspace.querySelectorAll('.custom-value-row').forEach(valueRow => valueRow.classList.toggle('drop-target', valueRow === row));
  });
  workspace.addEventListener('drop', event => {
    const row = event.target.closest('[data-custom-list-field]');
    if (!row || !dragFieldId) return;
    event.preventDefault();
    const item = itemByKey(selectedKey);
    if (item) moveListValue(item, dragFieldId, row.dataset.customListField);
    dragFieldId = '';
  });
  workspace.addEventListener('dragend', () => {
    dragFieldId = '';
    workspace.querySelectorAll('.custom-value-row').forEach(row => row.classList.remove('dragging', 'drop-target'));
  });

  const legacyRenderCustomFields = renderCustomFields;
  renderCustomFields = function () {
    legacyRenderCustomFields();
    render();
    void refreshBindings(bindingUserId !== Number(userData.active_user_id || 0));
  };

  const legacyShowUserView = showUserView;
  showUserView = function (name) {
    const resolved = name === 'custom-actions' ? 'custom-data' : name;
    legacyShowUserView(resolved);
    if (resolved === 'custom-data') {
      render();
      void refreshBindings(bindingUserId !== Number(userData.active_user_id || 0));
    }
  };

  const legacyTipsHtml = tipsHtml;
  tipsHtml = function (context) {
    if (context === 'custom-data' || context === 'custom-actions') return '<b>Custom:</b> Create reusable values and optionally expose them as Single Paste or Iterator actions. Action-enabled items can be assigned from Keybinds.';
    return legacyTipsHtml(context);
  };

  function normalizeLegacyRoute() {
    if (location.hash !== '#user/custom-actions') return;
    history.replaceState(null, '', `${location.pathname}${location.search}#user/custom-data`);
    if ($('userPage').classList.contains('active')) showUserView('custom-data');
  }
  window.addEventListener('hashchange', normalizeLegacyRoute);
  normalizeLegacyRoute();

  window.JawCustomWorkspace = { render, save: saveNow };
  render();
  void refreshBindings(true);
})();
