import { useMemo, useRef, useState } from "react";
import { CheckCircle2, Download, Loader2, Play, Printer, Square, XCircle, Clock } from "lucide-react";
import { errorText, money, useI18n, type Lang, type T } from "../lib";
import { parseBulk, type BulkItem } from "../bulk";
import { factCount } from "../facts";
import type { Audit } from "../types";
import { runAudit } from "./AuditPage";
import { actionText } from "./Results";

type Row = { key: string; line: number; label: string; body: BulkItem["body"]; status: "queued" | "running" | "done" | "error"; audit?: Audit; error?: string };

/** The cells shown in the table AND written to the CSV, built once from the same audit (issue #102). */
function cells(r: Row, t: T, lang: Lang) {
  const a = r.audit;
  const fc = a && factCount(a);
  return {
    input: r.body.url || r.body.title || "", kind: r.body.url ? "url" : "draft", product: a?.product.title || r.label,
    status: t(`bulk.st.${r.status}`), error: r.error || "",
    rank: a ? (a.rank.total > 1 ? t("rep.rank", { pos: a.rank.position, total: a.rank.total }) : t("rep.noPeers")) : "",
    score: a ? a.rank.score : "", facts: fc ? `${fc.n} / ${fc.of}` : "",
    fixes: a ? a.actions.slice(0, 3).map((x) => actionText(x, a, t, lang).title) : [],
    price: a?.product.price != null ? money(a.product.price, a.product.currency, lang) : "",
    position: a?.price_position.position ? t(`pos.${a.price_position.position}`) : "",
  };
}

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
  const stop = useRef(false);
  const parsed = useMemo(() => parseBulk(text), [text]);

  async function run() {
    if (!parsed.items.length) return;
    stop.current = false;
    setRunning(true);
    const rs: Row[] = parsed.items.map((it) => ({ key: `${it.line}:${it.label}`, line: it.line, label: it.label, body: it.body, status: "queued" }));
    setRows([...rs]);
    for (let i = 0; i < rs.length && !stop.current; i++) {
      rs[i] = { ...rs[i], status: "running" }; setRows([...rs]);
      try {
        rs[i] = { ...rs[i], status: "done", audit: await runAudit(rs[i].body) };
      } catch (e) {
        rs[i] = { ...rs[i], status: "error", error: errorText(e, t).msg };
      }
      setRows([...rs]);
    }
    setRunning(false);
  }

  function csv() {
    const head = ["line", "input", "type", "product", "status", "rank", "listing_quality", "facts", "fix_1", "fix_2", "fix_3", "price", "price_position", "error"];
    const lines = rows.map((r) => {
      const c = cells(r, t, lang);
      return [r.line, c.input, c.kind, c.product, c.status, c.rank, c.score, c.facts, c.fixes[0], c.fixes[1], c.fixes[2], c.price, c.position, c.error].map(csvCell).join(",");
    });
    const skipped = parsed.rejects.map((x) => [x.line, x.text, "", "", t("bulk.skipped"), "", "", "", "", "", "", "", "", t(`bulk.why.${x.reason}`)].map(csvCell).join(","));
    const blob = new Blob(["﻿" + [head.join(","), ...lines, ...skipped].join("\r\n")], { type: "text/csv;charset=utf-8" });
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
  const nUrl = parsed.items.filter((i) => i.body.url).length, nDraft = parsed.items.length - nUrl;

  return (
    <div className="mx-auto max-w-6xl">
      <div className="no-print">
        <h1 className="text-2xl font-bold tracking-tight">{t("bulk.title")}</h1>
        <p className="mt-1 max-w-2xl text-sm muted">{t("bulk.sub")}</p>
        <div className="card mt-5 p-4 sm:p-5">
          <label htmlFor="bulk" className="text-xs font-medium muted">{t("bulk.inputLabel")}</label>
          <textarea id="bulk" data-focus-key rows={7} className="input mt-1 font-mono text-sm" value={text} onChange={(e) => setText(e.target.value)} placeholder={t("bulk.placeholder")} disabled={running} aria-describedby="bulk-help" />
          <p id="bulk-help" className="mt-1 text-xs muted">{t("bulk.help")}</p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {running ? (
              <button className="btn-outline" onClick={() => { stop.current = true; }}><Square className="size-4" aria-hidden /> {t("bulk.stop")}</button>
            ) : (
              <button className="btn-primary" onClick={run} disabled={!parsed.items.length}><Play className="size-4" aria-hidden /> {t("bulk.run", { n: parsed.items.length })}</button>
            )}
            {rows.length > 0 && !running && <>
              <button className="btn-ghost" onClick={csv}><Download className="size-4" aria-hidden /> {t("bulk.csv")}</button>
              <button className="btn-ghost" onClick={() => window.print()}><Printer className="size-4" aria-hidden /> {t("bulk.print")}</button>
            </>}
            {running && <span className="text-sm muted" role="status">{doneN} / {rows.length}</span>}
            {text.trim() && !running && <span className="text-sm muted">{t("bulk.counts", { u: nUrl, d: nDraft, s: parsed.rejects.length })}</span>}
          </div>
          {parsed.rejects.length > 0 && (
            <div role="alert" className="mt-3 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
              <p className="font-semibold">{t("bulk.rejected", { n: parsed.rejects.length })}</p>
              <ul className="mt-1 space-y-0.5">
                {parsed.rejects.map((x) => <li key={`${x.line}-${x.reason}`}><b>{t("bulk.line", { n: x.line })}</b>: {t(`bulk.why.${x.reason}`)} <span className="font-mono text-xs opacity-80">{x.text.slice(0, 60)}</span></li>)}
              </ul>
            </div>
          )}
        </div>
      </div>

      {rows.length > 0 && (
        <section className="mt-6">
          <div className="hidden print:block">
            <h1 className="text-2xl font-bold">{t("bulk.reportTitle")}</h1>
            <p className="text-sm">{new Date().toLocaleDateString(lang)} · {t("bulk.reportNote")}</p>
          </div>
          <div className="card overflow-x-auto" role="region" aria-label={t("bulk.title")} tabIndex={0}>
            <table className="w-full min-w-[820px] text-sm">
              <thead className="border-b border-[var(--border)] text-left text-xs muted">
                <tr>
                  <th scope="col" className="px-3 py-2 font-medium">{t("bulk.col.line")}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t("bulk.col.product")}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t("bulk.col.status")}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t("rank.eyebrow")}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t("bulk.col.facts")}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t("bulk.col.fix")}</th>
                  <th scope="col" className="px-3 py-2 font-medium">{t("bulk.col.price")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {rows.map((r) => {
                  const c = cells(r, t, lang);
                  return (
                    <tr key={r.key} className="align-top">
                      <td className="px-3 py-2 tabular-nums muted">{r.line}</td>
                      <td className="max-w-[16rem] px-3 py-2">
                        <p className="truncate font-medium">{c.product}</p>
                        {r.body.url ? <a href={r.body.url} target="_blank" rel="noopener noreferrer" className="block truncate text-xs muted hover:underline">{r.body.url}</a>
                          : <span className="chip bg-amber-50 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300">{t("draft.badge")}</span>}
                      </td>
                      <td className="px-3 py-2"><Status r={r} />{c.error && <p className="mt-1 max-w-[14rem] text-xs text-rose-700 dark:text-rose-400">{c.error}</p>}</td>
                      <td className="px-3 py-2">{c.rank}{c.score !== "" && <span className="block text-xs muted">{c.score}/100</span>}</td>
                      <td className="px-3 py-2 tabular-nums">{c.facts}</td>
                      <td className="px-3 py-2">{c.fixes.length > 0 && <ol className="list-inside list-decimal space-y-0.5">{c.fixes.map((f, i) => <li key={i}>{f}</li>)}</ol>}</td>
                      <td className="px-3 py-2 whitespace-nowrap">{c.price}{c.position && <span className="block text-xs muted">{c.position}</span>}</td>
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
