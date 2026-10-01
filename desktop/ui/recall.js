/* Quick recall: Alt+Shift+H opens a keyboard-first list of Spatial's own Ask and dictation history. It only copies to the
   clipboard; it never types into another app. */
(function () {
  'use strict';
  if (typeof window === 'undefined' || !window.__TAURI__) return;
  const T = window.__TAURI__;
  const win = T.window.getCurrentWindow();
  const D = window.SpatialDashboard;
  const $ = (id) => document.getElementById(id);
  let all = [];
  let shown = [];
  let index = 0;
  let armed = false;

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => { if (k === 'class') node.className = v; else node.setAttribute(k, v); });
    (children || []).forEach((c) => node.append(c));
    return node;
  }

  async function load() {
    const headers = await Spatial.headers();
    const get = async (path) => { const r = await fetch(Spatial.server() + path, { headers }); if (!r.ok) throw new Error(path); return r.json(); };
    const [contexts, dictations] = await Promise.all([get('/api/contexts?limit=100').catch(() => []), get('/api/dictations?limit=100').catch(() => [])]);
    all = D.recallItems(contexts, dictations);
  }

  function render() {
    shown = D.filterRecall(all, $('q').value);
    index = Math.min(index, Math.max(0, shown.length - 1));
    $('list').replaceChildren(...(shown.length ? shown.map((item, i) => {
      const row = el('div', { class: 'item', role: 'option', 'aria-selected': String(i === index) }, [
        el('div', { class: 'kind' }, [item.kind === 'ask' ? '?' : '🎙']),
        el('div', { class: 'main' }, [el('div', { class: 'title' }, [item.title]), el('div', { class: 'sub' }, [item.when + (item.subtitle ? ' · ' + item.subtitle : '')])]),
      ]);
      row.onclick = () => { index = i; copy(false); };
      return row;
    }) : [el('div', { class: 'empty' }, [all.length ? 'No matches.' : 'Nothing saved yet.'])]));
    const selected = $('list').querySelector('[aria-selected="true"]');
    if (selected) selected.scrollIntoView({ block: 'nearest' });
    $('preview').textContent = shown[index] ? shown[index].text : '';
  }

  async function copy(plain) {
    const item = shown[index];
    if (!item || !item.text) return;
    try { await navigator.clipboard.writeText(plain ? D.plainText(item.text) : item.text); $('hint').textContent = 'Copied.'; }
    catch (_) { $('hint').textContent = 'Could not copy.'; return; }
    setTimeout(close, 350);
  }

  function close() { armed = false; win.hide(); }

  async function open() {
    document.body.classList.remove('preview');
    $('q').value = '';
    $('hint').textContent = '↑↓ choose · Enter copy · Shift+Enter copy as plain text · F3 preview · Esc close';
    index = 0;
    await load();
    render();
    await win.show();
    await win.setFocus();
    $('q').focus();
    setTimeout(() => { armed = true; }, 400);
  }

  $('q').addEventListener('input', () => { index = 0; render(); });
  window.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') { event.preventDefault(); close(); }
    else if (event.key === 'ArrowDown') { event.preventDefault(); index = Math.min(index + 1, shown.length - 1); render(); }
    else if (event.key === 'ArrowUp') { event.preventDefault(); index = Math.max(index - 1, 0); render(); }
    else if (event.key === 'Enter') { event.preventDefault(); copy(event.shiftKey); }
    else if (event.key === 'F3') { event.preventDefault(); document.body.classList.toggle('preview'); }
  });
  window.addEventListener('blur', () => { if (armed) close(); });
  T.event.listen('spatial://recall-open', open);
})();
