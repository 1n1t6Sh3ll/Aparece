import { useState, type ReactNode } from "react";
import { AlertTriangle, ArrowLeft, ArrowRight, Check, Copy, KeyRound, Plus, Trash2 } from "lucide-react";
import { api, errorText, useI18n } from "../lib";
import { auditDefaults, CURRENCIES, emptyCompany, papi, token, type Company, type Person, type ProductIn, type Profile } from "../profile";
import { productLinks, refreshPrefill } from "../prefill";
import { useSession } from "../session";
import { useToast } from "../ui";

const PLATFORMS = ["", "shopify", "woocommerce", "magento", "bigcommerce", "custom", "other"] as const;
const POSITIONS = ["", "budget", "mid", "premium", "luxury"] as const;
const lines = (s: string) => s.split(/[\n,]+/).map((x) => x.trim()).filter(Boolean);
const URL_RE = /^https?:\/\/[^\s/]+\.[^\s]+$/i;

function Field({ id, label, hint, children }: { id: string; label: string; hint?: string; children: ReactNode }) {
  return (
    <div>
      <label htmlFor={id} className="text-sm font-medium">{label}</label>
      {hint && <p id={`${id}-hint`} className="text-xs muted">{hint}</p>}
      <div className="mt-1">{children}</div>
    </div>
  );
}

/** Create (3 steps) or edit (steps 1-2, PUT) the merchant profile. */
export default function Onboarding({ edit }: { edit?: Profile }) {
  const { t, lang } = useI18n();
  const { reload, switchTo } = useSession();
  const toast = useToast();
  const [step, setStep] = useState(0);
  const [person, setPerson] = useState<Person>(edit?.person ?? { name: "", role: "", about: "" });
  const c0 = edit ? { ...edit.company, claims: edit.company.claims.map((x) => x.text) } : emptyCompany();
  const [company, setCompany] = useState<Company>(c0);
  const [text, setText] = useState({ markets: c0.markets.join(", "), languages: c0.languages.join(", "),
    claims: c0.claims.join("\n"), competitors: c0.competitors.join("\n") });
  const [urls, setUrls] = useState("");
  const [manual, setManual] = useState<ProductIn[]>([]);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [newToken, setNewToken] = useState("");
  const [copied, setCopied] = useState(false);
  const steps = edit ? [t("ob.s1"), t("ob.s2")] : [t("ob.s1"), t("ob.s2"), t("ob.s3")];
  const setC = (k: keyof Company, v: string) => setCompany({ ...company, [k]: v });
  const def = auditDefaults({ website: company.website, languages: lines(text.languages), markets: lines(text.markets) }, lang);

  function body() {
    return { person, language: lang, company: { ...company, markets: lines(text.markets), languages: lines(text.languages),
      claims: text.claims.split("\n").map((x) => x.trim()).filter(Boolean), competitors: lines(text.competitors) } };
  }

  function next() {
    setErr("");
    if (step === 1) {
      if (!company.name.trim()) return setErr(t("ob.needName"));
      const bad = [company.website, ...lines(text.competitors)].filter((u) => u && !URL_RE.test(u));
      if (bad.length) return setErr(t("ob.badUrl", { url: bad[0] }));
      if (edit) return save();
    }
    if (step === 1) setUrls(refreshPrefill(urls, def.prefix));  // store URL prefills the links; an unedited old prefill is replaced
    setStep(step + 1);
  }

  async function save() {
    setBusy(true); setErr("");
    try {
      if (edit) {
        await papi("/v1/profile", { method: "PUT", body: JSON.stringify(body()) });
        await reload(); toast("ok", t("set.saved")); setBusy(false);
        return;
      }
      const list = productLinks(urls);  // bare <store>/products/ prefills are not products
      const bad = list.find((u) => !URL_RE.test(u));
      if (bad) { setBusy(false); return setErr(t("ob.badUrl", { url: bad })); }
      const products = [...list.map((url) => ({ url })), ...manual.filter((m) => m.title?.trim())];
      const r = await api<{ token: string }>("/v1/profile", { method: "POST", body: JSON.stringify({ ...body(), products }) });
      token.set(r.token, company.name);
      setNewToken(r.token);
    } catch (e) {
      setErr(errorText(e, t).msg);
    }
    setBusy(false);
  }

  if (newToken) {
    return (
      <div className="mx-auto max-w-xl py-8 rise">
        <div className="card p-6 sm:p-8">
          <span className="grid size-10 place-items-center rounded-xl bg-emerald-50 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-300"><KeyRound className="size-5" aria-hidden /></span>
          <h1 className="mt-4 text-2xl font-bold">{t("ob.tokenTitle")}</h1>
          <p className="mt-2 text-sm muted">{t("ob.tokenSub")}</p>
          <div className="mt-4 flex gap-2">
            <input readOnly aria-label={t("ob.tokenTitle")} className="input font-mono text-sm" value={newToken} onFocus={(e) => e.target.select()} />
            <button className="btn-ghost border border-stone-200 dark:border-stone-700" onClick={() => { navigator.clipboard?.writeText(newToken); setCopied(true); }}>
              {copied ? <Check className="size-4" aria-hidden /> : <Copy className="size-4" aria-hidden />} {copied ? t("ob.copied") : t("ob.copy")}
            </button>
          </div>
          <p className="mt-3 flex gap-2 text-sm text-amber-700 dark:text-amber-400"><AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />{t("ob.tokenWarn")}</p>
          <button className="btn-primary mt-6 w-full" onClick={() => switchTo(newToken)}>{t("ob.toDashboard")} <ArrowRight className="size-4" aria-hidden /></button>
        </div>
      </div>
    );
  }

  const inp = (k: keyof Company, id: string, ph?: string) => (
    <input id={id} className="input" value={company[k] as string} placeholder={ph} onChange={(e) => setC(k, e.target.value)} />
  );
  const txt = (k: keyof typeof text, id: string, rows = 2, ph?: string) => (
    <textarea id={id} rows={rows} className="input" value={text[k]} placeholder={ph} onChange={(e) => setText({ ...text, [k]: e.target.value })} />
  );

  return (
    <div className={edit ? "" : "mx-auto max-w-2xl py-4"}>
      {!edit && <h1 className="text-2xl font-bold tracking-tight">{t("ob.title")}</h1>}
      <p className="mt-2 muted">{t("ob.sub")}</p>
      <ol className="mt-6 flex gap-2" aria-label={t("ob.progress")}>
        {steps.map((s, i) => (
          <li key={s} aria-current={i === step ? "step" : undefined} className="flex-1">
            <div className={`h-1.5 rounded-full ${i <= step ? "bg-brand-500" : "bg-stone-200 dark:bg-stone-800"}`} />
            <p className={`mt-2 text-xs ${i === step ? "font-semibold" : "muted"}`}>{i + 1}. {s}</p>
          </li>
        ))}
      </ol>
      <div className="card mt-6 grid gap-4 p-5 sm:p-6">
        {step === 0 && <>
          <Field id="p-name" label={t("ob.name")}><input id="p-name" className="input" value={person.name} autoFocus onChange={(e) => setPerson({ ...person, name: e.target.value })} /></Field>
          <Field id="p-role" label={t("ob.role")}><input id="p-role" className="input" value={person.role} placeholder={t("ob.rolePh")} onChange={(e) => setPerson({ ...person, role: e.target.value })} /></Field>
          <Field id="p-about" label={t("ob.about")}><textarea id="p-about" rows={4} className="input" value={person.about} placeholder={t("ob.aboutPh")} onChange={(e) => setPerson({ ...person, about: e.target.value })} /></Field>
        </>}
        {step === 1 && <>
          <p className="rounded-xl bg-[var(--surface-2)] p-3 text-sm">{t("ob.whyCompany")}</p>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field id="c-name" label={t("ob.company") + " *"}>{inp("name", "c-name")}</Field>
            <Field id="c-web" label={t("ob.website")} hint={t("ob.websiteHint")}>{inp("website", "c-web", "https://")}</Field>
          </div>
          <Field id="c-sells" label={t("ob.sells")} hint={t("ob.sellsHint")}>{inp("sells", "c-sells", t("ob.sellsPh"))}</Field>
          <Field id="c-brand" label={t("ob.brand")}><textarea id="c-brand" rows={3} className="input" value={company.brand} onChange={(e) => setC("brand", e.target.value)} /></Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field id="c-markets" label={t("ob.markets")} hint={t("ob.marketsHint")}>{txt("markets", "c-markets", 1, "ES, US")}</Field>
            <Field id="c-langs" label={t("ob.languages")} hint={t("ob.languagesHint")}>{txt("languages", "c-langs", 1, "en, es")}</Field>
            <Field id="c-price" label={t("ob.price")}>
              <select id="c-price" className="input" value={company.price_positioning} onChange={(e) => setC("price_positioning", e.target.value)}>
                {POSITIONS.map((p) => <option key={p} value={p}>{t(`ob.price.${p || "none"}`)}</option>)}
              </select>
            </Field>
            <Field id="c-platform" label={t("ob.platform")}>
              <select id="c-platform" className="input" value={company.platform} onChange={(e) => setC("platform", e.target.value)}>
                {PLATFORMS.map((p) => <option key={p} value={p}>{t(`ob.platform.${p || "none"}`)}</option>)}
              </select>
            </Field>
          </div>
          <Field id="c-aud" label={t("ob.audience")}>{inp("audience", "c-aud")}</Field>
          <Field id="c-claims" label={t("ob.claims")} hint={t("ob.claimsHint")}>{txt("claims", "c-claims", 3)}</Field>
          <Field id="c-comp" label={t("ob.competitors")} hint={t("ob.competitorsHint")}>{txt("competitors", "c-comp", 2, "https://")}</Field>
        </>}
        {step === 2 && <>
          <Field id="pr-urls" label={t("ob.urls")} hint={t("ob.urlHint")}>
            <textarea id="pr-urls" rows={4} className="input font-mono text-sm" value={urls} placeholder="https://yourstore.com/products/..." onChange={(e) => setUrls(e.target.value)} />
          </Field>
          <div>
            <p className="text-sm font-medium">{t("ob.manual")}</p>
            <p className="text-xs muted">{t("ob.manualHint")}</p>
            {manual.map((m, i) => {
              const set = (k: keyof ProductIn, v: string) => setManual(manual.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
              return (
                <fieldset key={i} className="mt-3 grid gap-2 rounded-xl border border-dashed border-stone-300 p-3 dark:border-stone-700 sm:grid-cols-4">
                  <legend className="chip bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300">{t("label.merchantStated")}</legend>
                  <input aria-label={t("hero.draftTitle")} className="input sm:col-span-3" placeholder={t("hero.draftTitlePh")} value={m.title || ""} onChange={(e) => set("title", e.target.value)} />
                  <button type="button" className="btn-ghost" onClick={() => setManual(manual.filter((_, j) => j !== i))} aria-label={t("ob.removeProduct")}><Trash2 className="size-4" aria-hidden /></button>
                  <textarea aria-label={t("hero.draftText")} rows={3} className="input sm:col-span-4" placeholder={t("hero.draftTextPh")} value={m.text || ""} onChange={(e) => set("text", e.target.value)} />
                  <input aria-label={t("hero.draftPrice")} inputMode="decimal" className="input sm:col-span-2" placeholder="35.00" value={m.price || ""} onChange={(e) => set("price", e.target.value.replace(/[^\d.,]/g, "").replace(",", "."))} />
                  <select aria-label={t("hero.draftCurrency")} className="input" value={m.currency} onChange={(e) => set("currency", e.target.value)}>{CURRENCIES.map((c) => <option key={c}>{c}</option>)}</select>
                  <select aria-label={t("hero.draftLang")} className="input" value={m.language} onChange={(e) => set("language", e.target.value)}><option value="en">English</option><option value="es">Español</option></select>
                </fieldset>
              );
            })}
            <button type="button" className="btn-ghost mt-2 border border-stone-200 dark:border-stone-700" onClick={() => setManual([...manual, { currency: def.currency, language: def.language }])}>
              <Plus className="size-4" aria-hidden /> {t("ob.addManual")}
            </button>
          </div>
        </>}
        <p className="text-xs muted">{t("privacy.short")}</p>
        {err && <p role="alert" className="text-sm text-rose-600 dark:text-rose-400">{err}</p>}
        <div className="flex justify-between gap-2">
          {step > 0 ? <button type="button" className="btn-ghost" onClick={() => setStep(step - 1)}><ArrowLeft className="size-4" aria-hidden /> {t("ob.back")}</button>
            : <a href="#/" className="btn-ghost">{t("ob.cancel")}</a>}
          {step < steps.length - 1 ? <button type="button" className="btn-primary" onClick={next}>{t("ob.next")} <ArrowRight className="size-4" aria-hidden /></button>
            : <button type="button" className="btn-primary" disabled={busy} onClick={edit ? next : save}>{edit ? t("ob.save") : t("ob.create")} <Check className="size-4" aria-hidden /></button>}
        </div>
      </div>
    </div>
  );
}
