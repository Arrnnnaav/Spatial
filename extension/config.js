/* Build-time configuration for the Spatial extension: server URL, API paths and feature flags. */
(function (root) {
  root.SPATIAL_CONFIG = {
    productName: 'Spatial Point & Ask',
    apiBase: 'http://127.0.0.1:8787',
    paths: {
      ask: '/api/ask',
      stream: '/api/ask/stream',
      health: '/api/health',
      transcribe: '/api/stt',
      synthesize: '/api/tts',
      traceConfig: '/api/traces/config',
    },
    features: {
      providerPicker: true,    // self-hosters choose the provider
      powerMode: true,
    },
    protocolVersion: 2,
  };
})(typeof self !== 'undefined' ? self : this);
