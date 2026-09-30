import { AnimatePresence, motion } from "framer-motion";
import { Bell, Coins, Inbox, KeyRound, LogOut, Map as MapIcon, OctagonX, Pause, Play, ScrollText, Sparkles, Wifi, WifiOff, Zap, ZapOff } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Button, Card, Gauge, Input, Modal, cx } from "./components/ui";
import { api, clearToken, eur, getToken, setToken } from "./lib/api";
import { StoreProvider, useStore } from "./lib/store";
import { AlertsPage } from "./pages/AlertsPage";
import { BudgetPage } from "./pages/BudgetPage";
import { LogsPage } from "./pages/LogsPage";
import { MapPage } from "./pages/MapPage";
import { RequestsPage } from "./pages/RequestsPage";
import { SkillsPage } from "./pages/SkillsPage";

type Page = "carte" | "logs" | "budget" | "demandes" | "skills" | "alertes";

export default function App() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  useEffect(() => {
    if (!getToken()) return setAuthed(false);
    api("/api/overview").then(() => setAuthed(true)).catch(() => setAuthed(false));
  }, []);
  if (authed === null) return null;
  if (!authed) return <Login onOk={() => setAuthed(true)} />;
  return (
    <StoreProvider>
      <Shell />
    </StoreProvider>
  );
}

function Login({ onOk }: { onOk: () => void }) {
  const [t, setT] = useState("");
  const [err, setErr] = useState("");
  return (
    <div className="min-h-full flex items-center justify-center p-6 bg-[radial-gradient(ellipse_at_top,rgba(99,102,241,0.12),transparent_60%)]">
      <Card className="w-full max-w-sm p-6">
        <div className="flex items-center gap-2 mb-6"><Logo /><span className="font-semibold">Orchestra</span></div>
        <h1 className="text-lg font-semibold">Accès local</h1>
        <p className="text-sm text-ink-muted mt-1 mb-5">Collez le jeton <code className="text-xs">ORCHESTRA_TOKEN</code> du fichier <code className="text-xs">.env</code> (ou ouvrez le lien affiché par <code className="text-xs">start.ps1</code>).</p>
        <form className="space-y-3" onSubmit={async (e) => {
          e.preventDefault();
          setToken(t);
          try { await api("/api/overview"); onOk(); } catch { clearToken(); setErr("Jeton invalide"); }
        }}>
          <Input type="password" autoFocus value={t} onChange={(e) => setT(e.target.value)} placeholder="Jeton local" aria-label="Jeton local" />
          {err && <div className="text-xs text-red-400">{err}</div>}
          <Button variant="primary" className="w-full" type="submit"><KeyRound size={14} />Se connecter</Button>
        </form>
      </Card>
    </div>
  );
}

const Logo = () => (
  <span className="relative inline-flex w-6 h-6 rounded-full bg-accent-strong items-center justify-center">
    <span className="w-2 h-2 rounded-full bg-white" />
  </span>
);

function Shell() {
  const { overview, connected, reducedMotion, setReducedMotion, toasts } = useStore();
  const [page, setPage] = useState<Page>(() => (location.hash.replace("#", "") as Page) || "carte");
  useEffect(() => void history.replaceState(null, "", `#${page}`), [page]);
  const nav: { id: Page; label: string; icon: ReactNode; badge?: number }[] = [
    { id: "carte", label: "Carte", icon: <MapIcon size={16} /> },
    { id: "demandes", label: "Demandes", icon: <Inbox size={16} />, badge: overview?.demandes_en_attente },
    { id: "skills", label: "Skills", icon: <Sparkles size={16} /> },
    { id: "budget", label: "Budget", icon: <Coins size={16} /> },
    { id: "logs", label: "Logs", icon: <ScrollText size={16} /> },
    { id: "alertes", label: "Alertes", icon: <Bell size={16} />, badge: overview?.alertes_non_lues },
  ];
  const b = overview?.budget;
  return (
    <div className="h-full flex">
      <aside className="w-56 shrink-0 border-r border-line bg-bg-subtle flex flex-col">
        <div className="flex items-center gap-2 px-5 h-14 border-b border-line"><Logo /><span className="font-semibold tracking-tight">Orchestra</span></div>
        <nav className="p-3 space-y-0.5 flex-1">
          {nav.map((n) => (
            <button key={n.id} onClick={() => setPage(n.id)} data-testid={`nav-${n.id}`}
              className={cx("w-full flex items-center gap-2.5 px-3 py-2 text-sm font-medium rounded-lg transition-colors duration-150",
                page === n.id ? "bg-accent-subtle text-indigo-200" : "text-ink-muted hover:text-ink hover:bg-bg-muted")}>
              {n.icon}<span className="flex-1 text-left">{n.label}</span>
              {!!n.badge && <span className="min-w-[20px] px-1.5 py-0.5 text-[10px] font-semibold rounded-full bg-amber-400/15 text-amber-300 tabular-nums">{n.badge}</span>}
            </button>
          ))}
        </nav>
        <div className="p-4 border-t border-line space-y-3">
          {b && (
            <button className="w-full text-left" onClick={() => setPage("budget")}>
              <div className="flex justify-between text-xs"><span className="text-ink-muted">Budget du mois</span><span className="tabular-nums">{eur(b.depense_eur)} / {eur(b.plafond_eur, 0)}</span></div>
              <Gauge ratio={b.ratio} alert={b.alerte_ratio} className="mt-2" />
            </button>
          )}
          <button onClick={() => setReducedMotion(!reducedMotion)} className="flex items-center gap-2 text-xs text-ink-subtle hover:text-ink">
            {reducedMotion ? <ZapOff size={13} /> : <Zap size={13} />}{reducedMotion ? "Animations réduites" : "Réduire les animations"}
          </button>
          <div className="flex items-center justify-between text-xs text-ink-subtle">
            <span className="flex items-center gap-1.5">{connected ? <Wifi size={13} className="text-emerald-400" /> : <WifiOff size={13} className="text-red-400" />}{connected ? "Temps réel" : "Reconnexion…"}</span>
            <button onClick={() => { clearToken(); location.reload(); }} className="hover:text-ink" title="Se déconnecter"><LogOut size={13} /></button>
          </div>
        </div>
      </aside>
      <main className="flex-1 min-w-0 flex flex-col">
        <TopBar />
        <div className="flex-1 min-h-0 overflow-y-auto">
          <AnimatePresence mode="wait">
            <motion.div key={page} className="h-full" initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.18 }}>
              {page === "carte" && <MapPage />}
              {page === "logs" && <LogsPage />}
              {page === "budget" && <BudgetPage />}
              {page === "demandes" && <RequestsPage />}
              {page === "skills" && <SkillsPage />}
              {page === "alertes" && <AlertsPage />}
            </motion.div>
          </AnimatePresence>
        </div>
      </main>
      <div className="fixed bottom-4 left-1/2 -translate-x-1/2 z-[60] space-y-2 w-[min(520px,90vw)]">
        <AnimatePresence>
          {toasts.map((t) => (
            <motion.div key={t.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}
              className={cx("px-4 py-2.5 rounded-lg border text-sm shadow-xl backdrop-blur", t.kind === "err" ? "bg-red-950/90 border-red-500/40 text-red-200" : "bg-bg-raised/95 border-line-strong")}>
              {t.msg}
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </div>
  );
}

function TopBar() {
  const { overview, refresh, toast } = useStore();
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const active = overview?.emergency;
  const working = overview?.agents.filter((a) => a.activite === "travail").length ?? 0;
  const actifs = overview?.agents.filter((a) => a.statut === "actif").length ?? 0;
  return (
    <header className={cx("h-14 shrink-0 border-b flex items-center justify-between px-5 gap-4", active ? "border-red-500/40 bg-red-950/40" : "border-line")}>
      <div className="text-xs text-ink-muted flex items-center gap-4">
        {active ? <span className="text-red-300 font-semibold flex items-center gap-2"><OctagonX size={15} />ARRÊT D'URGENCE ACTIF — agents gelés, accès externes coupés</span> : (
          <>
            <span><span className="text-ink font-medium tabular-nums">{actifs}</span> agents actifs</span>
            <span><span className="text-ink font-medium tabular-nums">{working}</span> au travail</span>
          </>
        )}
      </div>
      <div className="flex items-center gap-2">
      {overview?.simulation != null && !active && (
        <Button size="sm" variant={overview.simulation ? "secondary" : "ghost"} data-testid="simulation-toggle"
          title="Mode démonstration : fait vivre l'organisation (tâches, messages, demandes, refus)"
          onClick={async () => {
            try { await api("/api/simulation", { body: { active: !overview.simulation } }); refresh(); } catch (e: any) { toast(e.message, "err"); }
          }}>
          {overview.simulation ? <><Pause size={13} /><span className="relative flex w-2 h-2"><span className="absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-60 animate-ping" /><span className="relative inline-flex w-2 h-2 rounded-full bg-emerald-400" /></span>Simulation en cours</> : <><Play size={13} />Lancer la simulation</>}
        </Button>
      )}
      {active ? (
        <Button variant="primary" loading={busy} onClick={async () => {
          setBusy(true);
          try { await api("/api/emergency/resume", { body: {} }); toast("Plateforme relancée"); refresh(); } catch (e: any) { toast(e.message, "err"); }
          setBusy(false);
        }} data-testid="emergency-resume"><Play size={14} />Reprendre</Button>
      ) : (
        <Button variant="danger" onClick={() => setConfirm(true)} data-testid="emergency-stop"><OctagonX size={15} />Arrêt d'urgence</Button>
      )}
      </div>
      <Modal open={confirm} onClose={() => setConfirm(false)} title="Arrêt d'urgence">
        <p className="text-sm text-ink-muted">Tous les agents sont gelés immédiatement, les conteneurs arrêtés et tout accès externe coupé. Seul le Propriétaire peut ensuite relancer.</p>
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="ghost" onClick={() => setConfirm(false)}>Annuler</Button>
          <Button variant="danger" loading={busy} data-testid="emergency-confirm" onClick={async () => {
            setBusy(true);
            try {
              const r = await api("/api/emergency/stop", { body: { raison: "arrêt d'urgence depuis le tableau de bord" } });
              toast(`Agents gelés en ${r.duree_s.toFixed(2)} s`);
              setConfirm(false);
              refresh();
            } catch (e: any) { toast(e.message, "err"); }
            setBusy(false);
          }}><OctagonX size={15} />Tout geler maintenant</Button>
        </div>
      </Modal>
    </header>
  );
}
