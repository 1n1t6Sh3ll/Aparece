import { useEffect, useState, type ReactNode } from "react";
import { Scale, Check, FlaskConical, Info, Trophy, X } from "lucide-react";
import { api, errorText, useI18n } from "../lib";

// Page-local strings (EN/ES) so the page stays self-contained while shared i18n/layout are restyled.
const STR: Record<string, Record<string, string>> = { en: {
  "cta": "Compare with AI models",
  "title": "AI comparison: title, tags, description",
  "sub": "Aparece and AI models each write a title, tags and description from the same verified facts. Every part is checked for unsupported claims, audited, and tested in a simulated AI shopping context.",
  "controlled": "Controlled evaluation: a simulated shopping context with 4 real competitor pages, judged by AI models. It is not proof of how any real assistant or search engine will rank a product.",
  "notInSet": "This product is not in the comparison set yet, so there are no AI comparison results for it. Other products' numbers are never shown in its place.",
  "notInSetTitle": "No AI comparison for this product yet",
  "seeSet": "See the products that were compared",
  "empty": "Not run yet. Results appear here after a real run of benchmark/shootout/run.py.",
  "best.title": "Best title",
  "best.tags": "Best tags",
  "best.description": "Best description",
  "best.visibility": "Highest measured visibility",
  "none": "none passed",
  "wins": "Products won: {w}",
  "separated": "Ahead of {r} by {d} MRR.",
  "tie": "Not separated from {r} ({d} MRR); treat as a tie.",
  "holdoutAgrees": "Held-out judge {j} agrees.",
  "holdoutDisagrees": "Held-out judge {j} disagrees.",
  "generators": "Generators",
  "col.gen": "Generator",
  "col.qualified": "No unsupported claims",
  "col.flagged": "Flagged parts",
  "col.titleScore": "Title audit",
  "col.tagsScore": "Tags audit",
  "col.coverage": "Facts covered",
  "col.intent": "Intents covered",
  "col.mrr": "MRR [95% CI]",
  "col.mention": "Mention rate [95% CI]",
  "qualifiedNote": "A generator is ranked only if none of its titles, tags or descriptions contain unsupported claims. Greyed rows are shown for reference.",
  "recommended": "Recommended for this product",
  "product": "Product",
  "part.title": "Title",
  "part.tags": "Tags",
  "part.description": "Description",
  "recommendedNote": "Each part comes from the best candidate that passed the claims check; tags are merged from passing tags only. Review before publishing.",
  "candidates": "All candidates",
  "noTags": "no tags",
  "caveats": "Caveats",
  "setup": "{p} products; judges {j} (held out: {h}); {q} dev/val prompts x {r} repeats.",
  "real": "Real run on {d}: live AI judges and generators, {n} judge calls, US${c} API cost as recorded by the run.",
  "pass": "passed",
  "fail": "failed",
  "liveRunning": "Comparing this product now: Aparece and AI models are writing a title, tags and description from its verified facts…",
  "liveNote": "Live comparison of this product, just now. Every part was checked for unsupported claims and audited; AI-visibility is measured only in the benchmark set. API cost: US${c}.",
}, es: {
  "cta": "Comparar con modelos de IA",
  "title": "Comparación IA: título, etiquetas, descripción",
  "sub": "Aparece y varios modelos de IA escriben un título, etiquetas y una descripción a partir de los mismos datos verificados. Cada parte se revisa para detectar afirmaciones sin respaldo, se audita y se prueba en un contexto de compra simulado.",
  "controlled": "Evaluación controlada: un contexto de compra simulado con 4 fichas reales de la competencia, juzgado por modelos de IA. No demuestra cómo clasificará un producto ningún asistente o buscador real.",
  "notInSet": "Este producto aún no está en el conjunto de comparación, así que no hay resultados de comparación con IA. Nunca mostramos cifras de otros productos en su lugar.",
  "notInSetTitle": "Aún no hay comparación con IA para este producto",
  "seeSet": "Ver los productos comparados",
  "empty": "Aún no se ha ejecutado. Los resultados aparecen aquí tras una ejecución real de benchmark/shootout/run.py.",
  "best.title": "Mejor título",
  "best.tags": "Mejores etiquetas",
  "best.description": "Mejor descripción",
  "best.visibility": "Mayor visibilidad medida",
  "none": "ninguno pasó",
  "wins": "Productos ganados: {w}",
  "separated": "Por delante de {r} por {d} MRR.",
  "tie": "Sin separación respecto a {r} ({d} MRR); considéralo un empate.",
  "holdoutAgrees": "El juez reservado {j} coincide.",
  "holdoutDisagrees": "El juez reservado {j} no coincide.",
  "generators": "Generadores",
  "col.gen": "Generador",
  "col.qualified": "Sin afirmaciones sin respaldo",
  "col.flagged": "Partes marcadas",
  "col.titleScore": "Auditoría del título",
  "col.tagsScore": "Auditoría de etiquetas",
  "col.coverage": "Datos cubiertos",
  "col.intent": "Intenciones cubiertas",
  "col.mrr": "MRR [IC 95%]",
  "col.mention": "Tasa de mención [IC 95%]",
  "qualifiedNote": "Un generador solo se clasifica si ninguno de sus títulos, etiquetas o descripciones contiene afirmaciones sin respaldo. Las filas en gris se muestran como referencia.",
  "recommended": "Recomendado para este producto",
  "product": "Producto",
  "part.title": "Título",
  "part.tags": "Etiquetas",
  "part.description": "Descripción",
  "recommendedNote": "Cada parte procede del mejor candidato que pasó la revisión de afirmaciones; las etiquetas se combinan solo entre las que pasaron. Revísalo antes de publicar.",
  "candidates": "Todos los candidatos",
  "noTags": "sin etiquetas",
  "caveats": "Advertencias",
  "setup": "{p} productos; jueces {j} (reservado: {h}); {q} preguntas dev/val × {r} repeticiones.",
  "real": "Ejecución real del {d}: jueces y generadores de IA reales, {n} llamadas de juez, US${c} de coste de API según lo registrado por la ejecución.",
  "pass": "supera la revisión",
  "fail": "no supera la revisión",
  "liveRunning": "Comparando este producto ahora: Aparece y los modelos de IA escriben un título, etiquetas y una descripción con sus datos verificados…",
  "liveNote": "Comparación en directo de este producto, hecha ahora. Cada parte se revisó en busca de afirmaciones sin respaldo y se auditó; la visibilidad en IA solo se mide en el conjunto del benchmark. Coste de API: US${c}.",
} };

// Caveats come in English from benchmark/shootout/report.py. Known ones are translated here; anything else is shown
// as is with the "original text in English" marker.
const CAVEATS_ES: [RegExp, string][] = [
  [/^Simulated context: (\d+) product pages chosen by us, not a real search index or live assistant\.$/,
    "Contexto simulado: $1 fichas de producto elegidas por nosotros, no un índice de búsqueda real ni un asistente de IA en funcionamiento."],
  [/^Small n: (\d+) products x (\d+) prompts x (\d+) repeats; CIs are cluster bootstrap over \(product, prompt\)\.$/,
    "Muestra pequeña: $1 productos × $2 preguntas × $3 repeticiones; los intervalos de confianza se calculan con bootstrap por grupos (producto, pregunta)."],
  [/^SAMPLE: the judges were MOCK models \(deterministic fakes\), not OpenAI or Anthropic; the visibility numbers are placeholders and mean nothing\. Only the audits are real\.$/,
    "EJEMPLO: los jueces eran modelos simulados (respuestas fijas), no de OpenAI ni de Anthropic; las cifras de visibilidad son de relleno y no significan nada. Solo las auditorías son reales."],
  [/^Judges are from the same model families as the AI generators \(OpenAI, Anthropic\); self-preference is possible\.$/,
    "Los jueces son de las mismas familias de modelos que los generadores de IA (OpenAI, Anthropic), así que pueden favorecer sus propios textos."],
  [/^Winner chosen on judges other than the held-out one \((.+)\); nothing was tuned on these results\.$/,
    "El ganador se eligió con los jueces que no son el reservado ($1); no se ajustó nada con estos resultados."],
  [/^Guardrail is a strict allowlist: harmless paraphrases can be flagged, which disqualifies that part\.$/,
    "El filtro solo admite palabras respaldadas por los datos: puede marcar paráfrasis inofensivas, y eso descalifica esa parte."],
  [/^Title and tag winners are deterministic audit scores, not measured visibility\.$/,
    "Los ganadores de título y etiquetas salen de puntuaciones de auditoría fijas, no de visibilidad medida."],
  [/^The merchant original is judged against the same Product Truth; the dataset has no merchant tags\.$/,
    "El texto original del comercio se evalúa con los mismos datos verificados; nuestra base de datos no incluye etiquetas del comercio."],
];

/** [text, isOriginalEnglish] for a report caveat in the UI language. */
function caveatText(c: string, lang: string): [string, boolean] {
  if (lang !== "es") return [c, lang !== "en"];
  for (const [re, es] of CAVEATS_ES) if (re.test(c)) return [c.replace(re, es), false];
  return [c, true];
}

function useStr() {
  const { lang } = useI18n();
  return (k: string, v: Record<string, string | number> = {}) =>
    (STR[lang]?.[k] ?? STR.en[k] ?? k).replace(/\{(\w+)\}/g, (_, x) => String(v[x] ?? `{${x}}`));
}

/** Link from an audit result to this page. */
const LIVE_KEY = "pl.compare.";  // sessionStorage: the audited record handed to #/compare/<id> for a live run

export function CompareLink({ productId, record, reportId }: { productId: string; record?: Record<string, unknown> | null; reportId?: string | null }) {
  const s = useStr();
  const keep = () => { try { if (record) sessionStorage.setItem(LIVE_KEY + productId, JSON.stringify(record)); } catch { /* storage off: the report id is enough */ } };
  const q = reportId ? `?report=${encodeURIComponent(reportId)}` : "";
  return <a href={`#/compare/${encodeURIComponent(productId)}${q}`} onClick={keep} className="btn-ghost no-print self-start sm:self-center"><Scale className="size-4" aria-hidden /> {s("cta")}</a>;
}

/** The audited record for a live run: this tab's copy, else the saved audit (GET /v1/audits/{id}) from ?report=. */
async function findRecord(productId?: string): Promise<Record<string, unknown> | null> {
  const local = liveRecord(productId);
  if (local || !productId) return local;
  const rid = new URLSearchParams(location.hash.split("?")[1] || "").get("report");
  if (!rid) return null;
  try { return (await api<{ record: Record<string, unknown> | null }>(`/v1/audits/${encodeURIComponent(rid)}`)).record; } catch { return null; }
}

function liveRecord(productId?: string): Record<string, unknown> | null {
  if (!productId) return null;
  try { const v = sessionStorage.getItem(LIVE_KEY + productId); return v ? JSON.parse(v) : null; } catch { return null; }
}


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
  available: boolean; sample?: boolean; live?: boolean; label?: string; caveats?: string[]; generated_at?: string;
  cost?: { judge_calls?: number; judge_usd?: number; generation_usd?: number };
  setup?: { products: number; judges: string[]; holdout_judge: string | null; prompts_per_product: number; repeats: number };
  overall?: { winner: string | null; runner_up?: string; decisive?: boolean; diff_vs_runner_up?: CI | null;
    holdout_judge?: { judge: string; winner: string | null; agrees: boolean };
    parts: Record<Part, { winner: string | null; wins: Record<string, number> }> };
  generators?: Record<string, Gen>; products?: Product[];
};

/** Display name for a generator id; ids stay unchanged.
 *  "productlens" = Aparece's pipeline with no model (text built from the facts),
 *  "productlens@openai:gpt-4o-mini" = Aparece's pipeline with gpt-4o-mini writing (guardrail, reward, fallback),
 *  "openai:gpt-4o-mini" = the model alone (its own text, same facts), "original" = the shop's text. */
let genLang: "en" | "es" = "en";  // set by the page on render
const genName = (g: string | null | undefined) => {
  if (!g) return g;
  const es = genLang === "es";
  if (g === "original") return es ? "Texto original de la tienda" : "Shop's original";
  if (g === "productlens") return es ? "Aparece (sin modelo de IA)" : "Aparece (no AI model)";
  if (g === "productlens+keywords") return es ? "Aparece + palabras clave" : "Aparece + keywords";
  const m = g.match(/^productlens@[^:]+:(.+)$/);
  if (m) return `Aparece + ${m[1]}`;
  const own = g.match(/^[^:@]+:(.+)$/);
  return own ? (es ? `${own[1]} solo` : `${own[1]} alone`) : g;
};
const PARTS: Part[] = ["title", "tags", "description"];
const pct = (v: number | null | undefined) => (v == null ? "–" : `${Math.round(v * 100)}%`);
const ci = (v: CI | undefined) => (v ? `${v.value.toFixed(2)} [${v.lo.toFixed(2)}–${v.hi.toFixed(2)}]` : "–");
function Pass({ ok }: { ok: boolean }) {
  const t = useStr();
  return ok ? <Check className="size-4 shrink-0 text-emerald-600" aria-label={t("pass")} />
    : <X className="size-4 shrink-0 text-rose-600" aria-label={t("fail")} />;
}

export default function AiComparison({ productId }: { productId?: string }) {
  const { t: tShared, lang } = useI18n();
  const t = useStr();
  genLang = lang === "es" ? "es" : "en";
  const [data, setData] = useState<Report | null>(null);
  const [err, setErr] = useState("");
  const [sel, setSel] = useState<string>("");
  const [live, setLive] = useState<"idle" | "running" | "none">("idle");
  useEffect(() => {
    api<Report>("/v1/shootout").then(async (rep) => {
      const inSaved = !!productId && (rep.products || []).some((p) => p.product_id === productId);
      const rec = inSaved ? null : await findRecord(productId);
      if (!rec) { setData(rep); if (productId && !inSaved) setLive("none"); return; }
      setLive("running");  // not in the saved run: compare this product now (same checks, no simulated shopping test)
      api<Report & { reason?: string }>("/v1/shootout/live", { method: "POST", body: JSON.stringify({ product: rec, language: lang }) })
        .then((r) => { if (r.available) { setData(r); setLive("idle"); } else { setData(rep); setLive("none"); } })
        .catch((e) => { setErr(errorText(e, tShared).msg); setLive("idle"); });
    }).catch((e) => setErr(errorText(e, tShared).msg));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const head = (
    <>
      <h1 className="text-2xl font-bold tracking-tight">{t("title")}</h1>
      <p className="mt-1 max-w-2xl text-sm muted">{t("sub")}</p>
    </>
  );
  const wrap = (body: ReactNode) => <div className="mx-auto max-w-6xl">{head}{body}</div>;
  if (err) return wrap(<p role="alert" className="mt-6 text-rose-700 dark:text-rose-400">{err}</p>);
  if (live === "running") return wrap(<p className="card mt-6 p-6 muted" role="status">{t("liveRunning")}</p>);
  if (!data) return wrap(<div className="card mt-6 h-64 animate-pulse bg-stone-100/60 dark:bg-stone-800/40" aria-hidden />);
  // The API falls back to a mock-judge sample report; never show it as results.
  if (!data.available || data.sample || !data.overall || !data.generators || !data.products) return wrap(<p className="card mt-6 p-6 muted">{t("empty")}</p>);

  const o = data.overall, gens = data.generators, products = data.products;
  const inSet = products.some((p) => p.product_id === productId);
  if (productId && !inSet) return wrap(  // never show another product's numbers for a real product
    <div className="card mt-6 p-6"><p className="font-semibold">{t("notInSetTitle")}</p><p className="mt-1 text-sm muted">{t("notInSet")}</p>
      <a className="btn-outline mt-4" href="#/compare">{t("seeSet")}</a></div>);
  const caveats = (data.caveats || []).map((c) => caveatText(c, lang));
  const cur = products.find((p) => p.product_id === (sel || (inSet ? productId : products[0].product_id)))!;

  return wrap(
    <>
      <p role="note" className="mt-5 flex items-start gap-2 rounded-xl border border-brand-300 bg-brand-50 p-3 text-sm text-brand-900 dark:border-brand-800 dark:bg-brand-950/40 dark:text-brand-200">
        <FlaskConical className="mt-0.5 size-4 shrink-0" aria-hidden />{t("controlled")}
      </p>
      {data.live && <p role="note" className="mt-3 text-sm muted">{t("liveNote", { c: (data.cost?.generation_usd ?? 0).toFixed(4) })}</p>}
      {data.sample === false && !data.live && data.generated_at && (
        <p role="note" className="mt-3 text-sm muted">
          {t("real", { d: data.generated_at.slice(0, 10), n: data.cost?.judge_calls ?? "–",
            c: ((data.cost?.judge_usd ?? 0) + (data.cost?.generation_usd ?? 0)).toFixed(4) })}
        </p>
      )}

      <section className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {PARTS.map((part) => (
          <div key={part} className="card p-5">
            <p className="text-sm muted">{t(`best.${part}`)}</p>
            <p className="mt-1 flex items-center gap-2 text-lg font-semibold"><Trophy className="size-4 text-amber-500" aria-hidden />{genName(o.parts[part].winner) || t("none")}</p>
            <p className="mt-1 text-xs muted">{t("wins", { w: Object.entries(o.parts[part].wins).map(([g, n]) => `${genName(g)} ${n}`).join(", ") || "–" })}</p>
          </div>
        ))}
        <div className="card p-5">
          <p className="text-sm muted">{t("best.visibility")}</p>
          <p className="mt-1 flex items-center gap-2 text-lg font-semibold"><Trophy className="size-4 text-amber-500" aria-hidden />{genName(o.winner) || t("none")}</p>
          <p className="mt-1 text-xs muted">
            {o.diff_vs_runner_up ? t(o.decisive ? "separated" : "tie", { r: genName(o.runner_up)!, d: ci(o.diff_vs_runner_up) }) : ""}
            {o.holdout_judge ? ` ${t(o.holdout_judge.agrees ? "holdoutAgrees" : "holdoutDisagrees", { j: o.holdout_judge.judge })}` : ""}
          </p>
        </div>
      </section>

      <section className="card mt-6 p-5 sm:p-6">
        <h2 className="text-lg font-semibold">{t("generators")}</h2>
        <div className="mt-4 -mx-5 overflow-x-auto sm:-mx-6" role="region" tabIndex={0} aria-label={t("generators")}>
          <table className="w-full min-w-[760px] text-sm">
            <thead className="text-left muted"><tr className="border-b border-stone-200 dark:border-stone-800">
              {["gen", "qualified", "flagged", "titleScore", "tagsScore", "coverage", "intent", "mrr", "mention"].map((k) =>
                <th key={k} scope="col" className="px-3 py-2 font-medium first:pl-5 sm:first:pl-6">{t(`col.${k}`)}</th>)}
            </tr></thead>
            <tbody className="divide-y divide-stone-100 dark:divide-stone-800">
              {Object.entries(gens).map(([g, v]) => (
                <tr key={g} className={v.qualified ? "" : "text-stone-400"}>
                  <th scope="row" className="px-5 py-2 text-left font-medium sm:px-6">{genName(g)}</th>
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
        <p className="mt-3 text-xs muted">{t("qualifiedNote")}</p>
      </section>

      <section className="card mt-6 p-5 sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">{t("recommended")}</h2>
          <label className="text-sm">
            <span className="sr-only">{t("product")}</span>
            <select className="rounded-lg border border-stone-300 bg-white px-2 py-1.5 dark:border-stone-700 dark:bg-stone-900"
              value={cur.product_id} onChange={(e) => setSel(e.target.value)}>
              {products.map((p) => <option key={p.product_id} value={p.product_id}>{p.brand} · {p.name} ({p.language})</option>)}
            </select>
          </label>
        </div>
        <dl className="mt-4 space-y-3 text-sm">
          <div><dt className="font-medium">{t("part.title")} <span className="chip bg-stone-100 dark:bg-stone-800">{genName(cur.recommended.title?.from) || "–"}</span></dt>
            <dd className="mt-1">{cur.recommended.title?.text || t("none")}</dd></div>
          <div><dt className="font-medium">{t("part.tags")} <span className="chip bg-stone-100 dark:bg-stone-800">{cur.recommended.tags?.from.map(genName).join(", ") || "–"}</span></dt>
            <dd className="mt-1 flex flex-wrap gap-1.5">{cur.recommended.tags?.list.map((x) => <span key={x} className="chip bg-brand-50 text-brand-800 dark:bg-brand-950 dark:text-brand-200">{x}</span>) || t("none")}</dd></div>
          <div><dt className="font-medium">{t("part.description")} <span className="chip bg-stone-100 dark:bg-stone-800">{genName(cur.recommended.description?.from) || "–"}</span></dt>
            <dd className="mt-1">{cur.recommended.description?.text || t("none")}</dd></div>
        </dl>
        <p className="mt-3 text-xs muted">{t("recommendedNote")}</p>

        <h3 className="mt-6 font-semibold">{t("candidates")}</h3>
        <ul className="mt-2 divide-y divide-stone-100 dark:divide-stone-800">
          {Object.entries(cur.candidates).map(([g, c]) => (
            <li key={g} className="py-3 text-sm">
              <p className="flex flex-wrap items-center gap-2 font-medium">{genName(g)}
                {Object.entries(cur.part_winners).filter(([, w]) => w === g).map(([part]) =>
                  <span key={part} className="chip bg-emerald-100 text-emerald-800 dark:bg-emerald-900/60 dark:text-emerald-200">{t(`best.${part}`)}</span>)}
                <span className="muted">MRR {ci(c.visibility?.mrr)}</span>
              </p>
              {c.raw.error && <p className="text-rose-700 dark:text-rose-400">{c.raw.error}</p>}
              <p className="mt-1 flex items-start gap-1.5">{c.title && <Pass ok={c.title.passes} />}<span>{c.raw.title || "–"}</span></p>
              <p className="mt-1 flex flex-wrap items-center gap-1.5"><Pass ok={c.tags.passes} />
                {c.raw.tags.length ? c.raw.tags.map((x, i) => <span key={i} className={`chip ${c.tags.false.includes(x) ? "bg-rose-50 text-rose-700 line-through dark:bg-rose-950/50 dark:text-rose-300" : "bg-stone-100 dark:bg-stone-800"}`}>{x}</span>)
                  : <span className="muted">{t("noTags")}</span>}</p>
              <p className="mt-1 flex items-start gap-1.5">{c.description && <Pass ok={c.description.passes} />}<span className="muted">{c.raw.text || "–"}</span></p>
            </li>
          ))}
        </ul>
      </section>

      <section className="card mt-6 p-5 sm:p-6">
        <h2 className="flex items-center gap-2 font-semibold"><Info className="size-5 text-stone-400" aria-hidden />{t("caveats")}</h2>
        <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm muted">
          {caveats.map(([c, en]) => <li key={c} lang={en ? "en" : undefined}>{c}{en && <span className="muted"> ({tShared("mod.origEn")})</span>}</li>)}
          {data.setup && <li>{t("setup", { p: data.setup.products, j: data.setup.judges.join(", "), h: data.setup.holdout_judge || "–", q: data.setup.prompts_per_product, r: data.setup.repeats })}</li>}
        </ul>
      </section>
    </>,
  );
}
