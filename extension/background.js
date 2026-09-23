/* Service worker: hotkey → inject the overlay; capture + crop the marked region; talk to the server.
   The page never sees the token or device id; only this worker holds them. */
importScripts('config.js');

const CFG = self.SPATIAL_CONFIG;
const VERSION = chrome.runtime.getManifest().version;
const CONSENT_VERSION = 1;
const DEFAULTS = {
  apiBase: CFG.apiBase, token: '', deviceId: '', consentVersion: 0, privacy: 'crop_only', provider: '', voice: '',
  readAloud: false, powerMode: false, pdfViewer: false, blocklistExtra: '', research: true, level: 'student',
};
/* Sites where the overlay never runs: money, health portals, government, browser internals. */
const BLOCKLIST = [/(^|\.)(paypal|stripe|coinbase|binance|robinhood|chase|wellsfargo|bankofamerica|citi|hdfcbank|icicibank|sbi)\.(com|co\.in|in)$/i,
                   /\.gov(\.[a-z]{2})?$/i, /(^|\.)(mychart|patientportal)\./i];
const PDF_URL = /^(https?|file):\/\/.*\.pdf($|[?#])/i;
const sessionState = { health: null, healthAt: 0 };

async function settings() {
  return { ...DEFAULTS, ...(await chrome.storage.local.get(Object.keys(DEFAULTS))) };
}

async function ensureDeviceId() {
  const { deviceId } = await chrome.storage.local.get('deviceId');
  if (deviceId) return deviceId;
  const fresh = crypto.randomUUID();
  await chrome.storage.local.set({ deviceId: fresh });
  return fresh;
}

chrome.runtime.onInstalled.addListener(async () => {
  await ensureDeviceId();
  chrome.contextMenus.create({ id: 'open-pdf-viewer', title: 'Open PDF in ' + CFG.productName + ' viewer', contexts: ['link', 'page'],
    targetUrlPatterns: ['*://*/*.pdf*', 'file:///*.pdf*'], documentUrlPatterns: ['*://*/*', 'file:///*'] });
});

chrome.contextMenus.onClicked.addListener((info, tab) => {
  if (info.menuItemId !== 'open-pdf-viewer') return;
  const url = info.linkUrl || info.pageUrl;
  if (url) chrome.tabs.create({ url: viewerUrl(url), index: tab ? tab.index + 1 : undefined });
});

function viewerUrl(pdfUrl) {
  return chrome.runtime.getURL('viewer.html?file=' + encodeURIComponent(pdfUrl));
}

function blocked(url, extra) {
  try {
    const u = new URL(url);
    if (!/^(https?|file):$/.test(u.protocol)) return 'browser page';
    if (BLOCKLIST.some(rx => rx.test(u.hostname))) return 'sensitive site';
    const custom = (extra || '').split(/[\s,]+/).filter(Boolean);
    if (custom.some(host => u.hostname === host || u.hostname.endsWith('.' + host))) return 'your blocklist';
  } catch (_) { return 'unsupported page'; }
  return null;
}

async function toggleOverlay(tab) {
  if (!tab || tab.id == null) return { ok: false, error: 'no active tab' };
  const config = await settings();
  if (tab.url && tab.url.startsWith(chrome.runtime.getURL('viewer.html'))) {
    await chrome.tabs.sendMessage(tab.id, { type: 'spatial:toggle', consent: config.consentVersion >= CONSENT_VERSION });
    return { ok: true };
  }
  const reason = blocked(tab.url || '', config.blocklistExtra);
  if (reason) return { ok: false, code: 'BLOCKED', error: 'Point & Ask stays off here (' + reason + ').' };
  const [{ result: alreadyLoaded } = {}] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: () => Boolean(window.__spatialSpatialLoaded) });
  if (!alreadyLoaded) {
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ['config.js', 'geometry.js', 'content.js'] });
  }
  await chrome.tabs.sendMessage(tab.id, { type: 'spatial:toggle', consent: config.consentVersion >= CONSENT_VERSION });
  return { ok: true };
}

chrome.commands.onCommand.addListener(async (command, tab) => {
  if (command === 'toggle-spatial') toggleOverlay(tab || (await chrome.tabs.query({ active: true, currentWindow: true }))[0]);
});

chrome.action.onClicked.addListener(tab => toggleOverlay(tab));

/* Opt-in only: hijacking every PDF is invasive, so the redirect runs when the user turned it on in the popup.
   Otherwise PDFs open via the context menu or the popup's "Open this PDF" button. */
chrome.webNavigation.onBeforeNavigate.addListener(async details => {
  if (details.frameId !== 0 || !PDF_URL.test(details.url)) return;
  const { pdfViewer } = await chrome.storage.local.get('pdfViewer');
  if (pdfViewer) chrome.tabs.update(details.tabId, { url: viewerUrl(details.url) });
});

/* Crop the visible tab to the marked box (CSS px, viewport coordinates). Keeps the drawn stroke in the
   image on purpose: the model sees exactly what the student circled. */
async function captureCrop(windowId, box, dpr, mode) {
  const dataUrl = await chrome.tabs.captureVisibleTab(windowId, { format: 'png' });
  const blob = await (await fetch(dataUrl)).blob();
  const bitmap = await createImageBitmap(blob);
  if (mode === 'full_frame') return { image: dataUrl, crop: { bbox: { x: 0, y: 0, width: bitmap.width / dpr, height: bitmap.height / dpr }, scale: dpr } };
  const pad = 28 * dpr;
  const sx = Math.max(0, Math.floor(box.x * dpr - pad)), sy = Math.max(0, Math.floor(box.y * dpr - pad));
  const sw = Math.min(bitmap.width - sx, Math.ceil(box.width * dpr + pad * 2)), sh = Math.min(bitmap.height - sy, Math.ceil(box.height * dpr + pad * 2));
  if (sw <= 0 || sh <= 0) return { image: null, crop: null };
  const scale = Math.min(1, 1600 / Math.max(sw, sh));
  const canvas = new OffscreenCanvas(Math.round(sw * scale), Math.round(sh * scale));
  canvas.getContext('2d').drawImage(bitmap, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
  const out = await canvas.convertToBlob({ type: 'image/jpeg', quality: 0.86 });
  const image = await new Promise(resolve => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.readAsDataURL(out); });
  // Crop geometry in CSS px of the viewport; scale = image px per CSS px (lets the server place OCR boxes).
  return { image, crop: { bbox: { x: sx / dpr, y: sy / dpr, width: sw / dpr, height: sh / dpr }, scale: scale * dpr } };
}

/* HTTP ------------------------------------------------------------------ */
async function headers(config, json = true) {
  const h = { 'X-Device-ID': await ensureDeviceId(), 'X-Client-Version': VERSION, 'X-Consent-Version': String(config.consentVersion || 0) };
  if (json) h['Content-Type'] = 'application/json';
  if (config.token) h.Authorization = 'Bearer ' + config.token;
  return h;
}

function apiUrl(config, key, params) {
  let path = CFG.paths[key];
  for (const [name, value] of Object.entries(params || {})) path = path.replace('{' + name + '}', encodeURIComponent(value));
  return config.apiBase.replace(/\/$/, '') + path;
}

/* Turn an HTTP failure into {code, message} the panel can act on. */
async function failure(response) {
  const data = await response.json().catch(() => ({}));
  const detail = data.detail;
  if (detail && typeof detail === 'object' && detail.code) return detail;
  const message = typeof detail === 'string' ? detail : (data.message || 'request failed (' + response.status + ')');
  const code = { 401: 'AUTH_REQUIRED', 402: 'COST_CAP', 426: 'CLIENT_OUTDATED', 429: 'RATE_LIMITED' }[response.status] || 'HTTP_' + response.status;
  return { code, message };
}

function askBody(payload, config) {
  return { ...payload, privacy_policy: config.privacy, provider: config.powerMode ? (config.provider || null) : null,
           protocol_version: CFG.protocolVersion, client_version: VERSION };
}

/* Streaming ask: forwards `delta` events to the tab as they arrive, resolves with the final document. */
async function askStream(payload, tabId, requestId) {
  const config = await settings();
  const response = await fetch(apiUrl(config, 'stream'), { method: 'POST', headers: await headers(config), body: JSON.stringify(askBody(payload, config)) });
  if (!response.ok) throw await failure(response);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '', complete = null;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split('\n\n'); buffer = blocks.pop();
    for (const block of blocks) {
      const match = block.match(/^event: (.+)\ndata: (.+)$/s);
      if (!match) continue;
      const data = JSON.parse(match[2]);
      if (match[1] === 'delta') chrome.tabs.sendMessage(tabId, { type: 'spatial:delta', requestId, text: data.text }).catch(() => {});
      else if (match[1] === 'status') chrome.tabs.sendMessage(tabId, { type: 'spatial:status', requestId, ...data }).catch(() => {});
      else if (match[1] === 'error') throw data;
      else if (match[1] === 'complete') complete = data;
    }
  }
  if (!complete) throw { code: 'STREAM_ENDED', message: 'server closed the stream without an answer' };
  return complete;
}

async function health(force) {
  if (!force && sessionState.health && Date.now() - sessionState.healthAt < 60_000) return sessionState.health;
  const config = await settings();
  const response = await fetch(apiUrl(config, 'health'), { headers: await headers(config, false) });
  if (!response.ok) throw await failure(response);
  sessionState.health = await response.json(); sessionState.healthAt = Date.now();
  return sessionState.health;
}

/* Server speech (Power mode / self-host). Browser Web Speech + speechSynthesis are the defaults in content.js. */
async function speak(text) {
  const config = await settings();
  const response = await fetch(apiUrl(config, 'synthesize'), { method: 'POST', headers: await headers(config), body: JSON.stringify({ text, voice: config.voice || null }) });
  if (!response.ok) throw await failure(response);
  const blob = await response.blob();
  return new Promise(resolve => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.readAsDataURL(blob); });
}

async function transcribe(audioDataUrl, mimeType) {
  const config = await settings();
  const blob = await (await fetch(audioDataUrl)).blob();
  const form = new FormData();
  form.append('audio', blob, 'question.' + (mimeType.includes('ogg') ? 'ogg' : 'webm'));
  const response = await fetch(apiUrl(config, 'transcribe'), { method: 'POST', headers: await headers(config, false), body: form });
  if (!response.ok) throw await failure(response);
  return (await response.json()).text || '';
}

/* Offscreen recorder: one microphone grant for the extension origin instead of one per website. */
async function ensureOffscreen() {
  if (await chrome.offscreen.hasDocument()) return;
  await chrome.offscreen.createDocument({ url: 'offscreen.html', reasons: ['USER_MEDIA'], justification: 'Record the spoken question for transcription' });
}

async function recordViaOffscreen(action) {
  await ensureOffscreen();
  const response = await chrome.runtime.sendMessage({ type: 'offscreen:' + action });
  if (response && response.code === 'MIC_PERMISSION') chrome.tabs.create({ url: chrome.runtime.getURL('permission.html') });
  return response || { ok: false, error: 'recorder did not answer' };
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message || !message.type || message.type.startsWith('offscreen:')) return false; // offscreen.js answers those
  (async () => {
    try {
      const config = await settings();
      switch (message.type) {
        case 'spatial:capture': {
          if (config.privacy === 'anchors_only') return sendResponse({ ok: true, image: null, crop: null });
          const { image, crop } = await captureCrop(sender.tab.windowId, message.box, message.dpr || 1, config.privacy);
          return sendResponse({ ok: true, image, crop });
        }
        case 'spatial:ask-stream': return sendResponse({ ok: true, result: await askStream(message.payload, sender.tab.id, message.requestId) });
        case 'spatial:consent': {
          await chrome.storage.local.set({ consentVersion: CONSENT_VERSION, privacy: message.privacy || 'crop_only' });
          return sendResponse({ ok: true });
        }
        case 'spatial:set': { const { type, ...patch } = message; await chrome.storage.local.set(patch); return sendResponse({ ok: true }); }
        case 'spatial:settings': return sendResponse({ ok: true, settings: { ...config, token: undefined, hasToken: Boolean(config.token) }, config: CFG, version: VERSION });
        case 'spatial:health': return sendResponse({ ok: true, health: await health(message.force) });
        case 'spatial:speak': return sendResponse({ ok: true, audio: await speak(message.text) });
        case 'spatial:transcribe': return sendResponse({ ok: true, text: await transcribe(message.audio, message.mimeType || 'audio/webm') });
        case 'spatial:record': return sendResponse(await recordViaOffscreen(message.action));
        case 'spatial:start-active': {
          const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
          return sendResponse(await toggleOverlay(tab));
        }
        case 'spatial:open-pdf': {
          const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
          if (!tab || !PDF_URL.test(tab.url || '')) return sendResponse({ ok: false, error: 'current tab is not a PDF' });
          await chrome.tabs.update(tab.id, { url: viewerUrl(tab.url) });
          return sendResponse({ ok: true });
        }
        default: return sendResponse({ ok: false, error: 'unknown message' });
      }
    } catch (error) {
      const detail = error && error.code ? error : { code: 'ERROR', message: error && error.message ? error.message : String(error) };
      sendResponse({ ok: false, code: detail.code, error: detail.message });
    }
  })();
  return true;
});
