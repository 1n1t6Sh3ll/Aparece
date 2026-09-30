/**
 * SAMPLE data for the product history page while the snapshot/diff/trend/chat endpoints are not merged.
 * Invented for layout only; the page shows a "Sample data" banner whenever it is used. Never mix with real data.
 */
import type { ChatAnswer, Diff, SnapshotList, Trends } from "../history";

const DAYS = [56, 42, 28, 14, 0];
const at = (d: number) => new Date(Date.UTC(2026, 8, 29) - d * 864e5).toISOString();
const SNAP = [
  { score: 38.2, rank: 21, facts: 7, price: 29.0 },
  { score: 41.5, rank: 19, facts: 8, price: 29.0 },
  { score: 47.9, rank: 15, facts: 10, price: 27.5 },
  { score: 52.3, rank: 12, facts: 11, price: 27.5 },
  { score: 58.1, rank: 9, facts: 13, price: 27.5 },
];

export const sampleSnapshots = (id: number): SnapshotList => ({
  product_id: id,
  snapshots: SNAP.map((s, i) => ({ id: i + 1, taken_at: at(DAYS[i]), title: i < 3 ? "Sample tee" : "Sample tee - organic cotton",
    price: s.price, currency: "EUR", score: s.score, rank: s.rank, total: 25, facts_found: s.facts, facts_checked: 23 })),
  events: [
    { id: 1, at: at(42), type: "field_added", field: "fit_and_style.fit", before: null, after: "regular" },
    { id: 2, at: at(28), type: "price_changed", field: "commerce.price", before: 29.0, after: 27.5 },
    { id: 3, at: at(28), type: "field_added", field: "materials.material_percentages", before: null, after: { cotton: 100 } },
    { id: 4, at: at(14), type: "title_changed", field: "content.title", before: "Sample tee", after: "Sample tee - organic cotton" },
    { id: 5, at: at(0), type: "field_added", field: "variants.sizes", before: null, after: "S, M, L, XL" },
  ],
});

export const sampleDiff = (a: number, b: number): Diff => ({
  a, b,
  fields: [
    { field: "fit_and_style.fit", change: "added", before: null, after: "regular" },
    { field: "materials.material_percentages", change: "added", before: null, after: { cotton: 100 } },
    { field: "variants.sizes", change: "added", before: null, after: "S, M, L, XL" },
    { field: "content.title", change: "changed", before: "Sample tee", after: "Sample tee - organic cotton" },
    { field: "fit_and_style.pattern", change: "removed", before: "graphic", after: null },
  ],
  description: { before: "A soft tee for every day. Machine wash.", after: "A soft tee for every day, made of 100% organic cotton. Regular fit. Machine wash at 30°C." },
  price: { before: 29.0, after: 27.5, currency: "EUR" },
});

export const sampleTrends = (): Trends => ({
  points: SNAP.map((s, i) => ({ at: at(DAYS[i]), score: s.score, rank: s.rank, total: 25, facts_found: s.facts, facts_checked: 23,
    price: s.price, currency: "EUR", visibility: null })),
});

export const sampleChat = (): ChatAnswer => ({
  answer: "Sample answer (the product chat endpoint is not connected yet). Since the first snapshot the page added fit, material composition and sizes, and the price dropped from 29.00 to 27.50 EUR. Still not found: fabric weight and care instructions.",
  citations: [
    { label: "Snapshot 5", snapshot_id: 5, field: "variants.sizes", quote: "S, M, L, XL" },
    { label: "Snapshot 3", snapshot_id: 3, field: "commerce.price", quote: "27.50 EUR" },
  ],
});
