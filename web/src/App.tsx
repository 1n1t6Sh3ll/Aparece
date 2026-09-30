import { Aperture, BarChart3, Cpu, Globe, Home, Layers, ScanSearch } from "lucide-react";
import AuditPage from "./components/AuditPage";
import BulkPage from "./components/BulkPage";
import ModelsPage from "./components/ModelsPage";
import { HistoryPage, ProductsPage } from "./components/Monitor";
import { Dashboard, Landing } from "./components/Home";
import Onboarding from "./components/Onboarding";
import { Report, SharedReport } from "./components/Report";
import { useEffect, useState } from "react";
import { useHashRoute, useI18n } from "./lib";
import { papi, token, type Profile } from "./profile";

function EditProfile() {
  const [p, setP] = useState<Profile | null>(null);
  useEffect(() => { papi<Profile>("/v1/profile").then(setP).catch(() => { window.location.hash = "/"; }); }, []);
  return p ? <Onboarding edit={p} /> : null;
}

export default function App() {
  const { t, lang, setLang } = useI18n();
  const [route] = useHashRoute();
  const [page, arg] = route.split("/");
  const [, bump] = useState(0);
  const signedIn = !!token.get();  // re-read on every route change / sign-out
  const link = (to: string, label: string, Icon: typeof Layers) => {
    const active = page === to || (to === "" && !["bulk", "products", "models", "audit"].includes(page));
    return (
      <a href={`#/${to}`} aria-current={active ? "page" : undefined}
        className={`btn-ghost px-2 py-2 sm:px-3 ${active ? "bg-slate-100 text-slate-900 dark:bg-slate-800 dark:text-white" : ""}`}>
        <Icon className="size-4" aria-hidden /> <span className="hidden sm:inline">{label}</span>
      </a>
    );
  };
  return (
    <div className="flex min-h-screen flex-col">
      <header className="no-print sticky top-0 z-20 border-b border-slate-200/70 bg-white/80 backdrop-blur-lg dark:border-slate-800/70 dark:bg-slate-950/80">
        <nav className="mx-auto flex h-16 max-w-6xl items-center gap-0.5 px-4 sm:gap-1" aria-label="Main">
          <a href="#/" className="mr-auto flex items-center gap-2 font-bold tracking-tight">
            <span className="grid size-8 place-items-center rounded-lg bg-gradient-to-br from-indigo-500 to-violet-600 text-white shadow-sm">
              <Aperture className="size-5" aria-hidden />
            </span>
            ProductLens
          </a>
          {signedIn && link("", t("nav.home"), Home)}
          {link(signedIn ? "audit" : "", t("nav.audit"), ScanSearch)}
          {link("bulk", t("nav.bulk"), Layers)}
          {link("products", t("nav.products"), BarChart3)}
          {link("models", t("nav.models"), Cpu)}
          <button className="btn-ghost px-2 py-2 sm:px-3" onClick={() => setLang(lang === "en" ? "es" : "en")}
            aria-label={t("nav.lang")} title={t("nav.lang")}>
            <Globe className="size-4" aria-hidden /> <span>{lang === "en" ? "ES" : "EN"}</span>
          </button>
        </nav>
      </header>
      <main className="flex-1">
        {page === "share" && arg ? <SharedReport id={arg} /> : page === "onboarding" ? <Onboarding />
          : page === "profile" && signedIn ? <EditProfile /> : page === "report" && signedIn ? <Report />
          : page === "audit" ? <AuditPage /> : !page && signedIn ? <Dashboard onGone={() => bump((x) => x + 1)} />
          : !page ? <Landing />
          : page === "models" ? <ModelsPage /> : page === "bulk" ? <BulkPage /> : page === "products" && arg ? <HistoryPage id={Number(arg)} />
          : page === "products" ? <ProductsPage /> : <AuditPage />}
      </main>
      <footer className="no-print border-t border-slate-200/70 py-8 text-center text-sm muted dark:border-slate-800/70">
        <p className="mx-auto max-w-6xl px-4">{t("footer")} <a className="underline decoration-dotted underline-offset-2 hover:text-indigo-600" href="/dashboard/">{t("nav.analyst")}</a></p>
      </footer>
    </div>
  );
}
