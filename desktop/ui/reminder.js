/* Reminder popup. This window stays loaded (hidden) while the app is in the tray, so it owns the due-reminder poll and
   shows itself in the screen corner without stealing focus. Reminders missed while the app was closed fire on the next poll. */
(function () {
  'use strict';
  if (typeof window === 'undefined' || !window.__TAURI__) return;
  const T = window.__TAURI__;
  const win = T.window.getCurrentWindow();
  const list = document.getElementById('list');
  const POLL_MS = 15000;
  const SNOOZE_MS = 10 * 60000;
  const items = [];
  let busy = false;

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => { if (k === 'class') node.className = v; else node.setAttribute(k, v); });
    (children || []).forEach((c) => node.append(c));
    return node;
  }

  async function api(path, method, body) {
    const headers = await Spatial.headers();
    const response = await fetch(Spatial.server() + path, { method: method || 'GET', headers, body: body ? JSON.stringify(body) : undefined });
    if (!response.ok) throw new Error('server error ' + response.status);
    return response.json();
  }

  async function showCorner() {
    const scale = await win.scaleFactor();
    const size = await win.outerSize();
    await win.setPosition(new T.dpi.PhysicalPosition(
      Math.max(0, Math.round(screen.availWidth * scale - size.width - 16 * scale)),
      Math.max(0, Math.round(screen.availHeight * scale - size.height - 16 * scale)),
    ));
    await win.show(); // window is non-focusable: whatever the user is typing into keeps focus
  }

  function remove(id) {
    const index = items.findIndex((item) => item.id === id);
    if (index >= 0) items.splice(index, 1);
    render();
    if (!items.length) win.hide();
  }

  function render() {
    list.replaceChildren(...items.map((item) => {
      const dismiss = el('button', { type: 'button', class: 'primary' }, ['Dismiss']);
      dismiss.onclick = () => remove(item.id);
      const snooze = el('button', { type: 'button' }, ['Snooze 10 min']);
      snooze.onclick = async () => {
        snooze.disabled = true;
        try { await api('/api/reminders', 'POST', { text: item.text, due_at: new Date(Date.now() + SNOOZE_MS).toISOString() }); remove(item.id); }
        catch (_) { snooze.disabled = false; snooze.textContent = 'Could not snooze'; }
      };
      return el('div', { class: 'item' }, [el('div', { class: 'text' }, [item.text]), el('div', { class: 'row' }, [dismiss, snooze])]);
    }));
  }

  async function poll() {
    if (busy) return;
    busy = true;
    try {
      const due = await api('/api/reminders/due');
      const fresh = due.filter((reminder) => !items.some((item) => item.id === reminder.id));
      if (fresh.length) {
        items.push(...fresh);
        render();
        await showCorner();
      }
      for (const reminder of due) await api('/api/reminders/' + encodeURIComponent(reminder.id) + '/fired', 'POST');
    } catch (_) { /* server may still be starting; try again on the next tick */ }
    finally { busy = false; }
  }

  setTimeout(poll, 4000);
  setInterval(poll, POLL_MS);
})();
