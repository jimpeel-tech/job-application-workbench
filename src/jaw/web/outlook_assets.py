"""Small, self-contained dashboard surface for Outlook sync."""

from __future__ import annotations

OUTLOOK_PANEL = r'''
<section class="outlook-sync" id="outlookSyncPanel" aria-label="Outlook job mail sync" hidden>
  <div class="outlook-sync-main">
    <strong>Outlook</strong>
    <span class="outlook-sync-status" id="outlookSyncStatus">Checking connection…</span>
    <span class="outlook-sync-summary" id="outlookSyncSummary"></span>
  </div>
  <div class="outlook-sync-actions">
    <select id="outlookSyncDays" aria-label="Outlook sync window">
      <option value="30" selected>30 days</option>
      <option value="90">90 days</option>
      <option value="365">1 year</option>
      <option value="730">2 years</option>
    </select>
    <button class="btn" id="outlookConnect" type="button" hidden>Connect Outlook</button>
    <button class="btn" id="outlookReset" type="button" hidden>Reset test sync</button>
    <button class="btn primary" id="outlookSync" type="button" hidden>Sync Outlook</button>
  </div>
</section>
<dialog id="outlookAuthDialog" class="outlook-auth-dialog">
  <h2>Connect Outlook</h2>
  <p id="outlookAuthMessage" class="muted"></p>
  <div class="outlook-auth-code" id="outlookAuthCode"></div>
  <div class="dialog-actions">
    <a class="btn" id="outlookAuthLink" target="_blank" rel="noopener">Open Microsoft sign-in</a>
    <button class="btn primary" id="outlookAuthComplete" type="button">I've signed in</button>
    <button class="btn" id="outlookAuthCancel" type="button">Cancel</button>
  </div>
</dialog>
'''

OUTLOOK_STYLE = r'''
<style id="outlookSyncStyle">
.outlook-sync{display:flex;align-items:center;gap:14px;margin:12px 16px 0;padding:10px 12px;border:1px solid #343943;border-radius:8px;background:#202329}.outlook-sync[hidden]{display:none}
.outlook-sync-main{display:flex;align-items:baseline;gap:10px;min-width:0;flex:1}.outlook-sync-status,.outlook-sync-summary{color:#aab2bf;font-size:13px}.outlook-sync-summary{white-space:nowrap}.outlook-sync-actions{display:flex;gap:8px;align-items:center}.outlook-sync select{min-width:92px}
.outlook-auth-dialog{max-width:560px;background:#202329;color:#eef1f5;border:1px solid #444b57;border-radius:10px;padding:20px}.outlook-auth-dialog::backdrop{background:#0008}.outlook-auth-code{font:600 24px/1.2 Consolas,monospace;letter-spacing:2px;padding:14px;margin:14px 0;background:#15171b;border-radius:6px;text-align:center}.outlook-auth-dialog .dialog-actions{display:flex;gap:8px;justify-content:flex-end;align-items:center}
@media(max-width:850px){.outlook-sync{align-items:flex-start;flex-direction:column}.outlook-sync-actions{width:100%}.outlook-sync-summary{white-space:normal}}
</style>
'''

OUTLOOK_SCRIPT = r'''
<script id="outlookSyncScript">
(() => {
  const byId = id => document.getElementById(id);
  const panel = byId('outlookSyncPanel');
  if (!panel) return;
  const status = byId('outlookSyncStatus'), summary = byId('outlookSyncSummary');
  const connect = byId('outlookConnect'), reset = byId('outlookReset');
  const sync = byId('outlookSync'), days = byId('outlookSyncDays');
  const dialog = byId('outlookAuthDialog'), authMessage = byId('outlookAuthMessage');
  const authCode = byId('outlookAuthCode'), authLink = byId('outlookAuthLink');
  const authComplete = byId('outlookAuthComplete'), authCancel = byId('outlookAuthCancel');
  const json = async (path, body) => {
    const options = body === undefined ? {cache:'no-store'} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)};
    const response = await fetch(path, options), data = await response.json();
    if (!response.ok && response.status !== 207) throw new Error(data.error || 'Outlook request failed');
    return data;
  };
  const render = data => {
    if (!data.enabled) {
      panel.hidden = true;
      return;
    }
    panel.hidden = false;
    const auth = data.auth || {}, state = data.sync || {};
    status.textContent = auth.message || 'Outlook';
    connect.hidden = !auth.configured || auth.connected;
    sync.hidden = !auth.connected;
    reset.hidden = !auth.connected || !state.last_sync_at;
    if (!auth.configured) status.textContent = 'Setup required · set JAW_OUTLOOK_CLIENT_ID';
    if (state.last_sync_at) summary.textContent = `${state.last_scanned || 0} scanned · ${state.last_updated || 0} status updates · ${state.last_review || 0} review`;
    else summary.textContent = '';
  };
  const refresh = async () => { try { render(await json('/api/outlook/status')); } catch (error) { panel.hidden = true; status.textContent = error.message; } };
  connect.onclick = async () => {
    connect.disabled = true;
    try {
      const flow = await json('/api/outlook/auth/start', {});
      authMessage.textContent = flow.message || 'Open Microsoft sign-in and enter this code.';
      authCode.textContent = flow.user_code || '';
      authLink.href = flow.verification_uri || 'https://microsoft.com/devicelogin';
      dialog.showModal();
    } catch (error) { status.textContent = error.message; }
    finally { connect.disabled = false; }
  };
  authComplete.onclick = async () => {
    authComplete.disabled = true; authComplete.textContent = 'Finishing…';
    try { await json('/api/outlook/auth/complete', {}); dialog.close(); await refresh(); }
    catch (error) { authMessage.textContent = error.message; }
    finally { authComplete.disabled = false; authComplete.textContent = "I've signed in"; }
  };
  authCancel.onclick = () => dialog.close();
  reset.onclick = async () => {
    if (!window.confirm('Undo JAW changes from Outlook sync and reprocess these messages on the next sync? Manual status changes made after sync are preserved.')) return;
    reset.disabled = true; sync.disabled = true; summary.textContent = 'Resetting Outlook test sync…';
    try {
      const result = await json('/api/outlook/reset', {});
      summary.textContent = `${result.messages_reset || 0} messages reset · ${result.statuses_restored || 0} statuses restored`;
      if (typeof loadJobs === 'function') await loadJobs();
      if (typeof selectedJob !== 'undefined' && selectedJob && typeof showJob === 'function') await showJob(selectedJob);
      await refresh();
    } catch (error) { summary.textContent = error.message; }
    finally { reset.disabled = false; sync.disabled = false; }
  };
  sync.onclick = async () => {
    sync.disabled = true; sync.textContent = 'Syncing…'; summary.textContent = 'Reading Outlook with local Ollama classification…';
    try {
      const result = await json('/api/outlook/sync', {days:Number(days.value || 30)});
      summary.textContent = `${result.scanned} scanned · ${result.updated} status updates · ${result.categorized} categorized · ${result.review} review${result.errors ? ` · ${result.errors} errors` : ''}${result.truncated ? ' · message limit reached' : ''}`;
      if (typeof loadJobs === 'function') await loadJobs();
      if (typeof selectedJob !== 'undefined' && selectedJob && typeof showJob === 'function') await showJob(selectedJob);
      await refresh();
    } catch (error) { summary.textContent = error.message; }
    finally { sync.disabled = false; sync.textContent = 'Sync Outlook'; }
  };
  refresh();
})();
</script>
'''


def decorate_dashboard(html: str) -> str:
    marker = '<div id="jobsPage" class="page active">\n'
    if marker not in html:
        raise RuntimeError("dashboard.html is missing the Job Tracker page marker")
    html = html.replace(marker, marker + OUTLOOK_PANEL, 1)
    return html.replace("</head>", OUTLOOK_STYLE + "</head>", 1).replace(
        "</body>", OUTLOOK_SCRIPT + "</body>", 1
    )


__all__ = ["decorate_dashboard"]
