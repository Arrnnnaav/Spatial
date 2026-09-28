/* Spatial Context overlay: runs on any page (injected by the service worker) and inside the bundled
   PDF viewer (loaded directly). Draw over what you are reading, ask, get an answer about that region.
   Requires config.js and geometry.js to be loaded first. */
(function () {
  'use strict';
  if (window.__spatialSpatialLoaded) return;
  window.__spatialSpatialLoaded = true;

  const CFG = window.SPATIAL_CONFIG || { mode: 'standalone', productName: 'Point & Ask', features: {} };
  const G = window.SpatialGeometry;
  const STROKE = '#ff3d7f', SOURCE = '#ff3d7f', TARGET = '#2f7cf6', HIGHLIGHT = '#00d4aa';
  const state = { open: false, tool: 'pen', role: 'reference', marks: [], contextId: null, busy: false, drawing: null, consent: true, requestId: 0, settings: {}, pinTarget: null };
  let host, root, svg, panel, toolbar, hint, consentCard;

  const CSS = `
    :host { all: initial; }
    .overlay { position: fixed; inset: 0; z-index: 2147483646; cursor: crosshair; touch-action: none; }
    svg { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
    .toolbar { position: fixed; top: 14px; left: 50%; transform: translateX(-50%); display: flex; gap: 4px; align-items: center;
      background: #14141a; color: #fff; border-radius: 999px; padding: 6px 10px; font: 500 13px/1 system-ui, sans-serif;
      box-shadow: 0 10px 30px rgba(0,0,0,.35); z-index: 2147483647; cursor: default; white-space: nowrap; }
    .toolbar button { all: unset; cursor: pointer; padding: 6px 10px; border-radius: 999px; color: #d7d7e0; }
    .toolbar button:hover { background: #26262f; }
    .toolbar button.active { background: ${STROKE}; color: #fff; }
    .toolbar button.role.active-source { background: ${SOURCE}; color: #fff; }
    .toolbar button.role.active-target { background: ${TARGET}; color: #fff; }
    .toolbar .sep { width: 1px; height: 18px; background: #333; margin: 0 4px; }
    .toolbar .kbd { color: #8f8fa3; font-size: 11px; padding-left: 4px; }
    .hint { position: fixed; bottom: 22px; left: 50%; transform: translateX(-50%); background: rgba(20,20,26,.9); color: #fff;
      padding: 8px 14px; border-radius: 10px; font: 13px/1.3 system-ui, sans-serif; z-index: 2147483647; pointer-events: none; }
    .panel { position: fixed; width: 360px; max-width: calc(100vw - 24px); background: #fff; color: #17171c; border-radius: 14px;
      box-shadow: 0 18px 50px rgba(0,0,0,.28), 0 0 0 1px rgba(0,0,0,.06); font: 14px/1.45 system-ui, sans-serif; z-index: 2147483647;
      cursor: default; display: flex; flex-direction: column; overflow: hidden; }
    .panel header { display: flex; align-items: center; gap: 8px; padding: 10px 12px; background: #fafafc; border-bottom: 1px solid #ececf1; font-size: 12px; color: #6b6b7b; }
    .panel header b { color: ${STROKE}; font-size: 12px; letter-spacing: .04em; }
    .panel header .badge { font-size: 10px; padding: 2px 6px; border-radius: 999px; color: #fff; background: ${SOURCE}; }
    .panel header .badge.target { background: ${TARGET}; }
    .panel header .close { margin-left: auto; all: unset; cursor: pointer; padding: 2px 6px; border-radius: 6px; color: #6b6b7b; }
    .panel header .close:hover { background: #ececf1; }
    .thread { max-height: 40vh; overflow: auto; padding: 10px 12px; display: flex; flex-direction: column; gap: 10px; }
    .thread:empty { display: none; }
    .q { align-self: flex-end; background: #f1f1f6; padding: 7px 10px; border-radius: 12px 12px 3px 12px; max-width: 90%; white-space: pre-wrap; }
    .a { background: #fff; white-space: pre-wrap; }
    .a small { display: block; color: #8f8fa3; font-size: 11px; margin-top: 4px; }
    .a.err { color: #b3261e; }
    .a .actions { display: flex; gap: 6px; margin-top: 6px; flex-wrap: wrap; }
    .a .actions button { all: unset; cursor: pointer; font-size: 12px; color: #6b6b7b; padding: 3px 8px; border-radius: 6px; background: #f1f1f6; }
    .a .actions button:hover { background: #e6e6ee; }
    .a .actions button.on { color: #fff; background: ${STROKE}; }
    .a .actions button.done { color: #1a7f4b; }
    .ask { display: flex; gap: 6px; padding: 10px 12px; border-top: 1px solid #ececf1; align-items: flex-end; }
    textarea { flex: 1; resize: none; border: 1px solid #d9d9e3; border-radius: 10px; padding: 8px 10px; font: inherit; min-height: 40px; max-height: 120px; outline: none; }
    textarea:focus { border-color: ${STROKE}; }
    .ask button { all: unset; cursor: pointer; height: 38px; min-width: 38px; display: grid; place-items: center; border-radius: 10px; }
    .ask .send { background: #17171c; color: #fff; padding: 0 12px; font-weight: 600; }
    .ask .send[disabled] { opacity: .5; cursor: progress; }
    .ask .mic { background: #f1f1f6; }
    .ask .mic.on { background: ${STROKE}; color: #fff; animation: pulse 1s infinite; }
    .ask .mic.busy { opacity: .6; cursor: progress; }
    @keyframes pulse { 50% { opacity: .6; } }
    @keyframes ring { 0% { stroke-opacity: .9; stroke-width: 3; } 100% { stroke-opacity: 0; stroke-width: 14; } }
    .ring { fill: none; stroke: ${HIGHLIGHT}; animation: ring 1.4s ease-out infinite; }
    .ring-static { fill: rgba(0,212,170,.10); stroke: ${HIGHLIGHT}; stroke-width: 2; }
    .ring-choice { fill: rgba(47,124,246,.08); stroke: ${TARGET}; stroke-width: 2; stroke-dasharray: 6 4; }
    .ring-label { fill: ${TARGET}; font: 700 14px system-ui, sans-serif; }
    .a .clarify { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-top: 6px; font-size: 12px; color: #6b6b7b; }
    .a .clarify button { all: unset; cursor: pointer; font-size: 12px; padding: 3px 8px; border-radius: 6px; background: #eaf1fe; color: #17171c; }
    .a .clarify button:hover { background: #d8e6fd; }
    .meta { padding: 0 12px 10px; font-size: 11px; color: #8f8fa3; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
    .meta label { display: inline-flex; gap: 4px; align-items: center; color: #17171c; cursor: pointer; white-space: nowrap; }
    .meta input { margin: 0; }
    .meta .levels { display: inline-flex; border: 1px solid #d9d9e3; border-radius: 999px; overflow: hidden; }
    .meta .levels button { all: unset; cursor: pointer; padding: 2px 8px; font-size: 11px; color: #6b6b7b; }
    .meta .levels button.on { background: #17171c; color: #fff; }
    .a .sources { margin-top: 6px; font-size: 11px; color: #6b6b7b; display: flex; flex-direction: column; gap: 2px; }
    .a .sources a { color: #2f7cf6; text-decoration: none; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .a .sources a.cited { font-weight: 600; }
    .a .sources a.unsupported::after { content: ' ⚠ not supported'; color: #b3261e; font-weight: 400; }
    .consent { position: fixed; inset: 0; z-index: 2147483647; display: grid; place-items: center; background: rgba(10,10,14,.55); cursor: default; }
    .consent .card { width: 420px; max-width: calc(100vw - 32px); background: #fff; color: #17171c; border-radius: 16px; padding: 22px; font: 14px/1.5 system-ui, sans-serif; box-shadow: 0 24px 60px rgba(0,0,0,.35); }
    .consent h2 { margin: 0 0 6px; font-size: 18px; }
    .consent p { margin: 6px 0; color: #4a4a58; }
    .consent label { display: flex; gap: 10px; align-items: flex-start; margin: 8px 0; cursor: pointer; }
    .consent label b { display: block; }
    .consent .row { display: flex; gap: 8px; margin-top: 14px; justify-content: flex-end; }
    .consent button { all: unset; cursor: pointer; padding: 9px 14px; border-radius: 10px; font-weight: 600; }
    .consent .go { background: ${STROKE}; color: #fff; }
    .consent .no { color: #6b6b7b; }
  `;

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (key === 'class') node.className = value; else if (key.startsWith('on')) node[key] = value; else node.setAttribute(key, value);
    }
    for (const child of children || []) node.append(child);
    return node;
  }

  function send(message) {
    return new Promise(resolve => chrome.runtime.sendMessage(message, response => resolve(response || { ok: false, error: chrome.runtime.lastError?.message || 'no response' })));
  }

  /* Build ------------------------------------------------------------------ */
  function build() {
    host = el('div', { id: 'spatial-overlay-host' });
    host.style.cssText = 'all:initial;position:fixed;inset:0;z-index:2147483646;';
    root = host.attachShadow({ mode: 'open' });
    root.append(el('style', {}, [CSS]));
    const overlay = el('div', { class: 'overlay' });
    svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    overlay.append(svg);
    toolbar = el('div', { class: 'toolbar' }, [
      el('button', { 'data-tool': 'pen', class: 'active', title: 'Freehand', onclick: () => setTool('pen') }, ['✎ Pen']),
      el('button', { 'data-tool': 'circle', onclick: () => setTool('circle') }, ['◯ Circle']),
      el('button', { 'data-tool': 'rect', onclick: () => setTool('rect') }, ['▭ Box']),
      el('span', { class: 'sep' }),
      el('button', { 'data-role': 'source', class: 'role', title: 'Next mark = SOURCE (the thing)', onclick: () => setRole('source') }, ['A Source']),
      el('button', { 'data-role': 'target', class: 'role', title: 'Next mark = TARGET (where / compared to)', onclick: () => setRole('target') }, ['B Target']),
      el('span', { class: 'sep' }),
      el('button', { onclick: clearMarks }, ['Clear']),
      el('button', { onclick: close }, ['Done']),
      el('span', { class: 'kbd' }, ['Esc']),
    ]);
    hint = el('div', { class: 'hint' }, ['Circle or scribble over the part you have a question about']);
    root.append(overlay, toolbar, hint);
    overlay.addEventListener('pointerdown', onDown);
    overlay.addEventListener('pointermove', onMove);
    overlay.addEventListener('pointerup', onUp);
    overlay.addEventListener('pointercancel', onUp);
    document.documentElement.append(host);
  }

  function setTool(tool) {
    state.tool = tool;
    for (const button of toolbar.querySelectorAll('[data-tool]')) button.classList.toggle('active', button.dataset.tool === tool);
  }

  function setRole(role) {
    state.role = state.role === role ? 'reference' : role;
    for (const button of toolbar.querySelectorAll('[data-role]')) {
      button.classList.toggle('active-source', state.role === 'source' && button.dataset.role === 'source');
      button.classList.toggle('active-target', state.role === 'target' && button.dataset.role === 'target');
    }
    hint.textContent = state.role === 'reference' ? 'Circle or scribble over the part you have a question about'
      : state.role === 'source' ? 'Mark the SOURCE (the thing you mean), then switch to Target' : 'Mark the TARGET (where it goes / what to compare against)';
  }

  async function open() {
    if (!host) build();
    const info = await send({ type: 'spatial:settings' });
    if (info.ok) state.settings = info.settings || {};
    host.style.display = '';
    state.open = true;
    document.addEventListener('keydown', onKey, true);
    if (!state.consent) showConsent();
  }

  function close() {
    state.open = false;
    if (host) host.style.display = 'none';
    document.removeEventListener('keydown', onKey, true);
    stopSpeaking();
  }

  function clearMarks() {
    state.marks = []; state.contextId = null;
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    if (panel) { panel.remove(); panel = null; }
    hint.style.display = '';
    setRole('reference');
  }

  function onKey(event) {
    if (event.key === 'Escape') { event.stopPropagation(); close(); }
  }

  /* First-run consent: what leaves the browser, and the choice to keep pixels local. */
  function showConsent() {
    if (consentCard) return;
    let privacy = 'crop_only';
    let systemOne = false;
    const option = (value, title, text, checked) => el('label', {}, [
      el('input', { type: 'radio', name: 'privacy', value, ...(checked ? { checked: '' } : ''), onchange: () => { privacy = value; } }),
      el('span', {}, [el('b', {}, [title]), text])]);
    consentCard = el('div', { class: 'consent' }, [el('div', { class: 'card' }, [
      el('h2', {}, [CFG.productName + ' needs to see what you circle']),
      el('p', {}, ['When you ask, the text under your mark and (by default) a small image crop of the marked region are sent to the answer server. Nothing is sent until you press Ask, and nothing on the page is ever changed.']),
      option('crop_only', 'Crop of the marked region + text', ' (default, best answers for diagrams and equations)', true),
      option('anchors_only', 'Text only, no pixels', ' (works on any page with text; diagrams get weaker answers)'),
      option('full_frame', 'Whole visible tab + text', ' (only if you want the model to see surrounding context)'),
      el('label', {}, [el('input', { type: 'checkbox', onchange: e => { systemOne = e.target.checked; } }),
        el('span', {}, [el('b', {}, ['Use TypeSafe Jev']), ' (optional: sends your question and shortlisted text to TypeSafe to choose the target; no pixels)'])]),
      el('p', {}, ['It never runs on banking, health or government sites. You can change this any time from the extension icon.']),
      el('div', { class: 'row' }, [
        el('button', { class: 'no', onclick: () => { consentCard.remove(); consentCard = null; close(); } }, ['Not now']),
        el('button', { class: 'go', onclick: async () => {
          await send({ type: 'spatial:consent', privacy, systemOne });
          state.settings.systemOne = systemOne;
          state.consent = true; consentCard.remove(); consentCard = null;
        } }, ['Continue']),
      ]),
    ])]);
    consentCard.addEventListener('pointerdown', e => e.stopPropagation());
    root.append(consentCard);
  }

  /* Drawing ---------------------------------------------------------------- */
  function svgNode(name, attrs) {
    const node = document.createElementNS('http://www.w3.org/2000/svg', name);
    for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
    return node;
  }

  function strokeColor() { return state.role === 'target' ? TARGET : STROKE; }

  function onDown(event) {
    if (event.button !== 0 || !state.consent || (panel && panel.contains(event.target))) return;
    event.preventDefault();
    const start = [event.clientX, event.clientY];
    const color = strokeColor();
    let shape;
    if (state.tool === 'pen') shape = svgNode('path', { d: `M${start[0]} ${start[1]}`, fill: 'none', stroke: color, 'stroke-width': 4, 'stroke-linecap': 'round', 'stroke-linejoin': 'round', opacity: .9 });
    else if (state.tool === 'circle') shape = svgNode('ellipse', { fill: 'none', stroke: color, 'stroke-width': 4, opacity: .9 });
    else shape = svgNode('rect', { fill: 'none', stroke: color, 'stroke-width': 4, rx: 6, opacity: .9 });
    svg.append(shape);
    state.drawing = { start, points: [start], shape };
    event.currentTarget.setPointerCapture(event.pointerId);
  }

  function onMove(event) {
    const d = state.drawing; if (!d) return;
    const point = [event.clientX, event.clientY];
    if (state.tool === 'pen') { d.points.push(point); d.shape.setAttribute('d', d.shape.getAttribute('d') + ` L${point[0]} ${point[1]}`); return; }
    const box = G.shapeToMark(state.tool, d.start, point);
    if (state.tool === 'circle') { d.shape.setAttribute('cx', box.x + box.width / 2); d.shape.setAttribute('cy', box.y + box.height / 2); d.shape.setAttribute('rx', box.width / 2); d.shape.setAttribute('ry', box.height / 2); }
    else { d.shape.setAttribute('x', box.x); d.shape.setAttribute('y', box.y); d.shape.setAttribute('width', box.width); d.shape.setAttribute('height', box.height); }
    d.end = point;
  }

  function onUp(event) {
    const d = state.drawing; if (!d) return;
    state.drawing = null;
    const end = d.end || [event.clientX, event.clientY];
    const mark = state.tool === 'pen' ? G.strokeToMark(d.points, state.role) : G.shapeToMark(state.tool, d.start, end, state.role);
    if (mark.width < 6 && mark.height < 6) { d.shape.remove(); return; }
    mark.scrollX = window.scrollX; mark.scrollY = window.scrollY;
    state.marks.push(mark);
    hint.style.display = 'none';
    if (state.role === 'source') { setRole('target'); hint.style.display = ''; }
    showPanel(mark);
  }

  /* AI → human: pulse a ring around the element the server resolved for each mark. */
  function highlightAnchors(anchorsUsed) {
    for (const node of svg.querySelectorAll('.ring, .ring-static, .ring-choice, .ring-label')) node.remove();
    const seen = new Set();
    for (const anchor of anchorsUsed || []) {
      if (!anchor.bbox || seen.has(anchor.mark_index)) continue;
      seen.add(anchor.mark_index);
      const b = anchor.bbox, pad = 4;
      svg.append(svgNode('rect', { class: 'ring-static', x: b.x - pad, y: b.y - pad, width: b.width + pad * 2, height: b.height + pad * 2, rx: 6 }));
      const ring = svgNode('rect', { class: 'ring', x: b.x - pad, y: b.y - pad, width: b.width + pad * 2, height: b.height + pad * 2, rx: 6 });
      svg.append(ring);
      setTimeout(() => ring.remove(), 8000);
    }
  }

  /* Ambiguous mark: number the plausible targets on the page and offer them as chips. */
  function attachClarify(answerNode, clarify, question, input, thread, sendButton) {
    const row = el('div', { class: 'clarify' }, ['Did you mean:']);
    clarify.forEach((choice, index) => {
      const n = String(index + 1);
      if (choice.bbox) {
        const b = choice.bbox;
        svg.append(svgNode('rect', { class: 'ring-choice', x: b.x - 3, y: b.y - 3, width: b.width + 6, height: b.height + 6, rx: 6 }));
        const label = svgNode('text', { class: 'ring-label', x: b.x - 2, y: Math.max(14, b.y - 6) });
        label.textContent = n;
        svg.append(label);
      }
      const text = (choice.text || '').trim();
      const button = el('button', { title: text }, [n + '. ' + (text.length > 40 ? text.slice(0, 39) + '…' : text || 'this')]);
      button.onclick = () => {
        if (state.busy) return;
        state.pinTarget = choice.id;
        state.contextId = null; // the rejected answer must not enter the correction's model history
        if (answerNode.previousElementSibling?.classList.contains('q')) answerNode.previousElementSibling.remove();
        answerNode.remove();
        input.value = question;
        submit(input, thread, sendButton);
      };
      row.append(button);
    });
    answerNode.insertBefore(row, answerNode.querySelector('small'));
  }

  /* Ask panel --------------------------------------------------------------- */
  function showPanel(mark) {
    if (!panel) {
      panel = el('div', { class: 'panel' });
      const thread = el('div', { class: 'thread' });
      const input = el('textarea', { placeholder: 'Ask about what you marked… (Enter to send)', rows: 1 });
      const mic = el('button', { class: 'mic', title: 'Speak your question' }, ['🎤']);
      const sendButton = el('button', { class: 'send', onclick: () => submit(input, thread, sendButton) }, ['Ask']);
      input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submit(input, thread, sendButton); } e.stopPropagation(); });
      input.addEventListener('keyup', e => e.stopPropagation());
      setupMic(mic, input);
      panel.append(
        el('header', {}, [el('b', {}, ['POINT & ASK']), el('span', { class: 'marks' }, ['1 mark']),
          el('button', { class: 'close', title: 'Close', onclick: close }, ['✕'])]),
        thread,
        el('div', { class: 'ask' }, [input, mic, sendButton]),
        el('div', { class: 'meta' }, [
          el('label', { title: 'Search the web, answer only from sources, cite them. Slower (~5 s) but precise.' }, [
            el('input', { type: 'checkbox', id: 'research', ...(state.settings.research !== false ? { checked: '' } : {}), onchange: e => { state.settings.research = e.target.checked; send({ type: 'spatial:set', research: e.target.checked }); } }),
            '🔎 Verify with sources']),
          (() => { const box = el('span', { class: 'levels', title: 'How deep should the explanation go?' });
            for (const [key, label] of [['eli5', 'ELI5'], ['student', 'Student'], ['expert', 'Expert']]) {
              const b = el('button', { class: (state.settings.level || 'student') === key ? 'on' : '', onclick: () => { state.settings.level = key; for (const x of box.children) x.classList.toggle('on', x === b); send({ type: 'spatial:set', level: key }); } }, [label]);
              box.append(b);
            }
            return box; })(),
          el('span', {}, ['Reference only: nothing acts on the page.']),
        ]),
      );
      panel.addEventListener('pointerdown', e => e.stopPropagation());
      root.append(panel);
      setTimeout(() => input.focus(), 0);
    }
    const header = panel.querySelector('header');
    for (const badge of header.querySelectorAll('.badge')) badge.remove();
    const roles = state.marks.map(m => m.role).filter(r => r !== 'reference');
    for (const role of roles) header.insertBefore(el('span', { class: 'badge ' + role }, [role.toUpperCase()]), header.querySelector('.close'));
    panel.querySelector('.marks').textContent = state.marks.length + (state.marks.length === 1 ? ' mark' : ' marks');
    const margin = 12, width = Math.min(360, window.innerWidth - 24);
    let left = mark.x + mark.width + margin;
    if (left + width > window.innerWidth - margin) left = Math.max(margin, mark.x - width - margin);
    if (left + width > window.innerWidth - margin) left = Math.max(margin, window.innerWidth - width - margin);
    panel.style.left = left + 'px';
    panel.style.top = Math.max(margin, Math.min(mark.y, window.innerHeight - 260)) + 'px';
  }

  /* Mic: browser Web Speech API by default (zero install). In Power mode, record with MediaRecorder and
     transcribe on the server (faster-whisper) via the offscreen document so the mic is granted once. */
  function setupMic(button, input) {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    let webSpeech = null, recording = false;
    const finish = () => { button.classList.remove('on', 'busy'); input.focus(); };
    const startWebSpeech = () => {
      if (!Recognition) return false;
      webSpeech = new Recognition(); webSpeech.interimResults = true; webSpeech.lang = navigator.language || 'en-US';
      button.classList.add('on'); input.placeholder = 'Listening… click the mic again to stop';
      webSpeech.onresult = event => { input.value = Array.from(event.results).map(r => r[0].transcript).join(' '); };
      webSpeech.onend = () => { webSpeech = null; finish(); };
      webSpeech.onerror = event => { webSpeech = null; finish(); if (event.error === 'not-allowed') input.placeholder = 'Microphone blocked for this site — allow it in the address bar'; };
      try { webSpeech.start(); return true; } catch (_) { webSpeech = null; finish(); return false; }
    };
    const startServer = async () => {
      const started = await send({ type: 'spatial:record', action: 'start' });
      if (!started.ok) { input.placeholder = started.error || 'Recorder unavailable'; return startWebSpeech(); }
      recording = true; button.classList.add('on'); input.placeholder = 'Listening (server transcription)… click again to stop';
      return true;
    };
    const stopServer = async () => {
      recording = false; button.classList.remove('on'); button.classList.add('busy');
      const stopped = await send({ type: 'spatial:record', action: 'stop' });
      if (!stopped.ok) { input.placeholder = stopped.error || 'Recording failed'; return finish(); }
      const result = await send({ type: 'spatial:transcribe', audio: stopped.audio, mimeType: stopped.mimeType });
      if (result.ok) input.value = (input.value ? input.value + ' ' : '') + result.text; else input.placeholder = 'Transcription failed: ' + result.error;
      finish();
    };
    if (!Recognition && !navigator.mediaDevices) { button.style.display = 'none'; return; }
    button.onclick = () => {
      if (webSpeech) { webSpeech.stop(); return; }
      if (recording) { stopServer(); return; }
      if (state.settings.powerMode) startServer(); else if (!startWebSpeech()) input.placeholder = 'Speech recognition not available in this browser';
    };
  }

  /* Read aloud: server pocket-tts in Power mode, otherwise the OS voice via speechSynthesis. */
  let player = null;
  function stopSpeaking() { if (player) { player.pause(); player = null; } if (window.speechSynthesis) window.speechSynthesis.cancel(); }
  function attachSpeaker(actions, text) {
    const button = el('button', { title: 'Read aloud' }, ['🔊 Read aloud']);
    const reset = () => { player = null; button.classList.remove('on'); button.textContent = '🔊 Read aloud'; };
    button.onclick = async () => {
      if (player) { stopSpeaking(); reset(); return; }
      button.classList.add('on'); button.textContent = '… generating';
      if (state.settings.powerMode) {
        const response = await send({ type: 'spatial:speak', text });
        if (response.ok) {
          player = new Audio(response.audio); player.onended = reset; button.textContent = '⏹ Stop';
          try { await player.play(); return; } catch (_) { /* fall through to browser voice */ }
        }
      }
      if (!window.speechSynthesis) { reset(); button.textContent = '🔇 no voice'; return; }
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.onend = reset;
      player = { pause: () => window.speechSynthesis.cancel() };
      button.textContent = '⏹ Stop';
      window.speechSynthesis.cancel(); window.speechSynthesis.speak(utterance);
    };
    actions.append(button);
    return button;
  }

  /* Context collection ------------------------------------------------------ */
  function unionBox(marks) {
    const x = Math.min(...marks.map(m => m.x)), y = Math.min(...marks.map(m => m.y));
    return { x, y, width: Math.max(...marks.map(m => m.x + m.width)) - x, height: Math.max(...marks.map(m => m.y + m.height)) - y };
  }

  function elementText(element) {
    if (element.matches('img,svg,canvas,video,picture')) return (element.getAttribute('alt') || element.getAttribute('aria-label') || element.getAttribute('title') || '').trim();
    if (element.matches('input,textarea,select')) {
      const type = (element.getAttribute('type') || '').toLowerCase();
      const autocomplete = (element.getAttribute('autocomplete') || '').toLowerCase();
      if (['password', 'hidden', 'file'].includes(type) ||
          /(?:^|\s)(?:current-password|new-password|one-time-code|cc-[^\s]+)(?:\s|$)/.test(autocomplete)) return '';
      return (element.value || element.placeholder || '').trim();
    }
    return (element.innerText || element.textContent || '').replace(/\s+/g, ' ').trim();
  }

  /* DOM elements under each mark, deepest first, filtered so page-wide containers do not swamp the prompt.
     The user's text selection (if any) is the strongest signal and goes first. */
  function collectAnchors(marks) {
    const viewport = { width: window.innerWidth, height: window.innerHeight };
    const seen = new Map();
    if (host) host.style.pointerEvents = 'none';
    try {
      for (const mark of marks) {
        for (const [x, y] of G.samplePoints(mark, 6)) {
          if (x < 0 || y < 0 || x > viewport.width || y > viewport.height) continue;
          for (const element of document.elementsFromPoint(x, y).slice(0, 6)) {
            if (element === host || element === document.documentElement || element === document.body || seen.has(element)) continue;
            const rect = element.getBoundingClientRect();
            const bbox = { x: rect.left, y: rect.top, width: rect.width, height: rect.height };
            if (!G.anchorFilter(bbox, mark, viewport)) continue;
            const text = elementText(element).slice(0, 800);
            if (!text && !element.matches('img,svg,canvas,video')) continue;
            const page = element.closest('[data-page-number]');
            seen.set(element, { id: 'el-' + seen.size, type: element.tagName.toLowerCase(), role: element.getAttribute('role') || '', text, bbox,
              href: element.closest('a[href]')?.href || '', src: element.currentSrc || element.src || '', page: page ? Number(page.dataset.pageNumber) : null });
          }
        }
      }
    } finally { if (host) host.style.pointerEvents = ''; }
    const box = unionBox(marks);
    const ranked = G.rankAnchors([...seen.values()], box).slice(0, 12);
    for (const block of pdfTextBlocks(marks)) ranked.unshift(block);
    const selection = window.getSelection && window.getSelection();
    if (selection && selection.rangeCount && String(selection).trim()) {
      const rect = selection.getRangeAt(0).getBoundingClientRect();
      ranked.unshift({ id: 'selection', type: 'selection', text: String(selection).trim().slice(0, 800), score: 1,
        bbox: rect.width ? { x: rect.left, y: rect.top, width: rect.width, height: rect.height } : box });
    }
    return ranked;
  }

  /* In the PDF viewer the text layer is one span per glyph run, so a circled paragraph would arrive as
     dozens of fragments. Merge the spans inside each mark into one block per page, in reading order. */
  function pdfTextBlocks(marks) {
    if (!window.__spatialViewer) return [];
    const blocks = [];
    for (const [index, mark] of marks.entries()) {
      const perPage = new Map();
      for (const span of document.querySelectorAll('.textLayer span')) {
        const rect = span.getBoundingClientRect();
        if (rect.width <= 0 || rect.bottom < mark.y || rect.top > mark.y + mark.height || rect.right < mark.x || rect.left > mark.x + mark.width) continue;
        const cx = rect.left + rect.width / 2, cy = rect.top + rect.height / 2;
        if (cx < mark.x - 4 || cx > mark.x + mark.width + 4 || cy < mark.y - 4 || cy > mark.y + mark.height + 4) continue;
        const pageNumber = Number(span.closest('[data-page-number]')?.dataset.pageNumber || 0);
        if (!perPage.has(pageNumber)) perPage.set(pageNumber, []);
        perPage.get(pageNumber).push({ text: span.textContent, rect });
      }
      for (const [pageNumber, spans] of perPage) {
        spans.sort((a, b) => (Math.abs(a.rect.top - b.rect.top) > 4 ? a.rect.top - b.rect.top : a.rect.left - b.rect.left));
        let text = '', lastTop = null, lastRight = null;
        for (const item of spans) {
          if (lastTop !== null && Math.abs(item.rect.top - lastTop) > 4) text += '\n';
          else if (lastRight !== null && item.rect.left - lastRight > 3 && !text.endsWith(' ')) text += ' ';
          text += item.text; lastTop = item.rect.top; lastRight = item.rect.right;
        }
        text = text.replace(/[ \t]+/g, ' ').trim();
        if (!text) continue;
        const x = Math.max(mark.x, Math.min(...spans.map(i => i.rect.left))), y = Math.max(mark.y, Math.min(...spans.map(i => i.rect.top)));
        const right = Math.min(mark.x + mark.width, Math.max(...spans.map(i => i.rect.right))), bottom = Math.min(mark.y + mark.height, Math.max(...spans.map(i => i.rect.bottom)));
        blocks.push({ id: 'pdf-' + index + '-' + pageNumber, type: 'pdf-text', page: pageNumber, text: text.slice(0, 1600), score: 1, bbox: { x, y, width: right - x, height: bottom - y } });
      }
    }
    return blocks;
  }

  /* Submit ------------------------------------------------------------------ */
  const FRIENDLY = {
    AUTH_REQUIRED: 'Sign in from the extension icon to continue.',
    RATE_LIMITED: 'Daily limit reached. Sign in from the extension icon for more asks.',
    COST_CAP: 'Today\'s answer budget is used up. Try again tomorrow or switch to Power mode with a local model.',
    CLIENT_OUTDATED: 'Please update the extension (chrome://extensions → Update).',
    BLOCKED: 'Point & Ask stays off on this site.',
  };

  async function submit(input, thread, sendButton) {
    const question = input.value.trim();
    if (!question || state.busy || !state.marks.length) return;
    state.busy = true; sendButton.disabled = true; input.value = '';
    const pinnedTarget = state.pinTarget;
    state.pinTarget = null;
    thread.append(el('div', { class: 'q' }, [question]));
    const answerNode = el('div', { class: 'a' }, ['Looking at what you marked…']);
    const textNode = document.createTextNode(''); const statusNode = el('small', {}, ['']);
    thread.append(answerNode); thread.scrollTop = thread.scrollHeight;
    const requestId = ++state.requestId;
    let streamed = false;
    state.onDelta = (id, text) => { if (id !== requestId) return; if (!streamed) { answerNode.textContent = ''; answerNode.append(textNode, statusNode); streamed = true; } textNode.data += text; thread.scrollTop = thread.scrollHeight; };
    state.onStatus = (id, data) => { if (id === requestId && !streamed) answerNode.textContent = (data.anchors ? 'Found ' + data.anchors + ' thing' + (data.anchors === 1 ? '' : 's') + ' under your mark, ' : '') + 'thinking…'; };
    try {
      const marks = state.marks.map(m => ({ ...m }));
      const box = unionBox(marks);
      const anchors = collectAnchors(marks);
      toolbar.style.visibility = 'hidden'; panel.style.visibility = 'hidden';
      await new Promise(r => requestAnimationFrame(() => setTimeout(r, 30)));
      const capture = await send({ type: 'spatial:capture', box, dpr: window.devicePixelRatio || 1 });
      toolbar.style.visibility = ''; panel.style.visibility = '';
      const viewer = window.__spatialViewer || null;
      const payload = {
        question, marks, anchors, context_id: state.contextId, research: state.settings.research !== false,
        system_one: state.settings.systemOne === true, level: state.settings.level || 'student',
        canvas: { width: window.innerWidth, height: window.innerHeight },
        page: { url: viewer ? viewer.fileUrl : location.href, title: (viewer ? viewer.title : document.title || location.hostname).slice(0, 500), surface: viewer ? 'pdf' : 'web' },
        image_data: capture.ok ? capture.image : null,
        crop: capture.ok ? capture.crop : null,
        target_id: pinnedTarget,
      };
      const response = await send({ type: 'spatial:ask-stream', payload, requestId });
      if (!response.ok) throw response;
      const result = response.result;
      state.contextId = result.id;
      answerNode.textContent = ''; answerNode.append(document.createTextNode(result.answer));
      const used = (result.anchors_used || []).length;
      const pages = new Set();
      for (const a of result.anchors_used || []) if (a.page) pages.add(a.page); // pdf.js page numbers are already 1-based
      const note = [result.provider && result.provider !== 'none' ? result.provider + '/' + result.model : 'no model configured',
                    used ? used + ' anchor' + (used === 1 ? '' : 's') : 'no text found',
                    result.vision ? 'crop seen' : (result.ocr ? 'OCR' : (capture.image ? 'crop ignored' : 'no crop')),
                    Math.round((result.confidence || 0) * 100) + '% confidence'];
      if (result.sources && result.sources.length) note.push(result.sources.length + ' sources, ' + (result.cited || []).length + ' cited');
      if (result.diagram) note.push('diagram mode: no text under mark, read the image');
      if (result.level && result.level !== 'student') note.push(result.level.toUpperCase());
      if (pages.size) note.push('page' + (pages.size > 1 ? 's ' : ' ') + Array.from(pages).sort((a,b)=>a-b).join(', '));
      if (result.note) note.push(result.note);
      if (!pinnedTarget && result.confirmation_required && !(result.clarify || []).length) note.push('low confidence – circle tighter?');
      answerNode.append(el('small', {}, [note.join(' · ')]));
      const actions = el('div', { class: 'actions' });
      answerNode.append(actions);
      const speaker = attachSpeaker(actions, result.answer);
      if ((result.sources || []).length) {
        const cited = new Set(result.cited || []);
        const unsupported = new Set(result.unsupported_citations || []);
        const list = el('div', { class: 'sources' });
        for (const source of result.sources) list.append(el('a', { href: source.url, target: '_blank', rel: 'noopener', class: (cited.has(source.id) ? 'cited' : '') + (unsupported.has(source.id) ? ' unsupported' : ''), title: source.url + (unsupported.has(source.id) ? ' — the cited passage does not support the sentence' : '') }, ['[' + source.id + '] ' + source.title]));
        answerNode.insertBefore(list, answerNode.querySelector('small'));
      }
      highlightAnchors(result.anchors_used);
      if ((result.clarify || []).length >= 2) attachClarify(answerNode, result.clarify, question, input, thread, sendButton);
      if (state.settings.readAloud) speaker.click();
    } catch (error) {
      answerNode.className = 'a err';
      const code = error && error.code;
      answerNode.textContent = FRIENDLY[code] || error.error || error.message || String(error);
      if (code) answerNode.append(el('small', {}, [code]));
      toolbar.style.visibility = ''; if (panel) panel.style.visibility = '';
    } finally {
      state.busy = false; sendButton.disabled = false; thread.scrollTop = thread.scrollHeight; input.focus();
    }
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (!message || !message.type) return;
    if (message.type === 'spatial:bridge-collect') {
      const mapped = window.SpatialBridgeGeometry.map(message.region, message.monitor, message.window.rect, {
        dpr: window.devicePixelRatio || 1, innerWidth: window.innerWidth, innerHeight: window.innerHeight,
        outerWidth: window.outerWidth, outerHeight: window.outerHeight,
      });
      const candidates = mapped ? collectAnchors([mapped.mark]).filter((a) =>
        G.anchorFilter(a.bbox, mapped.mark, { width: window.innerWidth, height: window.innerHeight })).slice(0, 12).map((a) => ({
        candidate_id: 'dom-' + a.id, source: a.page ? 'pdf_text' : 'dom', object_type: a.type,
        text: (a.text || '').slice(0, 800), bbox: mapped.toMonitor(a.bbox), page: a.page || null,
        href: /^https?:\/\//.test(a.href || '') ? a.href.slice(0, 500) : null,
        src: /^https?:\/\//.test(a.src || '') ? a.src.slice(0, 500) : null,
        provenance: { extractor: 'chrome-dom', extractor_version: '1' },
      })) : [];
      sendResponse({ candidates });
    } else if (message.type === 'spatial:toggle') {
      state.consent = message.consent !== false;
      if (state.open) close(); else open();
      sendResponse({ ok: true, open: state.open });
    } else if (message.type === 'spatial:delta') state.onDelta && state.onDelta(message.requestId, message.text);
    else if (message.type === 'spatial:status') state.onStatus && state.onStatus(message.requestId, message);
  });
  window.__spatialSpatialToggle = () => (state.open ? close() : open());
})();
