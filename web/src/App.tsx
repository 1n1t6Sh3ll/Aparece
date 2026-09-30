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
import { useHashRoute } from "./lib";
import { useSession } from "./session";

export default function App() {
  const [route] = useHashRoute();
  const { signedIn } = useSession();
  const [page, arg] = route.split("?")[0].split("/");
  if (page === "share" && arg) return <SharedReport id={arg} />;
  if (!page && !signedIn) return <Landing />;
  const body = page === "audit" ? <AuditPage />
    : page === "bulk" ? <BulkPage />
    : page === "products" && arg ? <ProductDetail id={decodeURIComponent(arg)} />
    : page === "compare" ? <AiComparison productId={arg ? decodeURIComponent(arg) : undefined} />
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
