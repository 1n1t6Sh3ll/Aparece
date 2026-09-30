/**
 * Product history client (snapshots, diffs, trends, product chat).
 *
 * The endpoints are being built by another worker. Until they are merged, a 404/405/501 (or a network error) switches
 * the page to the labelled sample in fixtures/productHistory.ts; nothing from the sample is ever shown as the
 * merchant's data. Response shapes below are the contract this UI expects.
 */
import { ApiError, api } from "./lib";
import { token } from "./profile";
import { sampleChat, sampleDiff, sampleSnapshots, sampleTrends } from "./fixtures/productHistory";

export interface Snapshot { id: number; taken_at: string; title: string | null; price: number | null; currency: string | null;
  score: number | null; rank: number | null; total: number | null; facts_found: number | null; facts_checked: number | null }
export interface ChangeEvent { id: number; at: string; type: string; field: string | null; before: unknown; after: unknown }
export interface SnapshotList { product_id: number; snapshots: Snapshot[]; events: ChangeEvent[] }
export interface FieldChange { field: string; change: "added" | "removed" | "changed"; before: unknown; after: unknown }
export interface Diff { a: number; b: number; fields: FieldChange[]; description: { before: string; after: string };
  price: { before: number | null; after: number | null; currency: string | null } }
export interface TrendPoint { at: string; score: number | null; rank: number | null; total: number | null; facts_found: number | null;
  facts_checked: number | null; price: number | null; currency: string | null; visibility: number | null }
export interface Trends { points: TrendPoint[] }
export interface Citation { label: string; snapshot_id?: number | null; field?: string | null; quote?: string | null }
export interface ChatAnswer { answer: string; citations: Citation[] }

/** Header the history endpoints read (the profile access key). One place to change if the contract differs. */
const AUTH = "X-Profile-Token";
const headers = () => ({ [AUTH]: token.get() || "" });
const missing = (e: unknown) => !(e instanceof ApiError) || e.status === 0 || [404, 405, 501].includes(e.status);

export type Loaded<T> = { data: T; sample: boolean };
async function load<T>(path: string, sample: () => T, init?: RequestInit): Promise<Loaded<T>> {
  try {
    return { data: await api<T>(path, { ...init, headers: headers() }), sample: false };
  } catch (e) {
    if (missing(e)) return { data: sample(), sample: true };
    throw e;
  }
}

export const history = {
  snapshots: (id: number) => load<SnapshotList>(`/v1/products/${id}/snapshots`, () => sampleSnapshots(id)),
  diff: (id: number, a: number, b: number) => load<Diff>(`/v1/products/${id}/snapshots/${a}/diff/${b}`, () => sampleDiff(a, b)),
  trends: (id: number) => load<Trends>(`/v1/products/${id}/trends`, sampleTrends),
  chat: (id: number, question: string, language: string) => load<ChatAnswer>("/v1/chat", sampleChat,
    { method: "POST", body: JSON.stringify({ product_id: id, question, language }) }),
};

/** Word-level diff (LCS) for description text: [op, text][] with op "=" | "+" | "-". */
export function wordDiff(a: string, b: string): ["=" | "+" | "-", string][] {
  const x = a.split(/(\s+)/), y = b.split(/(\s+)/);
  if (x.length * y.length > 400_000) return [["-", a], ["+", b]];  // too long for a table: show both whole
  const n = x.length, m = y.length;
  const L = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) for (let j = m - 1; j >= 0; j--) L[i][j] = x[i] === y[j] ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
  const out: ["=" | "+" | "-", string][] = [];
  const push = (op: "=" | "+" | "-", s: string) => { const l = out[out.length - 1]; if (l && l[0] === op) l[1] += s; else out.push([op, s]); };
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (x[i] === y[j]) { push("=", x[i]); i++; j++; } else if (L[i + 1][j] >= L[i][j + 1]) push("-", x[i++]); else push("+", y[j++]);
  }
  while (i < n) push("-", x[i++]);
  while (j < m) push("+", y[j++]);
  return out;
}
