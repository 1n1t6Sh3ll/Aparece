import { useEffect, useState, type ReactNode } from "react";
import {
  ArrowLeft, BellRing, Bot, Check, ChevronDown, CircleHelp, ExternalLink, Eye, EyeOff, Gauge, ListChecks, Pencil,
  Quote, ScanSearch, ShieldCheck, Shirt, Sparkles, Tag, Trophy, Wand2,
} from "lucide-react";
import { api, cap, fieldLabel, fmtField, fmtValue, money, store, useI18n, type Lang, type T } from "../lib";
import type { Action, Audit, Label } from "../types";
import { CompareTable, Leaderboard, RankCard } from "./RankParts";

const LABEL_STYLE: Record<Label, string> = {
  OBSERVED_FACT: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-600/20 dark:bg-emerald-950/60 dark:text-emerald-300 dark:ring-emerald-400/20",
  SUPPORTED_HYPOTHESIS: "bg-amber-50 text-amber-700 ring-1 ring-amber-600/20 dark:bg-amber-950/60 dark:text-amber-300 dark:ring-amber-400/20",
  UNKNOWN: "bg-slate-100 text-slate-600 ring-1 ring-slate-500/20 dark:bg-slate-800 dark:text-slate-300",
};
const EFFORT_STYLE = { low: "text-emerald-700 dark:text-emerald-400", med: "text-amber-700 dark:text-amber-400", high: "text-rose-700 dark:text-rose-400" };

export function actionText(a: Action, audit: Audit, t: T, lang: Lang): { title: string; why: string; seo: string } {
  const ev = a.evidence as Record<string, number>;
  const label = a.field ? fieldLabel(lang, a.field) : "";
  const pp = audit.price_position;
  switch (a.kind) {
    case "missing_attribute":
      if (a.evidence.readable) {
        return { title: t("act.readable.t", { label }), why: t("act.readable.w", { label, c: ev.peers_with_attribute, n: ev.of }), seo: t("seo.markup") };
      }
      return { title: t("act.missing_attribute.t", { label }), why: t("act.missing_attribute.w", { label, c: ev.peers_with_attribute, n: ev.of }), seo: t("seo.safe") };
    case "description":
      return { title: t("act.description.t"), why: t("act.description.w", { t: ev.target_chars, m: Math.round(ev.peer_median_chars) }), seo: t("seo.safe") };
    case "structured_data": {
      const what = t(`sd.${(a.field || "").split(".").pop()}`);
      return { title: t("act.structured_data.t", { what }), why: ev.of ? t("act.structured_data.w", { what, c: ev.peers_present, n: ev.of }) : t("act.structured_data.w0", { what }), seo: t("seo.markup") };
    }
    case "price":
      return {
        title: t("act.price.t"), seo: t("seo.price"),
        why: t("act.price.w", { price: money(pp.price, pp.currency, lang), pos: t(`pos.${pp.position}`), n: ev.peer_count,
          lo: money(ev.p25, pp.currency, lang), hi: money(ev.p75, pp.currency, lang) }),
      };
    case "language":
      return { title: t("act.language.t"), why: t("act.language.w"), seo: t("seo.safe") };
    default:
      return { title: a.title, why: a.why, seo: a.seo_note };
  }
}

function Panel({ icon, title, sub, children, badge }: { icon: ReactNode; title: string; sub?: string; children: ReactNode; badge?: ReactNode }) {
  return (
    <section className="card p-5 sm:p-6 rise">
      <div className="flex items-start gap-3">
        <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-200">{icon}</span>
        <div className="min-w-0 flex-1">
          <h2 className="flex flex-wrap items-center gap-2 font-semibold">{title} {badge}</h2>
          {sub && <p className="mt-0.5 text-sm muted">{sub}</p>}
        </div>
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function usePersisted<V>(key: string, init: V): [V, (v: V) => void] {
  const [v, setV] = useState<V>(() => {
    try { return JSON.parse(store.get(key) || "null") ?? init; } catch { return init; }
  });
  return [v, (x: V) => { setV(x); store.set(key, JSON.stringify(x)); }];
}

function Bar({ label, you, peer, max, fmt }: { label: string; you: number; peer: number | null; max: number; fmt: (n: number) => string }) {
  const { t } = useI18n();
  const w = (n: number) => `${Math.max(2, Math.min(100, (100 * n) / (max || 1)))}%`;
  return (
    <div>
      <p className="text-sm font-medium">{label}</p>
      <div className="mt-2 space-y-1.5 text-xs">
        <div className="flex items-center gap-2">
          <span className="w-24 shrink-0 muted">{t("compare.you")}</span>
          <div className="h-2.5 flex-1 rounded-full bg-slate-100 dark:bg-slate-800"><div className="h-full rounded-full bg-indigo-500" style={{ width: w(you) }} /></div>
          <span className="w-20 shrink-0 text-right font-medium tabular-nums">{fmt(you)}</span>
        </div>
        {peer != null && (
          <div className="flex items-center gap-2">
            <span className="w-24 shrink-0 muted">{t("compare.peers")}</span>
            <div className="h-2.5 flex-1 rounded-full bg-slate-100 dark:bg-slate-800"><div className="h-full rounded-full bg-slate-400 dark:bg-slate-500" style={{ width: w(peer) }} /></div>
            <span className="w-20 shrink-0 text-right tabular-nums muted">{fmt(peer)}</span>
          </div>
        )}
      </div>
    </div>
  );
}

function ActionItem({ a, audit, done, toggle }: { a: Action; audit: Audit; done: boolean; toggle: () => void }) {
  const { t, lang } = useI18n();
  const [open, setOpen] = useState(false);
  const txt = actionText(a, audit, t, lang);
  const peerIds = (a.evidence.peer_ids as string[] | undefined) || [];
  const peerNames = peerIds.map((id) => audit.leaderboard.find((p) => p.product_id === id)?.title).filter(Boolean) as string[];
  const cid = `act-${a.id.replace(/\W/g, "-")}`;
  return (
    <li className={`rounded-xl border transition ${done ? "border-emerald-200 bg-emerald-50/40 dark:border-emerald-900/50 dark:bg-emerald-950/20" : "border-slate-200 dark:border-slate-800"}`}>
      <div className="flex items-start gap-3 p-4">
        <input id={cid} type="checkbox" checked={done} onChange={toggle}
          className="mt-1 size-5 shrink-0 cursor-pointer rounded accent-emerald-600" />
        <div className="min-w-0 flex-1">
          <label htmlFor={cid} className={`cursor-pointer font-medium ${done ? "text-slate-500 line-through dark:text-slate-500" : ""}`}>{txt.title}</label>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <span className="chip bg-indigo-50 text-indigo-700 ring-1 ring-indigo-600/20 dark:bg-indigo-950/60 dark:text-indigo-300 dark:ring-indigo-400/20">{t("res.prio", { n: a.priority })}</span>
            <span className={`chip ${LABEL_STYLE[a.label]}`}>{t(`res.label.${a.label}`)}</span>
            <span className={`chip ${EFFORT_STYLE[a.effort]}`}><Gauge className="size-3" aria-hidden /> {t(`res.effort.${a.effort}`)}</span>
          </div>
        </div>
        <button onClick={() => setOpen(!open)} aria-expanded={open} aria-controls={`${cid}-d`}
          className="btn-ghost shrink-0 p-2" aria-label={t("res.why")}>
          <ChevronDown className={`size-4 transition-transform ${open ? "rotate-180" : ""}`} aria-hidden />
        </button>
      </div>
      {open && (
        <div id={`${cid}-d`} className="space-y-3 border-t border-slate-200 px-4 py-4 text-sm dark:border-slate-800 sm:pl-12">
          <div><p className="font-semibold">{t("res.why")}</p><p className="mt-1 muted">{txt.why}</p></div>
          {peerNames.length > 0 && (
            <div><p className="font-semibold">{t("res.evidence")}</p>
              <ul className="mt-1 list-inside list-disc muted">{peerNames.slice(0, 5).map((n, i) => <li key={i}>{n}</li>)}</ul>
            </div>
          )}
          <p className="flex items-start gap-1.5 text-xs muted"><ShieldCheck className="mt-px size-3.5 shrink-0" aria-hidden /> <span><b>{t("res.seo")}:</b> {txt.seo}</span></p>
        </div>
      )}
    </li>
  );
}

function FactRow({ f, state, set }: { f: Audit["facts"][number]; state?: { s: "ok" | "fix"; note?: string }; set: (v: { s: "ok" | "fix"; note?: string } | undefined) => void }) {
  const { t, lang } = useI18n();
  const [editing, setEditing] = useState(false);
  const [note, setNote] = useState(state?.note || "");
  return (
    <li className="py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="text-sm muted">{cap(fieldLabel(lang, f.field).replace(/^(la|el|los|las) /, ""))}</span>
        <span className="flex items-center gap-1">
          {state?.s === "ok" ? (
            <span className="chip bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300"><Check className="size-3" aria-hidden /> {t("found.confirmed")}</span>
          ) : (
            <>
              <button className="rounded-md px-2 py-0.5 text-xs font-medium text-emerald-700 hover:bg-emerald-50 dark:text-emerald-400 dark:hover:bg-emerald-950" onClick={() => set({ s: "ok" })}>{t("found.confirm")}</button>
              <button className="rounded-md px-2 py-0.5 text-xs font-medium text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800" onClick={() => setEditing(!editing)} aria-expanded={editing}><Pencil className="inline size-3" aria-hidden /> {t("found.edit")}</button>
            </>
          )}
        </span>
      </div>
      <p className="mt-0.5 font-medium">{fmtField(f.field, f.value, t)}</p>
      {f.source_text && (
        <p className="mt-1 flex gap-1.5 text-xs muted"><Quote className="mt-px size-3 shrink-0" aria-hidden /><span className="line-clamp-2">“{f.source_text}”</span></p>
      )}
      {editing && (
        <form className="mt-2 flex gap-2" onSubmit={(e) => { e.preventDefault(); set({ s: "fix", note }); setEditing(false); }}>
          <label className="sr-only" htmlFor={`fix-${f.field}`}>{t("found.fixPlaceholder")}</label>
          <input id={`fix-${f.field}`} className="input py-1.5 text-sm" value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("found.fixPlaceholder")} />
          <button className="btn-primary px-3 py-1.5">{t("found.save")}</button>
        </form>
      )}
      {state?.s === "fix" && !editing && <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">{t("found.saved")}</p>}
    </li>
  );
}

function PriceScale({ audit }: { audit: Audit }) {
  const { t, lang } = useI18n();
  const pp = audit.price_position;
  if (!pp.available || pp.price == null || pp.p25 == null || pp.p75 == null || pp.median == null) {
    return <p className="text-sm muted">{pp.price == null || !pp.currency ? t("price.noPrice") : t("price.fewPeers")}</p>;
  }
  const lo = Math.min(pp.p25, pp.price) * 0.8, hi = Math.max(pp.p75, pp.price) * 1.15;
  const x = (v: number) => `${(100 * (v - lo)) / (hi - lo)}%`;
  const m = (v: number) => money(v, pp.currency, lang);
  return (
    <div>
      <div className="relative mt-8 h-3 rounded-full bg-slate-100 dark:bg-slate-800">
        <div className="absolute inset-y-0 rounded-full bg-indigo-200 dark:bg-indigo-900" style={{ left: x(pp.p25), right: `calc(100% - ${x(pp.p75)})` }} />
        <div className="absolute inset-y-[-3px] w-0.5 bg-slate-500" style={{ left: x(pp.median) }} title={t("price.median", { m: m(pp.median) })} />
        <div className="absolute -top-7 -translate-x-1/2 whitespace-nowrap text-xs font-semibold text-indigo-700 dark:text-indigo-300" style={{ left: x(pp.price) }}>
          {t("price.you")} {m(pp.price)}
        </div>
        <div className="absolute top-1/2 size-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-white bg-indigo-600 shadow dark:border-slate-900" style={{ left: x(pp.price) }} />
      </div>
      <p className="mt-3 text-sm">{t("price.range", { n: pp.peer_count ?? 0, lo: m(pp.p25), hi: m(pp.p75) })}</p>
      <p className="text-xs muted">{t("price.median", { m: m(pp.median) })}. {t("price.note")}</p>
    </div>
  );
}

function Enroll({ url }: { url: string }) {
  const { t } = useI18n();
  const [email, setEmail] = useState("");
  const [plans, setPlans] = useState<string[]>(["free"]);
  const [plan, setPlan] = useState("free");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => { api<{ plans: string[] }>("/v1/plans").then((p) => setPlans(p.plans)).catch(() => undefined); }, []);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return setMsg({ ok: false, text: t("mon.badEmail") });
    setBusy(true); setMsg(null);
    try {
      const r = await api<{ created: boolean }>("/v1/enroll", { method: "POST", body: JSON.stringify({ url, email: email || null, plan }) });
      setMsg({ ok: true, text: r.created ? t("mon.ok") : t("mon.exists") });
    } catch (e) {
      setMsg({ ok: false, text: t("err.generic", { detail: e instanceof Error ? e.message : String(e) }) });
    } finally { setBusy(false); }
  }
  return (
    <form onSubmit={submit} className="space-y-3">
      <div>
        <label htmlFor="mon-email" className="text-sm font-medium">{t("mon.email")}</label>
        <input id="mon-email" type="email" autoComplete="email" className="input mt-1 py-2" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@store.com" />
      </div>
      <div>
        <label htmlFor="mon-plan" className="text-sm font-medium">{t("mon.plan")}</label>
        <select id="mon-plan" className="input mt-1 py-2" value={plan} onChange={(e) => setPlan(e.target.value)}>
          {plans.map((p) => <option key={p} value={p}>{cap(p)}</option>)}
        </select>
      </div>
      <button className="btn-primary w-full" disabled={busy}><BellRing className="size-4" aria-hidden /> {t("mon.cta")}</button>
      {msg && (
        <p role="status" className={`text-sm ${msg.ok ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"}`}>
          {msg.text} {msg.ok && <a className="font-semibold underline" href="#/products">→</a>}
        </p>
      )}
    </form>
  );
}


export default function Results({ audit, onReset }: { audit: Audit; onReset: () => void }) {
  const { t, lang } = useI18n();
  const p = audit.product;
  const pid = p.product_id;
  const [done, setDone] = usePersisted<string[]>(`pl.done.${pid}`, []);
  const [facts, setFacts] = usePersisted<Record<string, { s: "ok" | "fix"; note?: string }>>(`pl.facts.${pid}`, {});
  const [imgOk, setImgOk] = useState(true);
  const acts = audit.actions;
  const top = acts.slice(0, 3);
  const comparable = audit.rank.total - 1;
  const cmp = audit.comparison;
  const s = audit.summary;
  const live = !!p.url && !p.url.includes("unknown.invalid");
  const toggle = (id: string) => setDone(done.includes(id) ? done.filter((x) => x !== id) : [...done, id]);

  return (
    <div className="mx-auto max-w-6xl px-4 py-8 sm:py-12">
      <button onClick={onReset} className="btn-ghost no-print -ml-3 mb-4"><ArrowLeft className="size-4" aria-hidden /> {t("res.new")}</button>

      {/* 1. Proof we read the right product */}
      <section className="card flex flex-col gap-5 p-5 sm:flex-row sm:items-center sm:p-6 rise">
        <div className="grid size-20 shrink-0 place-items-center overflow-hidden rounded-xl bg-slate-100 dark:bg-slate-800 sm:size-24">
          {p.image && imgOk ? <img src={p.image} alt={p.title || ""} referrerPolicy="no-referrer" onError={() => setImgOk(false)} className="size-full object-cover" />
            : <Shirt className="size-10 text-slate-400" aria-hidden />}
        </div>
        <div className="min-w-0 flex-1">
          {live && <p className="text-sm muted">{[p.brand, p.merchant].filter(Boolean).join(" · ")}</p>}
          <h1 className="mt-0.5 break-words text-xl font-bold tracking-tight sm:text-2xl">{p.title || p.url}</h1>
          <div className="mt-2 flex flex-wrap gap-2 text-xs">
            {p.draft && <span className="chip bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200">{t("draft.badge")}</span>}
            {p.price != null && <span className="chip bg-slate-100 dark:bg-slate-800"><Tag className="size-3" aria-hidden /> {money(p.price, p.currency, lang)}</span>}
            {audit.context.language && <span className="chip bg-slate-100 dark:bg-slate-800">{t("res.ctx.lang")}: {audit.context.language.toUpperCase()}</span>}
          </div>
          {p.draft && <p className="mt-2 text-xs muted">{t("draft.note")}</p>}
        </div>
        {live && (
          <a href={p.url!} target="_blank" rel="noopener noreferrer" className="btn-ghost self-start sm:self-center"><ExternalLink className="size-4" aria-hidden /> <span className="sr-only sm:not-sr-only">{p.merchant}</span></a>
        )}
      </section>

      {/* 2. Where you rank */}
      <div className="mt-6"><RankCard audit={audit} /></div>

      {/* 3. Headline answer: what to fix first */}
      <section className="mt-10 rise">
        <h2 className="text-3xl font-extrabold tracking-tight sm:text-4xl">
          {top.length === 0 ? t("res.headline0") : top.length === 3 ? t("res.headline") : top.length === 1 ? t("res.headline1") : t("res.headlineN", { n: top.length })}
        </h2>
        <p className="mt-2 text-lg muted">
          {cmp.of ? t("res.sentence", { facts: s.facts_found, of: s.attributes_checked, median: s.top_median_facts ?? 0 })
            : t("res.sentenceNoPeers", { facts: s.facts_found, of: s.attributes_checked })}
        </p>
        {top.length === 0 && <p className="mt-2 muted">{t("res.headline0.d")}</p>}
        {top.length > 0 && (
          <ol className="mt-6 grid gap-4 md:grid-cols-3">
            {top.map((a, i) => {
              const txt = actionText(a, audit, t, lang);
              return (
                <li key={a.id} className="card relative overflow-hidden p-5">
                  <span aria-hidden className="absolute right-4 top-1 text-6xl font-black text-slate-100 dark:text-slate-800">{i + 1}</span>
                  <div className="relative">
                    <span className={`chip ${LABEL_STYLE[a.label]}`}>{t(`res.label.${a.label}`)}</span>
                    <h3 className="mt-3 font-semibold leading-snug">{txt.title}</h3>
                    <p className="mt-2 text-sm muted">{txt.why}</p>
                    <p className={`mt-3 inline-flex items-center gap-1 text-xs font-medium ${EFFORT_STYLE[a.effort]}`}><Gauge className="size-3.5" aria-hidden /> {t(`res.effort.${a.effort}`)}</p>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
        <p className="mt-5 flex items-start gap-2 rounded-xl bg-indigo-50/70 p-4 text-sm text-indigo-900 dark:bg-indigo-950/40 dark:text-indigo-200">
          <ShieldCheck className="mt-0.5 size-4 shrink-0" aria-hidden /> {t("res.trust", { peers: comparable })}
        </p>
      </section>

      {/* 4. Side by side */}
      <div className="mt-10"><CompareTable audit={audit} /></div>

      {/* 5. Details */}
      <div className="mt-10 grid gap-6 lg:grid-cols-3">
        <div className="min-w-0 space-y-6 lg:col-span-2">
          {acts.length > 0 && (
            <Panel icon={<ListChecks className="size-5" aria-hidden />} title={t("res.plan")} sub={t("res.planSub")}
              badge={<span className="chip bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">{t("res.done", { done: done.filter((d) => acts.some((a) => a.id === d)).length, n: acts.length })}</span>}>
              <ul className="space-y-3">{acts.map((a) => <ActionItem key={a.id} a={a} audit={audit} done={done.includes(a.id)} toggle={() => toggle(a.id)} />)}</ul>
            </Panel>
          )}

          <Panel icon={<ScanSearch className="size-5" aria-hidden />} title={t("found.title")} sub={t("found.sub")}>
            {audit.facts.length ? (
              <>
                <ul className="divide-y divide-slate-100 dark:divide-slate-800">
                  {audit.facts.map((f) => <FactRow key={f.field} f={f} state={facts[f.field]} set={(v) => { const x = { ...facts }; if (v) x[f.field] = v; else delete x[f.field]; setFacts(x); }} />)}
                </ul>
                <p className="mt-3 text-xs muted">{t("found.localNote")}</p>
              </>
            ) : <p className="text-sm muted">{t("found.none")}</p>}
          </Panel>

          {audit.not_found.length > 0 && (
            <Panel icon={<EyeOff className="size-5" aria-hidden />} title={t("notfound.title")} sub={t("notfound.sub")}>
              <ul className="grid gap-2 sm:grid-cols-2">
                {audit.not_found.map((m) => (
                  <li key={m.field} className="rounded-xl border border-dashed border-slate-300 p-3 dark:border-slate-700">
                    <p className="text-sm font-medium">{cap(fieldLabel(lang, m.field).replace(/^(la|el|los|las) /, ""))}</p>
                    {m.of > 0 && <p className="text-xs muted">{t("notfound.peers", { c: m.peers_with, n: m.of })}</p>}
                    {m.predicted && (
                      <p className="mt-1.5 text-xs">
                        <span className="chip bg-violet-50 text-violet-700 ring-1 ring-violet-600/20 dark:bg-violet-950/60 dark:text-violet-300"><Wand2 className="size-3" aria-hidden /> {t("notfound.predicted")}</span>{" "}
                        {fmtValue(m.predicted.value)} ({Math.round(m.predicted.confidence * 100)}%). <span className="muted">{t("notfound.predictedNote")}</span>
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </Panel>
          )}
        </div>

        <aside className="min-w-0 space-y-6">
          {audit.leaderboard.length > 1 && (
            <Panel icon={<Trophy className="size-5" aria-hidden />} title={t("rank.board")} sub={t("rank.boardSub")}><Leaderboard audit={audit} /></Panel>
          )}

          {cmp.of > 0 && (
            <Panel icon={<Gauge className="size-5" aria-hidden />} title={t("compare.title")}>
              <div className="space-y-5">
                <Bar label={t("compare.facts")} you={cmp.facts.target} peer={cmp.facts.top_median} max={cmp.facts.of} fmt={(v) => `${v} / ${cmp.facts.of}`} />
                <Bar label={t("compare.desc")} you={cmp.description_chars.target} peer={cmp.description_chars.top_median}
                  max={Math.max(cmp.description_chars.target, cmp.description_chars.top_median || 0)} fmt={(v) => t("compare.chars", { n: Math.round(v) })} />
                <div><p className="text-sm font-medium">{t("compare.reviews")}</p>
                  <p className="mt-1 text-xs muted">{t("compare.reviewsVal", { you: cmp.reviews.target_has_rating ? t("compare.yes") : t("compare.no"), c: cmp.reviews.top_with_rating, n: cmp.of })}</p></div>
              </div>
            </Panel>
          )}

          <Panel icon={<Tag className="size-5" aria-hidden />} title={t("price.title")}><PriceScale audit={audit} /></Panel>

          <Panel icon={<Bot className="size-5" aria-hidden />} title={t("vis.title")}
            badge={!audit.visibility.available ? <span className="chip bg-violet-50 text-violet-700 dark:bg-violet-950/60 dark:text-violet-300"><Sparkles className="size-3" aria-hidden /> {t("vis.badge")}</span> : undefined}>
            <div className="rounded-xl border border-dashed border-slate-300 p-4 text-center text-sm muted dark:border-slate-700">
              <Eye className="mx-auto mb-2 size-6 text-slate-400" aria-hidden />{t("vis.empty")}
            </div>
          </Panel>

          <Panel icon={<CircleHelp className="size-5" aria-hidden />} title={t("unk.title")}>
            <ul className="space-y-2 text-sm muted">
              {["unk.1", "unk.2", "unk.3"].map((k) => <li key={k} className="flex gap-2"><span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-full bg-slate-400" />{t(k)}</li>)}
              {comparable > 0 && comparable < 3 && <li className="flex gap-2"><span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-full bg-amber-500" />{t("unk.fewPeers", { n: comparable })}</li>}
            </ul>
          </Panel>

          {live && (
            <Panel icon={<BellRing className="size-5" aria-hidden />} title={t("mon.title")} sub={t("mon.sub")}><Enroll url={p.url!} /></Panel>
          )}
        </aside>
      </div>
    </div>
  );
}
