"use strict";
// ProductLens dashboard. All text goes through textContent; no innerHTML.

const API = "/v1";
const LABELS = {
  OBSERVED_FACT: "Observed fact",
  SUPPORTED_HYPOTHESIS: "Supported hypothesis",
  UNKNOWN: "Unknown",
};
const FACT_SECTIONS = ["identity", "materials", "fit_and_style", "variants", "commerce"];
const SKIP_FACTS = new Set(["variants.items", "variants.product_group_id", "materials.fabric_weight_raw"]);

function el(tag, attrs, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "style") n.style.cssText = v;
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) {
    if (c === null || c === undefined || c === false) continue;
    n.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return n;
}

async function getJSON(path) {
  const r = await fetch(API + path);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

const fmt = (v) => (v === null || v === undefined || v === "" ? "—" : Array.isArray(v) ? v.join(", ") : String(v));
const pct = (v) => (typeof v === "number" ? `${(v * 100).toFixed(1)}%` : "—");
const money = (v, cur) => (typeof v === "number" ? `${v.toFixed(2)}${cur ? " " + cur : ""}` : "—");
// Merchant-readable names for schema keys and enum values; raw names stay in tooltips.
const NAMES = {
  brand: "Brand", product_name: "Product name", product_type: "Product type", subcategory: "Subcategory",
  audience: "Audience", full_description: "Description", primary_material: "Main material",
  material_percentages: "Material composition", fabric_type: "Fabric type", fabric_weight_gsm: "Fabric weight (GSM)",
  stretch: "Stretch", texture: "Texture", fit: "Fit", neckline: "Neckline", collar_type: "Collar",
  sleeve_length: "Sleeve length", shirt_length: "Length", pattern: "Pattern", style: "Style", colors: "Colours",
  sizes: "Sizes", variant_count: "Variant count", price: "Price", sale_price: "Sale price", currency: "Currency",
  availability: "Availability", rating: "Rating", review_count: "Reviews", sku: "SKU", gtin: "GTIN (barcode)",
  mpn: "MPN", product_schema_present: "Product structured data", offer_schema_present: "Offer structured data",
  product_group_present: "Variant group structured data", attribute_completeness: "Attribute completeness",
  description_chars: "Description length", attributes: "Attributes", price_band: "Price comparison",
  peers: "Comparable products", ranking_effect: "AI/search ranking effect", json_valid: "JSON valid",
  raw_full_description: "product description", raw_bullet_points: "bullet points", raw_title: "title",
  t_shirt: "T-shirt", polo_shirt: "Polo shirt", in_stock: "In stock", out_of_stock: "Out of stock",
  all_null_baseline: "All-null baseline", base_zero_shot: "Base model (zero-shot)", finetuned: "Fine-tuned",
};
const human = (s) => {
  const k = String(s);
  if (NAMES[k]) return NAMES[k];
  const t = k.replace(/_/g, " ");
  return t.charAt(0).toUpperCase() + t.slice(1);
};
const humanValue = (v) => (typeof v === "string" && NAMES[v]) || v;
// Replace raw snake_case keys inside analyzer sentences with readable names.
const humanText = (s) => String(s).replace(/\b[a-z]+(?:_[a-z]+)+\b/g, (w) => NAMES[w] || w);

function tile(label, value, sub) {
  return el("div", { class: "card tile" }, el("div", { class: "label" }, label),
    el("div", { class: "value" }, value), sub ? el("div", { class: "muted" }, sub) : null);
}

function barRow(name, value, max, text, cls) {
  const w = max > 0 ? Math.max(0, Math.min(100, (100 * value) / max)) : 0;
  return el("div", { class: "bar-row", title: `${name}: ${text}` },
    el("span", { class: "name" }, name),
    el("div", { class: "track", "aria-hidden": "true" }, el("div", { class: "fill " + (cls || ""), style: `width:${w}%` })),
    el("span", { class: "num" }, text));
}

function showError(target, err) {
  target.replaceChildren(el("div", { class: "card empty", role: "alert" }, `Could not load data (${err.message}).`));
}

/* ---------- Product view ---------- */

const results = document.getElementById("results");
const productBox = document.getElementById("product");

async function search(q) {
  try {
    const { results: rows } = await getJSON(`/products?q=${encodeURIComponent(q)}&limit=20`);
    results.replaceChildren(...(rows.length ? rows.map((r) => el("li", {},
      el("button", { type: "button", "data-id": r.product_id, "aria-pressed": "false" },
        el("span", {}, el("strong", {}, r.title || r.product_id), " ", el("span", { class: "muted" }, r.brand || "")),
        el("span", { class: "muted" }, [r.product_type && human(r.product_type), r.language, r.merchant].filter(Boolean).join(" · "))))) :
      [el("li", { class: "card empty" }, "No products found. The dataset may be empty.")]));
  } catch (e) { showError(results, e); }
}

results.addEventListener("click", (e) => {
  const b = e.target.closest("button[data-id]");
  if (!b) return;
  results.querySelectorAll("button[data-id]").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
  loadProduct(b.dataset.id);
});

document.getElementById("search").addEventListener("submit", (e) => {
  e.preventDefault();
  search(document.getElementById("q").value.trim());
});

async function loadProduct(id) {
  productBox.replaceChildren(el("p", { class: "muted" }, "Loading…"));
  try {
    const [p, g] = await Promise.all([getJSON(`/products/${encodeURIComponent(id)}`),
      getJSON(`/products/${encodeURIComponent(id)}/gaps`)]);
    renderProduct(p, g);
  } catch (e) { showError(productBox, e); }
}

function renderProduct(p, g) {
  const s = p.summary, m = g.metrics, c = m.attribute_completeness_pct, d = m.description_chars, pr = g.price;
  const head = el("div", { class: "head" }, el("h2", {}, s.title || s.product_id),
    el("span", { class: "badge", title: "Page language" }, `Language: ${fmt(s.language)}`),
    el("span", { class: "badge" }, `Quality: ${fmt(s.quality_status)}`),
    el("span", { class: "muted" }, [s.brand, s.merchant].filter(Boolean).join(" · ")));

  const compl = el("div", { class: "card" }, el("h3", {}, "Attribute completeness"),
    el("div", { class: "bars" },
      barRow("This product", c.target, 100, `${c.target}%`),
      barRow("Peer median", c.peer_median ?? 0, 100, c.peer_median === null ? "no peers" : `${c.peer_median}%`, "peer")),
    el("p", { class: "muted" }, `${c.attributes_checked} attributes checked across ${m.peer_count} comparable products.`));

  const dmax = Math.max(d.target, d.peer_median || 0, 1);
  const desc = el("div", { class: "card" }, el("h3", {}, "Description length (chars)"),
    el("div", { class: "bars" },
      barRow("This product", d.target, dmax, String(d.target)),
      barRow("Peer median", d.peer_median ?? 0, dmax, fmt(d.peer_median), "peer")));

  const price = el("div", { class: "card" }, el("h3", {}, "Price position"), priceRange(pr));

  const facts = el("div", { class: "card" }, el("h3", {}, "Facts"),
    el("p", { class: "muted" }, "Underlined values have evidence; hover or focus to see the source text."),
    factList(p));

  productBox.replaceChildren(head, el("div", { class: "grid" }, compl, desc, price),
    el("div", { class: "grid" }, facts, el("div", { class: "card" }, el("h3", {}, "Issues vs comparable products"), issueGroups(g.issues))));
}

function priceRange(pr) {
  if (typeof pr.target !== "number") return el("p", { class: "muted" }, "Price unknown for this product.");
  if (!pr.peer_count) return el("p", {}, `${money(pr.target, pr.currency)} — no comparable peer prices.`);
  const lo = Math.min(pr.peer_min, pr.target), hi = Math.max(pr.peer_max, pr.target), span = hi - lo || 1;
  const pos = (v) => `${(100 * (v - lo)) / span}%`;
  return el("div", {},
    el("div", { class: "range", role: "img",
      "aria-label": `Price ${money(pr.target, pr.currency)}; peer range ${money(pr.peer_min)} to ${money(pr.peer_max)}` },
      el("div", { class: "span", style: `left:${pos(pr.peer_min)};width:calc(${pos(pr.peer_max)} - ${pos(pr.peer_min)})` }),
      el("div", { class: "dot", style: `left:${pos(pr.target)}` })),
    el("div", { class: "range-labels" }, el("span", {}, money(lo)), el("span", {}, money(hi))),
    el("dl", { class: "facts" },
      el("dt", {}, "This product"), el("dd", {}, money(pr.target, pr.currency)),
      el("dt", {}, "Peer range"), el("dd", {}, `${money(pr.peer_min)} – ${money(pr.peer_max, pr.currency)}`),
      el("dt", {}, "Peer median"), el("dd", {}, `${money(pr.peer_median, pr.currency)} (n=${pr.peer_count})`)));
}

function factList(p) {
  const ev = {};
  for (const e of p.evidence || []) (ev[e.field] = ev[e.field] || []).push(e);
  const dl = el("dl", { class: "facts" });
  for (const sec of FACT_SECTIONS) {
    for (const [k, v] of Object.entries(p[sec] || {})) {
      const key = `${sec}.${k}`;
      if (SKIP_FACTS.has(key) || (v && typeof v === "object" && !Array.isArray(v)) ||
          (Array.isArray(v) && v.some((x) => x && typeof x === "object"))) continue;
      const items = ev[key];
      let dd;
      if (items) {
        const tip = items.map((e) => `“${e.source_text}” — ${human(e.source_location)}, ${e.method}, confidence ${e.confidence}`).join("\n");
        dd = el("dd", {}, el("span", { class: "ev", tabindex: "0", "aria-label": `${fmt(humanValue(v))}. Evidence: ${tip}` },
          fmt(humanValue(v)), el("span", { class: "tip", role: "tooltip" }, tip)));
      } else {
        dd = el("dd", { class: v === null || v === undefined || v === "" ? "muted" : null }, fmt(humanValue(v)));
      }
      dl.append(el("dt", { title: key }, human(k)), dd);
    }
  }
  return dl;
}

function issueGroups(issues) {
  const wrap = el("div", { class: "issues" });
  for (const type of Object.keys(LABELS)) {
    const list = issues.filter((i) => i.type === type);
    wrap.append(el("section", { class: "issue-group" },
      el("h3", {}, el("span", { class: `badge tag-${type}` }, LABELS[type]), el("span", { class: "muted" }, `${list.length}`)),
      list.length ? list.map((i) => el("div", { class: `issue ${type}` },
        el("div", { class: "field", title: i.field }, human(i.field.split(".").pop())),
        el("div", { title: i.statement }, humanText(i.statement)),
        el("div", { class: "action" }, humanText(i.suggested_action)),
        Object.keys(i.evidence || {}).length ?
          el("details", {}, el("summary", {}, "Evidence"), el("pre", {}, JSON.stringify(i.evidence, null, 1))) : null)) :
        el("p", { class: "muted" }, "None.")));
  }
  return wrap;
}

/* ---------- Dataset view ---------- */

async function loadStats() {
  const box = document.getElementById("stats");
  try {
    const s = await getJSON("/stats");
    if (!s.total) {
      box.replaceChildren(el("div", { class: "card empty" }, "No dataset loaded. Set PRODUCTLENS_DATA to a normalized JSONL file."));
      return;
    }
    const n = (o) => Object.keys(o).length;
    const charts = [["Source (merchant)", s.by_source], ["Language", s.by_language], ["Product type", s.by_product_type],
      ["Primary material", s.by_material], ["Quality status", s.by_quality]];
    box.replaceChildren(
      el("div", { class: "tiles" }, tile("Products", s.total), tile("Sources", n(s.by_source)),
        tile("Languages", n(s.by_language)), tile("Product types", n(s.by_product_type))),
      el("div", { class: "grid" }, charts.map(([title, counts]) => countChart(title, counts, s.total))));
  } catch (e) { showError(box, e); }
}

function countChart(title, counts, total) {
  const entries = Object.entries(counts);
  const max = Math.max(...entries.map(([, v]) => v), 1);
  return el("figure", { class: "card", style: "margin:0" }, el("figcaption", {}, el("h3", {}, title)),
    el("div", { class: "bars" }, entries.map(([k, v]) =>
      barRow(String(humanValue(k)).replace(/_/g, " "), v, max, `${v} (${Math.round((100 * v) / total)}%)`))));
}

/* ---------- Models view ---------- */

async function loadModels() {
  const box = document.getElementById("models");
  try {
    const e = await getJSON("/eval");
    const models = Object.entries(e.results || {});
    if (!e.available || !models.length) {
      box.replaceChildren(el("div", { class: "card empty" }, el("h2", {}, "No evaluation yet"),
        "Run train/eval.py and point PRODUCTLENS_EVAL at its JSON output."));
      return;
    }
    const names = models.map(([k]) => k);
    const fields = [...new Set(models.flatMap(([, r]) => Object.keys(r.field_exact || {})))];
    const rows = [["Examples (n)", (r) => fmt(r.n)], ["JSON valid", (r) => pct(r.json_valid)],
      ["Mean field exact", (r) => pct(r.mean_field_exact)],
      ...fields.map((f) => [human(f), (r) => pct((r.field_exact || {})[f])])];
    const parts = [el("h2", {}, "Per field (exact match)"),
      table(["Field", ...names.map(human)], rows.map(([label, fn]) => [label, ...models.map(([, r]) => fn(r))]))];
    for (const [name, r] of models) {
      const langs = Object.entries(r.per_language || {});
      if (!langs.length) continue;
      const lf = [...new Set(langs.flatMap(([, x]) => Object.keys(x.field_exact || {})))];
      parts.push(el("h2", {}, `Per language: ${human(name)}`),
        table(["Field", ...langs.map(([l, x]) => `${l} (n=${fmt(x.n)})`)],
          lf.map((f) => [human(f), ...langs.map(([, x]) => pct((x.field_exact || {})[f]))])));
    }
    box.replaceChildren(...parts);
  } catch (err) { showError(box, err); }
}

function table(head, rows) {
  return el("div", { class: "table-wrap" }, el("table", {},
    el("thead", {}, el("tr", {}, head.map((h) => el("th", { scope: "col" }, h)))),
    el("tbody", {}, rows.map((r) => el("tr", {}, r.map((c, i) => i ? el("td", {}, c) : el("th", { scope: "row" }, c)))))));
}

/* ---------- Routing ---------- */

const loaders = { product: () => results.childElementCount || search(""), dataset: loadStats, models: loadModels };

function route() {
  const view = (location.hash.slice(1).split("/")[0]) || "product";
  const name = loaders[view] ? view : "product";
  for (const v of Object.keys(loaders)) document.getElementById(`view-${v}`).hidden = v !== name;
  document.querySelectorAll("nav a").forEach((a) =>
    a.dataset.view === name ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current"));
  loaders[name]();
  const pid = new URLSearchParams(location.search).get("product");
  if (name === "product" && pid && !productBox.childElementCount) loadProduct(pid);
}

window.addEventListener("hashchange", route);
route();
