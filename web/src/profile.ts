import { api, store } from "./lib";
import type { Audit } from "./types";

/** Merchant profile (TEAM-45). Everything here is merchant-stated; ProductLens verifies none of it. */
export interface Company {
  name: string; website: string; sells: string; brand: string; markets: string[]; languages: string[];
  price_positioning: "" | "budget" | "mid" | "premium" | "luxury"; audience: string; claims: string[];
  competitors: string[]; platform: "" | "shopify" | "woocommerce" | "magento" | "bigcommerce" | "custom" | "other";
}
export interface Person { name: string; role: string; about: string }
export interface ProductIn { url?: string; title?: string; text?: string; price?: string; currency?: string; language?: string }
export interface Decision { status: "accepted" | "dismissed"; original: string; suggested: string; decided_at: string }
export interface Product extends ProductIn {
  id: number; source: "url" | "manual"; merchant_stated: boolean; audit: Audit | null; audited_at: string | null;
  record?: Record<string, unknown> | null; suggestions?: Record<string, Decision>;
}
export interface Profile {
  person: Person; company: Omit<Company, "claims"> & { claims: { text: string; source: string; verified: boolean }[] };
  language: "en" | "es"; shared: boolean; share_token: string | null; products: Product[];
}
export interface Shared { company: { name: string; website: string }; language: string; products: Product[] }

/** Access keys live only in this browser. Several companies can be kept; one is active (the company switcher). */
const KEY = "pl.profileToken";
const LIST = "pl.accounts";
export type Account = { token: string; name: string };
export const accounts = (): Account[] => { try { return JSON.parse(store.get(LIST) || "[]"); } catch { return []; } };
const saveAccounts = (a: Account[]) => store.set(LIST, JSON.stringify(a));
export const token = {
  get: () => store.get(KEY),
  set: (t: string, name = "") => {
    store.set(KEY, t);
    const rest = accounts().filter((a) => a.token !== t);
    saveAccounts([...rest, { token: t, name: name || accounts().find((a) => a.token === t)?.name || "" }]);
  },
  /** Forget the active key on this device and fall back to another saved company, if any. */
  clear: () => {
    const cur = store.get(KEY);
    const rest = accounts().filter((a) => a.token !== cur);
    saveAccounts(rest);
    try { if (rest.length) localStorage.setItem(KEY, rest[rest.length - 1].token); else localStorage.removeItem(KEY); } catch { /* */ }
  },
  name: (t: string, name: string) => saveAccounts(accounts().map((a) => (a.token === t ? { ...a, name } : a))),
};

export function papi<R>(path: string, init?: RequestInit): Promise<R> {
  return api<R>(path, { ...init, headers: { "X-Profile-Token": token.get() || "" } });
}

export const emptyCompany = (): Company => ({ name: "", website: "", sells: "", brand: "", markets: [], languages: [], price_positioning: "",
  audience: "", claims: [], competitors: [], platform: "" });

export function productName(p: Product) {
  return p.audit?.product.title || p.title || p.url || `#${p.id}`;
}
