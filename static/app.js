/* CodeJudge frontend: plain JavaScript, no build step. */

const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const state = { status: null, models: [], samples: [], audit: null, running: false };

const PIPE = [
  { id: 'static', icon: '⚙', name: 'Static analysis', sub: 'Bandit + Pylint scan' },
  { id: 'security', icon: '🛡', name: 'Security Agent', sub: 'Injection, secrets, crypto, deserialization' },
  { id: 'performance', icon: '⚡', name: 'Performance Agent', sub: 'Complexity, loops, leaks' },
  { id: 'quality', icon: '✦', name: 'Code Quality Agent', sub: 'Bugs, edge cases, maintainability' },
  { id: 'verify', icon: '⚖', name: 'Verification Judge', sub: 'Confirms or rejects static warnings' },
  { id: 'chief', icon: '★', name: 'Chief Judge', sub: 'Final verdict + auto-fix' },
];
const AGENT_LABEL = { security: 'Security', performance: 'Performance', quality: 'Code Quality' };
const GRADE_COLOR = { A: '#34d399', B: '#a3e635', C: '#facc15', D: '#fb923c', F: '#fb7185' };

// ------------------------------------------------------------------ helpers
async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  return res.json();
}

async function streamNDJSON(url, body, onEvent) {
  const res = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch {}
    throw new Error(msg);
  }
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, i).trim();
      buf = buf.slice(i + 1);
      if (line) onEvent(JSON.parse(line));
    }
  }
}

function toast(msg, kind = 'info') {
  const el = $('#toast');
  const color = kind === 'error' ? 'border-rose-500/40 text-rose-200' : 'border-indigo-500/40 text-slate-100';
  el.innerHTML = `<div class="card px-4 py-3 text-sm shadow-xl ${color}">${esc(msg)}</div>`;
  el.classList.remove('hidden');
  clearTimeout(toast.t);
  toast.t = setTimeout(() => el.classList.add('hidden'), 4000);
}

const fmtTime = (iso) => new Date(iso).toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });

// ------------------------------------------------------------------ routing
function route() {
  let view = (location.hash || '#audit').slice(1);
  if (!['audit', 'history', 'models', 'about'].includes(view)) view = 'audit';
  if (view === 'audit' && state.status && !state.status.model) view = 'models';
  document.querySelectorAll('.view').forEach((v) => v.classList.add('hidden'));
  $(`#view-${view}`).classList.remove('hidden');
  document.querySelectorAll('.nav-link').forEach((a) => a.classList.toggle('active', a.dataset.view === view));
  if (view === 'models') renderModels();
  if (view === 'history') renderHistory();
  if (view === 'about') renderAbout();
}
window.addEventListener('hashchange', route);

// ------------------------------------------------------------------ status chips
async function refreshStatus() {
  try {
    state.status = await api('/api/status');
  } catch { return; }
  const s = state.status;
  const chip = $('#chip-model');
  if (s.model) {
    const extra = s.loaded ? ` · ${(s.loaded.vram_mb / 1024).toFixed(1)} GB VRAM` : '';
    chip.innerHTML = `<span class="dot live bg-emerald-400"></span><span class="font-mono">${esc(s.model)}</span><span class="text-slate-500">${extra}</span>`;
  } else if (!s.ollama) {
    chip.innerHTML = `<span class="dot bg-rose-400"></span><span>Ollama offline</span>`;
  } else {
    chip.innerHTML = `<span class="dot bg-slate-500"></span><span>No model loaded</span>`;
  }
  const g = s.gpu, gchip = $('#chip-gpu');
  if (g) {
    gchip.classList.remove('hidden');
    gchip.innerHTML = `<svg class="w-3.5 h-3.5 text-emerald-300" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16" rx="2"/><path d="M9 9h6v6H9zM9 1v3M15 1v3M9 20v3M15 20v3M20 9h3M20 14h3M1 9h3M1 14h3"/></svg>
      <span>${esc(g.name.replace('NVIDIA GeForce ', ''))}</span>
      <span class="text-slate-500 font-mono">${(g.mem_used_mb / 1024).toFixed(1)}/${(g.mem_total_mb / 1024).toFixed(1)} GB · ${g.util_pct}%</span>`;
  }
  updateRunButton();
}

// ------------------------------------------------------------------ models view
async function renderModels() {
  const grid = $('#model-grid');
  try {
    const data = await api('/api/models');
    state.models = data.models;
    $('#ollama-down').classList.add('hidden');
  } catch {
    $('#ollama-down').classList.remove('hidden');
    grid.innerHTML = '';
    return;
  }
  const active = state.status?.model;
  grid.innerHTML = state.models.map((m) => {
    const isActive = m.name === active;
    const tagColor = m.tag === 'Recommended' ? 'text-indigo-300 bg-indigo-500/15 border-indigo-500/30'
      : 'text-slate-300 bg-white/5 border-white/10';
    return `
    <div class="card p-5 flex flex-col fade-in ${isActive ? 'ring-1 ring-emerald-400/50' : ''}">
      <div class="flex items-start justify-between gap-3">
        <div class="w-11 h-11 rounded-xl bg-gradient-to-br from-indigo-500/30 to-fuchsia-500/20 grid place-items-center text-lg">🧠</div>
        <span class="text-[11px] font-semibold px-2.5 py-1 rounded-full border ${tagColor}">${esc(m.tag)}</span>
      </div>
      <div class="mt-4 text-white font-semibold">${esc(m.label)}</div>
      <div class="font-mono text-xs text-slate-500 mt-0.5">${esc(m.name)}</div>
      <p class="text-sm text-slate-400 mt-3 flex-1">${esc(m.desc)}</p>
      <div class="flex items-center gap-3 text-xs text-slate-500 mt-4">
        ${m.size_gb ? `<span>${m.size_gb} GB</span><span>·</span>` : ''}
        ${m.installed ? '<span class="text-emerald-300">✓ Downloaded</span>' : '<span class="text-amber-300">↓ Downloads on first load</span>'}
      </div>
      ${isActive
        ? `<div class="flex gap-2 mt-4"><a href="#audit" class="btn-primary h-10 flex-1">Loaded · Start auditing</a>
           <button class="btn-ghost h-10" onclick="unloadModel()">Unload</button></div>`
        : `<button class="btn-ghost h-10 mt-4 w-full" onclick="loadModel('${esc(m.name)}')">Load into GPU</button>`}
    </div>`;
  }).join('');
}

const LOAD_STEPS = [
  { id: 'connect', label: 'Connect to Ollama runtime' },
  { id: 'download', label: 'Download model weights' },
  { id: 'free', label: 'Free GPU memory' },
  { id: 'loading', label: 'Load weights into VRAM' },
  { id: 'warmup', label: 'Warm-up inference' },
  { id: 'ready', label: 'Judge ready' },
];

async function loadModel(name) {
  const model = state.models.find((m) => m.name === name) || { name, installed: true };
  const steps = LOAD_STEPS.filter((s) => s.id !== 'download' || !model.installed);
  const order = steps.map((s) => s.id);
  let current = -1;

  $('#loader').classList.replace('hidden', 'flex');
  $('#loader-model').textContent = name;
  $('#loader-done').classList.add('hidden');
  $('#loader-err').classList.add('hidden');
  $('#loader-icon').className = 'spinner';
  $('#loader-icon').textContent = '';
  setLoaderPct(0);

  const drawSteps = () => {
    $('#loader-steps').innerHTML = steps.map((s, i) => {
      const st = i < current ? 'done' : i === current ? 'run' : 'wait';
      const icon = st === 'done' ? '<span class="text-emerald-400">✓</span>'
        : st === 'run' ? '<span class="spinner sm"></span>' : '<span class="w-2 h-2 rounded-full bg-ink-600"></span>';
      return `<li class="flex items-center gap-3 ${st === 'wait' ? 'text-slate-600' : st === 'run' ? 'text-white' : 'text-slate-400'}">
        <span class="w-5 grid place-items-center">${icon}</span>${s.label}</li>`;
    }).join('');
  };
  drawSteps();

  // live GPU memory gauge while the model streams into VRAM
  const gpuPoll = setInterval(async () => {
    try {
      const s = await api('/api/status');
      if (s.gpu) {
        const pct = (100 * s.gpu.mem_used_mb) / s.gpu.mem_total_mb;
        $('#vram-bar').style.width = pct + '%';
        $('#vram-num').textContent = `${(s.gpu.mem_used_mb / 1024).toFixed(2)} / ${(s.gpu.mem_total_mb / 1024).toFixed(1)} GB`;
        $('#vram-label').textContent = `${s.gpu.name.replace('NVIDIA GeForce ', '')} memory`;
      } else {
        $('#vram-label').textContent = 'No NVIDIA GPU detected (CPU mode)';
      }
    } catch {}
  }, 600);

  try {
    await streamNDJSON('/api/models/load', { model: name }, (ev) => {
      if (ev.stage === 'error') throw new Error(ev.message);
      const idx = order.indexOf(ev.stage);
      if (idx > current) { current = idx; drawSteps(); }
      setLoaderPct(ev.pct);
      $('#loader-msg').textContent = ev.message || '';
      if (ev.stage === 'ready') {
        current = steps.length; drawSteps();
        $('#loader-icon').className = 'w-[38px] h-[38px] rounded-full grid place-items-center bg-emerald-500/20 text-emerald-300 text-xl shrink-0';
        $('#loader-icon').textContent = '✓';
        $('#loader-summary').innerHTML = [
          ['Load time', `${ev.seconds}s`], ['VRAM used', `${(ev.vram_mb / 1024).toFixed(1)} GB`], ['On GPU', `${ev.gpu_pct}%`],
        ].map(([k, v]) => `<div class="rounded-xl bg-ink-850 border border-white/5 py-3"><div class="text-lg font-semibold text-white">${v}</div><div class="text-[11px] text-slate-500 uppercase tracking-wider mt-0.5">${k}</div></div>`).join('');
        $('#loader-done').classList.remove('hidden');
      }
    });
  } catch (e) {
    $('#loader-icon').className = 'w-[38px] h-[38px] rounded-full grid place-items-center bg-rose-500/20 text-rose-300 text-xl shrink-0';
    $('#loader-icon').textContent = '!';
    $('#loader-err-msg').textContent = e.message;
    $('#loader-err').classList.remove('hidden');
  } finally {
    setTimeout(() => clearInterval(gpuPoll), 1500);
    refreshStatus();
  }
}

function setLoaderPct(p) {
  $('#loader-bar').style.width = p + '%';
  $('#loader-pct').textContent = Math.round(p) + '%';
}

async function closeLoader(go) {
  $('#loader').classList.replace('flex', 'hidden');
  await refreshStatus();
  if (go) location.hash = '#audit'; else renderModels();
}

async function unloadModel() {
  await api('/api/models/unload', { method: 'POST' });
  await refreshStatus();
  renderModels();
  toast('Model unloaded from GPU');
}

// ------------------------------------------------------------------ editor
const codeEl = () => $('#code');
function syncGutter() {
  const n = Math.max(1, codeEl().value.split('\n').length);
  $('#gutter').textContent = Array.from({ length: n }, (_, i) => i + 1).join('\n');
  $('#line-count').textContent = `${codeEl().value ? n : 0} lines`;
  updateRunButton();
}
function setCode(code, filename) {
  codeEl().value = code;
  if (filename) $('#filename').value = filename;
  syncGutter();
}

async function initEditor() {
  const c = codeEl();
  c.addEventListener('input', syncGutter);
  c.addEventListener('scroll', () => { $('#gutter').scrollTop = c.scrollTop; });
  c.addEventListener('keydown', (e) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const s = c.selectionStart;
      c.setRangeText('    ', s, c.selectionEnd, 'end');
      syncGutter();
    }
  });
  $('#file-input').addEventListener('change', async (e) => {
    const f = e.target.files[0];
    if (f) setCode(await f.text(), f.name);
    e.target.value = '';
  });
  try {
    state.samples = await api('/api/samples');
    $('#sample-select').innerHTML += state.samples.map((s, i) => `<option value="${i}">${esc(s.name)}</option>`).join('');
  } catch {}
  $('#sample-select').addEventListener('change', (e) => {
    const s = state.samples[e.target.value];
    if (s) setCode(s.code, s.filename);
    e.target.value = '';
  });
  $('#run-btn').addEventListener('click', runAudit);
  syncGutter();
  renderPipeline({});
}

function updateRunButton() {
  const btn = $('#run-btn');
  if (!btn) return;
  const hasModel = !!state.status?.model;
  const hasCode = codeEl().value.trim().length > 0;
  btn.disabled = state.running || !hasModel || !hasCode;
  $('#run-hint').innerHTML = !hasModel ? 'Load a model first · <a class="text-indigo-300" href="#models">select model</a>'
    : !hasCode ? 'Paste code, upload a file or pick a demo sample'
    : state.running ? 'Judges are deliberating…' : `Judge: <span class="font-mono text-slate-400">${esc(state.status.model)}</span>`;
}

// ------------------------------------------------------------------ pipeline + audit
function renderPipeline(st) {
  $('#pipeline').innerHTML = PIPE.map((p) => {
    const s = st[p.id] || {};
    const cls = s.status === 'running' ? 'running' : s.status === 'done' ? 'done' : '';
    const icon = s.status === 'running' ? '<span class="spinner sm"></span>' : s.status === 'done' ? '✓' : p.icon;
    return `<li class="pstep ${cls}">
      <div class="pico">${icon}</div>
      <div class="min-w-0 flex-1">
        <div class="flex items-center justify-between gap-2">
          <span class="text-sm font-medium ${s.status ? 'text-white' : 'text-slate-400'}">${p.name}</span>
          ${s.secs != null ? `<span class="text-[11px] font-mono text-slate-500">${s.secs}s</span>` : ''}
        </div>
        <div class="text-xs ${s.detail ? 'text-emerald-300/90' : 'text-slate-500'} truncate">${esc(s.detail || p.sub)}</div>
      </div></li>`;
  }).join('');
}

async function runAudit() {
  if ($('#run-btn').disabled) return;
  state.running = true;
  updateRunButton();
  $('#results').innerHTML = '';
  const st = {};
  renderPipeline(st);
  const t0 = Date.now();
  const timer = setInterval(() => { $('#pipe-timer').textContent = ((Date.now() - t0) / 1000).toFixed(1) + 's'; }, 100);
  try {
    await streamNDJSON('/api/audit', { code: codeEl().value, filename: $('#filename').value || 'snippet.py' }, (ev) => {
      if (ev.type === 'step') { st[ev.step] = ev; renderPipeline(st); }
      if (ev.type === 'error') throw new Error(ev.message);
      if (ev.type === 'result') {
        state.audit = ev.audit;
        renderResult(ev.audit);
        setTimeout(() => $('#results').scrollIntoView({ behavior: 'smooth', block: 'start' }), 150);
      }
    });
  } catch (e) {
    toast('Audit failed: ' + e.message, 'error');
    refreshStatus();
  } finally {
    clearInterval(timer);
    state.running = false;
    updateRunButton();
  }
}

// ------------------------------------------------------------------ result rendering
function gradeRing(a) {
  const r = 54, c = 2 * Math.PI * r, off = c * (1 - a.overall / 10), col = GRADE_COLOR[a.grade];
  return `<svg viewBox="0 0 140 140" class="w-36 h-36 -rotate-90">
    <circle cx="70" cy="70" r="${r}" stroke="#1e2639" stroke-width="12" fill="none"/>
    <circle cx="70" cy="70" r="${r}" stroke="${col}" stroke-width="12" fill="none" stroke-linecap="round"
      stroke-dasharray="${c}" stroke-dashoffset="${c}" style="transition: stroke-dashoffset 1.2s ease" data-off="${off}"/>
  </svg>
  <div class="absolute inset-0 grid place-items-center text-center">
    <div><div class="text-5xl font-bold" style="color:${col}">${a.grade}</div>
    <div class="text-xs text-slate-400 font-mono mt-1">${a.overall}/10</div></div>
  </div>`;
}

const sevBadge = (s) => `<span class="sev sev-${s}">${s}</span>`;

function renderResult(a) {
  const sv = a.stats.by_severity;
  const noise = a.stats.static_total ? Math.round((100 * a.stats.static_rejected) / a.stats.static_total) : 0;
  const allIssues = Object.entries(a.agents).flatMap(([k, ag]) => ag.issues.map((i) => ({ ...i, agent: k })));
  const sevOrder = ['critical', 'high', 'medium', 'low'];
  allIssues.sort((x, y) => sevOrder.indexOf(x.severity) - sevOrder.indexOf(y.severity));

  const tile = (label, value, sub, color = 'text-white') => `
    <div class="card p-5"><div class="text-[11px] uppercase tracking-wider text-slate-500">${label}</div>
    <div class="text-3xl font-semibold mt-2 ${color}">${value}</div><div class="text-xs text-slate-500 mt-1">${sub}</div></div>`;

  $('#results').innerHTML = `
  <div class="fade-in">
    <div class="flex flex-wrap items-end gap-3 mb-5">
      <div><div class="eyebrow">Step 3 · Verdict</div>
        <h2 class="text-3xl font-semibold text-white tracking-tight mt-2">Audit report <span class="text-slate-500 font-normal text-xl">· ${esc(a.filename)}</span></h2></div>
      <div class="ml-auto flex gap-2">
        <a class="btn-ghost" href="/api/history/${a.id}/report.pdf">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M12 4v12m0 0l-4-4m4 4l4-4M4 20h16"/></svg>Download PDF</a>
      </div>
    </div>

    <div class="grid lg:grid-cols-[260px_1fr] gap-4">
      <div class="card p-6 flex flex-col items-center justify-center">
        <div class="relative">${gradeRing(a)}</div>
        <div class="text-sm text-slate-400 mt-3">Overall grade</div>
        ${a.critical_cap ? '<div class="text-[11px] text-rose-300/90 mt-1 text-center">Capped at D: critical vulnerability</div>' : ''}
      </div>
      <div class="card p-6">
        <div class="flex items-center gap-2 text-sm font-semibold text-white"><span class="text-amber-300">★</span> Chief Judge verdict</div>
        <p class="text-slate-300 mt-3 leading-relaxed">${esc(a.verdict || 'No verdict returned.')}</p>
        ${a.top_risks.length ? `<div class="mt-5 text-xs uppercase tracking-wider text-slate-500">Fix first</div>
        <ol class="mt-2 space-y-1.5">${a.top_risks.map((r, i) => `<li class="flex gap-3 text-sm"><span class="w-5 h-5 shrink-0 rounded-md bg-rose-500/15 text-rose-300 text-xs grid place-items-center font-semibold">${i + 1}</span><span class="text-slate-300">${esc(r)}</span></li>`).join('')}</ol>` : ''}
        <div class="mt-5 text-xs text-slate-500 font-mono">${esc(a.model)} · ${a.duration_s}s · ${a.stats.lines} lines · ${fmtTime(a.created_at)}</div>
      </div>
    </div>

    <div class="grid grid-cols-2 lg:grid-cols-4 gap-4 mt-4">
      ${tile('Issues found', a.stats.issues_total, 'across all three agents')}
      ${tile('Critical / High', `${sv.critical} / ${sv.high}`, 'need immediate attention', sv.critical + sv.high ? 'text-rose-300' : 'text-emerald-300')}
      ${tile('Static warnings', `${a.stats.static_confirmed}<span class="text-slate-500 text-xl">/${a.stats.static_total}</span>`, 'confirmed real by the judge')}
      ${tile('Noise removed', `${noise}%`, `${a.stats.static_rejected} false alarms rejected`, 'text-emerald-300')}
    </div>

    <div class="grid md:grid-cols-3 gap-4 mt-4">
      ${Object.entries(a.agents).map(([k, ag]) => {
        const col = ag.score >= 8 ? 'bg-emerald-400' : ag.score >= 5 ? 'bg-amber-400' : 'bg-rose-400';
        return `<div class="card p-5">
          <div class="flex items-center justify-between"><span class="text-sm font-medium text-white">${PIPE.find((p) => p.id === k).icon} ${AGENT_LABEL[k]}</span>
          <span class="text-2xl font-semibold text-white">${ag.score}<span class="text-sm text-slate-500">/10</span></span></div>
          <div class="h-1.5 rounded-full bg-ink-700 mt-3 overflow-hidden"><div class="h-full ${col} rounded-full transition-[width] duration-1000" style="width:0" data-w="${ag.score * 10}%"></div></div>
          <p class="text-xs text-slate-400 mt-3 leading-relaxed">${esc(ag.summary)}</p></div>`;
      }).join('')}
    </div>

    <div class="card mt-4">
      <div class="flex gap-1 px-3 border-b border-white/5 overflow-x-auto" id="tabs">
        <button class="tab active" data-tab="findings">Findings (${allIssues.length})</button>
        <button class="tab" data-tab="static">Static verification (${a.static.length})</button>
        <button class="tab" data-tab="diff">Auto-fix diff</button>
        <button class="tab" data-tab="code">Annotated code</button>
      </div>
      <div id="tab-findings" class="tabpane p-2">${renderFindings(allIssues)}</div>
      <div id="tab-static" class="tabpane p-2 hidden">${renderStatic(a.static, noise)}</div>
      <div id="tab-diff" class="tabpane hidden">${renderDiff(a)}</div>
      <div id="tab-code" class="tabpane hidden">${renderAnnotated(a.code, allIssues)}</div>
    </div>
  </div>`;

  document.querySelectorAll('#tabs .tab').forEach((t) => t.addEventListener('click', () => showTab(t.dataset.tab)));
  document.querySelectorAll('[data-goto]').forEach((el) => el.addEventListener('click', () => {
    showTab('code');
    const row = document.getElementById('L' + el.dataset.goto);
    if (row) row.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }));
  requestAnimationFrame(() => requestAnimationFrame(() => {
    document.querySelectorAll('[data-off]').forEach((c) => { c.style.strokeDashoffset = c.dataset.off; });
    document.querySelectorAll('[data-w]').forEach((b) => { b.style.width = b.dataset.w; });
  }));
}

function showTab(name) {
  document.querySelectorAll('#tabs .tab').forEach((t) => t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.tabpane').forEach((p) => p.classList.toggle('hidden', p.id !== 'tab-' + name));
}

function renderFindings(issues) {
  if (!issues.length) return '<div class="p-10 text-center text-emerald-300">✓ No issues found. The panel considers this code clean.</div>';
  return issues.map((i) => `
    <div class="flex gap-4 p-4 rounded-xl hover:bg-white/[.02]">
      <div class="pt-0.5 w-[74px] shrink-0">${sevBadge(i.severity)}</div>
      <div class="min-w-0 flex-1">
        <div class="flex flex-wrap items-center gap-x-3 gap-y-1">
          <span class="text-white font-medium">${esc(i.title)}</span>
          ${i.cwe ? `<span class="text-[11px] font-mono text-indigo-300 bg-indigo-500/10 px-1.5 py-0.5 rounded">${esc(i.cwe)}</span>` : ''}
        </div>
        <p class="text-sm text-slate-400 mt-1">${esc(i.description)}</p>
      </div>
      <div class="text-right shrink-0 text-xs">
        <div class="text-slate-500">${AGENT_LABEL[i.agent]}</div>
        ${i.line ? `<button data-goto="${i.line}" class="font-mono text-indigo-300 hover:underline mt-1">line ${i.line} →</button>` : ''}
      </div>
    </div>`).join('<div class="h-px bg-white/5 mx-4"></div>');
}

function renderStatic(findings, noise) {
  if (!findings.length) return '<div class="p-10 text-center text-slate-400">Bandit and Pylint raised no warnings for this code.</div>';
  const head = `<div class="p-4 flex items-center gap-4">
      <div class="flex-1 h-2.5 rounded-full bg-rose-400/70 overflow-hidden flex"><div class="h-full bg-emerald-400" style="width:${noise}%"></div></div>
      <div class="text-xs text-slate-400 shrink-0"><span class="text-emerald-300 font-semibold">${noise}%</span> of tool warnings were false alarms</div></div>`;
  return head + findings.map((f) => {
    const v = f.verdict === 'true_positive' ? ['Confirmed', 'text-rose-200 bg-rose-500/15 border-rose-500/30']
      : f.verdict === 'false_positive' ? ['False alarm', 'text-emerald-200 bg-emerald-500/15 border-emerald-500/30']
      : ['Unverified', 'text-slate-300 bg-white/5 border-white/10'];
    return `<div class="flex gap-4 p-4 rounded-xl hover:bg-white/[.02]">
      <span class="text-[11px] font-semibold px-2 py-1 rounded-md border h-fit w-[92px] text-center shrink-0 ${v[1]}">${v[0]}</span>
      <div class="min-w-0 flex-1">
        <div class="text-sm text-white"><span class="font-mono text-xs text-slate-500 mr-2">${esc(f.tool)} ${esc(f.rule)}</span>${esc(f.message)}</div>
        <div class="text-sm text-slate-400 mt-1"><span class="text-indigo-300">⚖ Judge:</span> ${esc(f.reason)}</div>
      </div>
      <button data-goto="${f.line}" class="font-mono text-xs text-indigo-300 hover:underline shrink-0 h-fit">line ${f.line} →</button>
    </div>`;
  }).join('<div class="h-px bg-white/5 mx-4"></div>');
}

function renderDiff(a) {
  if (!a.diff.length) return '<div class="p-10 text-center text-slate-400">The Chief Judge suggested no changes.</div>';
  const changed = a.diff.filter((r) => r.type !== 'equal').length;
  const rows = a.diff.map((r) => `<tr class="${r.type}">
      <td class="n">${r.l_no ?? ''}</td><td class="l">${esc(r.l ?? '')}</td>
      <td class="n border-l border-white/5">${r.r_no ?? ''}</td><td class="r">${esc(r.r ?? '')}</td></tr>`).join('');
  return `<div class="flex items-center gap-3 px-5 py-3 border-b border-white/5 text-xs">
      <span class="text-rose-300">Original</span><span class="text-slate-600">→</span><span class="text-emerald-300">Fixed by Chief Judge</span>
      <span class="text-slate-500 ml-2">${changed} changed lines</span>
      <button class="btn-ghost btn-sm ml-auto" onclick="copyFix()">Copy fixed code</button>
      <button class="btn-ghost btn-sm" onclick="applyFix()">Load fix into editor</button></div>
    <div class="overflow-auto max-h-[600px]"><table class="diff codeview w-full">${rows}</table></div>`;
}

function renderAnnotated(code, issues) {
  const byLine = {};
  issues.forEach((i) => { if (i.line) (byLine[i.line] ||= []).push(i); });
  const sevOrder = ['critical', 'high', 'medium', 'low'];
  return `<div class="overflow-auto max-h-[600px] py-3 codeview">${code.split('\n').map((ln, idx) => {
    const n = idx + 1, its = byLine[n];
    const worst = its ? its.map((i) => i.severity).sort((x, y) => sevOrder.indexOf(x) - sevOrder.indexOf(y))[0] : null;
    return `<div id="L${n}" class="row ${worst ? 'hl-' + worst : ''}"><span class="ln">${n}</span><span class="flex-1">${esc(ln) || ' '}</span>${
      its ? `<span class="px-3 text-[11px] text-slate-400 font-sans truncate max-w-[45%]">${its.map((i) => '● ' + esc(i.title)).join('  ')}</span>` : ''}</div>`;
  }).join('')}</div>`;
}

function copyFix() { navigator.clipboard.writeText(state.audit.fixed_code); toast('Fixed code copied'); }
function applyFix() {
  setCode(state.audit.fixed_code, state.audit.filename.replace(/\.py$/, '') + '_fixed.py');
  window.scrollTo({ top: 0, behavior: 'smooth' });
  toast('Fixed code loaded. Run the audit again to verify the fix.');
}

// ------------------------------------------------------------------ history
async function renderHistory() {
  const rows = await api('/api/history');
  const avg = rows.length ? (rows.reduce((s, r) => s + r.overall, 0) / rows.length).toFixed(1) : '–';
  const issues = rows.reduce((s, r) => s + r.issues, 0);
  const avgT = rows.length ? (rows.reduce((s, r) => s + r.duration_s, 0) / rows.length).toFixed(1) + 's' : '–';
  const dist = ['A', 'B', 'C', 'D', 'F'].map((g) => [g, rows.filter((r) => r.grade === g).length]);
  const max = Math.max(1, ...dist.map((d) => d[1]));
  $('#history-stats').innerHTML = `
    <div class="card p-5"><div class="text-[11px] uppercase tracking-wider text-slate-500">Audits run</div><div class="text-3xl font-semibold text-white mt-2">${rows.length}</div></div>
    <div class="card p-5"><div class="text-[11px] uppercase tracking-wider text-slate-500">Average score</div><div class="text-3xl font-semibold text-white mt-2">${avg}</div></div>
    <div class="card p-5"><div class="text-[11px] uppercase tracking-wider text-slate-500">Issues found · avg time</div><div class="text-3xl font-semibold text-white mt-2">${issues} <span class="text-lg text-slate-500">· ${avgT}</span></div></div>
    <div class="card p-5"><div class="text-[11px] uppercase tracking-wider text-slate-500">Grade distribution</div>
      <div class="flex items-end gap-2 h-12 mt-2">${dist.map(([g, n]) => `<div class="flex-1 flex flex-col items-center gap-1">
        <div class="w-full rounded-t grade-${g}" style="height:${Math.max(3, (40 * n) / max)}px"></div><div class="text-[10px] text-slate-500">${g}</div></div>`).join('')}</div></div>`;
  $('#history-body').innerHTML = rows.length ? rows.map((r) => `
    <tr class="border-b border-white/5 hover:bg-white/[.02]">
      <td class="px-5 py-3"><div class="grade grade-${r.grade} w-8 h-8">${r.grade}</div></td>
      <td class="px-3 py-3 font-mono text-slate-200">${esc(r.filename)}</td>
      <td class="px-3 py-3 text-white">${r.overall}</td>
      <td class="px-3 py-3">${r.issues}</td>
      <td class="px-3 py-3 font-mono text-xs text-slate-400">${esc(r.model)}</td>
      <td class="px-3 py-3 text-slate-400">${r.duration_s}s</td>
      <td class="px-3 py-3 text-slate-400">${fmtTime(r.created_at)}</td>
      <td class="px-5 py-3"><div class="flex justify-end gap-1.5">
        <button class="btn-ghost btn-sm" onclick="openAudit(${r.id})">View</button>
        <a class="btn-ghost btn-sm" href="/api/history/${r.id}/report.pdf">PDF</a>
        <button class="btn-ghost btn-sm hover:!text-rose-300" onclick="deleteAudit(${r.id})">✕</button></div></td>
    </tr>`).join('') : '<tr><td colspan="8" class="p-10 text-center text-slate-500">No audits yet. Run one from the Audit page.</td></tr>';
}

async function openAudit(id) {
  const a = await api(`/api/history/${id}`);
  state.audit = a;
  location.hash = '#audit';
  setTimeout(() => {
    setCode(a.code, a.filename);
    renderPipeline({});
    renderResult(a);
    $('#results').scrollIntoView({ behavior: 'smooth' });
  }, 50);
}

async function deleteAudit(id) {
  if (!confirm('Delete this audit from history?')) return;
  await api(`/api/history/${id}`, { method: 'DELETE' });
  renderHistory();
}

// ------------------------------------------------------------------ about
function renderAbout() {
  const node = (t, s, c = '') => `<div class="arch-node ${c}"><div class="text-white font-medium text-sm">${t}</div><div class="text-xs text-slate-400 mt-1">${s}</div></div>`;
  $('#arch').innerHTML = `
    ${node('📄 Input', 'Python file: pasted, uploaded or a demo sample. Line-numbered before analysis.')}
    <div class="arch-arrow">↓</div>
    ${node('⚙ Static analysis layer', 'Bandit (security rules, CWE mapped) + Pylint (bugs). Fast and deterministic but noisy.')}
    <div class="arch-arrow">↓</div>
    <div class="grid md:grid-cols-3 gap-3">
      ${node('🛡 Security Agent', 'Injection, secrets, weak crypto, deserialization. Rubric score 1–10 + CWE ids.', 'border-indigo-500/30')}
      ${node('⚡ Performance Agent', 'Complexity, repeated work in loops, leaks. Rubric score 1–10.', 'border-indigo-500/30')}
      ${node('✦ Code Quality Agent', 'Logic bugs, edge cases, error handling. Rubric score 1–10.', 'border-indigo-500/30')}
    </div>
    <div class="arch-arrow">↓</div>
    ${node('⚖ Verification Judge', 'Reads every static-tool warning in context and labels it true positive or false positive with a reason.', 'border-violet-500/30')}
    <div class="arch-arrow">↓</div>
    ${node('★ Chief Judge', 'Combines all reports: executive verdict, top risks, and a complete auto-fixed file.', 'border-fuchsia-500/30')}
    <div class="arch-arrow">↓</div>
    ${node('📊 Deterministic scoring', 'Overall = 0.5·Security + 0.25·Quality + 0.25·Performance. A critical vulnerability caps the grade at D.')}
    <div class="grid md:grid-cols-3 gap-3 mt-8 text-sm">
      ${node('🔒 Fully local', 'Ollama runs the LLM on your own GPU. Code never leaves the machine.')}
      ${node('🧾 Structured outputs', 'Every agent must answer in a strict JSON schema, so results are always machine-readable.')}
      ${node('🎯 Reproducible', 'Temperature 0 and a fixed seed: the same code gets the same verdict.')}
    </div>`;
}

// ------------------------------------------------------------------ boot
(async function boot() {
  await initEditor();
  await refreshStatus();
  route();
  setInterval(refreshStatus, 4000);
})();
