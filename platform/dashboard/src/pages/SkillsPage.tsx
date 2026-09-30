import { Sparkles } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Empty, Modal, PageHeader, Select, Spinner, STATUT_TONE } from "../components/ui";
import { api, dateFr, eur, qs } from "../lib/api";
import { useResource, useStore } from "../lib/store";

export function SkillsPage() {
  const { overview, toast } = useStore();
  const [portee, setPortee] = useState("");
  const [statut, setStatut] = useState("");
  const skills = useResource<any[]>(`/api/skills${qs({ portee, statut })}`, [], (e) => e.type === "skill");
  const [open, setOpen] = useState<any | null>(null);
  const name = (id: string) => overview?.agents.find((a) => a.id === id)?.nom ?? id;
  return (
    <div className="p-8 max-w-[1300px] mx-auto">
      <PageHeader title="Skills" subtitle="Compétences réutilisables créées par les agents, sans limite de nombre. Cycle : brouillon → auto-test → revue du Vérificateur → publié."
        actions={<>
          <Select value={portee} onChange={(e) => setPortee(e.target.value)} className="w-40"><option value="">Toutes portées</option><option value="agent">agent</option><option value="equipe">équipe</option><option value="global">global</option></Select>
          <Select value={statut} onChange={(e) => setStatut(e.target.value)} className="w-40"><option value="">Tous statuts</option>{["brouillon", "teste", "approuve", "obsolete"].map((s) => <option key={s}>{s}</option>)}</Select>
        </>} />
      <Card className="overflow-hidden">
        {skills.error ? <Empty title="Skills indisponibles">{skills.error}</Empty> : !skills.data ? <Spinner /> : !skills.data.length ? (
          <Empty icon={<Sparkles size={22} />} title="Aucun skill">Les agents créent leurs skills avec l'outil <code>creer_skill</code>.</Empty>
        ) : (
          <table className="w-full text-sm" data-testid="skills-table">
            <thead><tr className="border-b border-line text-ink-subtle">{["Skill", "Portée", "Statut", "Auteur", "Utilisations", "Réussite", "Coût moyen", "Dernier usage"].map((h) => <th key={h} className="text-left py-2.5 px-4 font-semibold uppercase tracking-wider text-[10px]">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-line">
              {skills.data.map((s) => (
                <tr key={s.id} className="hover:bg-bg-muted/60 cursor-pointer" onClick={() => setOpen(s)}>
                  <td className="py-2.5 px-4 font-medium">{s.nom} <span className="text-ink-subtle font-normal text-xs">v{s.version}</span>{s.signale && <Badge tone="orange">à revoir</Badge>}</td>
                  <td className="py-2.5 px-4"><Badge tone="violet">{s.portee}</Badge></td>
                  <td className="py-2.5 px-4"><Badge tone={STATUT_TONE[s.statut]}>{s.statut}</Badge></td>
                  <td className="py-2.5 px-4 text-ink-muted">{name(s.auteur)}</td>
                  <td className="py-2.5 px-4 tabular-nums">{s.utilisations}</td>
                  <td className="py-2.5 px-4 tabular-nums">{s.evaluations ? `${Math.round(s.taux_reussite * 100)} %` : "—"}</td>
                  <td className="py-2.5 px-4 tabular-nums text-ink-muted">{eur(s.cout_moyen_eur, 4)}</td>
                  <td className="py-2.5 px-4 text-ink-muted text-xs">{dateFr(s.derniere_utilisation)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
      <Modal open={!!open} onClose={() => setOpen(null)} title={open ? `Skill « ${open.nom} » v${open.version}` : ""} wide>
        {open && (
          <div className="space-y-4 text-sm">
            <div className="flex flex-wrap gap-2"><Badge tone="violet">{open.portee}</Badge><Badge tone={STATUT_TONE[open.statut]}>{open.statut}</Badge><Badge>auteur : {name(open.auteur)}</Badge>{(open.permissions_requises ?? []).map((p: string) => <Badge key={p} tone="orange">{p}</Badge>)}</div>
            {open.revue && <div className="text-xs text-ink-muted">Revue du Vérificateur : {open.revue}</div>}
            <pre className="whitespace-pre-wrap text-xs bg-bg border border-line rounded-lg p-3 max-h-80 overflow-y-auto">{open.contenu}</pre>
            {open.code && <pre className="whitespace-pre-wrap text-xs font-mono bg-bg border border-line rounded-lg p-3 max-h-60 overflow-y-auto">{open.code}</pre>}
            <div className="flex justify-end gap-2">
              {open.statut !== "obsolete" && <Button variant="ghost" onClick={async () => {
                try { await api(`/api/skills/${open.id}/obsolete`, { body: { raison: "retiré par le Propriétaire" } }); toast("Skill archivé (obsolète)"); setOpen(null); skills.reload(); } catch (e: any) { toast(e.message, "err"); }
              }}>Marquer obsolète</Button>}
              {open.statut === "teste" && <Button variant="primary" onClick={async () => {
                try { await api(`/api/skills/${open.id}/review`, { body: {} }); toast("Revue lancée"); setOpen(null); skills.reload(); } catch (e: any) { toast(e.message, "err"); }
              }}>Lancer la revue</Button>}
            </div>
          </div>
        )}
      </Modal>
    </div>
  );
}
