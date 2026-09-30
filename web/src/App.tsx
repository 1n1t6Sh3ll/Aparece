import AuditPage from "./components/AuditPage";
import BulkPage from "./components/BulkPage";
import Chat from "./components/Chat";
import { Landing, Overview, ProductsHub, SignIn } from "./components/Home";
import ModelsPage from "./components/ModelsPage";
import { HistoryPage } from "./components/Monitor";
import Onboarding from "./components/Onboarding";
import ProductDetail from "./components/ProductDetail";
import { Report, SharedReport } from "./components/Report";
import Settings from "./components/Settings";
import Shell from "./components/Shell";
import { useHashRoute } from "./lib";
import { useSession } from "./session";

export default function App() {
  const [route] = useHashRoute();
  const { signedIn } = useSession();
  const [page, arg, arg2] = route.split("?")[0].split("/");
  if (page === "share" && arg) return <SharedReport id={arg} />;
  if (!page && !signedIn) return <Landing />;
  const body = page === "audit" ? <AuditPage />
    : page === "bulk" ? <BulkPage />
    : page === "products" && arg === "p" && arg2 ? <ProductDetail id={Number(arg2)} />
    : page === "products" && arg ? <HistoryPage id={Number(arg)} />
    : page === "products" ? <ProductsHub />
    : page === "reports" ? <Report />
    : page === "models" ? <ModelsPage />
    : page === "chat" ? <Chat />
    : page === "settings" ? <Settings />
    : page === "onboarding" ? <Onboarding />
    : page === "signin" ? <SignIn />
    : <Overview />;
  return <Shell page={page || ""}>{body}</Shell>;
}
