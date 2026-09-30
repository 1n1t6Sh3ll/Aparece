import { useRef, useState } from "react";
import { CheckCircle2, Download, Loader2, Play, Printer, Square, XCircle, Clock } from "lucide-react";
import { errorText, fieldLabel, money, useI18n } from "../lib";
import type { Audit } from "../types";
import { runAudit } from "./AuditPage";
import { actionText } from "./Results";

type Row = { url: string; status: "queued" | "running" | "done" | "error"; audit?: Audit; error?: string };
const MAX = 20;

export function csvCell(v: unknown) {
  let s = v == null ? "" : String(v);
  if (/^[=+\-@\t\r]/.test(s)) s = "'" + s; // spreadsheet formula injection guard
  return `"${s.replace(/"/g, '""')}"`;
}

export default function BulkPage() {
  const { t, lang } = useI18n();
  const [text, setText] = useState("");
  const [rows, setRows] = useState<Row[]>([]);
  const [running, setRunning] = useState(false);
  const [msg, setMsg] = useState("");
  const stop = useRef(false);

  const urls = text.split(/\s+/).map((u) => u.trim()).filter((u) => /^https?:\/\//i.test(u));

  async function run() {
    const list = [...new Set(urls)].slice(0, MAX);
    if (!list.length) return setMsg(t("bulk.none"));
    setMsg(urls.length > MAX ? t("bulk.tooMany") : "");
    stop.current = false;
    setRunning(true);
    const rs: Row[] = list.map((url) => ({ url, status: "queued" }));
    setRows([...rs]);
    for (let i = 0; i < rs.length && !stop.current; i++) {
      rs[i] = { ...rs[i], status: "running" }; setRows([...rs]);
      try {
        rs[i] = { ...rs[i], status: "done", audit: await runAudit({ url: rs[i].url }) };
      } catch (e) {
        rs[i] = { ...rs[i], status: "error", error: errorText(e, t).msg };
      }
      setRows([...rs]);
    }
    setRunning(false);
  }

  function csv() {
    const head = ["url", "product", "status", "rank", "of", "listing_quality", "facts_found", "facts_checked", "fix_1", "fix_2", "fix_3", "price", "currency", "price_position", "error"];
    const lines = rows.map((r) => {
      const a = r.audit;
      const fixes = a ? a.actions.slice(0, 3).map((x) => actionText(x, a, t, lang).title) : [];
      return [r.url, a?.product.title, r.status, a?.rank.position, a?.rank.total, a?.rank.score, a?.summary.facts_found, a?.summary.attributes_checked,
        fixes[0], fixes[1], fixes[2], a?.product.price, a?.product.currency, a?.price_position.position, r.error].map(csvCell).join(",");
    });
    const blob = new Blob(["﻿" + [head.join(","), ...lines].join("\r\n")], { type: "text/csv;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `productlens-audit-${new Date().toISOString().slice(0, 10)}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
  }

  const doneN = rows.filter((r) => r.status === "done" || r.status === "error").length;
  const Status = ({ r }: { r: Row }) => {
    const m = { queued: [Clock, "text-stone-400"], running: [Loader2, "text-brand-500 animate-spin"], done: [CheckCircle2, "text-emerald-600"], error: [XCircle, "text-rose-600"] } as const;
    const [Icon, cls] = m[r.status];
    return <span className="inline-flex items-center gap-1.5 whitespace-nowrap"><Icon className={`size-4 ${cls}`} aria-hidden />{t(`bulk.st.${r.status}`)}</span>;
  };

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:py-14">
      <div className="no-print">
        <h1 className="text-3xl font-extrabold tracking-tight sm:text-4xl">{t("bulk.title")}</h1>
        <p className="mt-2 max-w-2xl muted">{t("bulk.sub")}</p>
        <div className="card mt-6 p-4 sm:p-5">
          <label htmlFor="bulk" className="sr-only">{t("bulk.title")}</label>
          <textarea id="bulk" rows={6} className="input font-mono text-sm" value={text} onChange={(e) => setText(e.target.value)} placeholder={t("bulk.placeholder")} disabled={running} />
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {running ? (
              <button className="btn-ghost border border-stone-300 dark:border-stone-700" onClick={() => { stop.current = true; }}><Square className="size-4" aria-hidden /> {t("bulk.stop")}</button>
            ) : (
              <button className="btn-primary" onClick={run} disabled={!urls.length}><Play className="size-4" aria-hidden /> {t("bulk.run", { n: Math.min(new Set(urls).size, MAX) })}</button>
            )}
            {rows.length > 0 && !running && <>
              <button className="btn-ghost" onClick={csv}><Download className="size-4" aria-hidden /> {t("bulk.csv")}</button>
              <button className="btn-ghost" onClick={() => window.print()}><Printer className="size-4" aria-hidden /> {t("bulk.print")}</button>
            </>}
            {running && <span className="text-sm muted" role="status">{doneN} / {rows.length}</span>}
            {msg && <span className="text-sm text-amber-700 dark:text-amber-400" role="alert">{msg}</span>}
          </div>
        </div>
      </div>

      {rows.length > 0 && (
        <section className="mt-8">
          <div className="hidden print:block">
            <h1 className="text-2xl font-bold">{t("bulk.reportTitle")}</h1>
            <p className="text-sm">{new Date().toLocaleDateString(lang)} · {t("bulk.reportNote")}</p>
          </div>
          <div className="card mt-4 overflow-x-auto" role="region" aria-label={t("bulk.title")} tabIndex={0}>
            <table className="w-full min-w-[760px] text-sm">
              <thead className="border-b border-stone-200 text-left muted dark:border-stone-800">
                <tr>
                  <th scope="col" className="px-4 py-3 font-medium">{t("bulk.col.product")}</th>
                  <th scope="col" className="px-4 py-3 font-medium">{t("bulk.col.status")}</th>
                  <th scope="col" className="px-4 py-3 font-medium">{t("rank.eyebrow")}</th>
                  <th scope="col" className="px-4 py-3 font-medium">{t("bulk.col.facts")}</th>
                  <th scope="col" className="px-4 py-3 font-medium">{t("bulk.col.fix")}</th>
                  <th scope="col" className="px-4 py-3 font-medium">{t("bulk.col.price")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100 dark:divide-stone-800">
                {rows.map((r) => {
                  const a = r.audit;
                  return (
                    <tr key={r.url} className="align-top">
                      <td className="max-w-[16rem] px-4 py-3">
                        <p className="truncate font-medium">{a?.product.title || r.url}</p>
                        <a href={r.url} target="_blank" rel="noopener noreferrer" className="block truncate text-xs muted hover:underline">{r.url}</a>
                      </td>
                      <td className="px-4 py-3"><Status r={r} />{r.error && <p className="mt-1 max-w-[14rem] text-xs text-rose-700 dark:text-rose-400">{r.error}</p>}</td>
                      <td className="px-4 py-3 tabular-nums">{a && a.rank.total > 1 ? <><b>#{a.rank.position}</b> <span className="muted">/ {a.rank.total}</span></> : null}</td>
                      <td className="px-4 py-3 tabular-nums">{a ? `${a.summary.facts_found} / ${a.summary.attributes_checked}` : null}</td>
                      <td className="px-4 py-3">
                        {a && <ol className="list-inside list-decimal space-y-0.5">
                          {a.actions.slice(0, 3).map((x) => <li key={x.id}>{x.kind === "missing_attribute" && x.field ? fieldLabel(lang, x.field) : actionText(x, a, t, lang).title}</li>)}
                        </ol>}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">{a?.product.price != null ? <>{money(a.product.price, a.product.currency, lang)}{a.price_position.position && <span className="block text-xs muted">{t(`pos.${a.price_position.position}`)}</span>}</> : null}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
