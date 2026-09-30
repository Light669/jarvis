import { Bell, CheckCheck } from "lucide-react";
import { Badge, Button, Card, Empty, PageHeader, Spinner, STATUT_TONE } from "../components/ui";
import { api, dateFr } from "../lib/api";
import { useResource, useStore } from "../lib/store";

export function AlertsPage() {
  const { refresh } = useStore();
  const alerts = useResource<any[]>("/api/alerts", [], (e) => e.type === "alert");
  const markAll = async () => {
    await Promise.all((alerts.data ?? []).filter((a) => !a.lue).map((a) => api(`/api/alerts/${a.id}/read`, { body: {} })));
    alerts.reload();
    refresh();
  };
  return (
    <div className="p-8 max-w-[1000px] mx-auto">
      <PageHeader title="Alertes" subtitle="Erreurs graves, budget, demandes en retard, actions interdites, intégrité des logs, boucles de messages." actions={<Button onClick={markAll}><CheckCheck size={14} />Tout marquer comme lu</Button>} />
      <Card className="overflow-hidden">
        {!alerts.data ? <Spinner /> : !alerts.data.length ? <Empty icon={<Bell size={22} />} title="Aucune alerte" /> : (
          <ul className="divide-y divide-line">
            {alerts.data.map((a) => (
              <li key={a.id} className={`flex items-start gap-3 px-5 py-3 ${a.lue ? "opacity-60" : ""}`}>
                <Badge tone={STATUT_TONE[a.gravite]} dot>{a.gravite}</Badge>
                <div className="flex-1 min-w-0">
                  <div className="text-sm">{a.message}</div>
                  <div className="text-xs text-ink-subtle mt-0.5">{a.type} · {dateFr(a.horodatage)}{a.agent_id ? ` · ${a.agent_id}` : ""}</div>
                </div>
                {!a.lue && <Button size="sm" variant="ghost" onClick={async () => { await api(`/api/alerts/${a.id}/read`, { body: {} }); alerts.reload(); refresh(); }}>Lu</Button>}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
