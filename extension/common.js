const DEFAULT_API_BASE = "http://localhost:8000";

function getApiBase() {
  return new Promise((resolve) => {
    if (!globalThis.chrome || !chrome.storage) return resolve(DEFAULT_API_BASE);
    chrome.storage.sync.get({ apiBase: DEFAULT_API_BASE }, (v) => resolve(v.apiBase || DEFAULT_API_BASE));
  });
}
