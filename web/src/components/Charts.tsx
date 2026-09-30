import { useState, type ReactNode } from "react";
import { money, useI18n } from "../lib";
import type { Audit, BoardRow } from "../types";

/** Highlight-vs-context charts: "you" in --chart-you, comparable products in --chart-peer, always direct-labelled. */
function Legend() {
  const { t } = useI18n();
  return (
    <div className="flex flex-wrap gap-4 text-xs muted">
      <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm bg-[var(--chart-you)]" aria-hidden />{t("rank.you")}</span>
      <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm bg-[var(--chart-peer)]" aria-hidden />{t("chart.peers")}</span>
    </div>
  );
}

function Tooltip({ at, children }: { at: { x: number; y: number } | null; children: ReactNode }) {
  if (!at) return null;
  return (
    <div role="tooltip" className="pointer-events-none absolute z-20 w-56 -translate-x-1/2 -translate-y-full rounded-lg bg-stone-900 px-3 py-2 text-xs text-white shadow-xl dark:bg-stone-700"
      style={{ left: at.x, top: at.y - 8 }}>{children}</div>
  );
}

/** Listing-quality score of every ranked product (0-100). Top 10 plus you. */
export function RankChart({ audit }: { audit: Audit }) {
  const { t } = useI18n();
  const [hover, setHover] = useState<{ r: BoardRow; i: number; x: number; y: number } | null>(null);
  const [table, setTable] = useState(false);
  const board = audit.leaderboard;
  if (board.length < 2) return <p className="text-sm muted">{t("rank.aloneD")}</p>;
  const rows = board.map((r, i) => ({ r, i })).filter(({ r, i }) => i < 10 || r.is_you);
  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-2"><Legend />
        <button className="text-xs font-medium text-[var(--accent)] hover:underline" onClick={() => setTable(!table)} aria-pressed={table}>{table ? t("chart.asChart") : t("chart.asTable")}</button>
      </div>
      {table ? (
        <table className="w-full text-sm">
          <thead className="text-left text-xs muted"><tr><th className="py-1 font-medium">#</th><th className="py-1 font-medium">{t("table.product")}</th><th className="py-1 text-right font-medium">{t("chart.score")}</th><th className="py-1 text-right font-medium">{t("chart.facts")}</th></tr></thead>
          <tbody>{board.map((r, i) => (
            <tr key={r.product_id} className={`border-t border-[var(--border)] ${r.is_you ? "font-semibold" : ""}`}>
              <td className="py-1 tabular-nums">{i + 1}</td><td className="max-w-0 truncate py-1">{r.is_you ? t("rank.you") : r.title}</td>
              <td className="py-1 text-right tabular-nums">{r.score}</td><td className="py-1 text-right tabular-nums">{r.facts_stated}</td>
            </tr>))}</tbody>
        </table>
      ) : (
        <div className="relative" onMouseLeave={() => setHover(null)}>
          <ol className="space-y-[2px]" aria-label={t("chart.rankLabel")}>
            {rows.map(({ r, i }) => (
              <li key={r.product_id} className="group grid grid-cols-[1.75rem_minmax(0,9rem)_1fr_2.5rem] items-center gap-2 text-xs"
                onMouseEnter={(e) => { const b = (e.currentTarget.parentElement!.parentElement as HTMLElement).getBoundingClientRect(); const m = e.currentTarget.getBoundingClientRect(); setHover({ r, i, x: m.left - b.left + m.width / 2, y: m.top - b.top }); }}>
                <span className="text-right tabular-nums muted">{i + 1}</span>
                <span className={`truncate ${r.is_you ? "font-semibold text-[var(--accent)]" : ""}`}>{r.is_you ? t("rank.you") : r.title || r.product_id}</span>
                <span className="relative h-4">
                  <span className={`absolute inset-y-0 left-0 rounded-r-[4px] transition-all ${r.is_you ? "bg-[var(--chart-you)]" : "bg-[var(--chart-peer)] opacity-70 group-hover:opacity-100"}`}
                    style={{ width: `${Math.max(1, r.score)}%` }} />
                </span>
                <span className={`text-right tabular-nums ${r.is_you ? "font-semibold" : "muted"}`}>{r.score}</span>
              </li>
            ))}
          </ol>
          <div className="mt-1 grid grid-cols-[1.75rem_minmax(0,9rem)_1fr_2.5rem] gap-2 text-[10px] muted" aria-hidden>
            <span /><span /><span className="flex justify-between"><span>0</span><span>50</span><span>100</span></span><span />
          </div>
          <Tooltip at={hover}>{hover && <>
            <p className="font-semibold">#{hover.i + 1} {hover.r.is_you ? t("rank.you") : hover.r.title}</p>
            {!hover.r.is_you && hover.r.merchant && <p className="opacity-70">{hover.r.merchant}</p>}
            <p className="mt-1">{t("chart.score")}: <b>{hover.r.score}</b> · {t("chart.facts")}: <b>{hover.r.facts_stated}/{hover.r.facts_checked}</b></p>
          </>}</Tooltip>
        </div>
      )}
    </div>
  );
}

/** Your price on a strip with the comparable listings' prices (same currency) and their middle-half band. */
export function PriceChart({ audit }: { audit: Audit }) {
  const { t, lang } = useI18n();
  const [hover, setHover] = useState<{ x: number; y: number; label: string; price: number } | null>(null);
  const pp = audit.price_position;
  if (!pp.available || pp.price == null || pp.p25 == null || pp.p75 == null || pp.median == null) {
    return <p className="text-sm muted">{pp.price == null || !pp.currency ? t("price.noPrice") : t("price.fewPeers")}</p>;
  }
  const peers = audit.leaderboard.filter((r) => !r.is_you && r.price != null && r.currency === pp.currency);
  const all = [pp.price, pp.p25, pp.p75, ...peers.map((r) => r.price!)];
  const lo = Math.min(...all) * 0.9, hi = Math.max(...all) * 1.08;
  const x = (v: number) => (100 * (v - lo)) / (hi - lo || 1);
  const m = (v: number) => money(v, pp.currency, lang);
  const dot = (e: React.MouseEvent, label: string, price: number) => {
    const b = (e.currentTarget.parentElement as HTMLElement).getBoundingClientRect(); const d = e.currentTarget.getBoundingClientRect();
    setHover({ x: d.left - b.left + d.width / 2, y: d.top - b.top, label, price });
  };
  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-4 text-xs muted"><Legend />
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-4 rounded-sm bg-[var(--chart-band)]" aria-hidden />{t("chart.middle")}</span></div>
      <div className="relative mt-8 h-10" onMouseLeave={() => setHover(null)} role="img"
        aria-label={t("price.range", { n: pp.peer_count ?? 0, lo: m(pp.p25), hi: m(pp.p75) }) + ". " + t("price.you") + " " + m(pp.price)}>
        <div className="absolute inset-x-0 top-1/2 h-px bg-[var(--border)]" />
        <div className="absolute top-1/2 h-3 -translate-y-1/2 rounded-[4px] bg-[var(--chart-band)]" style={{ left: `${x(pp.p25)}%`, width: `${x(pp.p75) - x(pp.p25)}%` }} />
        <div className="absolute top-1/2 h-5 w-0.5 -translate-y-1/2 bg-[var(--muted)]" style={{ left: `${x(pp.median)}%` }} />
        {peers.map((r) => (
          <button key={r.product_id} type="button" aria-label={`${r.title}: ${m(r.price!)}`} onMouseEnter={(e) => dot(e, r.title || r.product_id, r.price!)} onFocus={(e) => dot(e as unknown as React.MouseEvent, r.title || "", r.price!)}
            className="absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--chart-peer)] ring-2 ring-[var(--surface)]" style={{ left: `${x(r.price!)}%` }} />
        ))}
        <span className="absolute -top-6 -translate-x-1/2 whitespace-nowrap text-xs font-semibold text-[var(--accent)]" style={{ left: `${x(pp.price)}%` }}>{t("price.you")} {m(pp.price)}</span>
        <span className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-[var(--chart-you)] ring-2 ring-[var(--surface)]" style={{ left: `${x(pp.price)}%` }} />
        <Tooltip at={hover}>{hover && <><p className="font-semibold">{hover.label}</p><p>{m(hover.price)}</p></>}</Tooltip>
      </div>
      <div className="flex justify-between text-[10px] muted" aria-hidden><span>{m(lo)}</span><span>{m(hi)}</span></div>
      <p className="mt-3 text-sm">{t("price.range", { n: pp.peer_count ?? 0, lo: m(pp.p25), hi: m(pp.p75) })}</p>
      <p className="text-xs muted">{t("price.median", { m: m(pp.median) })}. {t("price.note")}</p>
    </div>
  );
}

/** Listing-quality components as filled bars against their maximum points. */
export function ScoreBreakdown({ audit }: { audit: Audit }) {
  const { t, lang } = useI18n();
  const c = audit.rank.components, w = audit.rank.weights;
  const rows = [
    { label: t("rank.facts"), p: c.points.facts, w: w.facts, d: `${c.facts_stated} / ${c.facts_checked}` },
    { label: t("rank.desc"), p: c.points.description, w: w.description, d: t("compare.chars", { n: c.description_chars.toLocaleString(lang) }) },
    ...(audit.product.draft ? [] : [{ label: t("rank.sd"), p: c.points.structured_data, w: w.structured_data, d: `${c.structured_data_flags} / 2` }]),
  ];
  return (
    <div className="space-y-3">
      {rows.map((x) => (
        <div key={x.label}>
          <div className="flex justify-between gap-2 text-xs"><span className="font-medium">{x.label}</span><span className="tabular-nums muted">{x.d} · {t("rank.pts", { p: x.p, w: x.w })}</span></div>
          <div className="mt-1 h-2 rounded-full bg-[var(--surface-2)]" role="img" aria-label={`${x.label}: ${t("rank.pts", { p: x.p, w: x.w })}`}>
            <div className="h-full rounded-full bg-[var(--chart-you)]" style={{ width: `${(100 * x.p) / (x.w || 1)}%` }} />
          </div>
        </div>
      ))}
    </div>
  );
}
