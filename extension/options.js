const input = document.getElementById("apiBase");
const msg = document.getElementById("msg");

const tokenInput = document.getElementById("token");
getApiBase().then((v) => { input.value = v; });
getProfileToken().then((v) => { tokenInput.value = v; });

document.getElementById("forget").addEventListener("click", () => {
  chrome.storage.local.remove("profileToken", () => { tokenInput.value = ""; msg.textContent = "Key removed from this device."; });
});

document.getElementById("save").addEventListener("click", async () => {
  let url;
  try {
    url = new URL(input.value.trim() || DEFAULT_API_BASE);
    if (!/^https?:$/.test(url.protocol)) throw new Error();
  } catch {
    msg.textContent = "Enter a valid http(s) URL.";
    return;
  }
  const apiBase = url.origin + url.pathname.replace(/\/+$/, "");
  // Request host access for this origin only (must run inside the click gesture).
  const granted = await chrome.permissions.request({ origins: [url.origin + "/*"] });
  if (!granted) {
    msg.textContent = "Host permission denied; requests to this API will fail.";
    return;
  }
  chrome.storage.local.set({ profileToken: tokenInput.value.trim() });
  chrome.storage.sync.set({ apiBase }, () => {
    input.value = apiBase;
    msg.textContent = "Saved.";
  });
});
