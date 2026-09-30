import { Download, Search, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Empty, Input, PageHeader, Select, Spinner, STATUT_TONE } from "../components/ui";
import { api, download, LEVEL_LABEL, LEVELS, qs } from "../lib/api";
import { useResource, useStore } from "../lib/store";

const TYPES = ["agent", "message", "demande", "tache", "action", "modele", "budget", "depense", "permission_refusee", "alerte",
  "coffre", "skill", "securite", "urgence", "tableau_de_bord", "systeme", "decision", "amelioration"];

export function LogsPage() {
  const { overview, toast } = useStore();
  const [f, setF] = useState({ q: "", agent_id: "", niveau: "", type_evenement: "", gravite: "", since: "", until: "" });
  const [applied, setApplied] = useState(f);
  const [live, setLive] = useState(true);
  const logs = useResource<any[]>(`/api/logs${qs({ ...applied, limit: 500 })}`, [], live ? (e) => e.type === "log" : undefined);
  const [integrity, setIntegrity] = useState<any>(null);
  const set = (k: keyof typeof f, v: string) => setF({ ...f, [k]: v });

  return (
    <div className="p-8 max-w-[1400px] mx-auto">
      <PageHeader
        title="Journal"
        subtitle="Append-only, chaîné par hash. Personne — ni agent ni tableau de bord — ne peut modifier ou effacer une ligne."
        actions={<>
          <Button onClick={async () => {
            try {
              const r = await api("/api/logs/verify");
              setIntegrity(r);
              toast(r.ok ? `Intégrité OK (${r.lignes} lignes)` : "Intégrité compromise !", r.ok ? "ok" : "err");
            } catch (e: any) { toast(e.message, "err"); }
          }}><ShieldCheck size={14} />Vérifier l'intégrité</Button>
          <Button onClick={() => download(`/api/logs/export.csv${qs(applied)}`, "orchestra-logs.csv")}><Download size={14} />Export CSV</Button>
        </>}
      />
      {integrity && !integrity.ok && (
        <Card className="p-4 mb-4 border-red-500/40 bg-red-500/5 text-sm text-red-300">
          <div className="font-semibold mb-1">Altération détectée</div>
          <ul className="list-disc ml-5 text-xs">{integrity.erreurs.slice(0, 10).map((e: string) => <li key={e}>{e}</li>)}</ul>
        </Card>
      )}
      <Card className="p-4 mb-4">
        <form className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-2" onSubmit={(e) => { e.preventDefault(); setApplied(f); }}>
          <div className="col-span-2 relative">
            <Search size={14} className="absolute left-3 top-2.5 text-ink-subtle" />
            <Input className="pl-8" placeholder="Recherche plein texte" value={f.q} onChange={(e) => set("q", e.target.value)} />
          </div>
          <Select value={f.agent_id} onChange={(e) => set("agent_id", e.target.value)}>
            <option value="">Tous les acteurs</option>
            <option value="proprietaire">Propriétaire</option>
            {overview?.agents.map((a) => <option key={a.id} value={a.id}>{a.nom}</option>)}
          </Select>
          <Select value={f.niveau} onChange={(e) => set("niveau", e.target.value)}>
            <option value="">Tous niveaux</option>
            {LEVELS.map((l) => <option key={l} value={l}>{LEVEL_LABEL[l]}</option>)}
          </Select>
          <Select value={f.type_evenement} onChange={(e) => set("type_evenement", e.target.value)}>
            <option value="">Tous types</option>
            {TYPES.map((t) => <option key={t}>{t}</option>)}
          </Select>
          <Select value={f.gravite} onChange={(e) => set("gravite", e.target.value)}>
            <option value="">Toute gravité</option>
            {["info", "attention", "grave", "critique"].map((g) => <option key={g}>{g}</option>)}
          </Select>
          <Input type="date" value={f.since} onChange={(e) => set("since", e.target.value)} title="Depuis" />
          <Input type="date" value={f.until} onChange={(e) => set("until", e.target.value)} title="Jusqu'au" />
          <div className="col-span-2 md:col-span-4 xl:col-span-8 flex items-center justify-between">
            <label className="flex items-center gap-2 text-xs text-ink-muted"><input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} />Mise à jour en direct</label>
            <div className="flex gap-2">
              <Button type="button" variant="ghost" size="sm" onClick={() => { const z = { q: "", agent_id: "", niveau: "", type_evenement: "", gravite: "", since: "", until: "" }; setF(z); setApplied(z); }}>Réinitialiser</Button>
              <Button type="submit" variant="primary" size="sm">Filtrer</Button>
            </div>
          </div>
        </form>
      </Card>
      <Card className="overflow-hidden">
        {!logs.data ? <Spinner /> : !logs.data.length ? <Empty title="Aucune entrée" /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs" data-testid="logs-table">
              <thead>
                <tr className="border-b border-line text-ink-subtle">
                  {["#", "Horodatage", "Acteur", "Niveau", "Type", "Action", "Cible", "Résultat", "Coût"].map((h) => (
                    <th key={h} className="text-left py-2.5 px-3 font-semibold uppercase tracking-wider text-[10px]">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {logs.data.map((l) => (
                  <tr key={l.seq} className="hover:bg-bg-muted/60 transition-colors">
                    <td className="py-2 px-3 font-mono text-ink-subtle">{l.seq}</td>
                    <td className="py-2 px-3 font-mono whitespace-nowrap text-ink-muted">{l.horodatage.replace("T", " ").slice(0, 23)}</td>
                    <td className="py-2 px-3 whitespace-nowrap">{overview?.agents.find((a) => a.id === l.agent_id)?.nom ?? l.agent_id ?? "système"}</td>
                    <td className="py-2 px-3 text-ink-muted">{l.niveau ?? ""}</td>
                    <td className="py-2 px-3"><Badge tone={STATUT_TONE[l.gravite] ?? "gray"}>{l.type_evenement}</Badge></td>
                    <td className="py-2 px-3">{l.action}</td>
                    <td className="py-2 px-3 text-ink-muted max-w-[220px] truncate" title={l.cible ?? ""}>{l.cible}</td>
                    <td className="py-2 px-3 text-ink-muted max-w-[320px] truncate" title={l.resultat}>{l.resultat}</td>
                    <td className="py-2 px-3 tabular-nums text-ink-muted whitespace-nowrap">{l.cout_tokens ? `${l.cout_tokens} tk` : ""}{l.cout_eur ? ` · ${l.cout_eur.toFixed(4)} €` : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
