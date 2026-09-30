import { useCallback, useEffect, useState } from "react";
import { ArrowLeft, Camera, ExternalLink, History, Loader2, PauseCircle, RefreshCw, ScanSearch } from "lucide-react";
import { allManageTokens, api, cap, errorText, tn, fieldLabel, fmtValue, manageToken, useI18n } from "../lib";

type Monitored = { id: string; url: string; enrolled_at: string; active: number; plan: string | null; last_snapshot_at: string | null;
  snapshot_count: number; event_count: number };
type Event = { id: number; at: string; type: string; field: string | null; before: unknown; after: unknown };
type Snapshot = { id: number; taken_at: string; data: { content?: { title?: string; price?: number; currency?: string } } };

const when = (s: string | null, lang: string) => (s ? new Date(s).toLocaleString(lang, { dateStyle: "medium", timeStyle: "short" }) : "");

function Loading() {
  return <div className="space-y-3" aria-hidden>{[0, 1, 2].map((i) => <div key={i} className="card h-20 animate-pulse bg-stone-100/60 dark:bg-stone-800/40" />)}</div>;
}

function Failed({ msg }: { msg: string }) {
  return <p role="alert" className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-900 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-200">{msg}</p>;
}

export function ProductsPage({ embedded = false }: { embedded?: boolean }) {
  const { t, lang } = useI18n();
  const [rows, setRows] = useState<Monitored[] | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const load = useCallback(() => api<{ results: Monitored[] }>("/v1/monitored", { headers: { "X-Manage-Token": allManageTokens() } }).then((r) => setRows(r.results)).catch((e) => setErr(errorText(e, t).msg)), [t]);
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function act(id: string, kind: "crawl" | "stop") {
    if (kind === "stop" && !window.confirm(t("prod.confirm"))) return;
    setBusy(id);
    try {
      await api(kind === "crawl" ? `/v1/monitored/${id}/crawl` : `/v1/enroll/${id}`, { method: kind === "crawl" ? "POST" : "DELETE", headers: { "X-Manage-Token": manageToken(id) } });
      await load();
    } catch (e) { setErr(errorText(e, t).msg); }
    setBusy(null);
  }

  return (
    <div className={embedded ? "" : "mx-auto max-w-4xl"}>
      {embedded ? <p className="text-sm muted">{t("prod.sub")}</p> : <>
        <h1 className="text-2xl font-bold tracking-tight">{t("prod.title")}</h1>
        <p className="mt-1 text-sm muted">{t("prod.sub")}</p></>}
      <div className="mt-4 space-y-3">
        {err && <Failed msg={err} />}
        {!rows && !err && <Loading />}
        {rows && rows.length === 0 && (
          <div className="card flex flex-col items-center p-10 text-center">
            <ScanSearch className="size-10 text-stone-300" aria-hidden />
            <p className="mt-3 max-w-sm muted">{t("prod.empty")}</p>
            <a href="#/audit" className="btn-primary mt-5">{t("hero.cta")}</a>
          </div>
        )}
        {rows?.map((r) => (
          <article key={r.id} className={`card p-4 sm:p-5 ${r.active ? "" : "opacity-70"}`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  {!r.active && <span className="chip bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-300"><PauseCircle className="size-3" aria-hidden /> {t("prod.inactive")}</span>}
                  {r.plan && <span className="chip bg-brand-50 text-brand-700 dark:bg-brand-950/60 dark:text-brand-300">{cap(r.plan)}</span>}
                </div>
                <a href={r.url} target="_blank" rel="noopener noreferrer" className="mt-1 flex items-center gap-1 truncate font-medium hover:underline">
                  <span className="truncate">{r.url.replace(/^https?:\/\//, "")}</span><ExternalLink className="size-3.5 shrink-0" aria-hidden />
                </a>
                <p className="mt-1 text-xs muted">
                  {t("prod.last")}: {r.last_snapshot_at ? when(r.last_snapshot_at, lang) : t("prod.never")} · {tn(t, "prod.snaps", r.snapshot_count)} · {tn(t, "prod.events", r.event_count)}
                </p>
              </div>
              <div className="flex flex-wrap gap-1">
                <a href={`#/products/${r.id}`} className="btn-ghost px-3 py-2"><History className="size-4" aria-hidden /> {t("prod.history")}</a>
                {!!r.active && <>
                  <button className="btn-ghost px-3 py-2" disabled={busy === r.id} onClick={() => act(r.id, "crawl")}>
                    {busy === r.id ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <RefreshCw className="size-4" aria-hidden />} {t("prod.recrawl")}
                  </button>
                  <button className="btn-ghost px-3 py-2 text-rose-700 dark:text-rose-400" disabled={busy === r.id} onClick={() => act(r.id, "stop")}>{t("prod.unenroll")}</button>
                </>}
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}

function show(field: string | null, v: unknown, t: (k: string, p?: Record<string, string | number>) => string) {
  if (field === "commerce.price" && Array.isArray(v)) return v.filter((x) => x != null).join(" ");
  if (field === "structured_data" && v && typeof v === "object")
    return Object.entries(v as Record<string, boolean>).filter(([, x]) => x).map(([k]) => t(`sd.${k}`)).join(", ");
  if (field === "content.full_description") return t("compare.chars", { n: String(v) });
  return fmtValue(v);
}

export function HistoryPage({ id }: { id: string }) {
  const { t, lang } = useI18n();
  const [data, setData] = useState<{ product: Monitored; snapshots: Snapshot[]; events: Event[] } | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api<{ product: Monitored; snapshots: Snapshot[]; events: Event[] }>(`/v1/products/${id}/history`, { headers: { "X-Manage-Token": manageToken(id) } }).then(setData)
      .catch((e) => setErr(e.status === 404 ? t("hist.empty") : errorText(e, t).msg));
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  const items = data ? [
    ...data.events.map((e) => ({ at: e.at, key: `e${e.id}`, ev: e as Event | null, snap: null as Snapshot | null })),
    ...data.snapshots.map((s) => ({ at: s.taken_at, key: `s${s.id}`, ev: null, snap: s })),
  ].sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : a.ev ? -1 : 1)) : [];

  return (
    <div className="mx-auto max-w-3xl px-4 py-10 sm:py-14">
      <a href="#/products" className="btn-ghost -ml-3 mb-4"><ArrowLeft className="size-4" aria-hidden /> {t("hist.back")}</a>
      <h1 className="text-3xl font-extrabold tracking-tight">{t("hist.title")}</h1>
      {data && <p className="mt-2 truncate muted">{data.product.url}</p>}
      <div className="mt-6">
        {err && <Failed msg={err} />}
        {!data && !err && <Loading />}
        {data && data.events.length === 0 && <p className="card mb-4 p-4 text-sm muted">{t("hist.empty")}</p>}
        {data && (
          <ol className="relative space-y-4 border-l border-stone-200 pl-6 dark:border-stone-800">
            {items.map(({ key, at, ev, snap }) => (
              <li key={key} className="relative">
                <span className={`absolute -left-[31px] top-4 grid size-3.5 place-items-center rounded-full ring-4 ring-stone-50 dark:ring-stone-950 ${ev ? "bg-brand-500" : "bg-stone-300 dark:bg-stone-600"}`} aria-hidden />
                <div className="card p-4">
                  <p className="text-xs muted">{when(at, lang)}</p>
                  {ev ? (
                    <>
                      <p className="mt-1 font-semibold">{t(`hist.ev.${ev.type}`)}{ev.field && ev.field.includes(".") && ev.type.startsWith("ATTRIBUTE") ? `: ${fieldLabel(lang, ev.field)}` : ""}</p>
                      <dl className="mt-2 grid gap-1 text-sm sm:grid-cols-2">
                        {ev.before != null && <div><dt className="text-xs muted">{t("hist.before")}</dt><dd className="break-words">{show(ev.field, ev.before, t)}</dd></div>}
                        {ev.after != null && <div><dt className="text-xs muted">{t("hist.after")}</dt><dd className="break-words">{show(ev.field, ev.after, t)}</dd></div>}
                      </dl>
                    </>
                  ) : (
                    <p className="mt-1 flex items-center gap-2 text-sm"><Camera className="size-4 text-stone-400" aria-hidden /> {t("hist.snapshot")}{snap?.data?.content?.title ? `: ${snap.data.content.title}` : ""}</p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}
