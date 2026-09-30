import { useEffect, useRef, useState, type FormEvent } from "react";
import { ArrowRight, Clock, FilePen, Layers, Link2, ScanSearch, Trash2 } from "lucide-react";
import { api, ApiError, errorText, store, useI18n } from "../lib";
import type { Audit } from "../types";
import { ErrorBox, useToast } from "../ui";
import Results, { Checklist } from "./Results";

/** Real live product pages (no sample data). Re-verified 2026-09-29 with POST /v1/audit: all return a real audit
 * ranked among 25 comparable shirts (robots.txt allows them, 200 in under 4 s).
 * Re-verify before changing; stores that rate-limited us (HTTP 429) were dropped. */
export const SAMPLES = [
  { label: "Mundo Domingo T-shirt", url: "https://mundodomingo.xyz/products/tacos-domingo-tee-white" },
  { label: "Brava Fabrics Out of Office Tee", url: "https://bravafabrics.com/products/out-of-office-t-shirt-mint" },
  { label: "Sepiia Camiseta Soft", url: "https://sepiia.com/products/camiseta-hombre-cuello-redondo-negra-soft" },
];
const STEPS = ["steps.fetch", "steps.read", "steps.peers", "steps.compare", "steps.plan"];
export type AuditBody = { url?: string; title?: string; description?: string; details?: string; text?: string; price?: string; currency?: string; language?: string };
type Recent = { url: string; title: string; score: number; pos: number; total: number; at: string };

export function runAudit(body: AuditBody) {
  return api<Audit>("/v1/audit", { method: "POST", body: JSON.stringify(body) });
}
export type Stored = { id: string | null; audit: Audit; record: Record<string, unknown> | null; notSaved?: number };
/** Audit and keep the result under a stable unlisted id (#/report/<id>). Falls back to a plain /v1/audit (no stable
 * link) on older servers (404/405) or when saving fails on our side (500/503), so a storage fault never blocks an audit. */
export async function runStoredAudit(body: AuditBody): Promise<Stored> {
  try {
    return await api<Stored>("/v1/audits", { method: "POST", body: JSON.stringify(body) });
  } catch (e) {
    const missingRoute = e instanceof ApiError && ((e.status === 404 && e.detail === "Not Found") || e.status === 405);
    if (missingRoute || (e instanceof ApiError && (e.status === 500 || e.status === 503))) return { id: null, audit: await runAudit(body), record: null };
    // our save limit: still show the audit (plain /v1/audit), only the stable link / history save is skipped
    if (e instanceof ApiError && e.status === 429) return { id: null, audit: await runAudit(body), record: null, notSaved: e.retryAfter || 60 };
    throw e;
  }
}
const recents = (): Recent[] => { try { return JSON.parse(store.get("pl.recent") || "[]"); } catch { return []; } };

/** Skeleton of the results pane, with the live step list. */
function Working() {
  const { t } = useI18n();
  const [step, setStep] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 1400);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="space-y-5" role="status" aria-live="polite">
      <p className="sr-only">{t(STEPS[step])}</p>
      <div className="card flex items-center gap-4 p-4"><div className="skeleton size-16" /><div className="flex-1 space-y-2"><div className="skeleton h-3 w-1/4" /><div className="skeleton h-5 w-2/3" /></div></div>
      <div className="grid grid-cols-2 gap-3 xl:grid-cols-4">{[0, 1, 2, 3].map((i) => <div key={i} className="card space-y-2 p-4"><div className="skeleton h-3 w-1/2" /><div className="skeleton h-7 w-1/3" /></div>)}</div>
      <div className="card p-4">
        <ol className="flex flex-wrap gap-x-5 gap-y-2 text-sm">
          {STEPS.map((k, i) => <li key={k} className={`flex items-center gap-2 ${i > step ? "opacity-40" : i === step ? "font-semibold" : "muted"}`}>
            <span className={`size-2 rounded-full ${i < step ? "bg-emerald-500" : i === step ? "animate-pulse bg-[var(--accent)]" : "bg-stone-300"}`} />{t(k)}</li>)}
        </ol>
        <p className="mt-2 text-xs muted">{t("steps.wait")}</p>
      </div>
      <div className="grid gap-5 xl:grid-cols-2"><div className="card h-64 p-4"><div className="skeleton h-full" /></div><div className="card h-64 p-4"><div className="skeleton h-full" /></div></div>
    </div>
  );
}

const CURRENCIES = ["EUR", "USD", "GBP", "MXN"];

/** Guided audit workspace: input and checklist on the left, live results on the right. */
export default function AuditPage({ reportId }: { reportId?: string }) {
  const { t, lang } = useI18n();
  const toast = useToast();
  const [mode, setMode] = useState<"url" | "draft">("url");
  const [url, setUrl] = useState("");
  const [draft, setDraft] = useState({ title: "", description: "", details: "", price: "", currency: "EUR", language: "" });
  const [state, setState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [result, setResult] = useState<Audit | null>(null);
  const [stored, setStored] = useState<{ id: string | null; record: Record<string, unknown> | null; notSaved?: number }>({ id: reportId || null, record: null });
  const [err, setErr] = useState<{ msg: string; suggestText: boolean; openDraft?: boolean } | null>(null);
  const [formErr, setFormErr] = useState("");
  const [recent, setRecent] = useState<Recent[]>(recents);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {  // stored audit links are unlisted: keep them out of search indexes
    if (!reportId) return;
    const m = document.createElement("meta");
    m.name = "robots"; m.content = "noindex, nofollow";
    document.head.appendChild(m);
    return () => m.remove();
  }, [reportId]);

  useEffect(() => {
    if (!reportId) return;
    setState("loading");
    api<Stored>(`/v1/audits/${encodeURIComponent(reportId)}`)
      .then((r) => { setResult(r.audit); setStored({ id: r.id, record: r.record }); setState("done"); })
      .catch((e) => { setErr(e instanceof ApiError && e.status === 404 ? { msg: t("ws.reportGone"), suggestText: false } : errorText(e, t)); setState("error"); });
  }, [reportId]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (reportId) return;
    const pending = sessionStorage.getItem("pl.pendingUrl") || new URLSearchParams(window.location.search).get("url");
    if (pending) { sessionStorage.removeItem("pl.pendingUrl"); setUrl(pending); go({ url: pending }); }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function go(body: AuditBody) {
    setState("loading"); setErr(null);
    try {
      const r = await runStoredAudit(body);
      const a = r.audit;
      setResult(a); setStored({ id: r.id, record: r.record, notSaved: r.notSaved }); setState("done");
      if (r.id) window.history.replaceState(null, "", `#/report/${r.id}`);  // stable link without remounting the workspace
      if (body.url) {
        const r: Recent = { url: body.url, title: a.product.title || body.url, score: a.rank.score, pos: a.rank.position ?? 0, total: a.rank.total, at: new Date().toISOString() };
        const next = [r, ...recents().filter((x) => x.url !== body.url)].slice(0, 8);
        store.set("pl.recent", JSON.stringify(next)); setRecent(next);
      }
      toast("ok", t("ws.doneToast", { n: a.actions.length }));
    } catch (e) {
      const x = errorText(e, t);
      setErr(x); setState("error");
      if (x.openDraft && body.url) {  // robots / Amazon / bot check: open the draft form with the link kept
        setMode("draft");
        setDraft((d) => ({ ...d, details: d.details || `${t("hero.draftSource")}: ${body.url}` }));
      }
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    setFormErr("");
    if (mode === "draft") {
      if (!draft.title.trim()) return setFormErr(t("hero.emptyTitle"));
      return go({ title: draft.title, description: draft.description, ...(draft.language ? { language: draft.language } : {}),
        ...(draft.details.trim() ? { details: draft.details } : {}), ...(draft.price ? { price: draft.price, currency: draft.currency } : {}) });
    }
    const u = url.trim();
    if (!/^https?:\/\/[^\s/]+\.[^\s]+/i.test(u)) { setFormErr(t("hero.invalidUrl")); inputRef.current?.focus(); return; }
    go({ url: u });
  }

  const tab = (m: "url" | "draft", Icon: typeof Link2, label: string) => (
    <button type="button" role="tab" aria-selected={mode === m} onClick={() => { setMode(m); setFormErr(""); }}
      className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-sm font-medium transition ${mode === m ? "bg-[var(--surface)] shadow-sm" : "muted hover:text-[var(--text)]"}`}>
      <Icon className="size-4" aria-hidden /> {label}
    </button>
  );

  return (
    <div className="mx-auto grid max-w-[1400px] gap-6 lg:grid-cols-[22rem_minmax(0,1fr)]">
      <div className="no-print space-y-4 lg:sticky lg:top-20 lg:self-start">
        <form onSubmit={submit} noValidate className="card p-4">
          <div role="tablist" className="flex gap-1 rounded-lg bg-[var(--surface-2)] p-1">
            {tab("url", Link2, t("hero.tab.url"))}
            {tab("draft", FilePen, t("hero.tab.draft"))}
            <a href="#/bulk" className="flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-sm font-medium muted hover:text-[var(--text)]"><Layers className="size-4" aria-hidden /> {t("ws.bulk")}</a>
          </div>
          {mode === "url" ? (
            <div className="mt-3 space-y-2">
              <label htmlFor="url" className="text-xs font-medium muted">{t("hero.urlLabel")}</label>
              <input ref={inputRef} id="url" data-focus-key type="url" inputMode="url" autoComplete="url" value={url} autoFocus
                onChange={(e) => setUrl(e.target.value)} placeholder={t("hero.placeholder")} aria-invalid={!!formErr} aria-describedby={formErr ? "form-err" : "url-hint"} className="input" />
              <p id="url-hint" className="text-xs muted">{t("ws.hint")} <kbd className="kbd">/</kbd></p>
            </div>
          ) : (
            <div className="mt-3 grid grid-cols-2 gap-2">
              <div className="col-span-2"><label htmlFor="d-title" className="text-xs font-medium muted">{t("hero.draftTitle")}</label>
                <input id="d-title" data-focus-key className="input mt-1" value={draft.title} placeholder={t("hero.draftTitlePh")} maxLength={500} aria-invalid={!!formErr} onChange={(e) => setDraft({ ...draft, title: e.target.value })} /></div>
              <div className="col-span-2"><label htmlFor="d-text" className="text-xs font-medium muted">{t("hero.draftText")}</label>
                <textarea id="d-text" rows={5} className="input mt-1" value={draft.description} placeholder={t("hero.draftTextPh")} onChange={(e) => setDraft({ ...draft, description: e.target.value })} /></div>
              <div className="col-span-2"><label htmlFor="d-details" className="text-xs font-medium muted">{t("hero.draftDetails")}</label>
                <textarea id="d-details" rows={2} className="input mt-1" value={draft.details} placeholder={t("hero.draftDetailsPh")} onChange={(e) => setDraft({ ...draft, details: e.target.value })} /></div>
              <div><label htmlFor="d-price" className="text-xs font-medium muted">{t("hero.draftPrice")}</label>
                <input id="d-price" inputMode="decimal" className="input mt-1" value={draft.price} placeholder="35.00" onChange={(e) => setDraft({ ...draft, price: e.target.value.replace(/[^\d.,]/g, "").replace(",", ".") })} /></div>
              <div><label htmlFor="d-cur" className="text-xs font-medium muted">{t("hero.draftCurrency")}</label>
                <select id="d-cur" className="input mt-1" value={draft.currency} onChange={(e) => setDraft({ ...draft, currency: e.target.value })}>{CURRENCIES.map((c) => <option key={c}>{c}</option>)}</select></div>
              <div className="col-span-2"><label htmlFor="d-lang" className="text-xs font-medium muted">{t("hero.draftLang")}</label>
                <select id="d-lang" className="input mt-1" value={draft.language} onChange={(e) => setDraft({ ...draft, language: e.target.value })}>
                  <option value="">{t("ws.langAuto")}</option><option value="en">English</option><option value="es">Español</option><option value="de">Deutsch</option></select></div>
            </div>
          )}
          {formErr && <p id="form-err" role="alert" className="mt-2 text-sm text-rose-600 dark:text-rose-400">{formErr}</p>}
          <button className="btn-primary mt-3 w-full" disabled={state === "loading"}>{t("hero.cta")} <ArrowRight className="size-4" aria-hidden /></button>
        </form>

        {state === "done" && result ? <Checklist audit={result} /> : (
          <section className="card p-4" aria-labelledby="recent-h">
            <div className="flex items-center justify-between">
              <h2 id="recent-h" className="flex items-center gap-2 text-sm font-semibold"><Clock className="size-4" aria-hidden /> {t("ws.recent")}</h2>
              {recent.length > 0 && <button className="btn-ghost p-1" onClick={() => { store.set("pl.recent", "[]"); setRecent([]); }} aria-label={t("ws.clearRecent")}><Trash2 className="size-3.5" aria-hidden /></button>}
            </div>
            {recent.length ? (
              <ul className="mt-2 space-y-1">
                {recent.map((r) => (
                  <li key={r.url}><button className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-[var(--surface-2)]" onClick={() => { setMode("url"); setUrl(r.url); go({ url: r.url }); }}>
                    <span className="min-w-0 flex-1 truncate">{r.title}</span><span className="text-xs tabular-nums muted">{r.score}</span></button></li>
                ))}
              </ul>
            ) : <p className="mt-2 text-xs muted">{t("ws.noRecent")}</p>}
          </section>
        )}
      </div>

      <div className="min-w-0">
        {state === "loading" && <Working />}
        {state === "done" && result?.unranked && (
          <p role="note" className="card mb-4 border-l-4 border-l-[var(--accent)] p-3 text-sm">
            {t(result.unranked.type ? "ws.unranked" : "ws.unrankedNoType", { type: result.unranked.type || "", from: result.unranked.read_from, read: result.unranked.read_text })}</p>
        )}
        {state === "done" && stored.notSaved && <p role="status" className="mb-3 text-xs muted">{t("ws.notSaved", { n: stored.notSaved })}</p>}
        {state === "done" && result && <Results audit={result} record={stored.record} reportId={stored.id} onReset={() => { setState("idle"); setResult(null); setStored({ id: null, record: null }); window.history.replaceState(null, "", "#/audit"); setTimeout(() => inputRef.current?.focus()); }} />}
        {state === "error" && err && (
          <ErrorBox title={t("err.title")} msg={err.msg}>
            {err.suggestText && <button className="btn-primary" onClick={() => { setMode("draft"); setTimeout(() => (document.getElementById("d-title") as HTMLInputElement | null)?.focus()); }}><FilePen className="size-4" aria-hidden /> {t("err.auditDraft")}</button>}
            {err.suggestText && <p className="w-full text-xs">{t("err.useExtension")}</p>}
            <button className="btn-outline" onClick={() => go({ url: SAMPLES[0].url })}><ArrowRight className="size-4" aria-hidden /> {t("ws.trySample")}</button>
          </ErrorBox>
        )}
        {state === "idle" && (
          <div className="card flex min-h-[28rem] flex-col items-center justify-center px-6 py-12 text-center">
            <span className="grid size-12 place-items-center rounded-xl bg-[var(--accent-soft)] text-[var(--accent)]"><ScanSearch className="size-6" aria-hidden /></span>
            <h1 className="mt-4 text-xl font-bold">{t("ws.emptyTitle")}</h1>
            <p className="mt-1 max-w-md text-sm muted">{t("ws.emptyBody")}</p>
            <div className="mt-5 flex flex-wrap justify-center gap-2">
              {SAMPLES.map((s) => <button key={s.url} className="btn-outline" onClick={() => { setMode("url"); setUrl(s.url); go({ url: s.url }); }}>{s.label}</button>)}
            </div>
            <p className="mt-6 text-xs muted">{t("ws.shortcuts")} <kbd className="kbd">?</kbd></p>
          </div>
        )}
      </div>
    </div>
  );
}
