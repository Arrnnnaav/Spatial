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

  const shortcutIssues = () => ({ ask: notices.some((n) => /^Shortcut /.test(n)), dictate: notices.some((n) => /^Dictate shortcut /.test(n)) });
  const snoozed = () => Spatial.load('spatial.snoozed', '0') === '1';
  const activity = (kind) => { D.recordActivity(Spatial, kind); if (view === 'home') renderActivity(); };

  function addNotice(message) {
    if (!message || notices.includes(message)) return;
    notices.push(message);
    activity('An operation needs attention');
    renderNotices();
    if (view === 'home') refreshStatus();
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
    $('statusCards').replaceChildren(...D.statusCards(health, snoozed(), shortcutIssues()).map(([title, value]) =>
      el('div', { class: 'status-card' }, [el('small', {}, [title]), el('strong', {}, [value])])));
    renderActivity();
  }

  async function show(next) {
    view = VIEWS.includes(next) ? next : 'home';
    VIEWS.forEach((name) => { $('view-' + name).hidden = name !== view; });
    document.querySelectorAll('#nav button').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.view === view)));
    if (timer) { clearInterval(timer); timer = null; }
    if (view === 'home') { refreshTasks(); refreshReminders(); await refreshStatus(); timer = setInterval(refreshStatus, 10000); }
    if (view === 'ask') refreshHistory();
    if (view === 'dictation') refreshDictations();
    if (view === 'settings') await loadSettings();
  }

  async function reveal(next) {
    await show(next);
    await win.show(); await win.unminimize(); await win.setFocus();
  }

  async function api(path, method, body) {
    const response = await fetch(Spatial.server() + path, {
      method: method || 'GET', headers: await Spatial.headers(), body: body ? JSON.stringify(body) : undefined });
    if (!response.ok) throw new Error('server error ' + response.status);
    return response.json();
  }

  async function refreshTasks() {
    const host = $('taskList');
    try {
      const tasks = await api('/api/tasks');
      host.replaceChildren(...(tasks.length ? tasks.map((raw) => {
        const task = D.taskCard(raw);
        const box = el('input', { type: 'checkbox', 'aria-label': 'Done' });
        box.checked = task.done;
        box.onchange = async () => { try { await api('/api/tasks/' + encodeURIComponent(task.id), 'PATCH', { done: box.checked }); refreshTasks(); } catch (_) { addNotice('Could not update the task.'); } };
        const remove = el('button', { type: 'button', class: 'danger', title: 'Delete task' }, ['Delete']);
        remove.onclick = async () => { try { await api('/api/tasks/' + encodeURIComponent(task.id), 'DELETE'); refreshTasks(); } catch (_) { addNotice('Could not delete the task.'); } };
        const text = el('div', { class: 'grow' }, [task.text]);
        if (task.note) text.append(el('div', { class: 'muted' }, [task.note]));
        return el('div', { class: 'row-item' + (task.done ? ' done' : '') }, [box, text, remove]);
      }) : [el('p', { class: 'muted' }, ['No tasks yet.'])]));
    } catch (_) { host.replaceChildren(el('p', { class: 'muted' }, ['Tasks need the server to be running.'])); }
  }

  async function refreshReminders() {
    const host = $('reminderList');
    try {
      const reminders = await api('/api/reminders');
      host.replaceChildren(...(reminders.length ? reminders.map((raw) => {
        const card = D.reminderCard(raw);
        const remove = el('button', { type: 'button', class: 'danger', title: 'Delete reminder' }, ['Delete']);
        remove.onclick = async () => { try { await api('/api/reminders/' + encodeURIComponent(card.id), 'DELETE'); refreshReminders(); } catch (_) { addNotice('Could not delete the reminder.'); } };
        return el('div', { class: 'row-item' }, [el('div', { class: 'grow' }, [card.text, el('div', { class: 'muted' }, [card.when])]),
          el('span', { class: 'state ' + card.state }, [card.state]), remove]);
      }) : [el('p', { class: 'muted' }, ['No reminders.'])]));
    } catch (_) { host.replaceChildren(el('p', { class: 'muted' }, ['Reminders need the server to be running.'])); }
  }

  async function addReminder(dueIso) {
    const text = $('reminderText').value.trim();
    if (!text) { $('reminderText').focus(); return; }
    if (!dueIso) { $('reminderWhen').focus(); return; }
    try {
      await api('/api/reminders', 'POST', { text, due_at: dueIso });
      $('reminderText').value = '';
      $('reminderWhen').value = '';
      activity('Reminder added');
      refreshReminders();
    } catch (_) { addNotice('Could not add the reminder.'); }
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

  async function refreshDictations() {
    const host = $('dictationList');
    host.replaceChildren(el('p', { class: 'muted' }, ['Loading dictations…']));
    try {
      const response = await fetch(Spatial.server() + '/api/dictations?limit=100', { headers: await Spatial.headers() });
      if (!response.ok) throw new Error('Dictations could not be loaded.');
      const entries = await response.json();
      host.replaceChildren();
      if (!entries.length) { host.append(el('p', { class: 'muted' }, ['No saved dictations yet. Press Alt+Shift+D in any text field.'])); return; }
      entries.forEach((entry) => {
        const card = D.dictationCard(entry);
        const node = el('article', { class: 'history-card' });
        const open = el('button', { type: 'button', class: 'title' }, [card.title]);
        open.onclick = () => showDictation(node, entry);
        node.append(open, el('p', {}, [card.when + (card.source ? ' · ' + card.source : '')]), el('p', {}, [card.summary]));
        if (card.providers) node.append(el('p', {}, [card.providers]));
        host.append(node);
      });
    } catch (error) { host.replaceChildren(el('p', { class: 'muted' }, [error.message])); }
  }

  function showDictation(node, entry) {
    const existing = node.querySelector('.history-detail');
    if (existing) { existing.remove(); return; }
    const detail = el('div', { class: 'history-detail' });
    const title = el('input', { type: 'text', maxlength: '120', 'aria-label': 'Title' });
    title.value = entry.title;
    const text = el('textarea', { rows: '8', maxlength: '12000', 'aria-label': 'Transcript' });
    text.value = entry.text;
    const status = el('span', { class: 'muted', role: 'status' });
    const save = el('button', { type: 'button' }, ['Save changes']);
    save.onclick = async () => {
      try {
        const r = await fetch(Spatial.server() + '/api/dictations/' + encodeURIComponent(entry.id), {
          method: 'PATCH', headers: await Spatial.headers(), body: JSON.stringify({ title: title.value.trim() || entry.title, text: text.value.trim() || entry.text }) });
        if (!r.ok) throw new Error('save failed');
        status.textContent = 'Saved.';
      } catch (_) { addNotice('Could not save the dictation.'); }
    };
    const docx = el('button', { type: 'button' }, ['Download .docx']);
    docx.onclick = async () => {
      try {
        const r = await Spatial.send('/api/dictate/docx', JSON.stringify({ text: text.value.trim() || entry.text }), 'application/json');
        const url = URL.createObjectURL(await r.blob());
        const link = document.createElement('a');
        link.href = url; link.download = 'spatial-dictation-' + entry.created_at.slice(0, 10) + '.docx'; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } catch (_) { addNotice('Could not create the Word document.'); }
    };
    const remove = el('button', { type: 'button', class: 'danger' }, ['Delete']);
    remove.onclick = async () => {
      try {
        const r = await fetch(Spatial.server() + '/api/dictations/' + encodeURIComponent(entry.id), { method: 'DELETE', headers: await Spatial.headers() });
        if (!r.ok) throw new Error('delete failed');
        refreshDictations();
      } catch (_) { addNotice('Could not delete the dictation.'); }
    };
    detail.append(title, text, el('div', { class: 'actions' }, [save, docx, remove, status]));
    node.append(detail);
  }

  async function clearDictations() {
    if (!window.confirm('Delete all saved dictations on this device?')) return;
    try {
      const r = await fetch(Spatial.server() + '/api/dictations', { method: 'DELETE', headers: await Spatial.headers() });
      if (!r.ok) throw new Error('server error ' + r.status);
      activity('Dictation log cleared');
      refreshDictations();
    } catch (error) { addNotice('Could not clear dictations: ' + error.message); }
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
    const lines = ['Spatial diagnostics', ...D.statusCards(health, snoozed(), shortcutIssues()).map(([t, v]) => t + ': ' + v),
      'Recent event categories: ' + D.readActivity(Spatial).map((e) => e.kind).join(', ')];
    try { await navigator.clipboard.writeText(lines.join('\n')); $('copyDiagnostics').textContent = 'Copied'; }
    catch (_) { addNotice('Could not copy diagnostics.'); }
  };
  $('taskForm').onsubmit = async (event) => {
    event.preventDefault();
    const text = $('taskText').value.trim();
    if (!text) return;
    try { await api('/api/tasks', 'POST', { text }); $('taskText').value = ''; refreshTasks(); } catch (_) { addNotice('Could not add the task.'); }
  };
  $('reminderForm').onsubmit = (event) => { event.preventDefault(); addReminder(D.localInputToIso($('reminderWhen').value)); };
  document.querySelectorAll('[data-quick]').forEach((b) => { b.onclick = () => addReminder(D.quickDue(b.dataset.quick)); });
  $('refreshHistory').onclick = refreshHistory;
  $('refreshDictations').onclick = refreshDictations;
  $('clearDictations').onclick = clearDictations;
  $('clearHistory').onclick = clearHistory;
  $('saveSettings').onclick = saveSettings;
  $('copyPairingToken').onclick = async () => {
    try {
      await navigator.clipboard.writeText(await T.core.invoke('pairing_token'));
      $('copyPairingToken').textContent = 'Copied — paste into the extension API token field';
    } catch (err) { addNotice('Could not copy pairing token: ' + err.message); }
  };
  window.addEventListener('storage', () => { if (view === 'home') renderActivity(); });

  T.event.listen('spatial://dictation-saved', () => { activity('Dictation saved'); if (view === 'dictation') refreshDictations(); });
  T.event.listen('spatial://open', (event) => reveal((event.payload || {}).view));
  T.event.listen('spatial://notice', (event) => { addNotice((event.payload || {}).message); });
  T.event.listen('spatial://snooze', () => { Spatial.save('spatial.snoozed', '1'); activity('Ask shortcut snoozed'); if (view === 'home') refreshStatus(); });
  T.core.invoke('startup_notice').then((list) => { (list || []).forEach(addNotice); }).catch(() => {});
  // Autostart entries made before the `--autostart` flag would pop this window at sign-in: rewrite them once.
  if (Spatial.load('spatial.autostartFlag', '0') !== '1') {
    T.autostart.isEnabled().then(async (on) => {
      if (on) { await T.autostart.disable(); await T.autostart.enable(); }
      Spatial.save('spatial.autostartFlag', '1');
    }).catch(() => {});
  }
  renderNotices();
  show('home');
})();
