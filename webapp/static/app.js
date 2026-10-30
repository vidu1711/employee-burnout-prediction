/* PulseCheck front end: plain JavaScript, no build step. */
"use strict";

// ------------------------------------------------------------ helpers
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pad = (n) => String(n).padStart(2, "0");
const ymd = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const parseLocal = (s) => new Date(s);
const monday = (d) => { const x = new Date(d.getFullYear(), d.getMonth(), d.getDate()); x.setDate(x.getDate() - ((x.getDay() + 6) % 7)); return x; };
const addDays = (d, n) => { const x = new Date(d); x.setDate(x.getDate() + n); return x; };
const hm = (d) => `${pad(d.getHours())}:${pad(d.getMinutes())}`;
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const shortDate = (d) => `${d.getDate()} ${MONTHS[d.getMonth()]}`;
function ago(iso) {
  const d = parseLocal(iso), now = new Date(), diff = (now - d) / 60000;
  if (diff < 1) return "now";
  if (diff < 60) return `${Math.floor(diff)}m`;
  if (diff < 1440 && d.getDate() === now.getDate()) return hm(d);
  if (diff < 2880 && now.getDate() - d.getDate() === 1) return "Yesterday";
  return shortDate(d);
}
const initials = (n) => (n || "?").split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase();
const cap = (s) => (s ? s[0].toUpperCase() + s.slice(1) : "");
const chip = (label, text) => `<span class="chip c-${esc(String(label).toLowerCase())}">${esc(text || cap(label))}</span>`;
const avatar = (name, cls = "") => `<span class="avatar ${cls}" aria-hidden="true">${esc(initials(name))}</span>`;

function toast(msg, bad) {
  const t = document.createElement("div");
  t.className = "toast" + (bad ? " bad" : "");
  t.textContent = msg;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), 3800);
}

async function api(path, opts = {}) {
  const o = { method: opts.method || "GET", headers: {}, credentials: "same-origin" };
  if (opts.body !== undefined) { o.headers["Content-Type"] = "application/json"; o.body = JSON.stringify(opts.body); }
  let res;
  try { res = await fetch(path, o); } catch (e) { throw new Error("Can't reach the server. Is it still running?"); }
  let data = null;
  try { data = await res.json(); } catch (e) { /* empty */ }
  if (res.status === 401 && !path.startsWith("/api/auth/login")) { state.user = null; renderAuth(); throw new Error("Please sign in again."); }
  if (!res.ok) {
    let msg = data && data.detail;
    if (Array.isArray(msg)) msg = msg.map((m) => m.msg).join(". ");
    throw new Error(msg || "Something went wrong.");
  }
  return data;
}

const ICONS = {
  home: '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>',
  chat: '<path d="M21 12a8 8 0 01-11.6 7.1L4 20l1-4.6A8 8 0 1121 12z"/>',
  cal: '<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M8 3v4M16 3v4M3 10h18"/>',
  bot: '<rect x="4" y="8" width="16" height="12" rx="4"/><path d="M12 4v4M9 14h.01M15 14h.01"/>',
  chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
  users: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.6-3.6 3.2-5.5 6.5-5.5s5.9 1.9 6.5 5.5M16 4.8a3.5 3.5 0 010 6.4M18 14.8c2 .6 3.3 2.3 3.6 5.2"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 00.3 1.8l.1.1a2 2 0 11-2.8 2.8l-.1-.1a1.7 1.7 0 00-1.8-.3 1.7 1.7 0 00-1 1.5V21a2 2 0 11-4 0v-.1a1.7 1.7 0 00-1-1.5 1.7 1.7 0 00-1.8.3l-.1.1a2 2 0 11-2.8-2.8l.1-.1a1.7 1.7 0 00.3-1.8 1.7 1.7 0 00-1.5-1H3a2 2 0 110-4h.1a1.7 1.7 0 001.5-1 1.7 1.7 0 00-.3-1.8l-.1-.1a2 2 0 112.8-2.8l.1.1a1.7 1.7 0 001.8.3h0a1.7 1.7 0 001-1.5V3a2 2 0 114 0v.1a1.7 1.7 0 001 1.5 1.7 1.7 0 001.8-.3l.1-.1a2 2 0 112.8 2.8l-.1.1a1.7 1.7 0 00-.3 1.8v0a1.7 1.7 0 001.5 1H21a2 2 0 110 4h-.1a1.7 1.7 0 00-1.5 1z"/>',
  out: '<path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9"/>',
  menu: '<path d="M4 7h16M4 12h16M4 17h16"/>',
  send: '<path d="M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z"/>',
  heart: '<path d="M3 12h4l2-5 4 10 2-5h6"/>',
};
const icon = (n) => `<svg viewBox="0 0 24 24" aria-hidden="true">${ICONS[n] || ""}</svg>`;

// ------------------------------------------------------------ charts
function lineChart(series, { max = 100, height = 150, labels = [] } = {}) {
  const W = 420, H = height, L = 28, R = 10, T = 10, B = 22;
  const n = Math.max(...series.map((s) => s.values.length), 2);
  const x = (i) => L + ((W - L - R) * i) / (n - 1);
  const y = (v) => T + (H - T - B) * (1 - Math.max(0, Math.min(max, v)) / max);
  let g = "";
  [0, 50, 100].forEach((t) => { const v = (t / 100) * max; g += `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 6}" y="${y(v) + 3}" text-anchor="end">${Math.round(v)}</text>`; });
  let out = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Trend chart"><g class="grid">${g}</g>`;
  labels.forEach((l, i) => { out += `<text x="${x(i)}" y="${H - 5}" text-anchor="middle">${esc(l)}</text>`; });
  series.forEach((s) => {
    const pts = s.values.map((v, i) => (v == null ? null : [x(i), y(v)]));
    const d = pts.map((p, i) => (p ? `${pts[i - 1] ? "L" : "M"}${p[0].toFixed(1)},${p[1].toFixed(1)}` : "")).join(" ");
    if (s.fill) { const f = pts.filter(Boolean); if (f.length > 1) out += `<path d="${d} L${f[f.length - 1][0]},${H - B} L${f[0][0]},${H - B} Z" fill="${s.color}" opacity=".10"/>`; }
    out += `<path d="${d}" fill="none" stroke="${s.color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>`;
    pts.forEach((p) => { if (p) out += `<circle cx="${p[0]}" cy="${p[1]}" r="3.2" fill="#fff" stroke="${s.color}" stroke-width="2"/>`; });
  });
  return out + "</svg>";
}
const weekLabels = (weeks) => weeks.map((w) => shortDate(parseLocal(w.week_start + "T00:00:00")));
const LEVEL_COLOR = { calm: "#1f8a7d", tense: "#b97500", stressed: "#c53a62", light: "#9b94ad", balanced: "#1f8a7d", busy: "#b97500", hectic: "#c53a62", low: "#1f8a7d", medium: "#b97500", high: "#c53a62" };

// ---- week-load helpers (shared by Home and Schedule)
function loadTiles(A) {
  const days = A.days || [];
  const b2b = days.reduce((n, d) => n + (d.back_to_back || 0), 0);
  const late = days.filter((d) => (d.after_hours_min || 0) > 0).length;
  const t = (v, l, warn) => `<div class="tile ${warn ? "warn" : ""}"><b>${v}</b><span>${l}</span></div>`;
  return `<div class="tiles">${t(A.total_hours ?? 0, "hours booked")}${t(A.meeting_count ?? 0, "meetings")}${t(b2b, "back-to-back", b2b >= 8)}${t(late, late === 1 ? "late day" : "late days", late > 0)}</div>`;
}
function dayStrip(days, tall) {
  const wk = days.filter((d) => d.count > 0 || ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"].includes(d.weekday));
  return `<div class="strip ${tall ? "tall" : ""}">${wk.map((d) => `<div class="sd" title="${esc(d.weekday)}: ${d.count} meetings, ${d.hours} h"><div class="sb"><i style="height:${Math.max(4, Math.min(100, d.score))}%;background:${LEVEL_COLOR[d.label] || "#9b94ad"}"></i></div><span>${esc((d.weekday || "").slice(0, 3))}</span></div>`).join("")}</div>`;
}
function reasonCards(reasons) {
  if (!reasons || !reasons.length) return `<p class="small muted">Nothing stands out. This week is light.</p>`;
  return `<div class="rcards">${reasons.map((r) => {
    const m = /^(\w+day): (.*)$/.exec(r);
    if (!m) return `<div class="rc plain">${esc(r)}</div>`;
    return `<div class="rc"><b>${esc(m[1])}</b><div class="pills">${m[2].split(", ").map((x) => `<span class="pill">${esc(x)}</span>`).join("")}</div></div>`;
  }).join("")}</div>`;
}
function distBars(counts, order) {
  const total = order.reduce((a, k) => a + (counts[k] || 0), 0) || 1;
  return `<div class="bars">${order.map((k) => `<div class="r"><span>${cap(k)}</span><div class="track"><div class="fill" style="width:${((counts[k] || 0) / total) * 100}%;background:${LEVEL_COLOR[k]}"></div></div><b>${counts[k] || 0}</b></div>`).join("")}</div>`;
}

// ------------------------------------------------------------ modal
function modal(html, { drawer = false, onMount } = {}) {
  const s = document.createElement("div");
  s.className = "scrim" + (drawer ? " drawer" : "");
  s.innerHTML = `<div class="modal" role="dialog" aria-modal="true">${html}</div>`;
  const close = () => { s.remove(); document.removeEventListener("keydown", esc_); };
  const esc_ = (e) => { if (e.key === "Escape") close(); };
  s.addEventListener("mousedown", (e) => { if (e.target === s) close(); });
  document.addEventListener("keydown", esc_);
  document.body.appendChild(s);
  $$("[data-close]", s).forEach((b) => b.addEventListener("click", close));
  const first = $("input,textarea,select,button", s); if (first && !drawer) first.focus();
  if (onMount) onMount(s, close);
  return { el: s, close };
}

// ------------------------------------------------------------ state
const state = { user: null, route: "", timers: [], unread: 0, chatMeta: { mode: "builtin" } };
const ROLE_LABEL = { employee: "Employee", lead: "Team lead", admin: "Admin" };

function navFor(role) {
  const items = [];
  if (role === "employee") items.push(["home", "Home", "home"]);
  else items.push(["overview", "Overview", "chart"]);
  if (role === "admin") items.push(["people", "People", "users"]);
  items.push(["messages", "Messages", "chat"], ["schedule", "Schedule", "cal"], ["checkin", "Check-in", "heart"], ["assistant", "PulseBot", "bot"], ["settings", "Settings", "gear"]);
  return items;
}
const defaultRoute = (role) => (role === "employee" ? "home" : "overview");

function clearTimers() { state.timers.forEach(clearInterval); state.timers = []; }

// ------------------------------------------------------------ auth screen
function renderAuth() {
  clearTimers();
  document.title = "Sign in · PulseCheck";
  $("#app").innerHTML = `
  <div class="auth">
    <section class="auth-art">
      <div class="logo"><i>${'<svg width="20" height="20" viewBox="0 0 32 32"><path d="M4 17h6l3-8 5 15 3-9h7" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'}</i> PulseCheck</div>
      <div>
        <h1>Notice the strain before it becomes burnout.</h1>
        <p>Messages, calendars and weekly check-ins, read together so the right people can reach out early and kindly.</p>
      </div>
      <svg class="wave" viewBox="0 0 800 140" preserveAspectRatio="none" aria-hidden="true">
        <path id="w1" stroke="#8b66e8" stroke-width="3" d=""/><path id="w2" stroke="#d9d0f5" stroke-width="2" opacity=".55" d=""/><path id="w3" stroke="#6d3fd9" stroke-width="2" opacity=".7" d=""/>
      </svg>
      <div class="foot">Built for a final-year project. Demo data is synthetic.</div>
    </section>
    <section class="auth-form">
      <div class="auth-card">
        <h2 id="auth-title">Welcome back</h2>
        <p class="muted">Sign in with your work account.</p>
        <div class="tabs" role="tablist"><button role="tab" aria-selected="true" data-tab="in">Sign in</button><button role="tab" aria-selected="false" data-tab="up">Create account</button></div>
        <form id="auth-form" novalidate>
          <label class="field up hide"><span>Full name</span><input class="input" name="name" autocomplete="name"></label>
          <label class="field"><span>Username</span><input class="input" name="username" autocomplete="username" required></label>
          <label class="field"><span>Password</span><input class="input" type="password" name="password" autocomplete="current-password" required></label>
          <p class="err" id="auth-err" role="alert"></p>
          <button class="btn" style="width:100%" id="auth-btn">Sign in</button>
        </form>
        <div class="demo"><b>Demo accounts</b><p class="small muted" style="margin-top:4px">Pick one to fill the form. Employees are emp001 to emp150.</p>
          <div class="row">
            <button class="chipbtn" data-u="emp001" data-p="emp123">Employee</button>
            <button class="chipbtn" data-u="lead" data-p="lead123">Team lead</button>
            <button class="chipbtn" data-u="admin" data-p="admin123">Admin</button>
          </div></div>
      </div>
    </section>
  </div>`;
  let mode = "in";
  const form = $("#auth-form");
  $$(".tabs button").forEach((b) => b.addEventListener("click", () => {
    mode = b.dataset.tab;
    $$(".tabs button").forEach((x) => x.setAttribute("aria-selected", x === b));
    $$(".up").forEach((e) => e.classList.toggle("hide", mode === "in"));
    $("#auth-btn").textContent = mode === "in" ? "Sign in" : "Create account";
    $("#auth-title").textContent = mode === "in" ? "Welcome back" : "Join your team";
    form.password.autocomplete = mode === "in" ? "current-password" : "new-password";
    $("#auth-err").textContent = "";
  }));
  $$(".demo .chipbtn").forEach((b) => b.addEventListener("click", () => {
    form.username.value = b.dataset.u; form.password.value = b.dataset.p;
    $$(".tabs button")[0].click(); form.username.value = b.dataset.u; form.password.value = b.dataset.p; $("#auth-btn").focus();
  }));
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = $("#auth-btn"), err = $("#auth-err");
    err.textContent = "";
    const body = { username: form.username.value.trim(), password: form.password.value };
    if (!body.username || !body.password) { err.textContent = "Enter your username and password."; return; }
    if (mode === "up") {
      body.name = form.name.value.trim();
      if (body.name.length < 2) { err.textContent = "Enter your full name."; return; }
      if (body.password.length < 8) { err.textContent = "Use at least 8 characters for your password."; return; }
    }
    btn.disabled = true; btn.textContent = "Loading, please wait a moment...";
    try {
      const r = await api(mode === "in" ? "/api/auth/login" : "/api/auth/signup", { method: "POST", body });
      state.user = r.user; location.hash = ""; startShell();
    } catch (ex) { err.textContent = ex.message; btn.disabled = false; btn.textContent = mode === "in" ? "Sign in" : "Create account"; }
  });
  animateWave();
}
let waveRaf = 0;
function animateWave() {
  cancelAnimationFrame(waveRaf);
  const ps = [$("#w1"), $("#w2"), $("#w3")];
  if (!ps[0]) return;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const draw = (t) => {
    ps.forEach((p, k) => {
      let d = "";
      for (let x = 0; x <= 800; x += 8) {
        const env = Math.exp(-Math.pow((x - 400 - Math.sin(t / 2600 + k) * 60) / 130, 2));          // a heartbeat-like bump that drifts
        const y = 70 + Math.sin(x / (38 + k * 9) + t / (900 + k * 260)) * (6 + k * 3) - env * (46 - k * 10) * Math.sin(x / 11 + t / 500);
        d += (x ? "L" : "M") + x + "," + y.toFixed(1);
      }
      p.setAttribute("d", d);
    });
    if (!reduce && $("#w1")) waveRaf = requestAnimationFrame(draw);
  };
  draw(performance.now());
  if (!reduce) waveRaf = requestAnimationFrame(draw);
}

// ------------------------------------------------------------ shell
function startShell() {
  cancelAnimationFrame(waveRaf);
  const u = state.user;
  $("#app").innerHTML = `
  <div class="shell">
    <aside class="side" id="side">
      <div class="logo"><i><svg width="20" height="20" viewBox="0 0 32 32"><path d="M4 17h6l3-8 5 15 3-9h7" fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/></svg></i> PulseCheck</div>
      <nav class="nav" aria-label="Main">${navFor(u.role).map(([id, label, ic]) => `<a href="#/${id}" data-r="${id}">${icon(ic)}<span>${label}</span>${id === "messages" ? '<span class="badge hide" id="unread-badge"></span>' : ""}</a>`).join("")}</nav>
      <div class="me">${avatar(u.name)}<div><b>${esc(u.name)}</b><small>${ROLE_LABEL[u.role]}${u.team_name ? " · " + esc(u.team_name) : ""}</small></div>
        <button class="btn ghost sm" id="logout" style="margin-left:auto;color:#d8cff3;border-color:rgba(255,255,255,.2)" aria-label="Sign out" title="Sign out">${icon("out").replace("<svg", '<svg style="width:17px;height:17px;stroke:currentColor;fill:none;stroke-width:1.8"')}</button></div>
    </aside>
    <div class="main">
      <div class="topbar"><button class="menu-btn" id="menu" aria-label="Open menu">${icon("menu").replace("<svg", '<svg width="20" height="20" style="stroke:currentColor;fill:none;stroke-width:1.8"')}</button><h1 id="page-title"></h1><div id="top-actions"></div></div>
      <main class="page" id="page"></main>
    </div>
  </div>`;
  $("#logout").addEventListener("click", async () => { try { await api("/api/auth/logout", { method: "POST" }); } catch (e) { /* ignore */ } state.user = null; clearTimers(); renderAuth(); });
  $("#menu").addEventListener("click", () => $("#side").classList.toggle("open"));
  $("#side").addEventListener("click", (e) => { if (e.target.closest("a")) $("#side").classList.remove("open"); });
  pollUnread(); state.timers.push(setInterval(pollUnread, 20000));
  route();
}
async function pollUnread() {
  try {
    const r = await api("/api/notifications"); state.unread = r.unread_messages;
    const b = $("#unread-badge"); if (b) { b.textContent = r.unread_messages; b.classList.toggle("hide", !r.unread_messages); }
  } catch (e) { /* ignore */ }
}

const PAGES = {};
const TITLES = { home: "Home", overview: "Overview", people: "People", messages: "Messages", schedule: "Schedule", checkin: "Body check-in", assistant: "PulseBot", settings: "Settings" };
let pageToken = 0;
async function route() {
  if (!state.user) return;
  const allowed = navFor(state.user.role).map((n) => n[0]);
  let id = (location.hash.replace(/^#\//, "").split("?")[0]) || defaultRoute(state.user.role);
  if (!allowed.includes(id)) id = defaultRoute(state.user.role);
  state.route = id;
  const tok = ++pageToken;
  $$(".nav a").forEach((a) => (a.getAttribute("data-r") === id ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  $("#page-title").textContent = TITLES[id]; $("#top-actions").innerHTML = "";
  document.title = `${TITLES[id]} · PulseCheck`;
  clearTimers(); state.timers.push(setInterval(pollUnread, 20000));
  const page = $("#page");
  page.innerHTML = `<div class="boot" style="height:200px"><span class="spinner"></span> Loading, please wait a moment...</div>`;
  try { await PAGES[id](page, () => tok === pageToken); }
  catch (e) { if (tok === pageToken) page.innerHTML = `<div class="empty"><b>That didn't load</b>${esc(e.message)}<br><br><button class="btn quiet sm" onclick="route()">Try again</button></div>`; }
}
window.addEventListener("hashchange", route);
window.route = route;

// ------------------------------------------------------------ shared: meeting modal
function openMeetingModal({ invitees = [], title = "", kind = "meeting", date, start = "10:00", end = "10:30", onDone } = {}) {
  const picked = new Map(invitees.map((p) => [p.id, p]));
  const d0 = date || ymd(new Date());
  modal(`<h2>${kind === "wellbeing" ? "Book a check-in chat" : "New meeting"}</h2>
    <label class="field"><span>Title</span><input class="input" id="m-title" maxlength="80" value="${esc(title)}" placeholder="Weekly sync"></label>
    <div class="grid g3" style="gap:10px"><label class="field"><span>Date</span><input class="input" type="date" id="m-date" value="${d0}"></label>
      <label class="field"><span>Start</span><input class="input" type="time" id="m-start" value="${start}"></label>
      <label class="field"><span>End</span><input class="input" type="time" id="m-end" value="${end}"></label></div>
    <label class="field" style="margin-bottom:6px"><span>Invite people</span><input class="input" id="m-find" placeholder="Search by name" autocomplete="off"></label>
    <div class="pick hide" id="m-res"></div><div class="tags" id="m-tags"></div>
    <p class="err" id="m-err" role="alert"></p>
    <div class="actions"><button class="btn ghost" data-close>Cancel</button><button class="btn" id="m-save">Add to calendar</button></div>`, {
    onMount(s, close) {
      const tags = () => { $("#m-tags", s).innerHTML = [...picked.values()].map((p) => `<span class="tag">${esc(p.name)}<button data-x="${p.id}" aria-label="Remove ${esc(p.name)}">×</button></span>`).join(""); $$("[data-x]", s).forEach((b) => b.addEventListener("click", () => { picked.delete(+b.dataset.x); tags(); })); };
      tags();
      let t;
      $("#m-find", s).addEventListener("input", (e) => {
        clearTimeout(t);
        const q = e.target.value.trim(), box = $("#m-res", s);
        if (!q) { box.classList.add("hide"); return; }
        t = setTimeout(async () => {
          try {
            const r = await api("/api/people?q=" + encodeURIComponent(q));
            box.classList.remove("hide");
            box.innerHTML = r.people.length ? r.people.map((p) => `<button data-id="${p.id}" data-n="${esc(p.name)}">${avatar(p.name, "sm")}<span><b>${esc(p.name)}</b> <span class="muted small">${esc(p.team || "")}</span></span></button>`).join("") : `<div class="small muted" style="padding:10px">No one found.</div>`;
            $$("button", box).forEach((b) => b.addEventListener("click", () => { picked.set(+b.dataset.id, { id: +b.dataset.id, name: b.dataset.n }); tags(); box.classList.add("hide"); $("#m-find", s).value = ""; }));
          } catch (ex) { /* ignore */ }
        }, 200);
      });
      $("#m-save", s).addEventListener("click", async () => {
        const btn = $("#m-save", s); btn.disabled = true;
        try {
          const r = await api("/api/schedule", { method: "POST", body: { title: $("#m-title", s).value.trim() || "Meeting", date: $("#m-date", s).value, start: $("#m-start", s).value, end: $("#m-end", s).value, invitee_ids: [...picked.keys()], kind } });
          close();
          const warn = r.warning || (r.meeting && r.meeting.warning);
          toast(warn ? warn : "Added to your calendar.", !!warn && false);
          if (warn) toast(warn);
          if (onDone) onDone(r);
        } catch (ex) { $("#m-err", s).textContent = ex.message; btn.disabled = false; }
      });
    },
  });
}

// ------------------------------------------------------------ page: employee home
function resultBlock(r) {
  if (!r) return "";
  if (!r.status) return `<p class="small muted" style="margin-top:8px">Saved: heart rate ${r.hr}, skin reading ${Math.round(r.gsr)}. Your normal range is still being learned.</p>`;
  const sgn = (n) => (n > 0 ? "+" : "") + n;
  return `<div class="physio-res"><div class="row-between"><b>Physiological status</b>${chip(r.status)}</div>
    <div class="kv"><span>Heart rate</span><b>${Math.round(r.hr)} bpm</b><em>normal ${Math.round(r.hr_baseline)} · ${sgn(Math.round(r.hr_deviation))}</em></div>
    <div class="kv"><span>Skin reading</span><b>${Math.round(r.gsr)}</b><em>normal ${Math.round(r.gsr_baseline)} · ${sgn(Math.round(r.gsr_deviation_pct))}%</em></div></div>`;
}
function bodyCard(ins) {
  const b = ins.body, link = '<div class="actions" style="justify-content:flex-start;margin-top:10px"><a class="btn quiet sm" href="#/checkin">Open check-in</a></div>';
  if (!ins.physio_consent) return `<section class="card"><h2>Body check-in</h2><p class="muted small" style="margin-top:4px">Three quick finger checks a day show how your body is doing compared with your own normal. It is optional.</p>${link}</section>`;
  if (!b.baseline_ready) return `<section class="card"><h2>Body check-in</h2><p class="small" style="margin-top:6px">Learning your normal range: ${b.n_baseline} of ${b.baseline_needed} readings so far.</p>${link}</section>`;
  if (!b.status) return `<section class="card"><h2>Body check-in</h2><p class="small" style="margin-top:6px">No readings in the last 3 days.</p>${link}</section>`;
  return `<section class="card"><div class="row-between"><h2>Body check-in</h2>${chip(b.status)}</div><p class="small muted" style="margin-top:4px">Last 3 days compared with your own normal range.</p>
    <div class="kv"><span>Heart rate</span><b>${Math.round(b.hr_current)} bpm</b><em>normal ${Math.round(b.hr_baseline)} · ${b.hr_deviation_bpm > 0 ? "+" : ""}${Math.round(b.hr_deviation_bpm)}</em></div>
    <div class="kv"><span>Skin reading</span><b>${Math.round(b.gsr_current)}</b><em>${b.gsr_deviation_pct > 0 ? "+" : ""}${Math.round(b.gsr_deviation_pct)}% vs normal</em></div>${link}</section>`;
}

// ------------------------------------------------------------ page: body check-in
PAGES.checkin = async (page, live) => {
  let st = await api("/api/physio/status");
  if (!live()) return;
  const SLOT = { morning: "Morning", afternoon: "Afternoon", evening: "Evening" };
  let pollTimer = null;
  let tickTimer = null;
  const stop = () => { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } if (tickTimer) { clearInterval(tickTimer); tickTimer = null; } };
  const sum = st.summary;

  let offset = 0;                       // server clock minus this browser's clock, in seconds
  const noteClock = (r) => { if (r && r.server_now) offset = r.server_now - Date.now() / 1000; };
  noteClock(st.session);
  const stage = (r) => r.status === "pending" ? 0 : (r.measure_at ? 2 : 1);
  const STEPS = ["Device ready", "Fingers on", "Measuring", "Saved"];
  const sessionMeta = () => {
    const r = st.session, k = stage(r), total = r.seconds || 30;
    const el = k === 2 ? Math.max(0, Date.now() / 1000 + offset - r.measure_at) : 0;
    const left = Math.max(0, Math.ceil(total - el)), pct = k === 2 ? Math.min(100, (el / total) * 100) : 0;
    const fin = k === 2 && left === 0;
    const head = k === 0 ? ["Waiting for your device", "It checks in every couple of seconds. This usually takes under 5 seconds."]
      : k === 1 ? ["Waiting for your fingers", "Press one finger firmly on the heart-rate sensor (its red light should be on) and another on the two skin pads. The 30 second countdown starts as soon as the device feels your finger."]
      : !fin ? ["Measuring: keep still", "Do not lift your fingers. Moving makes the pulse hard to read."]
      : ["Finishing up", "Saving your reading."];
    return { r, k, left, pct, fin, head };
  };
  // The panel is built once per stage; after that only the numbers and the bar width change,
  // so nothing restarts or flickers while the bar fills.
  const sessionBody = () => {
    const m = sessionMeta();
    return `<div class="sess-top"><div><h2>${SLOT[m.r.slot]} check-in</h2><h3 style="margin-top:10px">${m.head[0]}</h3><p class="small muted" style="margin-top:3px">${m.head[1]}</p></div>
      <div class="cd">${m.k === 2 ? `<b id="p-left">${m.left}</b><span id="p-unit">seconds left</span>` : `<span class="spinner"></span>`}</div></div>
      <div class="pline"><div class="pbar" role="progressbar" aria-valuemin="0" aria-valuemax="100"><i id="p-fill" style="width:${m.pct}%"></i></div><b class="ppct" id="p-pct">${Math.round(m.pct)}%</b></div>
      <div class="psteps">${STEPS.map((t, i) => `<span data-i="${i}">${t}</span>`).join("")}</div>`;
  };
  const sessionPanel = () => st.session ? `<section class="card live"><div id="sess" data-key="">${sessionBody()}</div><div class="actions" style="justify-content:flex-start"><button class="btn ghost sm" id="s-cancel">Cancel</button></div></section>` : "";
  const paintSession = () => {
    const e = $("#sess"); if (!e || !st.session) return;
    const m = sessionMeta(), key = m.k + ":" + m.fin + ":" + st.session.id;
    if (e.dataset.key !== key) { e.innerHTML = sessionBody(); e.dataset.key = key; }
    const set = (id, v) => { const n = $("#" + id); if (n && n.textContent !== v) n.textContent = v; };
    if (m.k === 2) {
      const f = $("#p-fill"); if (f) f.style.width = m.pct.toFixed(1) + "%";
      set("p-left", String(m.left)); set("p-unit", m.left === 1 ? "second left" : "seconds left"); set("p-pct", Math.round(m.pct) + "%");
    }
    $$(".psteps span", e).forEach((n) => { const i = +n.dataset.i, cur = Math.min(m.k + (m.fin ? 1 : 0), 3); n.className = i < cur ? "done" : i === cur ? "now" : ""; });
  };
  const slotCard = (k) => {
    const r = st.slots[k];
    return `<section class="card slot"><div class="row-between"><h3>${SLOT[k]}</h3>${r ? '<span class="small muted">Done</span>' : '<span class="muted small">Not done</span>'}</div>
      ${r ? resultBlock(r) : '<p class="small muted" style="margin-top:8px">No reading yet today.</p>'}
      <div class="actions" style="justify-content:flex-start"><button class="btn ${r ? "quiet" : ""} sm" data-start="${k}" ${st.session || !st.consent ? "disabled" : ""}>${r ? "Measure again" : "Start check-in"}</button></div></section>`;
  };
  const hist = st.history.filter((h) => h.hr);
  const draw = () => {
    page.innerHTML = `
    <p class="muted" style="margin:-4px 0 18px">Three short checks a day: morning, afternoon and evening. Rest a finger on the heart-rate sensor and another on the skin sensor for 30 seconds.</p>
    ${!st.consent ? `<section class="card" style="margin-bottom:18px;border-color:var(--lilac);background:var(--mist)"><div class="switch"><div><h3>Turn on body check-ins</h3><p class="small muted" style="margin-top:4px">Your readings are compared with your own normal range. You see the numbers. Your manager sees only a level, never the numbers. These are wellbeing hints, not medical results.</p></div><button class="btn" id="consent-on">Turn on</button></div></section>` : ""}
    ${sessionPanel()}
    <div class="grid g3" style="margin-bottom:18px">${["morning", "afternoon", "evening"].map(slotCard).join("")}</div>
    <div class="grid g2" style="align-items:start">
      <section class="card"><h2>Your normal range</h2>
        ${sum.baseline_ready ? `<div class="kv"><span>Resting heart rate</span><b>${Math.round(sum.hr_baseline)} bpm</b><em>median of ${sum.n_baseline} older readings</em></div><div class="kv"><span>Skin reading</span><b>${Math.round(sum.gsr_baseline)}</b><em>median of ${sum.n_baseline} older readings</em></div>
        ${sum.status ? `<div class="tip">Last 3 days: <b>${cap(sum.status)}</b>. Heart rate ${sum.hr_deviation_bpm > 0 ? "+" : ""}${Math.round(sum.hr_deviation_bpm)} bpm, skin reading ${sum.gsr_deviation_pct > 0 ? "+" : ""}${Math.round(sum.gsr_deviation_pct)}% compared with normal.</div>` : `<p class="small muted" style="margin-top:8px">No readings in the last 3 days.</p>`}`
        : `<p class="small" style="margin-top:8px">Still learning. ${sum.n_baseline} of ${sum.baseline_needed} older readings collected.</p><div class="track" style="margin-top:8px"><div class="fill" style="width:${Math.min(100, (sum.n_baseline / sum.baseline_needed) * 100)}%;background:var(--violet)"></div></div><p class="tiny muted" style="margin-top:8px">Readings from the last 3 days are compared against older ones, so a normal range needs about ${sum.baseline_needed} readings that are more than 3 days old.</p>`}
        ${hist.length > 1 ? `<h3 style="margin-top:18px">Heart rate over time</h3>${lineChart([{ values: hist.map((h) => h.hr), color: "#6d3fd9", fill: true }], { max: Math.max(120, ...hist.map((h) => h.hr)) + 10, height: 130 })}` : ""}
      </section>
      <div class="grid" style="align-content:start">
        <section class="card"><h2>Devices</h2>
          <div style="margin-top:8px">${st.devices.map((d) => `<div class="dev"><span class="dot ${d.online ? "on" : ""}"></span><div><b>${esc(d.label)}</b><small class="muted"> ${esc(d.id)}${d.shared ? " · shared" : ""}</small></div><span class="small muted" style="margin-left:auto">${d.online ? "Online" : "Offline"}</span>${!d.shared ? `<button class="btn ghost sm" data-del="${esc(d.id)}">Remove</button>` : ""}</div>`).join("") || '<p class="small muted">No device yet.</p>'}</div>
          <div class="actions" style="justify-content:flex-start"><button class="btn quiet sm" id="dev-add">Add my own device</button></div></section>
        ${st.simulation ? `<section class="card"><h2>No device with you?</h2><p class="small muted" style="margin-top:4px">Demo buttons. These readings are saved as <b>simulated</b> and are for trying the website only.</p>
          <div class="actions" style="justify-content:flex-start;flex-wrap:wrap"><button class="btn quiet sm" data-sim="baseline">Fill a sample normal range</button><button class="btn quiet sm" data-sim="normal">Simulate a normal reading</button><button class="btn quiet sm" data-sim="elevated">Simulate an elevated reading</button></div></section>` : ""}
      </div>
    </div>`;
    const on = $("#consent-on");
    if (on) on.addEventListener("click", async () => { try { const r = await api("/api/me/settings", { method: "PATCH", body: { physio_consent: true } }); state.user = r.user; await refresh(); toast("Body check-ins are on."); } catch (e) { toast(e.message, true); } });
    $$("[data-start]").forEach((b) => b.addEventListener("click", async () => {
      try { await api("/api/physio/sessions", { method: "POST", body: { slot: b.dataset.start } }); await refresh(); } catch (e) { toast(e.message, true); }
    }));
    const c = $("#s-cancel");
    if (c) c.addEventListener("click", async () => { try { await api("/api/physio/sessions/" + st.session.id, { method: "DELETE" }); await refresh(); } catch (e) { toast(e.message, true); } });
    $$("[data-sim]").forEach((b) => b.addEventListener("click", async () => {
      try { await api("/api/physio/simulate", { method: "POST", body: { mode: b.dataset.sim } }); await refresh(); toast(b.dataset.sim === "baseline" ? "Sample normal range added." : "Simulated reading saved."); } catch (e) { toast(e.message, true); }
    }));
    $$("[data-del]").forEach((b) => b.addEventListener("click", async () => { try { await api("/api/physio/devices/" + b.dataset.del, { method: "DELETE" }); await refresh(); } catch (e) { toast(e.message, true); } }));
    $("#dev-add").addEventListener("click", () => {
      const m = modal(`<h2>Add your device</h2><label class="field" style="margin-top:12px"><span>Name</span><input class="input" id="dn" value="My ESP32" maxlength="40"></label><div class="actions"><button class="btn ghost" data-close>Cancel</button><button class="btn" id="dgo">Create</button></div>`);
      $("#dgo", m.el).addEventListener("click", async () => {
        try {
          const r = await api("/api/physio/devices", { method: "POST", body: { label: $("#dn", m.el).value } });
          $(".modal", m.el).innerHTML = `<h2>Device created</h2><p class="small muted" style="margin-top:6px">Copy these into the device code now. The key is shown only once.</p><pre class="code">DEVICE_ID  = "${esc(r.device_id)}"\nDEVICE_KEY = "${esc(r.device_key)}"</pre><div class="actions"><button class="btn" data-close>Done</button></div>`;
          $$("[data-close]", m.el).forEach((b) => b.addEventListener("click", () => { m.close(); refresh(); }));
        } catch (e) { toast(e.message, true); }
      });
    });
  };
  const refresh = async () => { st = await api("/api/physio/status"); if (!live()) return; Object.assign(sum, st.summary); draw(); watch(); };
  const watch = () => {
    stop();
    if (!st.session) return;
    paintSession(); tickTimer = setInterval(paintSession, 100);
    pollTimer = setInterval(async () => {
      if (!live()) return stop();
      try {
        const r = (await api("/api/physio/sessions/" + st.session.id)).session;
        noteClock(r);
        if (r.status === "pending" || r.status === "measuring") { st.session = r; paintSession(); return; }
        stop(); await refresh();
        if (r.status === "done") toast("Reading saved."); else toast(r.message || "That check-in did not finish.", true);
      } catch (e) { stop(); }
    }, 1000);
  };
  $("#top-actions").innerHTML = "";
  draw(); watch();
  const guard = setInterval(() => { if (!live()) { stop(); clearInterval(guard); } }, 1000);
  state.timers.push(guard);
};

PAGES.home = async (page, live) => {
  const [ins, wk, notes] = await Promise.all([api("/api/me/insights"), api("/api/schedule"), api("/api/notifications")]);
  if (!live()) return;
  const now = new Date(), h = now.getHours();
  const greet = h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
  const first = state.user.name.split(" ")[0];
  const today = ymd(now);
  const todays = wk.events.filter((e) => e.start.slice(0, 10) === today).sort((a, b) => a.start.localeCompare(b.start));
  const dayInfo = (wk.analysis.days || []).find((d) => d.date === today);
  const cur = ins.schedule.current;
  const latest = ins.mood.latest;
  const moods = ["great", "good", "okay", "stressed", "overwhelmed"];
  page.innerHTML = `
  <p class="muted" style="margin:-4px 0 18px">${greet}, ${esc(first)}. ${DAYS[now.getDay()]} ${shortDate(now)}.</p>
  ${ins.checkins && ins.checkins.length ? `<div class="card" style="margin-bottom:18px;border-color:var(--lilac);background:var(--mist)"><h3>A note from ${esc(ins.checkins[0].by_name || "your manager")}</h3><p style="margin-top:6px">${esc(ins.checkins[0].text)}</p><div class="actions" style="justify-content:flex-start;margin-top:12px"><a class="btn sm" href="#/messages">Reply</a></div></div>` : ""}
  <div class="grid g-main">
    <div class="grid">
      <section class="card"><div class="row-between"><div><h2>How are you feeling this week?</h2><p class="muted small">Takes one tap. Only you and the system see the detail.</p></div>${latest ? `<span class="small muted">Last: ${esc(cap(latest.label))}, ${ago(latest.created_at)}</span>` : ""}</div>
        <div class="moods" id="moods">${moods.map((m) => `<button class="mood" data-m="${m}">${cap(m)}</button>`).join("")}</div></section>
      <section class="card"><div class="row-between"><h2>Today</h2>${dayInfo ? chip(dayInfo.label, `${cap(dayInfo.label)} day`) : ""}</div>
        ${todays.length ? `<div style="margin-top:10px">${todays.map((e) => { const s = parseLocal(e.start), en = parseLocal(e.end); return `<div style="display:flex;gap:14px;padding:9px 0;border-bottom:1px solid var(--gray)"><span class="muted small" style="width:116px;flex:none;white-space:nowrap">${hm(s)} to ${hm(en)}</span><div><b>${esc(e.title)}</b>${e.attendee_count ? `<span class="muted small"> · ${e.attendee_count + 1} people</span>` : ""}</div></div>`; }).join("")}</div>` : `<div class="empty" style="margin-top:12px"><b>Nothing booked today</b>A clear day. Good time for focused work.</div>`}
        <div class="actions" style="justify-content:flex-start"><a class="btn quiet sm" href="#/schedule">Open schedule</a></div></section>
      <section class="card"><h2>How your messages have read</h2><p class="muted small">Weekly tone of what you send. Only you can see this.</p>
        ${ins.consent ? lineChart([{ values: ins.tone.weeks.map((w) => w.risk), color: "#6d3fd9", fill: true }], { labels: weekLabels(ins.tone.weeks) }) : `<div class="empty" style="margin-top:10px">Message analysis is off. You can turn it on in Settings.</div>`}</section>
    </div>
    <div class="grid" style="align-content:start">
      <section class="card"><div class="row-between"><h2>Your week</h2>${chip(cur.label, `${cap(cur.label)}`)}</div>
        ${loadTiles(cur)}${dayStrip(cur.days || [])}
        <div style="margin-top:12px">${reasonCards((cur.reasons || []).slice(0, 2))}</div>
        ${cur.suggestion ? `<div class="tip">${esc(cur.suggestion)}</div>` : ""}</section>
      <section class="card"><h2>Meeting load, last 6 weeks</h2>
        ${lineChart([{ values: ins.schedule.weeks.map((w) => w.score), color: "#8b66e8", fill: true }], { labels: weekLabels(ins.schedule.weeks), height: 140 })}</section>
      ${bodyCard(ins)}
      <section class="card" style="background:linear-gradient(135deg,var(--ink),#3a2670);color:#fff;border:0"><h3 style="color:#fff">Need a hand?</h3><p style="margin-top:6px;color:#d8cff3">PulseBot can find free time, book or move meetings, and share resources if things feel heavy.</p><div class="actions" style="justify-content:flex-start"><a class="btn" style="background:#fff;color:var(--violet-d)" href="#/assistant">Ask PulseBot</a></div></section>
    </div>
  </div>`;
  $$("#moods .mood").forEach((b) => {
    if (latest && latest.label === b.dataset.m && Date.now() - parseLocal(latest.created_at) < 36e5) b.classList.add("on");
    b.addEventListener("click", async () => {
      try { await api("/api/mood", { method: "POST", body: { label: b.dataset.m } }); $$("#moods .mood").forEach((x) => x.classList.toggle("on", x === b)); toast("Thanks, saved your check-in."); } catch (e) { toast(e.message, true); }
    });
  });
};

// ------------------------------------------------------------ page: messages
PAGES.messages = async (page, live) => {
  const consent = state.user.consent;
  let convs = (await api("/api/conversations")).conversations;
  if (!live()) return;
  let current = null, lastId = 0, searchTimer;
  page.innerHTML = `
  <div class="msgs" id="msgs">
    <section class="convs"><header><input class="input" id="c-search" placeholder="Search people to message" autocomplete="off" aria-label="Search people"></header><div class="list" id="c-list"></div></section>
    <section class="thread" id="thread"><div class="empty" style="margin:auto;max-width:340px;border:0"><b>Pick a conversation</b>Or search for a colleague on the left to start a new one.</div></section>
  </div>`;
  const list = $("#c-list");
  const drawList = (items) => {
    list.innerHTML = items.length ? items.map((c) => `<button class="conv ${current && current.id === c.user.id ? "on" : ""}" data-id="${c.user.id}">${avatar(c.user.name)}<div class="t"><b><span>${esc(c.user.name)}</span><small class="muted" style="font-weight:400">${c.last ? ago(c.last.at) : ""}</small></b><span>${c.last ? (c.last.from_me ? "You: " : "") + esc(c.last.text) : esc(c.user.team || "")}</span></div>${c.unread ? `<span class="badge">${c.unread}</span>` : ""}</button>`).join("") : `<div class="empty" style="margin:16px;border:0"><b>No conversations yet</b>Search for a colleague to say hello.</div>`;
    $$(".conv", list).forEach((b) => b.addEventListener("click", () => { const c = items.find((x) => x.user.id === +b.dataset.id); open(c.user); }));
  };
  drawList(convs);
  $("#c-search").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    const q = e.target.value.trim();
    if (!q) { drawList(convs); return; }
    searchTimer = setTimeout(async () => {
      try { const r = await api("/api/people?q=" + encodeURIComponent(q)); if (!live()) return; drawList(r.people.map((p) => ({ user: p, last: null, unread: 0 }))); } catch (ex) { /* ignore */ }
    }, 200);
  });

  async function open(user) {
    current = user; lastId = 0;
    $("#msgs").classList.add("open");
    $("#thread").innerHTML = `
      <header><button class="btn ghost sm back" id="back">Back</button>${avatar(user.name)}<div><b>${esc(user.name)}</b><div class="muted small">${esc(user.team || "")}${user.role && user.role !== "employee" ? " · " + ROLE_LABEL[user.role] : ""}</div></div></header>
      <div class="body" id="t-body"><div class="sk" style="width:40%"></div></div>
      <form class="composer" id="t-form"><textarea id="t-text" rows="1" maxlength="2000" placeholder="Write a message" aria-label="Message"></textarea><button class="btn" id="t-send" aria-label="Send">${icon("send").replace("<svg", '<svg style="width:18px;height:18px;stroke:#fff;fill:none;stroke-width:2"')}</button></form>
      <div class="notice">${consent ? "Your messages are read for tone so you can see how they come across. Only you see that. Managers see an overall level, never your words." : "Message analysis is off for your account, so nothing you send is analysed."}</div>`;
    $("#back").addEventListener("click", () => { $("#msgs").classList.remove("open"); });
    const ta = $("#t-text");
    ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#t-form").requestSubmit(); } });
    ta.addEventListener("input", () => { ta.style.height = "auto"; ta.style.height = Math.min(120, ta.scrollHeight) + "px"; });
    $("#t-form").addEventListener("submit", async (e) => {
      e.preventDefault();
      const text = ta.value.trim(); if (!text) return;
      $("#t-send").disabled = true;
      try { const r = await api("/api/messages", { method: "POST", body: { to_id: user.id, text } }); ta.value = ""; ta.style.height = "auto"; paint([r.message]); refreshConvs(); }
      catch (ex) { toast(ex.message, true); }
      $("#t-send").disabled = false; ta.focus();
    });
    await load(true);
    refreshConvs();
    pollUnread();
  }

  function bubble(m) {
    const t = parseLocal(m.at);
    if (m.kind === "checkin" && !m.from_me) {
      return `<div class="cardmsg" data-id="${m.id}"><b>Check-in from ${esc(current.name)}</b><p style="margin:6px 0 10px">${esc(m.text)}</p><button class="btn sm" data-book="1">Book a time to talk</button> <span class="muted tiny">${ago(m.at)}</span></div>`;
    }
    let extra = "";
    if (m.from_me && m.analysis) {
      const a = m.analysis;
      extra = `<div class="meta" data-meta="${m.id}">${chip(a.label, `Reads ${a.label}`)}${(a.cues || []).map((c) => `<span class="cue">${esc(c)}</span>`).join("")}</div>`;
    }
    return `<div class="bub ${m.from_me ? "me" : ""}" data-id="${m.id}">${esc(m.text)}<time>${hm(t)}</time></div>${extra}`;
  }
  function paint(msgs, replace) {
    const body = $("#t-body"); if (!body) return;
    const near = body.scrollHeight - body.scrollTop - body.clientHeight < 80;
    if (replace) body.innerHTML = "";
    msgs.forEach((m) => { if ($(`[data-id="${m.id}"]`, body)) return; body.insertAdjacentHTML("beforeend", bubble(m)); lastId = Math.max(lastId, m.id); });
    if (!msgs.length && replace) body.innerHTML = `<div class="empty" style="margin:auto;border:0"><b>No messages yet</b>Say hello to ${esc(current.name.split(" ")[0])}.</div>`;
    $$("[data-book]", body).forEach((b) => { b.onclick = () => { const d = addDays(new Date(), 1); openMeetingModal({ invitees: [{ id: current.id, name: current.name }], title: "Check-in chat", kind: "wellbeing", date: ymd(d), start: "11:00", end: "11:30" }); }; });
    if (replace || near) body.scrollTop = body.scrollHeight;
  }
  async function load(first) {
    if (!current) return;
    const id = current.id;
    const r = await api(`/api/messages/${id}` + (first ? "" : `?after=${lastId}`));
    if (!live() || !current || current.id !== id) return;
    paint(r.messages, first);
  }
  async function refreshConvs() { try { convs = (await api("/api/conversations")).conversations; if (live() && !$("#c-search").value.trim()) drawList(convs); } catch (e) { /* ignore */ } }
  state.timers.push(setInterval(async () => { if (!live()) return; try { await load(false); await refreshConvs(); } catch (e) { /* ignore */ } }, 5000));

  const want = new URLSearchParams(location.hash.split("?")[1] || "").get("to");
  if (want) { try { const r = await api("/api/people?q="); const p = (r.people || []).find((x) => x.id === +want); if (p) open(p); } catch (e) { /* ignore */ } }
};

// ------------------------------------------------------------ page: schedule
PAGES.schedule = async (page, live) => {
  let weekStart = monday(new Date()), openPanel = null;
  const START = 8, END = 20, PX = 45;
  const render = async () => {
    const data = await api("/api/schedule?week=" + ymd(weekStart));
    if (!live()) return;
    const A = data.analysis, days = A.days || [];
    const todayStr = ymd(new Date());
    const cols = [...Array(7)].map((_, i) => addDays(weekStart, i));
    const hours = [...Array(END - START + 1)].map((_, i) => START + i);
    const evByDay = (d) => data.events.filter((e) => e.start.slice(0, 10) === ymd(d)).sort((a, b) => a.start.localeCompare(b.start));
    const top = (d) => ((d.getHours() + d.getMinutes() / 60) - START) * PX;
    const rangeTxt = `${shortDate(cols[0])} to ${shortDate(cols[6])} ${cols[6].getFullYear()}`;
    page.innerHTML = `
      <div class="toolbar"><button class="btn ghost sm" id="prev" aria-label="Previous week">‹ Prev</button><button class="btn ghost sm" id="today">This week</button><button class="btn ghost sm" id="next" aria-label="Next week">Next ›</button><b style="margin-left:6px">${rangeTxt}</b><span style="flex:1"></span><button class="btn" id="new">New meeting</button></div>
      <section class="card wk-sum"><div class="wk-top">${chip(A.label || "light", cap(A.label || "light") + " week")}${loadTiles(A)}${dayStrip(days)}</div></section>
      <div>
        <div><div class="scroll-x"><div class="week">
          <div class="hd" style="border-left:0"></div>${cols.map((d, i) => `<div class="hd ${ymd(d) === todayStr ? "today" : ""}">${DAYS[d.getDay()]}<b>${d.getDate()}</b>${days[i] && days[i].count ? chip(days[i].label, cap(days[i].label)) : ""}</div>`).join("")}
          <div class="gutter">${hours.map((h) => `<span style="top:${(h - START) * PX}px">${pad(h)}:00</span>`).join("")}</div>
          ${cols.map((d) => {
            const wk = d.getDay() === 0 || d.getDay() === 6;
            let s = `<div class="col" data-day="${ymd(d)}">`;
            if (wk) s += `<div class="off" style="top:0;height:${(END - START) * PX}px"></div>`;
            else s += `<div class="off" style="top:0;height:${(9 - START) * PX}px"></div><div class="off" style="top:${(18 - START) * PX}px;height:${(END - 18) * PX}px"></div>`;
            evByDay(d).forEach((e) => {
              const st = parseLocal(e.start), en = parseLocal(e.end);
              const t = Math.max(0, top(st)), h = Math.max(20, top(en) - t - 2);
              const after = st.getHours() >= 18 || en.getHours() > 18 || (en.getHours() === 18 && en.getMinutes() > 0);
              s += `<button class="ev ${e.kind === "wellbeing" ? "wellbeing" : ""} ${after ? "after" : ""}" data-e="${e.id}" style="top:${t}px;height:${h}px" title="${esc(e.title)} ${hm(st)}-${hm(en)}"><b>${esc(e.title)}</b>${h > 36 ? `${hm(st)}-${hm(en)}` : ""}</button>`;
            });
            return s + "</div>";
          }).join("")}
        </div></div>
        <div class="legend" style="margin-top:10px"><span>Shaded: outside 9 to 18 working hours</span><span style="color:var(--stressed)">Red edge: runs past 18:00</span><span style="color:var(--calm)">Green: check-in chat</span></div></div>
        <div class="panels">
          <div class="tabsline"><button class="pt" data-p="load" aria-expanded="false">Week load <i>▾</i></button><button class="pt" data-p="days" aria-expanded="false">Day by day <i>▾</i></button></div>
          <section class="card pnl" id="p-load" hidden>${reasonCards(A.reasons)}${A.suggestion ? `<div class="tip">${esc(A.suggestion)}</div>` : ""}</section>
          <section class="card pnl" id="p-days" hidden><div class="dgrid">${days.map((d) => `<div class="dc"><div class="dh"><b>${esc((d.weekday || "").slice(0, 3))}</b><em>${d.date ? shortDate(parseLocal(d.date + "T00:00:00")) : ""}</em>${d.count ? chip(d.label, cap(d.label)) : '<span class="muted small">Free</span>'}</div>
            <div class="track"><div class="fill" style="width:${Math.min(100, d.score)}%;background:${LEVEL_COLOR[d.label] || "#9b94ad"}"></div></div>
            <div class="pills">${d.count ? `<span class="pill">${d.count} meetings</span><span class="pill">${d.hours} h</span>${d.back_to_back ? `<span class="pill">${d.back_to_back} back-to-back</span>` : ""}${d.lunch_blocked ? `<span class="pill warn">no lunch</span>` : ""}${d.after_hours_min ? `<span class="pill warn">${Math.round(d.after_hours_min / 60 * 10) / 10} h after 18:00</span>` : ""}` : ""}</div></div>`).join("")}</div>
            <p class="tiny muted" style="margin-top:10px">Score looks at hours booked, back-to-back meetings, a blocked lunch, and time after 18:00.</p></section>
        </div>
      </div>`;
    $$(".pt").forEach((b) => b.addEventListener("click", () => {
      const was = b.getAttribute("aria-expanded") === "true";
      $$(".pt").forEach((x) => x.setAttribute("aria-expanded", "false")); $$(".pnl").forEach((x) => (x.hidden = true));
      if (!was) { b.setAttribute("aria-expanded", "true"); $("#p-" + b.dataset.p).hidden = false; openPanel = b.dataset.p; } else openPanel = null;
    }));
    if (openPanel) { const b = $(`.pt[data-p="${openPanel}"]`); if (b) b.click(); }
    $("#prev").onclick = () => { weekStart = addDays(weekStart, -7); render().catch((e) => toast(e.message, true)); };
    $("#next").onclick = () => { weekStart = addDays(weekStart, 7); render().catch((e) => toast(e.message, true)); };
    $("#today").onclick = () => { weekStart = monday(new Date()); render().catch((e) => toast(e.message, true)); };
    $("#new").onclick = () => openMeetingModal({ onDone: () => render() });
    $$(".col").forEach((c) => c.addEventListener("dblclick", (ev) => { if (ev.target.closest(".ev")) return; const r = c.getBoundingClientRect(); const mins = Math.round(((ev.clientY - r.top) / PX + START) * 4) / 4; const h = Math.floor(mins); const m = Math.round((mins - h) * 60); openMeetingModal({ date: c.dataset.day, start: `${pad(h)}:${pad(m)}`, end: `${pad(Math.min(23, h + 1))}:${pad(m)}`, onDone: () => render() }); }));
    $$(".ev").forEach((b) => b.addEventListener("click", () => {
      const e = data.events.find((x) => x.id === +b.dataset.e), st = parseLocal(e.start), en = parseLocal(e.end);
      modal(`<h2>${esc(e.title)}</h2><p class="muted">${DAYS[st.getDay()]} ${shortDate(st)}, ${hm(st)} to ${hm(en)}</p>
        <p style="margin-top:10px">Organiser: <b>${esc(e.organizer || "You")}</b></p>
        ${e.attendees && e.attendees.length ? `<p class="small" style="margin-top:8px">With: ${e.attendees.map((a) => esc(a.name || a)).join(", ")}</p>` : ""}
        <div class="actions"><button class="btn ghost" data-close>Close</button><button class="btn danger" id="del">Remove from my calendar</button></div>`, {
        onMount(s, close) { $("#del", s).addEventListener("click", async () => { try { await api("/api/schedule/" + e.id, { method: "DELETE" }); close(); toast("Meeting removed."); render(); } catch (ex) { toast(ex.message, true); } }); },
      });
    }));
    const sc = $(".scroll-x"); if (sc && !sc.dataset.s) sc.dataset.s = 1;
  };
  await render();
};

// ------------------------------------------------------------ page: PulseBot
function md(text) {
  const lines = esc(text).split("\n"); let out = "", inList = false;
  const inline = (s) => s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/(^|[\s(])_([^_]+)_(?=[\s).,!?]|$)/g, "$1<em>$2</em>");
  for (const ln of lines) {
    const m = ln.match(/^\s*[-•*]\s+(.*)$/);
    if (m) { if (!inList) { out += "<ul>"; inList = true; } out += `<li>${inline(m[1])}</li>`; }
    else { if (inList) { out += "</ul>"; inList = false; } if (ln.trim()) out += `<p>${inline(ln)}</p>`; }
  }
  return out + (inList ? "</ul>" : "");
}
PAGES.assistant = async (page, live) => {
  const r = await api("/api/chat/history");
  if (!live()) return;
  state.chatMeta = { mode: r.mode, model: r.model };
  const role = state.user.role;
  const starters = role === "employee"
    ? ["What's on my calendar today?", "Find me a free hour tomorrow", "Book a 30 min catch-up with Priya on Friday at 3pm", "I'm feeling overwhelmed", "How is my week looking?"]
    : ["Who needs attention most?", "Give me a team overview", "What's on my calendar today?", "Find me a free hour tomorrow", "Show wellbeing resources"];
  page.innerHTML = `
  <div class="chat">
    <header><div class="botmark">${icon("bot").replace("<svg", '<svg style="width:22px;height:22px;stroke:#fff;fill:none;stroke-width:1.8"')}</div><div style="flex:1"><b>PulseBot</b><div class="muted small">Calendar, wellbeing and people help, with real actions</div></div>
      <span class="mode ${r.mode === "ai" ? "ai" : "builtin"}" id="mode" title="${r.mode === "ai" ? "Answers come from Claude, using the app's tools" : "No API key set, so the built-in assistant answers"}">${r.mode === "ai" ? "Claude AI" : "Built-in"}</span>
      <button class="btn ghost sm" id="clear">Clear chat</button></header>
    <div class="body" id="c-body"></div>
    <div class="sugs" id="sugs"></div>
    <form class="composer" id="c-form"><textarea id="c-text" rows="1" maxlength="2000" placeholder="Ask PulseBot, or tell it what to do" aria-label="Message PulseBot"></textarea><button class="btn" id="c-send" aria-label="Send">${icon("send").replace("<svg", '<svg style="width:18px;height:18px;stroke:#fff;fill:none;stroke-width:2"')}</button></form>
  </div>`;
  const body = $("#c-body"), ta = $("#c-text");
  const scroll = () => { body.scrollTop = body.scrollHeight; };
  const addUser = (t) => { body.insertAdjacentHTML("beforeend", `<div class="bub me">${esc(t)}</div>`); scroll(); };
  const addBot = (t, tools, notice) => {
    body.insertAdjacentHTML("beforeend", `<div class="bub bot">${notice ? `<p class="small muted"><em>${esc(notice)}</em></p>` : ""}${md(t)}${tools && tools.length ? `<div class="toolchips">${tools.map((x) => `<span class="toolchip">${esc(x)}</span>`).join("")}</div>` : ""}</div>`); scroll();
  };
  const sugs = (list) => { $("#sugs").innerHTML = (list || []).slice(0, 4).map((s) => `<button class="chipbtn" type="button">${esc(s)}</button>`).join(""); $$("#sugs .chipbtn").forEach((b) => b.addEventListener("click", () => send(b.textContent))); };
  addBot(`Hi ${state.user.name.split(" ")[0]}, I'm PulseBot. I can look at your calendar, find free time, book and cancel meetings, log how you're feeling${role === "employee" ? "" : ", and summarise your team's wellbeing"}. What would you like to do?`);
  r.messages.forEach((m) => (m.role === "user" ? addUser(m.content) : addBot(m.content, m.tools)));
  sugs(starters);
  let busy = false;
  async function send(text) {
    text = (text || "").trim(); if (!text || busy) return;
    busy = true; $("#c-send").disabled = true; ta.value = ""; ta.style.height = "auto"; $("#sugs").innerHTML = "";
    addUser(text);
    body.insertAdjacentHTML("beforeend", `<div class="bub bot" id="typing"><span class="typing"><i></i><i></i><i></i></span></div>`); scroll();
    try {
      const res = await api("/api/chat", { method: "POST", body: { message: text } });
      $("#typing")?.remove();
      addBot(res.reply, res.tools, res.notice); sugs(res.suggestions);
      const mb = $("#mode"); if (mb) { mb.textContent = res.mode === "ai" ? "Claude AI" : "Built-in"; mb.className = "mode " + (res.mode === "ai" ? "ai" : "builtin"); }
      if ((res.tools || []).length) pollUnread();
    } catch (ex) { $("#typing")?.remove(); addBot("Sorry, that didn't go through: " + ex.message); }
    busy = false; $("#c-send").disabled = false; ta.focus();
  }
  $("#c-form").addEventListener("submit", (e) => { e.preventDefault(); send(ta.value); });
  ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(ta.value); } });
  ta.addEventListener("input", () => { ta.style.height = "auto"; ta.style.height = Math.min(120, ta.scrollHeight) + "px"; });
  $("#clear").addEventListener("click", async () => { try { await api("/api/chat/history", { method: "DELETE" }); PAGES.assistant(page, live); } catch (e) { toast(e.message, true); } });
  ta.focus();
};

// ------------------------------------------------------------ manager helpers
const DEFAULT_CHECKIN = "Hi, I wanted to check in and see how you're doing this week. There's no pressure to reply in detail. If you'd like to talk, reply here or book a time with me.";
function checkinModal(people, { bulk = false, onDone } = {}) {
  const n = people.length;
  modal(`<h2>${bulk ? `Check in with ${n} ${n === 1 ? "person" : "people"}` : `Message ${esc(people[0].name)}`}</h2>
    <p class="muted small" style="margin-bottom:12px">${bulk ? "Everyone gets the same short, kind note. It doesn't mention their risk level or any score." : "This arrives as a check-in card with a button to book a time."}</p>
    <label class="field"><span>Your message</span><textarea class="input" id="ci-text" rows="5" maxlength="1000">${esc(DEFAULT_CHECKIN)}</textarea></label>
    <p class="err" id="ci-err" role="alert"></p>
    <div class="actions"><button class="btn ghost" data-close>Cancel</button><button class="btn" id="ci-send">${bulk ? `Send to ${n}` : "Send"}</button></div>`, {
    onMount(s, close) {
      $("#ci-send", s).addEventListener("click", async () => {
        const text = $("#ci-text", s).value.trim(); if (!text) { $("#ci-err", s).textContent = "Write a message first."; return; }
        $("#ci-send", s).disabled = true;
        try { const r = await api("/api/manager/checkins", { method: "POST", body: { employee_ids: people.map((p) => p.id), text } }); close(); toast(`Sent to ${r.sent}.`); if (onDone) onDone(); }
        catch (ex) { $("#ci-err", s).textContent = ex.message; $("#ci-send", s).disabled = false; }
      });
    },
  });
}
const bodyChip = (lvl, persistent) => (lvl ? chip(lvl, cap(lvl) + (persistent && lvl !== "normal" ? " (repeated)" : "")) : '<span class="muted small">No data</span>');
const sigCells = (r) => `<td>${chip(r.tone)}</td><td>${chip(r.schedule)}</td><td>${bodyChip(r.body, r.body_persistent)}</td><td>${r.mood ? chip(r.mood) : '<span class="muted small">No answer</span>'}</td>`;

async function employeeDrawer(id, refresh) {
  const d = modal(`<div class="boot" style="height:200px"><span class="spinner"></span> Loading, please wait a moment...</div>`, { drawer: true });
  try {
    const e = await api("/api/manager/employees/" + id);
    const cur = e.schedule.current || {};
    $(".modal", d.el).innerHTML = `
      <div class="row-between" style="align-items:flex-start"><div class="person">${avatar(e.name, "lg")}<div><h2 style="margin:0">${esc(e.name)}</h2><small class="muted">${esc(e.emp_code || "")} · ${esc(e.team || "")}</small></div></div><button class="btn ghost sm" data-close>Close</button></div>
      <div style="margin:16px 0 4px">${chip(e.risk, `${e.risk} risk`)}</div>
      <p class="tiny muted">You see levels and reasons. You never see what anyone wrote.</p>
      <h3 style="margin-top:18px">Why</h3>
      <ul class="reasons small">${(e.reasons || []).length ? e.reasons.map((r) => `<li>${esc(r)}</li>`).join("") : "<li>Nothing unusual right now.</li>"}</ul>
      <h3 style="margin-top:18px">Message tone ${chip(e.tone.level)}</h3>${e.consent ? lineChart([{ values: e.tone.weeks.map((w) => w.risk), color: "#6d3fd9", fill: true }], { labels: weekLabels(e.tone.weeks), height: 130 }) : `<p class="small muted">This person turned message analysis off.</p>`}
      <h3 style="margin-top:14px">Meeting load ${chip(e.schedule.level)}</h3>${lineChart([{ values: e.schedule.weeks.map((w) => w.score), color: "#8b66e8", fill: true }], { labels: weekLabels(e.schedule.weeks), height: 130 })}
      <h3 style="margin-top:14px">Body check-ins ${e.body && e.body.level ? bodyChip(e.body.level, e.body.persistent) : ""}</h3>
      <p class="small muted" style="margin-top:4px">${!e.physio_consent ? "This person has not turned body check-ins on." : !e.body || !e.body.ready ? "Still learning this person's normal range." : !e.body.level ? "No readings in the last 3 days." : e.body.level === "normal" ? "Recent readings are within their own normal range." : `Recent readings are above their own normal range${e.body.persistent ? ", on more than one occasion" : ""}. You see the level only, not the numbers.`}</p>
      ${e.assistant && e.assistant.level ? `<h3 style="margin-top:14px">Assistant chats ${chip(e.assistant.level)}</h3><p class="small muted" style="margin-top:4px">Overall tone of what they told PulseBot. The words stay private.</p>` : ""}
      <h3 style="margin-top:14px">Weekly check-ins</h3><div class="tags" style="margin-top:8px">${e.mood.weeks.map((w) => chip(w.label || "okay", w.label ? cap(w.label) : "–")).join(" ") || '<span class="muted small">None yet</span>'}</div>
      ${e.mood.missed ? `<p class="tiny muted" style="margin-top:6px">Skipped ${e.mood.missed} recent check-in${e.mood.missed > 1 ? "s" : ""}.</p>` : ""}
      ${e.checkins.length ? `<h3 style="margin-top:18px">Your recent check-ins</h3>${e.checkins.slice(0, 3).map((c) => `<p class="small" style="margin-top:6px"><span class="muted">${ago(c.at)} · ${esc(c.by_name)}:</span> ${esc(c.text)}</p>`).join("")}` : ""}
      ${e.meeting ? `<div class="tip">A check-in chat is booked: ${esc(e.meeting.title || "")} ${e.meeting.start ? shortDate(parseLocal(e.meeting.start)) + " " + hm(parseLocal(e.meeting.start)) : ""}</div>` : ""}
      <div class="actions" style="justify-content:flex-start;margin-top:22px"><button class="btn" id="dr-msg">Send a check-in</button><button class="btn quiet" id="dr-book">Book a time</button></div>`;
    $$("[data-close]", d.el).forEach((b) => b.addEventListener("click", d.close));
    $("#dr-msg", d.el).addEventListener("click", () => checkinModal([{ id: e.id, name: e.name }], { onDone: () => { d.close(); refresh && refresh(); } }));
    $("#dr-book", d.el).addEventListener("click", () => { const t = addDays(new Date(), 1); openMeetingModal({ invitees: [{ id: e.id, name: e.name }], title: "Check-in chat", kind: "wellbeing", date: ymd(t), start: "11:00", end: "11:30", onDone: () => { d.close(); refresh && refresh(); } }); });
  } catch (ex) { d.close(); toast(ex.message, true); }
}

// ------------------------------------------------------------ page: overview
PAGES.overview = async (page, live) => {
  const [ov, hi] = await Promise.all([api("/api/manager/overview"), api("/api/manager/employees?risk=High")]);
  if (!live()) return;
  const c = ov.counts, isAdmin = state.user.role === "admin";
  const highs = hi.employees;
  const weeks = ov.weeks || [];
  $("#top-actions").innerHTML = `<button class="btn" id="bulk" ${highs.length ? "" : "disabled"}>Message all high risk (${highs.length})</button>`;
  $("#bulk").addEventListener("click", () => checkinModal(highs.map((h) => ({ id: h.id, name: h.name })), { bulk: true, onDone: () => route() }));
  const stat = (n, label, color, sub) => `<div class="card stat-card"><div class="stat"><b>${n}</b><span>${label}</span></div><div class="bar"><div style="height:100%;width:${Math.min(100, (n / (c.total || 1)) * 100)}%;background:${color};border-radius:5px"></div></div>${sub ? `<div class="tiny muted" style="margin-top:8px">${sub}</div>` : ""}</div>`;
  page.innerHTML = `
  <p class="muted" style="margin:-4px 0 18px">${esc(ov.scope_name)} · ${c.total} people. You see levels and reasons, never what people wrote.</p>
  <div class="stats">
    ${stat(c.high, "Need a check-in", "#c53a62", "Strain on more than one signal")}
    ${stat(c.medium, "Worth watching", "#b97500", "One signal is elevated")}
    ${stat(c.low, "Doing fine", "#1f8a7d")}
    <div class="card stat-card"><div class="stat"><b>${ov.checkins_sent_7d}</b><span>Check-ins sent, 7 days</span></div><div class="tiny muted" style="margin-top:20px">${ov.wellbeing_meetings_booked} chat${ov.wellbeing_meetings_booked === 1 ? "" : "s"} booked</div></div>
  </div>
  <div style="margin-top:18px"><section class="card"><div class="row-between"><div><h2>Who to reach out to first</h2><p class="muted small">Sorted by how many signals point the same way.</p></div></div>
      <div class="tbl-wrap"><table class="tbl" id="fu"><thead><tr><th>Person</th><th>Messages</th><th>Calendar</th><th>Body</th><th>Mood</th><th>Last check-in</th><th></th></tr></thead><tbody>
      ${ov.followups.length ? ov.followups.map((r) => `<tr class="click" data-id="${r.id}"><td><div class="person">${avatar(r.name, "sm")}<div><b>${esc(r.name)}</b><small>${esc(r.team)}</small></div></div></td>${sigCells(r)}<td class="small muted">${r.last_checkin ? ago(r.last_checkin) : "None"}</td><td style="text-align:right"><button class="btn quiet sm" data-msg="${r.id}">Message</button></td></tr>`).join("") : `<tr><td colspan="7"><div class="empty" style="border:0"><b>No one needs follow-up</b>Nice. Check back after the next week of data.</div></td></tr>`}
      </tbody></table></div></section>
</div>
  <div class="grid g2" style="margin-top:18px;align-items:start"><section class="card"><h2>Trend, last 6 weeks</h2><p class="muted small">Share of people with stressed messages or a busy calendar.</p>
        ${lineChart([{ values: weeks.map((w) => w.stressed_share), color: "#c53a62" }, { values: weeks.map((w) => w.busy_share), color: "#6d3fd9" }], { labels: weekLabels(weeks), height: 150 })}
        <div class="legend" style="margin-top:6px"><span style="color:#c53a62">● Stressed messages (%)</span><span style="color:#6d3fd9">● Busy or hectic week (%)</span></div></section>
      <section class="card"><h3>Calendars</h3>${distBars(ov.schedule_levels, ["light", "balanced", "busy", "hectic"])}<h3 style="margin-top:18px">Message tone</h3>${distBars(ov.tone_levels, ["calm", "tense", "stressed"])}</section>
    </div>
  ${isAdmin && ov.teams ? `<section class="card" style="margin-top:18px"><h2>Teams</h2><div class="tbl-wrap"><table class="tbl"><thead><tr><th>Team</th><th>People</th><th>Need a check-in</th><th>Watching</th></tr></thead><tbody>${ov.teams.map((t) => `<tr><td><b>${esc(t.name)}</b></td><td>${t.size}</td><td>${t.high ? chip("high", t.high) : '<span class="muted">0</span>'}</td><td>${t.medium ? chip("medium", t.medium) : '<span class="muted">0</span>'}</td></tr>`).join("")}</tbody></table></div></section>` : ""}
  <section class="card" style="margin-top:18px"><h2>Everyone</h2>
    <div class="toolbar" style="margin-top:12px"><input class="input" id="q" placeholder="Search by name or ID" aria-label="Search people"><select class="input" id="rk" aria-label="Filter by level"><option value="">All levels</option><option value="High">High</option><option value="Medium">Medium</option><option value="Low">Low</option></select></div>
    <div class="tbl-wrap"><table class="tbl"><thead><tr><th>Person</th>${isAdmin ? "<th>Team</th>" : ""}<th>Level</th><th>Messages</th><th>Calendar</th><th>Body</th><th>Mood</th></tr></thead><tbody id="all"></tbody></table></div><div id="more" style="text-align:center;margin-top:12px"></div></section>`;
  const open = (id) => employeeDrawer(id, () => route());
  $$("#fu tr.click").forEach((tr) => tr.addEventListener("click", (e) => { if (e.target.closest("[data-msg]")) return; open(+tr.dataset.id); }));
  $$("#fu [data-msg]").forEach((b) => b.addEventListener("click", () => { const r = ov.followups.find((x) => x.id === +b.dataset.msg); checkinModal([{ id: r.id, name: r.name }], { onDone: () => route() }); }));
  let shown = 40, rows = [];
  const draw = () => {
    $("#all").innerHTML = rows.slice(0, shown).map((r) => `<tr class="click" data-id="${r.id}"><td><div class="person">${avatar(r.name, "sm")}<div><b>${esc(r.name)}</b><small>${esc(r.emp_code || "")}</small></div></div></td>${isAdmin ? `<td class="small">${esc(r.team)}</td>` : ""}<td>${chip(r.risk)}</td>${sigCells(r)}</tr>`).join("") || `<tr><td colspan="7" class="muted" style="padding:20px">No one matches.</td></tr>`;
    $$("#all tr.click").forEach((tr) => tr.addEventListener("click", () => open(+tr.dataset.id)));
    $("#more").innerHTML = rows.length > shown ? `<button class="btn ghost sm" id="more-b">Show more (${rows.length - shown})</button>` : "";
    const mb = $("#more-b"); if (mb) mb.onclick = () => { shown += 40; draw(); };
  };
  let t;
  const fetchRows = async () => { try { const r = await api(`/api/manager/employees?q=${encodeURIComponent($("#q").value.trim())}&risk=${$("#rk").value}`); if (!live()) return; rows = r.employees; shown = 40; draw(); } catch (e) { toast(e.message, true); } };
  $("#q").addEventListener("input", () => { clearTimeout(t); t = setTimeout(fetchRows, 250); });
  $("#rk").addEventListener("change", fetchRows);
  fetchRows();
};

// ------------------------------------------------------------ page: people (admin)
PAGES.people = async (page, live) => {
  const first = await api("/api/admin/users?limit=60");
  if (!live()) return;
  const teams = first.teams;
  page.innerHTML = `<p class="muted" style="margin:-4px 0 18px">Change someone's role or team. Leads see only their own team.</p>
    <section class="card"><div class="toolbar"><input class="input" id="pq" placeholder="Search by name, username or ID" aria-label="Search users" style="min-width:260px"><span class="muted small" id="pc"></span></div>
    <div class="tbl-wrap"><table class="tbl"><thead><tr><th>Person</th><th>Username</th><th>Role</th><th>Team</th></tr></thead><tbody id="pb"></tbody></table></div></section>`;
  const draw = (data) => {
    $("#pc").textContent = `Showing ${data.users.length} of ${data.total}`;
    $("#pb").innerHTML = data.users.map((u) => `<tr data-id="${u.id}"><td><div class="person">${avatar(u.name, "sm")}<div><b>${esc(u.name)}</b><small>${esc(u.emp_code || "")}</small></div></div></td><td class="small">${esc(u.username)}</td>
      <td><select class="input" data-f="role" aria-label="Role for ${esc(u.name)}" style="width:130px">${["employee", "lead", "admin"].map((r) => `<option value="${r}" ${u.role === r ? "selected" : ""}>${ROLE_LABEL[r]}</option>`).join("")}</select></td>
      <td><select class="input" data-f="team" aria-label="Team for ${esc(u.name)}" style="width:230px"><option value="">No team</option>${teams.map((t) => `<option value="${t.id}" ${u.team_id === t.id ? "selected" : ""}>${esc(t.name)}</option>`).join("")}</select></td></tr>`).join("");
    $$("#pb select").forEach((s) => s.addEventListener("change", async () => {
      const id = +s.closest("tr").dataset.id, body = s.dataset.f === "role" ? { role: s.value } : { team_id: +s.value || null };
      if (s.dataset.f === "team" && !s.value) { toast("Pick a team.", true); return; }
      try { await api("/api/admin/users/" + id, { method: "PATCH", body }); toast("Saved."); } catch (e) { toast(e.message, true); fetchUsers(); }
    }));
  };
  const fetchUsers = async () => { try { draw(await api("/api/admin/users?limit=60&q=" + encodeURIComponent($("#pq").value.trim()))); } catch (e) { toast(e.message, true); } };
  draw(first);
  let t; $("#pq").addEventListener("input", () => { clearTimeout(t); t = setTimeout(fetchUsers, 250); });
};

// ------------------------------------------------------------ page: settings
PAGES.settings = async (page, live) => {
  const u = state.user;
  page.innerHTML = `<div class="grid g2" style="align-items:start">
    <section class="card"><h2>Your account</h2><div class="person" style="margin:14px 0">${avatar(u.name, "lg")}<div><b>${esc(u.name)}</b><small>${ROLE_LABEL[u.role]}${u.team_name ? " · " + esc(u.team_name) : ""}<br>@${esc(u.username)}</small></div></div>
      <hr style="border:0;border-top:1px solid var(--line);margin:18px 0">
      <div class="switch"><div><h3>Read my messages for tone</h3><p class="small muted" style="margin-top:4px">When on, the messages you send are checked for stress wording. You see the result next to each message. Your manager sees only an overall level and short reasons, never the text. Turn it off any time and nothing new is analysed.</p></div>
        <button class="tog" id="consent" role="switch" aria-checked="${u.consent}" aria-label="Read my messages for tone"></button></div>
      <hr style="border:0;border-top:1px solid var(--line);margin:18px 0">
      <div class="switch"><div><h3>Use my body check-ins</h3><p class="small muted" style="margin-top:4px">When on, your heart rate and skin readings from the check-in device are compared with your own normal range. You see the numbers. Your manager sees only a level (normal, elevated or high), never the numbers. These are wellbeing hints, not medical results.</p></div>
        <button class="tog" id="physio-consent" role="switch" aria-checked="${!!u.physio_consent}" aria-label="Use my body check-ins"></button></div></section>
    <section class="card"><h2>Change password</h2><form id="pw" style="margin-top:12px"><label class="field"><span>Current password</span><input class="input" type="password" name="old" autocomplete="current-password"></label>
      <label class="field"><span>New password</span><input class="input" type="password" name="new" autocomplete="new-password" placeholder="At least 8 characters"></label><p class="err" id="pw-err" role="alert"></p><button class="btn">Update password</button></form></section></div>`;
  $("#consent").addEventListener("click", async (e) => {
    const on = e.currentTarget.getAttribute("aria-checked") !== "true";
    try { const r = await api("/api/me/settings", { method: "PATCH", body: { consent: on } }); state.user = r.user; e.currentTarget.setAttribute("aria-checked", on); toast(on ? "Message analysis is on." : "Message analysis is off."); } catch (ex) { toast(ex.message, true); }
  });
  $("#physio-consent").addEventListener("click", async (e) => {
    const on = e.currentTarget.getAttribute("aria-checked") !== "true";
    try { const r = await api("/api/me/settings", { method: "PATCH", body: { physio_consent: on } }); state.user = r.user; e.currentTarget.setAttribute("aria-checked", on); toast(on ? "Body check-ins are on." : "Body check-ins are off."); } catch (ex) { toast(ex.message, true); }
  });
  $("#pw").addEventListener("submit", async (e) => {
    e.preventDefault(); const f = e.target, err = $("#pw-err"); err.textContent = "";
    if (f.new.value.length < 8) { err.textContent = "Use at least 8 characters."; return; }
    try { await api("/api/me/password", { method: "POST", body: { old: f.old.value, new: f.new.value } }); f.reset(); toast("Password updated."); } catch (ex) { err.textContent = ex.message; }
  });
};

// ------------------------------------------------------------ boot
(async function init() {
  try {
    const r = await fetch("/api/auth/me", { credentials: "same-origin" });
    if (r.ok) { state.user = (await r.json()).user; startShell(); return; }
  } catch (e) { /* offline */ }
  renderAuth();
})();
