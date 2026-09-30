import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, CheckCircle2, Info, X } from "lucide-react";
import { store, useI18n } from "./lib";

/* ---------- theme ---------- */
export type Theme = "light" | "dark";
export function initialTheme(): Theme {
  const s = store.get("pl.theme");
  if (s === "light" || s === "dark") return s;
  return "dark";  // dark by default; a visitor's saved choice (pl.theme) wins
}
export function applyTheme(t: Theme) {
  document.documentElement.dataset.theme = t;
}
export function useTheme(): [Theme, () => void] {
  const [t, setT] = useState<Theme>(() => (document.documentElement.dataset.theme as Theme) || initialTheme());
  useEffect(() => { applyTheme(t); }, [t]);
  return [t, () => { const n = t === "dark" ? "light" : "dark"; store.set("pl.theme", n); setT(n); }];
}

/* ---------- toasts ---------- */
type Toast = { id: number; kind: "ok" | "err" | "info"; text: string; action?: { label: string; href: string } };
const ToastCtx = createContext<(kind: Toast["kind"], text: string, action?: Toast["action"]) => void>(() => undefined);
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const { t } = useI18n();
  const [items, setItems] = useState<Toast[]>([]);
  const n = useRef(0);
  const push = useCallback((kind: Toast["kind"], text: string, action?: Toast["action"]) => {
    const id = ++n.current;
    setItems((x) => [...x.slice(-3), { id, kind, text, action }]);
    setTimeout(() => setItems((x) => x.filter((i) => i.id !== id)), kind === "err" ? 7000 : 4500);
  }, []);
  const Icon = { ok: CheckCircle2, err: AlertTriangle, info: Info };
  const tone = { ok: "text-emerald-500", err: "text-rose-500", info: "text-brand-500" };
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="no-print pointer-events-none fixed inset-x-0 bottom-4 z-50 flex flex-col items-center gap-2 px-4 sm:items-end" aria-live="polite" role="status">
        {items.map((i) => {
          const I = Icon[i.kind];
          return (
            <div key={i.id} className="card rise pointer-events-auto flex w-full max-w-sm items-start gap-3 p-3 text-sm shadow-lg">
              <I className={`mt-0.5 size-4 shrink-0 ${tone[i.kind]}`} aria-hidden />
              <p className="flex-1">{i.text} {i.action && <a className="font-semibold text-[var(--accent)] underline-offset-2 hover:underline" href={i.action.href}>{i.action.label}</a>}</p>
              <button className="muted hover:text-[var(--text)]" onClick={() => setItems((x) => x.filter((y) => y.id !== i.id))} aria-label={t("kb.close")}><X className="size-4" aria-hidden /></button>
            </div>
          );
        })}
      </div>
    </ToastCtx.Provider>
  );
}

/* ---------- keyboard shortcuts ---------- */
const typing = (e: KeyboardEvent) => {
  const el = e.target as HTMLElement | null;
  return !!el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName));
};
/** "g" then a letter navigates; single keys run actions. Ignored while typing or with modifiers. */
export function useShortcuts(go: Record<string, string>, keys: Record<string, () => void>) {
  const pending = useRef(0);
  useEffect(() => {
    const on = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || typing(e)) return;
      if (pending.current && Date.now() - pending.current < 1200 && go[e.key]) {
        pending.current = 0; e.preventDefault(); window.location.hash = "/" + go[e.key]; return;
      }
      pending.current = 0;
      if (e.key === "g") { pending.current = Date.now(); return; }
      if (keys[e.key]) { e.preventDefault(); keys[e.key](); }
    };
    window.addEventListener("keydown", on);
    return () => window.removeEventListener("keydown", on);
  }, [go, keys]);
}

/* ---------- small shared pieces ---------- */
export function Empty({ icon, title, body, children }: { icon: ReactNode; title: string; body?: string; children?: ReactNode }) {
  return (
    <div className="card flex flex-col items-center px-6 py-12 text-center">
      <span className="grid size-12 place-items-center rounded-xl bg-[var(--accent-soft)] text-[var(--accent)]">{icon}</span>
      <h2 className="mt-4 font-semibold">{title}</h2>
      {body && <p className="mt-1 max-w-md text-sm muted">{body}</p>}
      {children && <div className="mt-5 flex flex-wrap justify-center gap-2">{children}</div>}
    </div>
  );
}

export function ErrorBox({ title, msg, children }: { title: string; msg: string; children?: ReactNode }) {
  return (
    <div role="alert" className="flex gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-rose-900 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-200">
      <AlertTriangle className="mt-0.5 size-5 shrink-0" aria-hidden />
      <div className="min-w-0">
        <p className="font-semibold">{title}</p>
        <p className="mt-1 text-sm">{msg}</p>
        {children && <div className="mt-3 flex flex-wrap gap-2">{children}</div>}
      </div>
    </div>
  );
}

export function PageHeader({ title, sub, children }: { title: string; sub?: string; children?: ReactNode }) {
  return (
    <header className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end">
      <div className="min-w-0 flex-1">
        <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
        {sub && <p className="mt-1 text-sm muted">{sub}</p>}
      </div>
      {children && <div className="no-print flex flex-wrap gap-2">{children}</div>}
    </header>
  );
}

export function Stat({ label, value, sub, icon }: { label: string; value: ReactNode; sub?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="card p-4">
      <p className="flex items-center gap-1.5 text-xs font-medium muted">{icon}{label}</p>
      <p className={`mt-1 text-2xl font-bold tracking-tight ${typeof value === "number" ? "tabular-nums" : ""}`}>{value}</p>
      {sub && <p className="mt-0.5 text-xs muted">{sub}</p>}
    </div>
  );
}

export function Tabs<K extends string>({ value, onChange, items, label }: { value: K; onChange: (k: K) => void; items: [K, string][]; label: string }) {
  return (
    <div role="tablist" aria-label={label} className="inline-flex gap-1 rounded-lg bg-[var(--surface-2)] p-1">
      {items.map(([k, l]) => (
        <button key={k} role="tab" aria-selected={value === k} onClick={() => onChange(k)}
          className={`rounded-md px-3 py-1.5 text-sm font-medium transition ${value === k ? "bg-[var(--surface)] shadow-sm" : "muted hover:text-[var(--text)]"}`}>{l}</button>
      ))}
    </div>
  );
}
