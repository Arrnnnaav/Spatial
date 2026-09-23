const CFG = window.SPATIAL_CONFIG;
const $ = id => document.getElementById(id);
const status = (text, kind) => { $('status').textContent = text; $('status').className = 'status ' + (kind || ''); };
const KEYS = ['apiBase', 'token', 'privacy', 'provider', 'voice', 'readAloud', 'research', 'powerMode', 'pdfViewer', 'blocklistExtra', 'deviceId'];

$('title').textContent = CFG.productName;

async function load() {
  const config = await chrome.storage.local.get(KEYS);
  $('apiBase').value = config.apiBase || CFG.apiBase;
  $('token').value = config.token || '';
  $('privacy').value = config.privacy || 'crop_only';
  $('voice').value = config.voice || '';
  $('blocklistExtra').value = config.blocklistExtra || '';
  $('readAloud').checked = Boolean(config.readAloud);
  $('research').checked = config.research !== false;
  $('powerMode').checked = Boolean(config.powerMode);
  $('pdfViewer').checked = Boolean(config.pdfViewer);
  $('providerLabel').hidden = !(CFG.features.providerPicker || config.powerMode);
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  $('openPdf').hidden = !(tab && /^(https?|file):\/\/.*\.pdf($|[?#])/i.test(tab.url || ''));
  await health(config.provider || '');
}

async function health(selectedProvider) {
  const response = await chrome.runtime.sendMessage({ type: 'spatial:health', force: true });
  if (!response || !response.ok) {
    status('Cannot reach ' + $('apiBase').value + '. Start the server: cd server && uvicorn app.main:app --port 8787', 'err');
    return;
  }
  const data = response.health;
  const select = $('provider');
  select.innerHTML = '<option value="">Auto (' + (data.provider_order || []).join(' → ') + ')</option>';
  for (const item of data.providers || []) {
    const option = document.createElement('option');
    option.value = item.name; option.disabled = !item.configured;
    option.textContent = item.name + (item.configured ? ' · ' + item.model + (item.vision_model ? ' + ' + item.vision_model : ' (text + OCR)') : ' · not configured');
    select.append(option);
  }
  select.value = selectedProvider;
  const ready = (data.providers || []).filter(p => p.configured).map(p => p.name);
  const audio = data.audio || {};
  $('traceLog').checked = Boolean(data.trace && data.trace.enabled);
  status('Connected.\nProviders ready: ' + (ready.join(', ') || 'none (answers will only quote the marked text)') +
    '\nSpeech: browser voice by default' + (audio.stt && audio.stt.installed ? '; server whisper available in Power mode' : ''), 'ok');
}

$('start').onclick = async () => {
  const response = await chrome.runtime.sendMessage({ type: 'spatial:start-active' });
  if (response && response.ok) window.close(); else status(response && response.error ? response.error : 'Cannot mark this page. Try a normal website or a PDF.', 'err');
};
$('openPdf').onclick = async () => { await chrome.runtime.sendMessage({ type: 'spatial:open-pdf' }); window.close(); };

$('save').onclick = async () => {
  await chrome.storage.local.set({ apiBase: $('apiBase').value.trim().replace(/\/$/, ''), token: $('token').value.trim(),
    voice: $('voice').value.trim(), blocklistExtra: $('blocklistExtra').value.trim() });
  await health($('provider').value);
};
$('privacy').onchange = () => chrome.storage.local.set({ privacy: $('privacy').value });
$('provider').onchange = () => chrome.storage.local.set({ provider: $('provider').value });
$('readAloud').onchange = () => chrome.storage.local.set({ readAloud: $('readAloud').checked });
$('research').onchange = () => chrome.storage.local.set({ research: $('research').checked });
$('pdfViewer').onchange = () => chrome.storage.local.set({ pdfViewer: $('pdfViewer').checked });
$('powerMode').onchange = async () => { await chrome.storage.local.set({ powerMode: $('powerMode').checked }); $('providerLabel').hidden = !(CFG.features.providerPicker || $('powerMode').checked); };
$('traceLog').onchange = async () => {
  const response = await chrome.runtime.sendMessage({ type: 'spatial:trace', enabled: $('traceLog').checked });
  if (!response || !response.ok) { $('traceLog').checked = !$('traceLog').checked; status((response && response.error) || 'Could not change the trace log', 'err'); }
  else status('Trace log ' + (response.trace.enabled ? 'on: ' + response.trace.dir : 'off') + '.', 'ok');
};

load();
