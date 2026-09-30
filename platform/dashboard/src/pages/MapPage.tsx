import { Plus, Users } from "lucide-react";
import { useState } from "react";
import { AgentForm, draftToPayload, emptyDraft } from "../components/AgentForm";
import { AgentMap, PARTICLE_COLORS } from "../components/AgentMap";
import { AgentPanel } from "../components/AgentPanel";
import { Button, Empty, Modal } from "../components/ui";
import { api, type Agent } from "../lib/api";
import { useStore } from "../lib/store";

export function MapPage() {
  const { overview, toast, refresh } = useStore();
  const [selected, setSelected] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [draft, setDraft] = useState(emptyDraft());
  const [saving, setSaving] = useState(false);
  const [groupTeams, setGroupTeams] = useState(true);
  const [showArchived, setShowArchived] = useState(false);

  const create = async () => {
    setSaving(true);
    try {
      const a = await api<Agent>("/api/agents", { body: draftToPayload(draft) });
      toast(`${a.nom} créé (${a.id}) — fiche ${a.vault_path}`);
      setCreating(false);
      setDraft(emptyDraft());
      await refresh();
      setSelected(a.id);
    } catch (e: any) {
      toast(e.message, "err");
    }
    setSaving(false);
  };

  const empty = overview && !overview.agents.length;
  return (
    <div className="relative h-full">
      <div className="absolute top-4 left-4 z-20 flex flex-wrap items-center gap-2">
        <Button variant="primary" onClick={() => setCreating(true)} data-testid="new-agent"><Plus size={15} />Nouvel agent</Button>
        <Button size="sm" variant={groupTeams ? "secondary" : "ghost"} onClick={() => setGroupTeams((v) => !v)}><Users size={13} />Équipes</Button>
        <Button size="sm" variant={showArchived ? "secondary" : "ghost"} onClick={() => setShowArchived((v) => !v)}>Archivés</Button>
      </div>
      <div className="absolute top-4 right-4 z-10 hidden md:flex items-center gap-3 text-[11px] text-ink-muted bg-bg-subtle/90 border border-line rounded-lg px-3 py-2">
        <Legend color={PARTICLE_COLORS.message} label="message" />
        <Legend color={PARTICLE_COLORS.demande} label="demande" />
        <Legend color={PARTICLE_COLORS.refus} label="refus" />
        <span className="w-px h-3 bg-line-strong" />
        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm border-2 border-indigo-400" />travail</span>
        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm border-2 border-amber-400" />attente</span>
        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm border-2 border-red-500" />erreur</span>
        <span className="flex items-center gap-1"><span className="w-2.5 h-2.5 rounded-sm outline outline-2 outline-sky-400" />pause</span>
      </div>
      {empty ? (
        <div className="h-full flex items-center justify-center">
          <Empty icon={<Users size={28} />} title="Aucun agent pour l'instant">
            Commencez par créer le Chef d'Orchestre, puis ses Responsables. Vous pouvez aussi déposer une fiche dans
            <code className="mx-1">Cerveau/Agents/</code> depuis Obsidian.
            <div className="mt-4"><Button variant="primary" onClick={() => { setDraft({ ...emptyDraft(), niveau: "chef", nom: "Chef d'Orchestre" }); setCreating(true); }}>Créer le Chef d'Orchestre</Button></div>
          </Empty>
        </div>
      ) : (
        <AgentMap selected={selected} onSelect={setSelected} groupTeams={groupTeams} showArchived={showArchived} />
      )}
      <AgentPanel agentId={selected} onClose={() => setSelected(null)} />
      <Modal open={creating} onClose={() => setCreating(false)} title="Nouvel agent" wide>
        <AgentForm draft={draft} onChange={setDraft} mode="create" />
        <div className="flex justify-end gap-2 mt-6">
          <Button variant="ghost" onClick={() => setCreating(false)}>Annuler</Button>
          <Button variant="primary" onClick={create} loading={saving} disabled={!draft.nom.trim()} data-testid="create-agent">Créer l'agent</Button>
        </div>
      </Modal>
    </div>
  );
}

const Legend = ({ color, label }: { color: string; label: string }) => (
  <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full" style={{ background: color, boxShadow: `0 0 6px ${color}` }} />{label}</span>
);
