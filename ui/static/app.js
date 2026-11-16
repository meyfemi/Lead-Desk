/* Lead Desk - vanilla SPA over the /api endpoints in ui/server.py */

const S = {
  files: [], file: null, leads: [], stats: null, timeline: [], followups: [],
  statuses: [], today: '', mail: false, apify: false, claudeCli: false, claudeKey: false,
  identity: { company_name: '', default_location: '', default_categories: [] },
  view: 'overview', query: '', filter: 'all', selection: new Set(),
  openLead: null, job: null, jobPoll: null,
  // Discover form. null = "use the default from .env" until the user edits the field.
  fl: { loc: null, cnt: 10, cats: null, mode: 'research' },
};

const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) =>
  ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const STATUS_META = {
  'Draft - Needs Copy': { cls: 'draft', color: '#9a6100', short: 'Draft' },
  'Ready to Send': { cls: 'ready', color: '#3b53d4', short: 'Ready' },
  'Sent': { cls: 'sent', color: '#12805c', short: 'Sent' },
  'Followed Up 1': { cls: 'fu', color: '#6836c4', short: 'Follow-up 1' },
  'Followed Up 2 (Final)': { cls: 'fu', color: '#9a6cf0', short: 'Follow-up 2' },
  'Send Failed': { cls: 'failed', color: '#b42318', short: 'Failed' },
  'No Email - Skip Send': { cls: 'skip', color: '#9aa1ab', short: 'No email' },
};
const meta = (s) => STATUS_META[s] || { cls: 'skip', color: '#9aa1ab', short: s || '-' };
const badge = (s) => `<span class="badge ${meta(s).cls}">${esc(meta(s).short)}</span>`;
const hasEmail = (l) => { const e = (l['Company Email'] || '').trim(); return e && e.toLowerCase() !== 'not found'; };

/* ── API ─────────────────────────────────────────────────── */
async function api(path, body) {
  const opts = body
    ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
    : {};
  const res = await fetch(path, opts);
  const data = await res.json().catch(() => ({ error: 'bad response' }));
  if (!res.ok || data.error) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function toast(msg, kind = '') {
  const el = document.createElement('div');
  el.className = `toast ${kind}`;
  el.textContent = msg;
  $('#toasts').appendChild(el);
  setTimeout(() => el.remove(), 4200);
}

async function load(file) {
  const q = file ? `?file=${encodeURIComponent(file)}` : '';
  const d = await api(`/api/bootstrap${q}`);
  Object.assign(S, {
    files: d.files, file: d.file, leads: d.leads, stats: d.stats,
    timeline: d.timeline, followups: d.followups, statuses: d.statuses,
    today: d.today, mail: d.mail_configured, apify: d.apify_configured,
    claudeCli: d.claude_cli, claudeKey: d.claude_key_configured,
    identity: d.identity || S.identity,
  });
  S.selection = new Set([...S.selection].filter((i) => i < S.leads.length));
  render();
}

/* ── Shell ───────────────────────────────────────────────── */
const TITLES = {
  overview: ['Overview', 'Pipeline health at a glance'],
  leads: ['Leads', 'Every company in the current file'],
  followups: ['Follow-ups', 'Leads whose next touch is due'],
  discover: ['Discover', 'Find new businesses via Apify Google Maps'],
  activity: ['Activity', 'Job output and the send log'],
};

/* Company name from .env drives the title, sidebar and favicon initial. */
function renderBrand() {
  const name = (S.identity.company_name || '').trim();
  const initial = (name || 'L').charAt(0).toUpperCase();
  document.title = name ? `Lead Desk - ${name}` : 'Lead Desk';
  $('#brand-mark').textContent = initial;
  $('#brand-sub').textContent = name ? `${name} outreach` : 'Outreach';
  $('#favicon').href = 'data:image/svg+xml,' + encodeURIComponent(
    `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='8' fill='#3b53d4'/>`
    + `<text x='16' y='23' font-size='18' font-family='sans-serif' font-weight='bold' fill='white' text-anchor='middle'>${initial}</text></svg>`);
}

function go(view) {
  S.view = view;
  if (location.hash.slice(1) !== view) location.hash = view;
  else render();
}

function render() {
  if (!TITLES[S.view]) S.view = 'overview';
  const [title, sub] = TITLES[S.view];
  $('#page-title').textContent = title;
  $('#page-sub').textContent = S.file ? `${sub} · ${S.file}` : sub;
  $('#pill-leads').textContent = S.leads.length;
  $('#pill-fu').textContent = S.followups.length;
  $('#dot-apify').className = `dot ${S.apify ? 'on' : 'off'}`;
  $('#dot-mail').className = `dot ${S.mail ? 'on' : 'off'}`;
  $('#dot-claude').className = `dot ${S.claudeKey ? 'on' : 'off'}`;
  renderBrand();

  document.querySelectorAll('#nav button').forEach((b) =>
    b.classList.toggle('active', b.dataset.view === S.view));

  const sel = $('#file-select');
  sel.innerHTML = S.files.map((f) =>
    `<option value="${esc(f.file)}" ${f.file === S.file ? 'selected' : ''}>${esc(f.label)} (${f.count})</option>`
  ).join('') || '<option>No lead files yet</option>';

  $('#view').innerHTML = ({
    overview: viewOverview, leads: viewLeads, followups: viewFollowups,
    discover: viewDiscover, activity: viewActivity,
  })[S.view]();

  wire();
  renderDrawer();
}

/* ── Overview ────────────────────────────────────────────── */
function viewOverview() {
  const st = S.stats || { total: 0, by_status: {}, contacted: 0, reachable: 0, coverage: 0, followups_due: 0 };
  const drafts = (st.by_status['Draft - Needs Copy'] || 0);
  const ready = (st.by_status['Ready to Send'] || 0);

  const segments = Object.entries(st.by_status)
    .filter(([, n]) => n > 0)
    .map(([s, n]) => ({ s, n, pct: (100 * n / Math.max(1, st.total)) }));

  const bar = segments.map((g) =>
    `<div style="width:${g.pct}%;background:${meta(g.s).color}" title="${esc(g.s)}: ${g.n}"></div>`).join('')
    || '<div style="width:100%;background:var(--border)"></div>';

  const legend = segments.map((g) => `
    <div class="legend-item">
      <span class="swatch" style="background:${meta(g.s).color}"></span>
      ${esc(g.s)} <b>${g.n}</b>
    </div>`).join('') || '<div class="legend-item">No leads yet</div>';

  const due = S.followups.slice(0, 6).map((f) => `
    <tr data-lead="${f.id}">
      <td><div class="cell-name">${esc(f['Company Name'])}</div>
          <div class="cell-sub">${esc(f['Company Email'])}</div></td>
      <td>${badge(f['Status'])}</td>
      <td style="color:var(--muted);white-space:nowrap">
        ${esc(f.due_date)} ${f.due_date < S.today ? '<span class="badge failed">overdue</span>' : ''}
      </td>
    </tr>`).join('');

  return `
    <div class="stat-grid">
      ${statCard('Total leads', st.total, `${st.reachable} with an email address`)}
      ${statCard('Contacted', st.contacted, `${st.coverage}% of reachable leads`, 'green')}
      ${statCard('Queued to send', ready, ready ? 'copy written, ready to go' : 'nothing waiting', 'accent')}
      ${statCard('Follow-ups due', st.followups_due, st.followups_due ? 'needs a touch today' : 'all caught up', st.followups_due ? 'amber' : '')}
    </div>

    <div class="grid-2">
      <div class="card">
        <div class="card-head"><h2>Pipeline breakdown</h2></div>
        <div class="card-body">
          <div class="statusbar">${bar}</div>
          <div class="legend">${legend}</div>
          ${drafts ? `<p class="hint" style="margin:18px 0 0">
            <b>${drafts}</b> lead${drafts > 1 ? 's have' : ' has'} no outreach copy yet.
            Open each one from the Leads tab to write it, or ask Claude Code to draft copy for the
            “Draft - Needs Copy” rows in this file. (A new <span class="kbd">/find-leads</span> run
            skips companies already in the file.)</p>` : ''}
        </div>
      </div>

      <div class="card">
        <div class="card-head"><h2>Outreach volume</h2><div class="spacer"></div>
          <span class="hint">last 30 days</span></div>
        <div class="card-body">${chart(S.timeline)}</div>
      </div>
    </div>

    <div class="card" style="margin-top:14px">
      <div class="card-head"><h2>Follow-ups due</h2><div class="spacer"></div>
        <button class="btn sm" data-goto="followups">Open follow-ups →</button></div>
      ${due ? `<div class="table-wrap"><table><thead><tr>
          <th>Company</th><th>Stage</th><th>Due</th></tr></thead>
          <tbody>${due}</tbody></table></div>`
      : `<div class="empty"><div class="big">✓</div>Nothing due - the pipeline is caught up.</div>`}
    </div>`;
}

function statCard(k, v, n, tone = '') {
  return `<div class="card stat"><div class="k">${esc(k)}</div>
    <div class="v ${tone}">${v}</div><div class="n">${esc(n)}</div></div>`;
}

function chart(series) {
  if (!series.length || series.every((p) => !p.count)) {
    return '<div class="empty" style="padding:26px">No sends recorded yet.</div>';
  }
  const max = Math.max(...series.map((p) => p.count), 1);
  const w = 100 / series.length;
  const bars = series.map((p, i) => {
    const h = p.count ? Math.max(6, (p.count / max) * 92) : 3;
    return `<rect class="bar ${p.count ? '' : 'zero'}" x="${(i * w) + w * 0.15}%"
      y="${100 - h}%" width="${w * 0.7}%" height="${h}%" rx="1.5">
      <title>${p.date}: ${p.count} sent</title></rect>`;
  }).join('');
  return `<svg class="chart" preserveAspectRatio="none">${bars}</svg>
    <div style="display:flex;justify-content:space-between;font-size:11px;color:var(--faint);margin-top:6px">
      <span>${series[0].date}</span><span>peak ${max}/day</span><span>${series.at(-1).date}</span></div>`;
}

/* ── Leads ───────────────────────────────────────────────── */
function filteredLeads() {
  const q = S.query.trim().toLowerCase();
  return S.leads.filter((l) => {
    if (S.filter === 'all') { /* keep */ }
    else if (S.filter === '__noemail') { if (hasEmail(l)) return false; }
    else if (l['Status'] !== S.filter) return false;
    if (!q) return true;
    return ['Company Name', 'Company Email', 'Company URL', 'Company Address', 'Company Summary']
      .some((k) => (l[k] || '').toLowerCase().includes(q));
  });
}

function viewLeads() {
  const rows = filteredLeads();
  const opts = ['<option value="all">All statuses</option>']
    .concat(S.statuses.map((s) => `<option value="${esc(s)}" ${S.filter === s ? 'selected' : ''}>${esc(s)}</option>`))
    .concat([`<option value="__noemail" ${S.filter === '__noemail' ? 'selected' : ''}>Missing email</option>`])
    .join('');

  const body = rows.map((l) => `
    <tr data-lead="${l.id}" class="${S.selection.has(l.id) ? 'selected' : ''}">
      <td class="tight"><input type="checkbox" data-check="${l.id}" ${S.selection.has(l.id) ? 'checked' : ''}></td>
      <td>
        <div class="cell-name">${esc(l['Company Name'])}</div>
        <div class="cell-sub truncate">${esc(l['Company Address'] || '-')}</div>
      </td>
      <td>${hasEmail(l)
      ? `<span class="truncate" style="display:block">${esc(l['Company Email'])}</span>`
      : '<span style="color:var(--faint)">no email</span>'}</td>
      <td>${badge(l['Status'])}</td>
      <td style="color:var(--muted);white-space:nowrap">${esc(l['Date Contacted'] || '-')}</td>
      <td style="color:var(--muted)">${l['First Mail Body'] ? '✎ written' : '<span style="color:var(--faint)">-</span>'}</td>
    </tr>`).join('');

  const n = S.selection.size;
  return `
    <div class="card">
      <div class="toolbar">
        <input class="search" type="text" id="q" placeholder="Search name, email, address, summary…" value="${esc(S.query)}">
        <select id="filter">${opts}</select>
        <div style="flex:1"></div>
        <span class="hint">${rows.length} of ${S.leads.length}</span>
      </div>

      ${n ? `<div class="selection-bar">
        <span>${n} selected</span>
        <div class="spacer"></div>
        <button class="btn sm" id="bulk-enrich">Enrich from website</button>
        <button class="btn sm" id="bulk-dry">Dry-run send</button>
        <button class="btn sm primary" id="bulk-send">Send first mail</button>
        <button class="btn sm" id="bulk-clear">Clear</button>
      </div>` : ''}

      <div class="table-wrap">
        <table>
          <thead><tr>
            <th class="tight"><input type="checkbox" id="check-all"></th>
            <th>Company</th><th>Email</th><th>Status</th><th>Contacted</th><th>Copy</th>
          </tr></thead>
          <tbody>${body}</tbody>
        </table>
      </div>
      ${rows.length ? '' : '<div class="empty"><div class="big">⌕</div>No leads match this filter.</div>'}
    </div>`;
}

/* ── Follow-ups ──────────────────────────────────────────── */
function viewFollowups() {
  if (!S.followups.length) {
    return `<div class="card"><div class="empty"><div class="big">✓</div>
      No follow-ups due. The next one appears here on its scheduled date.</div></div>`;
  }
  const rows = S.followups.map((f) => {
    const bodyKey = `Followup ${f.followup_stage} Body`;
    const written = (f[bodyKey] || '').trim();
    return `
    <tr data-lead="${f.id}">
      <td><div class="cell-name">${esc(f['Company Name'])}</div>
          <div class="cell-sub">${esc(f['Company Email'])}</div></td>
      <td>Touch ${f.followup_stage}</td>
      <td style="white-space:nowrap">${esc(f.due_date)}
        ${f.due_date < S.today ? '<span class="badge failed">overdue</span>' : ''}</td>
      <td>${written ? '<span class="badge ready">drafted</span>'
        : '<span class="badge draft">needs copy</span>'}</td>
      <td style="text-align:right">
        <button class="btn sm ${written ? 'primary' : ''}" data-fu-send="${f.id}"
          data-stage="${f.followup_stage}" ${written ? '' : 'disabled'}>Send</button>
      </td>
    </tr>`;
  }).join('');

  return `
    <div class="card">
      <div class="card-head"><h2>${S.followups.length} due</h2><div class="spacer"></div>
        <span class="hint">Click a row to write or edit the follow-up copy</span></div>
      <div class="table-wrap"><table><thead><tr>
        <th>Company</th><th>Stage</th><th>Due</th><th>Copy</th><th></th>
      </tr></thead><tbody>${rows}</tbody></table></div>
    </div>`;
}

/* ── Discover ────────────────────────────────────────────── */
/* "details" runs Apify + the scraper straight from the server; the other two run
   /find-leads through the claude CLI. */
const SCOPES = {
  details: { label: 'Find details only', button: 'Find details', running: 'Finding…', engine: 'Apify + website scrape' },
  research: { label: 'Research & draft only', button: 'Run /find-leads', running: 'Running…', engine: '/find-leads via Claude Code' },
  full: { label: 'Research, draft and send', button: 'Run /find-leads', running: 'Running…', engine: '/find-leads via Claude Code' },
};
const DISCOVER_JOBS = ['findleads', 'finddetails', 'pending'];

/* Form values come from state so the periodic re-render during a job keeps what was typed. */
function flForm() {
  const f = S.fl;
  return {
    loc: f.loc ?? (S.identity.default_location || ''),
    cats: f.cats ?? (S.identity.default_categories || []).join(', '),
    cnt: f.cnt,
    mode: SCOPES[f.mode] ? f.mode : 'research',
  };
}

function viewDiscover() {
  const f = flForm();
  const scope = SCOPES[f.mode];
  const isDetails = f.mode === 'details';
  const running = S.job && S.job.state === 'running' && DISCOVER_JOBS.includes(S.job.kind);
  const ready = isDetails ? S.apify : (S.claudeCli && S.claudeKey);

  const red = (msg) => `<br><span style="color:var(--red)">${msg}</span>`;
  const missing = isDetails
    ? (S.apify ? '' : red('APIFY_API_KEY is missing from .env - required to find details.'))
    : (S.claudeCli ? '' : red('The <b>claude</b> CLI was not found on PATH.'))
      + (S.claudeKey ? '' : red('ANTHROPIC_API_KEY is missing from .env - required to run /find-leads from here.'));

  const explain = isDetails
    ? `<b>Find details only</b> searches Google Maps through Apify, then scrapes each website
       for the contact email, phone, a named contact and a short factual summary. It writes no
       outreach copy and sends nothing: leads are filed as “Draft - Needs Copy”, and businesses
       with no email address are skipped entirely. Claude is not involved, so it costs only Apify
       credits and usually finishes in 5–15 minutes.`
    : `The run searches, scrapes each website, writes company-specific outreach copy and files
       every lead into the CSV - the same workflow as typing <span class="kbd">/find-leads</span>
       in Claude Code. Expect 15–40 minutes. <b>Research &amp; draft</b> stops before sending and
       leaves the leads at “Ready to Send” for you to review here.`;

  return `
    <div class="card" style="margin-bottom:14px">
      <div class="card-head"><h2>Find leads</h2><div class="spacer"></div>
        <span class="hint">${esc(scope.engine)}</span></div>
      <div class="card-body">
        <div style="display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap">
          <label class="field" style="margin:0;flex:1;min-width:180px"><span>Location</span>
            <input type="text" id="fl-loc" placeholder="City, Country" value="${esc(f.loc)}"></label>
          <label class="field" style="margin:0;width:110px"><span>Leads</span>
            <input type="number" id="fl-cnt" value="${esc(f.cnt)}" min="1" max="200"></label>
          <label class="field" style="margin:0;width:230px"><span>Scope</span>
            <select id="fl-mode">${Object.entries(SCOPES).map(([k, s]) =>
              `<option value="${k}" ${k === f.mode ? 'selected' : ''}>${esc(s.label)}</option>`).join('')}</select></label>
          <button class="btn primary" id="run-findleads" ${running || !ready ? 'disabled' : ''}
            style="margin-bottom:0">${running ? `<span class="spinner"></span> ${scope.running}` : scope.button}</button>
        </div>
        <label class="field" style="margin:12px 0 0"><span>Business categories to search</span>
          <input type="text" id="fl-cats" placeholder="e.g. dentist, gym, car wash" value="${esc(f.cats)}"></label>
        <p class="hint" style="margin:14px 0 0">
          Comma-separated. Each category becomes a Google Maps search in the location; blank
          uses <span class="kbd">DEFAULT_CATEGORIES</span> from .env. ${explain}${missing}
        </p>
      </div>
    </div>

    <div class="card">
      <div class="card-head"><h2>Run output</h2></div>
      <div class="card-body">${consoleBlock(
    S.job && DISCOVER_JOBS.includes(S.job.kind) ? S.job : null,
    'Start a run and its progress appears here.')}</div>
    </div>`;
}

/* ── Activity ────────────────────────────────────────────── */
function viewActivity() {
  return `
    <div class="card">
      <div class="card-head"><h2>Current job</h2>${S.job && S.job.state === 'running'
      ? '<span class="spinner" style="margin-left:6px"></span>' : ''}</div>
      <div class="card-body">${consoleBlock(S.job, 'No job has run in this session yet.')}</div>
    </div>
    <div class="card" style="margin-top:14px">
      <div class="card-head"><h2>Send log</h2><div class="spacer"></div>
        <span class="hint">leads/send_log.txt</span></div>
      <div class="card-body"><div class="console" id="sendlog">loading…</div></div>
    </div>`;
}

function consoleBlock(job, placeholder) {
  if (!job) return `<div class="empty" style="padding:26px">${esc(placeholder)}</div>`;
  const lines = job.log.map((l) => {
    const cls = /^✓|SENT/.test(l) ? 'ok' : /^✗|FAILED|Error|error/.test(l) ? 'err'
      : /^[$·–]/.test(l) ? 'dim' : '';
    return `<span class="${cls}">${esc(l)}</span>`;
  }).join('\n');
  const tail = job.state === 'error' ? `\n<span class="err">✗ ${esc(job.error)}</span>`
    : job.stopped ? ''
      : job.state === 'done' ? '\n<span class="dim">- finished -</span>' : '';
  const stop = job.state === 'running' && (job.kind === 'findleads' || job.kind === 'finddetails')
    ? `<div style="margin-top:10px"><button class="btn sm danger" id="stop-job">Stop run</button></div>` : '';
  return `<div class="console" data-autoscroll>${lines || '<span class="dim">starting…</span>'}${tail}</div>${stop}`;
}

/* ── Drawer ──────────────────────────────────────────────── */
function renderDrawer() {
  const drawer = $('#drawer');
  const open = S.openLead !== null;
  $('#scrim').classList.toggle('open', open);
  drawer.classList.toggle('open', open);
  drawer.setAttribute('aria-hidden', String(!open));
  if (!open) { drawer.innerHTML = ''; return; }

  const l = S.leads[S.openLead];
  if (!l) { S.openLead = null; return; }

  const fu = S.followups.find((f) => f.id === l.id);
  const stage = fu ? fu.followup_stage : 0;
  const bodyField = stage ? `Followup ${stage} Body` : 'First Mail Body';
  const canSend = hasEmail(l) && (l['Email Subject'] || '').trim() && (l[bodyField] || '').trim();

  drawer.innerHTML = `
    <div class="drawer-head">
      <div style="flex:1;min-width:0">
        <h2>${esc(l['Company Name'])}</h2>
        <div style="margin-top:6px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          ${badge(l['Status'])}
          ${l['Company URL'] ? `<a href="${esc(l['Company URL'])}" target="_blank" rel="noopener"
            style="font-size:12.5px">${esc(l['Company URL'].replace(/^https?:\/\//, ''))} ↗</a>` : ''}
        </div>
      </div>
      <button class="icon-btn" id="drawer-close" title="Close (Esc)">×</button>
    </div>

    <div class="drawer-body">
      <div class="meta-grid">
        <div class="meta"><div class="k">Email</div><div class="v">${esc(l['Company Email'] || '-')}</div></div>
        <div class="meta"><div class="k">Phone</div><div class="v">${esc(l['Company Phone'] || '-')}</div></div>
        <div class="meta"><div class="k">Contact</div><div class="v">${esc(l['Company CEO'] || '-')}</div></div>
        <div class="meta"><div class="k">Contacted</div><div class="v">${esc(l['Date Contacted'] || 'never')}</div></div>
        <div class="meta" style="grid-column:1/-1"><div class="k">Address</div>
          <div class="v">${esc(l['Company Address'] || '-')}</div></div>
      </div>

      ${l['Company Summary'] ? `<div class="section-title">Summary</div>
        <div class="prose">${esc(l['Company Summary'])}</div>` : ''}
      ${l['Specific Sales Edges'] ? `<div class="section-title">Sales edges</div>
        <div class="prose">${esc(l['Specific Sales Edges'])}</div>` : ''}

      <div class="section-title">${stage ? `Follow-up ${stage} (due ${esc(fu.due_date)})` : 'First mail'}</div>
      <label class="field"><span>Subject</span>
        <input type="text" id="f-subject" value="${esc(l['Email Subject'])}"
          placeholder="5–8 words, referencing something specific"></label>
      <label class="field"><span>${stage ? `Follow-up ${stage} body` : 'Body'}</span>
        <textarea id="f-body" rows="12" placeholder="${stage
      ? '2–3 sentences, a fresh angle, same sign-off.'
      : 'Four short paragraphs, 100–150 words.'}">${esc(l[bodyField])}</textarea></label>

      <div class="meta-grid">
        <label class="field" style="margin:0"><span>Contact email</span>
          <input type="text" id="f-email" value="${esc(l['Company Email'])}"></label>
        <label class="field" style="margin:0"><span>Status</span>
          <select id="f-status">${S.statuses.map((s) =>
        `<option ${s === l['Status'] ? 'selected' : ''}>${esc(s)}</option>`).join('')}</select></label>
      </div>

      <div class="section-title">Schedule</div>
      <div class="meta-grid">
        <label class="field" style="margin:0"><span>Follow-up 1 date</span>
          <input type="text" id="f-fu1" value="${esc(l['Followup 1 Date'])}" placeholder="YYYY-MM-DD"></label>
        <label class="field" style="margin:0"><span>Follow-up 2 date</span>
          <input type="text" id="f-fu2" value="${esc(l['Followup 2 Date'])}" placeholder="YYYY-MM-DD"></label>
      </div>
    </div>

    <div class="drawer-foot">
      <button class="btn primary" id="d-save">Save</button>
      <button class="btn" id="d-enrich">Enrich from site</button>
      <div style="flex:1"></div>
      <button class="btn" id="d-dry" ${canSend ? '' : 'disabled'}>Dry run</button>
      <button class="btn primary" id="d-send" ${canSend && S.mail ? '' : 'disabled'}
        data-stage="${stage}">Send ${stage ? `follow-up ${stage}` : 'now'}</button>
    </div>`;

  const patch = () => ({
    'Email Subject': $('#f-subject').value,
    [bodyField]: $('#f-body').value,
    'Company Email': $('#f-email').value,
    'Status': $('#f-status').value,
    'Followup 1 Date': $('#f-fu1').value.trim(),
    'Followup 2 Date': $('#f-fu2').value.trim(),
  });

  const save = async () => {
    await api('/api/lead/update', { file: S.file, id: l.id, patch: patch() });
    await load(S.file);
  };

  $('#drawer-close').onclick = closeDrawer;
  $('#d-save').onclick = async () => { await save(); toast('Saved', 'ok'); };
  $('#d-enrich').onclick = () => startJob('/api/enrich', { file: S.file, ids: [l.id] });
  $('#d-dry').onclick = async () => {
    await save();
    startJob('/api/send', { file: S.file, ids: [l.id], stage, dry_run: true });
  };
  $('#d-send').onclick = async () => {
    if (!confirm(`Send this ${stage ? `follow-up ${stage}` : 'email'} to ${l['Company Email']}?\n\nThis delivers a real email via Mailtrap.`)) return;
    await save();
    closeDrawer();
    startJob('/api/send', { file: S.file, ids: [l.id], stage, dry_run: false });
  };
}

function openDrawer(id) { S.openLead = id; renderDrawer(); }
function closeDrawer() { S.openLead = null; renderDrawer(); }

/* ── Jobs ────────────────────────────────────────────────── */
async function startJob(path, body) {
  try {
    const { job } = await api(path, body);
    clearInterval(S.jobPoll);
    S.job = { id: job, kind: 'pending', state: 'running', log: [] };
    if (S.view !== 'discover') go('activity'); else render();
    S.jobPoll = setInterval(() => pollJob(job), 1200);
    pollJob(job);
  } catch (e) { toast(e.message, 'err'); }
}

async function pollJob(id) {
  try {
    const job = await api(`/api/jobs/${id}`);
    S.job = job;
    if (job.state !== 'running') {
      clearInterval(S.jobPoll);
      let file = S.file;
      if (job.kind === 'send' && job.result) {
        const { sent, failed, dry_run } = job.result;
        toast(`${sent.length} ${dry_run ? 'would send' : 'sent'}, ${failed.length} failed`,
          failed.length ? 'err' : 'ok');
      } else if (job.kind === 'findleads' && job.result) {
        toast(job.result.stopped ? '/find-leads run stopped' : '/find-leads run finished',
          job.result.stopped ? '' : 'ok');
      } else if (job.kind === 'finddetails' && job.result) {
        const r = job.result;
        const n = `${r.added} lead${r.added === 1 ? '' : 's'}`;
        toast(r.stopped ? `Stopped - ${n} saved to ${r.file}`
          : `${n} saved to ${r.file}${r.skipped_no_email ? ` (${r.skipped_no_email} skipped - no email)` : ''}`,
          r.stopped ? '' : 'ok');
        if (r.added) file = r.file;  // show the file the new rows went into
      } else if (job.state === 'error') {
        toast(job.error, 'err');
      }
      await load(file);
      return;
    }
    if (S.view === 'activity' || S.view === 'discover') render();
  } catch (e) {
    clearInterval(S.jobPoll);
    toast(e.message, 'err');
  }
}

/* ── Wiring ──────────────────────────────────────────────── */
function wire() {
  const v = $('#view');

  v.querySelectorAll('[data-goto]').forEach((b) =>
    b.onclick = () => go(b.dataset.goto));

  v.querySelectorAll('tr[data-lead]').forEach((tr) => {
    tr.onclick = (e) => {
      if (e.target.matches('input,button')) return;
      openDrawer(Number(tr.dataset.lead));
    };
  });

  v.querySelectorAll('[data-check]').forEach((cb) => {
    cb.onclick = (e) => {
      e.stopPropagation();
      const id = Number(cb.dataset.check);
      cb.checked ? S.selection.add(id) : S.selection.delete(id);
      render();
    };
  });

  const all = $('#check-all', v);
  if (all) all.onclick = () => {
    const ids = filteredLeads().map((l) => l.id);
    if (all.checked) ids.forEach((i) => S.selection.add(i));
    else ids.forEach((i) => S.selection.delete(i));
    render();
  };

  const q = $('#q', v);
  if (q) {
    q.oninput = () => { S.query = q.value; render(); $('#q').focus(); };
    if (S.query) { q.focus(); q.setSelectionRange(q.value.length, q.value.length); }
  }
  const filter = $('#filter', v);
  if (filter) filter.onchange = () => { S.filter = filter.value; render(); };

  const ids = () => [...S.selection];
  const bind = (sel, fn) => { const el = $(sel, v); if (el) el.onclick = fn; };

  bind('#bulk-clear', () => { S.selection.clear(); render(); });
  bind('#bulk-enrich', () => startJob('/api/enrich', { file: S.file, ids: ids() }));
  bind('#bulk-dry', () => startJob('/api/send', { file: S.file, ids: ids(), stage: 0, dry_run: true }));
  bind('#bulk-send', () => {
    const targets = S.leads.filter((l) => S.selection.has(l.id));
    const sendable = targets.filter((l) => hasEmail(l) && (l['First Mail Body'] || '').trim());
    if (!sendable.length) return toast('None of the selected leads have an email and body', 'err');
    if (!confirm(`Send ${sendable.length} real email${sendable.length > 1 ? 's' : ''} via Mailtrap?\n\n`
      + sendable.slice(0, 8).map((l) => `• ${l['Company Name']} <${l['Company Email']}>`).join('\n')
      + (sendable.length > 8 ? `\n…and ${sendable.length - 8} more` : ''))) return;
    startJob('/api/send', { file: S.file, ids: sendable.map((l) => l.id), stage: 0, dry_run: false });
  });

  v.querySelectorAll('[data-fu-send]').forEach((b) => {
    b.onclick = (e) => {
      e.stopPropagation();
      const id = Number(b.dataset.fuSend), stage = Number(b.dataset.stage);
      const l = S.leads[id];
      if (!confirm(`Send follow-up ${stage} to ${l['Company Name']} <${l['Company Email']}>?`)) return;
      startJob('/api/send', { file: S.file, ids: [id], stage, dry_run: false });
    };
  });

  // Discover form: mirror every field into state so a re-render keeps it. A scope change
  // re-renders because the button, hint and enable rule depend on it.
  const flField = (sel, key) => { const el = $(sel, v); if (el) el.oninput = () => { S.fl[key] = el.value; }; };
  flField('#fl-loc', 'loc');
  flField('#fl-cats', 'cats');
  flField('#fl-cnt', 'cnt');
  const flMode = $('#fl-mode', v);
  if (flMode) flMode.onchange = () => { S.fl.mode = flMode.value; render(); };

  bind('#run-findleads', () => {
    const location = $('#fl-loc', v).value.trim();
    const categories = $('#fl-cats', v).value.trim();
    const count = Number($('#fl-cnt', v).value);
    const mode = $('#fl-mode', v).value;
    if (!location) return toast('Enter a location', 'err');
    if (mode === 'full' && !confirm(
      `Run /find-leads for ${count} leads in ${location} AND send the outreach emails?\n\n`
      + 'Real emails go out at the end of the run without a further prompt.')) return;
    startJob('/api/find-leads', { location, count, mode, categories });
  });

  bind('#stop-job', async () => {
    try { await api('/api/jobs/stop', { id: S.job.id }); toast('Stopping…'); }
    catch (e) { toast(e.message, 'err'); }
  });

  v.querySelectorAll('.console[data-autoscroll]').forEach((el) => {
    el.scrollTop = el.scrollHeight;
  });

  if (S.view === 'activity') {
    api('/api/log').then((d) => {
      const el = $('#sendlog');
      if (!el) return;
      el.innerHTML = (d.log || 'No sends logged yet.').split('\n').map((line) => {
        const cls = line.startsWith('✓') ? 'ok' : line.startsWith('✗') ? 'err'
          : line.startsWith('===') ? 'dim' : '';
        return `<span class="${cls}">${esc(line)}</span>`;
      }).join('\n');
      el.scrollTop = el.scrollHeight;
    }).catch(() => { });
  }
}

/* ── Boot ────────────────────────────────────────────────── */
document.querySelectorAll('#nav button').forEach((b) =>
  b.onclick = () => go(b.dataset.view));
$('#btn-refresh').onclick = () => load(S.file).then(() => toast('Refreshed'));
$('#file-select').onchange = (e) => { S.selection.clear(); load(e.target.value); };
$('#scrim').onclick = closeDrawer;
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && S.openLead !== null) closeDrawer();
});

window.addEventListener('hashchange', () => {
  const view = location.hash.slice(1);
  if (TITLES[view] && view !== S.view) { S.view = view; render(); }
});
if (TITLES[location.hash.slice(1)]) S.view = location.hash.slice(1);

load().catch((e) => {
  $('#view').innerHTML = `<div class="card"><div class="empty">
    <div class="big">⚠</div>Could not load data - ${esc(e.message)}</div></div>`;
});
