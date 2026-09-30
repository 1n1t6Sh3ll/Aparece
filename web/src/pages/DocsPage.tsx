import { BookOpen, Calculator, Cpu, Radar, Scale, ShieldCheck, Sparkles, Users } from "lucide-react";
import type { ReactNode } from "react";
import { useI18n } from "../lib";

/** #/docs: how Aparece works, in plain words (mirrors docs/HOW_IT_WORKS.md). */
type Doc = {
  title: string; sub: string;
  ideaT: string; idea: string[];
  helpsT: string; helps: [string, string, string][]; helpsCols: [string, string, string];
  stepsT: string; steps: [string, string][];
  genT: string; genIntro: string; gens: [string, string][];
  formT: string; formIntro: string; formulas: [string, string, string][];
  modelsT: string; models: string; modelRows: [string, string][]; modelsNote: string;
  resultsT: string; results: string[];
  neverT: string; never: string[];
  runT: string; run: string; more: string;
};

const EN: Doc = {
  title: "How Aparece works",
  sub: "What it does, what is behind it, and how it helps a shop get found by AI shopping assistants.",
  ideaT: "The idea",
  idea: [
    "Shoppers now ask AI assistants what to buy. The assistant answers from what it can read and trust on product pages. If a small shop's page doesn't state its facts clearly (material, weight, fit, care) in text and markup machines can read, it doesn't get recommended.",
    "We measured it: in 384 real shopping questions to gpt-4o-mini and Claude Haiku (English and Spanish), none of the 103 small shops we tested was named once. Everlane (78 answers), Uniqlo (74) and Patagonia (59) were.",
    "Aparece shows a shop owner what machines can and cannot read on each product page, compares it with similar shirts, and suggests fixes built only from facts the page already proves. It never invents claims.",
  ],
  helpsT: "Who it helps",
  helpsCols: ["Who", "Problem today", "What Aparece gives them"],
  helps: [
    ["Small apparel brand", "Doesn't know why AI assistants and search skip its products", "A rank vs similar shirts, the 3 facts to add first, and text to approve that only states what the page proves"],
    ["Agency with several stores", "Manual audits, guesswork", "Bulk audits with CSV, shareable reports, monitoring with change history"],
    ["Seller whose pages can't be fetched (e.g. Amazon)", "Tools can't read the listing", "Draft audit from pasted text, or the extension on the page open in their own browser"],
    ["Anyone publishing product copy", "AI writers invent claims", "A guardrail that rejects any sentence the facts don't support"],
  ],
  stepsT: "One audit, step by step",
  steps: [
    ["Fetch", "The page is downloaded once, politely. robots.txt is respected, never bypassed; Amazon is never fetched. Blocked? Paste the text or use the extension."],
    ["Verified facts", "Rules read structured data (JSON-LD, microdata, meta tags) and text, in English and Spanish. Every fact keeps the exact page text that proves it; conflicts stay empty, never guessed."],
    ["Rank", "The page is scored against comparable shirts from a 20,037-record dataset (same type, language, audience; widened step by step if few match). Score = key facts stated + shopper questions answered. It is a listing-quality rank, not a Google or AI ranking."],
    ["Top 3 fixes", "Each missing fact that the best-ranked similar shirts state becomes a fix, with the evidence behind it."],
    ["Generate Fix", "Several titles and descriptions are written only from your facts. A guardrail rejects any word or number not backed by them; a reward picks the best grounded one. You approve it; nothing is published for you."],
    ["AI visibility", "Real AI assistants get realistic shopping questions; we record which shops and brands they name and whether their claims match the facts."],
    ["AI comparison", "Your text, Aparece's and AI models' are compared on title, tags and description, live for any audited product."],
    ["Monitor", "Enrolled products are re-checked on a schedule: snapshots, what changed, rank over time, and a chat that may only cite stored data."],
  ],
  genT: "Who writes each version in the AI comparison",
  genIntro: "Every version gets the same verified facts. Then each part (title, tags, description) goes through the same fact-check and scoring.",
  gens: [
    ["Shop's original", "The store's own title and description, as published."],
    ["Aparece (no AI model)", "Aparece builds the text directly from the verified facts with fixed sentence templates. No AI model is involved."],
    ["Aparece + gpt-4o-mini", "gpt-4o-mini writes, but inside Aparece's pipeline: it sees only the verified facts and writes up to 3 candidates. Every sentence goes through the fact-check, flagged sentences are removed, and the reward picks the best candidate. If nothing passes, the template text is used."],
    ["gpt-4o-mini alone / claude-haiku-4-5 alone", "The AI model gets the same facts and instructions, and its own text is used as written, with no filtering. This shows what the model does on its own."],
  ],
  formT: "Formulas: how every number is computed",
  formIntro: "Nothing is a black box. These are the exact rules the code uses.",
  formulas: [
    ["Listing-quality score (0–100)", "score = 60 × (key facts stated ÷ 22) + 20 × (shopper questions answered ÷ 9) + 20 × (schema.org Product and Offer markup found ÷ 2)",
     "The 22 key facts: brand, audience, subcategory, primary material, material %, fabric type, weight (gsm), stretch, texture, fit, neckline, collar, sleeve, length, pattern, style, colours, sizes, price, currency, availability, GTIN. The 9 shopper questions: material, organic material, composition, fabric, stretch, fit, neck/collar, sleeve, care. A question only counts when the description answers it in a sentence that matches a verified fact; keyword lists and repeated text don't count. If markup is unknown for any compared shirt, markup is dropped for all and the weights become 75 / 25."],
    ["Rank", "position = 1 + number of comparable shirts with a higher score (ties share a position)",
     "Comparable = same product type, language and audience, up to 25 shirts. With fewer than 10 matches it widens step by step: drop the price band, then the sleeve length, then any shirt type. The page says which step was used. Every shirt in one ranking is scored with the same formula."],
    ["Top 3 fixes", "order = missing facts (most often stated by the 10 best-ranked similar shirts first) → description → structured markup → price → language; the first 3 are shown",
     "Each fix shows its evidence, e.g. \"8 of the 10 top-ranked similar shirts state their fabric weight\"."],
    ["Fact-check (guardrail)", "a sentence passes only if every word comes from your verified facts or a small neutral vocabulary, and every number is the verified value of the field it describes",
     "Allowed numbers: material %, weight in gsm, price (and sale price), sizes, 3/4 sleeve, and care temperatures stated on the page. Possessives of verified words (\"men's\" from \"For men\") are fine. Marketing words the page doesn't back up (\"premium\", \"breathable\", \"classic\") are flagged."],
    ["Generate Fix reward", "reward = 1 (valid title ≤ 90 chars + description) + 1 × share of sentences that pass the fact-check − 2 × each flagged sentence + 2 × share of your verified facts the text states",
     "An invalid format scores −10. A candidate with any flagged sentence can never win, whatever its reward."],
    ["Title score (comparison)", "title score = (brand present + product type present + material present + fit present + length 15–90 chars) ÷ number of checks that apply",
     "A check is skipped when the fact is unknown. The title must also pass the fact-check."],
    ["Tags score (comparison)", "tags score = average(fact relevance, shopper-intent relevance, language match) × share of unique tags × share of tags that pass the fact-check",
     "Aparece builds up to 8 tags from the verified facts (type, materials, fit, sleeve, neckline, pattern, audience, colours, gsm); AI models write their own. Every tag goes through the fact-check; a tag may name the product or brand itself, and a false one (e.g. \"organic cotton\" on a viscose shirt) is crossed out. Fact relevance = tags naming a verified fact; intent relevance = tags matching words shoppers use; language match = tags in the page's language. The recommended tags start with the winner's passing tags and add others' passing tags, up to 8, no duplicates."],
    ["Description (comparison)", "attribute coverage = verified facts the text states correctly ÷ facts in the full fact list;  intent coverage = shopper questions it addresses ÷ questions asked;  readability = Flesch reading ease (English) or Fernández-Huerta (Spanish)",
     "The description must pass the fact-check to be eligible."],
    ["Winner of each part", "title: highest title score (closest to 60 characters breaks ties); tags: highest tags score; description: highest measured AI visibility (MRR) when available, else highest attribute coverage",
     "Only parts that pass the fact-check can win. The recommended version combines the winning parts."],
    ["AI visibility", "mention rate = answers that name the shop ÷ answers;  top-3 rate = answers that name it among the first 3 ÷ answers;  MRR = average of 1 ÷ (position of the first mention), 0 when not named",
     "Confidence intervals use a bootstrap over (product, question). Two versions whose intervals overlap are reported as a tie."],
    ["Fact extraction accuracy (models)", "non-null accuracy = correct values ÷ fields the answer key has a value for;  null accuracy = fields correctly left empty ÷ fields the answer key leaves empty;  JSON valid = outputs that parse",
     "Exact match against our own label format, on 200 test products from 63 stores."],
  ],
  modelsT: "The models behind it",
  models: "A small language model was fine-tuned to read product pages into the same fact format. It only fills fields the rules left empty, and its output is labelled \"predicted\", never \"verified\". On 200 test products from 63 stores:",
  modelRows: [["Aparece Qwen2.5-0.5B, fine-tuned", "85.8% of facts correct"], ["GPT-4.1 (prompt only)", "27.2%"], ["Qwen2.5-0.5B, untuned", "4.7%"]],
  modelsNote: "Exact-match scoring on our own label format, which favours the fine-tuned model. Weights are on GitHub (release weights-v1).",
  resultsT: "Measured results",
  results: [
    "AI comparison (5 products, EN/ES): Aparece best on title, tags and description with no unsupported claims; AI-visibility a statistical tie.",
    "AI visibility (384 answers, 2 models): 0% mention rate for the small shops tested; big brands named instead.",
    "Live comparison example (Rivera Laredo tee): Aparece 0 flagged sentences; Claude Haiku 1; gpt-4o-mini 7; the shop's original 8. Most AI flags are wording the page doesn't back up (\"classic\", \"comfort\", \"designed\"). Cost $0.0023.",
  ],
  neverT: "What Aparece will not do",
  never: [
    "Bypass robots.txt, bot checks or rate limits, or fetch Amazon pages.",
    "Invent facts: missing stays missing; a guess is labelled as a prediction.",
    "Claim a fix will raise your Google or AI ranking: we report observed differences, not causes.",
    "Publish anything to your store without your approval.",
  ],
  runT: "Run it yourself",
  run: "docker run -p 8000:8000 ghcr.io/1n1t6sh3ll/powerlens:latest   ·   or: git clone, then ./run.sh",
  more: "Full technical reference, API routes and settings: docs/REFERENCE.md in the GitHub repository.",
};

const ES: Doc = {
  title: "Cómo funciona Aparece",
  sub: "Qué hace, qué hay detrás y cómo ayuda a que los asistentes de compra con IA encuentren una tienda.",
  ideaT: "La idea",
  idea: [
    "Hoy la gente pregunta a asistentes de IA qué comprar. El asistente responde con lo que puede leer y verificar en las fichas de producto. Si la ficha de una tienda pequeña no deja claros sus datos (material, gramaje, corte, cuidados) en texto y marcado legibles por máquinas, no la recomienda.",
    "Lo medimos: en 384 preguntas de compra reales a gpt-4o-mini y Claude Haiku (en inglés y español), ninguna de las 103 tiendas pequeñas analizadas apareció ni una vez. Sí aparecieron Everlane (78 respuestas), Uniqlo (74) y Patagonia (59).",
    "Aparece muestra al dueño de la tienda qué pueden y qué no pueden leer las máquinas en cada ficha, la compara con camisetas similares y propone arreglos basados solo en datos que la página ya demuestra. Nunca inventa afirmaciones.",
  ],
  helpsT: "A quién ayuda",
  helpsCols: ["Quién", "Problema hoy", "Qué le da Aparece"],
  helps: [
    ["Marca de ropa pequeña", "No sabe por qué los asistentes de IA y los buscadores ignoran sus productos", "Una posición frente a camisetas similares, los 3 datos que añadir primero y textos para aprobar que solo dicen lo que la página demuestra"],
    ["Agencia con varias tiendas", "Auditorías manuales y a ciegas", "Auditorías masivas con CSV, informes para compartir y seguimiento con historial de cambios"],
    ["Vendedor cuyas fichas no se pueden leer (p. ej. Amazon)", "Las herramientas no leen la ficha", "Auditoría de borrador con el texto pegado, o la extensión sobre la página abierta en su propio navegador"],
    ["Quien publique textos de producto", "Los redactores con IA inventan datos", "Un filtro que rechaza cualquier frase que los datos no respalden"],
  ],
  stepsT: "Una auditoría, paso a paso",
  steps: [
    ["Descarga", "La página se descarga una vez y con respeto: se cumple robots.txt, nunca se salta, y nunca se descarga Amazon. ¿Bloqueada? Pega el texto o usa la extensión."],
    ["Datos verificados", "Unas reglas leen los datos estructurados (JSON-LD, microdatos, metaetiquetas) y el texto, en inglés y español. Cada dato guarda el texto exacto que lo demuestra; si hay contradicciones, se deja vacío, nunca se adivina."],
    ["Posición", "La página se puntúa frente a camisetas comparables de una base de 20.037 fichas (mismo tipo, idioma y público; se amplía paso a paso si hay pocas). Puntuación = datos clave presentes + preguntas del comprador respondidas. Es una posición de calidad de ficha, no de Google ni de IA."],
    ["Los 3 arreglos", "Cada dato que falta y que sí indican las mejores camisetas similares se convierte en un arreglo, con su evidencia."],
    ["Generar arreglo", "Se escriben varios títulos y descripciones solo con tus datos. Un filtro rechaza cualquier palabra o cifra sin respaldo, y una recompensa elige el mejor. Tú lo apruebas; no se publica nada por ti."],
    ["Visibilidad en IA", "Se hacen preguntas de compra reales a asistentes de IA y se registra qué tiendas y marcas nombran y si lo que dicen coincide con los datos."],
    ["Comparación con IA", "Tu texto, el de Aparece y el de los modelos de IA se comparan en título, etiquetas y descripción, en directo para cualquier producto auditado."],
    ["Seguimiento", "Los productos inscritos se revisan periódicamente: capturas, qué cambió, posición en el tiempo y un chat que solo puede citar datos guardados."],
  ],
  genT: "Quién escribe cada versión en la comparación con IA",
  genIntro: "Todas las versiones reciben los mismos datos verificados. Después, cada parte (título, etiquetas, descripción) pasa por la misma revisión de datos y la misma puntuación.",
  gens: [
    ["Texto original de la tienda", "El título y la descripción de la tienda, tal como están publicados."],
    ["Aparece (sin modelo de IA)", "Aparece construye el texto directamente con los datos verificados y plantillas de frases fijas. No interviene ningún modelo de IA."],
    ["Aparece + gpt-4o-mini", "gpt-4o-mini escribe, pero dentro del proceso de Aparece: solo ve los datos verificados y escribe hasta 3 propuestas. Cada frase pasa la revisión, las frases marcadas se eliminan y la recompensa elige la mejor propuesta. Si ninguna pasa, se usa el texto de plantilla."],
    ["gpt-4o-mini solo / claude-haiku-4-5 solo", "El modelo recibe los mismos datos e instrucciones y se usa su texto tal cual, sin filtrar. Así se ve lo que hace el modelo por sí mismo."],
  ],
  formT: "Fórmulas: cómo se calcula cada cifra",
  formIntro: "Nada es una caja negra. Estas son las reglas exactas que usa el código.",
  formulas: [
    ["Puntuación de calidad de la ficha (0–100)", "puntuación = 60 × (datos clave presentes ÷ 22) + 20 × (preguntas del comprador respondidas ÷ 9) + 20 × (marcado schema.org Product y Offer encontrado ÷ 2)",
     "Los 22 datos clave: marca, público, subcategoría, material principal, % de materiales, tipo de tejido, gramaje (g/m²), elasticidad, textura, corte, escote, cuello, manga, largo, estampado, estilo, colores, tallas, precio, moneda, disponibilidad, GTIN. Las 9 preguntas: material, material orgánico, composición, tejido, elasticidad, corte, escote/cuello, manga, cuidados. Una pregunta solo cuenta si la descripción la responde en una frase que coincide con un dato verificado; las listas de palabras clave y el texto repetido no cuentan. Si el marcado es desconocido para alguna camiseta comparada, se elimina para todas y los pesos pasan a 75 / 25."],
    ["Posición", "posición = 1 + número de camisetas comparables con mayor puntuación (los empates comparten posición)",
     "Comparables = mismo tipo de producto, idioma y público, hasta 25 camisetas. Con menos de 10 coincidencias se amplía paso a paso: sin franja de precio, luego sin largo de manga y luego cualquier tipo de camiseta. La página indica qué paso se usó. Todas las camisetas de una misma clasificación se puntúan con la misma fórmula."],
    ["Los 3 arreglos", "orden = datos que faltan (primero los que más indican las 10 camisetas similares mejor posicionadas) → descripción → marcado estructurado → precio → idioma; se muestran los 3 primeros",
     "Cada arreglo muestra su evidencia, p. ej. \"8 de las 10 camisetas similares mejor posicionadas indican su gramaje\"."],
    ["Revisión de datos (filtro)", "una frase pasa solo si cada palabra sale de tus datos verificados o de un vocabulario neutro pequeño, y cada cifra es el valor verificado del campo que describe",
     "Cifras permitidas: % de materiales, gramaje, precio (y precio rebajado), tallas, manga 3/4 y temperaturas de cuidado indicadas en la página. Los posesivos de palabras verificadas están permitidos. Las palabras de marketing sin respaldo (\"premium\", \"transpirable\", \"clásico\") se marcan."],
    ["Recompensa de Generar arreglo", "recompensa = 1 (título válido de ≤ 90 caracteres + descripción) + 1 × proporción de frases que pasan la revisión − 2 × cada frase marcada + 2 × proporción de tus datos verificados que menciona el texto",
     "Un formato no válido puntúa −10. Una propuesta con alguna frase marcada nunca puede ganar, sea cual sea su recompensa."],
    ["Puntuación del título (comparación)", "puntuación = (marca presente + tipo de producto presente + material presente + corte presente + largo de 15–90 caracteres) ÷ número de comprobaciones aplicables",
     "Una comprobación se omite si el dato es desconocido. El título también debe pasar la revisión de datos."],
    ["Puntuación de etiquetas (comparación)", "puntuación = media(relevancia de datos, relevancia para el comprador, idioma correcto) × proporción de etiquetas únicas × proporción de etiquetas que pasan la revisión",
     "Aparece crea hasta 8 etiquetas con los datos verificados (tipo, materiales, corte, manga, escote, estampado, público, colores, gramaje); los modelos de IA escriben las suyas. Cada etiqueta pasa la revisión de datos; puede nombrar el producto o la marca, y una falsa (p. ej. \"algodón orgánico\" en una camiseta de viscosa) se tacha. Relevancia de datos = etiquetas que nombran un dato verificado; relevancia para el comprador = etiquetas con palabras que usan los compradores; idioma = etiquetas en el idioma de la página. Las etiquetas recomendadas empiezan por las válidas del ganador y añaden las válidas de los demás, hasta 8, sin repetir."],
    ["Descripción (comparación)", "cobertura de datos = datos verificados que el texto indica correctamente ÷ datos de la lista completa;  cobertura de intención = preguntas del comprador que trata ÷ preguntas;  legibilidad = Flesch (inglés) o Fernández-Huerta (español)",
     "La descripción debe pasar la revisión de datos para poder ganar."],
    ["Ganador de cada parte", "título: mayor puntuación de título (desempata el más cercano a 60 caracteres); etiquetas: mayor puntuación de etiquetas; descripción: mayor visibilidad en IA medida (MRR) si existe, si no mayor cobertura de datos",
     "Solo pueden ganar las partes que pasan la revisión. La versión recomendada combina las partes ganadoras."],
    ["Visibilidad en IA", "tasa de mención = respuestas que nombran la tienda ÷ respuestas;  tasa top-3 = respuestas que la nombran entre las 3 primeras ÷ respuestas;  MRR = media de 1 ÷ (posición de la primera mención), 0 si no aparece",
     "Los intervalos de confianza usan bootstrap por (producto, pregunta). Si los intervalos de dos versiones se solapan, se informa de un empate."],
    ["Precisión de extracción (modelos)", "precisión no nula = valores correctos ÷ campos con valor en la clave de respuestas;  precisión nula = campos dejados vacíos correctamente ÷ campos vacíos en la clave;  JSON válido = respuestas que se pueden leer",
     "Coincidencia exacta con nuestro propio formato de etiquetas, en 200 productos de prueba de 63 tiendas."],
  ],
  modelsT: "Los modelos detrás",
  models: "Se ajustó un modelo de lenguaje pequeño para leer fichas de producto en el mismo formato de datos. Solo rellena campos que las reglas dejaron vacíos, y su resultado se marca como \"previsto\", nunca como \"verificado\". Con 200 productos de prueba de 63 tiendas:",
  modelRows: [["Aparece Qwen2.5-0.5B, ajustado", "85,8 % de datos correctos"], ["GPT-4.1 (solo instrucciones)", "27,2 %"], ["Qwen2.5-0.5B sin ajustar", "4,7 %"]],
  modelsNote: "Puntuación de coincidencia exacta con nuestro propio formato de etiquetas, lo que favorece al modelo ajustado. Los pesos están en GitHub (versión weights-v1).",
  resultsT: "Resultados medidos",
  results: [
    "Comparación con IA (5 productos, EN/ES): Aparece gana en título, etiquetas y descripción sin afirmaciones sin respaldo; en visibilidad, empate estadístico.",
    "Visibilidad en IA (384 respuestas, 2 modelos): 0 % de menciones para las tiendas pequeñas analizadas; se nombraron grandes marcas.",
    "Ejemplo en directo (camiseta Rivera Laredo): Aparece 0 frases marcadas; Claude Haiku 1; gpt-4o-mini 7; el texto original de la tienda 8. La mayoría de las marcas a la IA son palabras que la página no respalda (\"clásico\", \"comodidad\", \"diseñado\"). Coste 0,0023 $.",
  ],
  neverT: "Lo que Aparece no hará",
  never: [
    "Saltarse robots.txt, comprobaciones antibots o límites de peticiones, ni descargar páginas de Amazon.",
    "Inventar datos: lo que falta sigue faltando; una suposición se marca como previsión.",
    "Prometer que un arreglo subirá tu posición en Google o en IA: mostramos diferencias observadas, no causas.",
    "Publicar nada en tu tienda sin tu aprobación.",
  ],
  runT: "Ejecútalo tú",
  run: "docker run -p 8000:8000 ghcr.io/1n1t6sh3ll/powerlens:latest   ·   o bien: git clone y después ./run.sh",
  more: "Referencia técnica completa, rutas de la API y ajustes: docs/REFERENCE.md en el repositorio de GitHub.",
};

function Section({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <section className="card mt-6 p-5 sm:p-6">
      <h2 className="flex items-center gap-2 text-lg font-semibold">{icon}{title}</h2>
      <div className="mt-3 space-y-3 text-sm leading-relaxed">{children}</div>
    </section>
  );
}

export default function DocsPage() {
  const { lang } = useI18n();
  const d = lang === "es" ? ES : EN;
  const ic = "size-5 text-[var(--accent)]";
  return (
    <div className="mx-auto max-w-4xl">
      <h1 className="text-2xl font-bold tracking-tight">{d.title}</h1>
      <p className="mt-1 max-w-2xl text-sm muted">{d.sub}</p>

      <Section icon={<Sparkles className={ic} aria-hidden />} title={d.ideaT}>
        {d.idea.map((p) => <p key={p}>{p}</p>)}
      </Section>

      <Section icon={<Users className={ic} aria-hidden />} title={d.helpsT}>
        <div className="-mx-5 overflow-x-auto sm:-mx-6" role="region" tabIndex={0} aria-label={d.helpsT}>
          <table className="w-full min-w-[640px] text-sm">
            <thead className="text-left muted"><tr className="border-b border-stone-200 dark:border-stone-800">
              {d.helpsCols.map((c) => <th key={c} scope="col" className="px-3 py-2 font-medium first:pl-5 sm:first:pl-6">{c}</th>)}
            </tr></thead>
            <tbody className="divide-y divide-stone-100 dark:divide-stone-800">
              {d.helps.map(([w, p, g]) => (
                <tr key={w}><th scope="row" className="px-5 py-2 text-left align-top font-medium sm:px-6">{w}</th>
                  <td className="px-3 py-2 align-top muted">{p}</td><td className="px-3 py-2 align-top">{g}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section icon={<BookOpen className={ic} aria-hidden />} title={d.stepsT}>
        <ol className="space-y-3">
          {d.steps.map(([h, b], i) => (
            <li key={h} className="flex gap-3">
              <span className="grid size-6 shrink-0 place-items-center rounded-full bg-[var(--accent)] text-xs font-semibold text-white">{i + 1}</span>
              <p><span className="font-semibold">{h}.</span> {b}</p>
            </li>
          ))}
        </ol>
      </Section>

      <Section icon={<Scale className={ic} aria-hidden />} title={d.genT}>
        <p className="muted">{d.genIntro}</p>
        <dl className="divide-y divide-stone-100 dark:divide-stone-800">
          {d.gens.map(([n, w]) => <div key={n} className="py-2.5"><dt className="font-semibold">{n}</dt><dd className="mt-0.5 muted">{w}</dd></div>)}
        </dl>
      </Section>

      <Section icon={<Calculator className={ic} aria-hidden />} title={d.formT}>
        <p className="muted">{d.formIntro}</p>
        <div className="space-y-4">
          {d.formulas.map(([n, f, x]) => (
            <div key={n}>
              <p className="font-semibold">{n}</p>
              <p className="mt-1 overflow-x-auto rounded-lg bg-[var(--surface-2)] px-3 py-2 font-mono text-xs leading-relaxed">{f}</p>
              <p className="mt-1 text-xs muted">{x}</p>
            </div>
          ))}
        </div>
      </Section>

      <Section icon={<Cpu className={ic} aria-hidden />} title={d.modelsT}>
        <p>{d.models}</p>
        <ul className="divide-y divide-stone-100 dark:divide-stone-800">
          {d.modelRows.map(([m, v]) => <li key={m} className="flex justify-between gap-3 py-2"><span>{m}</span><span className="font-semibold tabular-nums">{v}</span></li>)}
        </ul>
        <p className="text-xs muted">{d.modelsNote}</p>
      </Section>

      <Section icon={<Radar className={ic} aria-hidden />} title={d.resultsT}>
        <ul className="list-disc space-y-1.5 pl-5">{d.results.map((r) => <li key={r}>{r}</li>)}</ul>
      </Section>

      <Section icon={<ShieldCheck className={ic} aria-hidden />} title={d.neverT}>
        <ul className="list-disc space-y-1.5 pl-5">{d.never.map((r) => <li key={r}>{r}</li>)}</ul>
      </Section>

      <Section icon={<BookOpen className={ic} aria-hidden />} title={d.runT}>
        <pre className="overflow-x-auto rounded-lg bg-[var(--surface-2)] p-3 text-xs"><code>{d.run}</code></pre>
        <p className="text-xs muted">{d.more}</p>
      </Section>
    </div>
  );
}
