const out = document.getElementById("out");
const statusEl = document.getElementById("status");
const MOCK = new URLSearchParams(location.search).has("mock");

// [label, dotted path into normalized, optional formatter]; null/empty => "Not found on page".
const FIELDS = [
  ["Product name", "identity.product_name"],
  ["Type", "identity.product_type"],
  ["Language", "source.language"],
  ["Materials", "materials.material_percentages", (v) =>
    Object.entries(v).map(([m, p]) => `${m} ${p}%`).join(", ")],
  ["Fit", "fit_and_style.fit"],
  ["Sleeve", "fit_and_style.sleeve_length"],
  ["Neckline", "fit_and_style.neckline"],
  ["Colors", "variants.colors", (v) => v.map((c) => c.original_color_name).join(", ")],
  ["Sizes", "variants.sizes", (v) => v.map((s) => s.raw_size).join(", ")],
  ["Price", "commerce.price"],
  ["Currency", "commerce.currency"],
];

const get = (obj, path) => path.split(".").reduce((o, k) => (o == null ? o : o[k]), obj);

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  Object.assign(e, attrs);
  e.append(...kids);
  return e;
}

function showError(text) {
  out.replaceChildren(el("div", { className: "error", textContent: text }));
}

function render(data) {
  const n = data.normalized || {};
  const evidence = data.evidence || n.evidence || [];
  const facts = el("dl");
  const missing = [];

  for (const [label, path, fmt] of FIELDS) {
    let v = get(n, path);
    if (v == null && path === "source.language") v = data.language;
    if (v != null && fmt) v = fmt(v);
    if (v == null || v === "") { missing.push(label); continue; }
    const ev = evidence.filter((e) => e.field === path || e.field.startsWith(path + "."));
    const dd = el("dd");
    if (ev.length) {
      const d = el("details", {}, el("summary", {
        textContent: String(v),
        title: ev.map((e) => e.source_text).join("\n---\n"),
      }));
      for (const e of ev) {
        d.append(el("div", {
          className: "ev",
          textContent: `${e.source_text}\n(${e.source_location}, ${e.method}, conf ${e.confidence})`,
        }));
      }
      dd.append(d);
    } else {
      dd.append(el("span", { textContent: String(v) }), el("span", { className: "muted", textContent: " (no evidence)" }));
    }
    facts.append(el("dt", { textContent: label }), dd);
  }

  const q = data.quality_status || n.quality_status || "unknown";
  const parts = [
    el("h2", { textContent: "Overview " }, el("span", { className: `badge q-${q}`, textContent: `quality: ${q}` })),
    facts,
  ];
  if (missing.length) {
    parts.push(el("h2", { textContent: "Not found on page" }),
      el("ul", { className: "missing" }, ...missing.map((m) => el("li", { textContent: m }))));
  }
  const conflicts = data.conflicts || [];
  if (conflicts.length) {
    parts.push(el("h2", { textContent: `Conflicts (${conflicts.length})` }),
      el("ul", {}, ...conflicts.map((c) => el("li", {
        textContent: `${c.field}: ${(c.observations || []).map((o) => o.value).join(" vs ")}`,
      }))));
  }
  out.replaceChildren(...parts);
}

async function audit() {
  out.replaceChildren();
  statusEl.textContent = "Auditing...";
  try {
    if (MOCK) {
      render(await (await fetch("mock.json")).json());
      statusEl.textContent = "Mock data (mock.json)";
      return;
    }
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !/^https?:/.test(tab.url || "")) throw new Error("Open a product page (http/https) first.");
    const apiBase = await getApiBase();
    let res;
    try {
      res = await fetch(`${apiBase}/v1/extract`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url: tab.url }),
      });
    } catch (e) {
      throw new Error(`Cannot reach API at ${apiBase}. Is it running? Check Settings.\n${e.message}`);
    }
    const body = await res.text();
    if (!res.ok) throw new Error(`API error ${res.status}: ${body.slice(0, 300)}`);
    let data;
    try { data = JSON.parse(body); } catch { throw new Error("API returned invalid JSON."); }
    statusEl.textContent = tab.url;
    render(data);
    if (data.product_id && /^https?:\/\//.test(apiBase)) {
      const href = `${apiBase}/dashboard/?product=${encodeURIComponent(data.product_id)}#product`;
      out.prepend(el("a", { href, target: "_blank", rel: "noopener", textContent: "Open in dashboard" }));
    }
  } catch (e) {
    statusEl.textContent = "";
    showError(e.message);
  }
}

// Profile context (TEAM-45): with an access key, show the company and save the page to the merchant's report.
const who = document.getElementById("who");
const saveBtn = document.getElementById("save");

async function profileFetch(path, init = {}) {
  const [apiBase, token] = await Promise.all([getApiBase(), getProfileToken()]);
  const res = await fetch(`${apiBase}${path}`, {
    ...init, headers: { "Content-Type": "application/json", "X-Profile-Token": token },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(`API error ${res.status}: ${String(body.detail || "").slice(0, 200)}`);
  return body;
}

async function loadProfile() {
  if (MOCK || !(await getProfileToken())) return;
  try {
    const p = await profileFetch("/v1/profile");
    who.textContent = `Signed in: ${p.company.name}`;
    saveBtn.hidden = false;
  } catch {
    who.textContent = "Access key not recognised. Check Settings.";
  }
}

saveBtn.addEventListener("click", async () => {
  statusEl.textContent = "Saving to your report...";
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !/^https?:/.test(tab.url || "")) throw new Error("Open a product page (http/https) first.");
    const p = await profileFetch("/v1/profile/products", { method: "POST", body: JSON.stringify({ url: tab.url }) });
    statusEl.textContent = "Saved. Auditing...";
    const a = await profileFetch(`/v1/profile/products/${p.id}/audit`, { method: "POST" });
    const r = a.audit && a.audit.rank;
    statusEl.textContent = r ? `Saved to your report: #${r.position} of ${r.total} comparable shirts.` : "Saved to your report.";
  } catch (e) {
    statusEl.textContent = "";
    showError(e.message);
  }
});

document.getElementById("audit").addEventListener("click", audit);
loadProfile();
if (MOCK) audit();
