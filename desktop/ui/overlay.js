/* Freeze-frame overlay: shows the captured monitor, lets the user mark it (pen / box / point), then hides itself
   BEFORE the panel asks the server for candidates (UIA reads what is on screen under the mark, not us). */
(function () {
  'use strict';
  const T = window.__TAURI__;
  const win = T.window.getCurrentWindow();
  const G = window.SpatialGeometry;
  const frame = document.getElementById('frame');
  const ink = document.getElementById('ink');
  const verb = document.getElementById('verb');
  const NS = 'http://www.w3.org/2000/svg';
  let capture = null;
  let tool = 'pen';
  let stroke = null;
  let busy = false;

  T.event.listen('spatial://start', start);

  async function start() {
    if (busy) return;
    busy = true;
    try {
      const panel = await T.webviewWindow.WebviewWindow.getByLabel('panel');
      if (panel) await panel.hide(); // keep the previous answer out of the frozen frame
      capture = await Spatial.post('/api/desktop/capture', {});
      frame.src = capture.image_data;
      await frame.decode().catch(() => {});
      ink.replaceChildren();
      setTool('pen');
      const m = capture.monitor;
      await win.setPosition(new T.dpi.PhysicalPosition(m.x, m.y));
      await win.setSize(new T.dpi.PhysicalSize(m.width, m.height));
      await win.show();
      await win.setFocus();
    } catch (err) {
      await T.event.emitTo('panel', 'spatial://error', { message: String((err && err.message) || err) });
    } finally {
      busy = false;
    }
  }

  function setTool(next) {
    tool = next;
    verb.textContent = { pen: 'Circle', box: 'Drag a box around', point: 'Click' }[tool];
  }

  async function cancel() {
    stroke = null;
    ink.replaceChildren();
    await win.hide();
  }

  // Monitor pixels = CSS px * devicePixelRatio (the window covers exactly the captured monitor).
  function toMonitor(event) {
    const k = window.devicePixelRatio || 1;
    return [event.clientX * k, event.clientY * k];
  }

  window.addEventListener('keydown', (event) => {
    const key = event.key.toLowerCase();
    if (key === 'escape') cancel();
    else if (key === 'b') setTool('box');
    else if (key === 'p' || key === '.') setTool('point');
    else if (key === 'c') setTool('pen');
  });

  ink.addEventListener('pointerdown', (event) => {
    if (!capture) return;
    ink.setPointerCapture(event.pointerId);
    ink.replaceChildren();
    stroke = { start: [event.clientX, event.clientY], points: [[event.clientX, event.clientY]], raw: [toMonitor(event)] };
    if (tool === 'pen') stroke.node = document.createElementNS(NS, 'path');
    else if (tool === 'box') stroke.node = document.createElementNS(NS, 'rect');
    if (stroke.node) ink.append(stroke.node);
  });

  ink.addEventListener('pointermove', (event) => {
    if (!stroke) return;
    stroke.points.push([event.clientX, event.clientY]);
    stroke.raw.push(toMonitor(event));
    if (tool === 'pen') {
      stroke.node.setAttribute('d', 'M' + stroke.points.map((p) => p.join(' ')).join(' L'));
    } else if (tool === 'box') {
      const [x0, y0] = stroke.start;
      stroke.node.setAttribute('x', Math.min(x0, event.clientX));
      stroke.node.setAttribute('y', Math.min(y0, event.clientY));
      stroke.node.setAttribute('width', Math.abs(event.clientX - x0));
      stroke.node.setAttribute('height', Math.abs(event.clientY - y0));
    }
  });

  ink.addEventListener('pointerup', async (event) => {
    if (!stroke) return;
    const raw = stroke.raw.concat([toMonitor(event)]);
    const first = raw[0];
    const last = raw[raw.length - 1];
    const travel = Math.max(...raw.map((p) => Math.hypot(p[0] - first[0], p[1] - first[1])));
    stroke = null;
    let mark;
    if (tool === 'point' || travel < 6) {
      mark = { kind: 'point', role: 'reference', bbox: { x: Math.round(last[0]), y: Math.round(last[1]), width: 0, height: 0 } };
      const dot = document.createElementNS(NS, 'circle');
      dot.setAttribute('cx', event.clientX);
      dot.setAttribute('cy', event.clientY);
      dot.setAttribute('r', 7);
      ink.append(dot);
    } else if (tool === 'box') {
      const m = G.shapeToMark('rectangle', first.map(Math.round), last.map(Math.round));
      mark = { kind: 'rectangle', role: 'reference', bbox: { x: m.x, y: m.y, width: m.width, height: m.height } };
    } else {
      const m = G.strokeToMark(raw);
      mark = { kind: 'polygon', role: 'reference', closed: m.closed, points: m.points.slice(0, 2000),
               bbox: { x: m.x, y: m.y, width: m.width, height: m.height } };
    }
    await new Promise((resolve) => setTimeout(resolve, 120)); // let the user see their mark
    await win.hide();
    await new Promise((resolve) => setTimeout(resolve, 80)); // DWM repaint before UIA probes the screen
    ink.replaceChildren();
    await T.event.emitTo('panel', 'spatial://mark', { capture_id: capture.capture_id, monitor: capture.monitor, mark });
  });
})();
