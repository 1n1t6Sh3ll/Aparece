import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import en from "./i18n/en.json";
import es from "./i18n/es.json";

type Dict = Record<string, unknown>;
export type Lang = "en" | "es";
const DICTS: Record<Lang, Dict> = { en, es };

export const store = {
  get(key: string): string | null {
    try { return localStorage.getItem(key); } catch { return null; }
  },
  set(key: string, value: string) {
    try { localStorage.setItem(key, value); } catch { /* storage unavailable: feature just doesn't persist */ }
  },
};

function initialLang(): Lang {
  const saved = store.get("pl.lang");
  if (saved === "en" || saved === "es") return saved;
  return navigator.language?.toLowerCase().startsWith("es") ? "es" : "en";
}

export type T = (key: string, params?: Record<string, string | number>) => string;
const Ctx = createContext<{ lang: Lang; setLang: (l: Lang) => void; t: T }>(null!);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(initialLang);
  useEffect(() => { document.documentElement.lang = lang; }, [lang]);
  const setLang = (l: Lang) => { setLangState(l); store.set("pl.lang", l); };
  const t: T = (key, params) => {
    const d = DICTS[lang];
    const raw = (d[key] ?? (DICTS.en as Dict)[key] ?? key) as string;
    return raw.replace(/\{(\w+)\}/g, (_, k) => (params && k in params ? String(params[k]) : `{${k}}`));
  };
  return <Ctx.Provider value={{ lang, setLang, t }}>{children}</Ctx.Provider>;
}

export const useI18n = () => useContext(Ctx);

export function fieldLabel(lang: Lang, field: string): string {
  const f = (DICTS[lang].fields as Record<string, string>)[field] ?? (DICTS.en.fields as Record<string, string>)[field];
  return f ?? field.split(".").pop()!.replace(/_/g, " ");
}

/** Plural-aware t(): uses "<key>.one" when n is 1 and that key exists. */
export const tn = (t: T, key: string, n: number, params: Record<string, string | number> = {}) => {
  const one = `${key}.one`;
  return n === 1 && t(one) !== one ? t(one, { n, ...params }) : t(key, { n, ...params });
};

export const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export function money(v: number | null | undefined, cur: string | null | undefined, lang: Lang) {
  if (v == null) return "";
  try {
    return cur ? new Intl.NumberFormat(lang, { style: "currency", currency: cur }).format(v) : String(v);
  } catch {
    return `${v} ${cur ?? ""}`.trim();
  }
}

export function fmtValue(v: unknown): string {
  if (v == null) return "";
  if (Array.isArray(v)) {
    // list items like sizes/colours are {raw, normalized, ...}: show one readable name each
    const name = (x: unknown) => x && typeof x === "object"
      ? fmtValue(["normalized_size", "raw_size", "original_color_name", "normalized", "raw", "name"].map((k) => (x as Record<string, unknown>)[k]).find((y) => y != null && y !== ""))
      : fmtValue(x);
    return [...new Set(v.map(name).filter(Boolean))].join(", ");
  }
  if (typeof v === "object") return Object.entries(v as Record<string, unknown>).map(([k, x]) => `${k.replace(/_/g, " ")} ${x}%`).join(", ");
  return String(v).replace(/_/g, " ");
}

/** A fact value in the viewer's language: description is a character count, booleans are Yes/No. */
export function fmtField(field: string, v: unknown, t: T): string {
  if (field === "content.full_description" && typeof v === "number") return t("compare.chars", { n: v });
  if (typeof v === "boolean") return t(v ? "val.yes" : "val.no");
  return fmtValue(v);
}

export class ApiError extends Error {
  constructor(public status: number, public detail: string) { super(detail); }
}

/** Per-enrollment manage tokens (shown once by POST /v1/enroll), kept only in this browser. */
function manageTokens(): Record<string, string> {
  try { return JSON.parse(store.get("pl.manage") || "{}"); } catch { return {}; }
}
export const saveManageToken = (id: string, token: string) => store.set("pl.manage", JSON.stringify({ ...manageTokens(), [id]: token }));
export const manageToken = (id: string) => manageTokens()[id] || "";
/** All tokens this browser holds, for GET /v1/monitored (which lists only the caller's products). */
export const allManageTokens = () => Object.values(manageTokens()).join(",");

export async function api<R>(path: string, init?: RequestInit): Promise<R> {
  let r: Response;
  try {
    r = await fetch(path, { ...init, headers: { "Content-Type": "application/json", ...(init?.headers || {}) } });
  } catch {
    throw new ApiError(0, "network");
  }
  const body = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = body?.detail;
    throw new ApiError(r.status, typeof d === "string" ? d : Array.isArray(d) ? d[0]?.msg ?? "invalid request" : `HTTP ${r.status}`);
  }
  return body as R;
}

/** Map an API error to user-facing copy; the raw detail is only interpolated as plain text. */
/** Map an API error to translated copy. Coded details ("code: text") map by code; raw codes never reach the user. */
export function errorText(e: unknown, t: T): { msg: string; suggestText: boolean; openDraft?: boolean } {
  if (!(e instanceof ApiError)) return { msg: t("err.unknown"), suggestText: false };
  const d = e.detail || "";
  const code = /^([a-z_]+):/.exec(d)?.[1];
  const coded: Record<string, [string, boolean]> = {
    amazon_not_supported: ["err.amazon", true], blocked_by_store: ["err.blocked", true], host_not_found: ["err.dns", false],
    not_a_web_page: ["err.notPage", false], page_not_found: ["err.pageNotFound", false], product_gone: ["err.gone", true],
    not_a_product_page: ["err.notProduct", false], not_a_shirt: ["err.notShirt", false], draft_needs_title: ["hero.emptyTitle", false],
    too_many_requests: ["err.tooMany", false], invalid_price: ["err.invalidPrice", false], invalid_currency: ["err.invalidCurrency", false], invalid_field: ["err.invalidField", false],
  };
  if (e.status === 0) return { msg: t("err.network"), suggestText: false };
  if (code && coded[code]) return { msg: t(coded[code][0]), suggestText: coded[code][1], openDraft: coded[code][1] };
  if (e.status === 429) return { msg: t("err.tooMany"), suggestText: false };  // our own per-network limit, not the store's
  if (/upstream HTTP (429|503)/.test(d)) return { msg: t("err.rateLimited"), suggestText: true, openDraft: true };
  if (/robots\.txt disallows/.test(d)) return { msg: t("err.robots"), suggestText: true, openDraft: true };
  if (d.includes("does not resolve")) return { msg: t("err.dns"), suggestText: false };
  if (d.includes("http(s)")) return { msg: t("err.scheme"), suggestText: false };
  if (d.includes("non-public")) return { msg: t("err.private"), suggestText: false };
  if (e.status === 504 || d.includes("deadline") || d.includes("Timeout")) return { msg: t("err.timeout"), suggestText: true };
  if (e.status === 413) return { msg: t("err.tooBig"), suggestText: true };
  if (e.status === 415) return { msg: t("err.notPage"), suggestText: false };
  if (d.startsWith("upstream") || d.startsWith("fetch failed") || e.status === 502) return { msg: t("err.upstreamPlain"), suggestText: true };
  if (e.status === 401 || e.status === 403) return { msg: t("err.denied"), suggestText: false };
  if (e.status === 404) return { msg: t("err.notFound"), suggestText: false };
  if (d.includes("provide url, html or text")) return { msg: t("err.empty"), suggestText: false };
  if (e.status === 422) return { msg: t("err.invalid"), suggestText: false };
  return { msg: t("err.unknown"), suggestText: false };
}

export function useHashRoute(): [string, (r: string) => void] {
  const read = () => window.location.hash.replace(/^#\/?/, "");
  const [route, setRoute] = useState(read);
  useEffect(() => {
    const on = () => { setRoute(read()); window.scrollTo({ top: 0 }); };
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  return [route, (r: string) => { window.location.hash = "/" + r; }];
}
