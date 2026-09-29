const input = document.getElementById("apiBase");
const msg = document.getElementById("msg");

getApiBase().then((v) => { input.value = v; });

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
  chrome.storage.sync.set({ apiBase }, () => {
    input.value = apiBase;
    msg.textContent = "Saved.";
  });
});
