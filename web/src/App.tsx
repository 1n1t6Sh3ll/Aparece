import { Aperture, BarChart3, Cpu, Globe, Layers, ScanSearch } from "lucide-react";
import AuditPage from "./components/AuditPage";
import BulkPage from "./components/BulkPage";
import AiComparison from "./pages/AiComparison";
import ModelsPage from "./components/ModelsPage";
import { HistoryPage, ProductsPage } from "./components/Monitor";
import { useHashRoute, useI18n } from "./lib";

export default function App() {
  const { t, lang, setLang } = useI18n();
  const [route] = useHashRoute();
  const [page, arg] = route.split("/");
  const link = (to: string, label: string, Icon: typeof Layers) => {
    const active = page === to || (to === "" && !["bulk", "products", "models"].includes(page));
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
          {link("", t("nav.audit"), ScanSearch)}
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
        {page === "compare" ? <AiComparison productId={arg ? decodeURIComponent(arg) : undefined} /> : page === "models" ? <ModelsPage /> : page === "bulk" ? <BulkPage /> : page === "products" && arg ? <HistoryPage id={arg} />
          : page === "products" ? <ProductsPage /> : <AuditPage />}
      </main>
      <footer className="no-print border-t border-slate-200/70 py-8 text-center text-sm muted dark:border-slate-800/70">
        <p className="mx-auto max-w-6xl px-4">{t("footer")} <a className="underline decoration-dotted underline-offset-2 hover:text-indigo-600" href="/dashboard/">{t("nav.analyst")}</a></p>
      </footer>
    </div>
  );
}
