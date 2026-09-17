/* Build-time configuration for the standalone Spatial extension. Every other extension file is synced
   verbatim from StudyOS (learning-platform/apps/extension) by scripts/sync_spatial.py. */
(function (root) {
  root.SPATIAL_CONFIG = {
    mode: 'standalone',
    productName: 'Spatial Point & Ask',
    apiBase: 'http://127.0.0.1:8787',
    dashboardUrl: '',
    paths: {
      ask: '/api/ask',
      stream: '/api/ask/stream',
      health: '/api/health',
      transcribe: '/api/stt',
      synthesize: '/api/tts',
      login: '',
      register: '',
      quiz: '',
    },
    features: {
      accounts: false,         // single-user local server, optional shared token instead
      quizLater: false,        // no review queue in the standalone product
      providerPicker: true,    // self-hosters choose the provider
      powerMode: true,
    },
    anonymousDailyLimit: 0,
    protocolVersion: 2,
  };
})(typeof self !== 'undefined' ? self : this);
