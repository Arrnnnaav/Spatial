/* Shared by overlay + panel: server URL, auth headers, JSON POST. Settings live in this app's localStorage. */
(function () {
  'use strict';
  const DEFAULT_SERVER = 'http://127.0.0.1:8787';

  function load(key, fallback) {
    try { return localStorage.getItem(key) || fallback; } catch (_) { return fallback; }
  }

  function save(key, value) {
    try {
      if (value) localStorage.setItem(key, value);
      else localStorage.removeItem(key);
    } catch (_) {
      // storage unavailable: settings last for this session only
    }
  }

  function server() { return load('spatial.server', DEFAULT_SERVER).replace(/\/+$/, ''); }

  async function headers() {
    // Per-launch token the server writes to a local file; only this app can read it (never a web page).
    const token = await window.__TAURI__.core.invoke('desktop_token');
    const out = { 'Content-Type': 'application/json', 'X-Spatial-Desktop': token };
    const apiToken = load('spatial.apiToken', '') || await window.__TAURI__.core.invoke('pairing_token').catch(() => '');
    if (apiToken) out.Authorization = 'Bearer ' + apiToken;
    return out;
  }

  async function post(path, body) {
    const response = await fetch(server() + path, { method: 'POST', headers: await headers(), body: JSON.stringify(body) });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error((data.detail && data.detail.message) || 'server error ' + response.status);
    return data;
  }

  /* Multipart/binary calls (speech): same auth, but let the browser set Content-Type. */
  async function send(path, body, contentType) {
    const h = await headers();
    delete h['Content-Type'];
    if (contentType) h['Content-Type'] = contentType;
    const response = await fetch(server() + path, { method: 'POST', headers: h, body });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error((data.detail && data.detail.message) || 'server error ' + response.status);
    }
    return response;
  }

  window.Spatial = { load, save, headers, post, send, server, DEFAULT_SERVER };
})();
