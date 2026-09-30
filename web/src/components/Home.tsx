import { useEffect, useMemo, useState, type FormEvent } from "react";
import {
  Aperture, ArrowRight, BarChart3, Building2, CheckCircle2, Puzzle, FileText, Globe, KeyRound, Link2, ListChecks, Loader2, Moon,
  Package, Play, Plus, Quote, ScanSearch, Search, ShieldCheck, Sun, Trash2, TriangleAlert, UserPlus, PenLine, XCircle,
} from "lucide-react";
import { allManageTokens, api, ApiError, errorText, fieldLabel, money, useI18n } from "../lib";
import { history, type Monitored } from "../history";
import { auditDefaults, papi, productName, token, type Product } from "../profile";
import { isBarePrefix } from "../prefill";
import { useSession } from "../session";
import { Empty, ErrorBox, PageHeader, Stat, Tabs, useTheme, useToast } from "../ui";
import { ProductsPage as Monitoring } from "./Monitor";
import { SAMPLES } from "./AuditPage";

/** Send a URL to the audit page (it runs on arrival). */
const start = (u: string) => { sessionStorage.setItem("pl.pendingUrl", u); window.location.hash = "/audit"; };

/** Logged-out marketing landing (no app shell). */
export function Landing() {
  const { t, lang, setLang } = useI18n();
  const [theme, toggle] = useTheme();
  const [url, setUrl] = useState("");
  const [err, setErr] = useState("");
  const [total, setTotal] = useState<number | null>(null);
  useEffect(() => { api<{ total: number }>("/v1/stats").then((s) => setTotal(s.total || null)).catch(() => undefined); }, []);
  function submit(e: FormEvent) {
    e.preventDefault();
    if (!/^https?:\/\/[^\s/]+\.[^\s]+/i.test(url.trim())) return setErr(t("hero.invalidUrl"));
    start(url.trim());
  }
  const features = [
    { Icon: ScanSearch, k: "audit" }, { Icon: BarChart3, k: "rank" }, { Icon: ListChecks, k: "plan" },
    { Icon: PenLine, k: "suggest" }, { Icon: FileText, k: "report" }, { Icon: Puzzle, k: "ext" },
  ];
  return (
    <div className="min-h-screen bg-[var(--surface)]">
      <header className="sticky top-0 z-20 border-b border-[var(--border)] bg-[var(--surface)]">
        <nav className="mx-auto flex h-16 max-w-6xl items-center gap-2 px-4" aria-label={t("nav.menu")}>
          <a href="#/" className="mr-auto flex items-center gap-2 font-bold tracking-tight">
            <span className="grid size-8 place-items-center rounded-lg bg-[var(--accent)] text-white"><Aperture className="size-5" aria-hidden /></span>ProductLens
          </a>
          <a href="#features" onClick={(e) => { e.preventDefault(); document.getElementById("features")?.scrollIntoView({ behavior: "smooth" }); }} className="btn-ghost hidden sm:inline-flex">{t("land.nav.features")}</a>
          <a href="#/models" className="btn-ghost hidden sm:inline-flex">{t("nav.models")}</a>
          <button className="btn-ghost p-2" onClick={() => setLang(lang === "en" ? "es" : "en")} aria-label={t("nav.lang")}><Globe className="size-4" aria-hidden /><span className="text-xs">{lang === "en" ? "ES" : "EN"}</span></button>
          <button className="btn-ghost p-2" onClick={toggle} aria-label={t("kb.theme")}>{theme === "dark" ? <Sun className="size-4" aria-hidden /> : <Moon className="size-4" aria-hidden />}</button>
          <a href="#/signin" className="btn-ghost">{t("home.signin")}</a>
          <a href="#/onboarding" className="btn-primary">{t("home.signup")}</a>
        </nav>
      </header>

      <section className="mx-auto grid max-w-6xl gap-10 px-4 pb-16 pt-14 sm:pt-20 lg:grid-cols-[1.15fr_1fr] lg:items-center">
        <div>
          <p className="eyebrow">{t("hero.eyebrow")}</p>
          <h1 className="mt-4 text-balance text-4xl leading-[1.05] sm:text-6xl">{t("land.title")}</h1>
          <p className="mt-5 max-w-xl text-pretty text-lg muted">{t("land.sub")}</p>
          <form onSubmit={submit} noValidate className="mt-8 flex max-w-xl flex-col gap-2 sm:flex-row">
            <label htmlFor="land-url" className="sr-only">{t("hero.urlLabel")}</label>
            <div className="relative flex-1">
              <Link2 className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 muted" aria-hidden />
              <input id="land-url" data-focus-key type="url" value={url} onChange={(e) => { setUrl(e.target.value); setErr(""); }} placeholder={t("hero.placeholder")}
                aria-invalid={!!err} className="input py-3 pl-9 text-base" />
            </div>
            <button className="btn-primary px-5 py-3 text-base">{t("hero.cta")} <ArrowRight className="size-4" aria-hidden /></button>
          </form>
          {err && <p role="alert" className="mt-2 text-sm text-rose-700">{err}</p>}
          <div className="mt-4 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm">
            <span className="muted">{t("hero.try")}:</span>
            {SAMPLES.map((s) => <button key={s.url} className="underline decoration-[var(--border)] underline-offset-4 hover:decoration-[var(--accent)]" onClick={() => start(s.url)}>{s.label}</button>)}
          </div>
          <p className="mt-6 text-sm muted">{t("land.free")}</p>
        </div>
        <figure className="card overflow-hidden" aria-label={t("land.checks")}>
          <figcaption className="border-b border-[var(--border)] bg-[var(--surface-2)] px-4 py-2.5">
            <span className="eyebrow">{t("land.checks")}</span>
          </figcaption>
          <ul className="divide-y divide-[var(--border)] text-sm">
            {["identity.brand", "materials.material_percentages", "materials.fabric_weight_gsm", "fit_and_style.fit", "fit_and_style.neckline", "variants.sizes", "variants.colors", "commerce.price", "commerce.gtin"].map((f) => (
              <li key={f} className="px-4 py-2">{fieldLabel(lang, f)}</li>
            ))}
          </ul>
          <p className="border-t border-[var(--border)] px-4 py-2.5 text-xs muted">{t("land.checks.note")}</p>
        </figure>
      </section>

      <section className="border-y border-[var(--border)] bg-[var(--bg)]">
        <dl className="mx-auto grid max-w-5xl grid-cols-2 gap-6 px-4 py-8 text-center sm:grid-cols-4">
          {[[total ? total.toLocaleString(lang) : "–", t("land.stat.products")], ["22", t("land.stat.facts")], ["EN · ES", t("land.stat.langs")], ["0", t("land.stat.invented")]].map(([v, l]) => (
            <div key={l}><dt className="text-xs muted">{l}</dt><dd className="mt-1 text-2xl font-bold tabular-nums">{v}</dd></div>
          ))}
        </dl>
      </section>

      <section id="features" className="mx-auto max-w-6xl px-4 py-20">
        <h2 className="text-center text-3xl font-bold tracking-tight">{t("land.features")}</h2>
        <p className="mx-auto mt-2 max-w-2xl text-center muted">{t("land.featuresSub")}</p>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {features.map(({ Icon, k }) => (
            <div key={k} className="card p-6">
              <span className="grid size-10 place-items-center rounded-xl bg-[var(--accent-soft)] text-[var(--accent)]"><Icon className="size-5" aria-hidden /></span>
              <h3 className="mt-4 font-semibold">{t(`land.f.${k}.t`)}</h3>
              <p className="mt-1 text-sm muted">{t(`land.f.${k}.d`)}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="bg-[var(--bg)] py-20">
        <div className="mx-auto max-w-5xl px-4">
          <h2 className="text-center text-3xl font-bold tracking-tight">{t("land.how")}</h2>
          <ol className="mt-10 grid gap-6 sm:grid-cols-3">
            {[1, 2, 3].map((n) => (
              <li key={n} className="card p-6">
                <span className="grid size-8 place-items-center rounded-full bg-[var(--accent)] text-sm font-bold text-white">{n}</span>
                <h3 className="mt-4 font-semibold">{t(`land.how.${n}.t`)}</h3><p className="mt-1 text-sm muted">{t(`land.how.${n}.d`)}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="mx-auto max-w-5xl px-4 py-20">
        <div className="card grid gap-6 p-8 md:grid-cols-[auto_1fr] md:items-center">
          <span className="grid size-14 place-items-center rounded-2xl bg-emerald-50 text-emerald-600 dark:bg-emerald-950 dark:text-emerald-300"><ShieldCheck className="size-7" aria-hidden /></span>
          <div>
            <h2 className="text-2xl font-bold tracking-tight">{t("land.honest")}</h2>
            <ul className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
              {[1, 2, 3, 4].map((n) => <li key={n} className="flex gap-2"><Quote className="mt-0.5 size-4 shrink-0 text-emerald-600" aria-hidden />{t(`land.honest.${n}`)}</li>)}
            </ul>
          </div>
        </div>
      </section>

      <section className="border-t border-[var(--border)] bg-[var(--bg)] py-16 text-center">
        <h2 className="text-2xl font-bold tracking-tight">{t("land.cta")}</h2>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          <a href="#/onboarding" className="btn-primary px-6 py-3"><UserPlus className="size-4" aria-hidden /> {t("home.signup")}</a>
          <a href="#/audit" className="btn-outline px-6 py-3"><ScanSearch className="size-4" aria-hidden /> {t("land.tryApp")}</a>
        </div>
        <p className="mt-8 text-xs muted">{t("footer")}</p>
      </section>
    </div>
  );
}

/** Sign in with an access key (adds the company to the switcher). */
export function SignIn() {
  const { t } = useI18n();
  const { switchTo } = useSession();
  const toast = useToast();
  const [tok, setTok] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true); setErr("");
    try {
      const r = await fetch("/v1/profile", { headers: { "X-Profile-Token": tok.trim() } });
      if (r.status === 401) throw new ApiError(401, "bad");
      const p = await r.json();
      token.set(tok.trim(), p.company?.name);
      switchTo(tok.trim());
      toast("ok", t("si.ok", { name: p.company?.name || "" }));
    } catch (x) {
      setErr(x instanceof ApiError && x.status === 401 ? t("home.badToken") : errorText(x, t).msg);
    }
    setBusy(false);
  }
  return (
    <div className="mx-auto max-w-md py-10">
      <div className="card p-6">
        <span className="grid size-10 place-items-center rounded-xl bg-[var(--accent-soft)] text-[var(--accent)]"><KeyRound className="size-5" aria-hidden /></span>
        <h1 className="mt-4 text-xl font-bold">{t("si.title")}</h1>
        <p className="mt-1 text-sm muted">{t("si.sub")}</p>
        <form onSubmit={submit} className="mt-5 space-y-3">
          <label htmlFor="tok" className="text-xs font-medium muted">{t("home.tokenLabel")}</label>
          <input id="tok" data-focus-key autoFocus className="input font-mono" autoComplete="off" value={tok} onChange={(e) => setTok(e.target.value)} />
          {err && <p role="alert" className="text-sm text-rose-600">{err}</p>}
          <button className="btn-primary w-full" disabled={!tok.trim() || busy}>{busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null} {t("home.signin")}</button>
        </form>
        <p className="mt-4 text-center text-sm muted">{t("si.none")} <a className="font-semibold text-[var(--accent)] hover:underline" href="#/onboarding">{t("home.signup")}</a></p>
      </div>
    </div>
  );
}

/** Audit one or more profile products, updating the shared session as each finishes. */
function useAuditRunner() {
  const { t } = useI18n();
  const { updateProduct } = useSession();
  const toast = useToast();
  const [busy, setBusy] = useState<Record<number, "run" | string>>({});
  async function run(ps: Product[]) {
    let ok = 0;
    for (const p of ps) {
      setBusy((b) => ({ ...b, [p.id]: "run" }));
      try {
        updateProduct(await papi<Product>(`/v1/profile/products/${p.id}/audit`, { method: "POST" }));
        setBusy((b) => { const { [p.id]: _, ...rest } = b; return rest; });
        ok++;
      } catch (e) {
        setBusy((b) => ({ ...b, [p.id]: errorText(e, t).msg }));
      }
    }
    toast(ok === ps.length ? "ok" : "err", t("run.done", { ok, n: ps.length }));
  }
  return { busy, run, running: Object.values(busy).includes("run") };
}

const rankText = (p: Product, t: (k: string, x?: Record<string, string | number>) => string) =>
  !p.audit ? t("home.notAudited") : p.audit.rank.total > 1 ? t("rep.rank", { pos: p.audit.rank.position ?? 0, total: p.audit.rank.total }) : t("rep.noPeers");

/** Logged-in home: KPIs, products needing attention, next steps. */
export function Overview() {
  const { t, lang } = useI18n();
  const { profile, loading, error } = useSession();
  const { busy, run, running } = useAuditRunner();
  if (loading && !profile) return <div className="grid gap-3 sm:grid-cols-4">{[0, 1, 2, 3].map((i) => <div key={i} className="card space-y-2 p-4"><div className="skeleton h-3 w-1/2" /><div className="skeleton h-7 w-1/3" /></div>)}</div>;
  if (!profile) return <ErrorBox title={t("err.title")} msg={error ? t("err.loadProfile") : t("home.badToken")}><a className="btn-outline" href="#/signin">{t("home.signin")}</a></ErrorBox>;
  const ps = profile.products;
  const audited = ps.filter((p) => p.audit);
  const avg = audited.length ? Math.round(audited.reduce((s, p) => s + p.audit!.rank.score, 0) / audited.length) : null;
  const open = audited.reduce((s, p) => s + p.audit!.actions.length, 0);
  const pending = ps.filter((p) => !p.audit);
  const worst = [...audited].sort((a, b) => a.audit!.rank.score - b.audit!.rank.score).slice(0, 5);
  const missing: Record<string, number> = {};
  audited.forEach((p) => p.audit!.not_found.forEach((m) => { missing[m.field] = (missing[m.field] || 0) + 1; }));
  const topMissing = Object.entries(missing).sort((a, b) => b[1] - a[1]).slice(0, 5);
  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title={profile.person.name ? t("home.hi", { name: profile.person.name }) : profile.company.name} sub={profile.company.sells || profile.company.name}>
        <a href="#/audit" className="btn-outline"><ScanSearch className="size-4" aria-hidden /> {t("nav.audit")}</a>
        <a href="#/reports" className="btn-primary"><FileText className="size-4" aria-hidden /> {t("home.report")}</a>
      </PageHeader>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat icon={<Package className="size-3.5" aria-hidden />} label={t("ov.products")} value={ps.length} sub={t("ov.audited", { n: audited.length })} />
        <Stat icon={<BarChart3 className="size-3.5" aria-hidden />} label={t("rep.avg")} value={avg ?? "–"} sub={avg != null ? "/100" : t("ov.runFirst")} />
        <Stat icon={<ListChecks className="size-3.5" aria-hidden />} label={t("ov.open")} value={open} sub={t("ov.openSub")} />
        <Stat icon={<ShieldCheck className="size-3.5" aria-hidden />} label={t("share.title")} value={profile.shared ? t("ov.on") : t("ov.off")} sub={<a className="text-[var(--accent)] hover:underline" href="#/settings">{t("nav.settings")}</a>} />
      </div>

      {pending.length > 0 && (
        <div className="card mt-5 flex flex-col gap-3 border-brand-200 bg-[var(--accent-soft)] p-4 sm:flex-row sm:items-center dark:border-brand-900">
          <Play className="size-5 text-[var(--accent)]" aria-hidden />
          <p className="flex-1 text-sm"><b>{t("ov.pending", { n: pending.length })}</b> {t("ov.pendingSub")}</p>
          <button className="btn-primary" disabled={running} onClick={() => run(pending)}>{running ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <Play className="size-4" aria-hidden />} {t("home.auditAll", { n: pending.length })}</button>
        </div>
      )}

      <div className="mt-5 grid grid-cols-1 gap-5 lg:grid-cols-3">
        <section className="card lg:col-span-2" aria-labelledby="ov-worst">
          <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-3">
            <h2 id="ov-worst" className="text-sm font-semibold">{t("ov.attention")}</h2>
            <a href="#/products" className="text-xs font-medium text-[var(--accent)] hover:underline">{t("ov.all")}</a>
          </div>
          {worst.length ? (
            <ul className="divide-y divide-[var(--border)]">
              {worst.map((p) => (
                <li key={p.id} className="flex items-center gap-3 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <a href="#/products" className="block truncate text-sm font-medium hover:underline">{productName(p)}</a>
                    <p className="truncate text-xs muted">{p.audit!.actions[0] ? t("ov.next", { f: p.audit!.actions[0].field ? fieldLabel(lang, p.audit!.actions[0].field) : p.audit!.actions[0].kind }) : t("rep.noFixes")}</p>
                  </div>
                  <span className="text-xs muted">{rankText(p, t)}</span>
                  <span className="w-20"><span className="block h-1.5 rounded-full bg-[var(--surface-2)]"><span className="block h-full rounded-full bg-[var(--chart-you)]" style={{ width: `${p.audit!.rank.score}%` }} /></span></span>
                  <span className="w-8 text-right text-sm font-semibold tabular-nums">{p.audit!.rank.score}</span>
                  {busy[p.id] === "run" && <Loader2 className="size-4 animate-spin" aria-hidden />}
                </li>
              ))}
            </ul>
          ) : <div className="p-4"><Empty icon={<Package className="size-6" aria-hidden />} title={t("ov.noAudits")} body={t("ov.noAuditsBody")}><a href="#/products" className="btn-primary"><Plus className="size-4" aria-hidden /> {t("home.add")}</a></Empty></div>}
        </section>
        <section className="card p-4" aria-labelledby="ov-miss">
          <h2 id="ov-miss" className="text-sm font-semibold">{t("ov.missing")}</h2>
          <p className="mt-0.5 text-xs muted">{t("ov.missingSub")}</p>
          {topMissing.length ? (
            <ul className="mt-3 space-y-2.5">
              {topMissing.map(([f, n]) => (
                <li key={f} className="text-sm">
                  <div className="flex justify-between"><span>{fieldLabel(lang, f)}</span><span className="tabular-nums muted">{n}/{audited.length}</span></div>
                  <div className="mt-1 h-1.5 rounded-full bg-[var(--surface-2)]"><div className="h-full rounded-full bg-amber-500" style={{ width: `${(100 * n) / audited.length}%` }} /></div>
                </li>
              ))}
            </ul>
          ) : <p className="mt-3 text-sm muted">{t("ov.runFirst")}</p>}
          <a href="#/chat" className="btn-outline mt-4 w-full">{t("ov.ask")}</a>
        </section>
      </div>
    </div>
  );
}

type SortK = "name" | "score" | "fixes";

/** Product photo from the audited page (hot-linked, no referrer), or a neutral placeholder. */
function Thumb({ src }: { src?: string | null }) {
  const [ok, setOk] = useState(true);
  return (
    <span className="grid size-9 shrink-0 place-items-center overflow-hidden rounded-sm bg-[var(--surface-2)]">
      {src && ok ? <img src={src} alt="" loading="lazy" referrerPolicy="no-referrer" onError={() => setOk(false)} className="size-full object-cover" /> : <Package className="size-4 muted" aria-hidden />}
    </span>
  );
}

/** My products: the company's catalogue (audits, add, remove) and monitored pages. */
export function ProductsHub() {
  const { t, lang } = useI18n();
  const { signedIn, profile, reload } = useSession();
  const toast = useToast();
  const [tab, setTab] = useState<"catalog" | "monitor">(signedIn ? "catalog" : "monitor");
  const { busy, run, running } = useAuditRunner();
  const prefix = profile ? auditDefaults(profile.company, lang).prefix : "";  // store URL prefills the product-link field
  const [url, setUrl] = useState("");
  useEffect(() => { if (prefix) setUrl((u) => u || prefix); }, [prefix]);
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<SortK>("score");
  const [msg, setMsg] = useState("");
  const [tracked, setTracked] = useState<Record<string, string>>({});  // page URL -> monitored public id
  const loadTracked = () => api<{ results: Monitored[] }>("/v1/monitored", { headers: { "X-Manage-Token": allManageTokens() } })
    .then((r) => setTracked(Object.fromEntries(r.results.map((m) => [m.url, m.id])))).catch(() => undefined);
  useEffect(() => { loadTracked(); }, []);
  const [tracking, setTracking] = useState<number | null>(null);
  async function track(p: Product) {
    setTracking(p.id);
    try { const id = await history.enroll(p.url!); toast("ok", t("pr.tracking")); window.location.hash = `/products/${encodeURIComponent(id)}`; }
    catch (x) { toast("err", errorText(x, t).msg); }
    setTracking(null);
  }
  const rows = useMemo(() => {
    const ps = (profile?.products || []).filter((p) => productName(p).toLowerCase().includes(q.toLowerCase()) || (p.url || "").includes(q));
    const score = (p: Product) => p.audit?.rank.score ?? -1;
    return ps.sort((a, b) => sort === "name" ? productName(a).localeCompare(productName(b), lang) : sort === "score" ? score(a) - score(b) : (b.audit?.actions.length ?? -1) - (a.audit?.actions.length ?? -1));
  }, [profile, q, sort, lang]);

  async function add(e: FormEvent) {
    e.preventDefault();
    if (isBarePrefix(url) || !/^https?:\/\/[^\s/]+\.[^\s]+$/i.test(url.trim())) return setMsg(t("hero.invalidUrl"));
    try {
      const p = await papi<Product>("/v1/profile/products", { method: "POST", body: JSON.stringify({ url: url.trim() }) });
      setUrl(prefix); setMsg(""); await reload();
      toast("info", t("pr.added"));
      run([p]);
    } catch (x) { setMsg(errorText(x, t).msg); }
  }
  async function remove(p: Product) {
    if (!window.confirm(t("pr.confirmRemove", { name: productName(p) }))) return;
    await papi(`/v1/profile/products/${p.id}`, { method: "DELETE" }).catch(() => undefined);
    await reload();
    toast("ok", t("pr.removed"));
  }
  const pending = rows.filter((p) => !p.audit);
  const rivals = profile?.company.competitors ?? [];
  const th = (k: SortK, label: string, cls = "") => (
    <th scope="col" className={`px-4 py-2 font-medium ${cls}`} aria-sort={sort === k ? "ascending" : undefined}>
      <button className="hover:text-[var(--text)]" onClick={() => setSort(k)}>{label}{sort === k ? " ↑" : ""}</button>
    </th>
  );

  return (
    <div className="mx-auto max-w-6xl">
      <PageHeader title={t("nav.products")} sub={t("pr.sub")}>
        <Tabs label={t("nav.products")} value={tab} onChange={setTab} items={[["catalog", t("pr.catalog")], ["monitor", t("pr.monitor")]]} />
      </PageHeader>
      {tab === "monitor" ? <Monitoring embedded /> : !signedIn ? (
        <Empty icon={<Building2 className="size-6" aria-hidden />} title={t("pr.signupTitle")} body={t("home.signupSub")}>
          <a href="#/onboarding" className="btn-primary"><UserPlus className="size-4" aria-hidden /> {t("home.signup")}</a><a href="#/signin" className="btn-outline">{t("home.signin")}</a>
        </Empty>
      ) : (
        <section className="card">
          <div className="flex flex-col gap-2 border-b border-[var(--border)] p-3 sm:flex-row sm:items-center">
            <div className="relative sm:w-64"><Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-stone-400" aria-hidden />
              <label htmlFor="pr-q" className="sr-only">{t("table.search")}</label>
              <input id="pr-q" className="input py-1.5 pl-8" placeholder={t("table.search")} value={q} onChange={(e) => setQ(e.target.value)} /></div>
            <form onSubmit={add} className="flex flex-1 gap-2">
              <label htmlFor="add-url" className="sr-only">{t("hero.urlLabel")}</label>
              <input id="add-url" data-focus-key type="url" className="input py-1.5" value={url} placeholder={t("hero.placeholder")} onChange={(e) => setUrl(e.target.value)} />
              <button className="btn-outline shrink-0"><Plus className="size-4" aria-hidden /> {t("home.add")}</button>
            </form>
            {pending.length > 0 && <button className="btn-primary" disabled={running} onClick={() => run(pending)}><Play className="size-4" aria-hidden /> {t("home.auditAll", { n: pending.length })}</button>}
          </div>
          {msg && <p role="alert" className="px-4 pt-2 text-sm text-rose-600">{msg}</p>}
          {rivals.length > 0 && (
            <p className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-[var(--border)] px-4 py-2 text-xs">
              <span className="muted">{t("pr.auditCompetitor")}:</span>
              {rivals.slice(0, 5).map((u) => <button key={u} className="max-w-[14rem] truncate underline decoration-[var(--border)] underline-offset-4 hover:decoration-[var(--accent)]" onClick={() => start(u)}>{u.replace(/^https?:\/\/(www\.)?/, "").replace(/\/$/, "")}</button>)}
            </p>
          )}
          {rows.length ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-sm">
                <thead className="text-left text-xs muted"><tr>
                  {th("name", t("table.product"))}<th scope="col" className="px-4 py-2 font-medium">{t("pr.rank")}</th>{th("score", t("chart.score"))}{th("fixes", t("pr.fixes"))}
                  <th scope="col" className="px-4 py-2 font-medium">{t("rep.price")}</th><th scope="col" className="px-4 py-2"><span className="sr-only">{t("pr.actions")}</span></th></tr></thead>
                <tbody className="divide-y divide-[var(--border)]">
                  {rows.map((p) => {
                    const a = p.audit, b = busy[p.id];
                    return (
                      <tr key={p.id} className="hover:bg-[var(--surface-2)]/60">
                        <td className="max-w-[20rem] px-4 py-3">
                          {p.url && tracked[p.url] ? (
                            <a href={`#/products/${encodeURIComponent(tracked[p.url])}`} className="flex items-center gap-3 font-medium hover:underline">
                              <Thumb src={a?.product.image} /><span className="truncate">{productName(p)}</span>
                            </a>
                          ) : <span className="flex items-center gap-3 font-medium"><Thumb src={a?.product.image} /><span className="truncate">{productName(p)}</span></span>}
                          <p className="flex items-center gap-2 truncate text-xs muted">
                            {p.merchant_stated ? <span className="chip bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300">{t("label.merchantStated")}</span> : <span className="truncate">{p.url}</span>}
                          </p>
                          {b && b !== "run" && <p className="mt-1 flex items-center gap-1 text-xs text-rose-600"><XCircle className="size-3" aria-hidden />{b}</p>}
                        </td>
                        <td className="px-4 py-3 text-xs">{b === "run" ? <span className="flex items-center gap-1.5 muted"><Loader2 className="size-3.5 animate-spin" aria-hidden />{t("home.auditing")}</span> : rankText(p, t)}</td>
                        <td className="px-4 py-3">{a ? <span className="flex items-center gap-2"><span className="h-1.5 w-16 rounded-full bg-[var(--surface-2)]"><span className="block h-full rounded-full bg-[var(--chart-you)]" style={{ width: `${a.rank.score}%` }} /></span><span className="tabular-nums">{a.rank.score}</span></span> : <span className="muted">–</span>}</td>
                        <td className="px-4 py-3 tabular-nums">{a ? a.actions.length : "–"}</td>
                        <td className="px-4 py-3 whitespace-nowrap">{a?.product.price != null ? money(a.product.price, a.product.currency, lang) : "–"}</td>
                        <td className="px-4 py-3 text-right whitespace-nowrap">
                          {p.url && (tracked[p.url]
                            ? <a className="btn-ghost px-2 py-1 text-xs" href={`#/products/${encodeURIComponent(tracked[p.url])}`}>{t("pr.history")}</a>
                            : <button className="btn-ghost px-2 py-1 text-xs" disabled={tracking === p.id} onClick={() => track(p)}>{tracking === p.id ? <Loader2 className="size-3.5 animate-spin" aria-hidden /> : null}{t("pr.track")}</button>)}
                          <button className="btn-ghost px-2 py-1 text-xs" disabled={b === "run"} onClick={() => run([p])}>{a ? t("home.reaudit") : t("home.audit")}</button>
                          <button className="btn-ghost p-1.5" onClick={() => remove(p)} aria-label={t("ob.removeProduct")}><Trash2 className="size-4" aria-hidden /></button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : <div className="p-4"><Empty icon={<Package className="size-6" aria-hidden />} title={q ? t("table.none") : t("ov.noAudits")} body={q ? undefined : t("ov.noAuditsBody")} /></div>}
        </section>
      )}
      {tab === "catalog" && signedIn && <p className="mt-3 flex items-center gap-1.5 text-xs muted"><CheckCircle2 className="size-3.5" aria-hidden /> {t("pr.note")} <TriangleAlert className="ml-2 size-3.5" aria-hidden /> {t("pr.limit")}</p>}
    </div>
  );
}
