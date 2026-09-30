/**
 * Bulk input parsing (issue #102). Pure (no imports) so it runs under `node --test` as well as in the app.
 *
 * Accepted input, one item per line:
 *   - a product URL (http/https)
 *   - a draft as tab-separated values: title <TAB> description [<TAB> price [<TAB> currency [<TAB> language]]]
 * or a JSON array of {url} / {title, description, price?, currency?, language?} objects.
 * Every rejected line is reported with its line number and a reason code (translated in the UI as bulk.why.<code>).
 */
export type BulkItem = { line: number; label: string; body: { url?: string; title?: string; description?: string; price?: string; currency?: string; language?: string } };
export type BulkReject = { line: number; text: string; reason: "not_http" | "no_title" | "bad_price" | "bad_currency" | "duplicate" | "too_many" | "unrecognised" | "invalid_json" };
export type Parsed = { items: BulkItem[]; rejects: BulkReject[] };

export const MAX = 20;
const URL_RE = /^https?:\/\/[^\s/]+\.[^\s]+$/i;

function draft(line: number, raw: Record<string, unknown>, text: string): BulkItem | BulkReject {
  const s = (k: string) => (typeof raw[k] === "string" || typeof raw[k] === "number" ? String(raw[k]).trim() : "");
  const title = s("title"), description = s("description") || s("text"), price = s("price").replace(",", "."), currency = s("currency").toUpperCase();
  if (!title) return { line, text, reason: "no_title" };
  if (price && !/^\d+(\.\d+)?$/.test(price)) return { line, text, reason: "bad_price" };
  if (currency && !/^[A-Z]{3}$/.test(currency)) return { line, text, reason: "bad_currency" };
  const body: BulkItem["body"] = { title, description };
  if (price) { body.price = price; body.currency = currency || "EUR"; }
  if (s("language")) body.language = s("language").toLowerCase();
  return { line, label: title, body };
}

function one(line: number, text: string, raw: unknown): BulkItem | BulkReject {
  if (raw && typeof raw === "object") {
    const o = raw as Record<string, unknown>;
    if (typeof o.url === "string" && o.url.trim()) return one(line, text, o.url.trim());
    return draft(line, o, text);
  }
  const r0 = String(raw ?? "").replace(/[\r\n]+$/, "");
  if (r0.includes("\t")) {  // split before trimming so an empty first column stays empty
    const [title, description, price, currency, language] = r0.split("\t");
    return draft(line, { title, description, price, currency, language }, text);
  }
  const t = r0.trim();
  if (URL_RE.test(t)) return { line, label: t, body: { url: t } };
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(t) || /^www\./i.test(t)) return { line, text, reason: "not_http" };
  return { line, text, reason: "unrecognised" };
}

export function parseBulk(input: string): Parsed {
  const items: BulkItem[] = [], rejects: BulkReject[] = [];
  const src = input.trim();
  let entries: [number, string, unknown][];
  if (src.startsWith("[")) {
    let arr: unknown;
    try { arr = JSON.parse(src); } catch { return { items, rejects: [{ line: 1, text: src.slice(0, 80), reason: "invalid_json" }] }; }
    if (!Array.isArray(arr)) return { items, rejects: [{ line: 1, text: src.slice(0, 80), reason: "invalid_json" }] };
    entries = arr.map((x, i) => [i + 1, JSON.stringify(x).slice(0, 120), x]);
  } else {
    entries = input.split(/\r?\n/).map((l, i) => [i + 1, l, l] as [number, string, unknown]).filter(([, l]) => (l as string).trim() !== "");
  }
  const seen = new Set<string>();
  for (const [line, text, raw] of entries) {
    const r = one(line, text.trim(), raw);
    if ("reason" in r) { rejects.push(r); continue; }
    const key = r.body.url || `${r.body.title}\u0000${r.body.description}`;
    if (seen.has(key)) { rejects.push({ line, text: text.trim(), reason: "duplicate" }); continue; }
    if (items.length >= MAX) { rejects.push({ line, text: text.trim(), reason: "too_many" }); continue; }
    seen.add(key);
    items.push(r);
  }
  return { items, rejects };
}
