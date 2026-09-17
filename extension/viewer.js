/* Minimal pdf.js viewer: every page rendered to a canvas with a text layer, so the Point & Ask
   overlay (content.js, loaded on this page directly) gets real text anchors with page numbers. */
import * as pdfjsLib from './vendor/pdf.min.mjs';

// Outside the extension (dev harness) fall back to a relative URL.
const assetUrl = path => (globalThis.chrome && chrome.runtime && chrome.runtime.getURL ? chrome.runtime.getURL(path) : new URL(path, location.href).href);
pdfjsLib.GlobalWorkerOptions.workerSrc = assetUrl('vendor/pdf.worker.min.mjs');

const params = new URLSearchParams(location.search);
const fileUrl = params.get('file') || '';
const titleNode = document.getElementById('title');
const countNode = document.getElementById('count');
const statusNode = document.getElementById('status');
const pagesNode = document.getElementById('pages');

document.getElementById('mark').onclick = () => window.__spatialSpatialToggle && window.__spatialSpatialToggle();

function fileName(url) {
  try { return decodeURIComponent(new URL(url).pathname.split('/').pop() || url); } catch (_) { return url; }
}

async function load() {
  if (!fileUrl) { statusNode.textContent = 'No PDF given. Open a .pdf link and it will appear here.'; return; }
  const name = fileName(fileUrl);
  document.title = name + ' · ' + (window.SPATIAL_CONFIG ? window.SPATIAL_CONFIG.productName : 'Point & Ask');
  titleNode.textContent = name;
  titleNode.title = fileUrl;
  window.__spatialViewer = { fileUrl, title: name };
  let data;
  try {
    const response = await fetch(fileUrl);
    if (!response.ok) throw new Error('HTTP ' + response.status);
    data = await response.arrayBuffer();
  } catch (error) {
    statusNode.innerHTML = fileUrl.startsWith('file:')
      ? 'Cannot read this local file. Enable <b>Allow access to file URLs</b> for Spatial Point &amp; Ask at <a href="#" id="ext">chrome://extensions</a>, then reload.'
      : 'Could not fetch the PDF (' + (error.message || error) + '). <a href="' + fileUrl + '" id="raw">Open it directly</a>.';
    const ext = document.getElementById('ext');
    if (ext) ext.onclick = e => { e.preventDefault(); chrome.tabs.create({ url: 'chrome://extensions/?id=' + chrome.runtime.id }); };
    return;
  }
  const pdf = await pdfjsLib.getDocument({ data }).promise;
  countNode.textContent = pdf.numPages + (pdf.numPages === 1 ? ' page' : ' pages');
  const scale = Math.min(1.6, Math.max(1, (window.innerWidth - 80) / 820));
  for (let number = 1; number <= pdf.numPages; number++) {
    const page = await pdf.getPage(number);
    const viewport = page.getViewport({ scale });
    const wrapper = document.createElement('div');
    wrapper.className = 'page'; wrapper.dataset.pageNumber = String(number);
    wrapper.style.width = viewport.width + 'px'; wrapper.style.height = viewport.height + 'px';
    const canvas = document.createElement('canvas');
    const ratio = window.devicePixelRatio || 1;
    canvas.width = Math.floor(viewport.width * ratio); canvas.height = Math.floor(viewport.height * ratio);
    canvas.style.width = viewport.width + 'px'; canvas.style.height = viewport.height + 'px';
    const textLayer = document.createElement('div');
    textLayer.className = 'textLayer';
    wrapper.append(canvas, textLayer);
    pagesNode.append(wrapper);
    await page.render({ canvasContext: canvas.getContext('2d'), viewport, transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : null }).promise;
    textLayer.style.setProperty('--scale-factor', String(scale));
    await new pdfjsLib.TextLayer({ textContentSource: page.streamTextContent(), container: textLayer, viewport }).render();
  }
}

load().catch(error => { statusNode.textContent = 'Failed to render PDF: ' + (error.message || error); });
