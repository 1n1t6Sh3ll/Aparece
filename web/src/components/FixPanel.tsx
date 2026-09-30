import { useState } from "react";
import { Check, Copy, Loader2, PenLine, X } from "lucide-react";
import { api, errorText, fieldLabel, useI18n } from "../lib";

type Sugg = { title: string; description: string; missing_attributes?: { field: string }[] | string[]; json_ld?: unknown };
export type FixDecision = { status: "accepted" | "dismissed"; original: string; suggested: string };

/**
 * "Generate fix": POST /v1/optimize on the audited record (Product Truth) and show current vs suggested text.
 * Accept copies the text for the merchant to paste; nothing is ever published from here.
 */
export default function FixPanel({ record, decisions, onDecide, compact = false }: {
  record: Record<string, unknown>; decisions: Record<string, FixDecision>;
  onDecide: (field: "title" | "description", d: FixDecision) => void | Promise<void>; compact?: boolean;
}) {
  const { t, lang } = useI18n();
  const [s, setS] = useState<Sugg | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "error">("idle");
  const [err, setErr] = useState("");
  const content = (record.content || {}) as { title?: string; full_description?: string };
  const original = { title: content.title || "", description: content.full_description || "" };

  async function run() {
    setState("loading");
    try {
      setS(await api<Sugg>("/v1/optimize", { method: "POST", body: JSON.stringify({ product: record, language: lang }) }));
      setState("idle");
    } catch (e) { setErr(errorText(e, t).msg); setState("error"); }
  }
  const missing = (s?.missing_attributes || []).map((m) => (typeof m === "string" ? m : m.field)).filter(Boolean);
  return (
    <section className={compact ? "no-print mt-4 rounded-md border border-dashed border-[var(--border)] p-3" : "card no-print p-4 sm:p-5"} aria-labelledby="fix-h">
      <div className="flex flex-wrap items-center gap-2">
        <h2 id="fix-h" className="mr-auto flex items-center gap-2 text-sm font-semibold"><PenLine className="size-4" aria-hidden /> {t("sug.title")}</h2>
        <button className={s ? "btn-ghost px-2 text-sm" : "btn-primary"} onClick={run} disabled={state === "loading"}>
          {state === "loading" ? <Loader2 className="size-4 animate-spin" aria-hidden /> : <PenLine className="size-4" aria-hidden />} {s ? t("sug.again") : t("sug.run")}
        </button>
      </div>
      <p className="mt-1 text-xs muted">{t("sug.note")}</p>
      {state === "error" && <p role="alert" className="mt-2 text-sm text-rose-700 dark:text-rose-400">{err}</p>}
      {s && (["title", "description"] as const).map((f) => {
        const d = decisions[f];
        return (
          <div key={f} className="mt-4 grid gap-3 sm:grid-cols-2">
            <div><p className="text-xs font-medium muted">{t(`sug.orig.${f}`)}</p><p className="mt-1 whitespace-pre-line rounded-md bg-[var(--surface-2)] p-2 text-sm">{original[f] || t("sug.empty")}</p></div>
            <div><p className="text-xs font-medium muted">{t(`sug.new.${f}`)}</p><p className="mt-1 rounded-md bg-emerald-50 p-2 text-sm dark:bg-emerald-950/40">{s[f]}</p>
              <div className="mt-1 flex items-center gap-2 text-sm">
                {d && d.suggested === s[f] ? <span className="chip bg-[var(--surface-2)]">{t(`sug.${d.status}`)}</span> : <>
                  <button className="btn-ghost px-2 py-1 text-emerald-800 dark:text-emerald-400" onClick={() => { navigator.clipboard?.writeText(s[f]).catch(() => undefined); onDecide(f, { status: "accepted", original: original[f], suggested: s[f] }); }}><Check className="size-4" aria-hidden /> {t("sug.accept")}</button>
                  <button className="btn-ghost px-2 py-1" onClick={() => onDecide(f, { status: "dismissed", original: original[f], suggested: s[f] })}><X className="size-4" aria-hidden /> {t("sug.dismiss")}</button>
                  <button className="btn-ghost p-1.5" aria-label={t("ob.copy")} onClick={() => navigator.clipboard?.writeText(s[f]).catch(() => undefined)}><Copy className="size-3.5" aria-hidden /></button>
                </>}
              </div>
            </div>
          </div>
        );
      })}
      {s && missing.length > 0 && <p className="mt-4 text-xs muted">{t("sug.missing")}: {missing.map((f) => fieldLabel(lang, f)).join(", ")}</p>}
      {s && <p className="mt-2 text-xs muted">{t("sug.publish")}</p>}
    </section>
  );
}
