const $ = id => document.getElementById(id), esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); let selectedJob = null, userData = { users: [] };
$('menuButton').onclick = () => $('drawer').classList.toggle('open'); document.querySelectorAll('.nav').forEach(b => b.onclick = () => { document.querySelectorAll('.page').forEach(p => p.classList.remove('active')); $(b.dataset.page).classList.add('active'); $('drawer').classList.remove('open'); if (b.dataset.page === 'userPage') loadUserData(); renderTips() }); document.addEventListener('keydown', e => { if (e.key === 'Escape' && $('drawer').classList.contains('open')) { $('drawer').classList.remove('open'); e.preventDefault() } });
async function api(path, body) { const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); if (!r.ok) throw new Error((await r.json()).error || 'Save failed'); return r.json() } function toast(t) { $('toast').textContent = t; $('toast').style.display = 'block'; setTimeout(() => $('toast').style.display = 'none', 1600) }
const TRACKER_STATUSES = ['Captured', 'Reviewing', 'Interested', 'Applying', 'Applied', 'Recruiter Screen', 'Interviewing', 'Offer', 'Rejected', 'Withdrawn', 'Archived'];
let trackerCurrentJob = null, trackerTab = 'overview', trackerReusableAnswers = [], trackerEditingIdentity = false;
function trackerText(value, fallback = '—') { const text = String(value ?? '').trim(); return text || fallback }
function trackerDate(value) { if (!value) return '—'; return String(value).replace('T', ' ').replace('Z', '').slice(0, 16) }
function trackerMoney(value, currency = 'USD') { const number = Number(value); if (!Number.isFinite(number)) return ''; try { return new Intl.NumberFormat(undefined, { style: 'currency', currency: currency || 'USD', maximumFractionDigits: 0 }).format(number) } catch { return `${currency || '$'} ${Math.round(number).toLocaleString()}` } }
function trackerPay(job) { const low = trackerMoney(job.pay_min, job.currency), high = trackerMoney(job.pay_max, job.currency); if (low && high && low !== high) return `${low}–${high}${job.pay_period ? ` / ${job.pay_period}` : ''}`; return (low || high) ? `${low || high}${job.pay_period ? ` / ${job.pay_period}` : ''}` : 'Not listed' }
function trackerList(items, empty = 'None identified') { return (items || []).length ? `<ul class="tracker-list">${items.map(item => `<li>${esc(item)}</li>`).join('')}</ul>` : `<div class="tracker-empty-inline">${esc(empty)}</div>` }
function trackerStatusOptions(current) { return TRACKER_STATUSES.map(status => `<option ${status === current ? 'selected' : ''}>${esc(status)}</option>`).join('') }
function trackerJobCard(job) { const meta = [trackerText(job.remote_status, ''), trackerText(job.location, ''), job.question_count ? `${job.question_count} Q&A` : ''].filter(Boolean); return `<div class="job tracker-job ${job.id === selectedJob ? 'active' : ''}" onclick="showJob(${job.id})"><div class="tracker-job-top"><div class="tracker-job-title">${esc(job.title || 'Untitled job')}</div><div class="tracker-job-score">${job.match_score ?? '—'}%</div></div><div class="tracker-job-company">${esc(job.company || 'Unknown company')}</div><div class="tracker-job-meta"><span class="tracker-job-status">${esc(job.status || 'Captured')}</span>${meta.map(value => `<span>${esc(value)}</span>`).join('')}</div></div>` }
async function loadJobs() { const p = new URLSearchParams({ q: $('search').value, sort: $('sort').value, status: $('status').value }); const response = await fetch('/api/jobs?' + p, { cache: 'no-store' }); const rows = await response.json(); $('jobs').innerHTML = rows.map(trackerJobCard).join('') || '<div class="empty">No jobs found.</div>' }
function trackerSplitConcerns(job) { const unassessed = [], concerns = []; for (const item of (job.concerns || [])) { (/(?:0\s*\/\s*5|unrated|unassessed)/i.test(item) ? unassessed : concerns).push(item) } return { unassessed, concerns } }
function trackerOverview(job) { const split = trackerSplitConcerns(job), watch = [...split.concerns, ...(job.missing_qualifications || [])].slice(0, 5); return `<div class="tracker-grid"><section class="tracker-card"><h2>Current analysis</h2><div class="tracker-summary">${esc(job.summary || 'No analysis summary is available yet.')}</div></section><section class="tracker-card"><h2>At a glance</h2><div class="tracker-stat-grid"><div class="tracker-stat"><label>Status</label><strong>${esc(job.status || 'Captured')}</strong></div><div class="tracker-stat"><label>Match</label><strong>${job.match_score ?? '—'}%</strong></div><div class="tracker-stat"><label>Application Q&A</label><strong>${(job.questions || []).length}</strong></div><div class="tracker-stat"><label>Captured</label><strong>${esc(trackerDate(job.created_at))}</strong></div><div class="tracker-stat"><label>Work arrangement</label><strong>${esc(trackerText(job.remote_status))}</strong></div><div class="tracker-stat"><label>Pay</label><strong>${esc(trackerPay(job))}</strong></div></div></section><section class="tracker-card"><h2>Top strengths</h2>${trackerList((job.strong_matches || []).slice(0, 5), 'No strong matches identified yet.')}</section><section class="tracker-card"><h2>Watch</h2>${trackerList(watch, 'No current concerns or missing qualifications.')}${split.unassessed.length ? `<div class="tracker-match-group unassessed"><h3>Unassessed, not a gap</h3>${trackerList(split.unassessed)}</div>` : ''}</section></div>` }
function trackerMatch(job) { const split = trackerSplitConcerns(job); return `<section class="tracker-card"><div class="tracker-match-group strong"><h3>Strong matches</h3>${trackerList(job.strong_matches, 'No direct strong matches identified.')}</div><div class="tracker-match-group unassessed"><h3>Unassessed</h3><div class="tracker-empty-inline">Rating 0 means JAW has no proficiency assessment; it is not treated as evidence of a gap.</div>${trackerList(split.unassessed, 'No unrated capability mentions.')}</div><div class="tracker-match-group concern"><h3>Concerns</h3>${trackerList(split.concerns, 'No concerns identified.')}</div><div class="tracker-match-group"><h3>Missing qualifications</h3>${trackerList(job.missing_qualifications, 'No missing qualifications identified.')}</div></section>` }
function trackerReusableOptions() { return `<option value="">Use reusable answer…</option>${trackerReusableAnswers.map((entry, index) => `<option value="${index}">${esc(entry.title)}</option>`).join('')}` }
function trackerQuestionCard(question, index, { draft = false } = {}) { const key = draft ? 'new' : String(question.id), answer = question.submitted_answer || ''; return `<div class="tracker-question-card ${draft ? 'draft' : ''}" data-tracker-question="${key}"><div class="tracker-question-head"><span class="tracker-question-number">${draft ? 'New Q&A' : `Question ${index + 1}`}</span><span class="spacer"></span>${draft ? '' : `<button class="btn tracker-danger-link" onclick="deleteTrackerQuestion(${question.id})">Delete</button>`}</div><div class="tracker-question-fields"><label>Question<input data-tracker-question-text value="${esc(question.question || '')}" placeholder="Application or recruiter question"></label><label>Answer used<textarea data-tracker-answer-text placeholder="Record the answer you submitted or want to remember">${esc(answer)}</textarea></label></div>${!answer && question.suggested_answer ? `<div class="tracker-suggestion"><b>Reusable answer suggestion</b><br>${esc(question.suggested_answer)}<br><button class="btn" onclick="useTrackerSuggestion('${key}')">Use suggestion</button></div>` : ''}<div class="tracker-question-actions"><button class="btn primary" onclick="saveTrackerQuestion('${key}')">Save</button><select onchange="useTrackerReusable('${key}',this)">${trackerReusableOptions()}</select><button class="btn" onclick="saveTrackerReusable('${key}')">Save as reusable Q&A</button></div></div>` }
function trackerTimeline(job) { const events = job.events || []; return events.length ? `<div class="tracker-timeline">${events.map(event => `<div class="tracker-event"><time>${esc(trackerDate(event.occurred_at))}</time><div><b>${esc(event.event_type)}</b>${event.details ? `<div class="muted">${esc(event.details)}</div>` : ''}</div></div>`).join('')}</div>` : '<div class="tracker-empty-inline">No application history yet.</div>' }
function trackerApplication(job) { const questions = job.questions || []; return `<div class="tracker-section-stack"><section class="tracker-card"><div class="tracker-application-head"><h2>Application Q&A</h2><span class="muted">Keep the exact answers you used so they are ready for recruiter screens and interviews.</span><span class="spacer"></span><button class="btn primary" onclick="addTrackerQuestion()">+ Add Q&A</button></div><div class="tracker-question-list" id="trackerQuestions">${questions.map((q, index) => trackerQuestionCard(q, index)).join('') || '<div class="tracker-empty-inline" id="trackerNoQuestions">No questions captured yet. Add one here or capture questions while completing the application.</div>'}</div></section><div class="tracker-grid"><section class="tracker-card"><h2>Application details</h2><div class="tracker-stat-grid"><div class="tracker-stat"><label>Status</label><strong>${esc(job.status || 'Captured')}</strong></div><div class="tracker-stat"><label>Applied</label><strong>${esc(trackerDate(job.applied_at))}</strong></div><div class="tracker-stat"><label>Location</label><strong>${esc(trackerText(job.location))}</strong></div><div class="tracker-stat"><label>Work arrangement</label><strong>${esc(trackerText(job.remote_status))}</strong></div><div class="tracker-stat"><label>Pay</label><strong>${esc(trackerPay(job))}</strong></div><div class="tracker-stat"><label>Job URL</label><strong>${job.source_url ? `<a href="${esc(job.source_url)}" target="_blank" rel="noopener">Open posting</a>` : '—'}</strong></div></div></section><section class="tracker-card"><h2>History</h2>${trackerTimeline(job)}</section></div></div>` }
function trackerDescription(job) { return `<section class="tracker-card tracker-description-card"><h2>Original job description</h2><div class="tracker-description">${esc(job.raw_description || '')}</div></section>` }
function trackerIdentityHeading(job) {
  if (!trackerEditingIdentity) {
    return `<div class="tracker-job-heading"><h1>${esc(job.title || 'Untitled job')}</h1><div class="company">${esc(job.company || 'Unknown company')}</div><div class="tracker-job-facts">${[trackerText(job.remote_status, ''), trackerText(job.location, ''), trackerPay(job)].filter(Boolean).map(value => `<span>${esc(value)}</span>`).join('')}</div></div>`;
  }
  return `<div class="tracker-job-heading tracker-job-heading-edit"><input id="trackerTitleEdit" class="tracker-identity-input tracker-title-input" value="${esc(job.title || '')}" placeholder="Role / title" aria-label="Role / title"><input id="trackerCompanyEdit" class="tracker-identity-input tracker-company-input" value="${esc(job.company || '')}" placeholder="Company" aria-label="Company"><div class="tracker-job-facts">${[trackerText(job.remote_status, ''), trackerText(job.location, ''), trackerPay(job)].filter(Boolean).map(value => `<span>${esc(value)}</span>`).join('')}</div></div>`;
}
function editTrackerIdentity() {
  if (!trackerCurrentJob) return;
  trackerEditingIdentity = true;
  renderTrackerJob();
  const title = $('trackerTitleEdit');
  if (title) { title.focus(); title.select(); }
}
function cancelTrackerIdentity() { trackerEditingIdentity = false; renderTrackerJob(); }
function trackerIdentityKeydown(event) {
  if (event.key === 'Enter') { event.preventDefault(); void saveTrackerIdentity(); }
  else if (event.key === 'Escape') { event.preventDefault(); cancelTrackerIdentity(); }
}
async function saveTrackerIdentity() {
  if (!trackerCurrentJob) return;
  const title = $('trackerTitleEdit')?.value.trim() || '';
  const company = $('trackerCompanyEdit')?.value.trim() || '';
  if (!company || !title) { toast('Company and role / title are required'); return; }
  const result = await api(`/api/jobs/${trackerCurrentJob.id}/identity`, { company, title });
  trackerCurrentJob = result.job || { ...trackerCurrentJob, company, title };
  trackerEditingIdentity = false;
  renderTrackerJob();
  loadJobs();
  toast('Job details saved');
}
function renderTrackerJob() {
  const job = trackerCurrentJob;
  if (!job) return;
  const tabBody = trackerTab === 'match' ? trackerMatch(job) : trackerTab === 'application' ? trackerApplication(job) : trackerTab === 'description' ? trackerDescription(job) : trackerOverview(job);
  const identityActions = trackerEditingIdentity ? `<button class="btn primary" onclick="saveTrackerIdentity()">Save details</button><button class="btn" onclick="cancelTrackerIdentity()">Cancel</button>` : `<button class="btn" onclick="editTrackerIdentity()">Edit details</button>`;
  $('detail').innerHTML = `<div class="tracker-job-header"><div class="tracker-job-header-top">${trackerIdentityHeading(job)}<div class="tracker-header-actions"><div class="tracker-match-score"><span>${job.match_score ?? '—'}%</span><small>match</small></div><select class="tracker-status-select" id="trackerStatusSelect">${trackerStatusOptions(job.status)}</select>${identityActions}${job.source_url ? `<a class="btn" href="${esc(job.source_url)}" target="_blank" rel="noopener">Open job</a>` : ''}<button class="btn tracker-document-action" onclick="openTrackerDocuments(${job.id})">Generate Document</button><span class="tracker-action-divider" aria-hidden="true"></span><button class="btn tracker-danger-link" onclick="deleteJob(${job.id})">Delete</button></div></div><nav class="tracker-tabs"><button class="tracker-tab ${trackerTab === 'overview' ? 'active' : ''}" onclick="setTrackerTab('overview')">Overview</button><button class="tracker-tab ${trackerTab === 'match' ? 'active' : ''}" onclick="setTrackerTab('match')">Match</button><button class="tracker-tab ${trackerTab === 'application' ? 'active' : ''}" onclick="setTrackerTab('application')">Application${(job.questions || []).length ? ` · ${(job.questions || []).length}` : ''}</button><button class="tracker-tab ${trackerTab === 'description' ? 'active' : ''}" onclick="setTrackerTab('description')">Job Description</button></nav></div><div class="tracker-detail-body">${tabBody}</div>`;
  $('trackerStatusSelect').onchange = event => updateTrackerStatus(event.target.value);
  if (trackerEditingIdentity) {
    $('trackerTitleEdit').onkeydown = trackerIdentityKeydown;
    $('trackerCompanyEdit').onkeydown = trackerIdentityKeydown;
  }
}
async function showJob(id) { selectedJob = id; trackerEditingIdentity = false; const [job, user] = await Promise.all([fetch('/api/jobs/' + id, { cache: 'no-store' }).then(r => { if (!r.ok) throw new Error('Job not found'); return r.json() }), fetch('/api/user-data', { cache: 'no-store' }).then(r => r.json())]); trackerCurrentJob = job; trackerReusableAnswers = user.answers || []; renderTrackerJob(); loadJobs() }
function setTrackerTab(tab) { trackerTab = tab; renderTrackerJob() }
async function updateTrackerStatus(status) { if (!trackerCurrentJob) return; const result = await api(`/api/jobs/${trackerCurrentJob.id}/status`, { status }); trackerCurrentJob = result.job || { ...trackerCurrentJob, status }; renderTrackerJob(); loadJobs(); toast(`Status · ${status}`) }
function trackerQuestionNode(key) { return document.querySelector(`[data-tracker-question="${CSS.escape(String(key))}"]`) }
function addTrackerQuestion() { trackerTab = 'application'; if (!trackerCurrentJob) return; if (trackerQuestionNode('new')) { trackerQuestionNode('new').querySelector('[data-tracker-question-text]').focus(); return } renderTrackerJob(); const host = $('trackerQuestions'), empty = $('trackerNoQuestions'); if (empty) empty.remove(); host.insertAdjacentHTML('afterbegin', trackerQuestionCard({ question: '', submitted_answer: '', suggested_answer: '' }, -1, { draft: true })); trackerQuestionNode('new').querySelector('[data-tracker-question-text]').focus() }
async function saveTrackerQuestion(key) { if (!trackerCurrentJob) return; const node = trackerQuestionNode(key); if (!node) return; const question = node.querySelector('[data-tracker-question-text]').value.trim(), answer = node.querySelector('[data-tracker-answer-text]').value; if (!question) { toast('Question is required'); return } const path = key === 'new' ? `/api/jobs/${trackerCurrentJob.id}/questions` : `/api/jobs/${trackerCurrentJob.id}/questions/${key}`; const result = await api(path, { question, answer }); trackerCurrentJob = result.job || trackerCurrentJob; renderTrackerJob(); loadJobs(); toast('Q&A saved') }
async function deleteTrackerQuestion(questionId) { if (!trackerCurrentJob || !confirm('Delete this Q&A from the job?')) return; const response = await fetch(`/api/jobs/${trackerCurrentJob.id}/questions/${questionId}`, { method: 'DELETE' }), result = await response.json(); if (!response.ok) { toast(result.error || 'Delete failed'); return } trackerCurrentJob = result.job || trackerCurrentJob; renderTrackerJob(); loadJobs(); toast('Q&A deleted') }
function useTrackerSuggestion(key) { const node = trackerQuestionNode(key); if (!node || !trackerCurrentJob) return; const question = (trackerCurrentJob.questions || []).find(item => String(item.id) === String(key)); if (question) node.querySelector('[data-tracker-answer-text]').value = question.suggested_answer || '' }
function useTrackerReusable(key, select) { const node = trackerQuestionNode(key), entry = trackerReusableAnswers[Number(select.value)]; if (node && entry) node.querySelector('[data-tracker-answer-text]').value = entry.answer || ''; select.value = '' }
async function saveTrackerReusable(key) { const node = trackerQuestionNode(key); if (!node) return; const title = node.querySelector('[data-tracker-question-text]').value.trim(), answer = node.querySelector('[data-tracker-answer-text]').value; if (!title || !answer.trim()) { toast('Add both a question and answer first'); return } const current = await fetch('/api/user-data', { cache: 'no-store' }).then(r => r.json()), answers = [...(current.answers || [])], normalized = title.toLocaleLowerCase(), index = answers.findIndex(entry => String(entry.title || '').trim().toLocaleLowerCase() === normalized); if (index >= 0) answers[index] = { title, answer }; else answers.unshift({ title, answer }); await api('/api/user/answers', { answers }); trackerReusableAnswers = answers; document.querySelectorAll('.tracker-question-actions select').forEach(select => { select.innerHTML = trackerReusableOptions() }); toast(index >= 0 ? 'Reusable Q&A updated' : 'Reusable Q&A added') }
async function deleteJob(id) { if (confirm('Permanently delete this job and its captured Q&A?')) { await fetch('/api/jobs/' + id, { method: 'DELETE' }); selectedJob = null; trackerCurrentJob = null; $('detail').innerHTML = '<div class="empty">Select a job to review it.</div>'; loadJobs() } }

// Document Studio -----------------------------------------------------------
// The web UI deliberately treats the document API as a domain boundary. It
// composes profiles, blueprints, content templates, and reusable blocks here;
// rendering and persistence remain server responsibilities.
const DOCUMENT_VIEWS = {
  profiles: { key: 'generation_profiles', title: 'Generation Profiles', eyebrow: 'Recipe', hint: 'Combine a blueprint with a content strategy to generate a document.', empty: 'No generation profiles yet.' },
  blueprints: { key: 'blueprints', title: 'Document Blueprints', eyebrow: 'Construction', hint: 'Blueprints define fields, rendering options, and the final document layout.', empty: 'No document blueprints yet.' },
  content_templates: { key: 'content_templates', title: 'Content Templates', eyebrow: 'Composition', hint: 'Content templates arrange reusable blocks and define the overall writing strategy.', empty: 'No content templates yet.' },
  content_blocks: { key: 'content_blocks', title: 'Content Blocks', eyebrow: 'Content unit', hint: 'Blocks combine reusable content with ordered generation expressions.', empty: 'No content blocks yet.' }
};
let documentState = { render_templates: [], blueprints: [], content_blocks: [], content_templates: [], generation_profiles: [], generated_documents: [], jobs: [] };
let documentView = 'profiles', selectedDocumentId = '', documentGenerating = false, documentEditor = null, draggedDocumentPlacement = -1, draggedDocumentExpression = -1, draggedDraftBlock = -1, documentLoadVersion = 0;
let trackerDocumentJob = null, trackerDocumentProfileId = '', trackerDocumentId = '';
function documentId(item) { return String(item?.id ?? item?.key ?? item?.slug ?? '') }
function documentName(item, fallback = 'Untitled') { return String(item?.name ?? item?.title ?? item?.display_name ?? item?.block_name ?? item?.profile_name ?? fallback) }
function documentItems(view = documentView) { return documentState[DOCUMENT_VIEWS[view]?.key] || [] }
function documentById(collection, id) { return (documentState[collection] || []).find(item => documentId(item) === String(id)) }
function documentLinkedName(collection, id, fallback = 'Not selected') { return documentName(documentById(collection, id), fallback) }
function documentModeLabel(mode) { return String(mode || 'generated').replaceAll('_', ' ').replace(/\b\w/g, value => value.toUpperCase()) }
function documentDate(value) { return value ? trackerDate(value) : 'Not rendered yet' }
function normalizeDocumentState(payload) {
  const source = payload?.documents || payload?.state || payload || {};
  for (const key of ['render_templates', 'blueprints', 'content_blocks', 'content_templates', 'generation_profiles', 'generated_documents', 'jobs']) {
    documentState[key] = Array.isArray(source[key]) ? source[key] : (documentState[key] || []);
  }
  documentState.expression_reference = source.expression_reference || source.generation_reference || documentState.expression_reference || {};
  return documentState;
}
async function documentApiGet(path) { const response = await fetch(path, { cache: 'no-store' }); const result = await response.json().catch(() => ({})); if (!response.ok) throw new Error(result.error || `Document request failed (${response.status})`); return result }
async function loadDocuments({ keepSelection = true } = {}) {
  const loadVersion = ++documentLoadVersion, payload = await documentApiGet('/api/documents/state');
  if (loadVersion !== documentLoadVersion) return;
  normalizeDocumentState(payload);
  if (!documentState.jobs.length) {
    try { const jobs = await documentApiGet('/api/jobs?q=&sort=updated_at&status='); if (loadVersion !== documentLoadVersion) return; documentState.jobs = jobs } catch { documentState.jobs = [] }
  }
  const items = documentItems();
  if (!keepSelection || !items.some(item => documentId(item) === selectedDocumentId)) selectedDocumentId = documentId(items[0]);
  renderDocumentStudio();
}
function documentListMeta(item) {
  if (documentView === 'profiles') return `${documentLinkedName('blueprints', item.blueprint_id, 'Blueprint')} · ${documentLinkedName('content_templates', item.content_template_id, 'Content template')}`;
  if (documentView === 'blueprints') return `${documentModeLabel(item.renderer || item.renderer_name || 'Tectonic')} · ${(item.fields || item.field_definitions || []).length} fields`;
  if (documentView === 'content_templates') return `${(item.blocks || item.block_placements || item.content_blocks || []).length} blocks`;
  if (documentView === 'content_blocks') return `${(item.expressions || []).length} generation expressions`;
  return '';
}
function renderDocumentList() {
  const query = $('documentSearch').value.trim().toLocaleLowerCase();
  const items = documentItems().filter(item => `${documentName(item)} ${documentListMeta(item)}`.toLocaleLowerCase().includes(query));
  $('documentList').innerHTML = items.map(item => `<button class="document-list-item ${documentId(item) === selectedDocumentId ? 'active' : ''}" type="button" data-document-id="${esc(documentId(item))}"><b>${esc(documentName(item, 'Untitled'))}</b><span>${esc(documentListMeta(item))}</span></button>`).join('') || `<div class="document-list-empty">${esc(query ? 'No matching items.' : DOCUMENT_VIEWS[documentView].empty)}</div>`;
  document.querySelectorAll('[data-document-id]').forEach(button => button.onclick = () => { selectedDocumentId = button.dataset.documentId; documentEditor = null; renderDocumentStudio() });
}
function documentDefinitionRows(rows) {
  return (rows || []).length ? `<div class="document-definition-list">${rows.map(row => `<div><b>${esc(row.name || row.key || row.field || 'Field')}</b><span>${esc(row.field_type || row.type || row.value_type || (row.required ? 'Required' : 'Optional'))}${row.required ? ' · Required' : ''}</span></div>`).join('')}</div>` : '<div class="document-empty-inline">No field definitions.</div>';
}
function documentPlacementRows(template) {
  const placements = template?.block_placements || template?.blocks || template?.content_blocks || [];
  if (!placements.length) return '<div class="document-empty-inline">No content blocks in this template.</div>';
  return `<div class="document-block-stack">${placements.map((placement, index) => { const block = placement.block || documentById('content_blocks', placement.block_id ?? placement.content_block_id ?? placement.id) || placement, details = [`${(block.expressions || []).length} expressions`, placement.required || block.required ? 'Required' : '', placement.max_length || block.max_length ? `${placement.max_length || block.max_length} max` : ''].filter(Boolean); return `<div class="document-block-row"><span>${index + 1}</span><div><b>${esc(documentName(block, 'Content block'))}</b><small>${esc(details.join(' · '))}</small></div></div>` }).join('')}</div>`;
}
function renderBlueprint(blueprint) {
  const renderTemplate = blueprint.render_template || documentById('render_templates', blueprint.render_template_id);
  return `<section class="document-editor-card"><div class="document-editor-title"><div><div class="document-eyebrow">Document Blueprint</div><h2>${esc(documentName(blueprint))}</h2></div>${documentReadActions()}</div><p class="document-copy">${esc(blueprint.description || 'Defines how document fields are resolved and rendered.')}</p><div class="document-stat-grid"><div class="document-stat"><span>Renderer</span><b>${esc(documentModeLabel(blueprint.renderer || 'Tectonic'))}</b></div><div class="document-stat"><span>Output</span><b>${esc(String(blueprint.output_format || 'PDF').toUpperCase())}</b></div><div class="document-stat"><span>Render template</span><b>${esc(documentName(renderTemplate, 'Not selected'))}</b></div></div><h3>Input contract</h3>${documentDefinitionRows(blueprint.fields || blueprint.field_definitions)}</section>`;
}
function generatedPdfUrl(item) { return `/api/documents/generated/${encodeURIComponent(documentId(item))}/pdf` }
function showTrackerGeneratedPreview(item) { const url = generatedPdfUrl(item); $('trackerDocumentDownload').href = url; $('trackerDocumentDownload').hidden = false; $('trackerDocumentPreview').innerHTML = `<iframe title="Generated document preview" src="${esc(url)}"></iframe>` }
function clearTrackerGeneratedPreview() { $('trackerDocumentDownload').hidden = true; $('trackerDocumentDownload').removeAttribute('href'); $('trackerDocumentPreview').innerHTML = '<div class="document-preview-empty"><b>No PDF selected</b><span>Render a draft or choose a generated document.</span></div>' }
async function seedDocuments() {
  try { const result = await api('/api/documents/seed', {}); normalizeDocumentState(result); await loadDocuments({ keepSelection: false }); toast('Starter document recipe ready') } catch (error) { toast(error.message) }
}
// Document authoring and draft review ---------------------------------------
const DOCUMENT_AUTHORING = {
  profiles: { singular: 'profile', endpoint: 'profiles', key: 'generation_profiles', payload: 'profile' },
  blueprints: { singular: 'blueprint', endpoint: 'blueprints', key: 'blueprints', payload: 'blueprint' },
  content_templates: { singular: 'content template', endpoint: 'content-templates', key: 'content_templates', payload: 'content_template' },
  content_blocks: { singular: 'content block', endpoint: 'content-blocks', key: 'content_blocks', payload: 'block' }
};
function documentClone(value) { return structuredClone(value || {}) }
function documentEditorActions() {
  return '<div class="document-editor-actions"><button class="btn primary" id="documentEditSave" type="button">Save</button><button class="btn" id="documentEditCancel" type="button">Cancel</button></div>';
}
function documentReadActions() {
  if (!DOCUMENT_AUTHORING[documentView]) return '';
  return '<div class="document-editor-actions"><button class="btn" id="documentEdit" type="button">Edit</button><button class="btn" id="documentDuplicate" type="button">Duplicate</button><button class="btn danger" id="documentDelete" type="button">Delete</button></div>';
}
function documentFieldInput(label, id, value = '', options = '') {
  return `<label class="document-form-field ${options}"><span>${esc(label)}</span><input id="${id}" value="${esc(value)}"></label>`;
}
function documentTextarea(label, id, value = '', hint = '') {
  return `<label class="document-form-field document-form-wide"><span>${esc(label)}</span><textarea id="${id}">${esc(value)}</textarea>${hint ? `<small>${esc(hint)}</small>` : ''}</label>`;
}
function documentSelectOptions(collection, selected, emptyLabel) {
  return `<option value="">${esc(emptyLabel)}</option>${(documentState[collection] || []).map(item => `<option value="${esc(documentId(item))}" ${String(documentId(item)) === String(selected || '') ? 'selected' : ''}>${esc(documentName(item))}</option>`).join('')}`;
}
function documentBlockDefaults(block) {
  const settings = block?.settings || {};
  return {
    required: Boolean(settings.default_required ?? settings.required ?? block?.required),
    enabled: Boolean(settings.default_enabled ?? settings.enabled ?? true),
    max_length: settings.default_max_length ?? settings.max_length ?? block?.max_length ?? ''
  };
}
function documentBlockExpressions(block) { return documentClone(block.expressions || []).map((expression, index) => ({ ...expression, expression_key: expression.expression_key || expression.key || '', name: expression.name || expression.expression_key || expression.key || '', sort_order: index })) }
function documentExpressionRows(expressions) {
  if (!expressions.length) return '<div class="document-empty-inline document-placement-empty">No generation expressions. Add one when part of this block should be generated from instructions.</div>';
  return expressions.map((expression, index) => `<article class="document-expression-editor" data-expression-index="${index}"><button class="document-drag-handle" draggable="true" type="button" aria-label="Drag expression to reorder" title="Drag to reorder">&#8942;&#8942;</button><label class="document-form-field"><span>Expression key</span><input data-expression-key value="${esc(expression.expression_key || expression.key || '')}" placeholder="strongest_match"></label><label class="document-form-field"><span>Name</span><input data-expression-name value="${esc(expression.name || '')}" placeholder="Strongest match"></label><label class="document-form-field document-expression-max"><span>Max length</span><input data-expression-max type="number" min="0" value="${esc(expression.max_length || '')}" placeholder="None"></label><label class="document-form-field document-expression-instructions"><span>Instructions</span><textarea data-expression-instructions>${esc(expression.instructions || '')}</textarea></label><div class="document-placement-actions"><button class="btn" type="button" data-expression-up="${index}" ${index === 0 ? 'disabled' : ''} aria-label="Move up">&#8593;</button><button class="btn" type="button" data-expression-down="${index}" ${index === expressions.length - 1 ? 'disabled' : ''} aria-label="Move down">&#8595;</button><button class="btn danger" type="button" data-expression-remove="${index}">Delete</button></div></article>`).join('');
}
function renderContentBlockEditor(block) {
  const expressions = documentBlockExpressions(block); documentEditor.expressions = expressions;
  return `<section class="document-editor-card document-authoring-card"><div class="document-editor-title"><div><div class="document-eyebrow">${block.id ? 'Edit content block' : 'New content block'}</div><h2>${esc(block.name || 'Untitled block')}</h2></div>${documentEditorActions()}</div><div class="document-form-grid">${documentFieldInput('Name', 'documentBlockName', block.name || '')}${documentFieldInput('Description', 'documentBlockDescription', block.description || '')}${documentTextarea('Content', 'documentBlockContent', block.content || '', 'Use placeholders such as {{ company }}, {{ position_name }}, or an expression key.')}</div><div class="document-composition-head"><div><h3>Generation expressions</h3><p class="muted">Ordered AI instructions that resolve named values for this block.</p></div><button class="btn" id="documentAddExpression" type="button">+ Add expression</button></div><div id="documentExpressionEditor" class="document-expression-list">${documentExpressionRows(expressions)}</div></section>`;
}
function documentTemplatePlacements(template) {
  return documentClone(template.blocks || template.block_placements || template.content_blocks || []).map((placement, index) => {
    const block = placement.block || documentById('content_blocks', placement.block_id ?? placement.content_block_id ?? placement.id) || {};
    const defaults = documentBlockDefaults(block);
    return {
      ...placement,
      block_id: placement.block_id ?? placement.content_block_id ?? block.id,
      block,
      enabled: Boolean(placement.enabled ?? defaults.enabled),
      required: Boolean(placement.required ?? defaults.required),
      max_length: placement.max_length ?? defaults.max_length ?? '',
      sort_order: index
    };
  });
}
function documentPlacementEditorRows(placements) {
  if (!placements.length) return '<div class="document-empty-inline document-placement-empty">No blocks yet. Add one from the menu below.</div>';
  return placements.map((placement, index) => {
    const block = placement.block || documentById('content_blocks', placement.block_id) || {};
    return `<article class="document-placement-editor" draggable="true" data-placement-index="${index}" data-block-id="${esc(placement.block_id)}"><button class="document-drag-handle" type="button" title="Drag to reorder" aria-label="Drag ${esc(documentName(block, 'block'))} to reorder">&#8942;&#8942;</button><div class="document-placement-copy"><b>${esc(documentName(block, 'Missing block'))}</b><small>${(block.expressions || []).length} expressions</small></div><label class="document-check"><input data-placement-enabled type="checkbox" ${placement.enabled ? 'checked' : ''}> Enabled</label><label class="document-check"><input data-placement-required type="checkbox" ${placement.required ? 'checked' : ''}> Required</label><label class="document-placement-limit"><span>Max</span><input data-placement-max type="number" min="0" value="${esc(placement.max_length)}" placeholder="None"></label><div class="document-placement-actions"><button class="btn" type="button" data-placement-up="${index}" ${index === 0 ? 'disabled' : ''} aria-label="Move up">&#8593;</button><button class="btn" type="button" data-placement-down="${index}" ${index === placements.length - 1 ? 'disabled' : ''} aria-label="Move down">&#8595;</button><button class="btn danger" type="button" data-placement-remove="${index}">Remove</button></div></article>`;
  }).join('');
}
function renderContentTemplateEditor(template) {
  const placements = documentTemplatePlacements(template);
  documentEditor.placements = placements;
  return `<section class="document-editor-card document-authoring-card"><div class="document-editor-title"><div><div class="document-eyebrow">${template.id ? 'Edit content template' : 'New content template'}</div><h2>${esc(template.name || 'Untitled template')}</h2></div>${documentEditorActions()}</div><div class="document-form-grid">${documentFieldInput('Name', 'documentTemplateName', template.name || '')}${documentFieldInput('Description', 'documentTemplateDescription', template.description || '')}${documentTextarea('Global generation instructions', 'documentTemplateInstructions', template.instructions || template.generation_instructions || '', 'These instructions apply to every block in this composition.')}</div><div class="document-composition-head"><div><h3>Ordered composition</h3><p class="muted">Drag blocks or use the arrow controls. Placement settings override block defaults.</p></div><label class="document-add-block"><span>Add block</span><select id="documentAddTemplateBlock"><option value="">Choose a reusable block...</option>${(documentState.content_blocks || []).map(block => `<option value="${esc(documentId(block))}">${esc(documentName(block))}</option>`).join('')}</select></label></div><div id="documentPlacementEditor" class="document-placement-list">${documentPlacementEditorRows(placements)}</div></section>`;
}
function documentBlueprintFields(blueprint) { return documentClone(blueprint.fields || blueprint.field_definitions || []).map((field, index) => ({ ...field, field_key: field.field_key || field.key || field.name || '', sort_order: index })) }
function documentBlueprintFieldRows(fields) {
  if (!fields.length) return '<div class="document-empty-inline document-placement-empty">No field definitions yet.</div>';
  return fields.map((field, index) => { const type = field.field_type || field.type || 'text'; return `<article class="document-blueprint-field" data-blueprint-field-index="${index}"><label class="document-form-field"><span>Field key</span><input data-blueprint-field-key value="${esc(field.field_key)}" placeholder="company"></label><label class="document-form-field"><span>Label</span><input data-blueprint-field-label value="${esc(field.label || field.display_label || '')}" placeholder="Company"></label><label class="document-form-field"><span>Type</span><select data-blueprint-field-type><option value="text" ${type === 'text' ? 'selected' : ''}>Text</option><option value="multiline" ${type === 'multiline' ? 'selected' : ''}>Multi-line</option><option value="date" ${type === 'date' ? 'selected' : ''}>Date</option><option value="list" ${type === 'list' ? 'selected' : ''}>List</option><option value="block_collection" ${type === 'block_collection' ? 'selected' : ''}>Block collection</option></select></label><label class="document-form-field"><span>Source path</span><input data-blueprint-field-source value="${esc(field.source_path || '')}" placeholder="job.company"></label><label class="document-form-field"><span>Field scope</span><input data-blueprint-field-scope value="${esc(field.field_scope || '')}" placeholder="standard"></label><label class="document-check"><input data-blueprint-field-required type="checkbox" ${field.required ? 'checked' : ''}> Required</label><label class="document-form-field"><span>Default</span><input data-blueprint-field-default value="${esc(field.default_value || field.default || '')}"></label><div class="document-placement-actions"><button class="btn" type="button" data-blueprint-field-up="${index}" ${index === 0 ? 'disabled' : ''} aria-label="Move up">&#8593;</button><button class="btn" type="button" data-blueprint-field-down="${index}" ${index === fields.length - 1 ? 'disabled' : ''} aria-label="Move down">&#8595;</button><button class="btn danger" type="button" data-blueprint-field-remove="${index}">Delete</button></div></article>` }).join('');
}
function renderBlueprintEditor(blueprint) {
  const renderTemplate = documentClone(blueprint.render_template || documentById('render_templates', blueprint.render_template_id) || {}), fields = documentBlueprintFields(blueprint); documentEditor.blueprintFields = fields; documentEditor.renderTemplate = renderTemplate;
  return `<section class="document-editor-card document-authoring-card"><div class="document-editor-title"><div><div class="document-eyebrow">${blueprint.id ? 'Edit document blueprint' : 'New document blueprint'}</div><h2>${esc(blueprint.name || 'Untitled blueprint')}</h2></div>${documentEditorActions()}</div><div class="document-form-grid">${documentFieldInput('Name', 'documentBlueprintName', blueprint.name || '')}${documentFieldInput('Description', 'documentBlueprintDescription', blueprint.description || '')}${documentFieldInput('Renderer', 'documentBlueprintRenderer', blueprint.renderer || 'tectonic')}${documentFieldInput('Output format', 'documentBlueprintOutput', blueprint.output_format || 'pdf')}${documentTextarea('Rendering options (JSON)', 'documentBlueprintOptions', JSON.stringify(blueprint.rendering_options || {}, null, 2), 'Renderer-specific options stored with the blueprint.')}</div><div class="document-editor-subsection"><div class="document-composition-head"><div><h3>Field definitions</h3><p class="muted">Fields available to the render template.</p></div><button class="btn" id="documentAddBlueprintField" type="button">+ Add field</button></div><div id="documentBlueprintFields" class="document-blueprint-fields">${documentBlueprintFieldRows(fields)}</div></div><div class="document-editor-subsection"><h3>Linked render template</h3><div class="document-form-grid">${documentFieldInput('Template name', 'documentRenderTemplateName', renderTemplate.name || '')}${documentFieldInput('Template format', 'documentRenderTemplateFormat', renderTemplate.template_format || 'latex_jinja')}${documentFieldInput('Description', 'documentRenderTemplateDescription', renderTemplate.description || '', 'document-form-wide')}${documentTextarea('Template source', 'documentRenderTemplateSource', renderTemplate.source || '', 'Jinja placeholders are resolved before the renderer runs.')}</div></div></section>`;
}
function renderProfileEditor(profile) {
  const settings = profile.settings || {};
  return `<section class="document-editor-card document-authoring-card"><div class="document-editor-title"><div><div class="document-eyebrow">${profile.id ? 'Edit generation profile' : 'New generation profile'}</div><h2>${esc(profile.name || 'Untitled profile')}</h2></div>${documentEditorActions()}</div><div class="document-form-grid">${documentFieldInput('Name', 'documentProfileName', profile.name || '')}${documentFieldInput('Description', 'documentProfileDescription', profile.description || '')}<label class="document-form-field"><span>Document Blueprint</span><select id="documentProfileBlueprint">${documentSelectOptions('blueprints', profile.blueprint_id, 'Select a blueprint...')}</select></label><label class="document-form-field"><span>Content Template</span><select id="documentProfileTemplate">${documentSelectOptions('content_templates', profile.content_template_id, 'Select a content template...')}</select></label>${documentFieldInput('Tone', 'documentProfileTone', settings.tone || profile.tone || '', 'document-form-small')}${documentFieldInput('Audience', 'documentProfileAudience', settings.audience || profile.audience || '', 'document-form-small')}${documentTextarea('Generation instructions', 'documentProfileInstructions', settings.generation_instructions || profile.generation_instructions || profile.instructions || '', 'Profile-level guidance is applied after the content template strategy.')}</div></section>`;
}
function renderDocumentEditor() {
  if (!documentEditor) return '';
  if (documentEditor.view === 'profiles') return renderProfileEditor(documentEditor.item);
  if (documentEditor.view === 'blueprints') return renderBlueprintEditor(documentEditor.item);
  if (documentEditor.view === 'content_templates') return renderContentTemplateEditor(documentEditor.item);
  return renderContentBlockEditor(documentEditor.item);
}
function beginDocumentCreate() {
  if (!DOCUMENT_AUTHORING[documentView]) return;
  const item = documentView === 'profiles' ? { name: '', description: '', blueprint_id: '', content_template_id: '', settings: {} } : documentView === 'blueprints' ? { name: '', description: '', renderer: 'tectonic', output_format: 'pdf', rendering_options: {}, fields: [], render_template: { name: '', description: '', template_format: 'latex_jinja', source: '' } } : documentView === 'content_templates' ? { name: '', description: '', instructions: '', blocks: [] } : { name: '', description: '', content: '', expressions: [] };
  documentEditor = { view: documentView, item, isNew: true, placements: [], expressions: [], blueprintFields: [] };
  renderDocumentWorkspace();
  requestAnimationFrame(() => document.querySelector('.document-authoring-card input')?.focus());
}
function beginDocumentEdit() {
  const item = documentById(DOCUMENT_VIEWS[documentView].key, selectedDocumentId);
  if (!item || !DOCUMENT_AUTHORING[documentView]) return;
  documentEditor = { view: documentView, item: documentClone(item), isNew: false, placements: [], expressions: [], blueprintFields: [] };
  renderDocumentWorkspace();
}
function collectTemplateEditor() {
  const placements = [...document.querySelectorAll('[data-placement-index]')].map((row, index) => ({
    ...(documentEditor.placements?.[Number(row.dataset.placementIndex)] || {}),
    block_id: Number(row.dataset.blockId) || row.dataset.blockId,
    enabled: row.querySelector('[data-placement-enabled]').checked,
    required: row.querySelector('[data-placement-required]').checked,
    max_length: Number(row.querySelector('[data-placement-max]').value) || null,
    sort_order: index
  }));
  documentEditor.placements = placements;
  return {
    ...documentEditor.item,
    name: $('documentTemplateName').value.trim(),
    description: $('documentTemplateDescription').value.trim(),
    instructions: $('documentTemplateInstructions').value,
    blocks: placements.map(({ block, content_block, block_id, content_block_id, ...placement }, index) => ({ ...placement, content_block_id: content_block_id ?? block_id, sort_order: index }))
  };
}
function collectExpressionEditor() {
  const expressions = [...document.querySelectorAll('[data-expression-index]')].map((row, index) => ({
    ...(documentEditor.expressions?.[Number(row.dataset.expressionIndex)] || {}),
    expression_key: row.querySelector('[data-expression-key]').value.trim(),
    name: row.querySelector('[data-expression-name]').value.trim(),
    instructions: row.querySelector('[data-expression-instructions]').value,
    max_length: Number(row.querySelector('[data-expression-max]').value) || null,
    sort_order: index
  }));
  documentEditor.expressions = expressions; return expressions;
}
function collectBlueprintEditor() {
  let renderingOptions;
  try { renderingOptions = JSON.parse($('documentBlueprintOptions').value || '{}') } catch { throw new Error('Rendering options must be valid JSON') }
  const fields = [...document.querySelectorAll('[data-blueprint-field-index]')].map((row, index) => ({
    ...(documentEditor.blueprintFields?.[Number(row.dataset.blueprintFieldIndex)] || {}),
    field_key: row.querySelector('[data-blueprint-field-key]').value.trim(),
    label: row.querySelector('[data-blueprint-field-label]').value.trim(),
    field_type: row.querySelector('[data-blueprint-field-type]').value,
    source_path: row.querySelector('[data-blueprint-field-source]').value.trim(),
    field_scope: row.querySelector('[data-blueprint-field-scope]').value.trim(),
    required: row.querySelector('[data-blueprint-field-required]').checked,
    default_value: row.querySelector('[data-blueprint-field-default]').value,
    sort_order: index
  }));
  documentEditor.blueprintFields = fields;
  return { ...documentEditor.item, name: $('documentBlueprintName').value.trim(), description: $('documentBlueprintDescription').value.trim(), renderer: $('documentBlueprintRenderer').value.trim(), output_format: $('documentBlueprintOutput').value.trim(), rendering_options: renderingOptions, fields, render_template: { ...(documentEditor.renderTemplate || {}), name: $('documentRenderTemplateName').value.trim(), description: $('documentRenderTemplateDescription').value.trim(), template_format: $('documentRenderTemplateFormat').value.trim(), source: $('documentRenderTemplateSource').value } };
}
function collectDocumentEditor() {
  if (documentEditor.view === 'content_templates') return collectTemplateEditor();
  if (documentEditor.view === 'blueprints') return collectBlueprintEditor();
  if (documentEditor.view === 'profiles') {
    return { ...documentEditor.item, name: $('documentProfileName').value.trim(), description: $('documentProfileDescription').value.trim(), blueprint_id: Number($('documentProfileBlueprint').value) || $('documentProfileBlueprint').value, content_template_id: Number($('documentProfileTemplate').value) || $('documentProfileTemplate').value, generation_instructions: $('documentProfileInstructions').value, settings: { ...(documentEditor.item.settings || {}), tone: $('documentProfileTone').value.trim(), audience: $('documentProfileAudience').value.trim(), generation_instructions: $('documentProfileInstructions').value } };
  }
  return { ...documentEditor.item, name: $('documentBlockName').value.trim(), description: $('documentBlockDescription').value.trim(), content: $('documentBlockContent').value, expressions: collectExpressionEditor() };
}
function documentResponseHasState(result, key) {
  const source = result?.documents || result?.state || result;
  return Array.isArray(source?.[key]);
}
async function refreshDocumentStateFromMutation(result, key) {
  const loadVersion = ++documentLoadVersion;
  normalizeDocumentState(result);
  if (!documentResponseHasState(result, key)) {
    const payload = await documentApiGet('/api/documents/state');
    if (loadVersion === documentLoadVersion) normalizeDocumentState(payload);
  }
}
async function saveDocumentEditor() {
  if (!documentEditor) return;
  const definition = DOCUMENT_AUTHORING[documentEditor.view]; let item;
  try { item = collectDocumentEditor() } catch (error) { toast(error.message); return }
  if (!item.name) { toast('A name is required'); return }
  if (documentEditor.view === 'profiles' && (!item.blueprint_id || !item.content_template_id)) { toast('Choose a blueprint and content template'); return }
  if (documentEditor.view === 'content_blocks') {
    const keys = item.expressions.map(expression => String(expression.expression_key || '').trim());
    const invalid = keys.find(key => !/^[A-Za-z_][A-Za-z0-9_]*$/.test(key));
    const duplicate = keys.find((key, index) => keys.indexOf(key) !== index);
    if (invalid !== undefined) { toast(`Expression key "${invalid || '(blank)'}" must start with a letter or underscore and contain only letters, numbers, and underscores`); return }
    if (duplicate) { toast(`Expression key "${duplicate}" is duplicated`); return }
  }
  const button = $('documentEditSave'); button.disabled = true; button.textContent = 'Saving...';
  const beforeIds = new Set((documentState[definition.key] || []).map(documentId));
  try {
    const result = await api(`/api/documents/${definition.endpoint}/save`, { [definition.payload]: item });
    await refreshDocumentStateFromMutation(result, definition.key);
    const items = documentState[definition.key] || [], saved = item.id ? items.find(entry => String(entry.id) === String(item.id)) : items.find(entry => !beforeIds.has(documentId(entry)) && documentName(entry) === item.name) || [...items].reverse().find(entry => documentName(entry) === item.name);
    selectedDocumentId = documentId(saved || items[0]); documentEditor = null; renderDocumentStudio(); toast(`${documentModeLabel(definition.singular)} saved`);
  } catch (error) { button.disabled = false; button.textContent = 'Save'; toast(error.message) }
}
async function duplicateDocumentDefinition() {
  const definition = DOCUMENT_AUTHORING[documentView], item = documentById(definition?.key, selectedDocumentId); if (!definition || !item) return;
  const beforeIds = new Set((documentState[definition.key] || []).map(documentId));
  try { const result = await api(`/api/documents/${definition.endpoint}/duplicate`, { id: item.id }); await refreshDocumentStateFromMutation(result, definition.key); const copy = (documentState[definition.key] || []).find(entry => !beforeIds.has(documentId(entry))); selectedDocumentId = documentId(copy || item); renderDocumentStudio(); toast(`${documentModeLabel(definition.singular)} duplicated`) } catch (error) { toast(error.message) }
}
async function deleteDocumentDefinition() {
  const definition = DOCUMENT_AUTHORING[documentView], item = documentById(definition?.key, selectedDocumentId); if (!definition || !item) return;
  if (!confirm(`Delete ${definition.singular} "${documentName(item)}"?\n\nDefinitions that are in use cannot be deleted.`)) return;
  try { const result = await api(`/api/documents/${definition.endpoint}/delete`, { id: item.id }); await refreshDocumentStateFromMutation(result, definition.key); selectedDocumentId = documentId(documentState[definition.key]?.[0]); documentEditor = null; renderDocumentStudio(); toast(`${documentModeLabel(definition.singular)} deleted`) } catch (error) { toast(error.message) }
}
function updateTemplatePlacementModel() {
  documentEditor.item = collectTemplateEditor(); documentEditor.item.blocks = documentEditor.placements;
}
function moveTemplatePlacement(from, to) {
  updateTemplatePlacementModel(); const placements = documentEditor.placements; if (from < 0 || to < 0 || from >= placements.length || to >= placements.length || from === to) return; const [moved] = placements.splice(from, 1); placements.splice(to, 0, moved); documentEditor.item.blocks = placements; renderDocumentWorkspace();
}
function bindTemplatePlacementEditor() {
  const add = $('documentAddTemplateBlock'); if (add) add.onchange = () => { if (!add.value) return; updateTemplatePlacementModel(); const block = documentById('content_blocks', add.value); const defaults = documentBlockDefaults(block); documentEditor.placements.push({ block_id: Number(add.value) || add.value, block, enabled: defaults.enabled, required: defaults.required, max_length: defaults.max_length, sort_order: documentEditor.placements.length }); documentEditor.item.blocks = documentEditor.placements; renderDocumentWorkspace() };
  document.querySelectorAll('[data-placement-up]').forEach(button => button.onclick = () => moveTemplatePlacement(Number(button.dataset.placementUp), Number(button.dataset.placementUp) - 1));
  document.querySelectorAll('[data-placement-down]').forEach(button => button.onclick = () => moveTemplatePlacement(Number(button.dataset.placementDown), Number(button.dataset.placementDown) + 1));
  document.querySelectorAll('[data-placement-remove]').forEach(button => button.onclick = () => { updateTemplatePlacementModel(); documentEditor.placements.splice(Number(button.dataset.placementRemove), 1); documentEditor.item.blocks = documentEditor.placements; renderDocumentWorkspace() });
  document.querySelectorAll('[data-placement-index]').forEach(row => {
    row.ondragstart = event => { draggedDocumentPlacement = Number(row.dataset.placementIndex); row.classList.add('dragging'); event.dataTransfer.effectAllowed = 'move' };
    row.ondragend = () => { draggedDocumentPlacement = -1; row.classList.remove('dragging'); document.querySelectorAll('.document-placement-editor').forEach(item => item.classList.remove('drag-over')) };
    row.ondragover = event => { event.preventDefault(); row.classList.add('drag-over') };
    row.ondragleave = () => row.classList.remove('drag-over');
    row.ondrop = event => { event.preventDefault(); row.classList.remove('drag-over'); moveTemplatePlacement(draggedDocumentPlacement, Number(row.dataset.placementIndex)) };
  });
}
function updateExpressionModel() { documentEditor.item = collectDocumentEditor(); documentEditor.item.expressions = documentEditor.expressions }
function moveDocumentExpression(from, to) { updateExpressionModel(); const rows = documentEditor.expressions; if (from < 0 || to < 0 || from >= rows.length || to >= rows.length || from === to) return; const [moved] = rows.splice(from, 1); rows.splice(to, 0, moved); documentEditor.item.expressions = rows; renderDocumentWorkspace() }
function bindExpressionEditor() {
  $('documentAddExpression')?.addEventListener('click', () => { updateExpressionModel(); documentEditor.expressions.push({ expression_key: '', name: '', instructions: '', max_length: null, settings: {}, sort_order: documentEditor.expressions.length }); documentEditor.item.expressions = documentEditor.expressions; renderDocumentWorkspace(); requestAnimationFrame(() => document.querySelector('[data-expression-index]:last-child [data-expression-key]')?.focus()) });
  document.querySelectorAll('[data-expression-up]').forEach(button => button.onclick = () => moveDocumentExpression(Number(button.dataset.expressionUp), Number(button.dataset.expressionUp) - 1));
  document.querySelectorAll('[data-expression-down]').forEach(button => button.onclick = () => moveDocumentExpression(Number(button.dataset.expressionDown), Number(button.dataset.expressionDown) + 1));
  document.querySelectorAll('[data-expression-remove]').forEach(button => button.onclick = () => { updateExpressionModel(); documentEditor.expressions.splice(Number(button.dataset.expressionRemove), 1); documentEditor.item.expressions = documentEditor.expressions; renderDocumentWorkspace() });
  document.querySelectorAll('[data-expression-index]').forEach(row => { const handle = row.querySelector('.document-drag-handle'); handle.ondragstart = event => { draggedDocumentExpression = Number(row.dataset.expressionIndex); row.classList.add('dragging'); event.dataTransfer.effectAllowed = 'move' }; handle.ondragend = () => { draggedDocumentExpression = -1; row.classList.remove('dragging') }; row.ondragover = event => { event.preventDefault(); row.classList.add('drag-over') }; row.ondragleave = () => row.classList.remove('drag-over'); row.ondrop = event => { event.preventDefault(); row.classList.remove('drag-over'); moveDocumentExpression(draggedDocumentExpression, Number(row.dataset.expressionIndex)) } });
}
function updateBlueprintFieldModel() { documentEditor.item = collectDocumentEditor(); documentEditor.item.fields = documentEditor.blueprintFields }
function moveBlueprintField(from, to) { updateBlueprintFieldModel(); const rows = documentEditor.blueprintFields; if (from < 0 || to < 0 || from >= rows.length || to >= rows.length || from === to) return; const [moved] = rows.splice(from, 1); rows.splice(to, 0, moved); documentEditor.item.fields = rows; renderDocumentWorkspace() }
function bindBlueprintEditor() {
  $('documentAddBlueprintField')?.addEventListener('click', () => { updateBlueprintFieldModel(); documentEditor.blueprintFields.push({ field_key: '', label: '', field_type: 'text', source_path: '', field_scope: '', required: false, default_value: '', settings: {}, sort_order: documentEditor.blueprintFields.length }); documentEditor.item.fields = documentEditor.blueprintFields; renderDocumentWorkspace(); requestAnimationFrame(() => document.querySelector('[data-blueprint-field-index]:last-child [data-blueprint-field-key]')?.focus()) });
  document.querySelectorAll('[data-blueprint-field-up]').forEach(button => button.onclick = () => moveBlueprintField(Number(button.dataset.blueprintFieldUp), Number(button.dataset.blueprintFieldUp) - 1));
  document.querySelectorAll('[data-blueprint-field-down]').forEach(button => button.onclick = () => moveBlueprintField(Number(button.dataset.blueprintFieldDown), Number(button.dataset.blueprintFieldDown) + 1));
  document.querySelectorAll('[data-blueprint-field-remove]').forEach(button => button.onclick = () => { updateBlueprintFieldModel(); documentEditor.blueprintFields.splice(Number(button.dataset.blueprintFieldRemove), 1); documentEditor.item.fields = documentEditor.blueprintFields; renderDocumentWorkspace() });
}
function draftBlockName(block, index) { return block.name || block.block_name || block.block_snapshot?.name || block.snapshot?.name || `Content block ${index + 1}` }
function draftBlockContent(block) { return block.content ?? block.resolved_content ?? block.rendered_content ?? block.text ?? '' }
function draftBlockMaximum(block) { return block.max_length || block.metadata?.max_length || '' }
function renderDraftDocument(item) {
  const blocks = item.blocks || item.resolved_blocks || item.content_blocks || [], profile = item.profile_snapshot || item.profile || {}, fields = item.resolved_fields || {};
  const blockRows = blocks.map((block, index) => `<article class="document-draft-block" data-draft-index="${index}" data-draft-id="${esc(block.id || '')}" data-placement-id="${esc(block.placement_id || block.template_block_id || '')}" data-block-id="${esc(block.block_id || block.content_block_id || '')}"><div class="document-draft-block-head"><div><button class="document-draft-drag-handle" draggable="true" type="button" title="Drag to reorder" aria-label="Drag ${esc(draftBlockName(block, index))} to reorder">&#8942;&#8942;</button><span data-draft-number>${index + 1}</span><b>${esc(draftBlockName(block, index))}</b></div><div class="document-draft-badges">${block.required ? '<em>Required</em>' : ''}${draftBlockMaximum(block) ? `<em>${esc(draftBlockMaximum(block))} max</em>` : ''}</div></div><textarea data-draft-content ${block.locked ? 'data-locked="true"' : ''}>${esc(draftBlockContent(block))}</textarea><div class="document-draft-controls"><div class="document-draft-order"><button class="btn" type="button" data-draft-up="${index}" ${index === 0 ? 'disabled' : ''} aria-label="Move block up">&#8593;</button><button class="btn" type="button" data-draft-down="${index}" ${index === blocks.length - 1 ? 'disabled' : ''} aria-label="Move block down">&#8595;</button></div><label class="document-check"><input data-draft-enabled type="checkbox" ${block.enabled !== false && block.enabled !== 0 ? 'checked' : ''} ${block.required ? 'disabled title="Required blocks must remain included"' : ''}> Include in document</label><label class="document-check" title="Keep this text unchanged during future block regeneration"><input data-draft-locked type="checkbox" ${block.locked ? 'checked' : ''}> Lock against regeneration</label><span class="document-draft-count" data-draft-count></span></div></article>`).join('');
  return `<section class="document-editor-card document-draft-card"><div class="document-editor-title"><div><div class="document-eyebrow">Draft review</div><h2>${esc(documentName(item, 'Document draft'))}</h2><p class="muted">Review, reorder, include, or lock resolved blocks before creating an immutable PDF.</p></div><span class="document-mode-chip">Draft</span></div><div class="document-stat-grid"><div class="document-stat"><span>Profile</span><b>${esc(documentName(profile, item.profile_name || 'Generation profile'))}</b></div><div class="document-stat"><span>Position</span><b>${esc(fields.position_name || fields.job_title || item.job_title || 'Tracked job')}</b></div><div class="document-stat"><span>Company</span><b>${esc(fields.company || item.company || '—')}</b></div></div><div class="document-draft-blocks">${blockRows || '<div class="document-empty-inline">This draft has no resolved content blocks.</div>'}</div><div class="document-draft-footer"><span class="muted">Saving updates the working draft. Rendering freezes its current order and content as an immutable snapshot.</span><button class="btn" id="documentSaveDraft" type="button">Save Draft</button><button class="btn primary" id="documentRenderDraft" type="button" ${blocks.length ? '' : 'disabled'}>Render PDF</button></div></section>`;
}
function trackerJobDocuments() { return (documentState.generated_documents || []).filter(item => Number(item.job_id || item.generation_context?.job_id || item.job_snapshot?.id || item.job?.id) === Number(trackerDocumentJob?.id)) }
function currentTrackerDocument() { return trackerJobDocuments().find(item => documentId(item) === String(trackerDocumentId)) }
function upsertTrackerDocument(item) { const index = documentState.generated_documents.findIndex(entry => documentId(entry) === documentId(item)); if (index >= 0) documentState.generated_documents[index] = item; else documentState.generated_documents.unshift(item); trackerDocumentId = documentId(item) }
function collectDraftBlocks() {
  return [...document.querySelectorAll('[data-draft-index]')].map((row, index) => ({ id: Number(row.dataset.draftId) || undefined, placement_id: Number(row.dataset.placementId) || undefined, block_id: Number(row.dataset.blockId) || undefined, sort_order: index, content: row.querySelector('[data-draft-content]').value, enabled: row.querySelector('[data-draft-enabled]').checked, locked: row.querySelector('[data-draft-locked]').checked }));
}
function updateDraftCounts() {
  document.querySelectorAll('[data-draft-index]').forEach(row => { const text = row.querySelector('[data-draft-content]').value, counter = row.querySelector('[data-draft-count]'); counter.textContent = `${text.length} characters` });
}
function refreshDraftOrderUi() {
  const rows = [...document.querySelectorAll('[data-draft-index]')];
  rows.forEach((row, index) => {
    row.dataset.draftIndex = index; row.querySelector('[data-draft-number]').textContent = index + 1;
    const up = row.querySelector('[data-draft-up]'), down = row.querySelector('[data-draft-down]'); up.dataset.draftUp = index; up.disabled = index === 0; down.dataset.draftDown = index; down.disabled = index === rows.length - 1;
  });
}
function moveDraftBlock(from, to) {
  const list = document.querySelector('.document-draft-blocks'), rows = [...list.querySelectorAll('[data-draft-index]')];
  if (from < 0 || to < 0 || from >= rows.length || to >= rows.length || from === to) return;
  const [moved] = rows.splice(from, 1); rows.splice(to, 0, moved); list.replaceChildren(...rows); refreshDraftOrderUi(); updateDraftCounts();
}
async function saveDocumentDraft() {
  const item = currentTrackerDocument(); if (!item) return;
  const button = $('documentSaveDraft'); button.disabled = true; button.textContent = 'Saving...';
  try { const result = await api('/api/documents/drafts/save', { document_id: item.id, blocks: collectDraftBlocks() }); const draft = result.draft || result.generated_document || result.document; if (draft) upsertTrackerDocument(draft); else normalizeDocumentState(await documentApiGet('/api/documents/state')); renderTrackerDocumentDialog(); toast('Draft saved') } catch (error) { button.disabled = false; button.textContent = 'Save Draft'; toast(error.message) }
}
async function renderDocumentDraft() {
  const item = currentTrackerDocument(); if (!item) return;
  const renderButton = $('documentRenderDraft'); renderButton.disabled = true; renderButton.textContent = 'Rendering...';
  try { await api('/api/documents/drafts/save', { document_id: item.id, blocks: collectDraftBlocks() }); const result = await api('/api/documents/drafts/render', { document_id: item.id }); const generated = result.generated_document || result.document || (result.id ? result : null); if (generated) upsertTrackerDocument(generated); else normalizeDocumentState(await documentApiGet('/api/documents/state')); renderTrackerDocumentDialog(); toast('PDF rendered') } catch (error) { renderButton.disabled = false; renderButton.textContent = 'Render PDF'; toast(error.message) }
}
function bindDraftWorkspace() {
  $('documentSaveDraft')?.addEventListener('click', saveDocumentDraft); $('documentRenderDraft')?.addEventListener('click', renderDocumentDraft);
  document.querySelectorAll('[data-draft-content]').forEach(textarea => textarea.addEventListener('input', updateDraftCounts));
  document.querySelectorAll('[data-draft-locked]').forEach(input => input.addEventListener('change', () => input.closest('[data-draft-index]').querySelector('[data-draft-content]').toggleAttribute('data-locked', input.checked)));
  document.querySelector('.document-draft-blocks')?.addEventListener('click', event => { const up = event.target.closest('[data-draft-up]'), down = event.target.closest('[data-draft-down]'); if (up) moveDraftBlock(Number(up.dataset.draftUp), Number(up.dataset.draftUp) - 1); if (down) moveDraftBlock(Number(down.dataset.draftDown), Number(down.dataset.draftDown) + 1) });
  document.querySelectorAll('[data-draft-index]').forEach(row => {
    const handle = row.querySelector('.document-draft-drag-handle');
    handle.ondragstart = event => { draggedDraftBlock = Number(row.dataset.draftIndex); row.classList.add('dragging'); event.dataTransfer.effectAllowed = 'move' };
    handle.ondragend = () => { draggedDraftBlock = -1; row.classList.remove('dragging'); document.querySelectorAll('.document-draft-block').forEach(item => item.classList.remove('drag-over')) };
    row.ondragover = event => { event.preventDefault(); row.classList.add('drag-over') };
    row.ondragleave = event => { if (!row.contains(event.relatedTarget)) row.classList.remove('drag-over') };
    row.ondrop = event => { event.preventDefault(); row.classList.remove('drag-over'); moveDraftBlock(draggedDraftBlock, Number(row.dataset.draftIndex)) };
  });
  refreshDraftOrderUi(); updateDraftCounts();
}
function bindDocumentAuthoringWorkspace() {
  $('documentEdit')?.addEventListener('click', beginDocumentEdit); $('documentDuplicate')?.addEventListener('click', duplicateDocumentDefinition); $('documentDelete')?.addEventListener('click', deleteDocumentDefinition);
  $('documentEditSave')?.addEventListener('click', saveDocumentEditor); $('documentEditCancel')?.addEventListener('click', () => { documentEditor = null; renderDocumentStudio() });
  if (documentEditor?.view === 'content_templates') bindTemplatePlacementEditor();
  if (documentEditor?.view === 'content_blocks') bindExpressionEditor();
  if (documentEditor?.view === 'blueprints') bindBlueprintEditor();
}

// Replace the original read-only views with authoring-aware variants.
function renderContentTemplate(template) {
  return `<section class="document-editor-card"><div class="document-editor-title"><div><div class="document-eyebrow">Content Template</div><h2>${esc(documentName(template))}</h2></div>${documentReadActions()}</div><p class="document-copy">${esc(template.description || 'An ordered, reusable content strategy.')}</p><h3>Overall strategy</h3><p class="document-copy">${esc(template.instructions || template.generation_instructions || 'No global generation instructions have been added.')}</p><h3>Ordered composition</h3>${documentPlacementRows(template)}</section>`;
}
function renderContentBlock(block) {
  const expressions = block.expressions || [];
  return `<section class="document-editor-card"><div class="document-editor-title"><div><div class="document-eyebrow">Content block</div><h2>${esc(documentName(block))}</h2></div>${documentReadActions()}</div><p class="document-copy">${esc(block.description || '')}</p><h3>Content</h3><p class="document-copy">${esc(block.content || 'No reusable content has been added.')}</p><h3>Generation expressions</h3>${expressions.length ? `<div class="document-definition-list">${expressions.map(expression => `<div><div><b>${esc(expression.name || expression.expression_key)}</b><small><code>{{ ${esc(expression.expression_key)} }}</code>${expression.instructions ? ` · ${esc(expression.instructions)}` : ''}</small></div><span>${expression.max_length ? `${esc(expression.max_length)} max` : 'No limit'}</span></div>`).join('')}</div>` : '<div class="document-empty-inline">No generation expressions.</div>'}</section>`;
}
function renderGenerationProfile(profile) {
  const blueprint = profile.blueprint || documentById('blueprints', profile.blueprint_id), template = profile.content_template || documentById('content_templates', profile.content_template_id), settings = profile.settings || {}, profileInstructions = profile.generation_instructions || profile.instructions || settings.generation_instructions || settings.instructions;
  return `<div class="document-profile-hero"><div><div class="document-editor-title"><div><div class="document-eyebrow">Selectable recipe</div><h2>${esc(documentName(profile))}</h2></div>${documentReadActions()}</div><p>${esc(profile.description || 'This profile combines a document blueprint with a reusable content strategy.')}</p>${settings.tone || settings.audience ? `<div class="document-profile-tags">${settings.tone ? `<span>Tone: ${esc(settings.tone)}</span>` : ''}${settings.audience ? `<span>Audience: ${esc(settings.audience)}</span>` : ''}</div>` : ''}</div><div class="document-recipe-map"><div><span>Blueprint</span><b>${esc(documentName(blueprint, 'Not selected'))}</b></div><span>+</span><div><span>Content template</span><b>${esc(documentName(template, 'Not selected'))}</b></div></div></div><div class="document-detail-grid"><section><h3>Generation instructions</h3><p class="document-copy">${esc(profileInstructions || template?.instructions || 'Use the selected template strategy and only evidence supported by the user data.')}</p></section><section><h3>Output</h3><div class="document-stat"><span>Renderer</span><b>${esc(documentModeLabel(blueprint?.renderer || 'Tectonic'))}</b></div><div class="document-stat"><span>Format</span><b>${esc(String(blueprint?.output_format || 'PDF').toUpperCase())}</b></div></section></div>`;
}
function renderTrackerGeneratedDocument(item) {
  if (String(item.status || '').toLocaleLowerCase() === 'draft') return renderDraftDocument(item);
  showTrackerGeneratedPreview(item); const profile = item.profile_snapshot || item.profile || {}, job = item.job_snapshot || item.job || {}, fields = item.resolved_fields || {};
  return `<section class="document-editor-card"><div class="document-editor-title"><div><div class="document-eyebrow">Generated document</div><h2>${esc(documentName(item, documentName(profile, 'Generated document')))}</h2><p class="muted">${esc(documentDate(item.created_at || item.generated_at))}</p></div><a class="btn primary" href="${esc(generatedPdfUrl(item))}" download>Download PDF</a></div><div class="document-stat-grid"><div class="document-stat"><span>Profile</span><b>${esc(documentName(profile, item.profile_name || 'Snapshot preserved'))}</b></div><div class="document-stat"><span>Job</span><b>${esc(documentName(job, fields.position_name || fields.job_title || item.job_title || 'No linked job'))}</b></div><div class="document-stat"><span>Company</span><b>${esc(job.company || fields.company || item.company || '—')}</b></div><div class="document-stat"><span>Status</span><b>${esc(documentModeLabel(item.status || 'generated'))}</b></div></div>${item.error ? `<div class="document-render-error"><b>Render error</b>${esc(item.error)}</div>` : ''}</section>`;
}
function bindDocumentWorkspace() {
  bindDocumentAuthoringWorkspace();
}
function renderDocumentWorkspace() {
  const meta = DOCUMENT_VIEWS[documentView], item = documentById(meta.key, selectedDocumentId);
  $('documentWorkspaceEyebrow').textContent = meta.eyebrow; $('documentWorkspaceTitle').textContent = meta.title; $('documentWorkspaceHint').textContent = meta.hint;
  if (documentEditor) { $('documentWorkspace').innerHTML = renderDocumentEditor(); bindDocumentWorkspace(); return }
  if (!item) { $('documentWorkspace').innerHTML = `<div class="empty">${esc(meta.empty)}${documentView === 'profiles' ? '<br><br>Use Starter recipe or create a profile.' : ''}</div>`; return }
  $('documentWorkspace').innerHTML = documentView === 'profiles' ? renderGenerationProfile(item) : documentView === 'blueprints' ? renderBlueprint(item) : documentView === 'content_templates' ? renderContentTemplate(item) : renderContentBlock(item); bindDocumentWorkspace();
}
function referenceRows(values, fallback) {
  const rows = Array.isArray(values) ? values : values && typeof values === 'object' ? Object.entries(values).map(([key, value]) => typeof value === 'object' ? { key, ...value } : { key, description: value }) : [];
  return rows.length ? rows.map(value => { const key = typeof value === 'string' ? value : value.key || value.name || value.path || value.reference || value.placeholder || '', description = typeof value === 'string' ? '' : value.description || value.label || value.type || ''; return `<div class="document-reference-row"><code>${esc(key)}</code>${description ? `<span>${esc(description)}</span>` : ''}</div>` }).join('') : `<div class="document-empty-inline">${esc(fallback)}</div>`;
}
function renderDocumentReference() {
  const reference = documentState.expression_reference || {}, placeholders = reference.output_placeholders || reference.placeholders || [], variables = reference.template_variables || reference.variables || ['candidate_name', 'company', 'position_name', 'date', 'paragraphs'], contexts = reference.context_references || reference.generation_references || reference.context || ['job.company', 'job.title', 'job.description', 'user.work_history', 'capabilities.match_selection'];
  const hasPlaceholders = Array.isArray(placeholders) ? placeholders.length : placeholders && typeof placeholders === 'object' && Object.keys(placeholders).length;
  $('documentReference').innerHTML = `${hasPlaceholders ? `<section class="document-reference-section"><h3>Output placeholders</h3><p>Resolved values available to block content and render templates.</p>${referenceRows(placeholders, 'No output placeholders advertised by the server.')}</section>` : ''}<section class="document-reference-section"><h3>Template variables</h3><p>Use Jinja placeholders in block content and render templates.</p>${referenceRows(variables, 'No variables advertised by the server.')}</section><section class="document-reference-section"><h3>Generation context</h3><p>Expressions may reference these evidence sources in their instructions.</p>${referenceRows(contexts, 'No context references advertised by the server.')}</section><section class="document-reference-example"><span>Example</span><code>Dear {{ company }},</code><code>{{ strongest_match }}</code></section>`;
}
function renderDocumentStudio() {
  document.querySelectorAll('[data-document-view]').forEach(button => button.classList.toggle('active', button.dataset.documentView === documentView));
  const authoring = DOCUMENT_AUTHORING[documentView]; $('documentCreate').hidden = !authoring; if (authoring) $('documentCreate').textContent = `+ New ${authoring.singular}`;
  renderDocumentList(); renderDocumentWorkspace(); renderDocumentReference();
}
function renderTrackerDocumentHistory() {
  const items = trackerJobDocuments(); $('trackerDocumentHistoryCount').textContent = String(items.length); $('trackerDocumentHistory').innerHTML = items.map(item => `<button class="document-list-item ${documentId(item) === String(trackerDocumentId) ? 'active' : ''}" type="button" data-tracker-document-id="${esc(documentId(item))}"><b>${esc(documentName(item, 'Job document'))}</b><span>${String(item.status || '').toLocaleLowerCase() === 'draft' ? 'Draft' : 'PDF'} · ${esc(documentDate(item.updated_at || item.created_at))}</span></button>`).join('') || '<div class="document-list-empty">No documents generated for this job.</div>';
  document.querySelectorAll('[data-tracker-document-id]').forEach(button => button.onclick = () => { trackerDocumentId = button.dataset.trackerDocumentId; renderTrackerDocumentDialog() });
}
function renderTrackerDocumentDialog() {
  if (!trackerDocumentJob) return; const profiles = documentState.generation_profiles || [], current = currentTrackerDocument();
  $('trackerDocumentTitle').textContent = trackerDocumentJob.title || 'Generate Document'; $('trackerDocumentSubtitle').textContent = trackerDocumentJob.company || 'Unknown company';
  $('trackerDocumentProfile').innerHTML = profiles.length ? profiles.map(profile => `<option value="${esc(profile.id)}" ${String(profile.id) === String(trackerDocumentProfileId) ? 'selected' : ''}>${esc(documentName(profile))}</option>`).join('') : '<option value="">Create a profile in Document Studio first</option>';
  $('trackerDocumentPrepare').disabled = documentGenerating || !profiles.length; $('trackerDocumentPrepare').textContent = documentGenerating ? 'Preparing...' : 'Prepare Draft';
  clearTrackerGeneratedPreview(); renderTrackerDocumentHistory();
  if (!current) $('trackerDocumentWorkspace').innerHTML = `<div class="tracker-document-start"><div class="document-eyebrow">Job-scoped workflow</div><h2>Prepare a document draft</h2><p>Select a Generation Profile, then review its resolved blocks before rendering. Only documents for this job appear here.</p></div>`;
  else $('trackerDocumentWorkspace').innerHTML = renderTrackerGeneratedDocument(current);
  if (current && String(current.status || '').toLocaleLowerCase() === 'draft') bindDraftWorkspace();
}
async function prepareTrackerDocument() {
  const profileId = Number($('trackerDocumentProfile').value); if (!trackerDocumentJob || !profileId || documentGenerating) return; documentGenerating = true; renderTrackerDocumentDialog();
  try {
    const result = await api('/api/documents/drafts/prepare', { job_id: trackerDocumentJob.id, profile_id: profileId }); const draft = result.draft || result.generated_document || result.document; if (draft) upsertTrackerDocument(draft); else { normalizeDocumentState(await documentApiGet('/api/documents/state')); trackerDocumentId = documentId(trackerJobDocuments().find(item => String(item.status || '').toLocaleLowerCase() === 'draft') || trackerJobDocuments()[0]) } toast('Draft prepared');
  } catch (error) { toast(error.message) } finally { documentGenerating = false; renderTrackerDocumentDialog() }
}
async function openTrackerDocuments(id) { trackerDocumentJob = trackerCurrentJob && Number(trackerCurrentJob.id) === Number(id) ? trackerCurrentJob : await documentApiGet(`/api/jobs/${id}`); normalizeDocumentState(await documentApiGet('/api/documents/state')); trackerDocumentProfileId = String(documentState.generation_profiles?.[0]?.id || ''); trackerDocumentId = documentId(trackerJobDocuments()[0]); renderTrackerDocumentDialog(); if (!$('trackerDocumentDialog').open) $('trackerDocumentDialog').showModal() }
$('documentSearch').oninput = renderDocumentList;
$('documentSeed').onclick = seedDocuments;
$('documentCreate').onclick = beginDocumentCreate;
document.querySelectorAll('[data-document-view]').forEach(button => button.onclick = () => { documentView = button.dataset.documentView; selectedDocumentId = documentId(documentItems()[0]); documentEditor = null; renderDocumentStudio() });
$('trackerDocumentClose').onclick = () => $('trackerDocumentDialog').close();
$('trackerDocumentProfile').onchange = event => { trackerDocumentProfileId = event.target.value };
$('trackerDocumentPrepare').onclick = prepareTrackerDocument;

let timer; $('search').oninput = () => { clearTimeout(timer); timer = setTimeout(loadJobs, 180) }; $('sort').onchange = loadJobs; $('status').onchange = loadJobs;
async function loadUserData() { userData = await fetch('/api/user-data', { cache: 'no-store' }).then(r => { if (!r.ok) throw new Error(`User data request failed (${r.status})`); return r.json() }); renderUserSelector(); renderUser(); renderWork(); renderAnswers(); $('keyboardLayout').value = userData.keyboard_layout || 'qwerty' }
async function reloadActiveUserScopedPage() {
  if ($('capabilitiesPage').classList.contains('active')) {
    capabilitySetId = '__all__';
    capabilitySetSelection = null;
    await loadCapabilities();
  }
  if ($('documentsPage').classList.contains('active')) {
    await loadDocuments({ keepSelection: false });
  }
}
queueMicrotask(() => loadUserData().catch(error => { console.error(error); $('userSelector').innerHTML = '<option>User data unavailable</option>'; toast(error.message) }));
async function syncActiveUser() {
  try {
    const current = await fetch('/api/user-data', { cache: 'no-store' }).then(response => response.json());
    if (current.active_user_id && current.active_user_id !== userData.active_user_id) {
      userData = current; renderUserSelector(); renderUser(); renderWork(); renderAnswers(); $('keyboardLayout').value = userData.keyboard_layout || 'qwerty'; await reloadActiveUserScopedPage(); toast(`Switched to ${userData.active_user_name}`);
    }
  } catch (error) { console.error(error) }
}
setInterval(syncActiveUser, 750);
window.addEventListener('focus', syncActiveUser);
function renderUserSelector() { $('userSelector').innerHTML = userData.users.map(u => `<option value="${u.id}" ${u.id === userData.active_user_id ? 'selected' : ''}>${esc(u.name)}</option>`).join('') }
$('userSelector').onchange = async () => { await api('/api/users/switch', { id: Number($('userSelector').value) }); await loadUserData(); await reloadActiveUserScopedPage(); toast(`Switched to ${userData.active_user_name}`) }; $('newUserButton').onclick = async () => { const name = prompt('New user name'); if (!name) return; const clone = confirm('Copy the current user data into the new user?\n\nOK = copy current user\nCancel = start empty'); await api('/api/users/create', { name, clone }); await loadUserData() };
$('dataMenuButton').onclick = e => { e.stopPropagation(); $('dataMenu').classList.toggle('open') }; document.addEventListener('click', () => $('dataMenu').classList.remove('open')); $('exportData').onclick = () => location.href = '/api/user-data/export'; $('downloadTemplate').onclick = () => location.href = '/api/user-data/template'; $('importData').onclick = () => { $('dataMenu').classList.remove('open'); $('importDialog').showModal() }; $('cancelImport').onclick = () => $('importDialog').close(); $('chooseImport').onclick = () => $('importFile').click(); $('importFile').onchange = async () => { const file = $('importFile').files[0]; if (!file) return; try { const data = JSON.parse(await file.text()), mode = document.querySelector('input[name="importMode"]:checked').value; await api('/api/user-data/import', { data, mode }); $('importDialog').close(); $('importFile').value = ''; await loadUserData(); toast('Import complete') } catch (error) { toast(error.message) } };
const deleteUserButton = document.createElement('button'); deleteUserButton.className = 'btn danger'; deleteUserButton.textContent = 'Delete current user'; $('dataMenu').appendChild(deleteUserButton); deleteUserButton.onclick = async () => { if (confirm(`Delete user ${userData.active_user_name}? This cannot be undone unless you exported it.`)) { await api('/api/users/delete', { id: userData.active_user_id }); await loadUserData(); toast('User deleted') } };
const dialogTemplate = document.createElement('button'); dialogTemplate.className = 'btn'; dialogTemplate.textContent = 'Download template'; dialogTemplate.onclick = () => location.href = '/api/user-data/template'; $('chooseImport').before(dialogTemplate);
$('keyboardLayout').onchange = async () => { await api('/api/user/keyboard-layout', { layout: $('keyboardLayout').value }); toast('Keyboard layout saved') };
const userFieldLabels = { first_name: 'First name', last_name: 'Last name', email: 'Email', phone_number: 'Phone number', street_address: 'Street address', city: 'City', state: 'State', zip_code: 'ZIP code', country: 'Country', linkedin: 'LinkedIn', github: 'GitHub', portfolio: 'Portfolio', facebook: 'Facebook', x: 'X' };
function renderUser() { $('userFields').innerHTML = Object.entries(userFieldLabels).map(([name, label]) => `<div class="field ${['street_address', 'linkedin', 'portfolio'].includes(name) ? 'wide' : ''}"><label for="user_${name}">${label}</label><input id="user_${name}" data-user-field="${name}" value="${esc(userData.user?.[name] || '')}"></div>`).join(''); renderCustomFields(); renderCustomActions() }
$('saveUser').addEventListener('click', async () => { const button = $('saveUser'), values = {}; document.querySelectorAll('[data-user-field]').forEach(input => values[input.dataset.userField] = input.value); button.disabled = true; button.textContent = 'Saving…'; try { await api('/api/user/save', values); await loadUserData(); toast('User data saved') } catch (error) { console.error(error); toast(error.message) } finally { button.disabled = false; button.textContent = 'Save user data' } });
function renderCustomFields() { $('customFields').innerHTML = (userData.custom_fields || []).map((field, i) => `<div class="editor-entry" data-custom-index="${i}" data-custom-id="${esc(field.id || '')}"><div class="entry-head"><h3>${esc(field.label || 'New Custom Data')}</h3><button class="btn danger" data-remove-custom="${i}">Delete</button></div><div class="form-grid"><div class="field"><label>Unique label</label><input data-custom-label value="${esc(field.label)}"></div><div class="field"><label>Value type</label><select data-custom-type><option value="single" ${(field.type || 'single') === 'single' ? 'selected' : ''}>Single line</option><option value="multi" ${field.type === 'multi' ? 'selected' : ''}>Multi-line</option></select></div><div class="field wide"><label>Value</label>${field.type === 'multi' ? `<textarea data-custom-value>${esc(field.value)}</textarea>` : `<input data-custom-value value="${esc(field.value)}">`}</div></div></div>`).join(''); document.querySelectorAll('[data-remove-custom]').forEach(b => b.onclick = () => { userData.custom_fields.splice(Number(b.dataset.removeCustom), 1); renderCustomFields() }); document.querySelectorAll('[data-custom-type]').forEach(select => select.onchange = () => { const index = Number(select.closest('[data-custom-index]').dataset.customIndex); collectCustomFields(); userData.custom_fields[index].type = select.value; renderCustomFields() }) }
function collectCustomFields() { userData.custom_fields = [...document.querySelectorAll('[data-custom-index]')].map(row => ({ id: row.dataset.customId, label: row.querySelector('[data-custom-label]').value, value: row.querySelector('[data-custom-value]').value, type: row.querySelector('[data-custom-type]').value })) }
function renderCustomActions() { const fields = userData.custom_fields || []; $('customActions').innerHTML = (userData.custom_actions || []).map((action, i) => { const selected = action.field_ids || [], available = fields.filter(field => !selected.includes(field.id)); return `<div class="editor-entry" data-action-index="${i}" data-action-id="${esc(action.id || '')}"><div class="entry-head"><h3>${esc(action.label || 'New Custom Action')}</h3><button class="btn danger" data-remove-action="${i}">Delete</button></div><div class="form-grid"><div class="field"><label>Unique action label</label><input data-action-label value="${esc(action.label)}"></div><div class="field"><label>Action type</label><select data-action-type><option value="single" ${action.type === 'single' ? 'selected' : ''}>Single paste</option><option value="iterator" ${action.type === 'iterator' ? 'selected' : ''}>Iterator</option></select></div><div class="field"><label>Paste behavior</label><label class="check"><input data-action-auto-return type="checkbox" ${action.auto_return ? 'checked' : ''}> Auto Return</label></div></div><div class="custom-action-values"><label class="muted">Paste values in this order</label>${selected.map((id, index) => { const field = fields.find(item => item.id === id); return field ? `<div class="custom-action-value" data-value-index="${index}"><span>${esc(field.label)}</span><button class="btn" data-value-up="${index}" ${index === 0 ? 'disabled' : ''}>↑</button><button class="btn" data-value-down="${index}" ${index === selected.length - 1 ? 'disabled' : ''}>↓</button><button class="btn danger" data-value-remove="${index}">Remove</button></div>` : '' }).join('')}<div class="custom-action-add"><select data-add-action-field><option value="">Add Custom Data…</option>${available.map(field => `<option value="${esc(field.id)}">${esc(field.label)}</option>`).join('')}</select></div></div></div>` }).join(''); bindCustomActions() }
function collectCustomActions() { document.querySelectorAll('[data-action-index]').forEach(row => { const action = userData.custom_actions[Number(row.dataset.actionIndex)]; action.label = row.querySelector('[data-action-label]').value; action.type = row.querySelector('[data-action-type]').value; if (action.type === 'single') action.field_ids = (action.field_ids || []).slice(0, 1); const autoReturn = row.querySelector('[data-action-auto-return]'); action.auto_return = Boolean(autoReturn?.checked) }) }
function validateVisibleLabels(selector) {
  const inputs = [...document.querySelectorAll(selector)], counts = new Map();
  for (const input of inputs) { const label = input.value.trim().toLocaleLowerCase(); if (label) counts.set(label, (counts.get(label) || 0) + 1) }
  let valid = true;
  for (const input of inputs) {
    const duplicate = input.value.trim() && counts.get(input.value.trim().toLocaleLowerCase()) > 1;
    input.classList.toggle('label-invalid', Boolean(duplicate));
    input.setAttribute('aria-invalid', String(Boolean(duplicate)));
    let error = input.parentElement.querySelector('.label-error');
    if (duplicate && !error) { error = document.createElement('div'); error.className = 'label-error'; input.after(error) }
    if (error) { error.textContent = duplicate ? 'Label is already in use.' : ''; error.hidden = !duplicate }
    if (duplicate) valid = false;
  }
  return valid;
}
function bindCustomActions() {
  document.querySelectorAll('[data-action-index]').forEach(row => {
    const index = Number(row.dataset.actionIndex), action = userData.custom_actions[index];
    row.querySelector('[data-action-type]').onchange = e => {
      collectCustomActions(); action.type = e.target.value;
      if (action.type === 'single') action.field_ids = (action.field_ids || []).slice(0, 1);
      renderCustomActions();
    };
    row.querySelector('[data-add-action-field]').onchange = e => {
      if (!e.target.value) return;
      collectCustomActions(); action.field_ids ??= [];
      if (action.type === 'single') action.field_ids = [e.target.value];
      else if (!action.field_ids.includes(e.target.value)) action.field_ids.push(e.target.value);
      renderCustomActions();
    };
    row.querySelectorAll('[data-value-up]').forEach(b => b.onclick = () => {
      collectCustomActions(); const n = Number(b.dataset.valueUp);
      [action.field_ids[n - 1], action.field_ids[n]] = [action.field_ids[n], action.field_ids[n - 1]];
      renderCustomActions();
    });
    row.querySelectorAll('[data-value-down]').forEach(b => b.onclick = () => {
      collectCustomActions(); const n = Number(b.dataset.valueDown);
      [action.field_ids[n + 1], action.field_ids[n]] = [action.field_ids[n], action.field_ids[n + 1]];
      renderCustomActions();
    });
    row.querySelectorAll('[data-value-remove]').forEach(b => b.onclick = () => {
      collectCustomActions(); action.field_ids.splice(Number(b.dataset.valueRemove), 1);
      renderCustomActions();
    });
  });
  document.querySelectorAll('[data-remove-action]').forEach(b => b.onclick = () => {
    collectCustomActions(); userData.custom_actions.splice(Number(b.dataset.removeAction), 1);
    renderCustomActions();
  });
}
function showUserView(name) { ['userFormView', 'workView', 'customDataView', 'customActionsView', 'qaView'].forEach(id => $(id).style.display = 'none'); document.querySelectorAll('.top-tabs .tab').forEach(tab => tab.classList.remove('active')); if (name === 'user') { $('userFormView').style.display = 'block'; $('userTab').classList.add('active') } if (name === 'work') { $('workView').style.display = 'block'; $('workTab').classList.add('active') } if (name === 'custom-data') { $('customDataView').style.display = 'block'; $('customDataTab').classList.add('active'); renderCustomFields() } if (name === 'custom-actions') { $('customActionsView').style.display = 'block'; $('customActionsTab').classList.add('active'); renderCustomActions() } if (name === 'qa') { $('qaView').style.display = 'block'; $('qaTab').classList.add('active') } renderTips() }
$('userTab').onclick = () => showUserView('user');
$('workTab').onclick = () => showUserView('work');
$('customDataTab').onclick = () => showUserView('custom-data');
$('customActionsTab').onclick = () => showUserView('custom-actions');
$('qaTab').onclick = () => showUserView('qa');
$('addCustomField').addEventListener('click', async () => {
  collectCustomFields(); userData.custom_fields ??= [];
  userData.custom_fields.push({ id: `custom_${crypto.randomUUID().replaceAll('-', '')}`, label: '', value: '', type: 'single' });
  const fields = structuredClone(userData.custom_fields);
  renderCustomFields();
  const inputs = document.querySelectorAll('[data-custom-label]');
  requestAnimationFrame(() => { const input = inputs[inputs.length - 1]; if (input) { input.placeholder = 'Data label'; input.focus() } });
  if (!validateVisibleLabels('[data-custom-label]')) return;
  try { await api('/api/user/custom-fields', { fields }); toast('Custom Data saved') } catch (error) { toast(error.message) }
});
$('addCustomAction').addEventListener('click', async () => {
  collectCustomActions(); userData.custom_actions ??= [];
  userData.custom_actions.push({ id: `custom_action_${crypto.randomUUID().replaceAll('-', '')}`, label: '', type: 'single', field_ids: [], auto_return: false });
  const actions = structuredClone(userData.custom_actions);
  renderCustomActions();
  const inputs = document.querySelectorAll('[data-action-label]');
  requestAnimationFrame(() => { const input = inputs[inputs.length - 1]; if (input) { input.placeholder = 'Action label'; input.focus() } });
  if (!validateVisibleLabels('[data-action-label]')) return;
  try { await api('/api/user/custom-actions', { actions }); toast('Custom Actions saved') } catch (error) { toast(error.message) }
});
$('customFields').addEventListener('click', event => {
  if (!event.target.closest('[data-remove-custom]')) return;
  setTimeout(async () => {
    const fields = structuredClone(userData.custom_fields || []);
    try { await api('/api/user/custom-fields', { fields }); toast('Custom Data deleted') } catch (error) { toast(error.message) }
  });
});
$('customActions').addEventListener('click', event => {
  if (!event.target.closest('[data-remove-action]')) return;
  setTimeout(async () => {
    const actions = structuredClone(userData.custom_actions || []);
    try { await api('/api/user/custom-actions', { actions }); toast('Custom Action deleted') } catch (error) { toast(error.message) }
  });
});
let customDataInputSaveTimer = null;
function saveCustomDataInputSoon() {
  clearTimeout(customDataInputSaveTimer);
  collectCustomFields();
  if (!validateVisibleLabels('[data-custom-label]')) return;
  const fields = structuredClone(userData.custom_fields || []);
  customDataInputSaveTimer = setTimeout(async () => {
    try { await api('/api/user/custom-fields', { fields }); toast('Custom Data saved') } catch (error) { toast(error.message) }
  }, 350);
}
$('customFields').addEventListener('input', saveCustomDataInputSoon);
$('customFields').addEventListener('change', saveCustomDataInputSoon);
let customActionInputSaveTimer = null;
function saveCustomActionInputSoon() {
  clearTimeout(customActionInputSaveTimer);
  collectCustomActions();
  if (!validateVisibleLabels('[data-action-label]')) return;
  const actions = structuredClone(userData.custom_actions || []);
  customActionInputSaveTimer = setTimeout(async () => {
    try { await api('/api/user/custom-actions', { actions }); toast('Custom Actions saved') } catch (error) { toast(error.message) }
  }, 350);
}
$('customActions').addEventListener('input', saveCustomActionInputSoon);
$('customActions').addEventListener('change', saveCustomActionInputSoon);
$('customActions').addEventListener('click', event => {
  if (!event.target.closest('[data-value-up],[data-value-down],[data-value-remove]')) return;
  setTimeout(saveCustomActionInputSoon);
});
let workSaveTimer = null; function saveWorkSoon() { clearTimeout(workSaveTimer); workSaveTimer = setTimeout(async () => { await api('/api/user/work-history', { entries: userData.work_history || [] }); toast('Work experience saved') }, 350) }
function renderWork(openIndex = -1) { $('workEntries').innerHTML = (userData.work_history || []).map((entry, i) => `<details class="editor-entry work-entry" data-work-index="${i}" ${i === openIndex ? 'open' : ''}><summary><span class="work-entry-title">${esc(entry.title || entry.company || 'Work experience')}</span><span class="work-drag-handle" draggable="true" data-work-drag="${i}" title="Drag to reorder">⋮⋮</span><button class="btn danger" data-remove-work="${i}">Delete</button></summary><div class="work-entry-body"><div class="form-grid"><div class="field"><label>Title</label><input data-work="title" value="${esc(entry.title)}"></div><div class="field"><label>Company</label><input data-work="company" value="${esc(entry.company)}"></div><div class="field"><label>Start</label><input data-work="start" value="${esc(entry.start)}"></div><div class="field"><label>End</label><input data-work="end" value="${esc(entry.end)}"></div></div><label class="muted">Highlights</label><textarea data-work="highlights">${esc(entry.highlights)}</textarea></div></details>`).join(''); document.querySelectorAll('[data-work]').forEach(input => input.oninput = () => { const row = Number(input.closest('[data-work-index]').dataset.workIndex); userData.work_history[row][input.dataset.work] = input.value; const title = input.closest('.work-entry').querySelector('.work-entry-title'); title.textContent = userData.work_history[row].title || userData.work_history[row].company || 'Work experience'; saveWorkSoon() }); document.querySelectorAll('[data-remove-work]').forEach(button => button.onclick = event => { event.preventDefault(); event.stopPropagation(); userData.work_history.splice(Number(button.dataset.removeWork), 1); renderWork(); saveWorkSoon() }); document.querySelectorAll('[data-work-drag]').forEach(handle => handle.ondragstart = event => { event.stopPropagation(); event.dataTransfer.effectAllowed = 'move'; event.dataTransfer.setData('text/x-jaw-work-index', handle.dataset.workDrag) }); document.querySelectorAll('.work-entry').forEach(entry => { entry.ondragover = event => { if (event.dataTransfer.types.includes('text/x-jaw-work-index')) { event.preventDefault(); entry.classList.add('drag-over') } }; entry.ondragleave = () => entry.classList.remove('drag-over'); entry.ondrop = event => { event.preventDefault(); entry.classList.remove('drag-over'); const from = Number(event.dataTransfer.getData('text/x-jaw-work-index')), to = Number(entry.dataset.workIndex); if (!Number.isInteger(from) || from === to) return; const [moved] = userData.work_history.splice(from, 1); userData.work_history.splice(to, 0, moved); renderWork(to); saveWorkSoon() } }) } $('addWork').onclick = () => { userData.work_history ??= []; userData.work_history.unshift({ title: '', company: '', start: '', end: '', highlights: '' }); renderWork(0); document.querySelector('[data-work="title"]').focus(); saveWorkSoon() };
function renderAnswers() { $('answerEntries').innerHTML = (userData.answers || []).map((entry, i) => `<div class="editor-entry" data-answer-index="${i}"><div class="entry-head"><h3>Question & Answer</h3><button class="btn danger" data-remove-answer="${i}">Delete</button></div><div class="field"><label>Question / title</label><input data-answer-title value="${esc(entry.title)}"></div><div class="field"><label>Answer</label><textarea data-answer-text>${esc(entry.answer)}</textarea></div></div>`).join(''); document.querySelectorAll('[data-remove-answer]').forEach(b => b.onclick = () => { userData.answers.splice(Number(b.dataset.removeAnswer), 1); renderAnswers() }) } $('addAnswer').onclick = () => { userData.answers ??= []; userData.answers.unshift({ title: '', answer: '' }); renderAnswers(); document.querySelector('[data-answer-title]').focus() }; $('saveAnswers').onclick = async () => { const answers = [...document.querySelectorAll('[data-answer-index]')].map(row => ({ title: row.querySelector('[data-answer-title]').value, answer: row.querySelector('[data-answer-text]').value })); await api('/api/user/answers', { answers }); toast('Q&A saved'); loadUserData() };
const builtinLayouts = {
  'colemak-dh': [['1', '2', '3', '4', '5'], ['Q', 'W', 'F', 'P', 'B'], ['A', 'R', 'S', 'T', 'G'], ['Z', 'X', 'C', 'D', 'V']],
  qwerty: [['1', '2', '3', '4', '5'], ['Q', 'W', 'E', 'R', 'T'], ['A', 'S', 'D', 'F', 'G'], ['Z', 'X', 'C', 'V', 'B']]
};
let keybindData = null, keyLayer = 'base', selectedAction = '', selectedCellKey = '', hoveredKeyCell = null, keyLayouts = {}, keybindMode = '', deleteBindMode = false, deleteAssignmentMode = false, hideAssignedActions = false, customActionsOnly = false, hideSinglePasteActions = localStorage.getItem('jaw_hide_single_paste_actions') === 'on', listeningHotkey = null;
function inferredIcons(action, display) { if (display.icons?.length) return display.icons.slice(0, 2); if (!display.svg) return []; const name = action.toLowerCase(); if (name.includes('brief')) return ['brief']; if (name.includes('cycle')) return ['cycle']; if (name.includes('linkedin')) return ['paste', 'linkedin']; if (name.includes('github')) return ['paste', 'github']; if (name.includes('portfolio')) return ['paste', 'portfolio']; if (name.includes('facebook')) return ['paste', 'facebook']; if (name === 'x' || name.endsWith('_x')) return ['paste', 'x']; if (name.includes('previous') || name.includes('up')) return ['iterate', 'arrow_up']; if (name.includes('next') || name.includes('down')) return ['iterate', 'arrow_down']; if (name.includes('toggle')) return ['toggle']; if (name.includes('iterate') || name.includes('sequence')) return ['iterate', 'paste']; return ['paste'] }
function actionIconNames(action) { const display = keybindData.action_displays[action] || {}; return inferredIcons(action, display).filter(name => keybindData.icon_library[name]).slice(0, 2) }
function actionDisplay(action) { const custom = keybindData.action_displays[action] || {}, label = custom.label || keybindData.action_labels[action] || action.replaceAll('_', ' '), icons = actionIconNames(action).map(name => keybindData.icon_library[name].svg).join(''); return `${icons ? `<span class="action-icons">${icons}</span>` : ''}<span>${esc(label)}</span>` }
function assignedActionNames() { return new Set([...Object.values(keybindData.base || {}), ...Object.values(keybindData.layer2 || {}), ...Object.values(keybindData.layer3 || {})].filter(Boolean)) }
function renderActionList() { const q = $('actionSearch').value.toLowerCase(), assigned = assignedActionNames(), customIds = new Set(keybindData.custom_action_ids || []), singleIds = new Set(keybindData.single_action_ids || []), actions = Object.keys(keybindData.action_labels).filter(action => !['layer2', 'layer3', 'toggle_hotkeys'].includes(action) && (!hideAssignedActions || !assigned.has(action)) && (!customActionsOnly || customIds.has(action)) && (!hideSinglePasteActions || !singleIds.has(action)) && (!q || action.toLowerCase().includes(q) || (keybindData.action_labels[action] || '').toLowerCase().includes(q))).sort((a, b) => (keybindData.action_labels[a] || a).localeCompare(keybindData.action_labels[b] || b)); $('actionList').innerHTML = actions.map(action => `<div class="action-item ${selectedAction === action ? 'selected' : ''}" draggable="true" data-action-id="${esc(action)}"><span>${actionDisplay(action)}</span><span class="action-id">${esc(action)}</span></div>`).join('') || '<div class="empty">No matching actions.</div>'; document.querySelectorAll('.action-item').forEach(item => { item.onclick = () => selectKeyAction(item.dataset.actionId); item.ondragstart = e => e.dataTransfer.setData('application/x-jaw-action', item.dataset.actionId) }) }
function eligibleIcons(action) { const icons = ['paste', 'iterate', 'arrow_up', 'arrow_down', 'toggle', 'cycle', 'selection', 'brief'], name = action.toLowerCase(); for (const social of ['linkedin', 'github', 'portfolio', 'facebook', 'x']) if (name === social || name.includes(social)) icons.push(social); return icons }
function setupIconEditor() {
  if (!$('actionIconChoices')) $('actionDisplayEditor').insertAdjacentHTML('beforeend', '<div class="field"><label>Icons — select up to two</label><div class="icon-choices" id="actionIconChoices"></div></div>');
  if (!$('assignedFilter')) {
    $('actionSearch').insertAdjacentHTML('afterend', '<button class="assigned-filter" id="assignedFilter" title="Show only actions that are not assigned to a key"><span class="assigned-filter-switch"></span><span>Unassigned only</span></button>');
    $('assignedFilter').onclick = () => { hideAssignedActions = !hideAssignedActions; $('assignedFilter').classList.toggle('active', hideAssignedActions); $('assignedFilter').setAttribute('aria-pressed', String(hideAssignedActions)); renderActionList() };
  }
  if (!$('customActionsFilter')) {
    $('assignedFilter').insertAdjacentHTML('afterend', '<button class="assigned-filter" id="customActionsFilter" title="Show only user-created Custom Actions"><span class="assigned-filter-switch"></span><span>Custom actions only</span></button>');
    $('customActionsFilter').onclick = () => { customActionsOnly = !customActionsOnly; $('customActionsFilter').classList.toggle('active', customActionsOnly); $('customActionsFilter').setAttribute('aria-pressed', String(customActionsOnly)); renderActionList() };
  }
  if (!$('singlePasteFilter')) {
    $('customActionsFilter').insertAdjacentHTML('afterend', '<button class="assigned-filter" id="singlePasteFilter" title="Hide built-in and custom single-value paste actions"><span class="assigned-filter-switch"></span><span>Hide single paste actions</span></button>');
    $('singlePasteFilter').classList.toggle('active', hideSinglePasteActions);
    $('singlePasteFilter').setAttribute('aria-pressed', String(hideSinglePasteActions));
    $('singlePasteFilter').onclick = () => { hideSinglePasteActions = !hideSinglePasteActions; localStorage.setItem('jaw_hide_single_paste_actions', hideSinglePasteActions ? 'on' : 'off'); $('singlePasteFilter').classList.toggle('active', hideSinglePasteActions); $('singlePasteFilter').setAttribute('aria-pressed', String(hideSinglePasteActions)); renderActionList() };
  }
}
function renderIconChoices() { if (!$('actionIconChoices')) return; if (!selectedAction) { $('actionIconChoices').innerHTML = ''; return } const selected = new Set(actionIconNames(selectedAction)); $('actionIconChoices').innerHTML = eligibleIcons(selectedAction).map(name => { const icon = keybindData.icon_library[name]; return `<label class="icon-choice"><input type="checkbox" value="${name}" ${selected.has(name) ? 'checked' : ''}>${icon.svg}<span>${esc(icon.label)}</span></label>` }).join(''); $('actionIconChoices').querySelectorAll('input').forEach(input => input.onchange = () => { const checked = [...$('actionIconChoices').querySelectorAll('input:checked')]; if (checked.length > 2) { input.checked = false; toast('Select no more than two icons') } updateActionDisplay() }) }
function selectKeyAction(action, cellKey = '') { selectedAction = action || ''; selectedCellKey = cellKey; renderActionList(); $('selectedActionName').textContent = action ? (keybindData.action_labels[action] || 'Selected action') : 'Select an action or bound key'; const display = action ? (keybindData.action_displays[action] || {}) : {}; $('actionDisplayName').value = action ? (display.label || keybindData.action_labels[action] || '') : ''; renderIconChoices() }
function currentLayout() { const layout = keyLayouts[$('keyboardLayout').value] || builtinLayouts.qwerty; for (const row of layout) for (let i = 0; i < row.length; i++)if (row[i] && !/^[A-Z0-9]$/i.test(row[i])) row[i] = ''; return layout }
function isBuiltinLayout() { return false }
function canEditBind(cell) { return true }
function setCursorMessage(cell, event) { const message = $('bindCursorMessage'), restricted = keybindMode === 'binds' && !canEditBind(cell); message.classList.toggle('visible', restricted); if (restricted && event) { message.style.left = `${event.clientX + 14}px`; message.style.top = `${event.clientY + 14}px` } }
function applyEditorMode() { const actions = keybindMode === 'actions', binds = keybindMode === 'binds', globals = keybindMode === 'globals'; $('actionPalette').classList.toggle('collapsed', !actions); document.querySelector('.keybind-layout').classList.toggle('palette-hidden', !actions); $('actionDisplayEditor').hidden = !actions; document.querySelector('.hotkey-settings').classList.toggle('editor-hidden', !globals); document.querySelector('.layer-tabs').classList.toggle('editor-hidden', globals); $('keybindMatrix').classList.toggle('editor-hidden', globals); $('deleteBind').disabled = !binds; $('deleteAssignment').disabled = !actions; $('globalsToggle').classList.toggle('mode-active', globals); $('actionsToggle').classList.toggle('mode-active', actions); $('editBinds').classList.toggle('mode-active', binds); $('actionHelp').textContent = 'Drag an action to a key, or select it and click a key. Select an action to edit its display.'; $('keybindModeHelp').textContent = binds ? 'Hover over a cell and press a key to change that layout position.' : actions ? 'Select or drag actions. Delete Assignments removes the action from a clicked cell.' : ''; $('bindCursorMessage').classList.remove('visible'); renderActionList(); renderKeyMatrix() }
function setMode(mode) { keybindMode = keybindMode === mode ? '' : mode; deleteBindMode = false; deleteAssignmentMode = false; selectKeyAction(''); $('deleteBind').classList.remove('mode-active'); $('deleteAssignment').classList.remove('mode-active'); applyEditorMode() }
function renderLayerWarning() { const bindings = keybindData[keyLayer] || {}; $('layerWarning').textContent = keyLayer !== 'base' && !Object.values(bindings).some(Boolean) ? `${keyLayer === 'layer2' ? 'Layer 2' : 'Layer 3'} has no assignments.` : '' }
const retiredLayerActions = new Set(['layer2_toggle', 'layer3_toggle']);
function normalizeCycleLayerBindings() { for (const layer of ['base', 'layer2', 'layer3']) for (const [key, action] of Object.entries(keybindData[layer] || {})) if (retiredLayerActions.has(String(action).split('|')[0])) delete keybindData[layer][key]; const owners = new Map(); for (const layer of ['base', 'layer2', 'layer3']) for (const [key, action] of Object.entries(keybindData[layer] || {})) if (String(action).split('|')[0] === 'cycle_layers') { if (owners.has(key)) delete keybindData[layer][key]; else owners.set(key, layer) } for (const [key, owner] of owners) for (const layer of ['base', 'layer2', 'layer3']) if (layer !== owner) delete keybindData[layer][key] }
function assignLayerAction(layer, key, action) { const actionId = String(action || '').split('|')[0]; if (retiredLayerActions.has(actionId)) return false; const cycleOwner = ['base', 'layer2', 'layer3'].find(name => String(keybindData[name]?.[key] || '').split('|')[0] === 'cycle_layers'); if (actionId !== 'cycle_layers' && cycleOwner && cycleOwner !== layer) { toast('This key position is reserved for Cycle Layers'); return false } if (actionId === 'cycle_layers') for (const name of ['base', 'layer2', 'layer3']) delete keybindData[name][key]; keybindData[layer][key] = action; return true }
document.addEventListener('click', event => { if (keybindMode !== 'actions' || !selectedAction || selectedCellKey) return; const cell = event.target.closest('#keybindMatrix .key-cell[data-key]'); if (!cell) return; event.preventDefault(); event.stopImmediatePropagation(); if (assignLayerAction(keyLayer, cell.dataset.key, selectedAction)) { selectKeyAction(''); renderKeyMatrix() } }, true);
document.addEventListener('drop', event => { if (keybindMode !== 'actions') return; const cell = event.target.closest('#keybindMatrix .key-cell[data-key]'); if (!cell) return; const target = cell.dataset.key, action = event.dataTransfer.getData('application/x-jaw-action'); let source = null; try { source = JSON.parse(event.dataTransfer.getData('application/x-jaw-cell') || 'null') } catch { } const movedAction = action || source?.action; if (!movedAction) return; event.preventDefault(); event.stopImmediatePropagation(); if (source && source.key === target) return; if (assignLayerAction(keyLayer, target, movedAction)) { if (source) delete keybindData[keyLayer][source.key]; selectKeyAction(''); renderKeyMatrix() } }, true);
function renderKeyMatrix() { const bindings = keybindData[keyLayer] || {}, rows = currentLayout(); $('keybindMatrix').innerHTML = rows.flatMap((row, rowIndex) => row.map((key, colIndex) => { const editable = keybindMode === 'binds' && (!isBuiltinLayout() || rowIndex === rows.length - 1); if (!key) return `<div class="key-cell key-empty ${editable ? 'bind-editable' : ''}" data-row="${rowIndex}" data-col="${colIndex}">Unused</div>`; const action = bindings[key] || ''; return `<div class="key-cell ${editable ? 'bind-editable' : ''} ${selectedCellKey === key ? 'selected' : ''}" draggable="${keybindMode === 'actions' && Boolean(action)}" data-key="${esc(key)}" data-row="${rowIndex}" data-col="${colIndex}"><div class="key-name">${esc(key)}</div><div class="key-action">${action ? actionDisplay(action) : '<span class="key-empty">Unassigned</span>'}</div></div>` })).join(''); renderLayerWarning(); document.querySelectorAll('.key-cell').forEach(cell => { cell.onmouseenter = e => { hoveredKeyCell = cell; setCursorMessage(cell, e) }; cell.onmousemove = e => setCursorMessage(cell, e); cell.onmouseleave = () => { if (hoveredKeyCell === cell) hoveredKeyCell = null; $('bindCursorMessage').classList.remove('visible') }; cell.onclick = () => { const key = cell.dataset.key; if (deleteAssignmentMode && key) { delete bindings[key]; selectKeyAction(''); renderKeyMatrix(); return } if (keybindMode === 'binds') { if (!canEditBind(cell)) return; if (deleteBindMode) { const oldKey = cell.dataset.key; if (oldKey) { for (const layer of ['base', 'layer2', 'layer3']) delete keybindData[layer][oldKey] } const row = currentLayout()[Number(cell.dataset.row)], col = Number(cell.dataset.col); if (isBuiltinLayout()) row.splice(col, 1); else row[col] = ''; selectedCellKey = ''; renderKeyMatrix() } return } if (keybindMode === 'display') { if (key && bindings[key]) selectKeyAction(bindings[key], key); return } if (keybindMode !== 'actions' || !key) return; if (selectedAction && !selectedCellKey) { bindings[key] = selectedAction; selectKeyAction(''); renderKeyMatrix(); return } if (bindings[key]) { selectKeyAction(bindings[key], key); renderKeyMatrix() } else { selectKeyAction(''); renderKeyMatrix() } }; cell.ondragstart = e => { if (keybindMode !== 'actions') return e.preventDefault(); const key = cell.dataset.key, action = bindings[key]; if (action) e.dataTransfer.setData('application/x-jaw-cell', JSON.stringify({ key, action })) }; cell.ondragover = e => { if (keybindMode === 'actions') { e.preventDefault(); cell.classList.add('drop-over') } }; cell.ondragleave = () => cell.classList.remove('drop-over'); cell.ondrop = e => { if (keybindMode !== 'actions') return; e.preventDefault(); cell.classList.remove('drop-over'); const target = cell.dataset.key; if (!target) return; const action = e.dataTransfer.getData('application/x-jaw-action'); if (action) bindings[target] = action; else { try { const source = JSON.parse(e.dataTransfer.getData('application/x-jaw-cell')); delete bindings[source.key]; bindings[target] = source.action } catch { } } selectKeyAction(''); renderKeyMatrix() } }) }
function renderLayoutOptions() { const current = userData.keyboard_layout || 'qwerty'; $('keyboardLayout').innerHTML = Object.keys(keyLayouts).map(name => `<option value="${esc(name)}">${esc(name === 'colemak-dh' ? 'Colemak-DH' : name === 'qwerty' ? 'QWERTY' : name)}</option>`).join(''); $('keyboardLayout').value = keyLayouts[current] ? current : 'qwerty' }
function hotkeyLabel(value) { return value ? value.split('+').map(x => x.length === 1 ? x : x[0] + x.slice(1).toLowerCase()).join(' + ') : 'Click and press shortcut' }
function setHotkey(path, value) { const settings = keybindData.hotkey_settings; if (path === 'toggle' || path === 'window') settings[path] = value; else settings.layers[path].hotkey = value; renderHotkeySettings() }
function renderLayerConfig(layer) { const settings = keybindData.hotkey_settings.layers[layer], host = document.querySelector(`[data-layer-config="${layer}"]`), label = layer === 'layer2' ? 'Layer 2' : 'Layer 3', cycleManaged = layer === 'layer3' && keybindData.hotkey_settings.layers.layer2.enabled && keybindData.hotkey_settings.layers.layer2.mode === 'cycle'; if (cycleManaged) settings.mode = 'cycle'; const modes = cycleManaged ? '<option value="cycle">Uses Layer 2 cycle</option>' : `<option value="hold">Hold</option><option value="toggle">Toggle</option>${layer === 'layer2' ? '<option value="cycle">Cycle</option>' : ''}`; host.innerHTML = `<label class="layer-toggle"><input type="checkbox" data-layer-enabled="${layer}" ${settings.enabled ? 'checked' : ''}> Enable ${label}</label><select data-layer-mode="${layer}" ${!settings.enabled || cycleManaged ? 'disabled' : ''}>${modes}</select><button class="hotkey-capture" data-hotkey-path="${layer}" ${!settings.enabled || cycleManaged ? 'disabled' : ''}>${cycleManaged ? 'Shared cycle key' : hotkeyLabel(settings.hotkey)}</button><button class="btn" data-clear-hotkey="${layer}" ${!settings.enabled || cycleManaged ? 'disabled' : ''}>Clear</button>`; host.querySelector('select').value = settings.mode; host.querySelector('[data-layer-enabled]').onchange = e => { settings.enabled = e.target.checked; renderHotkeySettings() }; host.querySelector('select').onchange = e => { settings.mode = e.target.value; if (layer === 'layer2' && settings.mode === 'cycle') keybindData.hotkey_settings.layers.layer3.mode = 'cycle'; renderHotkeySettings() } }
function renderHotkeySettings() { const settings = keybindData.hotkey_settings; ensureLayerSettings(); document.querySelectorAll('[data-hotkey-path="toggle"],[data-hotkey-path="window"]').forEach(button => button.textContent = hotkeyLabel(settings[button.dataset.hotkeyPath])); $('disableWhenMinimized').checked = settings.disable_when_minimized; document.querySelectorAll('.hotkey-capture:not(:disabled)').forEach(button => button.onclick = () => { listeningHotkey = button.dataset.hotkeyPath; document.querySelectorAll('.hotkey-capture').forEach(x => x.classList.toggle('listening', x === button)); button.textContent = 'Press shortcut…' }); document.querySelectorAll('[data-clear-hotkey]:not(:disabled)').forEach(button => button.onclick = () => setHotkey(button.dataset.clearHotkey, '')) };
function normalizeHotkeyEvent(e) { const parts = []; if (e.ctrlKey) parts.push('CTRL'); if (e.altKey) parts.push('ALT'); if (e.shiftKey) parts.push('SHIFT'); if (e.metaKey) parts.push('WIN'); const modifier = ['Control', 'Alt', 'Shift', 'Meta'].includes(e.key); if (!modifier) parts.push(e.key === ' ' ? 'SPACE' : e.key.toUpperCase()); return parts.join('+') }
function normalizeBuiltinOverride(rows) { const removed = new Set(['ESC', 'TAB', 'SHIFT', 'CTRL']); return rows.map(row => { const cleaned = row.filter(key => !removed.has(key)).slice(0, 5); return cleaned }) }
async function loadKeybinds() { keybindData = await fetch('/api/keybinds', { cache: 'no-store' }).then(r => { if (!r.ok) throw new Error(`Keybind request failed (${r.status})`); return r.json() }); keybindData.layer3 ??= {}; keybindData.action_displays ??= {}; keybindData.custom_layouts ??= {}; keybindData.hotkey_settings ??= { toggle: 'SHIFT+SPACE', window: 'CTRL+SHIFT+F1', disable_when_minimized: false, layers: { layer2: { enabled: true, hold: true, mode: 'hold', hotkey: 'SHIFT' }, layer3: { enabled: true } } }; for (const name of Object.keys(builtinLayouts)) if (keybindData.custom_layouts[name]) keybindData.custom_layouts[name] = normalizeBuiltinOverride(keybindData.custom_layouts[name]); keyLayouts = { ...structuredClone(builtinLayouts), ...structuredClone(keybindData.custom_layouts) }; setupIconEditor(); renderLayoutOptions(); renderActionList(); renderKeyMatrix(); renderHotkeySettings(); applyEditorMode(); selectKeyAction(selectedAction); renderLayerControls(); renderTips() }
document.querySelector('[data-page="keybindPage"]').addEventListener('click', loadKeybinds); $('globalsToggle').onclick = () => setMode('globals'); $('actionsToggle').onclick = () => setMode('actions'); $('editBinds').onclick = () => setMode('binds'); $('deleteAssignment').onclick = () => { deleteAssignmentMode = !deleteAssignmentMode; deleteBindMode = false; selectedAction = ''; selectedCellKey = ''; $('deleteAssignment').classList.toggle('mode-active', deleteAssignmentMode); $('deleteBind').classList.remove('mode-active'); renderActionList(); renderKeyMatrix() }; $('deleteBind').onclick = () => { deleteBindMode = !deleteBindMode; deleteAssignmentMode = false; selectedAction = ''; selectedCellKey = ''; $('deleteBind').classList.toggle('mode-active', deleteBindMode); $('deleteAssignment').classList.remove('mode-active'); renderActionList(); renderKeyMatrix() }; $('actionSearch').oninput = renderActionList; $('disableWhenMinimized').onchange = e => keybindData.hotkey_settings.disable_when_minimized = e.target.checked; document.querySelectorAll('[data-layer-enabled]').forEach(input => input.onchange = () => { keybindData.hotkey_settings.layers[input.dataset.layerEnabled].enabled = input.checked; renderHotkeySettings() }); document.querySelectorAll('[data-key-layer]').forEach(button => button.onclick = () => { keyLayer = button.dataset.keyLayer; selectedCellKey = ''; document.querySelectorAll('[data-key-layer]').forEach(x => x.classList.toggle('active', x === button)); renderKeyMatrix() }); $('keyboardLayout').onchange = async () => { selectedCellKey = ''; renderKeyMatrix(); await api('/api/user/keyboard-layout', { layout: $('keyboardLayout').value }) }; $('addLayout').onclick = () => { $('newLayoutName').value = ''; $('copyLayout').innerHTML = Object.keys(keyLayouts).map(name => `<option value="${esc(name)}">${esc(name === 'colemak-dh' ? 'Colemak-DH' : name === 'qwerty' ? 'QWERTY' : name)}</option>`).join(''); $('copyLayout').value = $('keyboardLayout').value; $('layoutDialog').showModal(); requestAnimationFrame(() => $('newLayoutName').focus()) }; $('cancelLayout').onclick = () => $('layoutDialog').close(); $('createLayout').onclick = () => { const name = $('newLayoutName').value.trim(), source = $('copyLayout').value; if (!name || keyLayouts[name]) return; keyLayouts[name] = structuredClone(keyLayouts[source]); keybindData.custom_layouts[name] = keyLayouts[name]; $('layoutDialog').close(); renderLayoutOptions(); $('keyboardLayout').value = name; renderKeyMatrix() }; $('saveKeybinds').onclick = async () => { keybindData.custom_layouts = { ...keybindData.custom_layouts, ...Object.fromEntries(Object.entries(keyLayouts).filter(([name]) => !builtinLayouts[name] || keybindData.custom_layouts[name])) }; await api('/api/keybinds', keybindData); await api('/api/user/keyboard-layout', { layout: $('keyboardLayout').value }); toast('Keybinds saved') }; $('actionDisplayName').oninput = updateActionDisplay; document.addEventListener('keydown', e => { if (!$('keybindPage').classList.contains('active')) return; if (listeningHotkey) { e.preventDefault(); const value = normalizeHotkeyEvent(e), modifierOnly = ['Control', 'Alt', 'Shift', 'Meta'].includes(e.key), layerSetting = keybindData.hotkey_settings.layers[listeningHotkey]; if (modifierOnly && (!layerSetting || layerSetting.mode !== 'hold')) return; if (value) setHotkey(listeningHotkey, value); listeningHotkey = null; return } if (e.target.matches('input,textarea,select')) return; if (e.key === 'Escape') { e.preventDefault(); deleteBindMode = false; deleteAssignmentMode = false; selectedAction = ''; selectedCellKey = ''; $('deleteBind').classList.remove('mode-active'); $('deleteAssignment').classList.remove('mode-active'); renderActionList(); renderKeyMatrix(); return } if (keybindMode !== 'binds' || deleteBindMode || !hoveredKeyCell || !canEditBind(hoveredKeyCell)) return; const key = e.key === ' ' ? 'SPACE' : e.key === 'Escape' ? 'ESC' : e.key === 'Enter' ? 'ENTER' : e.key.length === 1 ? e.key.toUpperCase() : e.key.toUpperCase(); if (!key) return; e.preventDefault(); const rows = currentLayout(), row = Number(hoveredKeyCell.dataset.row), col = Number(hoveredKeyCell.dataset.col), oldKey = rows[row][col]; rows[row][col] = key; for (const layer of ['base', 'layer2', 'layer3']) if (oldKey && keybindData[layer][oldKey] && !keybindData[layer][key]) { keybindData[layer][key] = keybindData[layer][oldKey]; delete keybindData[layer][oldKey] } if (!isBuiltinLayout()) keybindData.custom_layouts[$('keyboardLayout').value] = structuredClone(rows); renderKeyMatrix() });
function updateActionDisplay() { if (!selectedAction) return; const previous = keybindData.action_displays[selectedAction] || {}, icons = $('actionIconChoices') ? [...$('actionIconChoices').querySelectorAll('input:checked')].map(input => input.value).slice(0, 2) : inferredIcons(selectedAction, previous); keybindData.action_displays[selectedAction] = { label: $('actionDisplayName').value, icons }; renderActionList(); renderKeyMatrix() }
$('saveKeybinds').addEventListener('click', () => { keybindData.custom_layouts[$('keyboardLayout').value] = structuredClone(currentLayout()); for (const [action, display] of Object.entries(keybindData.action_displays)) { keybindData.action_displays[action] = { label: display.label || '', icons: inferredIcons(action, display).slice(0, 2) } } }, { capture: true });
$('saveKeybinds').addEventListener('click', () => { keybindData.hotkey_settings.layers = { layer2: { enabled: true, mode: 'hold', hotkey: 'SHIFT' } } }, { capture: true });
document.addEventListener('keydown', e => { if (!$('keybindPage').classList.contains('active') || keybindMode !== 'binds' || e.target.matches('input,textarea,select')) return; if (!/^[a-z0-9]$/i.test(e.key)) { e.preventDefault(); e.stopImmediatePropagation(); toast('Bindings are limited to letters and numbers. Shift is reserved for Layer 2.') } }, true);
document.querySelector('[data-key-layer="layer2"]').textContent = 'Layer 2';
const bindWarning = document.createElement('div'); bindWarning.id = 'bindWarning'; bindWarning.className = 'bind-warning'; bindWarning.hidden = true; bindWarning.textContent = 'Bindings accept A–Z and 0–9 only. Shift is reserved for Layer 2. Use modifiers only for global shortcuts; global shortcuts can override shortcuts in other applications.'; $('keybindMatrix').insertAdjacentElement('afterend', bindWarning); const updateBindWarning = () => bindWarning.hidden = keybindMode !== 'binds'; for (const id of ['globalsToggle', 'actionsToggle', 'editBinds']) $(id).addEventListener('click', updateBindWarning);
const contextualTips = document.createElement('div'); contextualTips.id = 'contextualTips'; contextualTips.className = 'context-tips';
function currentTipsContext() {
  if ($('keybindPage').classList.contains('active')) {
    if (keybindMode === 'actions' && deleteAssignmentMode) return 'keybind-actions-delete';
    if (keybindMode === 'binds' && deleteBindMode) return 'keybind-binds-delete';
    return `keybind-${keybindMode || 'overview'}`;
  }
  if ($('jobsPage').classList.contains('active')) return 'jobs';
  if ($('userPage').classList.contains('active')) {
    if ($('workView').style.display !== 'none') return 'work';
    if ($('customDataView').style.display !== 'none') return 'custom-data';
    if ($('customActionsView').style.display !== 'none') return 'custom-actions';
    if ($('qaView').style.display !== 'none') return 'qa';
    return 'user';
  }
  return 'user';
}
function tipsHtml(context) { const copy = { jobs: '<b>Job tracker:</b> Search, sort, and filter captured jobs. Select a job to review its analysis, application status, and saved Q&A.', user: '<b>User:</b> These values supply profile paste actions. Custom fields become available as actions after they are saved.', work: '<b>Work Experience:</b> Entries save automatically. Drag an entry by its handle to change the paste-iterator order.', competencies: '<b>Competencies:</b> Hover over a card and press 0–5 to rate it. Double-click a card to rename it. Ratings sort automatically.', skills: '<b>Skills:</b> Hover over a card and press 0–5 to rate it. Double-click a card to rename it. Ratings sort automatically.', qa: '<b>Q&A:</b> Store reusable application questions and answers here. Changes are committed with Save Q&A.', 'keybind-overview': '<b>Keybinds:</b> Select a layer, then choose a mode to assign actions, change physical key positions, or edit global shortcuts. Shift momentarily activates Layer 2.', 'keybind-globals': '<b>Edit Globals:</b> Configure Minimize/Restore and Hotkey Toggle shortcuts. Ctrl, Alt, Shift, and Windows modifiers are allowed only for these global shortcuts.', 'keybind-actions': '<b>Add / Move Actions:</b> Drag an action to a key, or select it and click a key. Select an action or occupied cell to edit its display. <button class="assigned-filter" id="tipsAssignedFilter"><span class="assigned-filter-switch"></span><span>Unassigned only</span></button>', 'keybind-actions-delete': '<b>Delete Assignment:</b> Click a matrix cell to remove its action without changing the physical key position.', 'keybind-binds': '<b>Edit Binds:</b> Hover over a cell and press an alphanumeric key to change that layout position. Bindings accept A–Z and 0–9 only.', 'keybind-binds-delete': '<b>Delete Binds:</b> Click a matrix cell to remove that physical key position and its assignments.' }; return copy[context] || '' }
function tipsState(context) { return localStorage.getItem(`jaw_tips_${context}`) !== 'off' }
$('tipsToggle').onclick = () => { const context = currentTipsContext(), enabled = tipsState(context); localStorage.setItem(`jaw_tips_${context}`, enabled ? 'off' : 'on'); renderTips() }; for (const id of ['globalsToggle', 'actionsToggle', 'editBinds', 'deleteAssignment', 'deleteBind']) $(id).addEventListener('click', renderTips);
const tipsShell = document.createElement('div'), tipsBody = document.createElement('div'); tipsShell.className = 'tips-shell'; tipsBody.className = 'tips-body'; tipsShell.append(tipsBody, $('tipsToggle'));
function placeTipsShell() { if ($('keybindPage').classList.contains('active')) document.querySelector('.keybind-page').prepend(tipsShell); else if ($('jobsPage').classList.contains('active')) $('jobsPage').prepend(tipsShell); else document.querySelector('#userPage .top-tabs').insertAdjacentElement('afterend', tipsShell) }
function ensureLayerSettings() { if (!keybindData) return null; keybindData.hotkey_settings ??= {}; keybindData.hotkey_settings.layers ??= {}; const layers = keybindData.hotkey_settings.layers; layers.layer2 = { enabled: layers.layer2?.enabled ?? true, hold: layers.layer2?.hold ?? true, mode: 'hold', hotkey: 'SHIFT' }; layers.layer3 = { enabled: layers.layer3?.enabled ?? true }; return layers }
function renderLayerControls() { const layers = ensureLayerSettings(); if (!layers) return; let controls = $('layerControlSet'); if (!controls) { controls = document.createElement('div'); controls.id = 'layerControlSet'; controls.className = 'layer-control-set'; document.querySelector('.layer-tabs').append(controls) } controls.innerHTML = `<label class="layer-control"><span>Layer 2</span><input id="layer2Enabled" type="checkbox" ${layers.layer2.enabled ? 'checked' : ''}><span class="layer-control-switch"></span></label><label class="layer-control ${layers.layer2.enabled ? '' : 'disabled'}"><span>Hold</span><input id="layer2Hold" type="checkbox" ${layers.layer2.hold ? 'checked' : ''} ${layers.layer2.enabled ? '' : 'disabled'}><span class="layer-control-switch"></span></label><label class="layer-control"><span>Layer 3</span><input id="layer3Enabled" type="checkbox" ${layers.layer3.enabled ? 'checked' : ''}><span class="layer-control-switch"></span></label>`; const layer2Tab = document.querySelector('[data-key-layer="layer2"]'), layer3Tab = document.querySelector('[data-key-layer="layer3"]'); layer2Tab.hidden = !layers.layer2.enabled; layer3Tab.hidden = !layers.layer3.enabled; if ((keyLayer === 'layer2' && !layers.layer2.enabled) || (keyLayer === 'layer3' && !layers.layer3.enabled)) { keyLayer = 'base'; document.querySelectorAll('[data-key-layer]').forEach(tab => tab.classList.toggle('active', tab.dataset.keyLayer === 'base')); renderKeyMatrix(); return } $('layer2Enabled').onchange = e => { layers.layer2.enabled = e.target.checked; renderLayerControls() }; $('layer2Hold').onchange = e => { layers.layer2.hold = e.target.checked }; $('layer3Enabled').onchange = e => { layers.layer3.enabled = e.target.checked; renderLayerControls() } }
const baseRenderLayerWarning = renderLayerWarning; renderLayerWarning = function () { baseRenderLayerWarning(); renderLayerControls() };
$('saveKeybinds').addEventListener('click', () => { const layers = ensureLayerSettings(); keybindData.hotkey_settings.layers = { layer2: { enabled: layers.layer2.enabled, hold: layers.layer2.hold, mode: 'hold', hotkey: 'SHIFT' }, layer3: { enabled: layers.layer3.enabled } } }, { capture: true });
const originalTipsHtml = tipsHtml; tipsHtml = function (context) { if (context === 'keybind-actions') return '<b>Add / Move Actions:</b> Drag an action to a key, or select it and click a key. Select an action or occupied cell to edit its display.'; if (context === 'custom-data') return '<b>Custom Data:</b> Create reusable single-line or multi-line values. Labels identify the values in Custom Actions and must be clear.'; if (context === 'custom-actions') return '<b>Custom Actions:</b> Single Paste copies one Custom Data value. Iterator cycles through multiple values in the displayed order. Action labels must be unique; renaming preserves bindings.'; return originalTipsHtml(context) };
function renderTips() {
  const context = currentTipsContext(), enabled = tipsState(context);
  placeTipsShell();
  $('tipsToggle').innerHTML = 'Tips <span class="tips-switch" aria-hidden="true"></span>';
  $('tipsToggle').classList.toggle('tips-enabled', enabled);
  $('tipsToggle').setAttribute('aria-label', `Turn ${context.replaceAll('-', ' ')} tips ${enabled ? 'off' : 'on'}`);
  $('tipsToggle').setAttribute('aria-pressed', String(enabled));
  tipsShell.classList.toggle('collapsed', !enabled);
  tipsBody.hidden = !enabled;
  tipsBody.innerHTML = tipsHtml(context);
  if (context === 'keybind-actions' && $('tipsAssignedFilter')) {
    $('tipsAssignedFilter').classList.toggle('active', hideAssignedActions);
    $('tipsAssignedFilter').setAttribute('aria-pressed', String(hideAssignedActions));
    $('tipsAssignedFilter').onclick = () => {
      hideAssignedActions = !hideAssignedActions;
      $('tipsAssignedFilter').classList.toggle('active', hideAssignedActions);
      if ($('assignedFilter')) $('assignedFilter').classList.toggle('active', hideAssignedActions);
      renderActionList();
    };
  }
};
renderTips(); $('userTab').addEventListener('click', () => loadUserData().then(() => renderUser()).catch(error => toast(error.message)));
$('customDataTab').onclick = () => showUserView('custom-data'); $('customActionsTab').onclick = () => showUserView('custom-actions');
let customDataSaveTimer, customActionSaveTimer;
let customDataSaveChain = Promise.resolve(), customActionSaveChain = Promise.resolve();
async function saveCustomDataNow() {
  clearTimeout(customDataSaveTimer); collectCustomFields();
  if (!validateVisibleLabels('[data-custom-label]')) return;
  const fields = structuredClone(userData.custom_fields);
  const request = customDataSaveChain.catch(() => { }).then(() => api('/api/user/custom-fields', { fields }));
  customDataSaveChain = request;
  try { await request; toast('Custom Data saved') } catch (error) { toast(error.message) }
}
function queueCustomDataSave() { clearTimeout(customDataSaveTimer); customDataSaveTimer = setTimeout(saveCustomDataNow, 450) }
async function saveCustomActionsNow() {
  clearTimeout(customActionSaveTimer); collectCustomActions();
  if (!validateVisibleLabels('[data-action-label]')) return;
  const labels = userData.custom_actions.map(action => action.label.trim().toLocaleLowerCase()).filter(Boolean);
  if (new Set(labels).size !== labels.length) { toast('Action labels must be unique'); return }
  const actions = structuredClone(userData.custom_actions);
  const request = customActionSaveChain.catch(() => { }).then(() => api('/api/user/custom-actions', { actions }));
  customActionSaveChain = request;
  try { await request; toast('Custom Actions saved') } catch (error) { toast(error.message) }
}
function queueCustomActionSave() { clearTimeout(customActionSaveTimer); customActionSaveTimer = setTimeout(saveCustomActionsNow, 450) }
$('customFields').addEventListener('click', event => { if (event.target.closest('[data-remove-custom]')) collectCustomFields() }, { capture: true });
$('customFields').addEventListener('input', queueCustomDataSave);
$('customFields').addEventListener('change', queueCustomDataSave);
$('customFields').addEventListener('click', event => { if (event.target.closest('[data-remove-custom]')) setTimeout(saveCustomDataNow) });
$('customActions').addEventListener('input', queueCustomActionSave);
$('customActions').addEventListener('change', queueCustomActionSave);
$('customActions').addEventListener('click', event => { if (event.target.closest('[data-remove-action],[data-value-up],[data-value-down],[data-value-remove]')) setTimeout(saveCustomActionsNow) });
const launchSearch = new URLSearchParams(location.search).get('q'); if (launchSearch) $('search').value = launchSearch; loadJobs(); const initial = new URLSearchParams(location.search).get('job'); if (initial) showJob(Number(initial));


/* --------------------------------------------------------------------------
 * JAW capability model UI + hash routing
 * -------------------------------------------------------------------------- */
const CAP_ROUTE_DEFAULT = 'tracker';
let capabilityState = { api_version: 2, entities: [], relationships: [], sets: [], view_preferences: {}, stats: {} };
let capabilitySchema = null;
let capabilityView = 'hierarchy';
let capabilitySetId = '__all__';
let capabilitySetSelection = null;
let capabilityHoveredId = '';
let capabilitySavingViewTimer = null;
let capabilityDisplayMode = 'compact';
let capabilityMatchMode = false;
let capabilityLeftPaneMode = 'fixed';
let capabilityRightPaneMode = 'fixed';
let capabilityShowUseGuide = true;
let smartAddPreviewData = null;
let routeApplying = false;

const FALLBACK_RATING_GUIDANCE = [
  { value: 0, label: 'Unrated', description: 'Not assessed' },
  { value: 1, label: 'Conceptual', description: 'Understand the concepts/use cases; little or no hands-on experience' },
  { value: 2, label: 'Hands-on', description: 'Have actually used it, but experience is limited or narrow' },
  { value: 3, label: 'Proficient', description: 'Can work independently on normal production tasks' },
  { value: 4, label: 'Advanced', description: 'Deep experience; handles complex design/troubleshooting and can guide others' },
  { value: 5, label: 'Expert', description: 'Extensive depth and breadth; regularly solves ambiguous/novel problems and can serve as a technical authority' },
];
const capById = () => Object.fromEntries((capabilityState.entities || []).map(entity => [String(entity.id), entity]));
const capName = entity => String(entity?.display_name || entity?.canonical_name || '');
const capRateable = entity => entity && entity.type !== 'set';
const capTypeLabel = type => ({ competency: 'Competency', technology: 'Technology', product: 'Product / Tool', set: 'Capability Set' })[type] || type;
const capRatingGuidance = () => Array.isArray(capabilitySchema?.ratings) && capabilitySchema.ratings.length ? capabilitySchema.ratings : FALLBACK_RATING_GUIDANCE;
const capRatingLabel = rating => capRatingGuidance().find(item => Number(item.value) === Number(rating))?.label || 'Unrated';
const capSectionGranularityLabel = value => ['', 'Broad', 'Coarse', 'Balanced', 'Detailed', 'Most detailed'][Number(value)] || 'Balanced';
const capEntityGranularityLabel = value => ['', 'Flat', 'Grouped', 'Balanced', 'Detailed', 'Most detailed'][Number(value)] || 'Balanced';

async function capabilityApi(path, body) {
  const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || `Capability request failed (${response.status})`);
  return payload;
}

async function loadCapabilities() {
  const response = await fetch('/api/capabilities', { cache: 'no-store' });
  if (!response.ok) throw new Error(`Capability model request failed (${response.status})`);
  capabilityState = await response.json();
  if (!capabilitySchema) {
    capabilitySchema = await fetch('/api/capabilities/schema', { cache: 'no-store' }).then(r => r.json()).catch(() => null);
  }
  const hierarchy = capabilityState.view_preferences?.hierarchy || {};
  const layout = capabilityState.view_preferences?.layout || {};
  $('capSectionGranularity').value = String(hierarchy.section_granularity ?? 3);
  $('capEntityGranularity').value = String(hierarchy.entity_granularity ?? 3);
  capabilityDisplayMode = hierarchy.display_mode === 'detailed' ? 'detailed' : 'compact';
  capabilityLeftPaneMode = ['fixed', 'auto', 'off'].includes(layout.left_pane) ? layout.left_pane : 'fixed';
  capabilityRightPaneMode = ['fixed', 'auto', 'off'].includes(layout.right_pane) ? layout.right_pane : 'fixed';
  capabilityShowUseGuide = layout.show_use_guide !== false;
  updateCapabilityGranularityLabels();
  renderCapabilityRatingGuide();
  renderCapabilities();
}

function capabilitySearchText(entity) { return [capName(entity), entity.canonical_name, ...(entity.aliases || []), capTypeLabel(entity.type)].join(' ').toLowerCase() }
function filteredCapabilities(includeSets = false) {
  const q = $('capSearch').value.trim().toLowerCase();
  const unratedOnly = $('capUnratedOnly').checked;
  return (capabilityState.entities || []).filter(entity => {
    if (!includeSets && entity.type === 'set') return false;
    if (q && !capabilitySearchText(entity).includes(q)) return false;
    if (unratedOnly && (!capRateable(entity) || Number(entity.rating) !== 0)) return false;
    return true;
  });
}

function renderCapabilityStats() {
  const stats = capabilityState.stats || {};
  $('capStats').innerHTML = `
    <div><b>${stats.capabilities ?? 0}</b><span>Capabilities</span></div>
    <div><b>${stats.sets ?? 0}</b><span>Capability Sets</span></div>
    <div><b>${stats.matching_enabled ?? 0}</b><span>Match enabled</span></div>
    <div><b>${stats.unrated ?? 0}</b><span>Unrated</span></div>`;
}

function relationshipBadges(entity, detailLevel) {
  if (detailLevel < 4) return '';
  const byId = capById();
  const items = (capabilityState.relationships || []).filter(rel => rel.source_id === entity.id || rel.target_id === entity.id).slice(0, 6).map(rel => {
    const outgoing = rel.source_id === entity.id;
    const other = byId[outgoing ? rel.target_id : rel.source_id];
    const arrow = outgoing ? '→' : '←';
    return `<span class="cap-rel" title="${esc(rel.type)}">${arrow} ${esc(capName(other) || 'Unknown')}</span>`;
  });
  return items.length ? `<div class="cap-relations">${items.join('')}</div>` : '';
}

function capabilityTooltip(entity) {
  const parts = [
    capName(entity),
    capTypeLabel(entity.type),
  ];
  if (capRateable(entity)) {
    parts.push(`Rating ${Number(entity.rating) || 0}/5 · ${capRatingLabel(entity.rating)}`);
    parts.push(entity.match_enabled ? 'Match enabled' : 'Match disabled');
    parts.push(entity.iterator_enabled ? 'Iterator enabled' : 'Iterator disabled');
  }
  if (entity.canonical_name && entity.canonical_name !== capName(entity)) {
    parts.push(`Canonical: ${entity.canonical_name}`);
  }
  if ((entity.aliases || []).length) {
    parts.push(`Aliases: ${(entity.aliases || []).join(', ')}`);
  }
  return parts.join(' · ');
}

function compactCapabilityPill(entity, selected = false) {
  const matchClass = capabilityMatchMode && capRateable(entity)
    ? (entity.match_enabled ? ' match-enabled' : ' match-disabled')
    : '';
  const indicator = capabilityMatchMode && capRateable(entity)
    ? `<span class="cap-match-indicator">${entity.match_enabled ? '✓' : '×'}</span>`
    : '';
  return `<button
    class="cap-pill rating-border-${Number(entity.rating) || 0}${selected ? ' selected' : ''}${matchClass}"
    type="button"
    data-cap-card="${esc(entity.id)}"
    title="${esc(capabilityTooltip(entity))}">
      <span class="cap-pill-name">${esc(capName(entity) || 'Unnamed')}</span>
      ${indicator}
    </button>`;
}

function detailedCapabilityCard(entity, detailLevel = 3, selected = false) {
  const aliases = (entity.aliases || []).filter(Boolean);
  const canonical = String(entity.canonical_name || '');
  const showCanonical = detailLevel >= 5 && canonical && canonical !== capName(entity);
  const showAliases = detailLevel >= 4 && aliases.length;
  return `<article
    class="cap-card rating-border-${Number(entity.rating) || 0} ${selected ? 'selected' : ''}"
    data-cap-card="${esc(entity.id)}"
    tabindex="0"
    title="${esc(capabilityTooltip(entity))}">
      <div class="cap-card-head">
        <span class="cap-type cap-type-${esc(entity.type)}">${esc(capTypeLabel(entity.type))}</span>
        ${capRateable(entity) ? `<span class="cap-rating-name">${Number(entity.rating) || 0} · ${esc(capRatingLabel(entity.rating))}</span>` : ''}
      </div>
      <div class="cap-card-name">${esc(capName(entity) || 'Unnamed')}</div>
      ${showCanonical ? `<div class="cap-canonical">${esc(canonical)}</div>` : ''}
      ${showAliases ? `<div class="cap-aliases">${aliases.map(alias => `<span>${esc(alias)}</span>`).join('')}</div>` : ''}
      ${relationshipBadges(entity, detailLevel)}
    </article>`;
}

function capabilityCard(entity, detailLevel = 3, selected = false) {
  if (capabilityView === 'set' && capabilitySetSelection) {
    selected = capabilitySetSelection.has(String(entity.id));
  }
  if (capabilityMatchMode || capabilityDisplayMode === 'compact') {
    return compactCapabilityPill(entity, selected);
  }
  return detailedCapabilityCard(entity, detailLevel, selected);
}

function providerGroupFor(entity) {
  const byId = capById();
  const rel = (capabilityState.relationships || []).find(item => item.source_id === entity.id && item.type === 'provided_by');
  return rel ? capName(byId[rel.target_id]) : '';
}
function alphaBucket(name) {
  const letter = (name || '#').trim().charAt(0).toUpperCase();
  if (letter >= 'A' && letter <= 'F') return 'A–F';
  if (letter >= 'G' && letter <= 'L') return 'G–L';
  if (letter >= 'M' && letter <= 'R') return 'M–R';
  if (letter >= 'S' && letter <= 'Z') return 'S–Z';
  return 'Other';
}
function hierarchySections(items, sectionLevel) {
  const section = (title, filter) => ({ title, items: items.filter(filter) });
  if (sectionLevel <= 1) return [section('Capabilities', () => true)];
  if (sectionLevel === 2) return [section('Competencies', e => e.type === 'competency'), section('Technical Capabilities', e => e.type !== 'competency')].filter(s => s.items.length);
  const result = [section('Competencies', e => e.type === 'competency'), section('Technologies', e => e.type === 'technology'), section('Products / Tools', e => e.type === 'product' || e.type === 'tool')];
  if (sectionLevel >= 4) {
    result.splice(2, 1, section('Products / Services', e => e.type === 'product'), section('Tools / Legacy', e => e.type === 'tool'));
  }
  return result.filter(s => s.items.length);
}
function renderEntityCollection(items, entityLevel) {
  const ordered = [...items].sort((a, b) => Number(b.rating || 0) - Number(a.rating || 0) || capName(a).localeCompare(capName(b)));
  if (entityLevel >= 3) return `<div class="${capabilityMatchMode || capabilityDisplayMode === 'compact' ? 'cap-pills' : 'cap-grid'}">${ordered.map(entity => capabilityCard(entity, entityLevel)).join('')}</div>`;
  const providerGroups = new Map();
  if (entityLevel === 1) {
    ordered.forEach(entity => { const provider = providerGroupFor(entity); if (provider) { if (!providerGroups.has(provider)) providerGroups.set(provider, []); providerGroups.get(provider).push(entity) } });
  }
  const groupedIds = new Set([...providerGroups.values()].flat().map(entity => entity.id));
  const groups = [];
  for (const [provider, entities] of providerGroups) groups.push([provider, entities]);
  const leftovers = ordered.filter(entity => !groupedIds.has(entity.id));
  const alpha = new Map(); leftovers.forEach(entity => { const bucket = alphaBucket(capName(entity)); if (!alpha.has(bucket)) alpha.set(bucket, []); alpha.get(bucket).push(entity) });
  for (const [bucket, entities] of alpha) groups.push([bucket, entities]);
  return groups.map(([name, entities]) => `<details class="cap-group" open><summary>${esc(name)} <span>${entities.length}</span></summary><div class="${capabilityMatchMode || capabilityDisplayMode === 'compact' ? 'cap-pills' : 'cap-grid'}">${entities.map(entity => capabilityCard(entity, entityLevel)).join('')}</div></details>`).join('');
}

function capabilityProjection() {
  const projection = capabilityState.view_preferences?.hierarchy?.projection;
  if (!projection) return null;
  if (Number(projection.version) >= 3 && projection.tree) return projection;
  if (Array.isArray(projection.sections)) return projection;
  return null;
}

function projectionTreeNode(raw, allowed, byId) {
  if (!raw || typeof raw !== 'object') return null;
  const direct = (raw.entity_ids || [])
    .map(id => byId[String(id)])
    .filter(entity => entity && allowed.has(String(entity.id)));
  const children = (raw.children || [])
    .map(child => projectionTreeNode(child, allowed, byId))
    .filter(Boolean);
  const count = direct.length + children.reduce((total, child) => total + child.count, 0);
  if (!count) return null;
  return {
    name: String(raw.name || 'Capabilities'),
    direct,
    children,
    count,
  };
}

function projectionTreeEntities(node) {
  if (!node) return [];
  return [
    ...node.direct,
    ...node.children.flatMap(child => projectionTreeEntities(child)),
  ];
}

function projectionLeafCount(node) {
  if (!node) return 0;
  if (!node.children.length) return node.count ? 1 : 0;
  return node.children.reduce((total, child) => total + projectionLeafCount(child), 0);
}

function sectionTargetForLevel(root, level) {
  const leaves = Math.max(1, projectionLeafCount(root));
  const maxSections = Math.max(1, Math.min(12, leaves));
  if (level <= 1) return 1;
  if (level >= 5) return maxSections;
  const ratio = (level - 1) / 4;
  return Math.max(1, Math.round(1 + (maxSections - 1) * ratio));
}

function sectionFrontier(root, level) {
  if (!root) return [];
  if (level <= 1) return [root];

  const target = sectionTargetForLevel(root, level);
  let frontier = [root];

  while (frontier.length < target) {
    const candidates = [];
    frontier.forEach((node, index) => {
      if (!node.children.length) return;
      const nextCount = frontier.length - 1 + node.children.length;
      const distance = Math.abs(target - nextCount);
      candidates.push({
        index,
        node,
        nextCount,
        distance,
        gain: node.children.length - 1,
      });
    });
    if (!candidates.length) break;

    candidates.sort((a, b) => {
      const aOver = a.nextCount > target ? 1 : 0;
      const bOver = b.nextCount > target ? 1 : 0;
      if (a.distance !== b.distance) return a.distance - b.distance;
      if (aOver !== bOver) return aOver - bOver;
      if (a.node.count !== b.node.count) return b.node.count - a.node.count;
      return b.gain - a.gain;
    });

    const best = candidates[0];
    const currentDistance = Math.abs(target - frontier.length);
    if (best.distance > currentDistance) break;

    frontier = [
      ...frontier.slice(0, best.index),
      ...best.node.children,
      ...frontier.slice(best.index + 1),
    ];

    if (frontier.length === target) break;
  }

  return frontier;
}

function capabilityCollection(items, entityLevel) {
  const ordered = [...items]
    .sort((a, b) => Number(b.rating || 0) - Number(a.rating || 0) || capName(a).localeCompare(capName(b)));
  if (!ordered.length) return '';
  return `<div class="${capabilityMatchMode || capabilityDisplayMode === 'compact' ? 'cap-pills' : 'cap-grid'}">${ordered.map(entity => capabilityCard(entity, entityLevel)).join('')}</div>`;
}

function renderTreeGroups(node, detailDepth, entityLevel, depth = 0) {
  if (detailDepth <= 0 || !node.children.length) {
    return capabilityCollection(projectionTreeEntities(node), entityLevel);
  }

  const loose = [...node.direct];
  const groups = [];

  for (const child of node.children) {
    const childEntities = projectionTreeEntities(child);

    // A one-entity category costs more screen space than it adds navigation
    // value, so suppress its heading without changing the taxonomy itself.
    if (childEntities.length <= 1) {
      loose.push(...childEntities);
      continue;
    }

    const inner = detailDepth <= 1
      ? capabilityCollection(childEntities, entityLevel)
      : renderTreeGroups(child, detailDepth - 1, entityLevel, depth + 1);

    groups.push(
      `<div class="cap-projection-group" style="margin-left:${Math.min(depth, 3) * 10}px">
        <div class="cap-projection-group-head">
          <h3>${esc(child.name)}</h3><span>${child.count}</span>
        </div>
        ${inner}
      </div>`
    );
  }

  return `${capabilityCollection(loose, entityLevel)}${groups.join('')}`;
}

function renderTreeProjection(items, sectionLevel, entityLevel, projection) {
  const allowed = new Set(items.map(entity => String(entity.id)));
  const root = projectionTreeNode(projection.tree, allowed, capById());
  if (!root) return '';

  const sections = sectionFrontier(root, sectionLevel);
  if (!sections.length) return '';

  // Entity granularity is the amount of category depth exposed *inside*
  // whichever nodes Section Granularity selected as visible sections.
  const detailDepth = Math.max(0, Number(entityLevel) - 1);

  return sections.map(section => {
    const body = renderTreeGroups(
      section,
      detailDepth,
      entityLevel,
      0
    );
    return `<section class="cap-section">
      <div class="cap-section-head">
        <h2>${esc(section.name)}</h2><span>${section.count}</span>
      </div>
      ${body}
    </section>`;
  }).join('');
}

function renderV2ProjectedHierarchy(items, sectionLevel, entityLevel, projection) {
  const allowed = new Set(items.map(entity => String(entity.id)));
  const byId = capById();
  const displayClass = capabilityMatchMode || capabilityDisplayMode === 'compact' ? 'cap-pills' : 'cap-grid';

  if (sectionLevel <= 1) {
    return `<section class="cap-section"><div class="cap-section-head"><h2>Capabilities</h2><span>${items.length}</span></div><div class="${displayClass}">${items.sort((a, b) => Number(b.rating || 0) - Number(a.rating || 0) || capName(a).localeCompare(capName(b))).map(entity => capabilityCard(entity, entityLevel)).join('')}</div></section>`;
  }

  const sections = [];
  for (const section of projection.sections) {
    const direct = (section.entity_ids || []).map(id => byId[String(id)]).filter(entity => entity && allowed.has(String(entity.id)));
    const groups = (section.groups || []).map(group => ({
      name: group.name,
      items: (group.entity_ids || []).map(id => byId[String(id)]).filter(entity => entity && allowed.has(String(entity.id))),
    })).filter(group => group.items.length);
    const count = direct.length + groups.reduce((total, group) => total + group.items.length, 0);
    if (count) sections.push({ name: section.name, direct, groups, count });
  }
  if (!sections.length) return '';

  return sections.map(section => {
    if (sectionLevel === 2) {
      const flattened = [...section.direct, ...section.groups.flatMap(group => group.items)];
      return `<section class="cap-section"><div class="cap-section-head"><h2>${esc(section.name)}</h2><span>${flattened.length}</span></div><div class="${displayClass}">${flattened.map(entity => capabilityCard(entity, entityLevel)).join('')}</div></section>`;
    }
    const direct = section.direct.length ? `<div class="${displayClass}">${section.direct.map(entity => capabilityCard(entity, entityLevel)).join('')}</div>` : '';
    const groups = section.groups.map(group => `<div class="cap-projection-group"><div class="cap-projection-group-head"><h3>${esc(group.name)}</h3><span>${group.items.length}</span></div><div class="${displayClass}">${group.items.map(entity => capabilityCard(entity, entityLevel)).join('')}</div></div>`).join('');
    return `<section class="cap-section"><div class="cap-section-head"><h2>${esc(section.name)}</h2><span>${section.count}</span></div>${direct}${groups}</section>`;
  }).join('');
}

function renderProjectedHierarchy(items, sectionLevel, entityLevel) {
  const projection = capabilityProjection();
  if (!projection) return '';
  if (Number(projection.version) >= 3 && projection.tree) {
    return renderTreeProjection(items, sectionLevel, entityLevel, projection);
  }
  if (Array.isArray(projection.sections)) {
    return renderV2ProjectedHierarchy(items, sectionLevel, entityLevel, projection);
  }
  return '';
}

function renderHierarchyView() {
  const sectionLevel = Number($('capSectionGranularity').value || 3);
  const entityLevel = Number($('capEntityGranularity').value || 3);
  const items = filteredCapabilities(false);
  const projected = renderProjectedHierarchy(items, sectionLevel, entityLevel);
  if (projected) return projected;
  const sections = hierarchySections(items, sectionLevel);
  if (!sections.length) return '<div class="empty">No capabilities yet. Use + Add → Smart Add to build the model from a short list.</div>';
  return sections.map(section => `<section class="cap-section"><div class="cap-section-head"><h2>${esc(section.title)}</h2><span>${section.items.length}</span></div>${renderEntityCollection(section.items, entityLevel)}</section>`).join('');
}

function renderRatingView() {
  const items = filteredCapabilities(false);
  return [5, 4, 3, 2, 1, 0].map(rating => {
    const bucket = items.filter(entity => Number(entity.rating) === rating);
    if (!bucket.length) return '';
    return `<section class="cap-section"><div class="cap-section-head"><h2>${rating} · ${esc(capRatingLabel(rating))}</h2><span>${bucket.length}</span></div><div class="${capabilityMatchMode || capabilityDisplayMode === 'compact' ? 'cap-pills' : 'cap-grid'}">${bucket.sort((a, b) => capName(a).localeCompare(capName(b))).map(entity => capabilityCard(entity, 4)).join('')}</div></section>`;
  }).join('') || '<div class="empty">No capabilities match the current filters.</div>';
}

function renderGapView() {
  const gaps = filteredCapabilities(false).filter(entity => entity.match_enabled && Number(entity.rating) <= 2).sort((a, b) => Number(a.rating) - Number(b.rating) || capName(a).localeCompare(capName(b)));
  if (!gaps.length) return '<div class="empty">No capabilities currently need assessment or development. This view shows match-enabled capabilities rated 0–2.</div>';
  return [0, 1, 2].map(rating => {
    const bucket = gaps.filter(entity => Number(entity.rating) === rating); if (!bucket.length) return '';
    return `<section class="cap-section"><div class="cap-section-head"><h2>${rating} · ${esc(capRatingLabel(rating))}</h2><span>${bucket.length}</span></div><div class="${capabilityMatchMode || capabilityDisplayMode === 'compact' ? 'cap-pills' : 'cap-grid'}">${bucket.map(entity => capabilityCard(entity, 5)).join('')}</div></section>`;
  }).join('');
}

function setMembershipSet(capabilitySet) { return new Set((capabilitySet?.capability_ids || []).map(String)) }
function setDisplayName(capabilitySet) { return capabilitySet?.system ? 'All Capabilities' : String(capabilitySet?.name || 'Capability Set') }
function renderSetView() {
  const sets = capabilityState.sets || [];
  if (!sets.some(capabilitySet => capabilitySet.id === capabilitySetId)) capabilitySetId = sets[0]?.id || '__all__';
  const capabilitySet = sets.find(item => item.id === capabilitySetId) || sets[0];
  if (!capabilitySet) return '<div class="empty">No capability sets are available.</div>';

  const chosen = setMembershipSet(capabilitySet);
  capabilitySetSelection = chosen;
  const items = filteredCapabilities(false).sort((a, b) => Number(b.rating || 0) - Number(a.rating || 0) || capName(a).localeCompare(capName(b)));
  const sectionLevel = Number($('capSectionGranularity').value || 3);
  const entityLevel = Number($('capEntityGranularity').value || 3);
  const projected = renderProjectedHierarchy(items, sectionLevel, entityLevel);
  const grouped = projected || hierarchySections(items, sectionLevel).map(section => `<section class="cap-section"><div class="cap-section-head"><h2>${esc(section.title)}</h2><span>${section.items.length}</span></div>${renderEntityCollection(section.items, entityLevel)}</section>`).join('');
  const customSetCount = sets.filter(item => !item.system).length;
  const setHelp = capabilitySet.system
    ? 'This is the global paste-iterator selection. Click capabilities to include or exclude them from the Skills iterator.'
    : 'This set is an optional iterator lens. Click capabilities to change membership; the same hierarchy grouping is reused here to keep large capability models easy to scan.';

  return `<div class="cap-set-layout">
    <aside class="cap-set-list">
      <div class="cap-set-list-head"><h3>Capability Sets</h3><button class="btn" id="capNewSet">+ Set</button></div>
      ${sets.map(item => `<button class="cap-set-button ${item.id === capabilitySet.id ? 'active' : ''}" data-cap-set="${esc(item.id)}"><span>${esc(setDisplayName(item))}</span><b>${(item.capability_ids || []).length}</b></button>`).join('')}
      ${customSetCount === 0 ? '<div class="cap-set-empty-note">No custom capability sets yet. All Capabilities remains the default iterator.</div>' : ''}
    </aside>
    <section class="cap-set-members">
      <div class="cap-set-head">
        <div><div class="cap-eyebrow">${capabilitySet.system ? 'Global iterator' : 'Set membership'}</div><h2>${esc(setDisplayName(capabilitySet))}</h2><p class="muted">${esc(setHelp)}</p></div>
        ${capabilitySet.system ? '' : '<button class="btn" id="capEditSet">Edit set</button>'}
      </div>
      <div class="cap-set-hierarchy">${grouped || '<div class="empty">No capabilities match the current filters.</div>'}</div>
    </section>
  </div>`;
}

function ratingGuideHtml() {
  return capRatingGuidance().map(item => `<div class="cap-rating-guide-row rating-${Number(item.value)}"><span class="cap-rating-number">${Number(item.value)}</span><span class="cap-rating-label">${esc(item.label)}</span><span class="cap-rating-description">${esc(item.description)}</span></div>`).join('');
}

function renderCapabilityRatingGuide() {
  const html = ratingGuideHtml();
  if ($('capRatingGuide')) $('capRatingGuide').innerHTML = html;
  if ($('capRatingPopover')) $('capRatingPopover').innerHTML = html;
  if ($('capEntityRating')) {
    const current = $('capEntityRating').value || '0';
    $('capEntityRating').innerHTML = capRatingGuidance().map(item => `<option value="${Number(item.value)}">${Number(item.value)} · ${esc(item.label)}</option>`).join('');
    $('capEntityRating').value = current;
  }
}

function capabilityUseGuide() {
  if ($('capSetDialog')?.open) {
    return {
      title: 'Capability Set',
      html: '<p>A capability set is a named subset of the capability model. It has no rating, aliases, or matching flags of its own.</p><p>Rename the set here; edit membership in Capability Set View.</p>',
    };
  }
  if ($('capEntityDialog')?.open) {
    const type = $('capEntityType')?.value || 'technology';
    const guides = {
      competency: ['Competency', 'Something you do, design, own, or practice professionally. Competencies are rated and can participate in matching and the paste iterator.'],
      technology: ['Technology', 'A platform, language, protocol, standard, or technical domain you know or use. Technologies are rated and can participate in matching and the paste iterator.'],
      product: ['Product / Tool', 'A specific named product, managed service, application, or tool. Products are rated and can participate in matching and the paste iterator.'],
      tool: ['Product / Tool', 'Legacy tool entities behave like products and remain rateable.'],
    };
    const [title, copy] = guides[type] || guides.technology;
    return { title, html: `<p>${esc(copy)}</p><p><b>Display name</b> is user-facing. <b>Canonical name</b> and aliases improve matching while stable IDs preserve identity.</p>` };
  }
  const guides = {
    hierarchy: { title: 'Hierarchy view', html: '<p>The taxonomy is a visual projection; it does not change entity identity or relationships.</p><ul><li>Hover a capability and press <b>0–5</b> to rate it.</li><li>Double-click a capability to edit it.</li><li>Section Granularity changes visible sections.</li><li>Entity Granularity exposes more or less taxonomy depth inside those sections.</li><li>Match Selection changes job-matching inclusion.</li></ul>' },
    set: { title: 'Capability Set view', html: '<p>Capability Sets reuse the same hierarchy projection so large lists stay organized.</p><p>Select a set on the left, then click capability pills/cards to include or exclude them. <b>All Capabilities</b> controls the global Skills iterator.</p>' },
    rating: { title: 'Rating view', html: '<p>Ratings describe your proficiency, not the importance of a capability. Hover a capability and press <b>0–5</b> to change its rating.</p><p><b>0 · Unrated</b> means no proficiency level has been assigned; it does not mean no knowledge.</p>' },
    gap: { title: 'Learning Gap view', html: '<p>This view surfaces match-enabled capabilities that need assessment or development.</p><p><b>0</b> means unassessed. Ratings <b>1–2</b> indicate limited proficiency and are the actual development-gap ratings.</p>' },
  };
  return guides[capabilityView] || guides.hierarchy;
}

function renderCapabilityReference() {
  const shell = $('capShell'); if (!shell) return;
  shell.dataset.leftPane = capabilityLeftPaneMode;
  shell.dataset.rightPane = capabilityRightPaneMode;
  const labels = { fixed: 'Fixed', auto: 'Auto', off: 'Off' };
  $('capLeftModeButton').textContent = `${labels[capabilityLeftPaneMode]} ▾`;
  $('capRightModeButton').textContent = `${labels[capabilityRightPaneMode]} ▾`;
  $('capRestoreLeftPane').hidden = capabilityLeftPaneMode !== 'off';
  $('capRestoreRightPane').hidden = capabilityRightPaneMode !== 'off';
  $('capUseGuideToggle').checked = capabilityShowUseGuide;
  $('capUseGuideSection').hidden = !capabilityShowUseGuide;
  document.querySelectorAll('[data-pane-mode]').forEach(button => {
    const current = button.dataset.paneSide === 'left' ? capabilityLeftPaneMode : capabilityRightPaneMode;
    button.classList.toggle('active', button.dataset.paneMode === current);
  });
  const guide = capabilityUseGuide();
  $('capUseGuideTitle').textContent = guide.title;
  $('capUseGuideContent').innerHTML = guide.html;
}

function closePaneMenus() {
  for (const id of ['capLeftModeMenu', 'capRightModeMenu']) { const menu = $(id); if (menu) menu.hidden = true }
  for (const id of ['capLeftModeButton', 'capRightModeButton']) { const button = $(id); if (button) button.setAttribute('aria-expanded', 'false') }
}
function togglePaneMenu(side, event) {
  event?.stopPropagation();
  const menu = $(side === 'left' ? 'capLeftModeMenu' : 'capRightModeMenu');
  const button = $(side === 'left' ? 'capLeftModeButton' : 'capRightModeButton');
  const next = menu.hidden; closePaneMenus(); menu.hidden = !next; button.setAttribute('aria-expanded', String(next));
}
async function setCapabilityPaneMode(side, mode) {
  if (!['fixed', 'auto', 'off'].includes(mode)) return;
  if (side === 'left') capabilityLeftPaneMode = mode; else capabilityRightPaneMode = mode;
  closePaneMenus(); renderCapabilityReference(); await saveCapabilityViewPreferences();
}

function renderCapabilities() {
  renderCapabilityStats();
  const setView = capabilityView === 'set';
  if (!setView) capabilitySetSelection = null;
  if (setView) capabilityMatchMode = false;
  $('capabilitiesPage').classList.toggle('cap-match-mode', capabilityMatchMode);
  $('capCompactMode').classList.toggle('active', capabilityDisplayMode === 'compact');
  $('capDetailedMode').classList.toggle('active', capabilityDisplayMode === 'detailed');
  $('capMatchMode').classList.toggle('active', capabilityMatchMode);
  $('capMatchMode').setAttribute('aria-pressed', String(capabilityMatchMode));
  $('capSelectionModes').hidden = setView;
  document.querySelectorAll('[data-cap-view]').forEach(button => button.classList.toggle('active', button.dataset.capView === capabilityView));
  $('capHierarchyControls').hidden = !['hierarchy', 'set'].includes(capabilityView);
  const meta = {
    hierarchy: ['Projection', 'Hierarchy View', 'Organize the same capability model at different levels of visual granularity.'],
    set: ['Semantic view', 'Capability Set View', 'Use the same hierarchy grouping to manage capability-set membership.'],
    rating: ['Assessment view', 'Rating View', 'Compare proficiency across the same underlying capability entities.'],
    gap: ['Development view', 'Learning Gap View', 'Match-enabled capabilities needing assessment or development. Rating 0 is unrated, not evidence of no knowledge.'],
  }[capabilityView];
  $('capViewEyebrow').textContent = meta[0]; $('capViewTitle').textContent = meta[1]; $('capViewHint').textContent = meta[2];
  $('capContent').innerHTML = capabilityView === 'set' ? renderSetView() : capabilityView === 'rating' ? renderRatingView() : capabilityView === 'gap' ? renderGapView() : renderHierarchyView();
  renderCapabilityReference();
  wireCapabilityContent();
}

function wireCapabilityContent() {
  document.querySelectorAll('[data-cap-card]').forEach(card => {
    card.onmouseenter = () => capabilityHoveredId = card.dataset.capCard;
    card.onmouseleave = () => { if (capabilityHoveredId === card.dataset.capCard) capabilityHoveredId = '' };
    card.onclick = async event => {
      if (capabilityView === 'set') {
        event.preventDefault();
        await toggleSetMembership(card.dataset.capCard);
        return;
      }
      if (!capabilityMatchMode) return;
      const entity = capById()[card.dataset.capCard];
      if (!entity || !capRateable(entity)) return;
      event.preventDefault();
      await mutateCapability('/api/capabilities/match', {
        entity_id: entity.id,
        enabled: !entity.match_enabled,
      });
    };
    card.ondblclick = event => {
      if (capabilityMatchMode || capabilityView === 'set') return;
      event.preventDefault();
      openCapabilityDialog(card.dataset.capCard);
    };
  });
  document.querySelectorAll('[data-cap-set]').forEach(button => {
    button.onclick = () => {
      capabilitySetId = button.dataset.capSet;
      renderCapabilities();
    };
    button.ondblclick = event => {
      event.preventDefault();
      if (button.dataset.capSet !== '__all__') openCapabilitySetDialog(button.dataset.capSet);
    };
  });
  if ($('capNewSet')) $('capNewSet').onclick = () => openCapabilitySetDialog();
  if ($('capEditSet')) $('capEditSet').onclick = () => openCapabilitySetDialog(capabilitySetId);
}

async function mutateCapability(path, body) {
  try { const result = await capabilityApi(path, body); capabilityState = result.capabilities || capabilityState; renderCapabilities() } catch (error) { toast(error.message) }
}
async function setCapabilityRating(entityId, rating) { await mutateCapability('/api/capabilities/rating', { entity_id: entityId, rating }) }

async function toggleSetMembership(entityId) {
  const capabilitySet = (capabilityState.sets || []).find(item => item.id === capabilitySetId); if (!capabilitySet) return;
  const chosen = setMembershipSet(capabilitySet); chosen.has(String(entityId)) ? chosen.delete(String(entityId)) : chosen.add(String(entityId));
  try {
    if (capabilitySet.system) {
      const entity = capById()[entityId];
      await mutateCapability('/api/capabilities/iterator', { entity_id: entityId, enabled: !entity.iterator_enabled });
      return;
    }
    const result = await capabilityApi('/api/capabilities/sets/save', {
      set_id: capabilitySet.id,
      name: capabilitySet.name,
      capability_ids: [...chosen],
    });
    capabilityState = result.capabilities || capabilityState;
    renderCapabilities();
  } catch (error) { toast(error.message) }
}

function updateCapabilityGranularityLabels() {
  $('capSectionGranularityLabel').textContent = capSectionGranularityLabel($('capSectionGranularity').value);
  $('capEntityGranularityLabel').textContent = capEntityGranularityLabel($('capEntityGranularity').value);
}
function queueCapabilityViewSave() {
  updateCapabilityGranularityLabels(); renderCapabilities(); clearTimeout(capabilitySavingViewTimer); capabilitySavingViewTimer = setTimeout(saveCapabilityViewPreferences, 180);
}
async function saveCapabilityViewPreferences() {
  const current = structuredClone(capabilityState.view_preferences || {});
  current.hierarchy ??= {};
  current.hierarchy.section_granularity = Number($('capSectionGranularity').value);
  current.hierarchy.entity_granularity = Number($('capEntityGranularity').value);
  current.hierarchy.display_mode = capabilityDisplayMode;
  current.layout = {
    ...(current.layout || {}),
    left_pane: capabilityLeftPaneMode,
    right_pane: capabilityRightPaneMode,
    show_use_guide: capabilityShowUseGuide,
  };
  try {
    const result = await capabilityApi('/api/capabilities/view-preferences', { view_preferences: current });
    capabilityState = result.capabilities || capabilityState;
  } catch (error) {
    toast(error.message);
  }
}

function openCapabilityDialog(entityId = '') {
  const entity = entityId ? capById()[entityId] : null;
  if (entity && !capRateable(entity)) return;
  $('capEntityId').value = entity?.id || '';
  $('capEntityType').value = entity?.type || 'technology';
  $('capEntityDisplayName').value = capName(entity) || '';
  $('capEntityCanonicalName').value = entity?.canonical_name || '';
  $('capEntityAliases').value = (entity?.aliases || []).join(', ');
  $('capEntityRating').value = String(entity?.rating ?? 0);
  $('capEntityMatch').checked = entity?.match_enabled ?? true;
  $('capEntityIterator').checked = entity?.iterator_enabled ?? true;
  $('capDeleteEntity').hidden = !entity;
  renderCapabilityRatingGuide();
  syncCapabilityDialogType();
  $('capEntityDialog').showModal();
  renderCapabilityReference();
  setTimeout(() => $('capEntityDisplayName').focus(), 0);
}
function capabilityTypeHelp(type) {
  return {
    competency: 'A competency is something you do, design, own, or practice professionally. It is rated and can be used for matching and the paste iterator.',
    technology: 'A technology is a platform, language, protocol, standard, or technical domain you know or use. It is rated and can be used for matching and the paste iterator.',
    product: 'A product/tool is a specific named product, managed service, application, or tool. It is rated and can be used for matching and the paste iterator.',
    tool: 'Legacy tool entities behave like products and remain rateable.',
  }[type] || '';
}
function syncCapabilityDialogType() {
  const type = $('capEntityType').value;
  const editing = Boolean($('capEntityId').value.trim());
  $('capEntityDialogTitle').textContent = editing ? 'Edit capability' : 'Add capability';
  $('capEntityHelp').textContent = capabilityTypeHelp(type) + ' Renaming changes the display name; stable IDs preserve identity across views and relationships.';
  $('capRatingPopover').hidden = true;
  $('capRatingHelp').setAttribute('aria-expanded', 'false');
  renderCapabilityReference();
}
function closeCapabilityDialog() {
  $('capRatingPopover').hidden = true;
  $('capRatingHelp').setAttribute('aria-expanded', 'false');
  if ($('capEntityDialog').open) $('capEntityDialog').close();
  renderCapabilityReference();
}

async function saveCapabilityEntity() {
  const id = $('capEntityId').value.trim(), type = $('capEntityType').value, display = $('capEntityDisplayName').value.trim(); if (!display) { toast('Display name is required'); return }
  const entity = {};
  if (id) entity.id = id;
  entity.type = type;
  entity.display_name = display;
  entity.canonical_name = $('capEntityCanonicalName').value.trim() || display;
  entity.aliases = $('capEntityAliases').value.split(',').map(item => item.trim()).filter(Boolean);
  entity.rating = Number($('capEntityRating').value);
  entity.match_enabled = $('capEntityMatch').checked;
  entity.iterator_enabled = $('capEntityIterator').checked;
  try {
    const result = await capabilityApi('/api/capabilities/entities/upsert', { entity });
    capabilityState = result.capabilities || capabilityState;
    closeCapabilityDialog();
    renderCapabilities();
  } catch (error) { toast(error.message) }
}
async function deleteCapabilityEntity() {
  const entityId = $('capEntityId').value.trim(); if (!entityId) return; const entity = capById()[entityId]; if (!confirm(`Delete ${capName(entity)}?`)) return;
  try { const result = await capabilityApi('/api/capabilities/entities/delete', { entity_id: entityId }); capabilityState = result.capabilities; closeCapabilityDialog(); renderCapabilities() } catch (error) { toast(error.message) }
}

function openCapabilitySetDialog(setId = '') {
  const capabilitySet = (capabilityState.sets || []).find(item => item.id === setId && !item.system) || null;
  $('capSetId').value = capabilitySet?.id || '';
  $('capSetName').value = capabilitySet?.name || '';
  $('capSetDocument').checked = capabilitySet?.document_enabled ?? true;
  $('capSetPaste').checked = capabilitySet?.paste_enabled ?? true;
  $('capSetDialogTitle').textContent = capabilitySet ? 'Edit capability set' : 'Add capability set';
  $('capDeleteSet').hidden = !capabilitySet;
  $('capSetDialog').showModal();
  renderCapabilityReference();
  setTimeout(() => $('capSetName').focus(), 0);
}
function closeCapabilitySetDialog() {
  if ($('capSetDialog').open) $('capSetDialog').close();
  renderCapabilityReference();
}
async function saveCapabilitySet() {
  const setId = $('capSetId').value.trim();
  const name = $('capSetName').value.trim();
  if (!name) { toast('Capability set name is required'); return }
  const current = (capabilityState.sets || []).find(item => item.id === setId);
  try {
    const result = await capabilityApi('/api/capabilities/sets/save', {
      set_id: setId,
      name,
      capability_ids: [...(current?.capability_ids || [])],
      document_enabled: $('capSetDocument').checked,
      paste_enabled: $('capSetPaste').checked,
    });
    capabilityState = result.capabilities || capabilityState;
    capabilitySetId = result.set_id || setId || capabilitySetId;
    capabilityView = 'set';
    closeCapabilitySetDialog();
    renderCapabilities();
  } catch (error) { toast(error.message) }
}
async function deleteCapabilitySet() {
  const setId = $('capSetId').value.trim();
  const capabilitySet = (capabilityState.sets || []).find(item => item.id === setId);
  if (!capabilitySet || capabilitySet.system || !confirm(`Delete capability set ${capabilitySet.name}?`)) return;
  try {
    const result = await capabilityApi('/api/capabilities/sets/delete', { set_id: setId });
    capabilityState = result.capabilities || capabilityState;
    capabilitySetId = '__all__';
    closeCapabilitySetDialog();
    renderCapabilities();
  } catch (error) { toast(error.message) }
}

function parseSmartAddNames() {
  const raw = $('capSmartInput').value || '';
  const choice = $('capSmartDelimiter').value;
  let delimiter = choice;
  if (choice === 'auto') {
    if (raw.includes('\n')) delimiter = 'newline';
    else if (raw.includes('|')) delimiter = '|';
    else if (raw.includes(';')) delimiter = ';';
    else delimiter = ',';
  }
  const parts = delimiter === 'newline' ? raw.split(/\r?\n/) : raw.split(delimiter);
  const seen = new Set(), names = [];
  for (const value of parts) {
    const name = value.trim();
    const key = name.toLocaleLowerCase();
    if (name && !seen.has(key)) { seen.add(key); names.push(name) }
  }
  $('capSmartDetected').textContent = String(names.length);
  return names;
}

function smartAddCurrentDataset() {
  return {
    entities: (capabilityState.entities || []).filter(entity => entity.type !== 'set').map(entity => ({
      id: String(entity.id),
      type: entity.type,
      canonical_name: String(entity.canonical_name || ''),
      display_name: String(entity.display_name || entity.canonical_name || ''),
      aliases: [...(entity.aliases || [])],
    })),
    relationships: (capabilityState.relationships || []).filter(rel => rel.type !== 'relevant_to').map(rel => ({
      source_id: String(rel.source_id), type: String(rel.type), target_id: String(rel.target_id),
    })),
    hierarchy_projection: capabilityProjection(),
  };
}

function buildSmartAddPrompt(names) {
  const current = smartAddCurrentDataset();
  return `You are classifying and organizing capabilities for JAW (Job Application Workbench). This prompt is self-contained. Do not assume any prior conversation, user profile, resume, work history, memories, personalization, profession, or knowledge of JAW beyond what is written here.

GOAL
Add the NEW INPUT NAMES to the existing capability knowledge graph, enrich existing entities only when useful, add conservative semantic relationships, and return one COMPLETE nested taxonomy tree for the final dataset.

JAW IS PROFESSION-NEUTRAL
The user may work in IT, law, healthcare, finance, administration, skilled trades, sales, education, or another field.
Do not hard-code an IT-style taxonomy unless the supplied capabilities actually justify it.
Infer the professional organization only from the supplied capability names and current dataset.

ENTITY TYPES
Use exactly one of these storage types:
- competency: something a person can DO, DESIGN, OWN, LEAD, PRACTICE, or APPLY professionally. This includes architecture/design disciplines even when technical. Examples: Cloud Architecture, Solution Architecture, Incident Response, Legal Research, Reconciliation, Patient Triage, Contract Administration.
- technology: a technical platform, language, protocol, standard, or technical knowledge domain — not a professional practice or architecture discipline. Examples: Kubernetes, Python, TCP/IP, SQL, AWS.
- product: a specific product, managed service, implementation, or tool. Examples across fields: Terraform, Microsoft Excel, Westlaw, QuickBooks, Salesforce.

- Do NOT create capability-set entities in Smart Add v3.

ENTITY TYPE DECISION RULE
Ask "Is this primarily something a person DOES/OWNS/DESIGNS, or something they KNOW/USE?"
- DOES / OWNS / DESIGNS / PRACTICES → competency
- KNOWS / USES as a platform, language, protocol, standard, or domain → technology
- specific named product/service/tool → product
Examples:
- Cloud Architecture → competency
- Site Reliability Engineering → competency
- Kubernetes → technology
- AWS → technology
- Terraform → product
- Prometheus → product

SEMANTIC RELATIONSHIPS
Smart Add v3 may create ONLY these relationship types:
- uses: source directly uses or depends on target.
- based_on: source is built on, implements, or extends target.
- provided_by: source product/service is provided by target platform/provider.
- related_to: meaningful semantic adjacency when none of the stronger relationships applies.

IMPORTANT:
- Do NOT generate relevant_to. JAW reserves relevant_to for capability → capability-set membership and manages it separately.
- Never create a relationship from an entity to itself.
- Use relationships conservatively. Do not add weak links merely to make the graph dense.
- When an existing provider/platform entity is already present and a provided_by relationship is unambiguous, include it.
- Taxonomy membership is NOT a semantic relationship.

USER-OWNED DATA — NEVER OUTPUT, INFER, OR CHANGE
- ratings
- match-enabled state
- iterator-enabled state
Existing display_name values are also user-owned. Do not rename an existing display_name.
You may improve an existing entity's type, canonical_name, or aliases when clearly justified.
Never delete an existing entity.

ALIASES
- Aliases must be recognized alternate names, acronyms, or spellings for the SAME entity.
- Never use descriptions, feature names, resource types, marketing phrases, or merely related concepts as aliases.
- Do not include an alias equal to canonical_name.
- Do not include an alias equal to display_name.
- Do not repeat the same alias with different capitalization.
- If canonical_name is the expanded name and display_name is the acronym, aliases may be empty. Example: canonical_name "Amazon Web Services", display_name "AWS", aliases [].

ANTI-FRAGMENTATION RULES
- Prefer one reusable entity over several near-duplicates.
- Add a separate entity only when independently useful for job matching, rating, learning, semantic reasoning, or navigation.
- Treat acronyms and alternate spellings as aliases when they refer to the same thing.
- If a NEW INPUT NAME duplicates an existing canonical name, display name, or alias, do not create a second entity.
- Use common industry naming for canonical_name. Keep display names concise.

NESTED TAXONOMY TREE
The hierarchy is a VIEW PROJECTION only. It does not change entity identity or semantic relationships.

Return ONE rooted category tree representing the complete final dataset.

Each category node has exactly:
{
  "name": "Category name",
  "entity_refs": [],
  "children": []
}

TREE RULES
1. The root node name MUST be "Capabilities".
2. Every final capability entity must appear EXACTLY ONCE in the entire tree.
3. Attach entities ONLY to LEAF category nodes.
4. Therefore:
   - a node with children MUST have entity_refs: []
   - a leaf node MUST have one or more entity_refs
5. A non-root node with children should have at least TWO children. Do not create redundant single-child category chains.
6. Build meaningful semantic ancestry from broad → narrower → specific.
7. Build enough ancestry above and below the likely balanced view that JAW can choose broad, balanced, and detailed visible sections by cutting the same tree at different points.
8. For medium or large datasets, aim for roughly 3–5 useful category levels from root to leaf when the domain supports it. Do NOT manufacture depth for a tiny dataset.
9. Avoid unnecessary fragmentation. A leaf may contain several closely related entities.
10. Single-entity leaf categories are allowed only when that category is genuinely useful; do not create one merely to label every entity.
11. Reorganize the FULL existing taxonomy when new entities make the old organization less coherent. Do not merely append the newest entities.
12. Category names should describe professional/functional areas, not storage entity types such as "Competencies" or "Products".

WHY THE TREE MATTERS
JAW itself does not understand the profession. It will only use the tree structure:
- Section Granularity selects a horizontal frontier through this tree.
- Entity Granularity controls how much descendant category depth is shown inside each selected section.
Therefore YOU decide semantic parent/child grouping; JAW only expands and collapses the structure.

REFERENCE RULES
- Every existing entity has an immutable id.
- When an existing entity needs enrichment, ref MUST equal its existing id and entity_id MUST contain that same id.
- For a new entity, create a unique ref beginning with "new:" and set entity_id to "".
- Relationships and hierarchy use these refs.
- Existing unchanged entities are omitted from entities but still appear exactly once in the complete tree by existing id.

WHAT TO RETURN
Return ONLY valid JSON.
Do not use markdown fences.
Do not include prose before or after the JSON.

Use exactly this top-level contract:
{
  "format": "jaw-smart-add",
  "version": 3,
  "entities": [
    {
      "ref": "new:kubernetes",
      "entity_id": "",
      "type": "technology",
      "canonical_name": "Kubernetes",
      "display_name": "Kubernetes",
      "aliases": ["K8s"]
    },
    {
      "ref": "new:eks",
      "entity_id": "",
      "type": "product",
      "canonical_name": "Amazon Elastic Kubernetes Service",
      "display_name": "EKS",
      "aliases": ["Amazon EKS"]
    }
  ],
  "relationships": [
    {
      "source_ref": "new:eks",
      "type": "based_on",
      "target_ref": "new:kubernetes"
    }
  ],
  "hierarchy": {
    "root": {
      "name": "Capabilities",
      "entity_refs": [],
      "children": [
        {
          "name": "Cloud & Platform",
          "entity_refs": [],
          "children": [
            {
              "name": "Containers & Orchestration",
              "entity_refs": [],
              "children": [
                {
                  "name": "Kubernetes Ecosystem",
                  "entity_refs": ["new:kubernetes", "new:eks"],
                  "children": []
                }
              ]
            }
          ]
        }
      ]
    }
  },
  "warnings": []
}

NOTE ABOUT THE EXAMPLE
The example demonstrates the JSON shape only. Its taxonomy is intentionally technical because the example entities are technical. For non-technical input, build an appropriate non-technical taxonomy.

The entities array contains ONLY:
- new entities, and
- existing entities whose type, canonical_name, or aliases should be enriched.

Unchanged existing entities MUST NOT be repeated in entities, but MUST still appear exactly once in the complete taxonomy tree using their existing id.

Return only relationships that are useful ADDITIONS. JAW preserves existing relationships.

FINAL SELF-CHECK BEFORE RESPONDING
Before returning JSON, verify all of the following:
1. format is exactly "jaw-smart-add".
2. version is exactly 3.
3. hierarchy.root exists and its name is exactly "Capabilities".
4. Every new entity ref begins with "new:" and has entity_id "".
5. Every existing enriched entity uses its immutable id for BOTH ref and entity_id.
6. No alias equals that entity's display_name or canonical_name.
7. Aliases are true alternate names, not descriptions.
8. No relevant_to relationship exists.
9. No self-relationship exists.
10. Every non-leaf taxonomy node has entity_refs: [].
11. Every leaf taxonomy node has at least one entity_ref.
12. Every non-root node with children has at least two children.
13. Every final capability entity appears exactly once in the entire taxonomy tree.
14. The full taxonomy may reorganize existing entities when that improves coherence.
15. Output is raw valid JSON only.

CURRENT DATASET
${JSON.stringify(current, null, 2)}

NEW INPUT NAMES
${JSON.stringify(names, null, 2)}

Now return the jaw-smart-add version 3 JSON only.`;
}

function resetSmartAddDialog() {
  smartAddPreviewData = null;
  $('capSmartInput').value = '';
  $('capSmartDelimiter').value = 'auto';
  $('capSmartDetected').textContent = '0';
  $('capSmartPrompt').value = '';
  $('capSmartResult').value = '';
  $('capSmartPromptStep').hidden = true;
  $('capSmartResultStep').hidden = true;
  $('capSmartPreviewPanel').hidden = true;
  $('capSmartPreviewPanel').innerHTML = '';
  $('capSmartApply').disabled = true;
}

function openSmartAddDialog() {
  resetSmartAddDialog();
  $('capSmartAddDialog').showModal();
  requestAnimationFrame(() => $('capSmartInput').focus());
}

function parseSmartAddResult() {
  let text = $('capSmartResult').value.trim();
  text = text.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  if (!text) throw new Error('Paste the JSON returned by ChatGPT');
  const data = JSON.parse(text);
  if (data.format !== 'jaw-smart-add' || Number(data.version) !== 3) {
    throw new Error('Expected jaw-smart-add version 3 JSON. Generate a fresh prompt before retrying.');
  }
  if (!Array.isArray(data.entities) || !Array.isArray(data.relationships) || !data.hierarchy?.root) {
    throw new Error('Smart Add JSON is missing entities, relationships, or hierarchy.root');
  }
  return data;
}

function previewSmartAdd() {
  try {
    const data = parseSmartAddResult();
    const currentEntities = (capabilityState.entities || []).filter(entity => entity.type !== 'set');
    const currentIds = new Set(currentEntities.map(entity => String(entity.id)));
    const newEntities = data.entities.filter(entity => !String(entity.entity_id || '').trim());
    const updates = data.entities.filter(entity => String(entity.entity_id || '').trim());
    const issues = [];
    const advisory = [...(data.warnings || [])];

    const entityRefs = new Set();
    for (const entity of data.entities) {
      const ref = String(entity.ref || '').trim();
      const entityId = String(entity.entity_id || '').trim();
      if (!ref) { issues.push('An entity is missing ref'); continue }
      if (entityRefs.has(ref)) issues.push(`Duplicate entity ref: ${ref}`);
      entityRefs.add(ref);

      if (entityId) {
        if (ref !== entityId) issues.push(`Existing entity must use the same ref and entity_id: ${ref}`);
        if (!currentIds.has(entityId)) issues.push(`Unknown existing entity_id: ${entityId}`);
      } else if (!ref.startsWith('new:')) {
        issues.push(`New entity ref must begin with new:: ${ref}`);
      }

      const canonical = String(entity.canonical_name || '').trim().toLocaleLowerCase();
      const display = String(entity.display_name || '').trim().toLocaleLowerCase();
      const aliasSeen = new Set();
      for (const rawAlias of entity.aliases || []) {
        const alias = String(rawAlias || '').trim();
        const key = alias.toLocaleLowerCase();
        if (!alias) continue;
        if (key === canonical || key === display) {
          advisory.push(`Redundant alias will be ignored in ${ref}: ${alias}`);
          continue;
        }
        if (aliasSeen.has(key)) {
          advisory.push(`Duplicate alias will be ignored in ${ref}: ${alias}`);
          continue;
        }
        aliasSeen.add(key);
      }
    }

    const planned = new Set([
      ...currentIds,
      ...newEntities.map(entity => String(entity.ref)),
    ]);

    for (const relationship of data.relationships) {
      const source = String(relationship.source_ref || '').trim();
      const target = String(relationship.target_ref || '').trim();
      const type = String(relationship.type || '').trim();
      if (type === 'relevant_to') {
        issues.push(`relevant_to is reserved for role membership: ${source} → ${target}`);
      } else if (!['uses', 'based_on', 'provided_by', 'related_to'].includes(type)) {
        issues.push(`Unsupported relationship type: ${type || '(blank)'}`);
      }
      if (source === target && source) issues.push(`Self-relationship: ${source}`);
      if (!planned.has(source)) issues.push(`Unknown relationship source: ${source}`);
      if (!planned.has(target)) issues.push(`Unknown relationship target: ${target}`);
    }

    const refs = [];
    let categoryCount = 0;
    let maxDepth = 0;
    let leafCount = 0;

    function walk(node, depth = 0, isRoot = false, path = []) {
      if (!node || typeof node !== 'object') {
        issues.push(`Invalid hierarchy category at ${path.join(' > ') || 'root'}`);
        return;
      }
      const name = String(node.name || '').trim();
      if (!name) {
        issues.push(`Hierarchy category is missing a name at depth ${depth}`);
      }
      if (isRoot && name !== 'Capabilities') {
        issues.push('hierarchy.root name must be exactly "Capabilities"');
      }

      const entityRefs = Array.isArray(node.entity_refs) ? node.entity_refs.map(String) : [];
      const children = Array.isArray(node.children) ? node.children : [];

      categoryCount += 1;
      maxDepth = Math.max(maxDepth, depth);

      if (children.length && entityRefs.length) {
        issues.push(`Category "${name}" has both children and entity_refs`);
      }
      if (!children.length) {
        leafCount += 1;
        if (!entityRefs.length && planned.size) {
          issues.push(`Leaf category "${name}" contains no entities`);
        }
      }
      if (!isRoot && children.length === 1) {
        issues.push(`Category "${name}" has only one child; collapse the redundant category`);
      }

      const childNames = new Set();
      for (const child of children) {
        const childName = String(child?.name || '').trim().toLocaleLowerCase();
        if (childName && childNames.has(childName)) {
          issues.push(`Duplicate child category under "${name}": ${child?.name}`);
        }
        if (childName) childNames.add(childName);
      }

      for (const ref of entityRefs) {
        refs.push(ref);
        if (!planned.has(ref)) issues.push(`Unknown hierarchy ref: ${ref}`);
      }
      children.forEach(child => walk(child, depth + 1, false, [...path, name]));
    }

    walk(data.hierarchy.root, 0, true, []);

    const duplicates = [...new Set(refs.filter((ref, index) => refs.indexOf(ref) !== index))];
    const missing = [...planned].filter(ref => !refs.includes(ref));
    if (duplicates.length) issues.push(`Duplicate hierarchy refs: ${duplicates.slice(0, 8).join(', ')}`);
    if (missing.length) issues.push(`Hierarchy missing: ${missing.slice(0, 8).join(', ')}`);

    const valid = !issues.length;
    $('capSmartPreviewPanel').innerHTML = `
      <div class="cap-smart-preview-stats">
        <div><b>${newEntities.length}</b><span>new entities</span></div>
        <div><b>${updates.length}</b><span>enriched / reclassified</span></div>
        <div><b>${data.relationships.length}</b><span>relationships</span></div>
        <div><b>${categoryCount}</b><span>categories</span></div>
        <div><b>${maxDepth}</b><span>tree depth</span></div>
      </div>
      ${newEntities.length ? `<div class="cap-smart-preview-list"><b>New:</b> ${newEntities.slice(0, 20).map(entity => esc(entity.display_name || entity.canonical_name || entity.ref)).join(', ')}${newEntities.length > 20 ? '…' : ''}</div>` : ''}
      <div class="cap-smart-preview-list"><b>Taxonomy:</b> ${leafCount} leaf categories · root ${esc(data.hierarchy.root?.name || '')}</div>
      ${issues.length ? `<div class="cap-smart-warnings"><b>Validation issues</b><ul>${issues.map(issue => `<li>${esc(issue)}</li>`).join('')}</ul></div>` : ''}
      ${advisory.length ? `<div class="cap-smart-warnings"><b>ChatGPT warnings</b><ul>${advisory.map(warning => `<li>${esc(warning)}</li>`).join('')}</ul></div>` : ''}
      ${valid ? `<div class="cap-smart-valid">✓ Nested taxonomy is ready to apply</div>` : ''}`;
    $('capSmartPreviewPanel').hidden = false;
    $('capSmartApply').disabled = !valid;
    smartAddPreviewData = valid ? data : null;
  } catch (error) {
    smartAddPreviewData = null;
    $('capSmartApply').disabled = true;
    $('capSmartPreviewPanel').hidden = false;
    $('capSmartPreviewPanel').innerHTML = `<div class="cap-smart-warnings"><b>Cannot preview</b><div>${esc(error.message)}</div></div>`;
  }
}

async function applySmartAdd() {
  if (!smartAddPreviewData) return;
  $('capSmartApply').disabled = true; $('capSmartApply').textContent = 'Applying…';
  try {
    const result = await capabilityApi('/api/capabilities/smart-add/apply', { data: smartAddPreviewData });
    capabilityState = result.capabilities || capabilityState;
    $('capSmartAddDialog').close();
    renderCapabilities();
    const summary = result.summary || {};
    toast(`Smart Add · ${summary.added || 0} added · ${summary.updated || 0} enriched`);
  } catch (error) {
    toast(error.message); $('capSmartApply').disabled = false;
  } finally { $('capSmartApply').textContent = 'Apply Smart Add' }
}

async function clearCapabilities() {
  const count = Number(capabilityState.stats?.capabilities || 0);
  if (!count) { toast('Capability model is already empty'); return }
  const ok = confirm(`Clear all ${count} capabilities and capability relationships?\n\nJobs, profile data, work history, Q&A, keybinds, and other JAW data are preserved.`);
  if (!ok) return;
  try {
    const result = await capabilityApi('/api/capabilities/clear', { confirm: true });
    capabilityState = result.capabilities || capabilityState;
    capabilitySetId = '__all__';
    renderCapabilities();
    toast('Capabilities cleared');
  } catch (error) { toast(error.message) }
}

function activateTopPage(pageId) { document.querySelectorAll('.page').forEach(page => page.classList.remove('active')); $(pageId)?.classList.add('active'); document.querySelectorAll('#drawer .nav').forEach(button => button.classList.toggle('active', button.dataset.page === pageId)); $('drawer').classList.remove('open') }
function normalizedHash() { return location.hash.replace(/^#/, '').replace(/^\//, '') }
function navigateHash(route) { const target = '#' + route; if (location.hash === target) { applyHashRoute(); return } location.hash = target }
async function applyHashRoute() {
  if (routeApplying) return; routeApplying = true;
  try {
    const route = normalizedHash() || CAP_ROUTE_DEFAULT; const parts = route.split('/').filter(Boolean); const root = parts[0] || CAP_ROUTE_DEFAULT;
    if (root === 'documents') {
      activateTopPage('documentsPage');
      documentView = Object.hasOwn(DOCUMENT_VIEWS, parts[1]) ? parts[1] : 'profiles';
      selectedDocumentId = '';
      await loadDocuments({ keepSelection: false });
    } else if (root === 'capabilities') {
      activateTopPage('capabilitiesPage'); capabilityView = ['hierarchy', 'set', 'rating', 'gap'].includes(parts[1]) ? parts[1] : 'hierarchy'; await loadCapabilities();
    } else if (root === 'user') {
      activateTopPage('userPage'); await loadUserData(); const view = ({ work: 'work', 'custom-data': 'custom-data', 'custom-actions': 'custom-actions', qa: 'qa' })[parts[1]] || 'user'; showUserView(view);
    } else if (root === 'keybinds') {
      activateTopPage('keybindPage');
    } else {
      activateTopPage('jobsPage'); await loadJobs(); const jobId = parts[1] === 'job' ? Number(parts[2]) : 0; if (jobId && jobId !== selectedJob) await originalShowJobForRouting(jobId);
    }
  } catch (error) { console.error(error); toast(error.message) } finally { routeApplying = false }
}

const originalShowJobForRouting = showJob;
showJob = async function (id) { await originalShowJobForRouting(id); if (!routeApplying && location.hash !== `#tracker/job/${id}`) history.replaceState(null, '', `${location.pathname}#tracker/job/${id}`) };
const originalDeleteJobForRouting = deleteJob;
deleteJob = async function (id) { await originalDeleteJobForRouting(id); if (!selectedJob) navigateHash('tracker') };

document.querySelectorAll('#drawer .nav').forEach(button => button.onclick = () => navigateHash(button.dataset.route || CAP_ROUTE_DEFAULT));
$('capAddEntity').onclick = event => {
  event.stopPropagation();
  $('capAddMenu').hidden = !$('capAddMenu').hidden;
};
$('capAddSingle').onclick = () => { $('capAddMenu').hidden = true; openCapabilityDialog() };
$('capSmartAdd').onclick = () => { $('capAddMenu').hidden = true; openSmartAddDialog() };
$('capClearCapabilities').onclick = () => { $('capAddMenu').hidden = true; clearCapabilities() };
document.addEventListener('click', event => {
  if (!event.target.closest('.cap-add-wrap')) $('capAddMenu').hidden = true;
  if (!event.target.closest('.cap-pane-mode-wrap')) closePaneMenus();
  if (!event.target.closest('.cap-rating-field')) {
    $('capRatingPopover').hidden = true;
    $('capRatingHelp').setAttribute('aria-expanded', 'false');
  }
});
$('capLeftModeButton').onclick = event => togglePaneMenu('left', event);
$('capRightModeButton').onclick = event => togglePaneMenu('right', event);
document.querySelectorAll('[data-pane-mode]').forEach(button => button.onclick = event => { event.stopPropagation(); setCapabilityPaneMode(button.dataset.paneSide, button.dataset.paneMode) });
$('capRestoreLeftPane').onclick = () => setCapabilityPaneMode('left', 'auto');
$('capRestoreRightPane').onclick = () => setCapabilityPaneMode('right', 'auto');
$('capUseGuideToggle').onchange = () => { capabilityShowUseGuide = $('capUseGuideToggle').checked; renderCapabilityReference(); saveCapabilityViewPreferences() };
$('capSmartInput').oninput = parseSmartAddNames; $('capSmartDelimiter').onchange = parseSmartAddNames;
$('capSmartPrepare').onclick = () => { const names = parseSmartAddNames(); if (!names.length) { toast('Add at least one capability name'); return } $('capSmartPrompt').value = buildSmartAddPrompt(names); $('capSmartPromptStep').hidden = false; $('capSmartResultStep').hidden = false; $('capSmartApply').disabled = true; smartAddPreviewData = null; $('capSmartPreviewPanel').hidden = true; requestAnimationFrame(() => $('capSmartPrompt').scrollIntoView({ behavior: 'smooth', block: 'start' })) };
$('capSmartCopyPrompt').onclick = async () => { try { await navigator.clipboard.writeText($('capSmartPrompt').value); toast('Smart Add prompt copied') } catch { toast('Clipboard access failed — select and copy the prompt manually') } };
$('capSmartOpenChatGPT').onclick = () => window.open('https://chatgpt.com/', '_blank', 'noopener');
$('capSmartPreview').onclick = previewSmartAdd; $('capSmartApply').onclick = applySmartAdd;
$('capSmartClose').onclick = () => $('capSmartAddDialog').close(); $('capSmartCancel').onclick = () => $('capSmartAddDialog').close();
document.querySelectorAll('[data-cap-view]').forEach(button => button.onclick = () => { capabilityView = button.dataset.capView; navigateHash(`capabilities/${capabilityView}`) });
$('capSearch').oninput = renderCapabilities;
$('capUnratedOnly').onchange = renderCapabilities;
$('capCompactMode').onclick = () => {
  capabilityDisplayMode = 'compact';
  renderCapabilities();
  saveCapabilityViewPreferences();
};
$('capDetailedMode').onclick = () => {
  capabilityDisplayMode = 'detailed';
  renderCapabilities();
  saveCapabilityViewPreferences();
};
$('capMatchMode').onclick = () => {
  capabilityMatchMode = !capabilityMatchMode;
  renderCapabilities();
  toast(
    capabilityMatchMode
      ? 'Match Selection · click pills to include or exclude'
      : 'Match Selection off'
  );
};
$('capSectionGranularity').oninput = queueCapabilityViewSave;
$('capEntityGranularity').oninput = queueCapabilityViewSave;
$('capEntityType').onchange = syncCapabilityDialogType;
$('capSaveSet').onclick = saveCapabilitySet;
$('capDeleteSet').onclick = deleteCapabilitySet;
$('capSetClose').onclick = closeCapabilitySetDialog;
$('capSetCancel').onclick = closeCapabilitySetDialog;
$('capSetForm').onsubmit = event => { event.preventDefault(); saveCapabilitySet() };
$('capSaveEntity').onclick = saveCapabilityEntity;
$('capDeleteEntity').onclick = deleteCapabilityEntity;
$('capEntityClose').onclick = closeCapabilityDialog;
$('capEntityCancel').onclick = closeCapabilityDialog;
$('capEntityForm').onsubmit = event => { event.preventDefault(); saveCapabilityEntity() };
$('capEntityDialog').addEventListener('close', () => {
  $('capRatingPopover').hidden = true;
  $('capRatingHelp').setAttribute('aria-expanded', 'false');
  renderCapabilityReference();
});
$('capRatingHelp').onclick = event => {
  event.preventDefault(); event.stopPropagation();
  const next = $('capRatingPopover').hidden;
  $('capRatingPopover').hidden = !next;
  $('capRatingHelp').setAttribute('aria-expanded', String(next));
};

document.addEventListener('keydown', event => {
  if (!$('capabilitiesPage').classList.contains('active') || event.target.matches('input,textarea,select,[contenteditable="true"]')) return;
  if (!capabilityMatchMode && capabilityView !== 'set' && capabilityHoveredId && event.key >= '0' && event.key <= '5') {
    const entity = capById()[capabilityHoveredId];
    if (entity && capRateable(entity)) {
      event.preventDefault();
      setCapabilityRating(entity.id, Number(event.key));
    }
  }
});
window.addEventListener('hashchange', applyHashRoute);

// User sub-tabs are now bookmarkable too.
$('userTab').onclick = () => navigateHash('user'); $('workTab').onclick = () => navigateHash('user/work'); $('customDataTab').onclick = () => navigateHash('user/custom-data'); $('customActionsTab').onclick = () => navigateHash('user/custom-actions'); $('qaTab').onclick = () => navigateHash('user/qa');

// Convert the legacy ?job=123 launch URL used by the desktop app into the
// bookmarkable hash route without reloading the page.
const launchJob = new URLSearchParams(location.search).get('job');
if (launchJob && !location.hash) { history.replaceState(null, '', `${location.pathname}#tracker/job/${Number(launchJob)}`) }
else if (!location.hash) { history.replaceState(null, '', `${location.pathname}#tracker`) }
applyHashRoute();
