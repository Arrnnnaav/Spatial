/* Runs only on the dashboard origins listed in manifest.json: lets the web app know the extension is installed
   so it can hide the "install" card and show the live hotkey instead. */
document.documentElement.dataset.pointAskExtension = chrome.runtime.getManifest().version;
window.addEventListener('message', event => {
  if (event.source === window && event.data && event.data.type === 'point-ask:ping') {
    window.postMessage({ type: 'point-ask:pong', version: chrome.runtime.getManifest().version }, '*');
  }
});
