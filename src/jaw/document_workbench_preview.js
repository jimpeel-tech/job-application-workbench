(() => {
  const generateButton = document.getElementById('wbGenerate');
  const previewButton = document.getElementById('wbPreview');
  const status = document.getElementById('wbStatus');
  const shell = document.querySelector('.wb-shell');
  const store = window.JawWorkbenchStore;
  const workbench = window.JawDocumentWorkbench;
  if (!generateButton || !previewButton || !status || !shell || !store || !workbench) return;

  const previews = new Map();
  const PREVIEW_WINDOW = 'jaw-document-preview';
  const ERROR_WINDOW = 'jaw-document-error';
  const PROVIDER_DEFAULTS = {
    ollama: 'qwen3:14b',
    openai: 'gpt-5.6-terra'
  };

  const statusActions = shell.querySelector('.wb-status-actions');
  const modelButton = document.getElementById('wbStatusGenerationModel') || document.createElement('button');
  modelButton.className = 'wb-status-button';
  modelButton.id = 'wbStatusGenerationModel';
  modelButton.type = 'button';
  modelButton.textContent = 'AI: Loading…';
  if (!modelButton.parentElement) statusActions?.prepend(modelButton);

  const modelPopup = document.createElement('div');
  modelPopup.className = 'wb-generation-popup';
  modelPopup.hidden = true;
  modelPopup.innerHTML = `
    <div class="wb-generation-card" role="dialog" aria-modal="true" aria-labelledby="wbGenerationModelTitle">
      <div class="wb-generation-head"><strong id="wbGenerationModelTitle">Document Generation Model</strong><button class="wb-generation-close" type="button" aria-label="Close">×</button></div>
      <div style="padding:14px 14px 4px">
        <label class="wb-field"><span>Provider</span><select id="wbGenerationProvider"><option value="ollama">Ollama</option><option value="openai">OpenAI</option></select></label>
        <label class="wb-field"><span>Model</span><input id="wbGenerationModel" type="text" autocomplete="off" spellcheck="false"></label>
        <div class="wb-generation-status" id="wbGenerationModelHint">Applies to Document Preview and Generate only. Job Analysis settings are unchanged.</div>
      </div>
      <div class="wb-generation-actions"><button class="wb-button" id="wbGenerationUseUser" type="button">Use user setting</button><span style="flex:1"></span><button class="wb-button" id="wbGenerationModelCancel" type="button">Cancel</button><button class="wb-button primary" id="wbGenerationModelApply" type="button">Apply</button></div>
    </div>`;
  shell.appendChild(modelPopup);

  const modelEls = {
    provider: document.getElementById('wbGenerationProvider'),
    model: document.getElementById('wbGenerationModel'),
    useUser: document.getElementById('wbGenerationUseUser'),
    cancel: document.getElementById('wbGenerationModelCancel'),
    apply: document.getElementById('wbGenerationModelApply'),
    hint: document.getElementById('wbGenerationModelHint')
  };

  let generationSettings = {
    loaded: false,
    userId: '',
    inheritedProvider: 'openai',
    inheritedModel: PROVIDER_DEFAULTS.openai,
    provider: 'openai',
    model: PROVIDER_DEFAULTS.openai,
    overridden: false
  };

  const resultPopup = document.createElement('div');
  resultPopup.className = 'wb-generation-popup';
  resultPopup.hidden = true;
  resultPopup.innerHTML = `
    <div class="wb-generation-card" role="dialog" aria-modal="true" aria-labelledby="wbGenerationTitle">
      <div class="wb-generation-head"><strong id="wbGenerationTitle">Document Generated</strong><button class="wb-generation-close" type="button" aria-label="Close">×</button></div>
      <div class="wb-generation-file" id="wbGenerationFile"></div>
      <div class="wb-generation-status" id="wbGenerationStatus"></div>
      <div class="wb-generation-path" id="wbGenerationPath"></div>
      <div class="wb-generation-actions"><button class="wb-button primary" id="wbGenerationOpen" type="button">Open</button><button class="wb-button" id="wbGenerationLocation" type="button">Open Location</button><button class="wb-button" id="wbGenerationDismiss" type="button">Close</button></div>
    </div>`;
  shell.appendChild(resultPopup);

  const popupEls = {
    file: document.getElementById('wbGenerationFile'),
    status: document.getElementById('wbGenerationStatus'),
    path: document.getElementById('wbGenerationPath'),
    open: document.getElementById('wbGenerationOpen'),
    location: document.getElementById('wbGenerationLocation')
  };
  let lastGenerated = null;
  let rendering = false;

  const setStatus = (text = '', kind = '') => {
    status.textContent = text;
    status.className = `wb-status ${kind}`;
  };
  function activeDocumentId() { return store.getActiveDocumentId() || ''; }
  function syncButtons() {
    const documentId = activeDocumentId();
    generateButton.disabled = rendering || !documentId;
    previewButton.disabled = rendering || !documentId;
  }
  function currentWorkingBuffers() {
    const buffers = {};
    shell.querySelectorAll('.wb-editor[data-resource-id]').forEach(editor => {
      const resourceId = String(editor.dataset.resourceId || '');
      if (resourceId) buffers[resourceId] = editor.value;
    });
    return buffers;
  }
  function providerLabel(provider) {
    return provider === 'ollama' ? 'Ollama' : provider === 'openai' ? 'OpenAI' : provider;
  }
  function generationStorageKey(kind, userId) {
    return `jaw.workbench.generation${kind}.${userId}`;
  }
  function updateModelButton() {
    if (!generationSettings.loaded) {
      modelButton.textContent = 'AI: User setting';
      modelButton.title = 'Click to choose the Document generation provider and model';
      return;
    }
    modelButton.textContent = `AI: ${providerLabel(generationSettings.provider)} · ${generationSettings.model}`;
    modelButton.title = generationSettings.overridden
      ? 'Documents override · Click to change'
      : 'Inherited from active user settings · Click to change';
    modelButton.classList.toggle('active', generationSettings.overridden);
  }
  async function refreshGenerationSettings() {
    try {
      const response = await fetch('/api/user-data', { cache: 'no-store' });
      const user = await response.json();
      if (!response.ok) throw new Error(user.error || `Request failed (${response.status})`);
      const userId = String(user.active_user_id || '');
      const inherited = user.analysis_settings || {};
      const inheritedProvider = ['ollama', 'openai'].includes(String(inherited.provider || '').toLowerCase())
        ? String(inherited.provider).toLowerCase()
        : 'openai';
      const inheritedModel = String(inherited.model || '').trim() || PROVIDER_DEFAULTS[inheritedProvider];
      const storedProvider = userId ? String(localStorage.getItem(generationStorageKey('Provider', userId)) || '').toLowerCase() : '';
      const storedModel = userId ? String(localStorage.getItem(generationStorageKey('Model', userId)) || '').trim() : '';
      const overridden = ['ollama', 'openai'].includes(storedProvider) && Boolean(storedModel);
      generationSettings = {
        loaded: true,
        userId,
        inheritedProvider,
        inheritedModel,
        provider: overridden ? storedProvider : inheritedProvider,
        model: overridden ? storedModel : inheritedModel,
        overridden
      };
      updateModelButton();
    } catch (error) {
      generationSettings.loaded = false;
      updateModelButton();
      modelButton.title = `Could not read user generation setting: ${String(error.message || error)}`;
    }
  }
  function generationPayload() {
    if (!generationSettings.loaded) return {};
    return {
      generation_provider: generationSettings.provider,
      generation_model: generationSettings.model
    };
  }
  function closeModelPopup() { modelPopup.hidden = true; }
  function openModelPopup() {
    modelEls.provider.value = generationSettings.provider;
    modelEls.model.value = generationSettings.model;
    modelEls.useUser.disabled = !generationSettings.overridden;
    modelEls.hint.textContent = generationSettings.overridden
      ? `Documents override. User setting: ${providerLabel(generationSettings.inheritedProvider)} · ${generationSettings.inheritedModel}.`
      : 'Using the active user setting. Changes here apply to Document Preview and Generate only.';
    modelPopup.hidden = false;
    requestAnimationFrame(() => modelEls.model.focus());
  }
  function applyModelOverride() {
    if (!generationSettings.loaded || !generationSettings.userId) {
      setStatus('Could not determine the active user generation settings.', 'error');
      return;
    }
    const provider = String(modelEls.provider.value || '').trim().toLowerCase();
    const model = String(modelEls.model.value || '').trim();
    if (!['ollama', 'openai'].includes(provider) || !model) {
      setStatus('Choose a provider and model.', 'error');
      return;
    }
    localStorage.setItem(generationStorageKey('Provider', generationSettings.userId), provider);
    localStorage.setItem(generationStorageKey('Model', generationSettings.userId), model);
    generationSettings = { ...generationSettings, provider, model, overridden: true };
    updateModelButton();
    closeModelPopup();
    setStatus(`Document AI · ${providerLabel(provider)} · ${model}`, 'ok');
  }
  function useUserGenerationSetting() {
    if (!generationSettings.loaded || !generationSettings.userId) return;
    localStorage.removeItem(generationStorageKey('Provider', generationSettings.userId));
    localStorage.removeItem(generationStorageKey('Model', generationSettings.userId));
    generationSettings = {
      ...generationSettings,
      provider: generationSettings.inheritedProvider,
      model: generationSettings.inheritedModel,
      overridden: false
    };
    updateModelButton();
    closeModelPopup();
    setStatus(`Document AI · ${providerLabel(generationSettings.provider)} · ${generationSettings.model}`, 'ok');
  }
  function pdfBlob(base64) {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
    return new Blob([bytes], { type: 'application/pdf' });
  }
  function rememberPreview(documentId, base64) {
    const previous = previews.get(documentId);
    if (previous) URL.revokeObjectURL(previous);
    const url = URL.createObjectURL(pdfBlob(base64));
    previews.set(documentId, url);
    return url;
  }
  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, character => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character]));
  }
  function errorHtml(error) {
    const message = String(error?.message || error || 'Unknown generation error');
    return `<!doctype html><html><head><meta charset="utf-8"><title>JAW · Document Error</title><style>:root{color-scheme:dark}body{margin:0;background:#181a1f;color:#d4d4d4;font:14px/1.55 Segoe UI,Arial,sans-serif}main{max-width:980px;margin:0 auto;padding:28px}h1{font-size:20px;margin:0 0 18px;color:#f0f0f0}pre{white-space:pre-wrap;word-break:break-word;background:#111318;border:1px solid #34373d;border-left:3px solid #c65f5f;padding:16px;color:#e2b1b1}p{color:#8f98a3}</style></head><body><main><h1>Document generation failed</h1><pre>${escapeHtml(message)}</pre><p>Return to JAW after correcting the source and try again.</p></main></body></html>`;
  }
  function openError(error) {
    const html = errorHtml(error);
    const url = URL.createObjectURL(new Blob([html], { type: 'text/html' }));
    if (!window.open(url, ERROR_WINDOW)) setStatus(String(error?.message || error), 'error');
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }
  function showPreviewError(previewWindow, error) {
    if (!previewWindow || previewWindow.closed) {
      openError(error);
      return;
    }
    const url = URL.createObjectURL(new Blob([errorHtml(error)], { type: 'text/html' }));
    previewWindow.location.replace(url);
    setTimeout(() => URL.revokeObjectURL(url), 60_000);
  }
  function closeResultPopup() { resultPopup.hidden = true; }
  function showResultPopup(generated) {
    lastGenerated = generated;
    popupEls.file.textContent = generated.filename || 'PDF';
    popupEls.path.textContent = generated.output_path || '';
    const generationCount = Array.isArray(generated.generations) ? generated.generations.length : 0;
    const generationText = generationCount ? ` · ${generationCount} AI generation${generationCount === 1 ? '' : 's'}` : '';
    popupEls.status.textContent = generated.warning || (generated.output_written ? `Generated successfully${generationText}` : 'Preview generated; file was not written');
    popupEls.status.className = `wb-generation-status ${generated.warning || !generated.output_written ? 'warning' : 'ok'}`;
    popupEls.open.disabled = !generated.output_written || !generated.output_path;
    popupEls.location.disabled = !generated.output_path;
    resultPopup.hidden = false;
  }
  async function openGenerated(target) {
    if (!lastGenerated?.output_path) return;
    try {
      await workbench.mutate('open-output', { path: lastGenerated.output_path, target });
      setStatus(target === 'location' ? 'Opened output location' : 'Opened generated PDF', 'ok');
    } catch (error) { setStatus(String(error.message || error), 'error'); }
  }
  async function preview() {
    const documentId = activeDocumentId();
    if (!documentId || rendering) return;

    const previewWindow = window.open('about:blank', PREVIEW_WINDOW);
    if (!previewWindow) {
      setStatus('Browser blocked the preview tab.', 'error');
      return;
    }
    try {
      previewWindow.document.title = 'JAW · Rendering Preview';
      previewWindow.document.body.innerHTML = '<div style="padding:24px;background:#181a1f;color:#d4d4d4;font:14px Segoe UI,Arial,sans-serif;min-height:100vh;box-sizing:border-box">Rendering preview…</div>';
    } catch (_error) {
      // A reused named window may already be displaying a blob URL. Navigation below still works.
    }

    rendering = true;
    syncButtons();
    setStatus('Rendering preview…');
    try {
      const generated = await workbench.mutate('generate', {
        document_id: documentId,
        preview: true,
        working_buffers: currentWorkingBuffers(),
        ...generationPayload()
      });
      if (!generated.pdf_base64) throw new Error('Renderer returned no PDF preview');
      const url = rememberPreview(documentId, generated.pdf_base64);
      previewWindow.location.replace(url);
      const duration = generated.duration_ms ? ` · ${generated.duration_ms} ms` : '';
      const calls = Array.isArray(generated.generations) && generated.generations.length ? ` · ${generated.generations.length} AI` : '';
      setStatus(`Previewed ${generated.filename || 'PDF'}${duration}${calls}`, 'ok');
    } catch (error) {
      setStatus(String(error.message || error), 'error');
      showPreviewError(previewWindow, error);
    } finally {
      rendering = false;
      syncButtons();
    }
  }
  async function generate() {
    const documentId = activeDocumentId();
    if (!documentId || rendering) return;
    rendering = true;
    syncButtons();
    setStatus('Generating…');
    try {
      const generated = await workbench.mutate('generate', {
        document_id: documentId,
        output_directory: localStorage.getItem('jaw.workbench.outputDirectory') || '',
        working_buffers: currentWorkingBuffers(),
        ...generationPayload()
      });
      if (!generated.pdf_base64) throw new Error('Renderer returned no PDF preview');
      rememberPreview(documentId, generated.pdf_base64);
      if (generated.warning) setStatus(generated.warning, 'error');
      else {
        const duration = generated.duration_ms ? ` · ${generated.duration_ms} ms` : '';
        const calls = Array.isArray(generated.generations) && generated.generations.length ? ` · ${generated.generations.length} AI` : '';
        setStatus(`Generated ${generated.filename || 'PDF'}${duration}${calls}`, 'ok');
      }
      showResultPopup(generated);
    } catch (error) {
      setStatus(String(error.message || error), 'error');
      openError(error);
    } finally {
      rendering = false;
      syncButtons();
    }
  }

  generateButton.addEventListener('click', generate);
  previewButton.addEventListener('click', preview);
  modelButton.addEventListener('click', openModelPopup);
  modelEls.provider?.addEventListener('change', () => {
    const provider = String(modelEls.provider.value || '').toLowerCase();
    modelEls.model.value = provider === generationSettings.inheritedProvider
      ? generationSettings.inheritedModel
      : (PROVIDER_DEFAULTS[provider] || '');
  });
  modelEls.apply?.addEventListener('click', applyModelOverride);
  modelEls.cancel?.addEventListener('click', closeModelPopup);
  modelEls.useUser?.addEventListener('click', useUserGenerationSetting);
  modelPopup.querySelector('.wb-generation-close')?.addEventListener('click', closeModelPopup);
  modelPopup.addEventListener('mousedown', event => { if (event.target === modelPopup) closeModelPopup(); });
  resultPopup.querySelector('.wb-generation-close')?.addEventListener('click', closeResultPopup);
  document.getElementById('wbGenerationDismiss')?.addEventListener('click', closeResultPopup);
  popupEls.open?.addEventListener('click', () => openGenerated('file'));
  popupEls.location?.addEventListener('click', () => openGenerated('location'));
  resultPopup.addEventListener('mousedown', event => { if (event.target === resultPopup) closeResultPopup(); });
  store.subscribe((_snapshot, reason) => {
    syncButtons();
    if (reason === 'load') void refreshGenerationSettings();
  });
  window.addEventListener('beforeunload', () => { for (const url of previews.values()) URL.revokeObjectURL(url); });
  syncButtons();
  void refreshGenerationSettings();
})();
