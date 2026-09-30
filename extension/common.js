const DEFAULT_API_BASE = "http://localhost:8000";

function getApiBase() {
  return new Promise((resolve) => {
    if (!globalThis.chrome || !chrome.storage) return resolve(DEFAULT_API_BASE);
    chrome.storage.sync.get({ apiBase: DEFAULT_API_BASE }, (v) => resolve(v.apiBase || DEFAULT_API_BASE));
  });
}

// Profile access key (TEAM-45): kept in chrome.storage.local (this device only, never synced).
function getProfileToken() {
  return new Promise((resolve) => {
    if (!globalThis.chrome || !chrome.storage) return resolve("");
    chrome.storage.local.get({ profileToken: "" }, (v) => resolve(v.profileToken || ""));
  });
}
