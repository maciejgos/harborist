'use strict';
const stages = ['intake', 'design', 'plan', 'build', 'test', 'review', 'package'];
const terminal = new Set(['FINISHED', 'FAILED', 'INTERRUPTED']);
const finished = record => terminal.has(record.state) || ['COMPLETED', 'FAILED', 'CANCELLED'].includes(record.run?.lifecycle);
const $ = id => document.getElementById(id);
let records = [], selected = location.hash.slice(1), busy = false, timer, lastSuccess = null, artifactRequest = 0;
const text = (tag, value, className) => { const node = document.createElement(tag); node.textContent = value; if (className) node.className = className; return node; };
const tone = value => ['VERIFIED', 'FINISHED', 'RUNNING'].includes(value) ? 'good' : ['FAILED', 'TEST_FAILED', 'CHANGES_REQUIRED'].includes(value) ? 'bad' : ['INTERRUPTED', 'CANCELLED', 'NEEDS_CLARIFICATION', 'NEEDS_RESCOPING'].includes(value) ? 'warning' : 'muted';
const date = value => value ? new Date(value).toLocaleString() : 'Unavailable';
async function api(path) {
  const response = await fetch('/api' + path, {cache: 'no-store', signal: AbortSignal.timeout(7000)});
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || 'The service is unavailable.');
  return body;
}
function filtered() {
  const query = $('search').value.trim().toLowerCase();
  return records.filter(r => [r.title, r.submission.run_id, r.state, r.run?.outcome, r.run?.lifecycle].join(' ').toLowerCase().includes(query));
}
function renderHistory() {
  const list = $('runs');
  const scrollTop = list.scrollTop;
  const focusId = document.activeElement?.dataset.runId;
  list.replaceChildren();
  const visible = filtered();
  $('history-status').textContent = records.length ? `${visible.length} of ${records.length} Runs` : 'No saved Runs yet. Start a Run from the CLI.';
  if (records.length && !visible.length) $('history-status').textContent = 'No matching Runs.';
  for (const record of visible) {
    const id = record.submission.run_id;
    const button = text('button', '', 'run');
    button.type = 'button'; button.dataset.runId = id;
    button.setAttribute('aria-current', String(id === selected));
    button.append(text('span', record.title || 'Untitled request', 'run-title'));
    const meta = text('span', '', 'run-meta');
    meta.append(text('span', id.slice(0, 8), 'mono muted'));
    const state = record.run?.outcome || record.run?.failure_reason || record.state || record.run?.lifecycle || 'UNAVAILABLE';
    meta.append(text('span', state, 'state ' + tone(state)));
    button.append(meta); button.addEventListener('click', () => choose(id)); list.append(button);
  }
  list.scrollTop = scrollTop;
  if (focusId) [...list.children].find(node => node.dataset.runId === focusId)?.focus({preventScroll: true});
}
function choose(id) {
  selected = id; history.replaceState(null, '', '#' + id);
  renderHistory(); renderDetail();
}
function pair(list, label, value, className = '') { list.append(text('dt', label), text('dd', value || 'Unavailable', className)); }
function renderDetail() {
  const main = $('detail'); main.replaceChildren();
  const record = records.find(r => r.submission.run_id === selected);
  if (!record) {
    const box = text('div', '', 'empty');
    box.append(text('h2', records.length ? 'Select a Run' : 'Your execution history starts here'), text('p', records.length ? 'Choose a Run to inspect its progress and evidence.' : 'Start the service, then submit a request with shipyard run. New Runs appear here automatically.'));
    main.append(box); return;
  }
  main.append(text('h2', record.title || 'Untitled request'), text('p', record.submission.run_id, 'mono run-id'));
  const timeline = text('ol', '', 'timeline'); timeline.setAttribute('aria-label', 'Canonical stage timeline');
  for (const name of stages) {
    const observation = record.stages?.[name];
    let state = observation?.state || (name === 'intake' && record.run ? 'completed' : 'unknown');
    if (state === 'completed' && ['TEST_FAILED', 'CHANGES_REQUIRED'].includes(observation?.reason)) state = 'failed';
    if (state === 'completed' && ['NEEDS_CLARIFICATION', 'NEEDS_RESCOPING'].includes(observation?.reason)) state = observation.reason.toLowerCase();
    if (state === 'started' && finished(record)) state = 'interrupted';
    const item = text('li', '', 'stage'); item.dataset.state = state;
    item.append(text('span', state === 'completed' ? '✓' : state === 'started' ? '●' : state === 'failed' ? '×' : '·', 'stage-symbol'), text('span', name.toUpperCase(), 'stage-name'), text('span', state === 'unknown' ? 'Not recorded' : state === 'started' ? 'Running' : (state[0].toUpperCase() + state.slice(1)).replaceAll('_', ' '), 'stage-state'));
    timeline.append(item);
  }
  main.append(timeline);
  const execution = text('section', ''); execution.append(text('h3', 'Execution'));
  const fields = text('dl', '');
  pair(fields, 'Status', record.run?.lifecycle, tone(record.run?.lifecycle));
  pair(fields, 'Attempt', record.attempt_id, 'mono');
  if (record.state) pair(fields, 'Delivery', record.state, tone(record.state));
  pair(fields, 'Verified candidate', record.candidate_sha, 'mono');
  pair(fields, record.source === 'saved' ? 'Recorded' : 'Submitted', date(record.submitted_at || record.recorded_at), 'mono');
  pair(fields, 'Updated', date(record.updated_at), 'mono');
  if (record.run?.outcome) pair(fields, 'Outcome', record.run.outcome, tone(record.run.outcome));
  if (record.run?.failure_reason) pair(fields, 'Failure', record.run.failure_reason, 'bad');
  execution.append(fields); main.append(execution);
  const evidence = text('section', ''); evidence.append(text('h3', 'Evidence'));
  const links = text('div', '', 'evidence-links');
  for (const name of ['report.md', 'evidence.json']) if (record.artifacts?.[name]) {
    const button = text('button', name === 'report.md' ? 'Read report' : 'View evidence'); button.type = 'button';
    button.dataset.artifactName = name; button.addEventListener('click', () => showArtifact(record.submission.run_id, name)); links.append(button);
  }
  if (!links.children.length) links.append(text('p', finished(record) ? 'No terminal report is available. Inspect the retained Run records.' : 'Reports and evidence become available during PACKAGE.', 'muted'));
  evidence.append(links); main.append(evidence);
  const current = text('section', ''); current.append(text('h3', 'What is happening'));
  let message = record.state === 'QUEUED' ? 'Waiting for the execution service.' : record.state === 'INTERRUPTED' ? 'The service stopped during this execution. The Run will not be retried automatically.' : record.state === 'FAILED' ? 'Execution could not finish. Inspect the error below and retained Run records.' : record.state === 'FINISHED' ? 'Execution has finished. Review the outcome and evidence above.' : record.progress?.state === 'started' ? `${record.progress.stage.toUpperCase()} is running. Progress is observational; validated Run state is authoritative.` : 'Waiting for the next recorded stage update.';
  if (record.source === 'saved') {
    message = !record.run ? 'This saved Run could not be read. Inspect the error below.' : record.run.lifecycle === 'COMPLETED' ? 'Execution has finished. Review the outcome and evidence above.' : record.run.lifecycle === 'FAILED' ? 'Execution failed. Review the failure and retained evidence.' : record.run.lifecycle === 'CANCELLED' ? 'Execution was cancelled.' : record.run.lifecycle === 'CREATED' ? 'This request was captured but has not started execution.' : 'The saved records report RUNNING. No background-service progress is recorded for this Run.';
  }
  current.append(text('p', message, 'notice'));
  for (const error of [record.error, record.run_error]) if (error) current.append(text('p', error, 'notice error'));
  for (const [stage, error] of Object.entries(record.stage_errors || {})) current.append(text('p', `${stage.toUpperCase()} history unavailable: ${error}`, 'notice error'));
  if (record.progress?.reason) current.append(text('p', record.progress.reason, 'muted'));
  main.append(current);
}
async function showArtifact(id, name) {
  const request = ++artifactRequest;
  $('artifact-title').textContent = name;
  $('artifact-content').textContent = '';
  $('artifact-status').textContent = 'Loading artifact…';
  $('artifact-dialog').showModal();
  try {
    const data = await api(`/runs/${id}/artifacts/${name}`);
    if (request !== artifactRequest) return;
    $('artifact-content').textContent = data.content;
    $('artifact-status').textContent = 'Read-only artifact';
  } catch (error) { if (request === artifactRequest) $('artifact-status').textContent = `Unable to load artifact: ${error.message}. Close and reopen to retry.`; }
}
async function refresh() {
  if (busy) return;
  busy = true; clearTimeout(timer);
  try {
    const data = await api('/runs');
    records = data.runs.slice().reverse(); lastSuccess = new Date();
    if (!selected && records.length) selected = (records.find(record => record.state === 'RUNNING') || records[0]).submission.run_id;
    $('connection').textContent = 'Connected'; $('connection').dataset.connected = 'true';
    $('connection-error').hidden = true;
    $('last-updated').textContent = `Updated ${lastSuccess.toLocaleTimeString()}`;
    renderHistory();
    // Preserve keyboard focus on an artifact button during observational refresh.
    if (!$('artifact-dialog').open && !$('detail').contains(document.activeElement)) renderDetail();
  } catch (error) {
    $('connection').textContent = 'Disconnected'; $('connection').dataset.connected = 'false';
    $('connection-error').textContent = `Cannot refresh execution history. ${lastSuccess ? 'Displayed data may be stale. ' : ''}${error.message} Use Refresh to retry.`;
    $('connection-error').hidden = false;
    if (!lastSuccess) { $('history-status').textContent = 'Service unavailable'; $('detail').replaceChildren(text('h2', 'Execution service unavailable'), text('p', 'Start shipyard service start, then select Refresh. The monitor reconnects automatically.')); }
  } finally { busy = false; timer = setTimeout(refresh, 2000); }
}
$('refresh').addEventListener('click', refresh);
$('search').addEventListener('input', renderHistory);
$('close-artifact').addEventListener('click', () => $('artifact-dialog').close());
$('artifact-dialog').addEventListener('close', () => { artifactRequest++; const name = $('artifact-title').textContent; renderDetail(); [...$('detail').querySelectorAll('[data-artifact-name]')].find(button => button.dataset.artifactName === name)?.focus({preventScroll: true}); });
window.addEventListener('hashchange', () => { selected = location.hash.slice(1); renderHistory(); renderDetail(); });
refresh();
