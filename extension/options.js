const $ = (id) => document.getElementById(id);
const msg = $("msg");

getSettings().then((s) => {
  const T = STR[pickLang(s.lang)];
  $("title").textContent = T.settings;
  $("lApi").textContent = T.oApi;
  $("lToken").textContent = T.oToken;
  $("tokenHelp").textContent = T.oTokenHelp;
  $("lLang").textContent = T.oLang;
  $("oAuto").textContent = T.oAuto;
  $("save").textContent = T.save;
  $("apiBase").value = s.apiBase;
  $("token").value = s.token;
  $("lang").value = s.lang;

  $("save").addEventListener("click", async () => {
    let url;
    try {
      url = new URL($("apiBase").value.trim() || DEFAULTS.apiBase);
      if (!/^https?:$/.test(url.protocol)) throw new Error();
    } catch {
      msg.textContent = T.badUrl;
      return;
    }
    const apiBase = url.origin + url.pathname.replace(/\/+$/, "");
    // Optional host access for this API origin only; must run inside the click gesture.
    const granted = await chrome.permissions.request({ origins: [url.origin + "/*"] });
    if (!granted) {
      msg.textContent = T.denied;
      return;
    }
    const token = $("token").value.trim();
    chrome.storage.local.set({ apiBase, token, lang: $("lang").value }, () => {
      $("apiBase").value = apiBase;
      msg.textContent = T.saved;
    });
  });
});
