import { useEffect, useRef, useState, type FormEvent } from "react";
import { CornerDownLeft, Info, MessageSquare, UserPlus } from "lucide-react";
import { fieldLabel, money, useI18n, type Lang, type T } from "../lib";
import { productName, type Product } from "../profile";
import { useSession } from "../session";
import { Empty, PageHeader } from "../ui";
import { actionText } from "./Results";

type Msg = { from: "you" | "pl"; text: string; lines?: string[]; link?: [string, string] };
const INTENTS: [string, RegExp][] = [
  ["fix", /fix|first|improve|todo|arregl|primero|mejorar|hacer/i],
  ["price", /price|cheap|expens|precio|caro|barat/i],
  ["missing", /missing|fact|attribute|not found|falta|dato|atribut/i],
  ["rank", /rank|best|worst|score|position|mejor|peor|puntua|posici/i],
  ["vis", /visib|ai\b|chatgpt|assistant|\bia\b|asistente/i],
  ["suggest", /suggest|text|copy|title|descri|sugier|texto|título/i],
];

/** Answers from the active company's stored audits only (deterministic rules, no model, nothing sent anywhere). */
function answer(q: string, ps: Product[], t: T, lang: Lang): Msg {
  const audited = ps.filter((p) => p.audit);
  const intent = INTENTS.find(([, re]) => re.test(q))?.[0];
  if (!audited.length && intent) return { from: "pl", text: t("chat.noAudits"), link: ["#/products", t("nav.products")] };
  const byScore = [...audited].sort((a, b) => a.audit!.rank.score - b.audit!.rank.score);
  switch (intent) {
    case "fix":
      return { from: "pl", text: t("chat.fix"), lines: byScore.slice(0, 5).filter((p) => p.audit!.actions.length).map((p) =>
        `${productName(p)}: ${actionText(p.audit!.actions[0], p.audit!, t, lang).title}`), link: ["#/reports", t("home.report")] };
    case "price": {
      const lines = audited.map((p) => {
        const pp = p.audit!.price_position;
        return `${productName(p)}: ${pp.available && pp.position ? t("chat.priceAt", { price: money(pp.price, pp.currency, lang), pos: t(`pos.${pp.position}`), n: pp.peer_count ?? 0 }) : t("rep.priceNa")}`;
      });
      return { from: "pl", text: t("chat.price"), lines };
    }
    case "missing": {
      const c: Record<string, number> = {};
      audited.forEach((p) => p.audit!.not_found.forEach((m) => { c[m.field] = (c[m.field] || 0) + 1; }));
      return { from: "pl", text: t("chat.missing", { n: audited.length }), lines: Object.entries(c).sort((a, b) => b[1] - a[1]).slice(0, 6).map(([f, n]) => `${fieldLabel(lang, f)}: ${n}/${audited.length}`) };
    }
    case "rank": {
      const best = byScore[byScore.length - 1], worst = byScore[0];
      return { from: "pl", text: t("chat.rank"), lines: [t("chat.best", { name: productName(best), s: best.audit!.rank.score }), t("chat.worst", { name: productName(worst), s: worst.audit!.rank.score })] };
    }
    case "vis":
      return { from: "pl", text: audited.some((p) => p.audit!.visibility.available) ? t("ws.visAvail") : t("vis.empty"), link: ["#/models", t("nav.models")] };
    case "suggest":
      return { from: "pl", text: t("chat.suggest"), link: ["#/reports", t("home.report")] };
    default:
      return { from: "pl", text: t("chat.help") };
  }
}

export default function Chat() {
  const { t, lang } = useI18n();
  const { signedIn, profile } = useSession();
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [q, setQ] = useState("");
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { end.current?.scrollIntoView({ block: "nearest" }); }, [msgs]);
  if (!signedIn) return (
    <div className="mx-auto max-w-3xl"><PageHeader title={t("nav.chat")} sub={t("chat.sub")} />
      <Empty icon={<UserPlus className="size-6" aria-hidden />} title={t("pr.signupTitle")} body={t("chat.needProfile")}><a href="#/onboarding" className="btn-primary">{t("home.signup")}</a></Empty></div>
  );
  const ask = (text: string) => {
    if (!text.trim() || !profile) return;
    setMsgs((m) => [...m, { from: "you", text }, answer(text, profile.products, t, lang)]);
    setQ("");
  };
  const chips = ["chat.q.fix", "chat.q.price", "chat.q.missing", "chat.q.rank", "chat.q.vis"];
  return (
    <div className="mx-auto flex max-w-3xl flex-col" style={{ minHeight: "calc(100vh - 8rem)" }}>
      <PageHeader title={t("nav.chat")} sub={t("chat.sub")} />
      <p className="mb-4 flex items-start gap-2 rounded-md border border-[var(--border)] bg-[var(--surface-2)] p-3 text-xs muted"><Info className="mt-px size-3.5 shrink-0" aria-hidden /> {t("chat.honest")}</p>
      <div className="card flex-1 space-y-3 overflow-y-auto p-4" role="log" aria-live="polite" aria-label={t("nav.chat")}>
        {!msgs.length && <div className="py-10 text-center"><MessageSquare className="mx-auto size-8 muted" aria-hidden /><p className="mt-2 text-sm muted">{t("chat.start")}</p></div>}
        {msgs.map((m, i) => (
          <div key={i} className={`flex ${m.from === "you" ? "justify-end" : ""}`}>
            <div className={`max-w-[85%] rounded-md px-3 py-2 text-sm ${m.from === "you" ? "bg-[var(--accent)] text-white" : "bg-[var(--surface-2)]"}`}>
              <p>{m.text}</p>
              {m.lines && m.lines.length > 0 && <ul className="mt-2 list-disc space-y-1 pl-4">{m.lines.map((l, j) => <li key={j}>{l}</li>)}</ul>}
              {m.link && <a href={m.link[0]} className="mt-2 inline-block font-semibold text-[var(--accent)] underline-offset-2 hover:underline">{m.link[1]} →</a>}
            </div>
          </div>
        ))}
        <div ref={end} />
      </div>
      <div className="mt-3 flex flex-wrap gap-2">{chips.map((c) => <button key={c} className="btn-outline px-2.5 py-1 text-xs" onClick={() => ask(t(c))}>{t(c)}</button>)}</div>
      <form onSubmit={(e: FormEvent) => { e.preventDefault(); ask(q); }} className="mt-3 flex gap-2">
        <label htmlFor="chat-q" className="sr-only">{t("chat.placeholder")}</label>
        <input id="chat-q" data-focus-key className="input" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("chat.placeholder")} />
        <button className="btn-primary" disabled={!q.trim()}><CornerDownLeft className="size-4" aria-hidden /><span className="sr-only">{t("chat.send")}</span></button>
      </form>
    </div>
  );
}
