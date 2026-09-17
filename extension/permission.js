navigator.mediaDevices.getUserMedia({ audio: true }).then(stream => {
  stream.getTracks().forEach(track => track.stop());
  document.getElementById('status').textContent = 'Microphone allowed. You can close this tab and press 🎤 again.';
  setTimeout(() => window.close(), 1500);
}).catch(error => {
  document.getElementById('status').textContent = 'Not allowed (' + error.name + '). Click the lock icon in the address bar to change it, then reload this page.';
});
