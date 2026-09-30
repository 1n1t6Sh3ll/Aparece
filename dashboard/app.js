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

let currentId = null;

async function loadProduct(id) {
  currentId = id;
  const u = new URL(location.href);
  u.searchParams.set("product", id);
  history.replaceState(null, "", u);
  productBox.replaceChildren(el("p", { class: "muted" }, "Loading…"));
  const base = `/products/${encodeURIComponent(id)}`;
  try {
    const [p, g, s] = await Promise.all([getJSON(base), getJSON(`${base}/gaps`),
      getJSON(`${base}/signals`).catch(() => ({ available: false }))]);
    renderProduct(p, g, s);
  } catch (e) {
    showError(productBox, e.message.startsWith("404") ? new Error("product not in the loaded dataset") : e);
  }
}

function renderProduct(p, g, sig) {
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

  const price = el("div", { class: "card" }, el("h3", {}, "Price position"), priceRange(pr, sig));

  const facts = el("div", { class: "card" }, el("h3", {}, "Facts"),
    el("p", { class: "muted" }, "Underlined values have evidence; hover or focus to see the source text."),
    factList(p));

  productBox.replaceChildren(head, el("div", { class: "grid" }, compl, desc, price),
    el("div", { class: "grid" }, signalPanel(sig), recommendations(g.issues)),
    el("div", { class: "grid" }, facts, el("div", { class: "card" }, el("h3", {}, "Issues vs comparable products"), issueGroups(g.issues))));
}

const FLAG_NAMES = {
  missing_currency: "Currency missing on page", nonpositive_price: "Price zero or negative",
  sale_above_list: "Sale price above list price", conflicting_prices: "Conflicting prices on page",
  rating_out_of_range: "Rating outside its scale", rating_conflict: "Listing rating differs from reviews",
  price_outlier: "Price outlier vs peers", suspicious_discount: "Suspicious discount",
};

function signalPanel(res) {
  const card = el("div", { class: "card" }, el("h3", {}, "Price & reviews"));
  const s = res && res.signal;
  if (!s) {
    card.append(el("p", { class: "muted" }, "No price or review signals for this product. Set PRODUCTLENS_SIGNALS to signals.jsonl."));
    return card;
  }
  const r = s.reviews || {};
  const rating = r.rating_5 ?? r.rating_mean ?? null;
  const dl = el("dl", { class: "facts" },
    el("dt", {}, "Rating"), el("dd", {}, rating === null ? "—" : `${Number(rating).toFixed(2)} / 5`,
      r.research_only ? el("span", { class: "muted" }, " (research-only data)") : null),
    el("dt", {}, "Reviews"), el("dd", {}, fmt(r.review_count ?? r.rating_count)),
    el("dt", {}, "Price in USD"), el("dd", {}, money(s.price_usd, "USD"), s.fx ? el("span", { class: "muted" }, ` (FX ${s.fx.date})`) : null),
    el("dt", {}, "Inflation-adjusted"), el("dd", {}, s.price_usd_2026 === null ? "—" :
      `${money(s.price_usd_2026, "USD")} in ${s.cpi.target_period} dollars (CPI-U, from ${s.cpi.base_period})`),
    el("dt", {}, "Data-quality flags"), el("dd", {}, s.flags.length ?
      el("ul", { class: "flags" }, s.flags.map((f) => el("li", { title: f }, FLAG_NAMES[f] || human(f)))) : "None"));
  card.append(dl, el("p", { class: "muted" }, "Price and peer position are in the Price position card."));
  return card;
}

function recommendations(issues) {
  const order = Object.keys(LABELS);
  const recs = issues.filter((i) => i.suggested_action)
    .sort((a, b) => order.indexOf(a.type) - order.indexOf(b.type));
  return el("div", { class: "card" }, el("h3", {}, "Recommendations"),
    el("p", { class: "muted" }, "Suggestions from gaps vs comparable products. Their effect on AI or search ranking is not measured; none is a causal claim."),
    recs.length ? el("ol", { class: "recs" }, recs.map((i) => el("li", {},
      el("span", { class: `badge tag-${i.type}` }, LABELS[i.type] || i.type), " ", humanText(i.suggested_action),
      el("div", { class: "muted" }, `Basis: ${humanText(i.statement)}`)))) :
      el("p", { class: "muted" }, "None."));
}

/* ---------- Competitors view ---------- */

async function loadCompetitors() {
  const box = document.getElementById("competitors");
  const id = currentId || new URLSearchParams(location.search).get("product");
  if (!id) {
    box.replaceChildren(el("div", { class: "card empty" }, "Pick a product on the Product page first."));
    return;
  }
  box.replaceChildren(el("p", { class: "muted" }, "Loading…"));
  try {
    const c = await getJSON(`/products/${encodeURIComponent(id)}/competitors`);
    const t = c.target;
    const pos = (v) => (v === null || v === undefined ? "—" : v === 0 ? "same price" :
      `${Math.abs(v)}% ${v > 0 ? "higher" : "lower"}`);
    const row = (p, label) => [label || p.title || p.product_id, fmt(p.brand), fmt(p.merchant), `${p.completeness_pct}%`,
      money(p.price, p.currency), label ? "—" : pos(p.price_diff_pct), fmt(p.peer_percentile)];
    box.replaceChildren(
      el("p", {}, "Comparable products for ", el("strong", {}, t.title || t.product_id),
        " (same product type and language; closest matches first)."),
      c.peers.length ? table(["Product", "Brand", "Merchant", "Attribute completeness", "Price", "Price vs this product", "Peer price percentile"],
        [row(t, `This product: ${t.title || t.product_id}`), ...c.peers.map((p) => row(p))]) :
        el("div", { class: "card empty" }, "No comparable products found in the dataset."),
      el("p", { class: "muted" }, "Price differences only compare listings in the same currency. Percentiles come from signals.jsonl peer groups."));
  } catch (e) { showError(box, e); }
}

/* ---------- AI visibility view ---------- */

const rate = (v) => (typeof v === "number" ? `${(v * 100).toFixed(0)}%` : "—");

function entityTable(first, rows, k) {
  return table([first, "Mention rate", `Top-${k} rate`, "MRR", "Citation rate"],
    Object.entries(rows || {}).map(([name, r]) => [name, rate(r.mention_rate), rate(r[`top${k}_rate`]),
      typeof r.mrr === "number" ? r.mrr.toFixed(2) : "—", rate(r.citation_rate)]));
}

async function loadVisibility() {
  const box = document.getElementById("visibility");
  try {
    const v = await getJSON("/visibility");
    if (!v.available) {
      box.replaceChildren(el("div", { class: "card empty" }, el("h2", {}, "No benchmark runs yet"),
        "Run the AI-visibility benchmark report and point PRODUCTLENS_VISIBILITY at its report.json."));
      return;
    }
    const rep = v.report, k = rep.k;
    const parts = [el("p", { class: "muted" }, `${rep.responses} responses. Observed outputs of black-box AI systems; ` +
      "rates describe what was mentioned, not why.")];
    for (const [model, m] of Object.entries(rep.models)) {
      parts.push(el("h2", {}, `Model: ${model}`),
        el("div", { class: "tiles" }, tile("Responses", m.responses), tile("Any catalog mention", rate(m.any_catalog_mention_rate)),
          tile("Stability", m.stability === null ? "n/a" : m.stability.toFixed(2), "Mean overlap across repeats"),
          tile("Unmatched mentions", m.unmatched_mentions)),
        el("h3", {}, "By site"), entityTable("Site", m.sites, k));
      const langs = Object.entries(m.languages || {});
      if (langs.length) {
        parts.push(el("h3", {}, "By language"), table(["Language", "Responses", "Any catalog mention", "Stability"],
          langs.map(([l, s]) => [l, fmt(s.responses), rate(s.any_catalog_mention_rate),
            s.stability === null ? "n/a" : s.stability.toFixed(2)])));
      }
      if (Object.keys(m.products || {}).length) parts.push(el("h3", {}, "By product"), entityTable("Product", m.products, k));
    }
    box.replaceChildren(...parts);
  } catch (e) { showError(box, e); }
}

/* ---------- Languages view ---------- */

async function loadLanguages() {
  const box = document.getElementById("languages");
  try {
    const { languages: langs, visibility_available: vis } = await getJSON("/languages");
    const entries = Object.entries(langs);
    if (!entries.length) {
      box.replaceChildren(el("div", { class: "card empty" }, "No dataset or benchmark report loaded."));
      return;
    }
    const models = [...new Set(entries.flatMap(([, x]) => Object.keys(x.visibility)))];
    box.replaceChildren(
      el("div", { class: "card", style: "margin-bottom:16px" }, el("h3", {}, "Median attribute completeness by language"),
        el("div", { class: "bars" }, entries.map(([l, x]) =>
          barRow(l, x.completeness_median ?? 0, 100, x.completeness_median === null ? "no products" : `${x.completeness_median}%`)))),
      table(["Language", "Products", "Completeness (median)", "Completeness (mean)",
        ...models.map((m) => `Any mention: ${m}`)],
      entries.map(([l, x]) => [l, x.products, x.completeness_median === null ? "—" : `${x.completeness_median}%`,
        x.completeness_mean === null ? "—" : `${x.completeness_mean}%`,
        ...models.map((m) => x.visibility[m] ? `${rate(x.visibility[m].any_catalog_mention_rate)} (n=${x.visibility[m].responses})` : "—")])),
      el("p", { class: "muted" }, vis ? "Coverage and visibility are shown side by side; this does not show that one causes the other." :
        "Visibility appears here once a benchmark report is loaded (PRODUCTLENS_VISIBILITY)."));
  } catch (e) { showError(box, e); }
}

function rangeBar(target, a, b, cur) {
  const lo = Math.min(a, target), hi = Math.max(b, target), span = hi - lo || 1;
  const pos = (v) => `${(100 * (v - lo)) / span}%`;
  return [el("div", { class: "range", role: "img",
    "aria-label": `Price ${money(target, cur)}; peer range ${money(a)} to ${money(b)}` },
  el("div", { class: "span", style: `left:${pos(a)};width:calc(${pos(b)} - ${pos(a)})` }),
  el("div", { class: "dot", style: `left:${pos(target)}` })),
  el("div", { class: "range-labels" }, el("span", {}, money(lo)), el("span", {}, money(hi)))];
}

// The single place the UI shows this product's price. Peer set: gap-analysis peers when they have
// comparable prices, else the signals.jsonl peer group (same type, language, currency and currency basis).
function priceRange(pr, res) {
  const s = res && res.signal;
  if (typeof pr.target === "number" && pr.peer_count) {
    return el("div", {}, el("p", { class: "muted" }, `Peer set: ${pr.peer_count} comparable products from gap analysis, same currency.`),
      rangeBar(pr.target, pr.peer_min, pr.peer_max, pr.currency),
      el("dl", { class: "facts" },
        el("dt", {}, "This product"), el("dd", {}, money(pr.target, pr.currency)),
        el("dt", {}, "Peer range"), el("dd", {}, `${money(pr.peer_min)} – ${money(pr.peer_max, pr.currency)}`),
        el("dt", {}, "Peer median"), el("dd", {}, `${money(pr.peer_median, pr.currency)} (n=${pr.peer_count})`)));
  }
  const target = typeof pr.target === "number" ? pr.target : s && s.price;
  const cur = typeof pr.target === "number" ? pr.currency : s && s.currency;
  if (typeof target !== "number") return el("p", { class: "muted" }, "Price unknown for this product.");
  const assumed = s && res.currency_assumed ? el("span", { class: "badge tag-SUPPORTED_HYPOTHESIS", title: s.currency_source },
    "Currency assumed") : null;
  const list = s && s.list_price ? [el("dt", {}, "List price"),
    el("dd", {}, `${money(s.list_price, cur)} (${fmt(s.discount_pct)}% off)`)] : null;
  const peer = s && s.peer;
  if (!peer || typeof pr.target === "number" && pr.currency !== s.currency) {
    return el("div", {}, el("dl", { class: "facts" }, el("dt", {}, "This product"), el("dd", {}, money(target, cur), " ", assumed), list),
      el("p", { class: "muted" }, "No comparable peer prices."));
  }
  return el("div", {},
    el("p", { class: "muted" }, `Peer set: ${peer.n} listings in signals group ${peer.group} (gap-analysis peers had no comparable prices). Bar shows the middle half.`),
    rangeBar(target, peer.p25, peer.p75, cur),
    el("dl", { class: "facts" },
      el("dt", {}, "This product"), el("dd", {}, money(target, cur), " ", assumed), list,
      el("dt", {}, "Middle half of peers"), el("dd", {}, `${money(peer.p25)} – ${money(peer.p75, cur)}`),
      el("dt", {}, "Peer median"), el("dd", {}, money(peer.p50, cur)),
      el("dt", {}, "Peer percentile"), el("dd", {}, `${peer.percentile} (${human(peer.position)})`)),
    s.guidance ? el("p", { class: "muted" }, s.guidance.note) : null);
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
      ["Accuracy on stated values", (r) => pct(r.non_null_acc)], ["Accuracy on absent values (null)", (r) => pct(r.null_acc)],
      ...fields.map((f) => [human(f.split(".").pop()), (r) => pct((r.field_exact || {})[f])])];
    const parts = [el("h2", {}, "Per field (exact match)"),
      table(["Field", ...names.map(human)], rows.map(([label, fn]) => [label, ...models.map(([, r]) => fn(r))]))];
    // Any per_<dimension> breakdown in the eval JSON (per_language, per_source, ...).
    for (const [name, r] of models) {
      for (const dim of Object.keys(r).filter((key) => key.startsWith("per_"))) {
        const groups = Object.entries(r[dim] || {});
        if (!groups.length) continue;
        const lf = [...new Set(groups.flatMap(([, x]) => Object.keys(x.field_exact || {})))];
        parts.push(el("h2", {}, `${human(dim.slice(4))}: ${human(name)}`),
          table(["Field", ...groups.map(([g, x]) => `${g} (n=${fmt(x.n)})`)],
            lf.map((f) => [human(f.split(".").pop()), ...groups.map(([, x]) => pct((x.field_exact || {})[f]))])));
      }
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

const loaders = { product: () => results.childElementCount || search(""), competitors: loadCompetitors,
  visibility: loadVisibility, languages: loadLanguages, dataset: loadStats, models: loadModels };

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
