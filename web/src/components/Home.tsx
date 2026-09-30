import { useEffect, useState, type FormEvent } from "react";
import { ArrowRight, Building2, CheckCircle2, FileText, KeyRound, Link2, Loader2, Pencil, Play, Plus, Share2, ShieldCheck, Trash2, UserPlus, XCircle } from "lucide-react";
import { ApiError, errorText, useI18n } from "../lib";
import { papi, productName, token, type Product, type Profile } from "../profile";
import AuditPage from "./AuditPage";

/** Logged-out home: sign-up / sign-in banner above the free single-product audit. */
export function Landing() {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const [tok, setTok] = useState("");
  const [err, setErr] = useState("");
  async function signIn(e: FormEvent) {
    e.preventDefault();
    token.set(tok.trim());
    try {
      await papi("/v1/profile");
      window.location.reload();
    } catch (x) {
      token.clear();
      setErr(x instanceof ApiError && x.status === 401 ? t("home.badToken") : errorText(x, t).msg);
    }
  }
  return (
    <>
      <section className="no-print mx-auto mt-6 max-w-5xl px-4">
        <div className="card flex flex-col gap-4 p-5 sm:flex-row sm:items-center">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-indigo-50 text-indigo-600 dark:bg-indigo-950 dark:text-indigo-300"><UserPlus className="size-5" aria-hidden /></span>
          <div className="flex-1">
            <h2 className="font-semibold">{t("home.signupTitle")}</h2>
            <p className="text-sm muted">{t("home.signupSub")}</p>
          </div>
          <div className="flex gap-2">
            <button className="btn-ghost" onClick={() => setOpen(!open)} aria-expanded={open}><KeyRound className="size-4" aria-hidden /> {t("home.signin")}</button>
            <a href="#/onboarding" className="btn-primary">{t("home.signup")} <ArrowRight className="size-4" aria-hidden /></a>
          </div>
        </div>
        {open && (
          <form onSubmit={signIn} className="card mt-2 flex flex-col gap-2 p-4 sm:flex-row">
            <label htmlFor="tok" className="sr-only">{t("home.tokenLabel")}</label>
            <input id="tok" className="input font-mono text-sm" autoComplete="off" value={tok} placeholder={t("home.tokenLabel")} onChange={(e) => setTok(e.target.value)} />
            <button className="btn-primary" disabled={!tok.trim()}>{t("home.signin")}</button>
            {err && <p role="alert" className="text-sm text-rose-600 sm:self-center">{err}</p>}
          </form>
        )}
      </section>
      <AuditPage />
    </>
  );
}

function Status({ p }: { p: Product }) {
  const { t } = useI18n();
  if (!p.audit) return <span className="chip bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">{t("home.notAudited")}</span>;
  return <span className="chip bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">{p.audit.rank.total > 1 ? t("rep.rank", { pos: p.audit.rank.position, total: p.audit.rank.total }) : t("rep.noPeers")}</span>;
}

/** Logged-in home. */
export function Dashboard({ onGone }: { onGone: () => void }) {
  const { t } = useI18n();
  const [prof, setProf] = useState<Profile | null>(null);
  const [busy, setBusy] = useState<Record<number, "run" | string>>({});
  const [url, setUrl] = useState("");
  const [msg, setMsg] = useState("");
  const [confirmDel, setConfirmDel] = useState(false);

  const load = () => papi<Profile>("/v1/profile").then(setProf).catch((e) => {
    if (e instanceof ApiError && e.status === 401) { token.clear(); onGone(); } else setMsg(errorText(e, t).msg);
  });
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function audit(ps: Product[]) {
    for (const p of ps) {
      setBusy((b) => ({ ...b, [p.id]: "run" }));
      try {
        const np = await papi<Product>(`/v1/profile/products/${p.id}/audit`, { method: "POST" });
        setProf((x) => x && { ...x, products: x.products.map((q) => (q.id === p.id ? np : q)) });
        setBusy((b) => { const { [p.id]: _, ...rest } = b; return rest; });
      } catch (e) {
        setBusy((b) => ({ ...b, [p.id]: errorText(e, t).msg }));
      }
    }
  }
  async function add(e: FormEvent) {
    e.preventDefault();
    if (!/^https?:\/\/[^\s/]+\.[^\s]+$/i.test(url.trim())) return setMsg(t("hero.invalidUrl"));
    try {
      await papi("/v1/profile/products", { method: "POST", body: JSON.stringify({ url: url.trim() }) });
      setUrl(""); setMsg(""); load();
    } catch (x) { setMsg(errorText(x, t).msg); }
  }
  async function removeProduct(id: number) {
    await papi(`/v1/profile/products/${id}`, { method: "DELETE" }).catch(() => undefined);
    load();
  }
  async function share(on: boolean) {
    await papi("/v1/profile/share", { method: on ? "POST" : "DELETE" }).catch((x) => setMsg(errorText(x, t).msg));
    load();
  }
  async function del() {
    await papi("/v1/profile", { method: "DELETE" });
    token.clear();
    onGone();
  }

  if (!prof) return <div className="grid place-items-center py-24" role="status">{msg || <Loader2 className="size-6 animate-spin" aria-label={t("home.loading")} />}</div>;
  const shareUrl = prof.share_token ? `${location.origin}${location.pathname}#/share/${prof.share_token}` : "";
  const pending = prof.products.filter((p) => !p.audit);

  return (
    <div className="mx-auto max-w-5xl space-y-6 px-4 py-10">
      <header className="flex flex-col gap-4 sm:flex-row sm:items-end">
        <div className="flex-1">
          <p className="muted">{prof.person.name ? t("home.hi", { name: prof.person.name }) : t("home.welcome")}</p>
          <h1 className="flex items-center gap-2 text-3xl font-extrabold tracking-tight"><Building2 className="size-7 text-indigo-500" aria-hidden />{prof.company.name}</h1>
          {prof.company.sells && <p className="mt-1 muted">{prof.company.sells}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          <a href="#/profile" className="btn-ghost"><Pencil className="size-4" aria-hidden /> {t("home.edit")}</a>
          <a href="#/report" className="btn-primary"><FileText className="size-4" aria-hidden /> {t("home.report")}</a>
        </div>
      </header>

      <section className="card p-5" aria-labelledby="h-products">
        <div className="flex flex-wrap items-center gap-2">
          <h2 id="h-products" className="mr-auto text-lg font-semibold">{t("home.products", { n: prof.products.length })}</h2>
          {pending.length > 0 && <button className="btn-primary" disabled={Object.values(busy).includes("run")} onClick={() => audit(pending)}><Play className="size-4" aria-hidden /> {t("home.auditAll", { n: pending.length })}</button>}
        </div>
        <ul className="mt-3 divide-y divide-slate-100 dark:divide-slate-800">
          {prof.products.map((p) => (
            <li key={p.id} className="flex flex-wrap items-center gap-3 py-3">
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium">{productName(p)}</p>
                <p className="flex flex-wrap items-center gap-2 text-xs muted">
                  {p.source === "manual" ? <span className="chip bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300">{t("label.merchantStated")}</span>
                    : <span className="flex items-center gap-1 truncate"><Link2 className="size-3" aria-hidden />{p.url}</span>}
                  {typeof busy[p.id] === "string" && busy[p.id] !== "run" && <span className="flex items-center gap-1 text-rose-600"><XCircle className="size-3" aria-hidden />{busy[p.id]}</span>}
                </p>
              </div>
              {busy[p.id] === "run" ? <Loader2 className="size-4 animate-spin" aria-label={t("home.auditing")} /> : p.audit ? <CheckCircle2 className="size-4 text-emerald-500" aria-hidden /> : null}
              <Status p={p} />
              <button className="btn-ghost px-2" disabled={busy[p.id] === "run"} onClick={() => audit([p])}>{p.audit ? t("home.reaudit") : t("home.audit")}</button>
              <button className="btn-ghost px-2" onClick={() => removeProduct(p.id)} aria-label={t("ob.removeProduct")}><Trash2 className="size-4" aria-hidden /></button>
            </li>
          ))}
        </ul>
        <form onSubmit={add} className="mt-3 flex flex-col gap-2 sm:flex-row">
          <label htmlFor="add-url" className="sr-only">{t("hero.urlLabel")}</label>
          <input id="add-url" type="url" className="input" value={url} placeholder={t("hero.placeholder")} onChange={(e) => setUrl(e.target.value)} />
          <button className="btn-ghost border border-slate-200 dark:border-slate-700"><Plus className="size-4" aria-hidden /> {t("home.add")}</button>
        </form>
        {msg && <p role="alert" className="mt-2 text-sm text-rose-600 dark:text-rose-400">{msg}</p>}
      </section>

      <div className="grid gap-6 sm:grid-cols-2">
        <section className="card p-5" aria-labelledby="h-share">
          <h2 id="h-share" className="flex items-center gap-2 font-semibold"><Share2 className="size-4" aria-hidden /> {t("share.title")}</h2>
          <p className="mt-1 text-sm muted">{t("share.sub")}</p>
          {prof.shared ? <>
            <input readOnly aria-label={t("share.title")} className="input mt-3 font-mono text-xs" value={shareUrl} onFocus={(e) => e.target.select()} />
            <button className="btn-ghost mt-2 px-2 text-rose-600" onClick={() => share(false)}>{t("share.revoke")}</button>
          </> : <button className="btn-ghost mt-3 border border-slate-200 dark:border-slate-700" onClick={() => share(true)}>{t("share.create")}</button>}
        </section>
        <section className="card p-5" aria-labelledby="h-priv">
          <h2 id="h-priv" className="flex items-center gap-2 font-semibold"><ShieldCheck className="size-4" aria-hidden /> {t("privacy.title")}</h2>
          <p className="mt-1 text-sm muted">{t("privacy.body")}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <button className="btn-ghost px-2" onClick={() => { token.clear(); onGone(); }}>{t("home.signout")}</button>
            {confirmDel ? <button className="btn px-3 bg-rose-600 text-white hover:bg-rose-500" onClick={del}>{t("privacy.confirm")}</button>
              : <button className="btn-ghost px-2 text-rose-600" onClick={() => setConfirmDel(true)}><Trash2 className="size-4" aria-hidden /> {t("privacy.delete")}</button>}
          </div>
        </section>
      </div>
    </div>
  );
}
