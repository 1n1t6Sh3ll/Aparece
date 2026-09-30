import { useEffect, useState, type ReactNode } from "react";
import {
  BellRing, Bookmark, Radar, Check, ChevronDown, CircleHelp, ExternalLink, EyeOff, Gauge, ListChecks, Pencil, Printer,
  Quote, RotateCcw, ScanSearch, ShieldCheck, Shirt, Tag, Trophy, PenLine,
} from "lucide-react";
import { api, cap, fieldLabel, fmtField, fmtValue, money, store, useI18n, type Lang, type T } from "../lib";
import type { Action, Audit, Label } from "../types";
import { papi } from "../profile";
import { useSession } from "../session";
import { useToast } from "../ui";
import { PriceChart, RankChart, ScoreBreakdown } from "./Charts";
import { CompareTable, Tip } from "./RankParts";

const LABEL_STYLE: Record<Label, string> = {
  OBSERVED_FACT: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-600/20 dark:bg-emerald-950/60 dark:text-emerald-300 dark:ring-emerald-400/20",
  SUPPORTED_HYPOTHESIS: "bg-amber-50 text-amber-700 ring-1 ring-amber-600/20 dark:bg-amber-950/60 dark:text-amber-300 dark:ring-amber-400/20",
  UNKNOWN: "bg-stone-100 text-stone-600 ring-1 ring-stone-500/20 dark:bg-stone-800 dark:text-stone-300",
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

export function Panel({ icon, title, sub, children, badge, className = "" }: { icon: ReactNode; title: string; sub?: string; children: ReactNode; badge?: ReactNode; className?: string }) {
  return (
    <section className={`card p-4 sm:p-5 rise ${className}`}>
      <div className="flex items-start gap-3">
        <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-[var(--surface-2)] muted">{icon}</span>
        <div className="min-w-0 flex-1">
          <h2 className="flex flex-wrap items-center gap-2 text-sm font-semibold">{title} {badge}</h2>
          {sub && <p className="mt-0.5 text-xs muted">{sub}</p>}
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
  useEffect(() => {
    const on = (e: Event) => { if ((e as CustomEvent).detail === key) { try { setV(JSON.parse(store.get(key) || "null") ?? init); } catch { /* */ } } };
    window.addEventListener("pl-store", on);
    return () => window.removeEventListener("pl-store", on);
  }, [key]); // eslint-disable-line react-hooks/exhaustive-deps
  return [v, (x: V) => { setV(x); store.set(key, JSON.stringify(x)); window.dispatchEvent(new CustomEvent("pl-store", { detail: key })); }];
}

function ActionItem({ a, audit, done, toggle }: { a: Action; audit: Audit; done: boolean; toggle: () => void }) {
  const { t, lang } = useI18n();
  const [open, setOpen] = useState(false);
  const txt = actionText(a, audit, t, lang);
  const peerIds = (a.evidence.peer_ids as string[] | undefined) || [];
  const peerNames = peerIds.map((id) => audit.leaderboard.find((p) => p.product_id === id)?.title).filter(Boolean) as string[];
  const cid = `act-${a.id.replace(/\W/g, "-")}`;
  return (
    <li className={`rounded-xl border transition ${done ? "border-emerald-200 bg-emerald-50/40 dark:border-emerald-900/50 dark:bg-emerald-950/20" : "border-stone-200 dark:border-stone-800"}`}>
      <div className="flex items-start gap-3 p-4">
        <input id={cid} type="checkbox" checked={done} onChange={toggle}
          className="mt-1 size-5 shrink-0 cursor-pointer rounded accent-emerald-600" />
        <div className="min-w-0 flex-1">
          <label htmlFor={cid} className={`cursor-pointer font-medium ${done ? "text-stone-500 line-through dark:text-stone-500" : ""}`}>{txt.title}</label>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <span className="chip bg-brand-50 text-brand-700 ring-1 ring-brand-600/20 dark:bg-brand-950/60 dark:text-brand-300 dark:ring-brand-400/20">{t("res.prio", { n: a.priority })}</span>
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
        <div id={`${cid}-d`} className="space-y-3 border-t border-stone-200 px-4 py-4 text-sm dark:border-stone-800 sm:pl-12">
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
              <button className="rounded-md px-2 py-0.5 text-xs font-medium text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800" onClick={() => setEditing(!editing)} aria-expanded={editing}><Pencil className="inline size-3" aria-hidden /> {t("found.edit")}</button>
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

/** Sticky action checklist with progress (left column of the audit workspace). Ticks persist per product in this browser. */
export function Checklist({ audit }: { audit: Audit }) {
  const { t } = useI18n();
  const acts = audit.actions;
  const [done, setDone] = usePersisted<string[]>(`pl.done.${audit.product.product_id}`, []);
  const n = done.filter((d) => acts.some((a) => a.id === d)).length;
  const pct = acts.length ? Math.round((100 * n) / acts.length) : 100;
  const toggle = (id: string) => setDone(done.includes(id) ? done.filter((x) => x !== id) : [...done, id]);
  return (
    <section className="card p-4" aria-labelledby="plan-h">
      <div className="flex items-center justify-between gap-2">
        <h2 id="plan-h" className="flex items-center gap-2 text-sm font-semibold"><ListChecks className="size-4" aria-hidden /> {t("res.plan")}</h2>
        <span className="text-xs tabular-nums muted">{t("res.done", { done: n, n: acts.length })}</span>
      </div>
      <div className="mt-2 h-1.5 rounded-full bg-[var(--surface-2)]" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={t("res.plan")}>
        <div className="h-full rounded-full bg-emerald-500 transition-all duration-500" style={{ width: `${pct}%` }} />
      </div>
      {acts.length ? <ul className="mt-3 max-h-[55vh] space-y-2 overflow-y-auto pr-1">{acts.map((a) => <ActionItem key={a.id} a={a} audit={audit} done={done.includes(a.id)} toggle={() => toggle(a.id)} />)}</ul>
        : <p className="mt-3 text-sm muted">{t("res.headline0.d")}</p>}
      {acts.length > 0 && n === acts.length && <p className="mt-3 text-sm text-emerald-700 dark:text-emerald-400">{t("res.allDone")}</p>}
    </section>
  );
}

function SaveToProducts({ url }: { url: string }) {
  const { t } = useI18n();
  const { signedIn, profile, reload } = useSession();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const saved = profile?.products.some((p) => p.url === url);
  if (!signedIn) return <a href="#/onboarding" className="btn-outline"><Bookmark className="size-4" aria-hidden /> {t("ws.saveSignup")}</a>;
  return (
    <button className="btn-outline" disabled={busy || saved} onClick={async () => {
      setBusy(true);
      try {
        const p = await papi<{ id: number }>("/v1/profile/products", { method: "POST", body: JSON.stringify({ url }) });
        await papi(`/v1/profile/products/${p.id}/audit`, { method: "POST" }).catch(() => undefined);
        await reload();
        toast("ok", t("ws.saved"), { label: t("nav.products"), href: "#/products" });
      } catch (e) { toast("err", e instanceof Error ? e.message : String(e)); }
      setBusy(false);
    }}>
      {saved ? <Check className="size-4" aria-hidden /> : <Bookmark className="size-4" aria-hidden />} {saved ? t("ws.inProducts") : t("ws.save")}
    </button>
  );
}

/** Right-hand results of the audit workspace. */
export default function Results({ audit, onReset }: { audit: Audit; onReset: () => void }) {
  const { t, lang } = useI18n();
  const p = audit.product;
  const [facts, setFacts] = usePersisted<Record<string, { s: "ok" | "fix"; note?: string }>>(`pl.facts.${p.product_id}`, {});
  const [imgOk, setImgOk] = useState(true);
  const top = audit.actions.slice(0, 3);
  const comparable = audit.rank.total - 1;
  const cmp = audit.comparison;
  const s = audit.summary;
  const pp = audit.price_position;
  const live = !!p.url && !p.url.includes("unknown.invalid");

  return (
    <div className="min-w-0 space-y-5">
      <section className="card flex flex-col gap-4 p-4 sm:flex-row sm:items-center rise">
        <div className="grid size-16 shrink-0 place-items-center overflow-hidden rounded-lg bg-[var(--surface-2)]">
          {p.image && imgOk ? <img src={p.image} alt={p.title || ""} referrerPolicy="no-referrer" onError={() => setImgOk(false)} className="size-full object-cover" />
            : <Shirt className="size-8 text-stone-400" aria-hidden />}
        </div>
        <div className="min-w-0 flex-1">
          {live && <p className="text-xs muted">{[p.brand, p.merchant].filter(Boolean).join(" · ")}</p>}
          <h1 className="break-words text-lg font-bold tracking-tight">{p.title || p.url}</h1>
          <div className="mt-1.5 flex flex-wrap gap-1.5 text-xs">
            {p.draft && <span className="chip bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200">{t("draft.badge")}</span>}
            {p.price != null && <span className="chip bg-[var(--surface-2)]"><Tag className="size-3" aria-hidden /> {money(p.price, p.currency, lang)}</span>}
            {audit.context.language && <span className="chip bg-[var(--surface-2)]">{t("res.ctx.lang")}: {audit.context.language.toUpperCase()}</span>}
            <span className="chip bg-[var(--surface-2)]">{t("ws.dataset", { n: audit.context.dataset_size.toLocaleString(lang) })}</span>
          </div>
        </div>
        <div className="no-print flex flex-wrap gap-2">
          {live && <SaveToProducts url={p.url!} />}
          {live && <a href={p.url!} target="_blank" rel="noopener noreferrer" className="btn-ghost px-2.5" aria-label={t("ws.open")}><ExternalLink className="size-4" aria-hidden /></a>}
          <button className="btn-ghost px-2.5" onClick={() => window.print()} aria-label={t("rep.print")}><Printer className="size-4" aria-hidden /></button>
          <button className="btn-ghost px-2.5" onClick={onReset} aria-label={t("res.new")} title={t("res.new")}><RotateCcw className="size-4" aria-hidden /></button>
        </div>
      </section>

      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">
        <div className="card p-4">
          <p className="flex items-center gap-1.5 text-xs font-medium muted"><Trophy className="size-3.5" aria-hidden /> {t("rank.eyebrow")}</p>
          <p className="mt-1 text-2xl font-bold tabular-nums">{comparable > 0 ? <>#{audit.rank.position}<span className="text-sm font-medium muted"> / {audit.rank.total}</span></> : "–"}</p>
          <p className="text-xs muted">{comparable > 0 ? t("ws.amongN", { n: comparable }) : t("rank.alone")}</p>
        </div>
        <div className="card p-4">
          <p className="flex items-center gap-1.5 text-xs font-medium muted"><Gauge className="size-3.5" aria-hidden /> <Tip text={t("rank.formula", { wf: audit.rank.weights.facts, wd: audit.rank.weights.description, ref: Math.round(audit.rank.components.description_ref).toLocaleString(lang), sd: p.draft ? "" : t("rank.formulaSd", { ws: audit.rank.weights.structured_data }) })}>{t("ws.quality")}</Tip></p>
          <p className="mt-1 text-2xl font-bold tabular-nums">{audit.rank.score}<span className="text-sm font-medium muted">/100</span></p>
          <p className="text-xs muted">{t("rank.aiNote").split(".")[0]}.</p>
        </div>
        <div className="card p-4">
          <p className="flex items-center gap-1.5 text-xs font-medium muted"><ScanSearch className="size-3.5" aria-hidden /> {t("compare.facts")}</p>
          <p className="mt-1 text-2xl font-bold tabular-nums">{s.facts_found}<span className="text-sm font-medium muted"> / {s.attributes_checked}</span></p>
          <p className="text-xs muted">{cmp.of && s.top_median_facts != null ? t("ws.topMedian", { m: s.top_median_facts }) : t("ws.noCompare")}</p>
        </div>
        <div className="card p-4">
          <p className="flex items-center gap-1.5 text-xs font-medium muted"><Tag className="size-3.5" aria-hidden /> {t("price.title")}</p>
          <p className="mt-1 text-2xl font-bold">{pp.available && pp.position ? cap(t(`pos.${pp.position}`)) : "–"}</p>
          <p className="text-xs muted">{pp.available ? t("ws.middleHalf") : t("ws.noPrice")}</p>
        </div>
      </div>

      <section className="rise">
        <h2 className="text-xl font-bold tracking-tight">
          {top.length === 0 ? t("res.headline0") : top.length === 3 ? t("res.headline") : top.length === 1 ? t("res.headline1") : t("res.headlineN", { n: top.length })}
        </h2>
        <p className="mt-1 text-sm muted">
          {cmp.of ? t("res.sentence", { facts: s.facts_found, of: s.attributes_checked, median: s.top_median_facts ?? 0 }) : t("res.sentenceNoPeers", { facts: s.facts_found, of: s.attributes_checked })}
        </p>
        {top.length > 0 && (
          <ol className="mt-4 grid gap-3 md:grid-cols-3">
            {top.map((a, i) => {
              const txt = actionText(a, audit, t, lang);
              return (
                <li key={a.id} className="card relative overflow-hidden p-4">
                  <span aria-hidden className="absolute right-3 top-0 text-5xl font-black text-[var(--surface-2)]">{i + 1}</span>
                  <div className="relative">
                    <span className={`chip ${LABEL_STYLE[a.label]}`}>{t(`res.label.${a.label}`)}</span>
                    <h3 className="mt-2 text-sm font-semibold leading-snug">{txt.title}</h3>
                    <p className="mt-1.5 text-xs muted">{txt.why}</p>
                    <p className={`mt-2 inline-flex items-center gap-1 text-xs font-medium ${EFFORT_STYLE[a.effort]}`}><Gauge className="size-3.5" aria-hidden /> {t(`res.effort.${a.effort}`)}</p>
                  </div>
                </li>
              );
            })}
          </ol>
        )}
      </section>

      <div className="grid gap-5 xl:grid-cols-2">
        <Panel icon={<Trophy className="size-4" aria-hidden />} title={t("rank.board")} sub={t("rank.boardSub")}><RankChart audit={audit} /></Panel>
        <div className="space-y-5">
          <Panel icon={<Gauge className="size-4" aria-hidden />} title={t("ws.breakdown")} sub={t("rank.score", { s: audit.rank.score })}><ScoreBreakdown audit={audit} /></Panel>
          <Panel icon={<Tag className="size-4" aria-hidden />} title={t("price.title")}><PriceChart audit={audit} /></Panel>
        </div>
      </div>

      <CompareTable audit={audit} />

      <div className="grid gap-5 xl:grid-cols-2">
        <Panel icon={<ScanSearch className="size-4" aria-hidden />} title={t("found.title")} sub={t("found.sub")}>
          {audit.facts.length ? (
            <>
              <ul className="divide-y divide-[var(--border)]">
                {audit.facts.map((f) => <FactRow key={f.field} f={f} state={facts[f.field]} set={(v) => { const x = { ...facts }; if (v) x[f.field] = v; else delete x[f.field]; setFacts(x); }} />)}
              </ul>
              <p className="mt-3 text-xs muted">{t("found.localNote")}</p>
            </>
          ) : <p className="text-sm muted">{t("found.none")}</p>}
        </Panel>
        <div className="space-y-5">
          {audit.not_found.length > 0 && (
            <Panel icon={<EyeOff className="size-4" aria-hidden />} title={t("notfound.title")} sub={t("notfound.sub")}>
              <ul className="grid gap-2 sm:grid-cols-2">
                {audit.not_found.map((m) => (
                  <li key={m.field} className="rounded-lg border border-dashed border-[var(--border)] p-2.5">
                    <p className="text-sm font-medium">{cap(fieldLabel(lang, m.field).replace(/^(la|el|los|las) /, ""))}</p>
                    {m.of > 0 && <p className="text-xs muted">{t("notfound.peers", { c: m.peers_with, n: m.of })}</p>}
                    {m.predicted && (
                      <p className="mt-1.5 text-xs">
                        <span className="chip bg-brand-50 text-brand-700 ring-1 ring-brand-600/20 dark:bg-brand-950/60 dark:text-brand-300"><PenLine className="size-3" aria-hidden /> {t("notfound.predicted")}</span>{" "}
                        {fmtValue(m.predicted.value)} ({Math.round(m.predicted.confidence * 100)}%). <span className="muted">{t("notfound.predictedNote")}</span>
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            </Panel>
          )}
          <Panel icon={<Radar className="size-4" aria-hidden />} title={t("vis.title")}
            badge={!audit.visibility.available ? <span className="chip bg-brand-50 text-brand-700 dark:bg-brand-950/60 dark:text-brand-300">{t("vis.badge")}</span> : undefined}>
            <p className="text-sm muted">{audit.visibility.available ? t("ws.visAvail") : t("vis.empty")}</p>
            <a href="#/models" className="mt-2 inline-block text-sm font-medium text-[var(--accent)] hover:underline">{t("ws.visNext")}</a>
          </Panel>
          <Panel icon={<CircleHelp className="size-4" aria-hidden />} title={t("unk.title")}>
            <ul className="space-y-2 text-sm muted">
              {["unk.1", "unk.2", "unk.3"].map((k) => <li key={k} className="flex gap-2"><span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-full bg-stone-400" />{t(k)}</li>)}
              {comparable > 0 && comparable < 3 && <li className="flex gap-2"><span aria-hidden className="mt-2 size-1.5 shrink-0 rounded-full bg-amber-500" />{t("unk.fewPeers", { n: comparable })}</li>}
            </ul>
            <p className="mt-3 flex items-start gap-2 text-xs muted"><ShieldCheck className="mt-px size-3.5 shrink-0" aria-hidden /> {t("res.trust", { peers: comparable })}</p>
          </Panel>
          {live && <Panel icon={<BellRing className="size-4" aria-hidden />} title={t("mon.title")} sub={t("mon.sub")}><Enroll url={p.url!} /></Panel>}
        </div>
      </div>
    </div>
  );
}
