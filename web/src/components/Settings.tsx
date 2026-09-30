import { useState } from "react";
import { Puzzle, Copy, KeyRound, LogOut, Moon, Share2, ShieldCheck, Sun, Trash2, UserPlus } from "lucide-react";
import { errorText, useI18n } from "../lib";
import { papi } from "../profile";
import { useSession } from "../session";
import { Empty, PageHeader, Tabs, useTheme, useToast } from "../ui";
import Onboarding from "./Onboarding";

type Tab = "profile" | "sharing" | "privacy" | "access" | "appearance";

export default function Settings() {
  const { t, lang, setLang } = useI18n();
  const { signedIn, profile, reload, signOut } = useSession();
  const toast = useToast();
  const [theme, toggleTheme] = useTheme();
  const [tab, setTab] = useState<Tab>(signedIn ? "profile" : "appearance");
  const [confirmDel, setConfirmDel] = useState("");

  async function share(on: boolean) {
    try {
      await papi("/v1/profile/share", { method: on ? "POST" : "DELETE" });
      await reload();
      toast("ok", on ? t("share.created") : t("share.revoked"));
    } catch (e) { toast("err", errorText(e, t).msg); }
  }
  async function del() {
    try {
      await papi("/v1/profile", { method: "DELETE" });
      toast("ok", t("privacy.deleted"));
      signOut();
    } catch (e) { toast("err", errorText(e, t).msg); }
  }
  const shareUrl = profile?.share_token ? `${location.origin}${location.pathname}#/share/${profile.share_token}` : "";
  const items: [Tab, string][] = signedIn
    ? [["profile", t("set.profile")], ["sharing", t("share.title")], ["privacy", t("privacy.title")], ["access", t("set.access")], ["appearance", t("set.appearance")]]
    : [["appearance", t("set.appearance")]];

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader title={t("nav.settings")} sub={profile?.company.name} />
      <div className="mb-5 overflow-x-auto"><Tabs label={t("nav.settings")} value={tab} onChange={setTab} items={items} /></div>

      {tab === "profile" && profile && <Onboarding key={profile.company.name} edit={profile} />}

      {tab === "sharing" && profile && (
        <section className="card p-5">
          <h2 className="flex items-center gap-2 font-semibold"><Share2 className="size-4" aria-hidden /> {t("share.title")}</h2>
          <p className="mt-1 text-sm muted">{t("share.sub")}</p>
          {profile.shared ? (
            <div className="mt-4 space-y-2">
              <div className="flex gap-2">
                <input readOnly aria-label={t("share.title")} className="input font-mono text-xs" value={shareUrl} onFocus={(e) => e.target.select()} />
                <button className="btn-outline" onClick={() => { navigator.clipboard?.writeText(shareUrl); toast("ok", t("ob.copied")); }}><Copy className="size-4" aria-hidden /> {t("ob.copy")}</button>
              </div>
              <div className="flex gap-2"><a className="btn-outline" href={shareUrl} target="_blank" rel="noopener noreferrer">{t("share.preview")}</a>
                <button className="btn-ghost text-rose-600" onClick={() => share(false)}>{t("share.revoke")}</button></div>
            </div>
          ) : <button className="btn-primary mt-4" onClick={() => share(true)}><Share2 className="size-4" aria-hidden /> {t("share.create")}</button>}
        </section>
      )}

      {tab === "privacy" && profile && (
        <section className="card p-5">
          <h2 className="flex items-center gap-2 font-semibold"><ShieldCheck className="size-4" aria-hidden /> {t("privacy.title")}</h2>
          <p className="mt-1 text-sm muted">{t("privacy.body")}</p>
          <p className="mt-2 text-sm muted">{t("privacy.short")}</p>
          <div className="mt-5 rounded-md border border-rose-200 p-4 dark:border-rose-900/60">
            <h3 className="font-semibold text-rose-700 dark:text-rose-400">{t("privacy.delete")}</h3>
            <p className="mt-1 text-sm muted">{t("privacy.typeName", { name: profile.company.name })}</p>
            <div className="mt-3 flex flex-col gap-2 sm:flex-row">
              <label htmlFor="del-name" className="sr-only">{t("ob.company")}</label>
              <input id="del-name" className="input" value={confirmDel} onChange={(e) => setConfirmDel(e.target.value)} />
              <button className="btn bg-rose-600 text-white hover:bg-rose-500" disabled={confirmDel.trim() !== profile.company.name} onClick={del}><Trash2 className="size-4" aria-hidden /> {t("privacy.confirm")}</button>
            </div>
          </div>
        </section>
      )}

      {tab === "access" && (
        <section className="card space-y-4 p-5">
          <div>
            <h2 className="flex items-center gap-2 font-semibold"><KeyRound className="size-4" aria-hidden /> {t("set.keyTitle")}</h2>
            <p className="mt-1 text-sm muted">{t("set.keyBody")}</p>
          </div>
          <div>
            <h3 className="flex items-center gap-2 text-sm font-semibold"><Puzzle className="size-4" aria-hidden /> {t("set.extTitle")}</h3>
            <p className="mt-1 text-sm muted">{t("set.extBody")}</p>
          </div>
          <button className="btn-outline" onClick={signOut}><LogOut className="size-4" aria-hidden /> {t("home.signout")}</button>
        </section>
      )}

      {tab === "appearance" && (
        <section className="card grid gap-5 p-5 sm:grid-cols-2">
          <div>
            <h2 className="text-sm font-semibold">{t("set.theme")}</h2>
            <button className="btn-outline mt-2" onClick={toggleTheme}>{theme === "dark" ? <Sun className="size-4" aria-hidden /> : <Moon className="size-4" aria-hidden />} {theme === "dark" ? t("set.light") : t("set.dark")}</button>
            <p className="mt-2 text-xs muted">{t("set.kbTheme")} <kbd className="kbd">t</kbd></p>
          </div>
          <div>
            <h2 className="text-sm font-semibold">{t("set.language")}</h2>
            <select className="input mt-2 w-auto" value={lang} onChange={(e) => setLang(e.target.value as "en" | "es")} aria-label={t("set.language")}>
              <option value="en">English</option><option value="es">Español</option>
            </select>
            <p className="mt-2 text-xs muted">{t("set.kbLang")} <kbd className="kbd">l</kbd></p>
          </div>
          {!signedIn && <div className="sm:col-span-2"><Empty icon={<UserPlus className="size-6" aria-hidden />} title={t("pr.signupTitle")} body={t("home.signupSub")}><a href="#/onboarding" className="btn-primary">{t("home.signup")}</a></Empty></div>}
        </section>
      )}
    </div>
  );
}
