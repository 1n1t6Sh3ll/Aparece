import { useEffect, useState } from "react";
import { Award, BarChart3, FlaskConical, Hourglass, Info } from "lucide-react";
import { api, cap, errorText, fieldLabel, useI18n } from "../lib";
import { Tip } from "./RankParts";

type Rates = { json_valid?: number; non_null_acc?: number; null_acc?: number; n?: number };
type Model = Rates & {
  label: string; field_exact?: Record<string, number>; by_language?: Record<string, Rates>;
  cost_per_1k_usd?: number | null; latency_ms?: number | null; time_s?: number | null;
  settings?: string | Record<string, unknown> | null;
  answered?: number; total?: number; partial?: boolean;
};
type Comparison = { available: boolean; sample: boolean; generated_at: string | null; test: { products?: number; stores?: number; note?: string };
  models: Record<string, Model>; new_fields: string[] };

const ORDER = ["all_null_baseline", "base_qwen_0_5b", "base_zero_shot", "ft_qwen_0_5b", "finetuned", "ft_qwen_1_5b", "gpt-4o-mini", "claude-haiku-4-5"];
const COLORS = ["#94a3b8", "#0ea5e9", "#6366f1", "#8b5cf6", "#10b981", "#f59e0b", "#ef4444", "#14b8a6"];
const BASELINE = "all_null_baseline";
const pct = (v: number | undefined | null) => (v == null ? null : `${Math.round(v * 1000) / 10}%`);
/** [answered, total] when a model answered fewer products than the test set (or the run marks it partial). */
const partialOf = (m: Model, n?: number): [number, number] | null => {
  const a = m.answered ?? m.n, tot = m.total ?? n;
  return a != null && tot != null && (m.partial || a < tot) ? [a, tot] : null;
};
/** Run files may bake the status into the label ("Claude ... — partial: 87 of 200"); the translated chip shows it. */
const tidy = (c: Comparison): Comparison => ({ ...c, models: Object.fromEntries(Object.entries(c.models || {}).map(([k, m]) =>
  [k, partialOf(m, c.test?.products) ? { ...m, label: m.label.replace(/\s*(?:[—–-]\s*partial\b.*|\(partial\b[^)]*\))$/i, "") } : m])) });

export default function ModelsPage() {
  const { t, lang } = useI18n();
  const [data, setData] = useState<Comparison | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    api<Comparison>("/v1/model-comparison").then((c) => setData(tidy(c))).catch((e) => setErr(errorText(e, t).msg));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const head = (
    <>
      <h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl">{t("mod.title")}</h1>
      <p className="mt-2 max-w-2xl muted">{t("mod.sub")}</p>
    </>
  );
  if (err) return <div className="mx-auto max-w-6xl px-4 py-10 sm:py-14">{head}<p role="alert" className="mt-6 text-rose-700 dark:text-rose-400">{err}</p></div>;
  if (!data) return <div className="mx-auto max-w-6xl px-4 py-10 sm:py-14">{head}<div className="card mt-6 h-64 animate-pulse bg-stone-100/60 dark:bg-stone-800/40" aria-hidden /></div>;
  if (!data.available || data.sample) {  // a sample file is never shown as results
    return (
      <div className="mx-auto max-w-6xl px-4 py-10 sm:py-14">
        {head}
        <div className="card mt-8 flex flex-col items-center p-10 text-center">
          <span className="grid size-14 place-items-center rounded-2xl bg-brand-50 text-brand-600 dark:bg-brand-950 dark:text-brand-300"><Hourglass className="size-7" aria-hidden /></span>
          <h2 className="mt-4 text-xl font-semibold">{t("mod.empty")}</h2>
          <p className="mt-1 max-w-md muted">{t("mod.emptyD")}</p>
        </div>
        <Method data={data} />
      </div>
    );
  }

  const keys = Object.keys(data.models).sort((a, b) => (ORDER.indexOf(a) + 1 || 99) - (ORDER.indexOf(b) + 1 || 99));
  const color = (k: string) => COLORS[keys.indexOf(k) % COLORS.length];
  const ms = keys.map((k) => ({ k, m: data.models[k] }));
  const contenders = ms.filter(({ k, m }) => k !== BASELINE && m.non_null_acc != null);
  const winner = contenders.reduce<(typeof ms)[number] | null>((w, x) => (!w || (x.m.non_null_acc! > w.m.non_null_acc!) ? x : w), null);
  const latency = (m: Model) => m.latency_ms != null ? `${(m.latency_ms / 1000).toFixed(1)} s`
    : m.time_s != null && m.n ? `${(m.time_s / m.n).toFixed(1)} s` : null;
  const showLatency = ms.some(({ m }) => latency(m));
  const best = (f: (m: Model) => number | null | undefined) => Math.max(...contenders.map(({ m }) => f(m) ?? -1));
  const n = data.test.products;
  const partial = (m: Model) => partialOf(m, n);

  const cell = (v: string | null, isBest = false) => v == null
    ? <span className="text-xs text-stone-400">{t("mod.notMeasured")}</span>
    : <span className={`tabular-nums ${isBest ? "font-bold text-emerald-700 dark:text-emerald-400" : ""}`}>{v}</span>;

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:py-14">
      {head}

      {winner && (
        <section className="card mt-6 flex items-start gap-4 p-6 rise">
          <span className="grid size-12 shrink-0 place-items-center rounded-2xl bg-[var(--accent)] text-white"><Award className="size-6" aria-hidden /></span>
          <div>
            <p className="text-lg font-semibold sm:text-xl">
              {n ? t("mod.headline", { m: winner.m.label, p: pct(winner.m.non_null_acc)!, n }) : t("mod.headlineNoN", { m: winner.m.label, p: pct(winner.m.non_null_acc)! })}
            </p>
            <p className="mt-1 text-sm muted">
              {[data.test.products && data.test.stores ? t("mod.productsStores", { p: data.test.products, s: data.test.stores }) : data.test.products ? t("mod.products", { p: data.test.products }) : null,
                data.generated_at ? t("mod.generated", { d: new Date(data.generated_at).toLocaleDateString(lang) }) : null].filter(Boolean).join(" · ")}
            </p>
          </div>
        </section>
      )}

      <section className="card mt-6 p-5 sm:p-6 rise">
        <h2 className="text-lg font-semibold">{t("mod.overall")}</h2>
        <div className="mt-4 -mx-5 overflow-x-auto sm:-mx-6" role="region" tabIndex={0} aria-label={t("mod.overall")}>
          <table className="w-full min-w-[640px] text-sm">
            <thead className="text-left muted">
              <tr className="border-b border-stone-200 dark:border-stone-800">
                <th scope="col" className="px-5 py-2 font-medium sm:px-6">{t("mod.model")}</th>
                <th scope="col" className="px-3 py-2 font-medium"><Tip text={t("mod.nonnullTip")}><span>{t("mod.nonnull")}</span></Tip></th>
                <th scope="col" className="px-3 py-2 font-medium"><Tip text={t("mod.nullTip")}><span>{t("mod.null")}</span></Tip></th>
                <th scope="col" className="px-3 py-2 font-medium">{t("mod.json")}</th>
                <th scope="col" className="px-3 py-2 font-medium">{t("mod.cost")}</th>
                {showLatency && <th scope="col" className="px-3 py-2 font-medium">{t("mod.latency")}</th>}
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100 dark:divide-stone-800">
              {ms.map(({ k, m }) => (
                <tr key={k} className={k === winner?.k ? "bg-emerald-50/50 dark:bg-emerald-950/20" : ""}>
                  <th scope="row" className="px-5 py-3 text-left font-medium sm:px-6">
                    <span className="flex items-center gap-2">
                      <span className="size-2.5 shrink-0 rounded-full" style={{ background: color(k) }} aria-hidden />
                      {m.label}
                      {k === BASELINE && <span className="chip bg-stone-100 text-stone-600 dark:bg-stone-800 dark:text-stone-300">{t("mod.baseline")}</span>}
                      {k === winner?.k && <span className="chip bg-emerald-100 text-emerald-800 dark:bg-emerald-900/60 dark:text-emerald-200">{t("mod.best")}</span>}
                      {partial(m) && <span className="chip bg-amber-100 text-amber-800 dark:bg-amber-900/50 dark:text-amber-200">{t("mod.partial", { a: partial(m)![0], n: partial(m)![1] })}</span>}
                    </span>
                  </th>
                  <td className="px-3 py-3">{cell(pct(m.non_null_acc), k !== BASELINE && m.non_null_acc === best((x) => x.non_null_acc))}</td>
                  <td className="px-3 py-3">{cell(pct(m.null_acc))}</td>
                  <td className="px-3 py-3">{cell(pct(m.json_valid))}</td>
                  <td className="px-3 py-3">{k === BASELINE ? null : m.cost_per_1k_usd === 0 ? <span className="text-xs muted">{t("mod.free")}</span>
                    : cell(m.cost_per_1k_usd != null ? `$${m.cost_per_1k_usd.toFixed(2)}` : null)}</td>
                  {showLatency && <td className="px-3 py-3">{k === BASELINE ? null : cell(latency(m))}</td>}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <LangBars ms={ms.filter(({ k }) => k !== BASELINE)} color={color} />

      <FieldTable title={t("mod.original")} ms={ms} fields={fieldsOf(ms).filter((f) => !data.new_fields.includes(f))} />
      {(() => {
        const nf = fieldsOf(ms).filter((f) => data.new_fields.includes(f));  // count what the run file actually scored
        return <FieldTable title={t("mod.newFields", { n: nf.length })} sub={t("mod.newFieldsSub")} ms={ms} fields={nf} />;
      })()}

      <Method data={data} />
    </div>
  );
}

function fieldsOf(ms: { m: Model }[]) {
  return [...new Set(ms.flatMap(({ m }) => Object.keys(m.field_exact || {})))];
}

function LangBars({ ms, color }: { ms: { k: string; m: Model }[]; color: (k: string) => string }) {
  const { t } = useI18n();
  const langs = ["en", "es", "other"].filter((l) => ms.some(({ m }) => m.by_language?.[l]?.non_null_acc != null));
  if (!langs.length) return null;
  return (
    <section className="card mt-6 p-5 sm:p-6 rise">
      <h2 className="flex items-center gap-2 text-lg font-semibold"><BarChart3 className="size-5 text-stone-400" aria-hidden />{t("mod.byLang")}</h2>
      <p className="mt-0.5 text-sm muted">{t("mod.byLangSub")}</p>
      <div className="mt-5 grid gap-6 md:grid-cols-3">
        {langs.map((l) => (
          <div key={l}>
            <p className="text-sm font-semibold">{t(`mod.lang.${l}`)}</p>
            <ul className="mt-2 space-y-1.5">
              {ms.map(({ k, m }) => {
                const r = m.by_language?.[l];
                const v = r?.non_null_acc;
                return (
                  <li key={k} className="flex items-center gap-2 text-xs">
                    <span className="w-28 shrink-0 truncate muted" title={m.label}>{m.label}</span>
                    <span className="h-3 flex-1 rounded-full bg-stone-100 dark:bg-stone-800" role="img" aria-label={`${m.label}: ${v != null ? pct(v) : t("mod.notMeasured")}`}>
                      {v != null && <span className="block h-full rounded-full" style={{ width: `${Math.max(1, v * 100)}%`, background: color(k) }} />}
                    </span>
                    <span className="w-14 shrink-0 text-right tabular-nums">{v != null ? pct(v) : <span className="text-stone-400">{t("mod.notMeasured")}</span>}</span>
                  </li>
                );
              })}
            </ul>
            {ms.find(({ m }) => m.by_language?.[l]?.n) && <p className="mt-1.5 text-xs muted">{t("mod.products", { p: ms.find(({ m }) => m.by_language?.[l]?.n)!.m.by_language![l].n! })}</p>}
          </div>
        ))}
      </div>
    </section>
  );
}

function FieldTable({ title, sub, ms, fields }: { title: string; sub?: string; ms: { k: string; m: Model }[]; fields: string[] }) {
  const { t, lang } = useI18n();
  if (!fields.length) return null;
  return (
    <section className="card mt-6 p-5 sm:p-6 rise">
      <h2 className="text-lg font-semibold">{t("mod.fields")}: {title}</h2>
      <p className="mt-0.5 text-sm muted">{sub || t("mod.fieldsSub")}</p>
      <div className="mt-4 -mx-5 overflow-x-auto sm:-mx-6" role="region" tabIndex={0} aria-label={title}>
        <table className="w-full min-w-[640px] text-sm">
          <thead className="text-left muted">
            <tr className="border-b border-stone-200 dark:border-stone-800">
              <th scope="col" className="px-5 py-2 font-medium sm:px-6">{t("mod.field")}</th>
              {ms.map(({ k, m }) => <th key={k} scope="col" className="px-3 py-2 font-medium">{m.label}</th>)}
            </tr>
          </thead>
          <tbody className="divide-y divide-stone-100 dark:divide-stone-800">
            {fields.map((f) => {
              const vals = ms.map(({ k, m }) => (k === BASELINE ? null : m.field_exact?.[f] ?? null));
              const top = Math.max(...vals.map((v) => v ?? -1));
              return (
                <tr key={f}>
                  <th scope="row" className="px-5 py-2 text-left font-medium sm:px-6">{cap(fieldLabel(lang, f).replace(/^(la|el|los|las) /, ""))}</th>
                  {ms.map(({ k, m }) => {
                    const v = m.field_exact?.[f];
                    const isTop = k !== BASELINE && v != null && v === top && top >= 0;
                    return (
                      <td key={k} className={`px-3 py-2 tabular-nums ${isTop ? "bg-emerald-50 font-bold text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300" : k === BASELINE ? "muted" : ""}`}>
                        {v != null ? pct(v) : <span className="text-xs text-stone-400">{t("mod.notMeasured")}</span>}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Method({ data }: { data: Comparison }) {
  const { t, lang } = useI18n();
  const s = data.test.products ? (data.test.stores ? t("mod.productsStores", { p: data.test.products, s: data.test.stores }) : t("mod.products", { p: data.test.products })) : "";
  const fmt = (v: unknown) => typeof v === "string" ? v
    : v && typeof v === "object" ? Object.entries(v as Record<string, unknown>).map(([k, x]) => `${k.replace(/_/g, " ")} ${typeof x === "object" ? JSON.stringify(x) : String(x)}`).join(", ") : "";
  const settings = Object.values(data.models).filter((m) => m.settings && fmt(m.settings)).map((m) => [m.label, fmt(m.settings)] as const);
  const hasBaseline = BASELINE in data.models;
  const hasCost = Object.values(data.models).some((m) => m.cost_per_1k_usd != null);
  return (
    <div className="mt-6 grid gap-6 md:grid-cols-2">
      <section className="card p-5 sm:p-6">
        <h2 className="flex items-center gap-2 font-semibold"><FlaskConical className="size-5 text-stone-400" aria-hidden />{t("mod.method")}</h2>
        <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm muted">
          <li>{s ? t("mod.m1", { s }) : t("mod.m1NoN")}</li><li>{t("mod.m2")}</li><li>{t("mod.m3")}</li>
          {hasBaseline && <li>{t("mod.m4")}</li>}
          {data.test.note && <li>{t("mod.runNote", { n: data.test.note })}{lang !== "en" && <span className="muted"> ({t("mod.origEn")})</span>}</li>}
        </ul>
        {settings.length > 0 && (
          <>
            <p className="mt-4 text-sm font-medium">{t("mod.settings")}</p>
            <dl className="mt-1 space-y-1 text-sm muted">
              {settings.map(([l, v]) => <div key={l}><dt className="inline font-medium text-stone-700 dark:text-stone-200">{l}: </dt><dd className="inline">{v}</dd></div>)}
            </dl>
          </>
        )}
      </section>
      <section className="card p-5 sm:p-6">
        <h2 className="flex items-center gap-2 font-semibold"><Info className="size-5 text-stone-400" aria-hidden />{t("mod.caveats")}</h2>
        <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm muted">
          <li>{t("mod.c1")}</li><li>{t("mod.c2")}</li>{hasCost && <li>{t("mod.c3")}</li>}
        </ul>
      </section>
    </div>
  );
}
