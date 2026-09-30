import AuditPage from "./components/AuditPage";
import BulkPage from "./components/BulkPage";
import AiComparison from "./pages/AiComparison";
import Chat from "./components/Chat";
import { Landing, Overview, ProductsHub, SignIn } from "./components/Home";
import ModelsPage from "./components/ModelsPage";
import Onboarding from "./components/Onboarding";
import ProductDetail from "./components/ProductDetail";
import { Report, SharedReport } from "./components/Report";
import Settings from "./components/Settings";
import Shell from "./components/Shell";
import { Compass } from "lucide-react";
import { useHashRoute, useI18n } from "./lib";
import { Empty } from "./ui";
import { useSession } from "./session";

function NotFound() {
  const { t } = useI18n();
  return <Empty icon={<Compass className="size-6" aria-hidden />} title={t("nf.title")} body={t("nf.body")}><a className="btn-primary" href="#/">{t("nf.home")}</a><a className="btn-outline" href="#/audit">{t("nav.audit")}</a></Empty>;
}

export default function App() {
  const [route] = useHashRoute();
  const { signedIn } = useSession();
  const [path, query = ""] = route.split("?");
  const [page, rawArg] = path.split("/");
  const arg = rawArg ? decodeURIComponent(rawArg) : new URLSearchParams(query).get("product") || undefined;
  if (page === "share" && arg) return <SharedReport id={arg} />;
  if (!page && !signedIn) return <Landing />;
  const body = page === "audit" ? <AuditPage />
    : page === "report" && arg ? <AuditPage key={arg} reportId={arg} />
    : page === "bulk" ? <BulkPage />
    : page === "products" && arg ? <ProductDetail key={arg} id={arg} />
    : page === "compare" ? <AiComparison key={arg || ""} productId={arg} />
    : page === "products" ? <ProductsHub />
    : page === "reports" ? <Report />
    : page === "models" ? <ModelsPage />
    : page === "chat" ? <Chat />
    : page === "settings" ? <Settings />
    : page === "onboarding" ? <Onboarding />
    : page === "signin" ? <SignIn />
    : !page ? <Overview />
    : <NotFound />;
  return <Shell page={page || ""}>{body}</Shell>;
}
