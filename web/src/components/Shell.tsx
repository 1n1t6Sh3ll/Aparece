import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  Aperture, Building2, Check, ChevronsUpDown, Cpu, FileText, Globe, Keyboard, LayoutDashboard, LogIn, Menu, MessageSquare,
  Moon, Package, Plus, Scale, ScanSearch, Settings, Sun, UserPlus, X,
} from "lucide-react";
import { useI18n } from "../lib";
import { accounts, token } from "../profile";
import { useSession } from "../session";
import { useShortcuts, useTheme } from "../ui";

export const NAV = [
  { to: "", key: "o", label: "nav.overview", Icon: LayoutDashboard, auth: true },
  { to: "audit", key: "a", label: "nav.audit", Icon: ScanSearch },
  { to: "products", key: "p", label: "nav.products", Icon: Package },
  { to: "reports", key: "r", label: "nav.reports", Icon: FileText },
  { to: "compare", key: "i", label: "nav.compare", Icon: Scale },
  { to: "models", key: "m", label: "nav.models", Icon: Cpu },
  { to: "chat", key: "c", label: "nav.chat", Icon: MessageSquare },
  { to: "settings", key: "s", label: "nav.settings", Icon: Settings },
] as const;

function Switcher() {
  const { t } = useI18n();
  const { profile, signedIn, switchTo } = useSession();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  if (!signedIn) {
    return (
      <div className="flex gap-2">
        <a href="#/signin" className="btn-ghost px-2.5"><LogIn className="size-4" aria-hidden /> <span className="hidden sm:inline">{t("home.signin")}</span></a>
        <a href="#/onboarding" className="btn-primary px-2.5"><UserPlus className="size-4" aria-hidden /> <span className="hidden sm:inline">{t("home.signup")}</span></a>
      </div>
    );
  }
  const cur = token.get();
  return (
    <div className="relative" ref={ref}>
      <button className="btn-outline max-w-[10rem] px-2.5 sm:max-w-[14rem]" aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className="grid size-6 place-items-center rounded-md bg-[var(--accent-soft)] text-[var(--accent)]"><Building2 className="size-3.5" aria-hidden /></span>
        <span className="truncate">{profile?.company.name || "…"}</span>
        <ChevronsUpDown className="size-3.5 shrink-0 muted" aria-hidden />
      </button>
      {open && (
        <div role="menu" className="card absolute right-0 z-40 mt-2 w-64 p-1 shadow-lg">
          <p className="eyebrow px-2 py-1.5">{t("sw.companies")}</p>
          {accounts().map((a) => (
            <button key={a.token} role="menuitemradio" aria-checked={a.token === cur} onClick={() => { setOpen(false); switchTo(a.token); }}
              className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-[var(--surface-2)]">
              <Building2 className="size-4 muted" aria-hidden /><span className="flex-1 truncate">{a.name || t("sw.unnamed")}</span>
              {a.token === cur && <Check className="size-4 text-[var(--accent)]" aria-hidden />}
            </button>
          ))}
          <div className="my-1 border-t border-[var(--border)]" />
          <a role="menuitem" href="#/onboarding" onClick={() => setOpen(false)} className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-[var(--surface-2)]"><Plus className="size-4 muted" aria-hidden /> {t("sw.add")}</a>
          <a role="menuitem" href="#/signin" onClick={() => setOpen(false)} className="flex items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-[var(--surface-2)]"><LogIn className="size-4 muted" aria-hidden /> {t("sw.key")}</a>
        </div>
      )}
    </div>
  );
}

function ShortcutHelp({ onClose }: { onClose: () => void }) {
  const { t } = useI18n();
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { ref.current?.showModal(); }, []);
  const rows: [string, string][] = [
    ...NAV.map((n) => [`g ${n.key}`, t(n.label)] as [string, string]),
    ["/", t("kb.focus")], ["t", t("kb.theme")], ["l", t("kb.lang")], ["?", t("kb.help")],
  ];
  return (
    <dialog ref={ref} onClose={onClose} className="card m-auto w-[min(26rem,calc(100%-2rem))] p-0 text-[var(--text)] backdrop:bg-stone-950/50">
      <div className="flex items-center justify-between border-b border-[var(--border)] px-4 py-3">
        <h2 className="flex items-center gap-2 font-semibold"><Keyboard className="size-4" aria-hidden /> {t("kb.title")}</h2>
        <button className="btn-ghost p-1.5" onClick={() => ref.current?.close()} aria-label={t("kb.close")}><X className="size-4" aria-hidden /></button>
      </div>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 px-4 py-3 text-sm">
        {rows.map(([k, l]) => <div key={k} className="contents"><dt>{k.split(" ").map((x) => <kbd key={x} className="kbd mr-1">{x}</kbd>)}</dt><dd className="muted">{l}</dd></div>)}
      </dl>
    </dialog>
  );
}

export default function Shell({ page, children }: { page: string; children: ReactNode }) {
  const { t, lang, setLang } = useI18n();
  const { signedIn } = useSession();
  const [theme, toggleTheme] = useTheme();
  const [drawer, setDrawer] = useState(false);
  const [help, setHelp] = useState(false);
  useEffect(() => setDrawer(false), [page]);
  useEffect(() => {
    if (!drawer) return;
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setDrawer(false); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [drawer]);

  const go = useMemo(() => Object.fromEntries(NAV.map((n) => [n.key, n.to])), []);
  const keys = useMemo(() => ({
    "?": () => setHelp(true),
    t: toggleTheme,
    l: () => setLang(lang === "en" ? "es" : "en"),
    "/": () => (document.querySelector("[data-focus-key]") as HTMLElement | null)?.focus(),
  }), [toggleTheme, lang, setLang]);
  useShortcuts(go, keys);

  const active = (to: string) => page === to || (to === "audit" && (page === "bulk" || page === "report"));
  const nav = (
    <nav aria-label="Main" className="flex flex-1 flex-col gap-0.5 px-3">
      {NAV.filter((n) => !("auth" in n) || signedIn).map(({ to, key, label, Icon }) => (
        <a key={to} href={`#/${to}`} aria-current={active(to) ? "page" : undefined}
          className={`group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${active(to) ? "bg-white/10 text-white" : "text-[var(--sidebar-ink)] hover:bg-white/5 hover:text-white"}`}>
          <Icon className="size-4" aria-hidden /> <span className="flex-1">{t(label)}</span>
          <span aria-hidden className="hidden text-[10px] opacity-0 transition group-hover:opacity-60 lg:inline">g {key}</span>
        </a>
      ))}
    </nav>
  );
  const brand = (
    <a href="#/" className="flex items-center gap-2 px-6 py-5 font-bold tracking-tight text-white">
      <span className="grid size-8 place-items-center rounded-lg bg-[var(--accent)] shadow-sm"><Aperture className="size-5" aria-hidden /></span>
      ProductLens
    </a>
  );
  const foot = (
    <div className="space-y-2 px-6 py-5 text-xs text-[var(--sidebar-ink)]">
      <button className="flex items-center gap-2 hover:text-white" onClick={() => setHelp(true)}><Keyboard className="size-3.5" aria-hidden /> {t("kb.title")} <kbd className="kbd border-white/10 bg-white/5">?</kbd></button>
      <a className="block hover:text-white" href="/dashboard/">{t("nav.analyst")}</a>
    </div>
  );

  return (
    <div className="min-h-screen overflow-x-clip lg:pl-60">
      <aside className="no-print fixed inset-y-0 left-0 z-30 hidden w-60 flex-col bg-[var(--sidebar)] lg:flex">{brand}{nav}{foot}</aside>
      {drawer && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true" aria-label={t("nav.menu")}>
          <div className="absolute inset-0 bg-stone-950/50" onClick={() => setDrawer(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-64 flex-col bg-[var(--sidebar)] rise">
            <button className="absolute right-3 top-5 rounded-md p-1.5 text-[var(--sidebar-ink)] hover:bg-white/10" onClick={() => setDrawer(false)} aria-label={t("nav.closeMenu")} autoFocus><X className="size-5" aria-hidden /></button>
            {brand}{nav}{foot}</aside>
        </div>
      )}
      <header className="no-print sticky top-0 z-20 flex h-14 items-center gap-2 border-b border-[var(--border)] bg-[var(--surface)] px-4 sm:px-6">
        <button className="btn-ghost -ml-2 p-2 lg:hidden" onClick={() => setDrawer(true)} aria-label={t("nav.menu")} aria-expanded={drawer}><Menu className="size-5" aria-hidden /></button>
        <p className="mr-auto min-w-0 truncate text-sm font-semibold max-sm:sr-only">{t(NAV.find((n) => active(n.to))?.label || (page === "onboarding" ? "ob.title" : page === "signin" ? "home.signin" : "nf.title"))}</p>
        <span className="flex-1 sm:hidden" aria-hidden />
        <button className="btn-ghost p-2" onClick={() => setLang(lang === "en" ? "es" : "en")} aria-label={t("nav.lang")} title={t("nav.lang")}>
          <Globe className="size-4" aria-hidden /><span className="text-xs">{lang === "en" ? "ES" : "EN"}</span>
        </button>
        <button className="btn-ghost p-2" onClick={toggleTheme} aria-label={t("kb.theme")} title={t("kb.theme")}>
          {theme === "dark" ? <Sun className="size-4" aria-hidden /> : <Moon className="size-4" aria-hidden />}
        </button>
        <Switcher />
      </header>
      <main className="print-full px-4 py-6 sm:px-6 lg:px-8">{children}</main>
      {help && <ShortcutHelp onClose={() => setHelp(false)} />}
    </div>
  );
}
