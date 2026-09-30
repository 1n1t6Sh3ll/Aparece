import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { ApiError } from "./lib";
import { papi, token, type Product, type Profile } from "./profile";

type Session = {
  signedIn: boolean; profile: Profile | null; loading: boolean; error: string;
  reload: () => Promise<void>; switchTo: (tok: string) => void; signOut: () => void;
  updateProduct: (p: Product) => void;
};
const Ctx = createContext<Session>(null!);
export const useSession = () => useContext(Ctx);

/** The active company's profile, loaded once and shared by the shell and pages. */
export function SessionProvider({ children }: { children: ReactNode }) {
  const [tok, setTok] = useState(token.get());
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(!!tok);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    const cur = token.get();
    setTok(cur);
    if (!cur) { setProfile(null); setLoading(false); return; }
    setLoading(true); setError("");
    try {
      const p = await papi<Profile>("/v1/profile");
      token.name(cur, p.company.name);
      setProfile(p);
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) { token.clear(); setTok(token.get()); setProfile(null); if (token.get()) return reload(); }
      else setError(e instanceof Error ? e.message : String(e));
    }
    setLoading(false);
  }, []);
  useEffect(() => { reload(); }, [reload]);

  const value: Session = {
    signedIn: !!tok, profile, loading, error, reload,
    switchTo: (t) => { token.set(t); reload(); window.location.hash = "/"; },
    signOut: () => { token.clear(); reload(); window.location.hash = "/"; },
    updateProduct: (np) => setProfile((p) => p && { ...p, products: p.products.map((q) => (q.id === np.id ? { ...q, ...np } : q)) }),
  };
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
