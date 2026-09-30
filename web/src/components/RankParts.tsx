import { useId, useState, type ReactNode } from "react";
import { Check, ChevronDown, Info, Minus, Trophy } from "lucide-react";
import { cap, fieldLabel, fmtField, useI18n } from "../lib";
import type { Audit } from "../types";

/** Accessible info tooltip: opens on hover, focus or tap; text is plain (no HTML). */
export function Tip({ text, children }: { text: string; children?: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span className="relative inline-flex items-center" onMouseEnter={() => setOpen(true)} onMouseLeave={() => setOpen(false)}>
      {children}
      <button type="button" aria-describedby={open ? id : undefined} aria-label={text} onClick={() => setOpen(!open)}
        onFocus={() => setOpen(true)} onBlur={() => setOpen(false)} onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
        className="ml-1 rounded-full p-0.5 text-stone-400 hover:text-brand-600 focus-visible:outline-2 focus-visible:outline-brand-500 dark:hover:text-brand-400">
        <Info className="size-3.5" aria-hidden />
      </button>
      {open && (
        <span role="tooltip" id={id} className="absolute left-1/2 top-full z-30 mt-2 w-64 -translate-x-1/2 rounded-lg bg-stone-900 p-3 text-xs font-normal leading-relaxed text-white shadow-xl dark:bg-stone-700">
          {text}
        </span>
      )}
    </span>
  );
}

export function RankCard({ audit }: { audit: Audit }) {
  const { t, lang } = useI18n();
  const r = audit.rank;
  const c = r.components;
  const w = r.weights;
  const [how, setHow] = useState(false);
  const draft = audit.product.draft;
  // ties share a position: "2–3" when shirts with the same score span positions 2 to 3 (API position_from/to)
  const tie = r as typeof r & { position_from?: number; position_to?: number };
  const pos = tie.position_from && tie.position_to && tie.position_to > tie.position_from
    ? `${tie.position_from}–${tie.position_to}` : String(r.position);
  if (r.total <= 1) {
    return (
      <section className="card p-6 rise">
        <p className="text-sm font-semibold uppercase tracking-wide text-brand-600 dark:text-brand-400">{t("rank.eyebrow")}</p>
        <h2 className="mt-2 text-2xl font-bold">{t("rank.alone")}</h2>
        <p className="mt-1 muted">{t("rank.aloneD")}</p>
        {lang === "en" && (audit.notes || []).map((n) => <p key={n} className="mt-2 text-sm muted">{n}</p>)}
      </section>
    );
  }
  // description_intents: the shopper questions the description answers (API), each counted once
  const intents = (c as typeof c & { description_intents?: string[] }).description_intents ?? [];
  const sdDropped = !(w.structured_data > 0);
  const rows = [
    { k: "facts", label: t("rank.facts"), tip: t("rank.factsTip", { w: w.facts }), p: c.points.facts, w: w.facts, detail: `${c.facts_stated} / ${c.facts_checked}` },
    { k: "description", label: t("rank.desc"), tip: t("rank.descTip", { w: w.description, ref: c.description_ref }), p: c.points.description, w: w.description, detail: t("rank.descDetail", { n: intents.length, of: c.description_ref }) },
    { k: "sd", label: t("rank.sd"), tip: t("rank.sdTip", { w: w.structured_data }), p: c.points.structured_data, w: w.structured_data, detail: `${c.structured_data_flags} / 2` },
  ].filter((x) => x.w > 0); // a component dropped from the comparison (weight 0) is not shown
  return (
    <section className="card overflow-hidden rise">
      <div className="grid gap-6 p-6 sm:p-8 md:grid-cols-[auto_1fr] md:items-center">
        <div className="flex items-center gap-5">
          <div className="relative grid size-28 shrink-0 place-items-center rounded-full bg-[var(--accent)] text-white shadow-lg shadow-brand-500/25">
            <div className="text-center leading-none">
              <span className="text-sm font-semibold opacity-80">#</span><span className={`${pos.length > 3 ? "text-3xl" : "text-5xl"} font-extrabold tracking-tight`}>{pos}</span>
            </div>
            <Trophy className="absolute -right-1 -top-1 size-8 rounded-full bg-white p-1.5 text-amber-500 shadow dark:bg-stone-900" aria-hidden />
          </div>
          <div>
            <p className="flex items-center text-sm font-semibold uppercase tracking-wide text-brand-600 dark:text-brand-400">
              {t("rank.eyebrow")}{draft && <span className="chip ml-2 bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200">{t("draft.badge")}</span>}
            </p>
            <h2 className="mt-1 text-2xl font-extrabold tracking-tight sm:text-3xl">#{pos} {t("rank.of", { n: r.total })}</h2>
            <p className="mt-1 text-sm muted">{t("rank.score", { s: r.score })}</p>
          </div>
        </div>
        <div className="space-y-3">
          {rows.map((x) => (
            <div key={x.k}>
              <div className="flex items-center justify-between gap-2 text-sm">
                <Tip text={x.tip}><span className="font-medium">{x.label}</span></Tip>
                <span className="tabular-nums muted">{x.detail} · {t("rank.pts", { p: x.p, w: x.w })}</span>
              </div>
              <div className="mt-1.5 h-2 rounded-full bg-stone-100 dark:bg-stone-800" role="img" aria-label={`${x.label}: ${t("rank.pts", { p: x.p, w: x.w })}`}>
                <div className="h-full rounded-full bg-brand-500 transition-all duration-700" style={{ width: `${(100 * x.p) / (x.w || 1)}%` }} />
              </div>
            </div>
          ))}
          {sdDropped && <p className="text-xs muted">{t("rank.sd")}: {t(draft ? "rank.sdDraft" : "rank.sdUnknown")}</p>}
        </div>
      </div>
      <div className="border-t border-stone-100 bg-stone-50/70 px-6 py-3 text-sm dark:border-stone-800 dark:bg-stone-900/60 sm:px-8">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="muted">{t("rank.aiNote")}</p>
          <button className="inline-flex items-center gap-1 font-medium text-brand-600 dark:text-brand-400" aria-expanded={how} onClick={() => setHow(!how)}>
            {t("rank.how")} <ChevronDown className={`size-4 transition-transform ${how ? "rotate-180" : ""}`} aria-hidden />
          </button>
        </div>
        {how && <p className="mt-2 text-xs leading-relaxed muted">{t("rank.formula", { wf: w.facts, wd: w.description, ref: c.description_ref,
          sd: sdDropped ? "" : t("rank.formulaSd", { ws: w.structured_data }) })}</p>}
      </div>
    </section>
  );
}

type SortKey = "gaps" | "coverage" | "az";

/** Side-by-side table: search, "only my gaps" filter, sort, column hover; rows you miss but peers state are highlighted. */
export function CompareTable({ audit }: { audit: Audit }) {
  const { t, lang } = useI18n();
  const { fields, rows } = audit.table;
  const [q, setQ] = useState("");
  const [onlyGaps, setOnlyGaps] = useState(false);
  const [sort, setSort] = useState<SortKey>("gaps");
  const [col, setCol] = useState<number | null>(null);
  if (rows.length < 2 || !fields.length) return null;
  const you = rows.find((r) => r.is_you)!;
  const peers = rows.filter((r) => !r.is_you);
  const name = (f: string) => cap(fieldLabel(lang, f).replace(/^(la|el|los|las) /, ""));
  const info = fields.map((f) => ({ f, name: name(f), cover: peers.filter((r) => r.values[f] !== undefined).length, gap: you.values[f] === undefined }));
  const shown = info
    .filter((x) => (!onlyGaps || x.gap) && x.name.toLowerCase().includes(q.trim().toLowerCase()))
    .sort((a, b) => sort === "az" ? a.name.localeCompare(b.name, lang)
      : sort === "coverage" ? b.cover - a.cover : (Number(b.gap) - Number(a.gap)) || b.cover - a.cover);
  const gaps = info.filter((x) => x.gap && x.cover > 0).length;
  const short = (s: string | null) => (s && s.length > 38 ? s.slice(0, 36) + "…" : s || "");
  return (
    <section className="card rise" aria-labelledby="cmp-h">
      <div className="flex flex-col gap-3 border-b border-[var(--border)] p-4 sm:p-5 lg:flex-row lg:items-end">
        <div className="flex-1">
          <h2 id="cmp-h" className="font-semibold">{t("table.title")}</h2>
          <p className="mt-0.5 text-sm muted">{t("table.gaps", { n: gaps })}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <label className="sr-only" htmlFor="cmp-q">{t("table.search")}</label>
          <input id="cmp-q" className="input w-40 py-1.5" placeholder={t("table.search")} value={q} onChange={(e) => setQ(e.target.value)} />
          <label className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-[var(--border)] px-2.5 py-1.5">
            <input type="checkbox" className="accent-brand-600" checked={onlyGaps} onChange={(e) => setOnlyGaps(e.target.checked)} /> {t("table.onlyGaps")}
          </label>
          <label className="sr-only" htmlFor="cmp-sort">{t("table.sort")}</label>
          <select id="cmp-sort" className="input w-auto py-1.5" value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
            <option value="gaps">{t("table.sort.gaps")}</option><option value="coverage">{t("table.sort.coverage")}</option><option value="az">{t("table.sort.az")}</option>
          </select>
        </div>
      </div>
      <div className="overflow-x-auto" tabIndex={0} role="region" aria-label={t("table.title")} onMouseLeave={() => setCol(null)}>
        <table className="w-full min-w-[720px] border-separate border-spacing-0 text-sm">
          <thead>
            <tr>
              <th scope="col" className="sticky left-0 z-10 bg-[var(--surface)] px-4 py-2 text-left text-xs font-medium muted">{t("table.fact")}</th>
              <th scope="col" className="px-3 py-2 text-left text-xs font-medium muted">{t("table.coverage")}</th>
              {rows.map((r, i) => (
                <th key={r.product_id} scope="col" onMouseEnter={() => setCol(i)} className={`px-3 py-2 text-left align-bottom font-semibold ${col === i ? "bg-[var(--surface-2)]" : ""}`}>
                  {r.is_you ? <span className="chip bg-[var(--accent)] text-white">{t("rank.you")}</span>
                    : r.url ? <a href={r.url} target="_blank" rel="noopener noreferrer" className="hover:underline">{short(r.title)}</a> : short(r.title)}
                  {!r.is_you && r.merchant && <span className="block text-xs font-normal muted">{r.merchant}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map(({ f, name: n, cover, gap }) => {
              const hot = gap && cover > 0;
              return (
                <tr key={f} className={hot ? "bg-amber-50/70 dark:bg-amber-950/20" : ""}>
                  <th scope="row" className={`sticky left-0 z-10 border-t border-[var(--border)] px-4 py-2 text-left font-medium ${hot ? "bg-amber-50 dark:bg-[#231d10]" : "bg-[var(--surface)]"}`}>
                    {n}{hot && <span className="chip ml-2 bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200">{t("table.gap")}</span>}
                  </th>
                  <td className="border-t border-[var(--border)] px-3 py-2">
                    <span className="flex items-center gap-2 text-xs tabular-nums"><span className="h-1.5 w-12 rounded-full bg-[var(--surface-2)]"><span className="block h-full rounded-full bg-[var(--chart-peer)]" style={{ width: `${(100 * cover) / (peers.length || 1)}%` }} /></span>{cover}/{peers.length}</span>
                  </td>
                  {rows.map((r, i) => {
                    const v = r.values[f];
                    return (
                      <td key={r.product_id} onMouseEnter={() => setCol(i)} className={`border-t border-[var(--border)] px-3 py-2 align-top ${col === i ? "bg-[var(--surface-2)]" : r.is_you ? "bg-[var(--accent-soft)]/60" : ""}`}>
                        {v !== undefined ? <span className="flex items-start gap-1.5"><Check className="mt-0.5 size-3.5 shrink-0 text-emerald-600" aria-label={t("table.listed")} /><span className="line-clamp-2">{fmtField(f, v, t)}</span></span>
                          : <span className="flex items-center gap-1.5 text-stone-400"><Minus className="size-3.5" aria-hidden />{t("table.notListed")}</span>}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
            {!shown.length && <tr><td colSpan={rows.length + 2} className="border-t border-[var(--border)] px-4 py-6 text-center text-sm muted">{t("table.none")}</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export function Leaderboard({ audit }: { audit: Audit }) {
  const { t } = useI18n();
  const [all, setAll] = useState(false);
  const board = audit.leaderboard;
  if (board.length < 2) return null;
  const youAt = board.findIndex((r) => r.is_you);
  const shown = all ? board.map((r, i) => [r, i] as const)
    : board.map((r, i) => [r, i] as const).filter(([, i]) => i < 3 || Math.abs(i - youAt) <= 1);
  return (
    <div>
      <ol className="space-y-1">
        {shown.map(([r, i], k) => (
          <li key={r.product_id}>
            {k > 0 && i - shown[k - 1][1] > 1 && <div className="py-1 text-center text-xs muted" aria-hidden>···</div>}
            <div className={`flex items-center gap-3 rounded-lg px-2 py-1.5 ${r.is_you ? "bg-brand-50 ring-1 ring-brand-200 dark:bg-brand-950/50 dark:ring-brand-800" : ""}`}>
              <span className="w-6 shrink-0 text-right text-sm font-semibold tabular-nums muted">{i + 1}</span>
              <span className="min-w-0 flex-1">
                {r.is_you ? <span className="text-sm font-semibold text-brand-700 dark:text-brand-300">{t("rank.you")}</span>
                  : r.url ? <a href={r.url} target="_blank" rel="noopener noreferrer" className="block truncate text-sm hover:underline">{r.title || r.product_id}</a>
                    : <span className="block truncate text-sm">{r.title || r.product_id}</span>}
                {!r.is_you && r.merchant && <span className="block truncate text-xs muted">{r.merchant}</span>}
              </span>
              <span className="shrink-0 text-sm font-medium tabular-nums">{r.score}</span>
            </div>
          </li>
        ))}
      </ol>
      {board.length > shown.length || all ? (
        <button className="mt-2 text-sm font-medium text-brand-600 hover:underline dark:text-brand-400" onClick={() => setAll(!all)} aria-expanded={all}>
          {all ? t("rank.showLess") : t("rank.showAll", { n: board.length })}
        </button>
      ) : null}
    </div>
  );
}
