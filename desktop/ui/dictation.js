(function (root) {
  'use strict';
  function escapeRegExp(text) { return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
  function clean(text, dictionary) {
    let value = String(text || '').trim()
      .replace(/\b(?:um+|uh+|erm+|er+)\b[, ]*/gi, '')
      .replace(/\b([\p{L}\p{N}]+),\s+\1\b/giu, '$1')
      .replace(/\b(\d+)\s+no\s+(\d+)\b/gi, '$2');
    const restart = /\b(?:scratch that|forget that|never mind)\b[, ]*/gi;
    let restartMatch;
    while ((restartMatch = restart.exec(value))) {
      const before = value.slice(0, restartMatch.index);
      const boundary = Math.max(before.lastIndexOf('.'), before.lastIndexOf('!'), before.lastIndexOf('?'), before.lastIndexOf('\n'));
      const clause = before.slice(boundary + 1);
      const comma = clause.lastIndexOf(',');
      const kept = comma >= 0 ? clause.slice(0, comma) : clause.replace(/\s+\S+\s*$/, '');
      value = before.slice(0, boundary + 1) + kept.trimEnd() + (kept.trim() ? ' ' : '') + value.slice(restart.lastIndex);
      restart.lastIndex = 0;
    }
    const commands = [
      [/\bnew paragraph\b/gi, '\n\n'], [/\bnew line\b/gi, '\n'],
      [/\bquestion mark\b/gi, '?'], [/\bexclamation point\b|\bexclamation mark\b/gi, '!'],
      [/\bperiod\b/gi, '.'], [/\bcomma\b/gi, ','], [/\bcolon\b/gi, ':'], [/\bsemicolon\b/gi, ';'],
    ];
    for (const [pattern, replacement] of commands) value = value.replace(pattern, replacement);
    value = value.replace(/[ \t]+([,.!?;:])/g, '$1').replace(/[ \t]+/g, ' ').replace(/ *\n */g, '\n').trim();

    const explicitList = /^(?:please\s+)?(?:create|make|start)(?:\s+me)?\s+(?:a\s+)?(?:to[ -]?do|todo|task)\s+list\s*[:,.]?\s*/i.exec(value);
    let heading = '';
    if (explicitList) {
      heading = 'To-do list:';
      value = value.slice(explicitList[0].length).trim();
    }
    const ordinal = /\b(?:first|firstly|second|secondly|third|thirdly|fourth|fourthly|fifth|fifthly|finally|lastly)\b[:,]?\s*/gi;
    const markers = [...value.matchAll(ordinal)];
    if (markers.length >= 2) {
      const items = markers.map((marker, i) => value.slice(marker.index + marker[0].length,
        i + 1 < markers.length ? markers[i + 1].index : value.length)
        .replace(/\b(?:and\s+)?then\s*$/i, '').replace(/^[,;\s]+|[,;\s.]+$/g, '').trim()).filter(Boolean);
      if (items.length >= 2) value = `${heading ? heading + '\n' : ''}${items.map((item) => '- ' + item).join('\n')}`;
    } else {
      const counted = /^(two|three|four|five|six|2|3|4|5|6)\s+(things|reasons|points|steps|options|ways|issues|updates|questions|items|ideas|problems|tips|decisions)\s*:\s*/i.exec(value);
      if (counted) {
        const count = Number(({ two: 2, three: 3, four: 4, five: 5, six: 6 })[counted[1].toLowerCase()] || counted[1]);
        const rest = value.slice(counted[0].length);
        const lineEnd = rest.search(/\n/);
        const body = lineEnd < 0 ? rest : rest.slice(0, lineEnd);
        const tail = lineEnd < 0 ? '' : rest.slice(lineEnd);
        const items = body.replace(/,?\s+(?:and|or)\s+/gi, ', ').split(/[,;]\s*/).map((item) => item.trim().replace(/[.!?]+$/, '')).filter(Boolean);
        if (items.length === count) {
          const title = counted[0].slice(0, counted[0].indexOf(':')).replace(/^(\w)/, (letter) => letter.toUpperCase());
          value = `${title}:\n${items.map((item, i) => `${i + 1}. ${item}`).join('\n')}${tail}`;
        }
      }
      if (heading && !value.startsWith(heading)) {
        const items = value.replace(/,?\s+(?:and|or)\s+/gi, ', ').split(/[,;]\s*/).map((item) => item.trim().replace(/[.!?]+$/, '')).filter(Boolean);
        if (items.length >= 2) value = `${heading}\n${items.map((item) => '- ' + item).join('\n')}`;
      }
    }
    for (const row of String(dictionary || '').split(/\r?\n/).slice(0, 100)) {
      const divider = row.indexOf('|');
      if (divider < 1) continue;
      const from = row.slice(0, divider).trim();
      const to = row.slice(divider + 1).trim();
      if (from && to) value = value.replace(new RegExp('\\b' + escapeRegExp(from) + '\\b', 'gi'), to);
    }
    return value;
  }
  root.SpatialDictation = { clean, format: clean };
  if (typeof module !== 'undefined') module.exports = root.SpatialDictation;
})(typeof window === 'undefined' ? globalThis : window);

(function () {
  'use strict';
  if (typeof window === 'undefined' || !window.__TAURI__) return;
  const T = window.__TAURI__;
  const win = T.window.getCurrentWindow();
  const $ = (id) => document.getElementById(id);
  let recorder = null;
  let chunks = [];
  let targetHwnd = 0;
  let pressedAt = 0;
  let starting = false;
  let stopWhenReady = false;
  let cancelled = false;
  let live = null;
  let maxDuration = null;
  let destination = 'external';
  const partialCalls = new Set();
  let recordingId = 0;

  T.event.listen('spatial://dictate-down', (event) => {
    if (recorder) { stop(); return; }
    if (starting) { stopWhenReady = true; return; }
    pressedAt = Date.now();
    targetHwnd = Number((event.payload || {}).target_hwnd) || 0;
    destination = (event.payload || {}).destination === 'composer' ? 'composer' : 'external';
    start();
  });
  T.event.listen('spatial://dictate-up', () => {
    if (Date.now() - pressedAt >= 250) stop(); // quick press toggles; hold releases to finish
  });
  T.event.listen('spatial://dictate-cancel', cancel);
  $('stop').onclick = stop;
  $('cancel').onclick = cancel;

  async function showPill() {
    const scale = await win.scaleFactor();
    const size = await win.outerSize();
    await win.setPosition(new T.dpi.PhysicalPosition(
      Math.max(0, Math.round(screen.availWidth * scale - size.width - 12 * scale)), Math.round(12 * scale),
    ));
    await win.show(); // window is non-focusable; the captured input remains the foreground window
  }

  async function start() {
    const id = ++recordingId;
    starting = true;
    cancelled = false;
    stopWhenReady = false;
    chunks = [];
    $('status').textContent = 'Requesting microphone…';
    try {
      await showPill();
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recorder = new MediaRecorder(stream, { mimeType: 'audio/webm;codecs=opus' });
      recorder.ondataavailable = (event) => { if (event.data.size) chunks.push(event.data); };
      recorder.onstop = () => {
        stream.getTracks().forEach((track) => track.stop());
        clearTimeout(maxDuration);
        T.core.invoke('set_dictation_active', { active: false }).catch(() => {});
        const audio = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
        recorder = null;
        if (!cancelled) finishLive().then((liveText) => transcribe(audio, id, liveText));
        else { finishLive(); win.hide(); }
      };
      recorder.start();
      if (destination === 'composer') startLive(stream, id).catch(() => {});
      $('status').textContent = destination === 'composer' ? 'Dictating into Spatial · click Dictate to stop' : 'Dictating · release to finish or press again to stop';
      if (destination === 'composer') {
        T.event.emit('spatial://dictation-state', { state: 'recording', destination, id });
      }
      await T.core.invoke('set_dictation_active', { active: true }).catch(() => {});
      maxDuration = setTimeout(stop, 60000);
      if (stopWhenReady) stop();
    } catch (error) {
      await T.event.emit('spatial://dictation-result', { error: 'Microphone unavailable. ' + (error.message || error.name) });
      await win.hide();
    } finally { starting = false; }
  }

  function stop() {
    if (starting && !recorder) { stopWhenReady = true; return; }
    if (recorder && recorder.state !== 'inactive') {
      $('status').textContent = 'Transcribing…';
      if (destination === 'composer') T.event.emit('spatial://dictation-state', { state: 'transcribing', destination, id: recordingId });
      recorder.stop();
    }
  }

  function cancel() {
    cancelled = true;
    chunks = [];
    if (destination === 'composer') T.event.emit('spatial://dictation-state', { state: 'cancelled', destination, id: recordingId });
    stop();
  }

  async function startLive(stream, id) {
    const headers = await Spatial.headers();
    const socket = new WebSocket(Spatial.server().replace(/^http/, 'ws') + '/api/stt/live');
    const context = new AudioContext({ sampleRate: 16000 });
    const source = context.createMediaStreamSource(stream);
    const processor = context.createScriptProcessor(2048, 1, 1);
    const silent = context.createGain();
    silent.gain.value = 0;
    const session = live = { id, socket, context, source, processor, silent, ready: false, closed: false,
      queue: [], text: '', done: null };
    session.opened = new Promise((resolve) => { session.resolveOpen = resolve; });
    session.done = new Promise((resolve) => { session.resolve = resolve; });
    socket.onopen = () => {
      socket.send(JSON.stringify({ desktop_token: headers['X-Spatial-Desktop'],
        api_token: (headers.Authorization || '').replace(/^Bearer\s+/i, '') }));
      session.resolveOpen();
    };
    socket.onmessage = (event) => {
      let message;
      try { message = JSON.parse(event.data); } catch (_) { return; }
      if (message.type === 'ready') {
        session.ready = true;
        for (const frame of session.queue.splice(0)) socket.send(frame);
      } else if (message.type === 'transcript') {
        session.text = message.text || session.text;
        if (session.text && live === session && !session.closed) T.event.emit('spatial://dictation-preview', { id, text: session.text });
      } else if (message.type === 'done' || message.type === 'error') {
        if (message.type === 'error') session.error = message.message;
        session.resolve();
      }
    };
    socket.onerror = () => { session.resolveOpen(); session.resolve(); };
    socket.onclose = () => { session.resolveOpen(); session.resolve(); };
    processor.onaudioprocess = (event) => {
      if (session.closed || socket.readyState !== WebSocket.OPEN) return;
      const samples = event.inputBuffer.getChannelData(0);
      const frame = new ArrayBuffer(samples.length * 2);
      const view = new DataView(frame);
      for (let i = 0; i < samples.length; i++) {
        view.setInt16(i * 2, Math.max(-32768, Math.min(32767, Math.round(samples[i] * 32767))), true);
      }
      if (session.ready) socket.send(frame);
      else if (session.queue.length < 32) session.queue.push(frame);
    };
    source.connect(processor);
    processor.connect(silent);
    silent.connect(context.destination);
    await context.resume();
  }

  async function finishLive() {
    const session = live;
    if (!session) return '';
    live = null;
    session.closed = true;
    try { session.processor.disconnect(); session.source.disconnect(); session.silent.disconnect(); } catch (_) {}
    await session.context.close().catch(() => {});
    await Promise.race([session.opened, new Promise((resolve) => setTimeout(resolve, 800))]);
    if (session.socket.readyState === WebSocket.OPEN) {
      session.socket.send(JSON.stringify({ type: 'end' }));
      await Promise.race([session.done, new Promise((resolve) => setTimeout(resolve, 1800))]);
      try { session.socket.close(); } catch (_) {}
    }
    return session.text || '';
  }

  async function transcribe(audio, id, liveText) {
    try {
      const form = new FormData();
      form.append('audio', audio, 'dictation.webm');
      let transcript;
      try { transcript = (await (await Spatial.send('/api/stt', form)).json()).text || ''; }
      catch (error) { if (!liveText) throw error; transcript = liveText; }
      if (!transcript) transcript = liveText;
      transcript = SpatialDictation.clean(transcript, Spatial.load('spatial.dictionary', ''));
      if (!transcript) throw new Error('No speech was recognized.');
      let status = 'local cleanup';
      if (Spatial.load('spatial.dictatePolish', '0') === '1') {
        const polish = await Spatial.post('/api/dictate/polish', { transcript, tone: 'neutral' });
        transcript = polish.text || transcript;
        status = polish.status;
      }
      if (targetHwnd) {
        const check = await Spatial.post('/api/desktop/dictation-safe', { target_hwnd: targetHwnd });
        if (check.safe) {
          try {
            await T.core.invoke('paste_dictation', { targetHwnd, text: transcript });
            await T.event.emit('spatial://dictation-inserted', { status });
            await win.hide();
            return;
          } catch (_) { /* Focus can still change between the UIA check and insertion. Keep the text for Copy. */ }
        }
      }
      await T.event.emit('spatial://dictation-result', { text: transcript, id,
        destination: destination === 'composer' ? 'composer' : 'external',
        reason: destination === 'composer' ? '' : 'Focus changed or the target field is protected; copy the transcript instead.', status });
    } catch (error) {
      await T.event.emit('spatial://dictation-result', { error: error.message || 'Dictation failed.', id, destination });
    } finally { await win.hide(); }
  }
})();
