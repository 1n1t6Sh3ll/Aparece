import { useEffect, useRef, useState, type FormEvent } from "react";
import { AlertTriangle, ArrowRight, Check, FilePen, Link2, Loader2, Quote, Scale, ShieldCheck, Sparkles, Trophy } from "lucide-react";
import { api, errorText, useI18n } from "../lib";
import type { Audit } from "../types";
import Results from "./Results";

export const SAMPLES = [
  { label: "Organic Basics Flex Tee", url: "https://organicbasics.com/products/womens-organic-cotton-flex-tee-grey-melange" },
  { label: "Brava Fabrics Out of Office Tee", url: "https://bravafabrics.com/products/out-of-office-t-shirt-mint" },
  { label: "Sepiia Camiseta Soft", url: "https://sepiia.com/products/camiseta-hombre-cuello-redondo-negra-soft" },
];
const STEPS = ["steps.fetch", "steps.read", "steps.peers", "steps.compare", "steps.plan"];
export type AuditBody = { url?: string; title?: string; text?: string; price?: string; currency?: string; language?: string };

export function runAudit(body: AuditBody) {
  return api<Audit>("/v1/audit", { method: "POST", body: JSON.stringify(body) });
}

function Progress() {
  const { t } = useI18n();
  const [step, setStep] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setStep((s) => Math.min(s + 1, STEPS.length - 1)), 1400);
    return () => clearInterval(id);
  }, []);
  return (
    <div className="mx-auto max-w-5xl px-4 py-12 rise" role="status" aria-live="polite">
      <div className="card mx-auto max-w-xl p-6 sm:p-8">
        <ol className="space-y-4">
          {STEPS.map((k, i) => (
            <li key={k} className={`flex items-center gap-3 transition-opacity duration-500 ${i > step ? "opacity-40" : ""}`}>
              <span className={`grid size-8 shrink-0 place-items-center rounded-full border transition-colors duration-500 ${
                i < step ? "border-emerald-500 bg-emerald-500 text-white"
                  : i === step ? "border-indigo-500 text-indigo-600 dark:text-indigo-400" : "border-slate-300 dark:border-slate-700"}`}>
                {i < step ? <Check className="size-4" aria-hidden /> : i === step ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <span className="text-xs">{i + 1}</span>}
              </span>
              <span className={i === step ? "font-semibold" : ""}>{t(k)}</span>
            </li>
          ))}
        </ol>
        <div className="mt-6 h-1.5 overflow-hidden rounded-full bg-slate-100 dark:bg-slate-800">
          <div className="h-full rounded-full bg-gradient-to-r from-indigo-500 to-violet-500 transition-all duration-1000" style={{ width: `${((step + 1) / STEPS.length) * 92}%` }} />
        </div>
        <p className="mt-3 text-sm muted">{t("steps.wait")}</p>
      </div>
      <div className="mt-8 space-y-4" aria-hidden>
        <div className="card flex items-center gap-4 p-5"><div className="size-20 animate-pulse rounded-xl bg-slate-100 dark:bg-slate-800" /><div className="flex-1 space-y-2"><div className="h-3 w-1/4 animate-pulse rounded bg-slate-100 dark:bg-slate-800" /><div className="h-5 w-2/3 animate-pulse rounded bg-slate-100 dark:bg-slate-800" /></div></div>
        <div className="grid gap-4 sm:grid-cols-3">{[0, 1, 2].map((i) => <div key={i} className="card h-32 animate-pulse bg-slate-100/60 dark:bg-slate-800/40" />)}</div>
      </div>
    </div>
  );
}

const CURRENCIES = ["EUR", "USD", "GBP", "MXN"];

export default function AuditPage() {
  const { t, lang } = useI18n();
  const [mode, setMode] = useState<"url" | "draft">("url");
  const [url, setUrl] = useState("");
  const [draft, setDraft] = useState({ title: "", text: "", price: "", currency: "EUR", language: lang as string });
  const [state, setState] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [result, setResult] = useState<Audit | null>(null);
  const [err, setErr] = useState<{ msg: string; suggestText: boolean } | null>(null);
  const [formErr, setFormErr] = useState("");
  const [total, setTotal] = useState<number | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api<{ total: number }>("/v1/stats").then((s) => setTotal(s.total || null)).catch(() => setTotal(null));
    const q = new URLSearchParams(window.location.search).get("url");
    if (q) { setUrl(q); go({ url: q }); }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function go(body: AuditBody) {
    setState("loading"); setErr(null);
    window.scrollTo({ top: 0 });
    try {
      setResult(await runAudit(body));
      setState("done");
    } catch (e) {
      setErr(errorText(e, t)); setState("error");
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    setFormErr("");
    if (mode === "draft") {
      if (!draft.title.trim()) return setFormErr(t("hero.emptyTitle"));
      return go({ title: draft.title, text: draft.text, language: draft.language, ...(draft.price ? { price: draft.price, currency: draft.currency } : {}) });
    }
    const u = url.trim();
    if (!/^https?:\/\/[^\s/]+\.[^\s]+/i.test(u)) { setFormErr(t("hero.invalidUrl")); inputRef.current?.focus(); return; }
    go({ url: u });
  }

  if (state === "loading") return <Progress />;
  if (state === "done" && result) return <Results audit={result} onReset={() => { setState("idle"); setResult(null); }} />;

  const tab = (m: "url" | "draft", Icon: typeof Link2, label: string) => (
    <button type="button" role="tab" aria-selected={mode === m} onClick={() => { setMode(m); setFormErr(""); }}
      className={`flex flex-1 items-center justify-center gap-2 rounded-lg px-3 py-2 text-sm font-semibold transition sm:flex-none ${mode === m ? "bg-white text-slate-900 shadow-sm dark:bg-slate-800 dark:text-white" : "text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white"}`}>
      <Icon className="size-4" aria-hidden /> {label}
    </button>
  );

  return (
    <div className="relative overflow-hidden">
      <div aria-hidden className="pointer-events-none absolute inset-x-0 -top-40 -z-10 flex justify-center blur-3xl">
        <div className="h-96 w-[56rem] rounded-full bg-gradient-to-tr from-indigo-300/50 via-violet-300/40 to-sky-200/40 opacity-70 dark:from-indigo-700/30 dark:via-violet-700/20 dark:to-sky-800/20" />
      </div>
      <section className="mx-auto max-w-3xl px-4 pb-12 pt-14 text-center sm:pt-24">
        <p className="chip mx-auto mb-5 border border-indigo-200 bg-white/70 px-3 py-1 text-indigo-700 dark:border-indigo-900 dark:bg-indigo-950/50 dark:text-indigo-300">
          <Sparkles className="size-3.5" aria-hidden /> {t("hero.eyebrow")}
        </p>
        <h1 className="text-balance text-4xl font-extrabold tracking-tight sm:text-6xl">{t("hero.title")}</h1>
        <p className="mx-auto mt-5 max-w-2xl text-pretty text-lg muted">{t("hero.sub")}</p>

        {state === "error" && err && (
          <div role="alert" className="mx-auto mt-8 flex max-w-2xl gap-3 rounded-2xl border border-rose-200 bg-rose-50 p-4 text-left text-rose-900 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-200">
            <AlertTriangle className="mt-0.5 size-5 shrink-0" aria-hidden />
            <div>
              <p className="font-semibold">{t("err.title")}</p>
              <p className="mt-1 text-sm">{err.msg}</p>
              {err.suggestText && mode === "url" && (
                <button className="mt-2 text-sm font-semibold underline underline-offset-2" onClick={() => setMode("draft")}>{t("err.useText")}</button>
              )}
            </div>
          </div>
        )}

        <form onSubmit={submit} noValidate className="mx-auto mt-8 max-w-2xl text-left">
          <div role="tablist" className="mb-3 flex gap-1 rounded-xl bg-slate-200/60 p-1 sm:inline-flex dark:bg-slate-900">
            {tab("url", Link2, t("hero.tab.url"))}
            {tab("draft", FilePen, t("hero.tab.draft"))}
          </div>
          <div className="card p-2 shadow-xl shadow-indigo-900/5">
            {mode === "url" ? (
              <div className="flex flex-col gap-2 sm:flex-row">
                <label htmlFor="url" className="sr-only">{t("hero.urlLabel")}</label>
                <div className="relative flex-1">
                  <Link2 className="pointer-events-none absolute left-4 top-1/2 size-5 -translate-y-1/2 text-slate-400" aria-hidden />
                  <input ref={inputRef} id="url" type="url" inputMode="url" autoComplete="url" value={url} autoFocus
                    onChange={(e) => setUrl(e.target.value)} placeholder={t("hero.placeholder")}
                    aria-invalid={!!formErr} aria-describedby={formErr ? "form-err" : undefined}
                    className="input border-transparent pl-12 shadow-none focus:border-transparent focus:ring-0 dark:border-transparent" />
                </div>
                <button className="btn-primary px-6 py-3 text-base">{t("hero.cta")} <ArrowRight className="size-4" aria-hidden /></button>
              </div>
            ) : (
              <div className="grid gap-3 p-2 sm:grid-cols-4">
                <div className="sm:col-span-4">
                  <label htmlFor="d-title" className="text-sm font-medium">{t("hero.draftTitle")}</label>
                  <input id="d-title" className="input mt-1" value={draft.title} placeholder={t("hero.draftTitlePh")} maxLength={500}
                    aria-invalid={!!formErr} onChange={(e) => setDraft({ ...draft, title: e.target.value })} />
                </div>
                <div className="sm:col-span-4">
                  <label htmlFor="d-text" className="text-sm font-medium">{t("hero.draftText")}</label>
                  <textarea id="d-text" rows={6} className="input mt-1" value={draft.text} placeholder={t("hero.draftTextPh")}
                    onChange={(e) => setDraft({ ...draft, text: e.target.value })} />
                </div>
                <div className="sm:col-span-2">
                  <label htmlFor="d-price" className="text-sm font-medium">{t("hero.draftPrice")}</label>
                  <input id="d-price" inputMode="decimal" className="input mt-1" value={draft.price} placeholder="35.00"
                    onChange={(e) => setDraft({ ...draft, price: e.target.value.replace(/[^\d.,]/g, "").replace(",", ".") })} />
                </div>
                <div>
                  <label htmlFor="d-cur" className="text-sm font-medium">{t("hero.draftCurrency")}</label>
                  <select id="d-cur" className="input mt-1" value={draft.currency} onChange={(e) => setDraft({ ...draft, currency: e.target.value })}>
                    {CURRENCIES.map((c) => <option key={c}>{c}</option>)}
                  </select>
                </div>
                <div>
                  <label htmlFor="d-lang" className="text-sm font-medium">{t("hero.draftLang")}</label>
                  <select id="d-lang" className="input mt-1" value={draft.language} onChange={(e) => setDraft({ ...draft, language: e.target.value })}>
                    <option value="en">English</option><option value="es">Español</option><option value="de">Deutsch</option>
                  </select>
                </div>
                <div className="sm:col-span-4 flex justify-end"><button className="btn-primary w-full px-6 py-3 text-base sm:w-auto">{t("hero.cta")} <ArrowRight className="size-4" aria-hidden /></button></div>
              </div>
            )}
          </div>
          {formErr && <p id="form-err" role="alert" className="mt-2 text-sm text-rose-600 dark:text-rose-400">{formErr}</p>}
          {mode === "url" && (
            <div className="mt-4 flex flex-wrap items-center justify-center gap-2 text-sm">
              <span className="muted">{t("hero.try")}:</span>
              {SAMPLES.map((s) => (
                <button type="button" key={s.url} onClick={() => { setUrl(s.url); go({ url: s.url }); }}
                  className="rounded-full border border-slate-200 bg-white px-3 py-1 text-slate-700 transition hover:border-indigo-300 hover:text-indigo-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:border-indigo-700 dark:hover:text-indigo-300">
                  {s.label}
                </button>
              ))}
            </div>
          )}
        </form>
      </section>

      <section className="mx-auto grid max-w-5xl gap-4 px-4 pb-24 sm:grid-cols-3">
        {[
          { Icon: Trophy, title: t("rank.eyebrow"), d: t("rank.aiNote") },
          { Icon: Quote, title: t("hero.p1.t"), d: t("hero.p1.d") },
          { Icon: total ? Scale : ShieldCheck, title: total ? t("hero.p2.t") : t("hero.p3.t"), d: total ? t("hero.p2.d", { n: total.toLocaleString(lang) }) : t("hero.p3.d") },
        ].map(({ Icon, title, d }) => (
          <div key={title} className="card p-6">
            <span className="grid size-10 place-items-center rounded-xl bg-indigo-50 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-300"><Icon className="size-5" aria-hidden /></span>
            <h2 className="mt-4 font-semibold">{title}</h2>
            <p className="mt-1 text-sm muted">{d}</p>
          </div>
        ))}
      </section>
    </div>
  );
}
