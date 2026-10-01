# Dashboard Shell (Phase A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give Spatial a real dashboard window (Home, Ask logs, Dictation logs, Settings) and strip status/settings/history out of the compact Ask panel; route startup, hotkey, server and autostart errors to Settings.

**Architecture:** A fourth Tauri window `dashboard` (plain HTML/JS like the others) shares the app's localStorage origin with `panel`, so settings and the content-free activity log keep working unchanged. Testable view logic lives in `ui/dashboard-model.js` (UMD, Node-tested like `dictation.js`). Rust routes app-level notices to `dashboard` instead of `panel`. Server gains one route to clear Ask history.

**Tech Stack:** Tauri v2 (Rust), vanilla JS, FastAPI + SQLite, `node --test`, pytest.

**Spec:** `docs/superpowers/specs/2026-10-01-desktop-dashboard-design.md` (phase A)

## Global Constraints

- Mark is a reference only; nothing here clicks, types or deletes outside Spatial's own data.
- No new runtime dependencies; no telemetry; activity log stays content-free (event kinds + times only, max 40).
- Provider keys are never echoed or logged; API token field stays `type=password`.
- All server routes stay behind `require_token`.
- Model/server text is rendered with `textContent`/text nodes only (`el()` helper), never `innerHTML`.
- Closing any window only hides it (existing `on_window_event`); app lives in the tray until Quit.
- Dictation tasks (phase C), reminders (D), recall popup (E), Deepgram (F) are **out of scope**.

## Review Focus

- Server down when the dashboard opens: Home shows "Needs attention", no exception (model test, `health=null`).
- Launch via autostart (`--autostart`) must **not** pop the dashboard; a normal launch must.
- Second app launch focuses the dashboard, not the Ask panel.
- Hotkey-registration / server-start failure shows in Settings Status, never as an error in the Ask panel.
- "Clear Ask history" with more than 200 rows really empties the table (server route, one call).
- Hostile page titles/questions (`<img onerror=…>`) render as text in Ask logs (model returns plain strings; view uses `el()`).

## File Structure

| File | Responsibility |
|---|---|
| `server/app/store.py` (modify) | `clear()` deletes all contexts |
| `server/app/main.py` (modify) | `DELETE /api/contexts` |
| `desktop/ui/dashboard-model.js` (create) | Pure logic: activity log, status cards, history card view-model |
| `desktop/ui/dashboard.html` / `dashboard.css` / `dashboard.js` (create) | Window UI: 4 sections, Settings, notices |
| `desktop/tests/dashboard-model.test.cjs` (create) | Node tests for the model |
| `desktop/src-tauri/tauri.conf.json`, `capabilities/default.json` (modify) | Register `dashboard` window + permissions |
| `desktop/src-tauri/src/main.rs` (modify) | `show_dashboard`, notice routing, tray/single-instance/autostart arg |
| `desktop/ui/panel.html`, `panel.js` (modify) | Remove home/settings/history/status; use shared activity helper |
| `docs/*` (modify) | TASKS, ARCHITECTURE, DESIGN, MEMORY, AGENTS layout |

---

### Task 1: Server — clear all Ask history

**Files:**
- Modify: `server/app/store.py` (after `delete`, ~line 66)
- Modify: `server/app/main.py` (before `@app.get("/api/contexts/{context_id}"…)`, ~line 717)
- Test: `server/tests/test_server.py`

**Interfaces:**
- Produces: `store.clear() -> int` (rows deleted); `DELETE /api/contexts` → `{"deleted": <int>}`

- [ ] **Step 1: Write the failing test** (append to `server/tests/test_server.py`)

```python
def test_clear_all_contexts_removes_every_row_and_needs_token(monkeypatch):
    from app import store
    with TestClient(app) as client:
        for n in range(3):
            store.create({"title": f"t{n}"}, f"q{n}", [], {}, {"history": []})
        monkeypatch.setattr(settings, "api_token", "secret")
        assert client.delete("/api/contexts").status_code == 401
        ok = client.delete("/api/contexts", headers={"Authorization": "Bearer secret"})
        assert ok.status_code == 200 and ok.json()["deleted"] >= 3
        monkeypatch.setattr(settings, "api_token", "")
        assert client.get("/api/contexts?limit=200").json() == []
```

- [ ] **Step 2: Run, expect failure**

Run: `cd server && python -m pytest tests/test_server.py::test_clear_all_contexts_removes_every_row_and_needs_token -q`
Expected: FAIL (405 Method Not Allowed).

- [ ] **Step 3: Implement**

`store.py`:
```python
def clear() -> int:
    with connect() as db:
        return db.execute("delete from contexts").rowcount
```
`main.py`:
```python
@app.delete("/api/contexts", dependencies=[Depends(require_token)])
def clear_contexts():
    return {"deleted": store.clear()}
```
(If `settings` is not imported in `test_server.py`, use the same import the nearby auth test at line ~130 uses.)

- [ ] **Step 4: Run, expect pass**

Run: `cd server && python -m pytest -q`
Expected: all pass (251+1).

- [ ] **Step 5: Commit**
```bash
git add server/app/store.py server/app/main.py server/tests/test_server.py
git commit -m "feat(server): DELETE /api/contexts clears Ask history"
```

---

### Task 2: Dashboard model (pure logic, Node-tested)

**Files:**
- Create: `desktop/ui/dashboard-model.js`
- Test: `desktop/tests/dashboard-model.test.cjs`

**Interfaces:**
- Produces on `SpatialDashboard` (also `module.exports`):
  - `ACTIVITY_KEY = 'spatial.activity'`, `MAX_ACTIVITY = 40`
  - `recordActivity(storage, kind, now = new Date()) -> void` — `storage` is `{load(key, fallback), save(key, value)}` (i.e. `window.Spatial`)
  - `readActivity(storage) -> [{at, kind}]` (newest first; tolerates corrupt JSON → `[]`)
  - `statusCards(health, snoozed) -> [[title, value], …]` (`health` may be `null`)
  - `historyCard(context) -> {id, title, when, question}` (all strings)

- [ ] **Step 1: Write failing tests**

```js
const test = require('node:test');
const assert = require('node:assert/strict');
const D = require('../ui/dashboard-model.js');

const memory = () => { const m = {}; return { load: (k, f) => (k in m ? m[k] : f), save: (k, v) => { if (v) m[k] = v; else delete m[k]; } }; };

test('activity keeps newest first, caps at 40 and stores kinds only', () => {
  const s = memory();
  for (let i = 0; i < 45; i++) D.recordActivity(s, 'event ' + i, new Date(2026, 9, 1, 0, i));
  const list = D.readActivity(s);
  assert.equal(list.length, 40);
  assert.equal(list[0].kind, 'event 44');
  assert.deepEqual(Object.keys(list[0]).sort(), ['at', 'kind']);
});

test('corrupt activity storage reads as empty and recovers', () => {
  const s = memory(); s.save(D.ACTIVITY_KEY, '{not json');
  assert.deepEqual(D.readActivity(s), []);
  D.recordActivity(s, 'ok');
  assert.equal(D.readActivity(s)[0].kind, 'ok');
});

test('status cards say Needs attention when the server is down', () => {
  const cards = Object.fromEntries(D.statusCards(null, false));
  assert.equal(cards['Server'], 'Needs attention');
  assert.equal(cards['Answer provider'], 'Not configured');
  assert.equal(cards['Speech to text'], 'Needs attention');
});

test('status cards reflect a healthy server and snooze', () => {
  const health = { providers: [{ configured: true }], audio: { backend: 'local', stt: { installed: true }, tts: { installed: true, enabled: true, voice: 'system' } } };
  const cards = Object.fromEntries(D.statusCards(health, true));
  assert.equal(cards['Server'], 'Ready');
  assert.equal(cards['Answer provider'], 'Configured');
  assert.equal(cards['Speech to text'], 'Ready · local');
  assert.equal(cards['Text to speech'], 'Ready · Windows voice');
  assert.equal(cards['Ask shortcut'], 'Snoozed');
});

test('history card falls back gracefully and keeps hostile text as plain strings', () => {
  const card = D.historyCard({ id: 'a', updated_at: '2026-10-01T10:00:00+00:00', question: 'q', page: { title: '<img src=x onerror=alert(1)>' }, answer: { history: [{ question: 'last?' }] }, turns: 2 });
  assert.equal(card.title, '<img src=x onerror=alert(1)>');
  assert.equal(card.question, 'last?');
  assert.equal(typeof card.when, 'string');
  assert.equal(D.historyCard({ id: 'b', updated_at: '2026-10-01T10:00:00+00:00', page: {}, answer: {} }).title, 'Spatial Ask');
});
```

- [ ] **Step 2: Run, expect failure**

Run: `cd desktop && node --test tests/dashboard-model.test.cjs`
Expected: FAIL — cannot find module `../ui/dashboard-model.js`.

- [ ] **Step 3: Implement `desktop/ui/dashboard-model.js`**

```js
/* Dashboard view logic with no DOM access, so it can be unit-tested in Node. Activity is content-free (kind + time). */
(function (root) {
  'use strict';
  const ACTIVITY_KEY = 'spatial.activity';
  const MAX_ACTIVITY = 40;

  function readActivity(storage) {
    try {
      const list = JSON.parse(storage.load(ACTIVITY_KEY, '[]'));
      return Array.isArray(list) ? list.filter((e) => e && typeof e.kind === 'string' && typeof e.at === 'string') : [];
    } catch (_) { return []; }
  }

  function recordActivity(storage, kind, now) {
    const events = readActivity(storage);
    events.unshift({ at: (now || new Date()).toISOString(), kind: String(kind) });
    storage.save(ACTIVITY_KEY, JSON.stringify(events.slice(0, MAX_ACTIVITY)));
  }

  function statusCards(health, snoozed) {
    const audio = (health && health.audio) || {};
    const providers = (health && health.providers) || [];
    const stt = audio.stt && audio.stt.installed;
    const tts = audio.tts && audio.tts.installed && audio.tts.enabled;
    const voice = audio.backend === 'nvidia' ? 'NVIDIA' : audio.tts && audio.tts.voice === 'system' ? 'Windows voice' : 'local voice';
    return [
      ['Server', health ? 'Ready' : 'Needs attention'],
      ['Answer provider', providers.some((p) => p.configured) ? 'Configured' : 'Not configured'],
      ['Speech to text', stt ? 'Ready · ' + (audio.backend || 'local') : 'Needs attention'],
      ['Text to speech', tts ? 'Ready · ' + voice : 'Needs attention'],
      ['Ask shortcut', snoozed ? 'Snoozed' : 'Alt+Shift+S enabled'],
      ['Dictation', 'Alt+Shift+D · Dictate button'],
    ];
  }

  function historyCard(context) {
    const page = context.page || {};
    const turns = (context.answer && context.answer.history) || [];
    const latest = turns[turns.length - 1] || {};
    return {
      id: String(context.id),
      title: String(page.title || page.surface || 'Spatial Ask'),
      when: new Date(context.updated_at).toLocaleString() + ' · ' + (context.turns || 1) + ' turn(s)',
      question: String(latest.question || context.question || 'Saved question'),
    };
  }

  root.SpatialDashboard = { ACTIVITY_KEY, MAX_ACTIVITY, readActivity, recordActivity, statusCards, historyCard };
  if (typeof module !== 'undefined') module.exports = root.SpatialDashboard;
})(typeof window === 'undefined' ? globalThis : window);
```

- [ ] **Step 4: Run, expect pass**

Run: `cd desktop && node --test tests/dashboard-model.test.cjs tests/dictation.test.cjs`
Expected: all pass.

- [ ] **Step 5: Commit**
```bash
git add desktop/ui/dashboard-model.js desktop/tests/dashboard-model.test.cjs
git commit -m "feat(desktop): dashboard view-model with activity log and status cards"
```

---

### Task 3: Dashboard window UI + Tauri registration

**Files:**
- Create: `desktop/ui/dashboard.html`, `desktop/ui/dashboard.css`, `desktop/ui/dashboard.js`
- Modify: `desktop/src-tauri/tauri.conf.json` (add window), `desktop/src-tauri/capabilities/default.json` (add `"dashboard"` to `windows`; add `"core:window:allow-unminimize"`)

**Interfaces:**
- Consumes: `Spatial.{load,save,headers,server}` (`shared.js`), `SpatialDashboard.*` (Task 2), Tauri commands `pairing_token`, `startup_notice`, autostart plugin.
- Consumes events: `spatial://open` `{view: 'home'|'ask'|'dictation'|'settings'}`, `spatial://notice` `{message}`, `spatial://snooze`.
- Produces: window label `dashboard` (Task 4 shows/emits to it); `Spatial.load('spatial.snoozed')` is reset to `'0'` on app start.

- [ ] **Step 1: Register the window** — add to `app.windows` in `tauri.conf.json` (after `panel`):

```json
{
  "label": "dashboard",
  "url": "dashboard.html",
  "title": "Spatial",
  "width": 960,
  "height": 680,
  "minWidth": 640,
  "minHeight": 480,
  "visible": false,
  "decorations": true,
  "resizable": true,
  "center": true
}
```
In `capabilities/default.json`: `"windows": ["overlay", "panel", "dictate", "dashboard"]`, and add `"core:window:allow-unminimize"`, `"core:window:allow-set-title"`.

- [ ] **Step 2: Create `dashboard.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Spatial</title>
<link rel="stylesheet" href="dashboard.css">
</head>
<body>
<aside>
  <h1>Spatial</h1>
  <nav id="nav" aria-label="Dashboard sections">
    <button data-view="home" aria-selected="true">Home</button>
    <button data-view="ask" aria-selected="false">Ask logs</button>
    <button data-view="dictation" aria-selected="false">Dictation logs</button>
    <button data-view="settings" aria-selected="false">Settings <span id="noticeBadge" hidden>!</span></button>
  </nav>
  <p class="hint">Alt+Shift+S point &amp; ask<br>Alt+Shift+D dictate</p>
</aside>
<main>
  <section id="view-home">
    <h2>Home</h2>
    <div class="status-cards" id="statusCards"></div>
    <div class="actions"><button id="refreshStatus">Refresh</button><button id="clearActivity">Clear activity</button><button id="copyDiagnostics">Copy diagnostics</button></div>
    <h3>Recent activity · this device</h3>
    <ul id="activityList"></ul>
    <p class="muted">Activity keeps event types and times only. It is not sent anywhere.</p>
  </section>
  <section id="view-ask" hidden>
    <h2>Ask logs</h2>
    <p class="muted">Saved Ask conversations on this device. You can read and delete them.</p>
    <div class="actions"><button id="refreshHistory">Refresh</button><button id="clearHistory" class="danger">Clear all</button></div>
    <div id="historyList"></div>
  </section>
  <section id="view-dictation" hidden>
    <h2>Dictation logs</h2>
    <p class="muted">Dictation entries are saved here in the next update. For now, dictate with Alt+Shift+D and copy or download the result.</p>
  </section>
  <section id="view-settings" hidden>
    <h2>Settings</h2>
    <h3>Status</h3>
    <ul id="noticeList"></ul>
    <h3>Server</h3>
    <label for="server">Server URL</label>
    <input type="url" id="server" placeholder="http://127.0.0.1:8787">
    <label for="apiToken">Custom server API token (leave blank for the bundled server)</label>
    <input type="password" id="apiToken" autocomplete="off">
    <button id="copyPairingToken" type="button">Copy browser extension pairing token</button>
    <h3>Answers</h3>
    <label class="check"><input type="checkbox" id="research"> Verify with web sources when needed</label>
    <label class="check"><input type="checkbox" id="systemOne"> Use TypeSafe Jev to resolve the mark (sends candidate text and the question when configured)</label>
    <h3>Dictation</h3>
    <label class="check"><input type="checkbox" id="dictatePolish"> Polish dictation with the configured answer provider (sends transcript text only)</label>
    <label for="dictionary">Personal dictionary (one “heard phrase|preferred spelling” per line; stays on this device)</label>
    <textarea id="dictionary" rows="4" maxlength="4000" spellcheck="false"></textarea>
    <p class="muted">Microphone audio goes to NVIDIA speech when configured; otherwise transcription runs on this computer.</p>
    <h3>App</h3>
    <label class="check"><input type="checkbox" id="autostart"> Start Spatial when I sign in</label>
    <p class="muted">Hotkeys: Alt+Shift+S and Alt+Shift+D anywhere. The mark is a reference only: Spatial explains, it never clicks or types.</p>
    <div class="actions"><button id="saveSettings" type="button">Save</button><span id="saved" class="muted" role="status"></span></div>
  </section>
</main>
<script src="shared.js"></script>
<script src="dashboard-model.js"></script>
<script src="dashboard.js"></script>
</body>
</html>
```

- [ ] **Step 3: Create `dashboard.css`**

```css
:root { --bg:#fff; --fg:#17171c; --muted:#6b6b7b; --line:#e6e6ee; --accent:#2f6feb; --chip:#eaf1fe; --chip-hover:#d8e6fd; --err:#9b1c1c; --err-bg:#fdecec; }
@media (prefers-color-scheme: dark) { :root { --bg:#17181d; --fg:#ececf1; --muted:#9a9aab; --line:#2b2d36; --chip:#22314f; --chip-hover:#2c3f66; --err:#ffb4b4; --err-bg:#3a1c1c; } }
* { box-sizing: border-box; }
html, body { margin:0; height:100%; background:var(--bg); color:var(--fg); font:14px/1.5 system-ui, sans-serif; }
body { display:grid; grid-template-columns: 200px 1fr; }
aside { border-right:1px solid var(--line); padding:16px 12px; display:flex; flex-direction:column; gap:12px; }
aside h1 { margin:0 0 4px 8px; font-size:16px; }
nav { display:flex; flex-direction:column; gap:2px; }
nav button { all:unset; cursor:pointer; padding:7px 10px; border-radius:8px; color:var(--muted); }
nav button:hover { background:var(--chip); color:var(--fg); }
nav button[aria-selected="true"] { background:var(--chip); color:var(--accent); font-weight:600; }
#noticeBadge { background:var(--err); color:var(--bg); border-radius:999px; padding:0 6px; font-size:11px; margin-left:4px; }
.hint { margin-top:auto; font-size:12px; color:var(--muted); padding-left:8px; }
main { overflow-y:auto; padding:20px 28px; max-width:860px; }
h2 { margin:0 0 10px; font-size:18px; } h3 { margin:18px 0 6px; font-size:13px; text-transform:uppercase; letter-spacing:.04em; color:var(--muted); }
.muted { color:var(--muted); font-size:12px; }
.status-cards { display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; margin-bottom:12px; }
.status-card, .history-card { border:1px solid var(--line); border-radius:10px; padding:10px; }
.status-card small { display:block; color:var(--muted); font-size:11px; } .status-card strong { font-size:13px; }
.actions { display:flex; flex-wrap:wrap; gap:8px; margin:10px 0 14px; align-items:center; }
button { font:inherit; }
main button { padding:6px 12px; border:0; border-radius:8px; background:var(--chip); color:var(--fg); cursor:pointer; }
main button:hover { background:var(--chip-hover); } main button.danger { color:var(--err); }
#saveSettings { background:var(--accent); color:#fff; }
.history-card { margin:8px 0; } .history-card .title { font-weight:600; background:transparent; padding:0; text-align:left; }
.history-card p { margin:4px 0 0; color:var(--muted); font-size:12px; overflow-wrap:anywhere; }
.history-detail { white-space:pre-wrap; overflow-wrap:anywhere; padding:10px; border:1px solid var(--line); border-radius:9px; margin:8px 0; }
label { display:block; font-size:12px; color:var(--muted); margin:10px 0 4px; } label.check { color:var(--fg); }
input[type=text], input[type=password], input[type=url], textarea { width:100%; padding:7px 9px; border-radius:8px; border:1px solid var(--line); background:var(--bg); color:var(--fg); font:inherit; }
input:focus, textarea:focus { outline:2px solid var(--accent); outline-offset:-1px; }
#noticeList { padding-left:18px; } #noticeList li.err { color:var(--err); } ul { padding-left:18px; }
```

- [ ] **Step 4: Create `dashboard.js`**

```js
/* Dashboard: Home (status + activity), Ask logs, Dictation logs (placeholder until phase C), Settings + app notices. */
(function () {
  'use strict';
  const T = window.__TAURI__;
  const win = T.window.getCurrentWindow();
  const D = window.SpatialDashboard;
  const $ = (id) => document.getElementById(id);
  const VIEWS = ['home', 'ask', 'dictation', 'settings'];
  const notices = [];
  let view = 'home';
  let health = null;
  let timer = null;

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => { if (k === 'class') node.className = v; else node.setAttribute(k, v); });
    (children || []).forEach((c) => node.append(c));
    return node;
  }

  const snoozed = () => Spatial.load('spatial.snoozed', '0') === '1';
  const activity = (kind) => { D.recordActivity(Spatial, kind); if (view === 'home') renderActivity(); };

  function addNotice(message) {
    if (!message || notices.includes(message)) return;
    notices.push(message);
    activity('An operation needs attention');
    renderNotices();
  }

  function renderNotices() {
    $('noticeList').replaceChildren(...(notices.length
      ? notices.map((m) => el('li', { class: 'err' }, [m]))
      : [el('li', { class: 'muted' }, ['Everything looks fine.'])]));
    $('noticeBadge').hidden = !notices.length;
  }

  function renderActivity() {
    const events = D.readActivity(Spatial);
    $('activityList').replaceChildren(...(events.length
      ? events.map((e) => el('li', {}, [new Date(e.at).toLocaleString() + ' · ' + e.kind]))
      : [el('li', { class: 'muted' }, ['No recent activity.'])]));
  }

  async function refreshStatus() {
    try {
      const response = await fetch(Spatial.server() + '/api/health', { headers: await Spatial.headers() });
      if (!response.ok) throw new Error('health check failed');
      const next = await response.json();
      if (health === null && timer !== null) activity('Server reconnected');
      health = next;
    } catch (_) { health = null; }
    $('statusCards').replaceChildren(...D.statusCards(health, snoozed()).map(([title, value]) =>
      el('div', { class: 'status-card' }, [el('small', {}, [title]), el('strong', {}, [value])])));
    renderActivity();
  }

  async function show(next) {
    view = VIEWS.includes(next) ? next : 'home';
    VIEWS.forEach((name) => { $('view-' + name).hidden = name !== view; });
    document.querySelectorAll('#nav button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.view === view)));
    if (timer) { clearInterval(timer); timer = null; }
    if (view === 'home') { await refreshStatus(); timer = setInterval(refreshStatus, 10000); }
    if (view === 'ask') refreshHistory();
    if (view === 'settings') await loadSettings();
  }

  async function reveal(next) {
    await show(next);
    await win.show(); await win.unminimize(); await win.setFocus();
  }

  async function refreshHistory() {
    const host = $('historyList');
    host.replaceChildren(el('p', { class: 'muted' }, ['Loading saved conversations…']));
    try {
      const response = await fetch(Spatial.server() + '/api/contexts?limit=100', { headers: await Spatial.headers() });
      if (!response.ok) throw new Error('History could not be loaded.');
      const contexts = await response.json();
      host.replaceChildren();
      if (!contexts.length) { host.append(el('p', { class: 'muted' }, ['No saved Ask conversations.'])); return; }
      contexts.forEach((context) => {
        const card = D.historyCard(context);
        const node = el('article', { class: 'history-card' });
        const open = el('button', { type: 'button', class: 'title' }, [card.title]);
        open.onclick = () => showDetail(node, context);
        const remove = el('button', { type: 'button', class: 'danger', title: 'Delete this saved conversation' }, ['Delete']);
        remove.onclick = async () => {
          try {
            const r = await fetch(Spatial.server() + '/api/contexts/' + encodeURIComponent(card.id), { method: 'DELETE', headers: await Spatial.headers() });
            if (!r.ok) throw new Error('delete failed');
            refreshHistory();
          } catch (_) { addNotice('Could not delete a saved conversation.'); }
        };
        node.append(open, el('p', {}, [card.when]), el('p', {}, [card.question]), remove);
        host.append(node);
      });
    } catch (error) { host.replaceChildren(el('p', { class: 'muted' }, [error.message])); }
  }

  function showDetail(node, context) {
    node.querySelector('.history-detail')?.remove();
    const detail = el('div', { class: 'history-detail' });
    const turns = (context.answer && context.answer.history) || [];
    (turns.length ? turns : [{ question: context.question, answer: context.answer && context.answer.text }]).forEach((turn) => {
      detail.append(el('strong', {}, [turn.question || 'Question']), el('p', {}, [turn.answer || 'No saved answer.']));
    });
    node.append(detail);
  }

  async function clearHistory() {
    if (!window.confirm('Delete all saved Ask conversations on this device?')) return;
    try {
      const r = await fetch(Spatial.server() + '/api/contexts', { method: 'DELETE', headers: await Spatial.headers() });
      if (!r.ok) throw new Error('server error ' + r.status);
      activity('Ask history cleared');
      refreshHistory();
    } catch (error) { addNotice('Could not clear Ask history: ' + error.message); }
  }

  async function loadSettings() {
    $('saved').textContent = '';
    $('server').value = Spatial.server();
    $('apiToken').value = Spatial.load('spatial.apiToken', '');
    $('research').checked = Spatial.load('spatial.research', '1') === '1';
    $('systemOne').checked = Spatial.load('spatial.systemOne', '1') === '1';
    $('dictatePolish').checked = Spatial.load('spatial.dictatePolish', '0') === '1';
    $('dictionary').value = Spatial.load('spatial.dictionary', '');
    $('autostart').checked = await T.autostart.isEnabled().catch(() => false);
    renderNotices();
  }

  async function saveSettings() {
    Spatial.save('spatial.server', $('server').value.trim());
    Spatial.save('spatial.apiToken', $('apiToken').value.trim());
    Spatial.save('spatial.research', $('research').checked ? '1' : '0');
    Spatial.save('spatial.systemOne', $('systemOne').checked ? '1' : '0');
    Spatial.save('spatial.dictatePolish', $('dictatePolish').checked ? '1' : '0');
    Spatial.save('spatial.dictionary', $('dictionary').value.slice(0, 4000));
    try {
      if ($('autostart').checked) await T.autostart.enable(); else await T.autostart.disable();
      $('saved').textContent = 'Saved.';
    } catch (err) { addNotice('Could not update autostart: ' + err.message); $('saved').textContent = 'Saved, except autostart.'; }
  }

  Spatial.save('spatial.snoozed', '0');
  activity('App started');
  document.querySelectorAll('#nav button').forEach((b) => { b.onclick = () => show(b.dataset.view); });
  $('refreshStatus').onclick = refreshStatus;
  $('clearActivity').onclick = () => { Spatial.save(D.ACTIVITY_KEY, '[]'); renderActivity(); };
  $('copyDiagnostics').onclick = async () => {
    const lines = ['Spatial diagnostics', ...D.statusCards(health, snoozed()).map(([t, v]) => t + ': ' + v),
      'Recent event categories: ' + D.readActivity(Spatial).map((e) => e.kind).join(', ')];
    try { await navigator.clipboard.writeText(lines.join('\n')); $('copyDiagnostics').textContent = 'Copied'; }
    catch (_) { addNotice('Could not copy diagnostics.'); }
  };
  $('refreshHistory').onclick = refreshHistory;
  $('clearHistory').onclick = clearHistory;
  $('saveSettings').onclick = saveSettings;
  $('copyPairingToken').onclick = async () => {
    try {
      await navigator.clipboard.writeText(await T.core.invoke('pairing_token'));
      $('copyPairingToken').textContent = 'Copied — paste into the extension API token field';
    } catch (err) { addNotice('Could not copy pairing token: ' + err.message); }
  };
  window.addEventListener('storage', () => { if (view === 'home') renderActivity(); });

  T.event.listen('spatial://open', (event) => reveal((event.payload || {}).view));
  T.event.listen('spatial://notice', (event) => { addNotice((event.payload || {}).message); });
  T.event.listen('spatial://snooze', () => { Spatial.save('spatial.snoozed', '1'); activity('Ask shortcut snoozed'); if (view === 'home') refreshStatus(); });
  T.core.invoke('startup_notice').then((notice) => { if (notice) addNotice(notice); }).catch(() => {});
  renderNotices();
  show('home');
})();
```

- [ ] **Step 5: Verify statically**

Run: `cd desktop && node --check ui/dashboard.js && node --test tests/*.cjs` — Expected: syntax OK, tests pass.
Run: `cd desktop/src-tauri && cargo check` — Expected: builds (config/capability JSON valid; a bad capability fails here).

- [ ] **Step 6: Commit**
```bash
git add desktop/ui/dashboard.* desktop/src-tauri/tauri.conf.json desktop/src-tauri/capabilities/default.json
git commit -m "feat(desktop): dashboard window with Home, Ask logs, Dictation logs, Settings"
```

---

### Task 4: Rust wiring — open dashboard, route notices, autostart arg

**Files:**
- Modify: `desktop/src-tauri/src/main.rs`

**Interfaces:**
- Consumes: window `dashboard`, events `spatial://open` / `spatial://notice` / `spatial://snooze` (Task 3).
- Produces: `fn show_dashboard(app: &tauri::AppHandle, view: &str)`, `fn notify(app: &tauri::AppHandle, message: String)` (stores `STARTUP_NOTICE` and emits to `dashboard`).

- [ ] **Step 1: Add helpers** (above `fn start_ask`):

```rust
fn show_dashboard(app: &tauri::AppHandle, view: &str) {
    if let Some(dashboard) = app.get_webview_window("dashboard") {
        let _ = dashboard.show();
        let _ = dashboard.unminimize();
        let _ = dashboard.set_focus();
    }
    let _ = app.emit_to("dashboard", "spatial://open", serde_json::json!({ "view": view }));
}

/// App-level problems (server start, hotkey ownership, autostart) belong in Settings, never in the Ask panel.
fn notify(app: &tauri::AppHandle, message: String) {
    if let Ok(mut current) = STARTUP_NOTICE.lock() { *current = Some(message.clone()); }
    let _ = app.emit_to("dashboard", "spatial://notice", serde_json::json!({ "message": message }));
}
```

- [ ] **Step 2: Replace panel-targeted notices.** In `main()`:
  - single-instance closure: replace the `panel` show/unminimize/focus block with `show_dashboard(app, "home");`
  - autostart plugin: `tauri_plugin_autostart::init(tauri_plugin_autostart::MacosLauncher::LaunchAgent, Some(vec!["--autostart"]))`
  - `start_server` failure in `setup`: replace the `STARTUP_NOTICE`/`emit_to("panel", …)` lines with `notify(app.handle(), format!("Server: {err}"));`
  - both shortcut-registration failures: replace the `STARTUP_NOTICE` assignment and `emit_to("panel", …)` with `notify(app.handle(), notice);` (keep the `eprintln!`).
  - tray `"open"`: `=> show_dashboard(app, "home"),`
  - tray `"settings"`: `=> show_dashboard(app, "settings"),`
  - tray `"snooze"`: emit to `"dashboard"` instead of `"panel"` (`let _ = app.emit_to("dashboard", "spatial://snooze", ());`)
  - tray `"server"` failure: `notify(app, format!("Server: {err}")); show_dashboard(app, "settings");`

- [ ] **Step 3: Launch behaviour.** At the end of `setup`, before `Ok(())`:

```rust
            // A normal launch opens the dashboard; sign-in autostart stays in the tray.
            if !std::env::args().any(|arg| arg == "--autostart") {
                show_dashboard(app.handle(), "home");
            }
```

- [ ] **Step 4: Verify**

Run (PowerShell): `$env:Path += ";$env:USERPROFILE\.cargo\bin"; cd desktop\src-tauri; cargo check`
Expected: no errors or new warnings.
Grep check: `Grep 'emit_to\("panel", "spatial://(error|settings|home|snooze)"' desktop/src-tauri/src/main.rs` → no matches.

- [ ] **Step 5: Commit**
```bash
git add desktop/src-tauri/src/main.rs
git commit -m "feat(desktop): open dashboard on launch/tray, route app notices to Settings"
```

---

### Task 5: Strip the Ask panel

**Files:**
- Modify: `desktop/ui/panel.html`, `desktop/ui/panel.js`

**Interfaces:**
- Consumes: `SpatialDashboard.recordActivity(Spatial, kind)` (Task 2) — load `dashboard-model.js` in `panel.html`.
- Produces: panel with only header (title + close), thread, composer. `spatial://error` still shows per-question errors.

- [ ] **Step 1: `panel.html`**
  - Delete the CSS blocks from `.home {` through `body.show-settings .settings { display: block; }` (lines 60–85) and the `.settings`-related `form button, .settings button` selector → `form button`.
  - Delete `<button id="homeButton">` and `<button id="gear">` from the header.
  - Delete `<section class="home" id="home">…</section>` and `<section class="settings" id="settings">…</section>`.
  - Add `<script src="dashboard-model.js"></script>` after `shared.js`.

- [ ] **Step 2: `panel.js`** — delete: `ACTIVITY_KEY`, `MAX_ACTIVITY`, `statusTimer`, `serverWasReady`, `lastHealth`, `renderActivity`, `refreshStatus`, `openHome`, `showDashboardView`, `refreshHistory`, `showHistoryDetail`, `clearHistory`, `openSettings`, `closeSettings`, the `saveSettings`/`copyPairingToken` handlers, the `spatial://settings|home|snooze` listeners, the `homeButton|gear|refreshStatus|overviewTab|historyTab|refreshHistory|clearActivity|clearHistory|copyDiagnostics` handlers, `Spatial.save('spatial.snoozed','0')`, and the `startup_notice` invoke line. Replace `recordActivity` with:

```js
  function recordActivity(kind) { SpatialDashboard.recordActivity(Spatial, kind); }
```
  Remove every reference to `statusTimer`, `show-home`, `show-settings`, `closeSettings()` (in `hidePanel`, `onMark`, `onDictationState`, `showDictationResult`; `onMark` keeps everything else). `showError` keeps `recordActivity('An operation needs attention')`.

- [ ] **Step 3: Verify**

Run: `cd desktop && node --check ui/panel.js && node --test tests/*.cjs`
Grep: `Grep 'show-home|show-settings|statusTimer|openSettings|refreshHistory|lastHealth' desktop/ui/panel.js desktop/ui/panel.html` → no matches.
Run: `cd desktop/src-tauri && cargo check`.

- [ ] **Step 4: Commit**
```bash
git add desktop/ui/panel.html desktop/ui/panel.js
git commit -m "refactor(desktop): Ask panel no longer hosts status, history or settings"
```

---

### Task 6: Build, E2E, docs

**Files:**
- Modify: `desktop/tests/bundled_server_smoke.py` (history-clear round trip), `docs/TASKS.md`, `docs/ARCHITECTURE.md`, `docs/DESIGN.md`, `docs/MEMORY.md`, `docs/AGENTS.md` (layout lines)

- [ ] **Step 1: Extend the packaged smoke test** — after the STT block in `bundled_server_smoke.py`, add an authenticated `DELETE /api/contexts` and assert `200` and `{"deleted": 0}` on the fresh temp profile, then `GET /api/contexts` returns `[]`. Print `history clear OK` in the final summary line.

- [ ] **Step 2: Full automated run**

```powershell
cd D:\PROJECTS\Spatial\server; python -m pytest -q
cd ..\extension; node --test tests/geometry.test.mjs
cd ..\desktop; node --test tests/*.cjs
cd ..; python scripts/eval.py cases
$env:Path += ";$env:USERPROFILE\.cargo\bin"; powershell -File desktop/build-release.ps1
python desktop/tests/bundled_server_smoke.py
```
Expected: pytest all pass; geometry 6/6; node tests all pass; eval top-1 92% (unchanged); installer builds; smoke prints `… history clear OK`.

- [ ] **Step 3: Native E2E (release exe, isolated from any installed copy)**
  1. Run `desktop/src-tauri/target/release/spatial-desktop.exe`. Expected: a window titled "Spatial" appears with Home, status cards populated.
  2. Click Settings → toggle a checkbox → Save → "Saved." Re-open: value persisted.
  3. Ask logs → Delete one / Clear all → list empties.
  4. Launch a second copy → existing dashboard is focused, no second process (single-instance).
  5. Launch with `--autostart` (after closing the first) → no window appears; tray icon present.
  6. Occupy `Alt+Shift+S` with another app, launch → Settings shows the shortcut notice with badge `!`; Ask panel shows no error.
  7. `Alt+Shift+S` mark → Ask panel header shows only title and ✕ (no Status/⚙).
  8. Close processes by exact test-exe path only; never stop a user's installed copy.

- [ ] **Step 4: Docs** — `TASKS.md`: add sub-project 7 row and phase A `[x]`, B–F `[ ]`; `ARCHITECTURE.md`: `dashboard` window, notice routing, `DELETE /api/contexts`; `DESIGN.md`: dashboard/panel split; `MEMORY.md`: decision that autostart passes `--autostart` (existing registry entries need re-saving in Settings to pick it up); `AGENTS.md` layout line for `desktop/ui`.

- [ ] **Step 5: Commit**
```bash
git add -A desktop/tests docs
git commit -m "test+docs: dashboard E2E smoke, living docs for sub-project 7 phase A"
```

---

## Self-Review

- **Spec coverage (phase A):** dashboard with 4 sections → Task 3; settings moved out of panel + provider/Jev/research/speech/autostart/pairing controls → Tasks 3, 5; hotkey/server/autostart errors to Settings → Tasks 3, 4; Ask logs editable/deletable → Tasks 1, 3 (delete one / clear all; rename deferred — YAGNI until a user asks); Dictation logs → placeholder view, real entries are phase C; Home tasks/notes/reminders → phase D (Home shows status + activity now).
- **Placeholders:** none in code steps; Task 5 gives exact deletion lists because the code being removed already exists.
- **Type consistency:** `SpatialDashboard.recordActivity(storage, kind)`, `readActivity`, `statusCards(health, snoozed)`, `historyCard(context)`, events `spatial://open|notice|snooze`, `show_dashboard`, `notify` are used identically across Tasks 2–5.
- **Known risk:** existing users' autostart registry entry lacks `--autostart`; saving Settings re-registers it (noted in MEMORY).
