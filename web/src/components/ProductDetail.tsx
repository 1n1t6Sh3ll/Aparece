import { useEffect, useState, type FormEvent } from "react";
import { ArrowLeft, CornerDownLeft, ExternalLink, GitCompare, History, KeyRound, Loader2, MessageSquare, RefreshCw, Shirt } from "lucide-react";
import { ApiError, cap, errorText, fieldLabel, fmtValue, manageToken, money, tn, useI18n } from "../lib";
import { history, num, type ChangeEvent, type ChatAnswer, type Diff, type Monitored, type Snapshot, type TrendPoint } from "../history";
import { useSession } from "../session";
import { Empty, ErrorBox, useToast } from "../ui";

const day = (s: string, lang: string) => new Date(s).toLocaleDateString(lang, { day: "numeric", month: "short" });
const when = (s: string, lang: string) => new Date(s).toLocaleString(lang, { dateStyle: "medium", timeStyle: "short" });

/** One-series line chart with a crosshair tooltip. `invert` puts lower values at the top (rank). */
function Line({ title, pts, fmt, invert = false, neutral = false, lang }: { title: string; pts: { at: string; v: number | null }[]; fmt: (n: number) => string; invert?: boolean; neutral?: boolean; lang: string }) {
  const { t } = useI18n();
  const [hi, setHi] = useState<number | null>(null);
  const data = pts.filter((p) => p.v != null) as { at: string; v: number }[];
  if (data.length < 2) return (
    <figure className="card p-3"><figcaption className="flex justify-between text-xs font-semibold"><span>{title}</span>{data[0] && <span className="tabular-nums">{fmt(data[0].v)}</span>}</figcaption>
      <p className="mt-6 pb-6 text-center text-xs muted">{data.length ? t("pd.onePoint") : t("pd.notMeasured")}</p></figure>
  );
  const W = 300, H = 90, P = 6;
  const vs = data.map((d) => d.v), lo = Math.min(...vs), span = Math.max(...vs) - lo || 1;
  const x = (i: number) => P + (i * (W - 2 * P)) / (data.length - 1);
  const y = (v: number) => { const f = (v - lo) / span; return P + (invert ? f : 1 - f) * (H - 2 * P); };
  const path = data.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(d.v).toFixed(1)}`).join(" ");
  const first = data[0], last = data[data.length - 1], delta = last.v - first.v;
  const good = (delta > 0) !== invert;
  return (
    <figure className="card p-3">
      <figcaption className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-semibold">{title}</span>
        <span className="text-sm font-semibold tabular-nums">{fmt(last.v)} <span className={`text-xs ${delta === 0 || neutral ? "muted" : good ? "text-emerald-700 dark:text-emerald-400" : "text-rose-700 dark:text-rose-400"}`}>{delta > 0 ? "+" : delta < 0 ? "−" : "±"}{fmt(Math.abs(delta)).replace(/^[#+-]/, "")}</span></span>
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

function Compare({ id, snaps }: { id: string; snaps: Snapshot[] }) {
  const { t, lang } = useI18n();
  const [a, setA] = useState(snaps[0].id);
  const [b, setB] = useState(snaps[snaps.length - 1].id);
  const [diff, setDiff] = useState<Diff | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    setDiff(null); setErr("");
    if (a === b) return;
    history.diff(id, a, b).then(setDiff).catch((e) => setErr(errorText(e, t).msg));
  }, [id, a, b]); // eslint-disable-line react-hooks/exhaustive-deps
  const tone = { added: "bg-emerald-50 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300", removed: "bg-rose-50 text-rose-800 dark:bg-rose-950/50 dark:text-rose-300", changed: "bg-amber-50 text-amber-800 dark:bg-amber-950/50 dark:text-amber-300" };
  const rows = diff ? [
    ...diff.attributes.added.map((x) => ({ field: x.field, change: "added" as const, before: null, after: x.new })),
    ...diff.attributes.changed.map((x) => ({ field: x.field, change: "changed" as const, before: x.old, after: x.new })),
    ...diff.attributes.removed.map((x) => ({ field: x.field, change: "removed" as const, before: x.old, after: null })),
  ] : [];
  const sd = diff?.structured_data.changed ? Object.keys({ ...diff.structured_data.old, ...diff.structured_data.new }).filter((k) => diff.structured_data.old[k] !== diff.structured_data.new[k]) : [];
  return (
    <section className="card" aria-labelledby="cmp-snap">
      <div className="flex flex-col gap-2 border-b border-[var(--border)] p-4 sm:flex-row sm:items-end">
        <h2 id="cmp-snap" className="mr-auto flex items-center gap-2 text-sm font-semibold"><GitCompare className="size-4" aria-hidden /> {t("pd.compare")}</h2>
        {(["a", "b"] as const).map((k) => (
          <label key={k} className="text-xs muted">{k === "a" ? t("pd.before") : t("pd.after")}
            <select className="input mt-1 w-auto py-1.5" value={k === "a" ? a : b} onChange={(e) => (k === "a" ? setA : setB)(Number(e.target.value))}>
              {snaps.map((s) => <option key={s.id} value={s.id}>#{s.id} · {when(s.crawled_at, lang)}</option>)}
            </select>
          </label>
        ))}
      </div>
      {a === b ? <p className="p-4 text-sm muted">{t("pd.same")}</p> : err ? <div className="p-4"><ErrorBox title={t("err.title")} msg={err} /></div>
        : !diff ? <div className="space-y-2 p-4"><div className="skeleton h-4" /><div className="skeleton h-4 w-2/3" /></div> : (
        <div className="grid lg:grid-cols-2">
          <div className="border-b border-[var(--border)] lg:border-b-0 lg:border-r">
            <table className="w-full text-sm">
              <thead className="text-left text-xs muted"><tr><th className="px-4 py-2 font-medium">{t("table.fact")}</th><th className="px-2 py-2 font-medium">{t("pd.before")}</th><th className="px-2 py-2 font-medium">{t("pd.after")}</th></tr></thead>
              <tbody className="divide-y divide-[var(--border)]">
                {rows.map((f) => (
                  <tr key={f.field} className="align-top">
                    <td className="px-4 py-2"><p className="font-medium">{cap(fieldLabel(lang, f.field))}</p><span className={`chip mt-1 ${tone[f.change]}`}>{t(`pd.ch.${f.change}`)}</span></td>
                    <td className="px-2 py-2 muted">{f.before == null ? "–" : <del className="decoration-rose-400">{fmtValue(f.before)}</del>}</td>
                    <td className="px-2 py-2">{f.after == null ? "–" : fmtValue(f.after)}</td>
                  </tr>
                ))}
                {!rows.length && <tr><td colSpan={3} className="px-4 py-4 text-center muted">{t("pd.noFieldChanges")}</td></tr>}
              </tbody>
            </table>
            <dl className="space-y-1 border-t border-[var(--border)] px-4 py-3 text-sm">
              <div className="flex gap-2"><dt className="muted">{t("rep.price")}:</dt><dd>{diff.price.changed ? <><del className="muted">{money(diff.price.old.price, diff.price.old.currency, lang) || "–"}</del> → <b>{money(diff.price.new.price, diff.price.new.currency, lang) || "–"}</b></> : t("pd.unchanged")}</dd></div>
              {sd.length > 0 && <div className="flex gap-2"><dt className="muted">{t("rank.sd")}:</dt><dd>{sd.map((k) => `${k.replace(/_/g, " ")} ${diff.structured_data.new[k] ? t("pd.present") : t("pd.absent")}`).join(", ")}</dd></div>}
              {(diff.languages.added.length > 0 || diff.languages.removed.length > 0) && <div className="flex gap-2"><dt className="muted">{t("set.language")}:</dt><dd>{diff.languages.added.map((l) => `+${l}`).concat(diff.languages.removed.map((l) => `−${l}`)).join(" ")}</dd></div>}
            </dl>
          </div>
          <div className="p-4">
            <p className="text-xs font-semibold muted">{t("pd.descDiff")}</p>
            {!diff.description.changed ? <p className="mt-2 text-sm muted">{t("pd.unchanged")}</p> : (
              <>
                <p className="mt-1 text-xs muted">{t("pd.chars", { a: diff.description.old_chars, b: diff.description.new_chars })}</p>
                {diff.description.text_diff ? (
                  <div className="mt-2 space-y-0.5 text-sm leading-relaxed">
                    {diff.description.text_diff.filter((l) => !/^(---|\+\+\+|@@)/.test(l)).map((l, i) =>
                      l.startsWith("+") ? <p key={i} className="bg-emerald-100 px-1 dark:bg-emerald-900/40"><span className="sr-only">{t("pd.added")}: </span>{l.slice(1)}</p>
                        : l.startsWith("-") ? <p key={i} className="bg-rose-100 px-1 text-rose-900 line-through decoration-rose-400 dark:bg-rose-900/30 dark:text-rose-200"><span className="sr-only">{t("pd.removed")}: </span>{l.slice(1)}</p>
                          : <p key={i} className="px-1 muted">{l.slice(1)}</p>)}
                  </div>
                ) : <p className="mt-2 text-sm muted">{t("pd.noText")}</p>}
                <p className="mt-3 flex gap-3 text-xs muted"><span className="bg-emerald-100 px-1 dark:bg-emerald-900/40">{t("pd.added")}</span><span className="bg-rose-100 px-1 line-through dark:bg-rose-900/30">{t("pd.removed")}</span></p>
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

function ProductChat({ productId }: { productId: string | null }) {
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const [log, setLog] = useState<{ q: string; a?: ChatAnswer; err?: string }[]>([]);
  const [busy, setBusy] = useState(false);
  async function ask(text: string) {
    if (!text.trim()) return;
    setBusy(true); setQ("");
    const i = log.length;
    const past = log.flatMap((m) => (m.a ? [{ role: "user" as const, content: m.q }, { role: "assistant" as const, content: m.a.answer }] : []));
    setLog((l) => [...l, { q: text }]);
    try {
      const a = await history.chat(productId, text, past);
      setLog((l) => l.map((x, j) => (j === i ? { ...x, a } : x)));
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
                <p className={m.a.refused ? "muted" : ""}>{m.a.answer}</p>
                {m.a.citations.length > 0 && (
                  <ul className="mt-2 flex flex-wrap gap-1 border-t border-[var(--border)] pt-2 text-xs">
                    {m.a.citations.map((c) => <li key={`${c.type}:${c.id}`} className="chip bg-[var(--surface)]">[{c.type}:{c.id}]{c.date && <span className="muted"> {String(c.date).slice(0, 10)}</span>}{c.merchant_stated && <span className="text-amber-800 dark:text-amber-300"> · {t("pd.stated")}</span>}</li>)}
                  </ul>
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

/** Monitored product workspace (public id): snapshot timeline, compare any two, trends, change events, chat. */
export default function ProductDetail({ id }: { id: string }) {
  const { t, lang } = useI18n();
  const { profile } = useSession();
  const toast = useToast();
  const [snaps, setSnaps] = useState<Snapshot[] | null>(null);
  const [points, setPoints] = useState<TrendPoint[] | null>(null);
  const [info, setInfo] = useState<{ product: Monitored; events: ChangeEvent[] } | null>(null);
  const [err, setErr] = useState<{ msg: string; auth: boolean; missing: boolean } | null>(null);
  const [busy, setBusy] = useState(false);
  const [img, setImg] = useState(true);

  const load = () => Promise.all([history.snapshots(id), history.trends(id), history.history(id)])
    .then(([s, tr, hi]) => { setSnaps(s); setPoints(tr); setInfo(hi); setErr(null); })
    .catch((e) => setErr({ msg: errorText(e, t).msg, auth: e instanceof ApiError && (e.status === 401 || e.status === 403), missing: e instanceof ApiError && e.status === 404 }));
  useEffect(() => { load(); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  if (err) return (
    <div className="mx-auto max-w-3xl">
      <a href="#/products" className="btn-ghost -ml-2 mb-3"><ArrowLeft className="size-4" aria-hidden /> {t("nav.products")}</a>
      {err.missing ? <Empty icon={<History className="size-6" aria-hidden />} title={t("pd.notFound")} body={t("pd.notFoundBody")}><a className="btn-outline" href="#/products">{t("nav.products")}</a></Empty>
        : err.auth || !manageToken(id)
        ? <Empty icon={<KeyRound className="size-6" aria-hidden />} title={t("pd.noToken")} body={t("pd.noTokenBody")} />
        : <ErrorBox title={t("err.title")} msg={err.msg}><button className="btn-outline" onClick={load}>{t("pd.retry")}</button></ErrorBox>}
    </div>
  );
  const url = info?.product.url;
  const linked = profile?.products.find((p) => p.url && p.url === url);  // same page in the active company's catalogue
  const a = linked?.audit;
  const cur = points?.find((p) => p.currency)?.currency || null;

  async function recrawl() {
    setBusy(true);
    try { await history.recrawl(id); await load(); toast("ok", t("pd.recrawled")); } catch (e) { toast("err", errorText(e, t).msg); }
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
          <h1 className="truncate text-xl">{a?.product.title || url || id}</h1>
          {url && <p className="truncate text-xs muted">{url}</p>}
          {info && snaps && <p className="mt-1.5 text-xs muted">{tn(t, "pd.snaps", snaps.length)} · {tn(t, "pd.events", info.events.length)} · {t("pd.lastCheck", { d: snaps.length ? when(snaps[snaps.length - 1].crawled_at, lang) : "–" })}</p>}
        </div>
        <div className="flex gap-2">
          {url && <a className="btn-ghost px-2.5" href={url} target="_blank" rel="noopener noreferrer" aria-label={t("ws.open")}><ExternalLink className="size-4" aria-hidden /></a>}
          <button className="btn-primary" disabled={busy} onClick={recrawl}>{busy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <RefreshCw className="size-4" aria-hidden />} {t("pd.recrawl")}</button>
        </div>
      </header>

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="min-w-0 space-y-5">
          <section aria-labelledby="pd-trends">
            <h2 id="pd-trends" className="mb-2 text-sm font-semibold">{t("pd.trends")}</h2>
            {!points ? <div className="grid gap-3 sm:grid-cols-2">{[0, 1, 2, 3].map((i) => <div key={i} className="card h-36 p-3"><div className="skeleton h-full" /></div>)}</div> : (
              <div className="grid gap-3 sm:grid-cols-2">
                <Line lang={lang} title={t("pd.rank")} pts={points.map((p) => ({ at: p.at, v: p.completeness_rank?.position ?? null }))} fmt={(n) => `#${Math.round(n)}`} invert />
                <Line lang={lang} title={t("pd.completeness")} pts={points.map((p) => ({ at: p.at, v: p.attribute_completeness_pct }))} fmt={(n) => `${Math.round(n)}%`} />
                <Line lang={lang} title={t("rep.price")} neutral pts={points.map((p) => ({ at: p.at, v: p.price }))} fmt={(n) => money(n, cur, lang)} />
                <Line lang={lang} title={t("compare.desc")} neutral pts={points.map((p) => ({ at: p.at, v: p.description_chars }))} fmt={(n) => t("compare.chars", { n: Math.round(n) })} />
                <Line lang={lang} title={t("vis.title")} pts={points.map((p) => ({ at: p.at, v: num(p.visibility) }))} fmt={(n) => `${Math.round(n * 100)}%`} />
              </div>
            )}
            <p className="mt-2 text-xs muted">{t("pd.rankNote")}</p>
          </section>
          {snaps && snaps.length >= 2 && <Compare id={id} snaps={snaps} />}
          {snaps && snaps.length < 2 && <Empty icon={<GitCompare className="size-6" aria-hidden />} title={t("pd.needTwo")} body={t("pd.needTwoBody")}><button className="btn-outline" onClick={recrawl} disabled={busy}><RefreshCw className="size-4" aria-hidden /> {t("pd.recrawl")}</button></Empty>}
        </div>

        <aside className="min-w-0 space-y-5">
          <section className="card" aria-labelledby="pd-tl">
            <h2 id="pd-tl" className="flex items-center gap-2 border-b border-[var(--border)] px-4 py-3 text-sm font-semibold"><History className="size-4" aria-hidden /> {t("pd.timeline")}</h2>
            {!snaps || !info ? <div className="space-y-2 p-4"><div className="skeleton h-4" /><div className="skeleton h-4" /></div> : (
              <ol className="max-h-[28rem] overflow-y-auto px-4 py-3">
                {[...snaps].reverse().map((s, k, arr) => {
                  const prev = arr[k + 1]?.crawled_at;
                  const evs = info.events.filter((e) => e.at <= s.crawled_at && (!prev || e.at > prev));
                  const m = s.metrics;
                  return (
                    <li key={s.id} className="relative border-l border-[var(--border)] pb-4 pl-4 last:pb-0">
                      <span className="absolute -left-[5px] top-1 size-2.5 rounded-full bg-[var(--chart-you)] ring-2 ring-[var(--surface)]" aria-hidden />
                      <p className="text-xs muted">{when(s.crawled_at, lang)} · #{s.id}</p>
                      <p className="text-sm">
                        {m.attribute_completeness_pct != null && <><b className="tabular-nums">{Math.round(m.attribute_completeness_pct)}%</b> {t("pd.facts")}</>}
                        {m.completeness_rank && <> · #{m.completeness_rank.position}/{m.completeness_rank.of}</>}
                        {m.price != null && <> · {money(m.price, m.currency, lang)}</>}
                      </p>
                      {evs.map((e) => <p key={e.id} className="mt-0.5 text-xs"><span className="chip bg-[var(--surface-2)]">{t(`hist.ev.${e.type}`)}</span> {e.field ? fieldLabel(lang, e.field) : ""}{e.after != null && <span className="muted"> → {fmtValue(e.after)}</span>}</p>)}
                    </li>
                  );
                })}
              </ol>
            )}
          </section>
          <ProductChat productId={a?.product.product_id ?? null} />
        </aside>
      </div>
    </div>
  );
}
