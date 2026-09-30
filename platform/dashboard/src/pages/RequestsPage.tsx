import { Check, Inbox, X } from "lucide-react";
import { useState } from "react";
import { Badge, Button, Card, Empty, Input, PageHeader, Spinner, STATUT_TONE } from "../components/ui";
import { api, dateFr, eur } from "../lib/api";
import { useResource, useStore } from "../lib/store";

export function RequestsPage() {
  const { overview, toast } = useStore();
  const pending = useResource<any[]>("/api/requests?pending=true", [], (e) => e.type === "request");
  const all = useResource<any[]>("/api/requests", [], (e) => e.type === "request");
  const [reponse, setReponse] = useState<Record<string, string>>({});
  const name = (id: string) => (id === "proprietaire" ? "Propriétaire" : overview?.agents.find((a) => a.id === id)?.nom ?? id);
  const decide = async (id: string, accepter: boolean) => {
    try {
      const r = await api(`/api/requests/${id}/decide`, { body: { accepter, reponse: reponse[id] ?? "" } });
      toast(`Demande ${r.statut}`);
      pending.reload();
      all.reload();
    } catch (e: any) { toast(e.message, "err"); }
  };
  return (
    <div className="p-8 max-w-[1100px] mx-auto">
      <PageHeader title="Demandes" subtitle="Les demandes sans réponse sont escaladées automatiquement au niveau supérieur. En tant que Propriétaire, vous pouvez décider de n'importe laquelle."
        actions={<Button onClick={async () => { const r = await api("/api/requests/escalate", { body: {} }); toast(`${r.length} demande(s) escaladée(s)`); pending.reload(); }}>Escalader les retards</Button>} />
      <h2 className="text-sm font-semibold mb-3">En attente ({pending.data?.length ?? 0})</h2>
      {!pending.data ? <Spinner /> : !pending.data.length ? <Card><Empty icon={<Inbox size={22} />} title="Aucune demande en attente" /></Card> : (
        <div className="space-y-3 mb-10">
          {pending.data.map((r) => (
            <Card key={r.id} className="p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2"><span className="font-medium">{r.sujet}</span><Badge tone="violet">{r.type}</Badge><Badge tone={STATUT_TONE[r.statut]} dot>{r.statut}</Badge></div>
                  <div className="text-xs text-ink-subtle mt-1">{name(r.de)} → {name(r.a)} · {dateFr(r.cree_le)} {r.escalades ? `· escaladée ${r.escalades}×` : ""} · coût {eur(r.cout_eur)}</div>
                </div>
              </div>
              <div className="grid md:grid-cols-2 gap-3 mt-3 text-sm">
                <div><div className="text-xs text-ink-muted mb-0.5">Justification</div>{r.justification}</div>
                <div><div className="text-xs text-ink-muted mb-0.5">Gain attendu</div>{r.gain_attendu || "—"}</div>
              </div>
              {r.reponse && <div className="text-xs text-ink-muted mt-2 italic">{r.reponse}</div>}
              <div className="flex flex-wrap gap-2 mt-4">
                <Input className="flex-1 min-w-[200px]" placeholder="Réponse (optionnel)" value={reponse[r.id] ?? ""} onChange={(e) => setReponse({ ...reponse, [r.id]: e.target.value })} />
                <Button variant="primary" onClick={() => decide(r.id, true)}><Check size={14} />Accepter</Button>
                <Button variant="ghost" onClick={() => decide(r.id, false)}><X size={14} />Refuser</Button>
              </div>
            </Card>
          ))}
        </div>
      )}
      <h2 className="text-sm font-semibold mb-3">Historique</h2>
      <Card className="overflow-hidden">
        {!all.data?.length ? <Empty title="Aucune demande" /> : (
          <table className="w-full text-xs">
            <thead><tr className="border-b border-line text-ink-subtle">{["Date", "De", "À", "Type", "Sujet", "Statut"].map((h) => <th key={h} className="text-left py-2.5 px-4 font-semibold uppercase tracking-wider text-[10px]">{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-line">
              {all.data.map((r) => (
                <tr key={r.id} className="hover:bg-bg-muted/60"><td className="py-2 px-4 whitespace-nowrap text-ink-muted">{dateFr(r.cree_le)}</td><td className="py-2 px-4">{name(r.de)}</td><td className="py-2 px-4">{name(r.a)}</td><td className="py-2 px-4">{r.type}</td><td className="py-2 px-4">{r.sujet}</td><td className="py-2 px-4"><Badge tone={STATUT_TONE[r.statut]}>{r.statut}</Badge></td></tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
