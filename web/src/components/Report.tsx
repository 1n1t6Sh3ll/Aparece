import { useEffect, useState } from "react";
import { Radar, Check, Download, FileText, Loader2, PenLine, Printer, Share2, X } from "lucide-react";
import { api, errorText, fieldLabel, money, useI18n, type Lang, type T } from "../lib";
import { papi, productName, type Decision, type Product, type Profile, type Shared } from "../profile";
import { useSession } from "../session";
import { Empty } from "../ui";
import { csvCell } from "./BulkPage";
import { factCount } from "../facts";
import FixPanel, { type FixDecision } from "./FixPanel";
import { actionText } from "./Results";

/** Owner-only: /v1/optimize suggestions with accept/dismiss recorded on the profile product (never published). */
function Suggestions({ p, onDecided }: { p: Product; onDecided: (p: Product) => void }) {
  if (!p.record) return null;
  return <FixPanel compact record={p.record} decisions={(p.suggestions || {}) as Record<string, FixDecision>}
    onDecide={async (field, d) => onDecided(await papi<Product>(`/v1/profile/products/${p.id}/suggestion`, { method: "PUT", body: JSON.stringify({ field, ...d }) }))} />;
}

function ProductCard({ p, owner, onChange }: { p: Product; owner: boolean; onChange?: (p: Product) => void }) {
  const { t, lang } = useI18n();
  const a = p.audit;
  return (
    <article className="card break-inside-avoid p-5">
      <header className="flex flex-col gap-2 sm:flex-row sm:items-start">
        <div className="min-w-0 flex-1">
          <h3 className="break-words font-semibold">{productName(p)}</h3>
          {p.url && <p className="truncate text-xs muted">{p.url}</p>}
        </div>
        <div className="flex shrink-0 flex-wrap gap-1.5">
        {p.merchant_stated && <span className="chip bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300">{t("label.merchantStated")}</span>}
        {a && <span className="chip bg-brand-50 text-brand-700 dark:bg-brand-950 dark:text-brand-300">{a.rank.total > 1 ? t("rep.rank", { pos: a.rank.position, total: a.rank.total }) : t("rep.noPeers")} · {a.rank.score}/100</span>}
        </div>
      </header>
      {!a ? <p className="mt-3 text-sm muted">{t("rep.notAudited")}</p> : (
        <div className="mt-4 grid grid-cols-1 gap-4 text-sm sm:grid-cols-2">
          <div>
            <p className="font-medium">{t("rep.fixes")}</p>
            <ol className="mt-1 list-decimal space-y-1 pl-5">{a.actions.slice(0, 3).map((x) => <li key={x.id}>{actionText(x, a, t, lang).title}</li>)}</ol>
            {!a.actions.length && <p className="muted">{t("rep.noFixes")}</p>}
          </div>
          <div>
            <p className="font-medium">{t("rep.found", { n: factCount(a).n, of: factCount(a).of })}</p>
            <p className="mt-1 muted">{t("rep.notFound")}: {a.not_found.slice(0, 6).map((x) => fieldLabel(lang, x.field)).join(", ") || "-"}</p>
          </div>
          <div>
            <p className="font-medium">{t("rep.competitors")}</p>
            <ul className="mt-1 space-y-0.5">{a.peers.slice(0, 3).map((x) => <li key={x.product_id} className="truncate">{x.title} <span className="muted">({x.merchant})</span></li>)}</ul>
            {!a.peers.length && <p className="mt-1 muted">{t("rep.noPeersLong")}</p>}
          </div>
          <div>
            <p className="font-medium">{t("rep.price")}</p>
            <p className="mt-1">{a.price_position.available && a.price_position.position
              ? t("rep.priceAt", { price: money(a.price_position.price, a.price_position.currency, lang), pos: t(`pos.${a.price_position.position}`), n: a.price_position.peer_count ?? 0 })
              : <span className="muted">{t("rep.priceNa")}</span>}</p>
            <p className="mt-2 flex items-center gap-1 muted"><Radar className="size-4" aria-hidden />{a.visibility.available ? t("rep.visYes") : t("rep.visNo")}</p>
          </div>
        </div>
      )}
      {owner && a && onChange && <Suggestions p={p} onDecided={onChange} />}
    </article>
  );
}

function summary(products: Product[]) {
  const audited = products.filter((p) => p.audit);
  const missing: Record<string, number> = {};
  const pos: Record<string, number> = {};
  for (const p of audited) {
    for (const f of p.audit!.summary.top_missing) missing[f] = (missing[f] || 0) + 1;
    const x = p.audit!.price_position.position;
    if (x) pos[x] = (pos[x] || 0) + 1;
  }
  const avg = audited.length ? Math.round(audited.reduce((s, p) => s + p.audit!.rank.score, 0) / audited.length) : null;
  return { audited: audited.length, avg, missing: Object.entries(missing).sort((a, b) => b[1] - a[1]).slice(0, 3), pos };
}

function csv(name: string, products: Product[], t: T, lang: Lang) {
  const head = ["product", "source", "merchant_stated", "url", "rank", "of", "listing_quality", "facts_found", "facts_checked", "fix_1", "fix_2", "fix_3", "price", "currency", "price_position", "ai_visibility"];
  const rows = products.map((p) => {
    const a = p.audit;
    const f = a ? a.actions.slice(0, 3).map((x) => actionText(x, a, t, lang).title) : [];
    return [productName(p), p.source, p.merchant_stated, p.url, a?.rank.position, a?.rank.total, a?.rank.score, a && factCount(a).n,
      a && factCount(a).of, f[0], f[1], f[2], a?.product.price, a?.product.currency, a?.price_position.position,
      a ? a.visibility.available : ""].map(csvCell).join(",");
  });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(new Blob(["﻿" + [head.join(","), ...rows].join("\r\n")], { type: "text/csv;charset=utf-8" }));
  link.download = `${name.replace(/[^\w-]+/g, "-").toLowerCase()}-report-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}

function ReportView({ name, website, products, owner, profile, onChange }: {
  name: string; website?: string; products: Product[]; owner: boolean; profile?: Profile; onChange?: (p: Product) => void;
}) {
  const { t, lang } = useI18n();
  const s = summary(products);
  return (
    <div className={`mx-auto max-w-5xl space-y-6 ${owner ? "" : "px-4 py-10"}`}>
      <div className="no-print flex flex-wrap gap-2">
        {owner && <a href="#/settings" className="btn-ghost mr-auto"><Share2 className="size-4" aria-hidden /> {t("share.title")}</a>}
        <button className={`btn-ghost ${owner ? "" : "ml-auto"}`} onClick={() => csv(name, products, t, lang)}><Download className="size-4" aria-hidden /> CSV</button>
        <button className="btn-primary" onClick={() => window.print()}><Printer className="size-4" aria-hidden /> {t("rep.print")}</button>
      </div>
      <header>
        <p className="muted">{t("rep.eyebrow")}</p>
        <h1 className="text-3xl font-extrabold tracking-tight">{name}</h1>
        {website && <p className="muted">{website}</p>}
      </header>
      <section className="card p-5" aria-labelledby="h-sum">
        <h2 id="h-sum" className="font-semibold">{t("rep.company")}</h2>
        <dl className="mt-3 grid gap-4 text-sm sm:grid-cols-3">
          <div><dt className="muted">{t("rep.audited")}</dt><dd className="text-2xl font-bold">{s.audited} / {products.length}</dd></div>
          <div><dt className="muted">{t("rep.avg")}</dt><dd className="text-2xl font-bold">{s.avg ?? "-"}{s.avg != null && <span className="text-sm muted">/100</span>}</dd></div>
          <div><dt className="muted">{t("rep.common")}</dt><dd>{s.missing.map(([f, n]) => `${fieldLabel(lang, f)} (${n})`).join(", ") || "-"}</dd></div>
        </dl>
        {Object.keys(s.pos).length > 0 && <p className="mt-3 text-sm muted">{t("rep.prices")}: {Object.entries(s.pos).map(([k, n]) => `${t(`pos.${k}`)} ${n}`).join(" · ")}</p>}
        {owner && profile && (profile.company.claims.length > 0 || profile.company.competitors.length > 0) && (
          <div className="mt-4 grid gap-4 border-t border-stone-100 pt-4 text-sm sm:grid-cols-2 dark:border-stone-800">
            {profile.company.claims.length > 0 && <div><p className="font-medium">{t("ob.claims")} <span className="chip bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300">{t("label.merchantStated")}</span></p>
              <ul className="mt-1 list-disc pl-5">{profile.company.claims.map((c) => <li key={c.text}>{c.text}</li>)}</ul></div>}
            {profile.company.competitors.length > 0 && <div><p className="font-medium">{t("ob.competitors")} <span className="chip bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300">{t("label.merchantStated")}</span></p>
              <ul className="mt-1 space-y-0.5">{profile.company.competitors.map((c) => <li key={c} className="truncate">{c}</li>)}</ul></div>}
          </div>
        )}
        <p className="mt-4 text-xs muted">{t("rep.method")}</p>
      </section>
      <div className="space-y-4">{products.map((p) => <ProductCard key={p.id} p={p} owner={owner} onChange={onChange} />)}</div>
    </div>
  );
}

export function Report() {
  const { t } = useI18n();
  const { signedIn, profile, loading, updateProduct } = useSession();
  if (!signedIn) return (
    <Empty icon={<FileText className="size-6" aria-hidden />} title={t("rep.signupTitle")} body={t("home.signupSub")}>
      <a href="#/onboarding" className="btn-primary">{t("home.signup")}</a><a href="#/bulk" className="btn-outline">{t("ws.bulk")}</a>
    </Empty>
  );
  if (!profile) return <div className="grid place-items-center py-24" role="status">{loading ? <Loader2 className="size-6 animate-spin" aria-hidden /> : null}</div>;
  return <ReportView name={profile.company.name} website={profile.company.website} products={profile.products} owner profile={profile}
    onChange={updateProduct} />;
}

export function SharedReport({ id }: { id: string }) {
  const { t } = useI18n();
  const [data, setData] = useState<Shared | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    const m = document.createElement("meta");
    m.name = "robots"; m.content = "noindex, nofollow";
    document.head.appendChild(m);
    api<Shared>(`/v1/share/${encodeURIComponent(id)}`).then(setData).catch(() => setErr(t("share.gone")));
    return () => m.remove();
  }, [id]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!data) return <div className="grid place-items-center py-24" role="status">{err || <Loader2 className="size-6 animate-spin" aria-hidden />}</div>;
  return <ReportView name={data.company.name} website={data.company.website} products={data.products} owner={false} />;
}
