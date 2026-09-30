import { useEffect, useState, type ReactNode } from "react";
import { AlertTriangle, Check, FlaskConical, Info, Trophy, X } from "lucide-react";
import { api, useI18n } from "../lib";

type CI = { value: number; lo: number; hi: number };
type Vis = { n: number; mrr: CI; mention_rate: CI; top3_rate: CI } | null;
type Gen = {
  candidates: number; qualified_products: number; qualified: boolean; flagged: number; unsupported_claims: number;
  title: { score: number | null }; tags: { score: number | null; false: number; duplicates: number };
  description: { attribute_coverage: number | null; intent_coverage: number | null; readability: number | null; words: number | null };
  visibility: Vis;
};
type Cand = {
  raw: { title: string | null; tags: string[]; text: string | null; error: string | null };
  title: { passes: boolean; score: number; chars: number } | null;
  tags: { passes: boolean; passing: string[]; false: string[]; score: number };
  description: { passes: boolean; attribute_coverage: number | null } | null;
  qualified: boolean; visibility: Vis;
};
type Product = {
  product_id: string; brand: string; name: string; language: string; url: string;
  candidates: Record<string, Cand>; part_winners: Record<Part, string | null>;
  recommended: { title: { text: string; from: string } | null; tags: { list: string[]; from: string[] } | null;
    description: { text: string; from: string } | null };
};
type Part = "title" | "tags" | "description";
type Report = {
  available: boolean; sample?: boolean; label?: string; caveats?: string[]; generated_at?: string;
  setup?: { products: number; judges: string[]; holdout_judge: string | null; prompts_per_product: number; repeats: number };
  overall?: { winner: string | null; runner_up?: string; decisive?: boolean; diff_vs_runner_up?: CI | null;
    holdout_judge?: { judge: string; winner: string | null; agrees: boolean };
    parts: Record<Part, { winner: string | null; wins: Record<string, number> }> };
  generators?: Record<string, Gen>; products?: Product[];
};

const PARTS: Part[] = ["title", "tags", "description"];
const pct = (v: number | null | undefined) => (v == null ? "–" : `${Math.round(v * 100)}%`);
const ci = (v: CI | undefined) => (v ? `${v.value.toFixed(2)} [${v.lo.toFixed(2)}–${v.hi.toFixed(2)}]` : "–");
const Pass = ({ ok }: { ok: boolean }) => ok
  ? <Check className="size-4 shrink-0 text-emerald-600" aria-label="pass" />
  : <X className="size-4 shrink-0 text-rose-600" aria-label="fail" />;

export default function ComparePage({ productId }: { productId?: string }) {
  const { t } = useI18n();
  const [data, setData] = useState<Report | null>(null);
  const [err, setErr] = useState("");
  const [sel, setSel] = useState<string>("");
  useEffect(() => {
    api<Report>("/v1/shootout").then(setData).catch((e) => setErr(t("err.generic", { detail: e.message })));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const head = (
    <>
      <h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl">{t("cmp.title")}</h1>
      <p className="mt-2 max-w-2xl muted">{t("cmp.sub")}</p>
    </>
  );
  const wrap = (body: ReactNode) => <div className="mx-auto max-w-6xl px-4 py-10 sm:py-14">{head}{body}</div>;
  if (err) return wrap(<p role="alert" className="mt-6 text-rose-700 dark:text-rose-400">{err}</p>);
  if (!data) return wrap(<div className="card mt-6 h-64 animate-pulse bg-slate-100/60 dark:bg-slate-800/40" aria-hidden />);
  if (!data.available || !data.overall || !data.generators || !data.products) return wrap(<p className="card mt-6 p-6 muted">{t("cmp.empty")}</p>);

  const o = data.overall, gens = data.generators, products = data.products;
  const inSet = products.some((p) => p.product_id === productId);
  const cur = products.find((p) => p.product_id === (sel || (inSet ? productId : products[0].product_id)))!;

  return wrap(
    <>
      <p role="note" className="mt-5 flex items-start gap-2 rounded-xl border border-sky-300 bg-sky-50 p-3 text-sm text-sky-900 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-200">
        <FlaskConical className="mt-0.5 size-4 shrink-0" aria-hidden />{t("cmp.controlled")}
      </p>
      {data.sample && (
        <p role="note" className="mt-3 flex items-start gap-2 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
          <AlertTriangle className="mt-0.5 size-4 shrink-0" aria-hidden />{t("cmp.sample")}
        </p>
      )}
      {productId && !inSet && <p className="mt-3 text-sm muted">{t("cmp.notInSet")}</p>}

      <section className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {PARTS.map((part) => (
          <div key={part} className="card p-5">
            <p className="text-sm muted">{t(`cmp.best.${part}`)}</p>
            <p className="mt-1 flex items-center gap-2 text-lg font-semibold"><Trophy className="size-4 text-amber-500" aria-hidden />{o.parts[part].winner || t("cmp.none")}</p>
            <p className="mt-1 text-xs muted">{t("cmp.wins", { w: Object.entries(o.parts[part].wins).map(([g, n]) => `${g} ${n}`).join(", ") || "–" })}</p>
          </div>
        ))}
        <div className="card p-5">
          <p className="text-sm muted">{t("cmp.best.visibility")}</p>
          <p className="mt-1 flex items-center gap-2 text-lg font-semibold"><Trophy className="size-4 text-amber-500" aria-hidden />{o.winner || t("cmp.none")}</p>
          <p className="mt-1 text-xs muted">
            {o.diff_vs_runner_up ? t(o.decisive ? "cmp.separated" : "cmp.tie", { r: o.runner_up!, d: ci(o.diff_vs_runner_up) }) : ""}
            {o.holdout_judge ? ` ${t(o.holdout_judge.agrees ? "cmp.holdoutAgrees" : "cmp.holdoutDisagrees", { j: o.holdout_judge.judge })}` : ""}
          </p>
        </div>
      </section>

      <section className="card mt-6 p-5 sm:p-6">
        <h2 className="text-lg font-semibold">{t("cmp.generators")}</h2>
        <div className="mt-4 -mx-5 overflow-x-auto sm:-mx-6" role="region" tabIndex={0} aria-label={t("cmp.generators")}>
          <table className="w-full min-w-[760px] text-sm">
            <thead className="text-left muted"><tr className="border-b border-slate-200 dark:border-slate-800">
              {["gen", "qualified", "flagged", "titleScore", "tagsScore", "coverage", "intent", "mrr", "mention"].map((k) =>
                <th key={k} scope="col" className="px-3 py-2 font-medium first:pl-5 sm:first:pl-6">{t(`cmp.col.${k}`)}</th>)}
            </tr></thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {Object.entries(gens).map(([g, v]) => (
                <tr key={g} className={v.qualified ? "" : "text-slate-400"}>
                  <th scope="row" className="px-5 py-2 text-left font-medium sm:px-6">{g}</th>
                  <td className="px-3 py-2"><span className="flex items-center gap-1"><Pass ok={v.qualified} />{v.qualified_products}/{v.candidates}</span></td>
                  <td className="px-3 py-2 tabular-nums">{v.flagged}</td>
                  <td className="px-3 py-2 tabular-nums">{pct(v.title.score)}</td>
                  <td className="px-3 py-2 tabular-nums">{pct(v.tags.score)}</td>
                  <td className="px-3 py-2 tabular-nums">{pct(v.description.attribute_coverage)}</td>
                  <td className="px-3 py-2 tabular-nums">{pct(v.description.intent_coverage)}</td>
                  <td className="px-3 py-2 tabular-nums">{ci(v.visibility?.mrr)}</td>
                  <td className="px-3 py-2 tabular-nums">{ci(v.visibility?.mention_rate)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs muted">{t("cmp.qualifiedNote")}</p>
      </section>

      <section className="card mt-6 p-5 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">{t("cmp.recommended")}</h2>
          <label className="text-sm">
            <span className="sr-only">{t("cmp.product")}</span>
            <select className="rounded-lg border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-700 dark:bg-slate-900"
              value={cur.product_id} onChange={(e) => setSel(e.target.value)}>
              {products.map((p) => <option key={p.product_id} value={p.product_id}>{p.brand} · {p.name} ({p.language})</option>)}
            </select>
          </label>
        </div>
        <dl className="mt-4 space-y-3 text-sm">
          <div><dt className="font-medium">{t("cmp.part.title")} <span className="chip bg-slate-100 dark:bg-slate-800">{cur.recommended.title?.from || "–"}</span></dt>
            <dd className="mt-1">{cur.recommended.title?.text || t("cmp.none")}</dd></div>
          <div><dt className="font-medium">{t("cmp.part.tags")} <span className="chip bg-slate-100 dark:bg-slate-800">{cur.recommended.tags?.from.join(", ") || "–"}</span></dt>
            <dd className="mt-1 flex flex-wrap gap-1.5">{cur.recommended.tags?.list.map((x) => <span key={x} className="chip bg-indigo-50 text-indigo-800 dark:bg-indigo-950 dark:text-indigo-200">{x}</span>) || t("cmp.none")}</dd></div>
          <div><dt className="font-medium">{t("cmp.part.description")} <span className="chip bg-slate-100 dark:bg-slate-800">{cur.recommended.description?.from || "–"}</span></dt>
            <dd className="mt-1">{cur.recommended.description?.text || t("cmp.none")}</dd></div>
        </dl>
        <p className="mt-3 text-xs muted">{t("cmp.recommendedNote")}</p>

        <h3 className="mt-6 font-semibold">{t("cmp.candidates")}</h3>
        <ul className="mt-2 divide-y divide-slate-100 dark:divide-slate-800">
          {Object.entries(cur.candidates).map(([g, c]) => (
            <li key={g} className="py-3 text-sm">
              <p className="flex flex-wrap items-center gap-2 font-medium">{g}
                {Object.entries(cur.part_winners).filter(([, w]) => w === g).map(([part]) =>
                  <span key={part} className="chip bg-emerald-100 text-emerald-800 dark:bg-emerald-900/60 dark:text-emerald-200">{t(`cmp.best.${part}`)}</span>)}
                <span className="muted">MRR {ci(c.visibility?.mrr)}</span>
              </p>
              {c.raw.error && <p className="text-rose-700 dark:text-rose-400">{c.raw.error}</p>}
              <p className="mt-1 flex items-start gap-1.5">{c.title && <Pass ok={c.title.passes} />}<span>{c.raw.title || "–"}</span></p>
              <p className="mt-1 flex flex-wrap items-center gap-1.5"><Pass ok={c.tags.passes} />
                {c.raw.tags.length ? c.raw.tags.map((x, i) => <span key={i} className={`chip ${c.tags.false.includes(x) ? "bg-rose-50 text-rose-700 line-through dark:bg-rose-950/50 dark:text-rose-300" : "bg-slate-100 dark:bg-slate-800"}`}>{x}</span>)
                  : <span className="muted">{t("cmp.noTags")}</span>}</p>
              <p className="mt-1 flex items-start gap-1.5">{c.description && <Pass ok={c.description.passes} />}<span className="muted">{c.raw.text || "–"}</span></p>
            </li>
          ))}
        </ul>
      </section>

      <section className="card mt-6 p-5 sm:p-6">
        <h2 className="flex items-center gap-2 font-semibold"><Info className="size-5 text-slate-400" aria-hidden />{t("cmp.caveats")}</h2>
        <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm muted">
          {(data.caveats || []).map((c) => <li key={c}>{c}</li>)}
          {data.setup && <li>{t("cmp.setup", { p: data.setup.products, j: data.setup.judges.join(", "), h: data.setup.holdout_judge || "–", q: data.setup.prompts_per_product, r: data.setup.repeats })}</li>}
        </ul>
      </section>
    </>,
  );
}
