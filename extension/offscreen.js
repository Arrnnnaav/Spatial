/* Offscreen document: records the microphone for server transcription. Lives on the extension origin, so the
   user grants the mic once (permission.html) instead of once per website. */
let recorder = null, chunks = [], stream = null;

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || !message.type || !message.type.startsWith('offscreen:')) return false;
  (async () => {
    try {
      if (message.type === 'offscreen:start') {
        try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
        catch (error) { return sendResponse({ ok: false, code: error.name === 'NotAllowedError' ? 'MIC_PERMISSION' : 'MIC_ERROR', error: 'Microphone not available: ' + error.message }); }
        const mimeType = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus'].find(type => MediaRecorder.isTypeSupported(type)) || '';
        recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined); chunks = [];
        recorder.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
        recorder.start();
        return sendResponse({ ok: true });
      }
      if (message.type === 'offscreen:stop') {
        if (!recorder) return sendResponse({ ok: false, error: 'not recording' });
        const done = new Promise(resolve => { recorder.onstop = resolve; });
        recorder.stop(); await done;
        stream.getTracks().forEach(track => track.stop());
        const blob = new Blob(chunks, { type: recorder.mimeType || 'audio/webm' });
        recorder = null; stream = null;
        const audio = await new Promise(resolve => { const reader = new FileReader(); reader.onload = () => resolve(reader.result); reader.readAsDataURL(blob); });
        return sendResponse({ ok: true, audio, mimeType: blob.type });
      }
      sendResponse({ ok: false, error: 'unknown' });
    } catch (error) { sendResponse({ ok: false, error: error.message || String(error) }); }
  })();
  return true;
});
