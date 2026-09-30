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
        className="ml-1 rounded-full p-0.5 text-slate-400 hover:text-indigo-600 focus-visible:outline-2 focus-visible:outline-indigo-500 dark:hover:text-indigo-400">
        <Info className="size-3.5" aria-hidden />
      </button>
      {open && (
        <span role="tooltip" id={id} className="absolute left-1/2 top-full z-30 mt-2 w-64 -translate-x-1/2 rounded-lg bg-slate-900 p-3 text-xs font-normal leading-relaxed text-white shadow-xl dark:bg-slate-700">
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
  if (r.total <= 1) {
    return (
      <section className="card p-6 rise">
        <p className="text-sm font-semibold uppercase tracking-wide text-indigo-600 dark:text-indigo-400">{t("rank.eyebrow")}</p>
        <h2 className="mt-2 text-2xl font-bold">{t("rank.alone")}</h2>
        <p className="mt-1 muted">{t("rank.aloneD")}</p>
        {lang === "en" && (audit.notes || []).map((n) => <p key={n} className="mt-2 text-sm muted">{n}</p>)}
      </section>
    );
  }
  const rows = [
    { k: "facts", label: t("rank.facts"), tip: t("rank.factsTip", { w: w.facts }), p: c.points.facts, w: w.facts, detail: `${c.facts_stated} / ${c.facts_checked}` },
    { k: "description", label: t("rank.desc"), tip: t("rank.descTip", { w: w.description, ref: Math.round(c.description_ref).toLocaleString(lang) }), p: c.points.description, w: w.description, detail: t("compare.chars", { n: c.description_chars.toLocaleString(lang) }) },
    ...(draft ? [] : [{ k: "sd", label: t("rank.sd"), tip: t("rank.sdTip", { w: w.structured_data }), p: c.points.structured_data, w: w.structured_data, detail: `${c.structured_data_flags} / 2` }]),
  ];
  return (
    <section className="card overflow-hidden rise">
      <div className="grid gap-6 p-6 sm:p-8 md:grid-cols-[auto_1fr] md:items-center">
        <div className="flex items-center gap-5">
          <div className="relative grid size-28 shrink-0 place-items-center rounded-full bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-lg shadow-indigo-500/25">
            <div className="text-center leading-none">
              <span className="text-sm font-semibold opacity-80">#</span><span className="text-5xl font-extrabold tracking-tight">{r.position}</span>
            </div>
            <Trophy className="absolute -right-1 -top-1 size-8 rounded-full bg-white p-1.5 text-amber-500 shadow dark:bg-slate-900" aria-hidden />
          </div>
          <div>
            <p className="flex items-center text-sm font-semibold uppercase tracking-wide text-indigo-600 dark:text-indigo-400">
              {t("rank.eyebrow")}{draft && <span className="chip ml-2 bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200">{t("draft.badge")}</span>}
            </p>
            <h2 className="mt-1 text-2xl font-extrabold tracking-tight sm:text-3xl">#{r.position} {t("rank.of", { n: r.total })}</h2>
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
              <div className="mt-1.5 h-2 rounded-full bg-slate-100 dark:bg-slate-800" role="img" aria-label={`${x.label}: ${t("rank.pts", { p: x.p, w: x.w })}`}>
                <div className="h-full rounded-full bg-indigo-500 transition-all duration-700" style={{ width: `${(100 * x.p) / (x.w || 1)}%` }} />
              </div>
            </div>
          ))}
          {draft && <p className="text-xs muted">{t("rank.sd")}: {t("rank.sdDraft")}</p>}
        </div>
      </div>
      <div className="border-t border-slate-100 bg-slate-50/70 px-6 py-3 text-sm dark:border-slate-800 dark:bg-slate-900/60 sm:px-8">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <p className="muted">{t("rank.aiNote")}</p>
          <button className="inline-flex items-center gap-1 font-medium text-indigo-600 dark:text-indigo-400" aria-expanded={how} onClick={() => setHow(!how)}>
            {t("rank.how")} <ChevronDown className={`size-4 transition-transform ${how ? "rotate-180" : ""}`} aria-hidden />
          </button>
        </div>
        {how && <p className="mt-2 text-xs leading-relaxed muted">{t("rank.formula", { wf: w.facts, wd: w.description, ref: Math.round(c.description_ref).toLocaleString(lang),
          sd: draft ? "" : t("rank.formulaSd", { ws: w.structured_data }) })}</p>}
      </div>
    </section>
  );
}

export function CompareTable({ audit }: { audit: Audit }) {
  const { t, lang } = useI18n();
  const { fields, rows } = audit.table;
  if (rows.length < 2 || !fields.length) return null;
  const short = (s: string | null) => (s && s.length > 38 ? s.slice(0, 36) + "…" : s || "");
  return (
    <section className="card p-5 sm:p-6 rise">
      <h2 className="text-lg font-semibold">{t("table.title")}</h2>
      <p className="mt-0.5 text-sm muted">{t("table.sub")}</p>
      <div className="mt-4 -mx-5 overflow-x-auto sm:-mx-6" tabIndex={0} role="region" aria-label={t("table.title")}>
        <table className="w-full min-w-[640px] border-separate border-spacing-0 text-sm">
          <thead>
            <tr>
              <th scope="col" className="sticky left-0 z-10 bg-white px-5 py-2 text-left font-medium muted dark:bg-slate-900 sm:px-6">{t("table.fact")}</th>
              {rows.map((r) => (
                <th key={r.product_id} scope="col" className={`px-3 py-2 text-left align-bottom font-semibold ${r.is_you ? "text-indigo-700 dark:text-indigo-300" : ""}`}>
                  {r.is_you ? <span className="chip bg-indigo-600 text-white">{t("rank.you")}</span>
                    : r.url ? <a href={r.url} target="_blank" rel="noopener noreferrer" className="hover:underline">{short(r.title)}</a> : short(r.title)}
                  {!r.is_you && r.merchant && <span className="block text-xs font-normal muted">{r.merchant}</span>}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {fields.map((f) => (
              <tr key={f} className="group">
                <th scope="row" className="sticky left-0 z-10 border-t border-slate-100 bg-white px-5 py-2 text-left font-medium dark:border-slate-800 dark:bg-slate-900 sm:px-6">
                  {cap(fieldLabel(lang, f).replace(/^(la|el|los|las) /, ""))}
                </th>
                {rows.map((r) => {
                  const v = r.values[f];
                  const has = v !== undefined;
                  return (
                    <td key={r.product_id} className={`border-t border-slate-100 px-3 py-2 align-top dark:border-slate-800 ${r.is_you ? "bg-indigo-50/60 dark:bg-indigo-950/30" : ""}`}>
                      {has ? (
                        <span className="flex items-start gap-1.5"><Check className="mt-0.5 size-3.5 shrink-0 text-emerald-600" aria-label={t("table.listed")} /><span className="line-clamp-2">{fmtField(f, v, t)}</span></span>
                      ) : (
                        <span className="flex items-center gap-1.5 text-slate-400"><Minus className="size-3.5" aria-hidden />{t("table.notListed")}</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
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
            <div className={`flex items-center gap-3 rounded-lg px-2 py-1.5 ${r.is_you ? "bg-indigo-50 ring-1 ring-indigo-200 dark:bg-indigo-950/50 dark:ring-indigo-800" : ""}`}>
              <span className="w-6 shrink-0 text-right text-sm font-semibold tabular-nums muted">{i + 1}</span>
              <span className="min-w-0 flex-1">
                {r.is_you ? <span className="text-sm font-semibold text-indigo-700 dark:text-indigo-300">{t("rank.you")}</span>
                  : r.url ? <a href={r.url} target="_blank" rel="noopener noreferrer" className="block truncate text-sm hover:underline">{r.title || r.product_id}</a>
                    : <span className="block truncate text-sm">{r.title || r.product_id}</span>}
                {!r.is_you && (r.merchant || r.link_unverified) && <span className="block truncate text-xs muted">
                  {[r.merchant, r.link_unverified && t("rank.linkUnverified")].filter(Boolean).join(" · ")}</span>}
              </span>
              <span className="shrink-0 text-sm font-medium tabular-nums">{r.score}</span>
            </div>
          </li>
        ))}
      </ol>
      {board.length > shown.length || all ? (
        <button className="mt-2 text-sm font-medium text-indigo-600 hover:underline dark:text-indigo-400" onClick={() => setAll(!all)} aria-expanded={all}>
          {all ? t("rank.showLess") : t("rank.showAll", { n: board.length })}
        </button>
      ) : null}
    </div>
  );
}
