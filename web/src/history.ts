/**
 * Monitored-product history client (monitor_api, PR #79): snapshots, snapshot diffs, trends, change events, plus
 * the grounded chat (chat_api). History calls send the per-product manage token saved at enrol (X-Manage-Token).
 */
import { api, manageToken, saveManageToken } from "./lib";

export interface Metrics {
  completeness_rank: { position: number; of: number; by: string } | null; attribute_completeness_pct: number | null;
  peer_median_completeness_pct: number | null; description_chars: number | null; price: number | null; currency: string | null;
  structured_data_present: boolean | null; language: string | null; visibility: unknown;
}
export interface Snapshot { id: number; crawled_at: string; content_hash: string; metrics: Metrics }
export interface TrendPoint extends Metrics { at: string; snapshot_id: number }
export interface ChangeEvent { id: number; at: string; type: string; field: string | null; before: unknown; after: unknown }
export interface Monitored { id: string; url: string; enrolled_at: string; active: number; plan: string | null;
  last_snapshot_at: string | null; snapshot_count: number; event_count: number }
export interface Diff {
  from: { id: number; crawled_at: string }; to: { id: number; crawled_at: string };
  attributes: { added: { field: string; new: unknown }[]; removed: { field: string; old: unknown }[]; changed: { field: string; old: unknown; new: unknown }[] };
  description: { changed: boolean; old_chars: number; new_chars: number; text_diff: string[] | null };
  price: { changed: boolean; old: { price: number | null; currency: string | null }; new: { price: number | null; currency: string | null } };
  structured_data: { changed: boolean; old: Record<string, boolean>; new: Record<string, boolean> };
  languages: { added: string[]; removed: string[] };
  visibility: { changed: boolean; old: unknown; new: unknown };
}
export interface ChatAnswer { answer: string; citations: { type: string; id: string; date: string | null; merchant_stated: boolean }[]; refused: boolean }

const h = (id: string) => ({ headers: { "X-Manage-Token": manageToken(id) } });
const enc = encodeURIComponent;

export const history = {
  snapshots: (id: string) => api<{ results: Snapshot[] }>(`/v1/products/${enc(id)}/snapshots`, h(id)).then((r) => r.results),
  diff: (id: string, a: number, b: number) => api<Diff>(`/v1/products/${enc(id)}/snapshots/${a}/diff/${b}`, h(id)),
  trends: (id: string) => api<{ points: TrendPoint[] }>(`/v1/products/${enc(id)}/trends`, h(id)).then((r) => r.points),
  history: (id: string) => api<{ product: Monitored; events: ChangeEvent[] }>(`/v1/products/${enc(id)}/history`, h(id)),
  recrawl: (id: string) => api(`/v1/monitored/${enc(id)}/crawl`, { method: "POST", ...h(id) }),
  /** Start monitoring a URL (crawls once now) and keep its manage token in this browser. Returns the public id. */
  enroll: async (url: string) => {
    const r = await api<{ product: Monitored; manage_token: string | null }>("/v1/enroll", { method: "POST", body: JSON.stringify({ url, crawl_now: true }) });
    if (r.manage_token) saveManageToken(r.product.id, r.manage_token);
    return r.product.id;
  },
  /** Grounded chat about monitored product `id`: sends its public id and manage token so answers use its snapshots. */
  chat: (id: string, message: string, past: { role: "user" | "assistant"; content: string }[]) =>
    api<ChatAnswer>("/v1/chat", { method: "POST", ...h(id), body: JSON.stringify({ product_id: id, message, history: past.slice(-20) }) }),
};

/** A number from a metrics value, or null (visibility may be an object per model; only a plain number is charted). */
export const num = (v: unknown) => (typeof v === "number" && Number.isFinite(v) ? v : null);
