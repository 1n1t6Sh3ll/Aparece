import type { Audit } from "./types";

/**
 * One source for "key facts found" everywhere in the UI (issue #103): the listing-quality components, which count the
 * key facts without the description (the description is scored separately). The top-ranked median comes from the
 * same per-product counts on the leaderboard, so "you" and "top-ranked" are always on the same scale.
 */
export function factCount(a: Audit): { n: number; of: number; topMedian: number | null } {
  const c = a.rank.components;
  const peers = a.leaderboard.filter((r) => !r.is_you).slice(0, a.summary.top_count || 10).map((r) => r.facts_stated).sort((x, y) => x - y);
  const m = peers.length ? (peers.length % 2 ? peers[(peers.length - 1) / 2] : (peers[peers.length / 2 - 1] + peers[peers.length / 2]) / 2) : null;
  return { n: c.facts_stated, of: c.facts_checked, topMedian: m };
}
