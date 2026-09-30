import { useEffect, useMemo, useState, type FormEvent } from "react";
import { ArrowLeft, CornerDownLeft, ExternalLink, FlaskConical, GitCompare, History, Loader2, MessageSquare, RefreshCw, Shirt } from "lucide-react";
import { cap, errorText, fieldLabel, fmtValue, money, useI18n } from "../lib";
import { history, wordDiff, type ChatAnswer, type Diff, type SnapshotList, type TrendPoint } from "../history";
import { papi, productName, type Product } from "../profile";
import { useSession } from "../session";
import { Empty, ErrorBox, useToast } from "../ui";

const day = (s: string, lang: string) => new Date(s).toLocaleDateString(lang, { day: "numeric", month: "short" });

/** One-series line chart with a crosshair tooltip. `invert` puts lower values at the top (rank). */
function Line({ title, pts, fmt, invert = false, neutral = false, lang }: { title: string; pts: { at: string; v: number | null }[]; fmt: (n: number) => string; invert?: boolean; neutral?: boolean; lang: string }) {
  const { t } = useI18n();
  const [hi, setHi] = useState<number | null>(null);
  const data = pts.filter((p) => p.v != null) as { at: string; v: number }[];
  if (data.length < 2) return (
    <figure className="card p-3"><figcaption className="text-xs font-semibold">{title}</figcaption>
      <p className="mt-6 pb-6 text-center text-xs muted">{data.length ? t("pd.onePoint") : t("pd.notMeasured")}</p></figure>
  );
  const W = 300, H = 90, P = 6;
  const vs = data.map((d) => d.v), lo = Math.min(...vs), hiV = Math.max(...vs), span = hiV - lo || 1;
  const x = (i: number) => P + (i * (W - 2 * P)) / (data.length - 1);
  const y = (v: number) => { const f = (v - lo) / span; return P + (invert ? f : 1 - f) * (H - 2 * P); };
  const path = data.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(d.v).toFixed(1)}`).join(" ");
  const last = data[data.length - 1], first = data[0];
  const delta = last.v - first.v;
  return (
    <figure className="card p-3">
      <figcaption className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-semibold">{title}</span>
        <span className="text-sm font-semibold tabular-nums">{fmt(last.v)} <span className={`text-xs ${delta === 0 || neutral ? "muted" : (delta > 0) !== invert ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"}`}>{delta > 0 ? "+" : ""}{fmt(delta).replace(/^\+/, "")}</span></span>
      </figcaption>
      <div className="relative mt-2" onMouseLeave={() => setHi(null)}>
        <svg viewBox={`0 0 ${W} ${H}`} className="h-24 w-full overflow-visible" role="img" aria-label={`${title}: ${data.map((d) => `${day(d.at, lang)} ${fmt(d.v)}`).join(", ")}`}
          onMouseMove={(e) => { const r = e.currentTarget.getBoundingClientRect(); const i = Math.round(((e.clientX - r.left) / r.width * W - P) / ((W - 2 * P) / (data.length - 1))); setHi(Math.max(0, Math.min(data.length - 1, i))); }}>
          <line x1={P} x2={W - P} y1={H - P} y2={H - P} stroke="var(--border)" />
          <path d={path} fill="none" stroke="var(--chart-you)" strokeWidth={2} strokeLinejoin="round" />
          {data.map((d, i) => <circle key={i} cx={x(i)} cy={y(d.v)} r={hi === i ? 4.5 : 3} fill="var(--chart-you)" stroke="var(--surface)" strokeWidth={2} />)}
          {hi != null && <line x1={x(hi)} x2={x(hi)} y1={P} y2={H - P} stroke="var(--muted)" strokeDasharray="2 3" />}
        </svg>
        {hi != null && (
          <div role="tooltip" className="pointer-events-none absolute -top-2 z-10 -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-sm bg-stone-900 px-2 py-1 text-xs text-white dark:bg-stone-700"
            style={{ left: `${(x(hi) / W) * 100}%` }}>{day(data[hi].at, lang)} · <b>{fmt(data[hi].v)}</b></div>
        )}
      </div>
      <div className="flex justify-between text-[10px] muted"><span>{day(first.at, lang)}</span><span>{day(last.at, lang)}</span></div>
    </figure>
  );
}

function Compare({ id, list, sample }: { id: number; list: SnapshotList; sample: boolean }) {
  const { t, lang } = useI18n();
  const snaps = list.snapshots;
  const [a, setA] = useState(snaps[0]?.id);
  const [b, setB] = useState(snaps[snaps.length - 1]?.id);
  const [diff, setDiff] = useState<Diff | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    if (a == null || b == null || a === b) { setDiff(null); return; }
    setErr("");
    history.diff(id, a, b).then((r) => setDiff(r.data)).catch((e) => setErr(errorText(e, t).msg));
  }, [id, a, b]); // eslint-disable-line react-hooks/exhaustive-deps
  const label = (s: typeof snaps[number]) => `#${s.id} · ${new Date(s.taken_at).toLocaleString(lang, { dateStyle: "medium", timeStyle: "short" })}`;
  const tone = { added: "bg-emerald-50 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300", removed: "bg-rose-50 text-rose-800 dark:bg-rose-950/50 dark:text-rose-300", changed: "bg-amber-50 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300" };
  return (
    <section className="card" aria-labelledby="cmp-snap">
      <div className="flex flex-col gap-2 border-b border-[var(--border)] p-4 sm:flex-row sm:items-end">
        <h2 id="cmp-snap" className="mr-auto flex items-center gap-2 text-sm font-semibold"><GitCompare className="size-4" aria-hidden /> {t("pd.compare")}</h2>
        {(["a", "b"] as const).map((k) => (
          <label key={k} className="text-xs muted">{k === "a" ? t("pd.before") : t("pd.after")}
            <select className="input mt-1 w-auto py-1.5" value={k === "a" ? a : b} onChange={(e) => (k === "a" ? setA : setB)(Number(e.target.value))}>
              {snaps.map((s) => <option key={s.id} value={s.id}>{label(s)}</option>)}
            </select>
          </label>
        ))}
      </div>
      {a === b ? <p className="p-4 text-sm muted">{t("pd.same")}</p> : err ? <div className="p-4"><ErrorBox title={t("err.title")} msg={err} /></div> : !diff ? <div className="space-y-2 p-4"><div className="skeleton h-4" /><div className="skeleton h-4 w-2/3" /></div> : (
        <div className="grid gap-0 lg:grid-cols-2">
          <div className="border-b border-[var(--border)] lg:border-b-0 lg:border-r">
            <table className="w-full text-sm">
              <thead className="text-left text-xs muted"><tr><th className="px-4 py-2 font-medium">{t("table.fact")}</th><th className="px-2 py-2 font-medium">{t("pd.before")}</th><th className="px-2 py-2 font-medium">{t("pd.after")}</th></tr></thead>
              <tbody className="divide-y divide-[var(--border)]">
                {diff.fields.map((f) => (
                  <tr key={f.field} className="align-top">
                    <td className="px-4 py-2"><p className="font-medium">{cap(fieldLabel(lang, f.field))}</p><span className={`chip mt-1 ${tone[f.change]}`}>{t(`pd.ch.${f.change}`)}</span></td>
                    <td className="px-2 py-2 muted">{f.before == null ? "–" : <del className="decoration-rose-400">{fmtValue(f.before)}</del>}</td>
                    <td className="px-2 py-2">{f.after == null ? "–" : <ins className="no-underline">{fmtValue(f.after)}</ins>}</td>
                  </tr>
                ))}
                {!diff.fields.length && <tr><td colSpan={3} className="px-4 py-4 text-center muted">{t("pd.noFieldChanges")}</td></tr>}
              </tbody>
            </table>
            {(diff.price.before != null || diff.price.after != null) && diff.price.before !== diff.price.after && (
              <p className="border-t border-[var(--border)] px-4 py-3 text-sm">{t("rep.price")}: <del className="muted">{money(diff.price.before, diff.price.currency, lang)}</del> → <b>{money(diff.price.after, diff.price.currency, lang)}</b></p>
            )}
          </div>
          <div className="p-4">
            <p className="text-xs font-semibold muted">{t("pd.descDiff")}</p>
            <p className="mt-2 text-sm leading-relaxed">
              {wordDiff(diff.description.before || "", diff.description.after || "").map(([op, s], i) =>
                op === "=" ? <span key={i}>{s}</span> : op === "+" ? <ins key={i} className="bg-emerald-100 no-underline dark:bg-emerald-900/50">{s}</ins> : <del key={i} className="bg-rose-100 text-rose-900 dark:bg-rose-900/40 dark:text-rose-200">{s}</del>)}
            </p>
            <p className="mt-3 flex gap-3 text-xs muted"><span><ins className="bg-emerald-100 px-1 no-underline dark:bg-emerald-900/50">{t("pd.added")}</ins></span><span><del className="bg-rose-100 px-1 dark:bg-rose-900/40">{t("pd.removed")}</del></span></p>
          </div>
        </div>
      )}
      {sample && <p className="border-t border-[var(--border)] px-4 py-2 text-xs text-amber-800 dark:text-amber-300">{t("pd.sampleShort")}</p>}
    </section>
  );
}

function ProductChat({ id }: { id: number }) {
  const { t, lang } = useI18n();
  const [q, setQ] = useState("");
  const [log, setLog] = useState<{ q: string; a?: ChatAnswer; sample?: boolean; err?: string }[]>([]);
  const [busy, setBusy] = useState(false);
  async function ask(text: string) {
    if (!text.trim()) return;
    setBusy(true); setQ("");
    const i = log.length;
    setLog((l) => [...l, { q: text }]);
    try {
      const r = await history.chat(id, text, lang);
      setLog((l) => l.map((x, j) => (j === i ? { ...x, a: r.data, sample: r.sample } : x)));
    } catch (e) {
      setLog((l) => l.map((x, j) => (j === i ? { ...x, err: errorText(e, t).msg } : x)));
    }
    setBusy(false);
  }
  return (
    <section className="card flex flex-col" aria-labelledby="pchat">
      <h2 id="pchat" className="flex items-center gap-2 border-b border-[var(--border)] px-4 py-3 text-sm font-semibold"><MessageSquare className="size-4" aria-hidden /> {t("pd.chat")}</h2>
      <div className="max-h-96 flex-1 space-y-3 overflow-y-auto p-4 text-sm" role="log" aria-live="polite">
        {!log.length && <p className="muted">{t("pd.chatHint")}</p>}
        {log.map((m, i) => (
          <div key={i} className="space-y-2">
            <p className="ml-auto w-fit max-w-[90%] rounded-md bg-[var(--accent)] px-3 py-2 text-[var(--accent-fg)]">{m.q}</p>
            {m.err ? <p className="text-rose-700 dark:text-rose-400">{m.err}</p> : !m.a ? <Loader2 className="size-4 animate-spin muted" aria-label={t("home.loading")} /> : (
              <div className="max-w-[95%] rounded-md bg-[var(--surface-2)] px-3 py-2">
                {m.sample && <p className="mb-1 text-xs font-semibold text-amber-800 dark:text-amber-300">{t("pd.sampleShort")}</p>}
                <p>{m.a.answer}</p>
                {m.a.citations.length > 0 && (
                  <ol className="mt-2 space-y-1 border-t border-[var(--border)] pt-2 text-xs">
                    {m.a.citations.map((c, k) => <li key={k}><b>[{k + 1}] {c.label}</b>{c.field && <> · {fieldLabel(lang, c.field)}</>}{c.quote && <span className="muted"> “{c.quote}”</span>}</li>)}
                  </ol>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
      <div className="border-t border-[var(--border)] p-3">
        <button className="btn-outline mb-2 w-full text-xs" disabled={busy} onClick={() => ask(t("pd.chatQ"))}>{t("pd.chatQ")}</button>
        <form onSubmit={(e: FormEvent) => { e.preventDefault(); ask(q); }} className="flex gap-2">
          <label htmlFor="pchat-q" className="sr-only">{t("chat.placeholder")}</label>
          <input id="pchat-q" className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("pd.chatPh")} />
          <button className="btn-primary" disabled={busy || !q.trim()} aria-label={t("chat.send")}><CornerDownLeft className="size-4" aria-hidden /></button>
        </form>
      </div>
    </section>
  );
}

/** Per-product workspace: snapshot timeline, compare any two, trends, change events and a product-scoped chat. */
export default function ProductDetail({ id }: { id: number }) {
  const { t, lang } = useI18n();
  const { profile, loading, updateProduct } = useSession();
  const toast = useToast();
  const [list, setList] = useState<SnapshotList | null>(null);
  const [trends, setTrends] = useState<TrendPoint[] | null>(null);
  const [sample, setSample] = useState(false);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const [img, setImg] = useState(true);
  const p: Product | undefined = profile?.products.find((x) => x.id === id);

  useEffect(() => {
    Promise.all([history.snapshots(id), history.trends(id)])
      .then(([s, tr]) => { setList(s.data); setTrends(tr.data.points); setSample(s.sample || tr.sample); })
      .catch((e) => setErr(errorText(e, t).msg));
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  const series = useMemo(() => (trends || []).map((x) => ({ ...x, completeness: x.facts_found != null && x.facts_checked ? Math.round((100 * x.facts_found) / x.facts_checked) : null })), [trends]);
  if (loading && !profile) return <div className="skeleton h-40" />;
  if (!p) return <Empty icon={<History className="size-6" aria-hidden />} title={t("pd.notFound")}><a className="btn-outline" href="#/products">{t("nav.products")}</a></Empty>;
  const a = p.audit;
  const cur = series[0]?.currency || a?.product.currency || null;

  async function reaudit() {
    setBusy(true);
    try { updateProduct(await papi<Product>(`/v1/profile/products/${id}/audit`, { method: "POST" })); toast("ok", t("run.done", { ok: 1, n: 1 })); }
    catch (e) { toast("err", errorText(e, t).msg); }
    setBusy(false);
  }

  return (
    <div className="mx-auto max-w-[1400px]">
      <a href="#/products" className="btn-ghost -ml-2 mb-3"><ArrowLeft className="size-4" aria-hidden /> {t("nav.products")}</a>
      <header className="card mb-5 flex flex-col gap-4 p-4 sm:flex-row sm:items-center">
        <div className="grid size-16 shrink-0 place-items-center overflow-hidden rounded-md bg-[var(--surface-2)]">
          {a?.product.image && img ? <img src={a.product.image} alt="" referrerPolicy="no-referrer" onError={() => setImg(false)} className="size-full object-cover" /> : <Shirt className="size-8 muted" aria-hidden />}
        </div>
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-xl">{productName(p)}</h1>
          {p.url && <p className="truncate text-xs muted">{p.url}</p>}
          <div className="mt-1.5 flex flex-wrap gap-1.5 text-xs">
            {a && <span className="chip bg-[var(--surface-2)]">{a.rank.total > 1 ? t("rep.rank", { pos: a.rank.position, total: a.rank.total }) : t("rep.noPeers")}</span>}
            {a && <span className="chip bg-[var(--surface-2)]">{t("ws.quality")} {a.rank.score}/100</span>}
            {p.merchant_stated && <span className="chip bg-amber-50 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300">{t("label.merchantStated")}</span>}
          </div>
        </div>
        <div className="flex gap-2">
          {p.url && <a className="btn-ghost px-2.5" href={p.url} target="_blank" rel="noopener noreferrer" aria-label={t("ws.open")}><ExternalLink className="size-4" aria-hidden /></a>}
          <button className="btn-primary" disabled={busy} onClick={reaudit}>{busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <RefreshCw className="size-4" aria-hidden />} {t("home.reaudit")}</button>
        </div>
      </header>

      {sample && (
        <p role="note" className="mb-5 flex items-start gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
          <FlaskConical className="mt-0.5 size-4 shrink-0" aria-hidden /> {t("pd.sample")}
        </p>
      )}
      {err && <div className="mb-5"><ErrorBox title={t("err.title")} msg={err} /></div>}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 space-y-5">
          <section aria-labelledby="pd-trends">
            <h2 id="pd-trends" className="mb-2 text-sm font-semibold">{t("pd.trends")}</h2>
            {!trends ? <div className="grid gap-3 sm:grid-cols-2">{[0, 1, 2, 3].map((i) => <div key={i} className="card h-36 p-3"><div className="skeleton h-full" /></div>)}</div> : (
              <div className="grid gap-3 sm:grid-cols-2">
                <Line lang={lang} title={t("ws.quality")} pts={series.map((x) => ({ at: x.at, v: x.score }))} fmt={(n) => n.toFixed(1)} />
                <Line lang={lang} title={t("pd.rank")} pts={series.map((x) => ({ at: x.at, v: x.rank }))} fmt={(n) => (n > 0 ? `#${Math.round(n)}` : `${Math.round(n)}`)} invert />
                <Line lang={lang} title={t("pd.completeness")} pts={series.map((x) => ({ at: x.at, v: x.completeness }))} fmt={(n) => `${Math.round(n)}%`} />
                <Line lang={lang} title={t("rep.price")} neutral pts={series.map((x) => ({ at: x.at, v: x.price }))} fmt={(n) => money(n, cur, lang)} />
                <Line lang={lang} title={t("vis.title")} pts={series.map((x) => ({ at: x.at, v: x.visibility }))} fmt={(n) => `${Math.round(n * 100)}%`} />
              </div>
            )}
          </section>
          {list && list.snapshots.length >= 2 && <Compare id={id} list={list} sample={sample} />}
          {list && list.snapshots.length < 2 && <Empty icon={<GitCompare className="size-6" aria-hidden />} title={t("pd.needTwo")} body={t("pd.needTwoBody")} />}
        </div>

        <aside className="min-w-0 space-y-5">
          <section className="card" aria-labelledby="pd-tl">
            <h2 id="pd-tl" className="flex items-center gap-2 border-b border-[var(--border)] px-4 py-3 text-sm font-semibold"><History className="size-4" aria-hidden /> {t("pd.timeline")}</h2>
            {!list ? <div className="space-y-2 p-4"><div className="skeleton h-4" /><div className="skeleton h-4" /></div> : (
              <ol className="relative max-h-[28rem] overflow-y-auto px-4 py-3">
                {[...list.snapshots].reverse().map((s) => {
                  const evs = list.events.filter((e) => day(e.at, lang) === day(s.taken_at, lang));
                  return (
                    <li key={s.id} className="relative border-l border-[var(--border)] pb-4 pl-4 last:pb-0">
                      <span className="absolute -left-[5px] top-1 size-2.5 rounded-full bg-[var(--chart-you)] ring-2 ring-[var(--surface)]" aria-hidden />
                      <p className="text-xs muted">{new Date(s.taken_at).toLocaleString(lang, { dateStyle: "medium", timeStyle: "short" })} · #{s.id}</p>
                      <p className="text-sm">{s.score != null && <><b className="tabular-nums">{s.score}</b>/100 · </>}{s.rank != null && s.total ? `#${s.rank}/${s.total} · ` : ""}{s.price != null ? money(s.price, s.currency, lang) : ""}</p>
                      {evs.map((e) => <p key={e.id} className="mt-0.5 text-xs"><span className="chip bg-[var(--surface-2)]">{t(`pd.ev.${e.type}`)}</span> {e.field ? fieldLabel(lang, e.field) : ""}{e.after != null && <span className="muted"> → {fmtValue(e.after)}</span>}</p>)}
                    </li>
                  );
                })}
              </ol>
            )}
          </section>
          <ProductChat id={id} />
        </aside>
      </div>
    </div>
  );
}
