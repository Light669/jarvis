import { AnimatePresence, motion } from "framer-motion";
import {
  Activity, ArrowDownCircle, ArrowUpCircle, Archive, Coins, FileText, History, MessagesSquare, Pause, Play, RotateCcw, Send, Sparkles, X,
} from "lucide-react";
import { useEffect, useState } from "react";
import { api, dateFr, eur, qs, STATUS_LABEL, type Agent } from "../lib/api";
import { useResource, useStore, type LiveEvent } from "../lib/store";
import { AgentForm, draftFromAgent, draftToPayload, type AgentDraft } from "./AgentForm";
import { Badge, Button, Card, Empty, Field, Gauge, Input, LevelBadge, Spinner, STATUT_TONE, Tabs, Textarea } from "./ui";

type Tab = "fiche" | "activite" | "messages" | "skills" | "historique" | "couts";

export function AgentPanel({ agentId, onClose }: { agentId: string | null; onClose: () => void }) {
  const { overview } = useStore();
  const agent = overview?.agents.find((a) => a.id === agentId) ?? null;
  const [tab, setTab] = useState<Tab>("fiche");
  return (
    <AnimatePresence>
      {agent && (
        <motion.aside
          key="panel"
          initial={{ x: 40, opacity: 0 }}
          animate={{ x: 0, opacity: 1 }}
          exit={{ x: 40, opacity: 0 }}
          transition={{ duration: 0.2 }}
          className="absolute right-0 top-0 bottom-0 z-30 w-full max-w-[560px] bg-bg-subtle border-l border-line flex flex-col shadow-2xl"
          data-testid="agent-panel"
        >
          <div className="px-5 pt-4 pb-3 flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-semibold truncate">{agent.nom}</h2>
                <LevelBadge level={agent.niveau} />
              </div>
              <div className="text-xs text-ink-subtle font-mono mt-0.5">
                {agent.id} · v{agent.version} · {agent.vault_path}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge tone={STATUT_TONE[agent.statut]} dot>{STATUS_LABEL[agent.statut]}</Badge>
              <button onClick={onClose} className="p-1 text-ink-subtle hover:text-ink rounded" aria-label="Fermer le panneau"><X size={16} /></button>
            </div>
          </div>
          <Tabs<Tab>
            value={tab}
            onChange={setTab}
            tabs={[
              { id: "fiche", label: "Fiche", icon: <FileText size={13} /> },
              { id: "activite", label: "Activité", icon: <Activity size={13} /> },
              { id: "messages", label: "Messages", icon: <MessagesSquare size={13} /> },
              { id: "skills", label: "Skills", icon: <Sparkles size={13} /> },
              { id: "historique", label: "Historique", icon: <History size={13} /> },
              { id: "couts", label: "Coûts", icon: <Coins size={13} /> },
            ]}
          />
          <div className="flex-1 overflow-y-auto p-5">
            {tab === "fiche" && <FicheTab agent={agent} />}
            {tab === "activite" && <ActivityTab agent={agent} />}
            {tab === "messages" && <MessagesTab agent={agent} />}
            {tab === "skills" && <SkillsTab agent={agent} />}
            {tab === "historique" && <HistoryTab agent={agent} />}
            {tab === "couts" && <CostsTab agent={agent} />}
          </div>
        </motion.aside>
      )}
    </AnimatePresence>
  );
}

// ------------------------------------------------------------------ Fiche
function FicheTab({ agent }: { agent: Agent }) {
  const { toast, refresh } = useStore();
  const [draft, setDraft] = useState<AgentDraft>(draftFromAgent(agent));
  const [saving, setSaving] = useState(false);
  const [raison, setRaison] = useState("");
  const versions = useResource<any[]>(`/api/agents/${agent.id}/versions`, [agent.version]);
  useEffect(() => setDraft(draftFromAgent(agent)), [agent.id, agent.version]); // eslint-disable-line
  const dirty = JSON.stringify(draftToPayload(draft)) !== JSON.stringify(draftToPayload(draftFromAgent(agent)));

  const run = async (fn: () => Promise<any>, ok: string) => {
    try {
      await fn();
      toast(ok);
      refresh();
    } catch (e: any) {
      toast(e.message, "err");
    }
  };
  const save = async () => {
    setSaving(true);
    const { niveau, ...payload } = draftToPayload(draft); // eslint-disable-line @typescript-eslint/no-unused-vars
    await run(() => api(`/api/agents/${agent.id}`, { method: "PATCH", body: { ...payload, raison: raison || undefined } }), "Fiche enregistrée (nouvelle version)");
    setRaison("");
    setSaving(false);
  };
  const act = (action: string, body: any = {}) => run(() => api(`/api/agents/${agent.id}/${action}`, { body }), "Action effectuée");

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-2">
        {agent.statut === "brouillon" && <Button size="sm" onClick={() => act("activate")}><Play size={13} />Activer</Button>}
        {agent.statut === "actif" && <Button size="sm" onClick={() => act("pause")}><Pause size={13} />Mettre en pause</Button>}
        {agent.statut === "pause" && <Button size="sm" onClick={() => act("resume")}><Play size={13} />Reprendre</Button>}
        {agent.niveau !== "chef" && agent.niveau !== "responsable" && agent.statut !== "archive" && (
          <Button size="sm" onClick={() => act("promote", { raison: "promotion par le Propriétaire" })}><ArrowUpCircle size={13} />Promouvoir</Button>
        )}
        {(agent.niveau === "salarie" || agent.niveau === "responsable") && agent.statut !== "archive" && (
          <Button size="sm" onClick={() => {
            const p = prompt("Identifiant du nouveau supérieur (ex. agent-0004) :");
            if (p) act("demote", { new_parent_id: p, raison: "rétrogradation par le Propriétaire" });
          }}><ArrowDownCircle size={13} />Rétrograder</Button>
        )}
        {agent.statut !== "archive" && (
          <Button size="sm" variant="ghost" className="text-red-300 hover:text-red-200" onClick={() => {
            const r = prompt("Raison de l'archivage (licenciement) — l'agent n'est jamais supprimé :");
            if (r) act("archive", { raison: r });
          }}><Archive size={13} />Archiver</Button>
        )}
      </div>

      {agent.statut === "actif" && <AssignTask agent={agent} />}

      <AgentForm draft={draft} onChange={setDraft} mode="edit" selfId={agent.id} />
      <div className="sticky bottom-0 -mx-5 px-5 py-3 bg-bg-subtle/95 backdrop-blur border-t border-line flex items-center gap-2">
        <Input placeholder="Raison de la modification (optionnel)" value={raison} onChange={(e) => setRaison(e.target.value)} className="flex-1" />
        <Button variant="primary" onClick={save} loading={saving} disabled={!dirty} data-testid="save-agent">Enregistrer</Button>
      </div>

      <div>
        <h3 className="text-sm font-semibold mb-2">Versions de la fiche</h3>
        {versions.loading && !versions.data ? <Spinner /> : (
          <div className="space-y-1.5">
            {(versions.data ?? []).map((v) => (
              <div key={v.version} className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg bg-bg border border-line text-xs">
                <div className="min-w-0">
                  <span className="font-semibold">v{v.version}</span>
                  <span className="text-ink-subtle"> · {dateFr(v.horodatage)} · {v.auteur}</span>
                  <div className="text-ink-muted truncate">{v.raison}</div>
                </div>
                {v.version !== agent.version && (
                  <Button size="sm" variant="ghost" onClick={() => run(() => api(`/api/agents/${agent.id}/restore/${v.version}`, { body: {} }), `Version ${v.version} restaurée`)}>
                    <RotateCcw size={12} />Restaurer
                  </Button>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function AssignTask({ agent }: { agent: Agent }) {
  const { toast } = useStore();
  const [consigne, setConsigne] = useState("");
  const [busy, setBusy] = useState(false);
  return (
    <Card className="p-3 space-y-2">
      <Field label="Confier une tâche">
        <Textarea rows={2} value={consigne} onChange={(e) => setConsigne(e.target.value)} placeholder="Ex. : Liste 10 PME lyonnaises du secteur BTP" className="font-sans text-sm" />
      </Field>
      <div className="flex justify-end">
        <Button size="sm" variant="primary" loading={busy} disabled={!consigne.trim()} onClick={async () => {
          setBusy(true);
          try {
            await api(`/api/agents/${agent.id}/tasks`, { body: { consigne } });
            toast("Tâche confiée");
            setConsigne("");
          } catch (e: any) {
            toast(e.message, "err");
          }
          setBusy(false);
        }}><Send size={13} />Lancer</Button>
      </div>
    </Card>
  );
}

// ------------------------------------------------------------------ Activité
function ActivityTab({ agent }: { agent: Agent }) {
  const { events, toast } = useStore();
  const tasks = useResource<any[]>(`/api/tasks${qs({ agent_id: agent.id, limit: 20 })}`, [], (e) => e.type === "task" && e.agent_id === agent.id);
  const mine = events.filter((e: LiveEvent) =>
    e.agent_id === agent.id || e.de === agent.id || e.a === agent.id || e.entry?.agent_id === agent.id || e.entry?.cible === agent.id).slice(0, 40);
  const validate = async (id: string, succes: boolean) => {
    try {
      await api(`/api/tasks/${id}/validate`, { body: { succes, point_echec: succes ? null : prompt("Point d'échec ?") || "non précisé" } });
      tasks.reload();
    } catch (e: any) {
      toast(e.message, "err");
    }
  };
  return (
    <div className="space-y-6">
      <Card className="p-4">
        <div className="text-xs text-ink-muted">Maintenant</div>
        <div className="text-base font-medium mt-1">{agent.activite === "travail" ? "Travaille" : agent.activite === "attente" ? "En attente d'une réponse" : agent.activite === "erreur" ? "En erreur" : agent.activite === "gele" ? "Gelé (arrêt d'urgence)" : "Inactif"}</div>
        {agent.activite_detail && <div className="text-sm text-ink-muted mt-1">{agent.activite_detail}</div>}
      </Card>
      <div>
        <h3 className="text-sm font-semibold mb-2">Tâches</h3>
        {!tasks.data?.length ? <Empty title="Aucune tâche" /> : (
          <div className="space-y-2">
            {tasks.data.map((t) => (
              <div key={t.id} className="p-3 rounded-lg bg-bg border border-line text-xs space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-ink-subtle">{t.id}</span>
                  <div className="flex items-center gap-1.5">
                    {t.succes === 1 && <Badge tone="green">validée</Badge>}
                    {t.succes === 0 && <Badge tone="red">échec</Badge>}
                    <Badge tone={STATUT_TONE[t.statut]}>{t.statut}</Badge>
                  </div>
                </div>
                <div className="text-ink">{t.consigne}</div>
                {t.resultat && <div className="text-ink-muted whitespace-pre-wrap line-clamp-4">{t.resultat}</div>}
                <div className="flex items-center justify-between text-ink-subtle">
                  <span>{dateFr(t.debut)} · {t.tokens} tokens · {eur(t.cout_eur, 4)}</span>
                  {t.statut === "terminee" && t.succes == null && (
                    <span className="flex gap-1">
                      <Button size="sm" variant="ghost" onClick={() => validate(t.id, true)}>✓ Valider</Button>
                      <Button size="sm" variant="ghost" onClick={() => validate(t.id, false)}>✗ Échec</Button>
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
      <div>
        <h3 className="text-sm font-semibold mb-2">Flux en direct</h3>
        {!mine.length ? <Empty title="Aucun événement depuis l'ouverture" /> : (
          <ul className="space-y-1 font-mono text-[11px]">
            {mine.map((e, i) => (
              <li key={i} className="text-ink-muted"><span className="text-ink-subtle">{e.ts.slice(11, 19)}</span> {e.type} {e.entry ? `${e.entry.type_evenement} · ${e.entry.action}` : e.statut ?? e.activite ?? e.sujet ?? ""}</li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Messages et demandes
function MessagesTab({ agent }: { agent: Agent }) {
  const { toast, overview } = useStore();
  const msgs = useResource<any[]>(`/api/messages${qs({ agent_id: agent.id, limit: 100 })}`, [], (e) => (e.type === "message" || e.type === "request") && (e.de === agent.id || e.a === agent.id));
  const reqs = useResource<any[]>(`/api/requests${qs({ agent_id: agent.id })}`, [], (e) => e.type === "request");
  const [sujet, setSujet] = useState("");
  const [corps, setCorps] = useState("");
  const name = (id: string) => (id === "proprietaire" ? "Propriétaire" : overview?.agents.find((a) => a.id === id)?.nom ?? id);
  const threads: Record<string, any[]> = {};
  (msgs.data ?? []).forEach((m) => (threads[m.thread_id] ??= []).push(m));
  return (
    <div className="space-y-6">
      <Card className="p-3 space-y-2">
        <div className="text-xs font-medium text-ink-muted">Écrire à {agent.nom} (en tant que Propriétaire)</div>
        <Input placeholder="Sujet" value={sujet} onChange={(e) => setSujet(e.target.value)} />
        <Textarea rows={3} placeholder="Message" value={corps} onChange={(e) => setCorps(e.target.value)} className="font-sans text-sm" />
        <div className="flex justify-end">
          <Button size="sm" variant="primary" disabled={!sujet || !corps} onClick={async () => {
            try {
              await api("/api/messages", { body: { a: agent.id, sujet, corps } });
              setSujet(""); setCorps(""); msgs.reload();
            } catch (e: any) { toast(e.message, "err"); }
          }}><Send size={13} />Envoyer</Button>
        </div>
      </Card>
      <div>
        <h3 className="text-sm font-semibold mb-2">Demandes</h3>
        {!reqs.data?.length ? <Empty title="Aucune demande" /> : reqs.data.map((r) => (
          <div key={r.id} className="p-3 mb-2 rounded-lg bg-bg border border-line text-xs space-y-1">
            <div className="flex justify-between gap-2"><span className="font-medium text-sm">{r.sujet}</span><Badge tone={STATUT_TONE[r.statut]}>{r.statut}</Badge></div>
            <div className="text-ink-subtle">{r.type} · {name(r.de)} → {name(r.a)} · {dateFr(r.cree_le)}</div>
            <div className="text-ink-muted">{r.justification}</div>
            {r.reponse && <div className="text-ink-muted italic">↳ {r.reponse}</div>}
          </div>
        ))}
      </div>
      <div>
        <h3 className="text-sm font-semibold mb-2">Fils de discussion</h3>
        {!Object.keys(threads).length ? <Empty title="Aucun message" /> : Object.entries(threads).map(([tid, list]) => (
          <details key={tid} className="mb-2 rounded-lg bg-bg border border-line group" open={Object.keys(threads).length < 4}>
            <summary className="px-3 py-2 text-xs cursor-pointer flex justify-between gap-2">
              <span className="font-medium truncate">{list[list.length - 1].sujet}</span>
              <span className="text-ink-subtle shrink-0">{list.length} msg</span>
            </summary>
            <div className="px-3 pb-3 space-y-2">
              {[...list].reverse().map((m) => (
                <div key={m.id} className={`text-xs p-2 rounded-md ${m.de === agent.id ? "bg-indigo-400/10 ml-6" : "bg-bg-muted mr-6"}`}>
                  <div className="text-ink-subtle mb-0.5">{name(m.de)} → {name(m.a)} · {dateFr(m.horodatage)} {m.kind === "demande" && <Badge tone="orange">demande</Badge>}</div>
                  <div className="whitespace-pre-wrap text-ink-muted">{m.corps}</div>
                </div>
              ))}
            </div>
          </details>
        ))}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Skills
function SkillsTab({ agent }: { agent: Agent }) {
  const skills = useResource<any[]>(`/api/skills${qs({ agent_id: agent.id })}`, [], (e) => e.type === "skill");
  if (skills.error) return <Empty title="Skills indisponibles">{skills.error}</Empty>;
  if (!skills.data) return <Spinner />;
  if (!skills.data.length) return <Empty icon={<Sparkles size={20} />} title="Aucun skill">Les skills créés ou accessibles par cet agent apparaîtront ici.</Empty>;
  return (
    <div className="space-y-2">
      {skills.data.map((s) => (
        <div key={s.id} className="p-3 rounded-lg bg-bg border border-line text-xs">
          <div className="flex items-center justify-between gap-2">
            <span className="font-medium text-sm">{s.nom} <span className="text-ink-subtle font-normal">v{s.version}</span></span>
            <div className="flex gap-1.5"><Badge tone="violet">{s.portee}</Badge><Badge tone={STATUT_TONE[s.statut]}>{s.statut}</Badge></div>
          </div>
          <div className="grid grid-cols-3 gap-2 mt-2 text-ink-muted">
            <div>{s.utilisations} utilisations</div>
            <div>{Math.round((s.taux_reussite ?? 0) * 100)} % réussite</div>
            <div>{eur(s.cout_moyen_eur ?? 0, 4)} / usage</div>
          </div>
          <div className="text-ink-subtle mt-1">{s.auteur === agent.id ? "Créé par cet agent" : `Auteur : ${s.auteur}`}</div>
        </div>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ Historique et logs
function HistoryTab({ agent }: { agent: Agent }) {
  const logs = useResource<any[]>(`/api/logs${qs({ agent_id: agent.id, limit: 100 })}`, [agent.version], (e) => e.type === "log" && e.entry?.agent_id === agent.id);
  const target = useResource<any[]>(`/api/logs${qs({ q: agent.id, limit: 50 })}`, [agent.version]);
  const hist = useResource<any>(`/api/agents/${agent.id}/history`, [agent.version]);
  const merged = [...(logs.data ?? []), ...(target.data ?? [])]
    .filter((v, i, arr) => arr.findIndex((x) => x.seq === v.seq) === i)
    .sort((a, b) => b.seq - a.seq);
  return (
    <div className="space-y-6">
      <div>
        <h3 className="text-sm font-semibold mb-2">Commits Git de la fiche</h3>
        {!hist.data?.commits?.length ? <Empty title="Aucun commit" /> : (
          <ul className="space-y-1 text-[11px] font-mono">
            {hist.data.commits.map((c: string) => <li key={c} className="text-ink-muted truncate"><span className="text-accent">{c.slice(0, 7)}</span> {c.slice(41)}</li>)}
          </ul>
        )}
      </div>
      <div>
        <h3 className="text-sm font-semibold mb-2">Journal</h3>
        {!merged.length ? <Empty title="Aucune entrée" /> : (
          <ul className="space-y-1 text-[11px]">
            {merged.map((l) => (
              <li key={l.seq} className="flex gap-2">
                <span className="text-ink-subtle font-mono shrink-0">{l.horodatage.slice(5, 19).replace("T", " ")}</span>
                <Badge tone={STATUT_TONE[l.gravite] ?? "gray"}>{l.type_evenement}</Badge>
                <span className="text-ink-muted truncate">{l.action}{l.cible ? ` → ${l.cible}` : ""}{l.resultat && l.resultat !== "ok" ? ` · ${l.resultat}` : ""}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

// ------------------------------------------------------------------ Coûts
function CostsTab({ agent }: { agent: Agent }) {
  const c = useResource<any>(`/api/agents/${agent.id}/costs`, [agent.jour_eur]);
  if (!c.data) return <Spinner />;
  const ratio = c.data.budget_jour_eur ? c.data.jour_eur / c.data.budget_jour_eur : 0;
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <Card className="p-4"><div className="text-xs text-ink-muted">Aujourd'hui</div><div className="text-xl font-semibold mt-1 tabular-nums">{eur(c.data.jour_eur, 4)}</div><Gauge ratio={ratio} className="mt-3" /><div className="text-xs text-ink-subtle mt-1">sur {eur(c.data.budget_jour_eur)} / jour</div></Card>
        <Card className="p-4"><div className="text-xs text-ink-muted">Ce mois</div><div className="text-xl font-semibold mt-1 tabular-nums">{eur(c.data.mois_eur, 4)}</div><div className="text-xs text-ink-subtle mt-3">{c.data.tokens_mois.toLocaleString("fr-FR")} tokens</div></Card>
      </div>
      <p className="text-xs text-ink-subtle">Les modèles locaux (Ollama) et les quotas gratuits ne coûtent rien : seuls les appels payants entrent dans le budget.</p>
    </div>
  );
}
