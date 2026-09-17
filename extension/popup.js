const CFG = window.SPATIAL_CONFIG;
const $ = id => document.getElementById(id);
const status = (text, kind) => { $('status').textContent = text; $('status').className = 'status ' + (kind || ''); };
const KEYS = ['apiBase', 'token', 'privacy', 'provider', 'voice', 'readAloud', 'research', 'powerMode', 'pdfViewer', 'blocklistExtra', 'email', 'deviceId'];

$('title').textContent = CFG.productName;
$('eyebrow').textContent = CFG.mode === 'studyos' ? 'STUDYOS' : 'SPATIAL';

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
  $('account').hidden = !CFG.features.accounts;
  $('tokenLabel').hidden = CFG.features.accounts;   // StudyOS uses sign-in tokens, not a shared secret
  $('providerLabel').hidden = !(CFG.features.providerPicker || config.powerMode);
  if (CFG.features.accounts) {
    const signedIn = Boolean(config.token);
    $('signedOut').hidden = signedIn; $('signedIn').hidden = !signedIn;
    $('who').textContent = 'Signed in as ' + (config.email || 'student') + '. Marks and answers are saved to your account.';
    $('registerLink').href = (config.apiBase || CFG.apiBase).replace(/\/$/, '') + '/';
    if (config.email) $('email').value = config.email;
  }
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  $('openPdf').hidden = !(tab && /^(https?|file):\/\/.*\.pdf($|[?#])/i.test(tab.url || ''));
  await health(config.provider || '');
}

async function health(selectedProvider) {
  const response = await chrome.runtime.sendMessage({ type: 'spatial:health', force: true });
  if (!response || !response.ok) {
    status('Cannot reach ' + $('apiBase').value + '. ' + (CFG.mode === 'studyos' ? 'Is StudyOS running?' : 'Start the server: cd server && uvicorn app.main:app --port 8787'), 'err');
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
  const quota = data.quota ? ' · ' + data.quota.remaining + ' of ' + data.quota.limit + ' asks left today' : '';
  if (data.quota && !data.quota.signed_in) $('quota').textContent = data.quota.remaining + ' of ' + data.quota.limit + ' free asks left today. Sign in to keep your history and get more.';
  status('Connected' + quota + '.\nProviders ready: ' + (ready.join(', ') || 'none (answers will only quote the marked text)') +
    '\nSpeech: browser voice by default' + (audio.stt && audio.stt.installed ? '; server whisper available in Power mode' : ''), 'ok');
}

$('start').onclick = async () => {
  const response = await chrome.runtime.sendMessage({ type: 'spatial:start-active' });
  if (response && response.ok) window.close(); else status(response && response.error ? response.error : 'Cannot mark this page. Try a normal website or a PDF.', 'err');
};
$('openPdf').onclick = async () => { await chrome.runtime.sendMessage({ type: 'spatial:open-pdf' }); window.close(); };

$('login').onclick = async () => {
  const apiBase = $('apiBase').value.trim().replace(/\/$/, '') || CFG.apiBase;
  status('Signing in…');
  try {
    const { deviceId } = await chrome.storage.local.get('deviceId');
    const response = await fetch(apiBase + CFG.paths.login, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Device-ID': deviceId || '' },
      body: JSON.stringify({ email: $('email').value.trim(), password: $('password').value }) });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error((data.detail && data.detail.message) || data.detail || 'Login failed (' + response.status + ')');
    await chrome.storage.local.set({ apiBase, token: data.access_token, email: $('email').value.trim() });
    $('password').value = '';
    await load();
  } catch (error) {
    status(error.message || String(error), 'err');
  }
};
$('signout').onclick = async () => { await chrome.storage.local.remove(['token']); await load(); };
$('dashboard').onclick = () => chrome.tabs.create({ url: ($('apiBase').value.trim().replace(/\/$/, '') || CFG.apiBase) + '/' });

$('save').onclick = async () => {
  await chrome.storage.local.set({ apiBase: $('apiBase').value.trim().replace(/\/$/, ''), token: CFG.features.accounts ? undefined : $('token').value.trim(),
    voice: $('voice').value.trim(), blocklistExtra: $('blocklistExtra').value.trim() });
  await health($('provider').value);
};
$('privacy').onchange = () => chrome.storage.local.set({ privacy: $('privacy').value });
$('provider').onchange = () => chrome.storage.local.set({ provider: $('provider').value });
$('readAloud').onchange = () => chrome.storage.local.set({ readAloud: $('readAloud').checked });
$('research').onchange = () => chrome.storage.local.set({ research: $('research').checked });
$('pdfViewer').onchange = () => chrome.storage.local.set({ pdfViewer: $('pdfViewer').checked });
$('powerMode').onchange = async () => { await chrome.storage.local.set({ powerMode: $('powerMode').checked }); $('providerLabel').hidden = !(CFG.features.providerPicker || $('powerMode').checked); };

load();
