/* Ask panel: receives the mark from the overlay, fetches UIA/OCR candidates for it (overlay already hidden), places
   itself beside the mark, streams the answer from /api/ask/stream, shows sources (⚠ unsupported) and clarify chips. */
(function () {
  'use strict';
  const T = window.__TAURI__;
  const win = T.window.getCurrentWindow();
  const $ = (id) => document.getElementById(id);
  const thread = $('thread');
  const input = $('question');
  const send = $('send');
  const POINT_PAD = 40; // monitor px around a point mark to look for candidates
  const MAX_RECORD_MS = 60000; // a forgotten mic never stays open
  let stopRecording = () => {};
  let state = null; // { capture_id, monitor, mark, candidates, window, contextId }
  let ownPid = null;
  let speechWhere = ' — speech provider unknown until the server connects';
  const ACTIVITY_KEY = 'spatial.activity';
  const MAX_ACTIVITY = 40;
  let statusTimer = null;
  let serverWasReady = null;
  let dictationDraft = null;
  let activeDictationId = null;

  function recordActivity(kind) {
    const events = JSON.parse(Spatial.load(ACTIVITY_KEY, '[]'));
    events.unshift({ at: new Date().toISOString(), kind });
    Spatial.save(ACTIVITY_KEY, JSON.stringify(events.slice(0, MAX_ACTIVITY)));
    if (document.body.classList.contains('show-home')) renderActivity();
  }

  function renderActivity() {
    const list = $('activityList');
    const events = JSON.parse(Spatial.load(ACTIVITY_KEY, '[]'));
    list.replaceChildren(...events.map((item) => el('li', {}, [new Date(item.at).toLocaleString() + ' · ' + item.kind])));
    if (!events.length) list.append(el('li', {}, ['No recent activity.']));
  }

  async function refreshStatus() {
    const list = $('statusList');
    const items = ['Shortcut: Alt+Shift+S (' + (Spatial.load('spatial.snoozed', '0') === '1' ? 'snoozed' : 'enabled') + ')'];
    try {
      const response = await fetch(Spatial.server() + '/api/health', { headers: await Spatial.headers() });
      if (!response.ok) throw new Error('health check failed');
      const health = await response.json();
      items.unshift('Server: Ready');
      items.push('Dictate shortcut: Alt+Shift+D (or Dictate button)');
      items.push('Dictation polish: ' + (Spatial.load('spatial.dictatePolish', '0') === '1' ? 'on' : 'off'));
      if (serverWasReady === false) recordActivity('Server reconnected');
      serverWasReady = true;
      items.push('Answer providers: ' + ((health.providers || []).some((p) => p.configured) ? 'configured' : 'none configured'));
      items.push('Speech backend: ' + ((health.audio && health.audio.backend) || 'unknown'));
    } catch (_) {
      items.unshift('Server: Needs attention');
      serverWasReady = false;
      items.push('Answer providers: unavailable');
      items.push('Speech backend: unavailable');
    }
    list.replaceChildren(...items.map((item) => el('li', {}, [item])));
    renderActivity();
  }

  function openHome() {
    document.body.classList.remove('show-settings');
    document.body.classList.add('show-home');
    $('app').textContent = 'Status & Activity';
    if (statusTimer) clearInterval(statusTimer);
    statusTimer = setInterval(() => { if (document.body.classList.contains('show-home')) refreshStatus(); }, 10000);
    refreshStatus();
    showWindow();
  }

  Spatial.save('spatial.snoozed', '0');
  recordActivity('App started');

  T.core.invoke('own_pid').then((pid) => { ownPid = pid; });
  setupMic($('mic'));

  T.event.listen('spatial://mark', (event) => onMark(event.payload));
  T.event.listen('spatial://error', (event) => showError(event.payload.message));
  T.event.listen('spatial://settings', () => openSettings());
  T.event.listen('spatial://home', openHome);
  T.event.listen('spatial://snooze', () => { Spatial.save('spatial.snoozed', '1'); recordActivity('Ask shortcut snoozed'); if (document.body.classList.contains('show-home')) refreshStatus(); });
  T.event.listen('spatial://dictation-result', (event) => showDictationResult(event.payload || {}));
  T.event.listen('spatial://dictation-preview', (event) => onDictationPreview(event.payload || {}));
  T.event.listen('spatial://dictation-inserted', () => recordActivity('Dictation inserted'));
  T.event.listen('spatial://dictation-state', (event) => onDictationState(event.payload || {}));

  $('close').onclick = () => hidePanel();
  $('dictateButton').onclick = () => T.event.emitTo('dictate', 'spatial://dictate-down', { target_hwnd: 0, destination: 'composer' })
    .catch(() => showError('Could not start dictation.'));
  T.core.invoke('startup_notice').then((notice) => { if (notice) showError(notice); }).catch(() => {});
  $('gear').onclick = () => (document.body.classList.contains('show-settings') ? closeSettings() : openSettings());
  $('homeButton').onclick = openHome;
  $('refreshStatus').onclick = refreshStatus;
  $('clearActivity').onclick = () => { Spatial.save(ACTIVITY_KEY, '[]'); renderActivity(); };
  $('copyDiagnostics').onclick = async () => {
    const diagnostics = ['Spatial diagnostics', $('statusList').children[0]?.textContent || 'Server: unknown', 'Shortcut: Alt+Shift+S (' + (Spatial.load('spatial.snoozed', '0') === '1' ? 'snoozed' : 'enabled') + ')', 'Recent event categories: ' + JSON.parse(Spatial.load(ACTIVITY_KEY, '[]')).map((item) => item.kind).join(', ')].join('\n');
    try { await navigator.clipboard.writeText(diagnostics); $('copyDiagnostics').textContent = 'Copied'; } catch (_) { showError('Could not copy diagnostics.'); }
  };
  window.addEventListener('keydown', (event) => { if (event.key === 'Escape') hidePanel(); });
  function hidePanel() {
    if (statusTimer) { clearInterval(statusTimer); statusTimer = null; }
    stopRecording();
    if (player) { player.pause(); player = null; }
    if (utterance) { window.speechSynthesis.cancel(); utterance = null; }
    win.hide();
  }
  // The bundled server starts after this WebView. Check again when the panel opens and before recording.
  async function refreshSpeechWhere() {
    let where = ' — speech provider unknown until the server connects';
    try {
      const headers = await Spatial.headers();
      const response = await fetch(Spatial.server() + '/api/health', { headers });
      if (response.ok) {
        const health = await response.json();
        where = (health.audio && health.audio.backend) === 'nvidia' ? ' — sent to NVIDIA speech' : ' — on this computer';
      }
    } catch (_) { /* bundled server may still be extracting */ }
    speechWhere = where;
    $('mic').title = 'Speak your question' + where;
  }
  refreshSpeechWhere();
  $('ask').addEventListener('submit', (event) => { event.preventDefault(); ask(input.value.trim()); });
  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
      event.preventDefault(); $('ask').requestSubmit();
    } else if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault(); $('ask').requestSubmit();
    }
  });
  input.addEventListener('input', updateDocxButton);
  updateDocxButton();
  $('downloadDocx').onclick = downloadDocx;
  $('saveSettings').onclick = async () => {
    Spatial.save('spatial.server', $('server').value.trim());
    Spatial.save('spatial.apiToken', $('apiToken').value.trim());
    Spatial.save('spatial.research', $('research').checked ? '1' : '0');
    Spatial.save('spatial.systemOne', $('systemOne').checked ? '1' : '0');
    Spatial.save('spatial.dictatePolish', $('dictatePolish').checked ? '1' : '0');
    Spatial.save('spatial.dictionary', $('dictionary').value.slice(0, 4000));
    try {
      if ($('autostart').checked) await T.autostart.enable();
      else await T.autostart.disable();
    } catch (err) { showError('Could not update autostart: ' + err.message); }
    closeSettings();
  };
  $('copyPairingToken').onclick = async () => {
    try {
      const token = await T.core.invoke('pairing_token');
      await navigator.clipboard.writeText(token);
      $('copyPairingToken').textContent = 'Copied — paste into the extension API token field';
    } catch (err) { showError('Could not copy pairing token: ' + err.message); }
  };

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => { if (k === 'class') node.className = v; else node.setAttribute(k, v); });
    (children || []).forEach((c) => node.append(c));
    return node;
  }

  async function showWindow() {
    refreshSpeechWhere();
    await win.show();
    await win.setFocus();
  }

  async function openSettings() {
    if (statusTimer) { clearInterval(statusTimer); statusTimer = null; }
    document.body.classList.remove('show-home');
    $('server').value = Spatial.server();
    $('apiToken').value = Spatial.load('spatial.apiToken', '');
    $('research').checked = Spatial.load('spatial.research', '1') === '1';
    $('systemOne').checked = Spatial.load('spatial.systemOne', '1') === '1';
    $('dictatePolish').checked = Spatial.load('spatial.dictatePolish', '0') === '1';
    $('dictionary').value = Spatial.load('spatial.dictionary', '');
    $('autostart').checked = await T.autostart.isEnabled().catch(() => false);
    document.body.classList.add('show-settings');
    await showWindow();
  }

  function closeSettings() {
    document.body.classList.remove('show-settings');
    $('app').textContent = 'Spatial';
    input.focus();
  }

  async function showError(message) {
    recordActivity('An operation needs attention');
    thread.append(el('div', { class: 'error' }, [message]));
    thread.scrollTop = thread.scrollHeight;
    await showWindow();
  }

  function onDictationState(payload) {
    if (payload.destination !== 'composer') return;
    if (payload.state === 'recording') {
      activeDictationId = payload.id;
      dictationDraft = { value: input.value, start: input.selectionStart, end: input.selectionEnd,
        selectionStart: input.selectionStart, selectionEnd: input.selectionEnd };
      input.disabled = true;
      $('dictateButton').textContent = 'Stop';
      $('dictateButton').title = 'Stop dictation';
      document.body.classList.remove('show-home', 'show-settings');
      $('app').textContent = 'Dictating…';
      showWindow();
    } else if (payload.id === activeDictationId && (payload.state === 'cancelled' || payload.state === 'transcribing')) {
      if (payload.state === 'cancelled') restoreDictationDraft(true);
      $('dictateButton').textContent = payload.state === 'transcribing' ? 'Working…' : 'Dictate';
      $('dictateButton').title = payload.state === 'transcribing' ? 'Transcribing audio' : 'Dictate into this composer';
    }
  }

  function onDictationPreview(payload) {
    if (!dictationDraft || payload.id !== activeDictationId) return;
    const { value, start, end } = dictationDraft;
    input.value = value.slice(0, start) + (payload.text || '') + value.slice(end);
    $('app').textContent = 'Dictating · live transcript';
    updateDocxButton();
  }

  function restoreDictationDraft(restoreSelection) {
    if (dictationDraft) {
      input.value = dictationDraft.value;
      if (restoreSelection) {
        input.focus();
        input.setSelectionRange(dictationDraft.selectionStart, dictationDraft.selectionEnd);
      }
    }
    dictationDraft = null;
    activeDictationId = null;
    input.disabled = false;
    $('dictateButton').textContent = 'Dictate';
    $('dictateButton').title = 'Dictate into this composer';
    updateDocxButton();
  }

  async function showDictationResult(payload) {
    if (payload.id !== undefined && payload.destination === 'composer' && payload.id !== activeDictationId) return;
    document.body.classList.remove('show-home', 'show-settings');
    if (payload.error) $('app').textContent = 'Dictation';
    else if (payload.destination === 'composer') {
      if (dictationDraft) {
        const { value, start, end } = dictationDraft;
        input.value = value.slice(0, start) + (payload.text || '') + value.slice(end);
      } else input.value = (input.value.trimEnd() ? input.value.trimEnd() + '\n' : '') + (payload.text || '');
      restoreDictationDraft();
      updateDocxButton();
      input.focus();
      input.setSelectionRange(input.value.length, input.value.length);
      $('app').textContent = 'Dictation draft';
      await showWindow();
      recordActivity('Dictation added to composer');
      return;
    } else $('app').textContent = 'Dictation';
    if (payload.destination === 'composer') restoreDictationDraft(true);
    if (payload.error) {
      thread.append(el('div', { class: 'error' }, [payload.error]));
    } else {
      const result = el('div', { class: 'dictation-result' }, [payload.text || '']);
      if (payload.reason) result.append(el('div', { class: 'meta' }, [payload.reason]));
      const copy = el('button', { type: 'button' }, ['Copy transcript']);
      copy.onclick = async () => { try { await navigator.clipboard.writeText(payload.text || ''); copy.textContent = 'Copied'; } catch (_) { copy.textContent = 'Copy failed'; } };
      result.append(copy);
      thread.append(result);
    }
    await showWindow();
    recordActivity(payload.error ? 'Dictation failed' : 'Dictation ready to copy');
  }

  function updateDocxButton() { $('downloadDocx').disabled = !input.value.trim(); }

  async function downloadDocx() {
    const text = input.value.trim();
    if (!text) return;
    const button = $('downloadDocx');
    button.disabled = true;
    try {
      const response = await Spatial.send('/api/dictate/docx', JSON.stringify({ text }), 'application/json');
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement('a');
      link.href = url;
      link.download = 'spatial-dictation-' + new Date().toISOString().slice(0, 10) + '.docx';
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      recordActivity('Dictation document downloaded');
    } catch (err) { showError('Could not download the Word document: ' + err.message); }
    finally { updateDocxButton(); }
  }

  function candidateRegion(mark) {
    const b = mark.bbox;
    if (mark.kind === 'point') return { x: Math.max(0, b.x - POINT_PAD), y: Math.max(0, b.y - POINT_PAD), width: POINT_PAD * 2, height: POINT_PAD * 2 };
    return b;
  }

  // Beside the mark (right, else left, else below), inside the captured monitor; never covering the mark if avoidable.
  async function placeBesideMark(monitor, mark) {
    const scale = await win.scaleFactor();
    const size = await win.outerSize();
    const w = size.width, h = size.height, gap = Math.round(16 * scale);
    const b = mark.bbox;
    const left = monitor.x + b.x, top = monitor.y + b.y, right = left + b.width, bottom = top + b.height;
    const maxX = monitor.x + monitor.width - w, maxY = monitor.y + monitor.height - h;
    let x;
    let y = Math.min(Math.max(monitor.y, top), maxY);
    if (right + gap <= maxX) x = right + gap;
    else if (left - gap - w >= monitor.x) x = left - gap - w;
    else {
      x = Math.min(Math.max(monitor.x, left), maxX);
      y = bottom + gap <= maxY ? bottom + gap : Math.max(monitor.y, top - gap - h);
    }
    await win.setPosition(new T.dpi.PhysicalPosition(Math.round(x), Math.round(y)));
  }

  async function onMark(payload) {
    if (statusTimer) { clearInterval(statusTimer); statusTimer = null; }
    closeSettings();
    document.body.classList.remove('show-home');
    recordActivity('Ask started');
    thread.replaceChildren();
    state = { ...payload, candidates: [], window: null, contextId: null };
    $('app').textContent = 'Reading…';
    try {
      const found = await Spatial.post('/api/desktop/candidates', {
        capture_id: payload.capture_id, region: candidateRegion(payload.mark), exclude_pids: ownPid ? [ownPid] : [],
      });
      state.candidates = found.candidates || [];
      state.window = found.window || null;
    } catch (err) {
      recordActivity('Screen reading failed');
      thread.append(el('div', { class: 'error' }, ['Could not read the screen: ' + err.message]));
    }
    const w = state.window || {};
    $('app').textContent = w.sensitive ? 'Protected window — not read' : (w.app || w.title || 'Spatial');
    // Best geometric match (same ranking as the extension and server resolver) until the server names the target.
    const G = window.SpatialGeometry;
    const region = candidateRegion(payload.mark);
    const viewport = { width: payload.monitor.width, height: payload.monitor.height };
    const top = G.rankAnchors(state.candidates.filter((c) => (c.text || '').trim() && G.anchorFilter(c.bbox, region, viewport)), region)[0];
    if (top && !w.sensitive) thread.append(el('div', { class: 'target', id: 'target' }, [top.text.slice(0, 300)]));
    await placeBesideMark(payload.monitor, payload.mark);
    await showWindow();
    input.value = '';
    input.focus();
  }

  function renderAnswer(node, text, unsupported) {
    // Build DOM nodes only: model output is untrusted text.
    node.replaceChildren();
    const bad = new Set((unsupported || []).map(Number));
    function inline(target, line) {
      let last = 0;
      for (const match of line.matchAll(/\*\*([^*\n]+)\*\*|`([^`\n]+)`|\[(\d{1,2})\]/g)) {
        target.append(line.slice(last, match.index));
        if (match[1]) target.append(el('strong', {}, [match[1]]));
        else if (match[2]) target.append(el('code', {}, [match[2]]));
        else target.append(el('sup', { class: bad.has(Number(match[3])) ? 'unsupported' : '' }, ['[' + match[3] + ']']));
        last = match.index + match[0].length;
      }
      target.append(line.slice(last));
    }
    let list = null;
    for (const line of text.split('\n')) {
      const heading = /^(#{1,3})\s+(.+)$/.exec(line);
      const item = /^\s*(?:[-*]|\d+[.)])\s+(.+)$/.exec(line);
      if (item) {
        const ordered = /^\s*\d/.test(line);
        const tag = ordered ? 'ol' : 'ul';
        if (!list || list.tagName.toLowerCase() !== tag) {
          list = el(tag);
          node.append(list);
        }
        const li = el('li');
        inline(li, item[1]);
        list.append(li);
      } else {
        list = null;
        const block = el(heading ? 'h' + Math.min(heading[1].length + 2, 6) : 'div');
        inline(block, heading ? heading[2] : line);
        node.append(block);
      }
    }
  }

  function requestBody(question, targetId) {
    const w = state.window || {};
    return {
      protocol_version: 3,
      client_version: 'desktop-0.1',
      capture_id: state.capture_id,
      context_id: state.contextId,
      target_id: targetId || null,
      research: Spatial.load('spatial.research', '1') === '1',
      system_one: Spatial.load('spatial.systemOne', '1') === '1',
      context: {
        surface: {
          kind: 'desktop', app: w.app || null, process: w.process || null, window_title: w.title || null,
          viewport: { width: state.monitor.width, height: state.monitor.height }, device_pixel_ratio: 1,
        },
        marks: [state.mark],
        candidates: state.candidates,
        question,
        privacy_policy: 'crop_only',
      },
    };
  }

  async function ask(question, targetId) {
    if (!question || !state) return;
    send.disabled = true;
    const answer = el('div', { class: 'a' }, ['thinking…']);
    const meta = el('div', { class: 'meta' });
    const turn = el('div', { class: 'turn' }, [el('div', { class: 'q' }, [question]), answer, meta]);
    thread.append(turn);
    input.value = '';
    let text = '';
    try {
      const response = await fetch(Spatial.server() + '/api/ask/stream', {
        method: 'POST', headers: await Spatial.headers(), body: JSON.stringify(requestBody(question, targetId)),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error((data.detail && data.detail.message) || 'server error ' + response.status);
      }
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let cut;
        while ((cut = buffer.indexOf('\n\n')) >= 0) {
          const chunk = buffer.slice(0, cut);
          buffer = buffer.slice(cut + 2);
          const name = (/^event: (.*)$/m.exec(chunk) || [])[1];
          const data = JSON.parse((/^data: (.*)$/m.exec(chunk) || [])[1] || '{}');
          if (name === 'delta') {
            text += data.text || '';
            renderAnswer(answer, text, []);
          } else if (name === 'complete') {
            finish(turn, answer, meta, data, question);
            recordActivity('Ask completed');
          } else if (name === 'error') {
            throw new Error(data.message || data.code || 'answer failed');
          }
          thread.scrollTop = thread.scrollHeight;
        }
      }
    } catch (err) {
      recordActivity('Ask failed');
      answer.replaceChildren(el('div', { class: 'error' }, [err.message]));
    } finally {
      send.disabled = false;
      input.focus();
    }
  }

  /* 🎤 Speech in: MediaRecorder (webm/opus) -> /api/stt (NVIDIA Parakeet, local whisper fallback) -> question box. */
  function setupMic(button) {
    let recorder = null;
    stopRecording = () => { if (recorder) recorder.stop(); };
    button.onclick = async () => {
      if (recorder) { recorder.stop(); return; }
      await refreshSpeechWhere();
      let stream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      } catch (err) {
        showError('Microphone unavailable: ' + (err.message || err.name));
        return;
      }
      const parts = [];
      try {
        recorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
      } catch (err) {
        stream.getTracks().forEach((track) => track.stop());
        showError('Cannot record: ' + (err.message || err.name));
        return;
      }
      const cap = setTimeout(() => { if (recorder) recorder.stop(); }, MAX_RECORD_MS);
      recorder.ondataavailable = (event) => { if (event.data.size) parts.push(event.data); };
      recorder.onstop = async () => {
        clearTimeout(cap);
        stream.getTracks().forEach((track) => track.stop());
        recorder = null;
        button.classList.remove('on');
        button.classList.add('busy');
        input.placeholder = 'Transcribing…';
        try {
          const form = new FormData();
          form.append('audio', new Blob(parts, { type: 'audio/webm' }), 'question.webm');
          const result = await (await Spatial.send('/api/stt', form)).json();
          input.value = (input.value ? input.value + ' ' : '') + (result.text || '');
          if (input.value.trim() && state) ask(input.value.trim()); // spoken question goes straight out
        } catch (err) {
          showError('Could not transcribe: ' + err.message);
        } finally {
          button.classList.remove('busy');
          input.placeholder = 'Ask about what you marked…';
          input.focus();
        }
      };
      recorder.start();
      button.classList.add('on');
      input.placeholder = 'Listening… click 🎤 again to stop';
    };
  }

  /* 🔊 Speech out: server voice when available, otherwise the system voice in WebView2. */
  let player = null;
  let utterance = null;
  function readAloudButton(text) {
    const button = el('button', { title: 'Read aloud' + speechWhere }, ['🔊']);
    button.onclick = async () => {
      if (player) {
        player.pause();
        player = null;
        button.textContent = '🔊';
        return;
      }
      if (utterance) {
        window.speechSynthesis.cancel(); utterance = null;
        button.textContent = '🔊';
        return;
      }
      button.textContent = '…';
      const spoken = text.replace(/\*\*|`/g, '').replace(/\[\d{1,2}\]/g, '');
      try {
        const wav = await (await Spatial.send('/api/tts', JSON.stringify({ text: spoken.slice(0, 4000) }), 'application/json')).blob();
        const url = URL.createObjectURL(wav);
        player = new Audio(url);
        player.onended = () => { URL.revokeObjectURL(url); player = null; button.textContent = '🔊'; };
        button.textContent = '⏹';
        await player.play();
      } catch (err) {
        player = null;
        if (!window.speechSynthesis || !window.SpeechSynthesisUtterance) {
          button.textContent = '🔊';
          showError('Could not read aloud: ' + err.message);
          return;
        }
        utterance = new SpeechSynthesisUtterance(spoken.slice(0, 4000));
        utterance.onend = utterance.onerror = () => { utterance = null; button.textContent = '🔊'; };
        button.textContent = '⏹';
        window.speechSynthesis.speak(utterance);
      }
    };
    return button;
  }

  function finish(turn, answer, meta, result, question) {
    state.contextId = result.id || state.contextId;
    renderAnswer(answer, result.answer || '', result.unsupported_citations);
    const used = (result.anchors_used || [])[0];
    const target = document.getElementById('target');
    if (used && used.text && target) target.textContent = used.text.slice(0, 300);
    const bits = [result.provider, result.model].filter(Boolean);
    if (result.confirmation_required && !(result.clarify || []).length) bits.push('low confidence — mark tighter?');
    meta.replaceChildren(bits.join(' · '));
    if (result.answer) meta.append(readAloudButton(result.answer));
    const sources = result.sources || [];
    if (sources.length) {
      const bad = new Set((result.unsupported_citations || []).map(Number));
      const list = el('ul', { class: 'sources' });
      sources.forEach((s) => {
        let host = s.url || '';
        let url = null;
        try {
          url = new URL(s.url);
          if (!['https:', 'http:'].includes(url.protocol)) url = null;
          else host = url.hostname;
        } catch (_) { /* display source without a link */ }
        const row = el('li', { class: bad.has(Number(s.id)) ? 'unsupported' : '' });
        const label = `[${s.id}] ${s.title || host} — ${host}`;
        if (url) {
          const link = el('a', { href: url.href, title: url.href }, [label]);
          link.onclick = (event) => {
            event.preventDefault();
            T.opener.openUrl(url.href).catch((err) => showError('Could not open source: ' + err.message));
          };
          row.append(link);
        } else row.append(label);
        list.append(row);
      });
      turn.append(list);
    }
    const clarify = result.clarify || [];
    if (clarify.length >= 2) {
      const row = el('div', { class: 'clarify' }, ['Did you mean:']);
      clarify.forEach((choice, i) => {
        const label = (choice.text || '').trim();
        const button = el('button', { title: label }, [`${i + 1}. ${label.length > 40 ? label.slice(0, 39) + '…' : label || 'this'}`]);
        button.onclick = () => ask(question, choice.id);
        row.append(button);
      });
      turn.append(row);
    }
  }
})();
