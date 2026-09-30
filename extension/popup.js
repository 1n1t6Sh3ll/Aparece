// Popup: POST {apiBase}/v1/audit {url}; if the store blocks the API or it's Amazon, offer a draft audit built
// from the tab's visible title + description (read only when the user clicks). All text is set via textContent.
const out = document.getElementById("out");
const statusEl = document.getElementById("status");
const auditBtn = document.getElementById("audit");
const draftBtn = document.getElementById("draft");
const MOCK = new URLSearchParams(location.search).has("mock");
let S = DEFAULTS, T = STR.en, LANG = "en";

const isAmazon = (u) => /(^|\.)amazon\.[a-z.]+$/i.test(new URL(u).hostname);

function show(msg, cls = "muted") {
  statusEl.className = cls;
  statusEl.textContent = msg || "";
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !/^https?:/.test(tab.url || "")) throw new Error(T.needPage);
  return tab;
}

async function post(body) {
  const headers = { "Content-Type": "application/json" };
  if (S.token) headers["X-Profile-Token"] = S.token;
  let res;
  try {
    res = await fetch(`${S.apiBase}/v1/audit`, { method: "POST", headers, body: JSON.stringify(body) });
  } catch {
    throw Object.assign(new Error(T.unreachable(S.apiBase)), { network: true });
  }
  const text = await res.text();
  if (!res.ok) {
    let detail = text;
    try { detail = JSON.parse(text).detail ?? text; } catch { /* plain text */ }
    throw Object.assign(new Error(T.apiError(res.status, String(detail).slice(0, 300))), { status: res.status });
  }
  try { return JSON.parse(text); } catch { throw new Error(T.badJson); }
}

// Runs in the page (chrome.scripting, activeTab) on click only. innerText returns rendered, visible text.
function readVisibleListing() {
  const q = (s) => document.querySelector(s);
  const txt = (e) => (e && e.innerText ? e.innerText.replace(/[ \t]+/g, " ").replace(/\n{3,}/g, "\n\n").trim() : "");
  const meta = (n) => ((q(`meta[property="${n}"]`) || q(`meta[name="${n}"]`) || {}).content || "").trim();
  const title = txt(q("#productTitle")) || txt(q("h1")) || meta("og:title") || document.title.trim();
  const parts = ["#feature-bullets", "#productFactsDesktopExpander", "#productOverview_feature_div", "#productDescription",
    "#detailBullets_feature_div", "[itemprop=description]", ".product__description", ".product-description",
    ".product-single__description"].map((s) => txt(q(s))).filter(Boolean);
  if (!parts.length) parts.push(meta("og:description") || meta("description"));
  // Amazon renders the displayed price split into spans; .a-offscreen holds the same price as one string.
  const price = (q("#corePrice_feature_div .a-offscreen, #corePriceDisplay_desktop_feature_div .a-offscreen") || {}).textContent || "";
  const lang = (document.documentElement.lang || "").slice(0, 2).toLowerCase();
  return { title: title.slice(0, 500), description: [...new Set(parts)].join("\n\n").slice(0, 20000),
    price: String(price).trim().slice(0, 40), language: lang || null };
}

async function auditUrl() {
  draftBtn.hidden = true;
  out.replaceChildren();
  try {
    if (MOCK) return render(await (await fetch("mock.json")).json(), { url: null }), show(T.mock);
    const tab = await activeTab();
    if (isAmazon(tab.url)) return offerDraft(T.amazon);
    show(T.auditing);
    const data = await post({ url: tab.url });
    show("");
    render(data, { url: tab.url });
  } catch (e) {
    if (e.status && e.status >= 403) return offerDraft(`${e.message}\n\n${T.blocked}`);
    show(e.message, "error");
  }
}

function offerDraft(msg) {
  show(msg, "notice");
  draftBtn.hidden = false;
  draftBtn.focus();
}

async function auditDraft() {
  out.replaceChildren();
  try {
    const tab = await activeTab();
    show(T.reading);
    const [{ result: d } = {}] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func: readVisibleListing });
    if (!d || !d.title) throw new Error(T.noTitle);
    const body = { title: d.title, description: d.price ? `${d.description}\n\nPrice: ${d.price}` : d.description };
    if (d.language) body.language = d.language;
    show(T.auditing);
    const data = await post(body);
    draftBtn.hidden = true;
    show(T.draftNote);
    render(data, { url: null });
  } catch (e) {
    show(e.message, "error");
  }
}

function section(title, ...kids) {
  return el("section", {}, el("h2", { textContent: title }), ...kids);
}

// Title and evidence are rendered from kind + field + evidence numbers so they follow the popup language.
function actionItem(a) {
  const lbl = LANG === "es" ? (LABEL_ES[a.field] || labelFor(a.field)) : labelFor(a.field);
  const make = a.kind === "missing_attribute" && a.evidence && a.evidence.readable ? T.act.readable : T.act[a.kind];
  const title = make ? make(lbl) : a.title;
  const ev = T.ev[a.kind] ? T.ev[a.kind](a.evidence || {}) : a.why;
  return el("li", {}, el("details", {},
    el("summary", { textContent: title }),
    el("p", { class: "ev", textContent: ev }),
    a.seo_note && LANG === "en" ? el("p", { class: "ev muted", textContent: a.seo_note }) : null));
}

let LABELS_EN = {};
const labelFor = (f) => String(LABELS_EN[f] || f || "").toLowerCase();
const cap = (s) => String(s).charAt(0).toUpperCase() + String(s).slice(1);

function render(data, { url }) {
  LABELS_EN = Object.fromEntries([...(data.not_found || []), ...(data.facts || [])].map((x) => [x.field, x.label]));
  Object.assign(LABELS_EN, (data.table && data.table.labels) || {});
  const p = data.product || {};
  const r = data.rank || {};
  const kind = T.shirts;
  const parts = [];

  parts.push(el("div", { class: "product" },
    el("div", { class: "ptitle", textContent: p.title || "—" }),
    el("div", { class: "muted", textContent: [p.brand, p.merchant].filter(Boolean).join(" · ") })));

  const peers = (r.total || 0) > 1;
  parts.push(section(T.rankHead,
    el("p", { class: "rank", textContent: peers ? T.rank(r.position, r.total, kind) : T.noPeers(kind) }),
    peers && r.score != null ? el("p", { class: "muted small", textContent: T.score(r.score) }) : null));

  const acts = (data.actions || []).slice(0, 3);
  parts.push(section(T.fixHead, acts.length ? el("ol", { class: "fixes" }, ...acts.map(actionItem))
    : el("p", { class: "muted", textContent: T.noFix })));

  const missing = (data.not_found || []).filter((m) => m.peers_with > 0).slice(0, 5);
  if (missing.length) {
    parts.push(section(T.missingHead,
      el("ul", { class: "missing" }, ...missing.map((m) => el("li", {},
        el("span", { textContent: cap(LANG === "es" ? (LABEL_ES[m.field] || m.label) : m.label) }),
        el("span", { class: "muted small", textContent: ` · ${T.missingOf(m.peers_with, m.of)}` })))),
      el("p", { class: "muted small", textContent: T.notFoundNote })));
  }

  const pp = data.price_position || {};
  parts.push(section(T.priceHead, pp.available
    ? el("p", {}, el("strong", { textContent: T.pos[pp.position] || pp.position }), el("br"),
      el("span", { class: "small", textContent: T.priceLine(pp.price, pp.currency, pp.p25, pp.p75, pp.median, pp.peer_count) }))
    : el("p", { class: "muted", textContent: T.noPrice })));

  parts.push(section(T.visHead, el("p", { class: "muted", textContent: T.visBody })));

  for (const n of data.notes || []) parts.push(el("p", { class: "muted small", textContent: n }));

  const base = S.apiBase.replace(/\/+$/, "");
  const links = el("div", { class: "links" });
  if (p.product_id) {
    links.append(el("a", { class: "button primary", target: "_blank", rel: "noopener",
      href: `${base}/#/compare?product=${encodeURIComponent(p.product_id)}`, textContent: T.compare }));
  }
  links.append(el("a", { class: "button secondary", target: "_blank", rel: "noopener",
    href: url ? `${base}/?url=${encodeURIComponent(url)}#/` : `${base}/#/`, textContent: T.report }));
  parts.push(links);

  out.replaceChildren(...parts);
}

async function init() {
  S = await getSettings();
  LANG = pickLang(S.lang);
  T = STR[LANG];
  document.documentElement.lang = LANG;
  document.getElementById("settings").textContent = T.settings;
  auditBtn.textContent = T.audit;
  draftBtn.textContent = T.draft;
  auditBtn.addEventListener("click", auditUrl);
  draftBtn.addEventListener("click", auditDraft);
  if (MOCK) auditUrl();
}

init();
