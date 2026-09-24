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

  T.core.invoke('own_pid').then((pid) => { ownPid = pid; });
  setupMic($('mic'));

  T.event.listen('spatial://mark', (event) => onMark(event.payload));
  T.event.listen('spatial://error', (event) => showError(event.payload.message));
  T.event.listen('spatial://settings', () => openSettings());

  $('close').onclick = () => hidePanel();
  $('gear').onclick = () => (document.body.classList.contains('show-settings') ? closeSettings() : openSettings());
  window.addEventListener('keydown', (event) => { if (event.key === 'Escape') hidePanel(); });
  function hidePanel() {
    stopRecording();
    if (player) { player.pause(); player = null; }
    win.hide();
  }
  // Speech goes to the server's backend (NVIDIA hosted by default): say so where the user presses.
  fetch(Spatial.server() + '/api/health').then((r) => r.json()).then((health) => {
    const where = (health.audio && health.audio.backend) === 'nvidia' ? ' — sent to NVIDIA speech' : ' — on this computer';
    $('mic').title += where;
    speechWhere = where;
  }).catch(() => {});
  $('ask').addEventListener('submit', (event) => { event.preventDefault(); ask(input.value.trim()); });
  $('saveSettings').onclick = () => {
    Spatial.save('spatial.server', $('server').value.trim());
    Spatial.save('spatial.apiToken', $('apiToken').value.trim());
    Spatial.save('spatial.research', $('research').checked ? '1' : '0');
    closeSettings();
  };

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([k, v]) => { if (k === 'class') node.className = v; else node.setAttribute(k, v); });
    (children || []).forEach((c) => node.append(c));
    return node;
  }

  async function showWindow() {
    await win.show();
    await win.setFocus();
  }

  async function openSettings() {
    $('server').value = Spatial.server();
    $('apiToken').value = Spatial.load('spatial.apiToken', '');
    $('research').checked = Spatial.load('spatial.research', '1') === '1';
    document.body.classList.add('show-settings');
    await showWindow();
  }

  function closeSettings() {
    document.body.classList.remove('show-settings');
    input.focus();
  }

  async function showError(message) {
    thread.append(el('div', { class: 'error' }, [message]));
    thread.scrollTop = thread.scrollHeight;
    await showWindow();
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
    closeSettings();
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
    // Built from DOM nodes only (never innerHTML): **bold**, `code` and [n] citations; everything else stays text.
    node.replaceChildren();
    const bad = new Set((unsupported || []).map(Number));
    let last = 0;
    for (const match of text.matchAll(/\*\*([^*\n]+)\*\*|`([^`\n]+)`|\[(\d{1,2})\]/g)) {
      node.append(text.slice(last, match.index));
      if (match[1]) node.append(el('strong', {}, [match[1]]));
      else if (match[2]) node.append(el('code', {}, [match[2]]));
      else node.append(el('sup', { class: bad.has(Number(match[3])) ? 'unsupported' : '' }, ['[' + match[3] + ']']));
      last = match.index + match[0].length;
    }
    node.append(text.slice(last));
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
          } else if (name === 'error') {
            throw new Error(data.message || data.code || 'answer failed');
          }
          thread.scrollTop = thread.scrollHeight;
        }
      }
    } catch (err) {
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

  /* 🔊 Speech out: /api/tts (NVIDIA Magpie, local pocket-tts fallback) -> WAV blob; click again to stop. */
  let player = null;
  let speechWhere = '';
  function readAloudButton(text) {
    const button = el('button', { title: 'Read aloud' + speechWhere }, ['🔊']);
    button.onclick = async () => {
      if (player) {
        player.pause();
        player = null;
        button.textContent = '🔊';
        return;
      }
      button.textContent = '…';
      try {
        const spoken = text.replace(/\*\*|`/g, '').replace(/\[\d{1,2}\]/g, '');
        const wav = await (await Spatial.send('/api/tts', JSON.stringify({ text: spoken.slice(0, 4000) }), 'application/json')).blob();
        const url = URL.createObjectURL(wav);
        player = new Audio(url);
        player.onended = () => { URL.revokeObjectURL(url); player = null; button.textContent = '🔊'; };
        button.textContent = '⏹';
        await player.play();
      } catch (err) {
        player = null;
        button.textContent = '🔊';
        showError('Could not read aloud: ' + err.message);
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
        try { host = new URL(s.url).hostname; } catch (_) { /* keep raw */ }
        list.append(el('li', { class: bad.has(Number(s.id)) ? 'unsupported' : '', title: s.url || '' }, [`[${s.id}] ${s.title || host} — ${host}`]));
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
