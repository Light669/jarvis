import { useMemo, useState } from "react";
import { LEVEL_LABEL, LEVELS, type Agent, type Level } from "../lib/api";
import { useStore } from "../lib/store";
import { Field, Input, Select, Textarea } from "./ui";

export type AgentDraft = {
  nom: string;
  niveau: Level;
  parent_id: string | null;
  modele: string;
  role: string;
  contexte: string;
  instructions: string;
  objectif: string;
  kpi: string;
  outils: string;
  skills: string;
  interdits: string;
  budget_jour_eur: number;
  budget_mois_eur: string;
  statut?: string;
};

const RANK: Record<Level, number> = { chef: 0, responsable: 1, salarie: 2, apprenti: 3 };
const MODELS = [
  "ollama/qwen2.5:7b",
  "ollama/qwen2.5:3b",
  "ollama/qwen2.5:14b",
  "ollama/llama3.1:8b",
  "groq/llama-3.1-8b-instant",
  "gemini/gemini-2.0-flash",
  "openrouter/meta-llama/llama-3.3-70b-instruct:free",
  "mistral/mistral-small-latest",
];
const TOOLS = ["recherche_web", "executer_code", "notion", "email_brouillon"];

export const draftFromAgent = (a: Agent): AgentDraft => ({
  nom: a.nom,
  niveau: a.niveau,
  parent_id: a.parent_id,
  modele: a.modele,
  role: a.role,
  contexte: a.contexte,
  instructions: a.instructions,
  objectif: a.objectif,
  kpi: a.kpi.join(", "),
  outils: a.outils.join(", "),
  skills: a.skills.join(", "),
  interdits: a.interdits,
  budget_jour_eur: a.budget_jour_eur,
  budget_mois_eur: a.budget_mois_eur == null ? "" : String(a.budget_mois_eur),
});

export const emptyDraft = (): AgentDraft => ({
  nom: "",
  niveau: "salarie",
  parent_id: null,
  modele: "ollama/qwen2.5:7b",
  role: "",
  contexte: "",
  instructions: "",
  objectif: "",
  kpi: "",
  outils: "",
  skills: "",
  interdits: "",
  budget_jour_eur: 0.5,
  budget_mois_eur: "",
  statut: "actif",
});

const list = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);

export function draftToPayload(d: AgentDraft) {
  return {
    ...d,
    kpi: list(d.kpi),
    outils: list(d.outils),
    skills: list(d.skills),
    budget_jour_eur: Number(d.budget_jour_eur) || 0,
    budget_mois_eur: d.budget_mois_eur === "" ? null : Number(d.budget_mois_eur),
  };
}

export function AgentForm({ draft, onChange, mode, selfId }: { draft: AgentDraft; onChange: (d: AgentDraft) => void; mode: "create" | "edit"; selfId?: string }) {
  const { overview } = useStore();
  const set = <K extends keyof AgentDraft>(k: K, v: AgentDraft[K]) => onChange({ ...draft, [k]: v });
  const parents = useMemo(
    () => (overview?.agents ?? []).filter((a) => a.statut !== "archive" && a.id !== selfId && RANK[a.niveau] === RANK[draft.niveau] - 1),
    [overview, draft.niveau, selfId],
  );
  const [showAdv, setShowAdv] = useState(mode === "create");

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3">
        <Field label="Nom">
          <Input value={draft.nom} onChange={(e) => set("nom", e.target.value)} placeholder="Prospecteur" required />
        </Field>
        <Field label="Modèle" hint="Local d'abord, puis API gratuites (repli automatique)">
          <Input list="models" value={draft.modele} onChange={(e) => set("modele", e.target.value)} />
          <datalist id="models">{MODELS.map((m) => <option key={m} value={m} />)}</datalist>
        </Field>
        <Field label="Niveau">
          <Select value={draft.niveau} disabled={mode === "edit"} onChange={(e) => onChange({ ...draft, niveau: e.target.value as Level, parent_id: null })}>
            {LEVELS.map((l) => <option key={l} value={l}>{LEVEL_LABEL[l]}</option>)}
          </Select>
        </Field>
        <Field label="Supérieur">
          <Select value={draft.parent_id ?? ""} disabled={draft.niveau === "chef"} onChange={(e) => set("parent_id", e.target.value || null)}>
            <option value="">{draft.niveau === "chef" ? "— (Propriétaire)" : "Choisir…"}</option>
            {parents.map((p) => <option key={p.id} value={p.id}>{p.nom} ({p.id})</option>)}
          </Select>
        </Field>
      </div>
      <Field label="Rôle">
        <Input value={draft.role} onChange={(e) => set("role", e.target.value)} placeholder="Trouver et qualifier des prospects B2B" />
      </Field>
      <Field label="Contexte" hint="Injecté dans le prompt système à chaque tâche">
        <Textarea value={draft.contexte} onChange={(e) => set("contexte", e.target.value)} rows={4} />
      </Field>
      <Field label="Instructions (Markdown)" hint="Injectées dans le prompt système à chaque tâche">
        <Textarea value={draft.instructions} onChange={(e) => set("instructions", e.target.value)} rows={6} />
      </Field>
      <button type="button" onClick={() => setShowAdv((v) => !v)} className="text-xs text-accent hover:underline">
        {showAdv ? "Masquer" : "Afficher"} objectif, outils, budget et interdits
      </button>
      {showAdv && (
        <div className="space-y-4">
          <Field label="Objectif mesurable">
            <Textarea value={draft.objectif} onChange={(e) => set("objectif", e.target.value)} rows={2} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="KPI" hint="Séparés par des virgules">
              <Input value={draft.kpi} onChange={(e) => set("kpi", e.target.value)} placeholder="10 leads/semaine, 85 % validés" />
            </Field>
            <Field label="Outils autorisés" hint={`Ex. : ${TOOLS.join(", ")}`}>
              <Input value={draft.outils} onChange={(e) => set("outils", e.target.value)} />
            </Field>
            <Field label="Skills de départ">
              <Input value={draft.skills} onChange={(e) => set("skills", e.target.value)} placeholder="prospection-b2b" />
            </Field>
            <Field label="Coût maximum par jour (€)">
              <Input type="number" min={0} step={0.05} value={draft.budget_jour_eur} onChange={(e) => set("budget_jour_eur", Number(e.target.value))} />
            </Field>
            {draft.niveau === "responsable" && (
              <Field label="Enveloppe mensuelle de l'équipe (€)" hint="Vide = pas d'enveloppe dédiée">
                <Input type="number" min={0} step={1} value={draft.budget_mois_eur} onChange={(e) => set("budget_mois_eur", e.target.value)} />
              </Field>
            )}
          </div>
          <Field label="Interdits">
            <Textarea value={draft.interdits} onChange={(e) => set("interdits", e.target.value)} rows={2} />
          </Field>
        </div>
      )}
    </div>
  );
}
