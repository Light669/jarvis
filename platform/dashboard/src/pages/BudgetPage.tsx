import { AlertTriangle, Lock } from "lucide-react";
import { useState } from "react";
import { Button, Card, Empty, Field, Gauge, Input, PageHeader, Spinner, Stat } from "../components/ui";
import { api, eur } from "../lib/api";
import { useResource, useStore } from "../lib/store";

export function BudgetPage() {
  const { toast } = useStore();
  const b = useResource<any>("/api/budget", [], (e) => e.type === "budget");
  const [form, setForm] = useState({ montant: "", description: "", kind: "expense" as "expense" | "revenue" });
  if (!b.data) return <Spinner />;
  const d = b.data;
  const ratio = d.ratio;
  return (
    <div className="p-8 max-w-[1200px] mx-auto">
      <PageHeader title="Budget" subtitle={`Plafond dur de ${eur(d.plafond_eur, 0)} par mois. Alerte à ${Math.round(d.alerte_ratio * 100)} %, blocage automatique à 100 %.`} />
      {d.bloque && (
        <Card className="p-4 mb-4 border-red-500/40 bg-red-500/5 flex items-center gap-3 text-sm text-red-300">
          <Lock size={16} /> Plafond atteint : toute dépense payante est bloquée jusqu'au mois prochain (les modèles gratuits restent disponibles).
        </Card>
      )}
      {!d.bloque && ratio >= d.alerte_ratio && (
        <Card className="p-4 mb-4 border-amber-400/40 bg-amber-400/5 flex items-center gap-3 text-sm text-amber-200">
          <AlertTriangle size={16} /> {Math.round(ratio * 100)} % du budget mensuel consommé.
        </Card>
      )}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3 mb-6">
        <Card className="p-4 md:col-span-2">
          <div className="text-xs font-medium text-ink-muted">Dépensé ce mois</div>
          <div className="flex items-baseline gap-2 mt-1">
            <span className="text-3xl font-semibold tabular-nums" data-testid="budget-spent">{eur(d.depense_eur)}</span>
            <span className="text-sm text-ink-subtle">/ {eur(d.plafond_eur, 0)}</span>
          </div>
          <div className="relative mt-4">
            <Gauge ratio={ratio} alert={d.alerte_ratio} className="h-2.5" />
            <div className="absolute -top-1 h-4.5 w-px bg-amber-300/70" style={{ left: `${d.alerte_ratio * 100}%`, height: 18 }} title="Seuil d'alerte" />
          </div>
          <div className="flex justify-between text-[11px] text-ink-subtle mt-1.5"><span>0 €</span><span>alerte {Math.round(d.alerte_ratio * 100)} %</span><span>{eur(d.plafond_eur, 0)}</span></div>
        </Card>
        <Stat label="Reste disponible" value={eur(Math.max(0, d.plafond_eur - d.depense_eur))} tone={ratio >= 1 ? "danger" : ratio >= d.alerte_ratio ? "warn" : undefined} />
        <Stat label="Revenus du mois" value={eur(d.revenus_eur)} sub="Suivi micro-entreprise" />
      </div>

      <Card className="p-5 mb-6">
        <h2 className="text-sm font-semibold">Dépenses par jour (€)</h2>
        <DailyBars days={d.par_jour} />
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <Card className="overflow-hidden">
          <div className="px-5 py-3 border-b border-line text-sm font-semibold">Par agent</div>
          {!d.par_agent.length ? <Empty title="Aucune dépense" /> : (
            <table className="w-full text-sm">
              <tbody className="divide-y divide-line">
                {d.par_agent.map((r: any) => (
                  <tr key={r.agent_id ?? "x"}><td className="py-2 px-5">{r.nom ?? r.agent_id ?? "Propriétaire"}</td><td className="py-2 px-5 text-right tabular-nums text-ink-muted">{(r.tokens ?? 0).toLocaleString("fr-FR")} tk</td><td className="py-2 px-5 text-right tabular-nums">{eur(r.eur, 4)}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
        <Card className="overflow-hidden">
          <div className="px-5 py-3 border-b border-line text-sm font-semibold">Par modèle</div>
          {!d.par_modele.length ? <Empty title="Aucun appel de modèle" /> : (
            <table className="w-full text-sm">
              <tbody className="divide-y divide-line">
                {d.par_modele.map((r: any) => (
                  <tr key={r.modele}><td className="py-2 px-5 font-mono text-xs">{r.modele}</td><td className="py-2 px-5 text-right tabular-nums text-ink-muted">{r.appels} appels</td><td className="py-2 px-5 text-right tabular-nums">{eur(r.eur, 4)}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      <Card className="p-5">
        <h2 className="text-sm font-semibold mb-3">Saisie manuelle</h2>
        <form className="grid grid-cols-1 md:grid-cols-[160px_140px_1fr_auto] gap-3 items-end" onSubmit={async (e) => {
          e.preventDefault();
          try {
            await api(`/api/budget/${form.kind}`, { body: { montant_eur: Number(form.montant), description: form.description } });
            toast(form.kind === "expense" ? "Dépense enregistrée" : "Revenu enregistré");
            setForm({ ...form, montant: "", description: "" });
            b.reload();
          } catch (err: any) { toast(err.message, "err"); }
        }}>
          <Field label="Type">
            <select className="w-full px-3 py-2 text-sm bg-bg border border-line-strong rounded-md" value={form.kind} onChange={(e) => setForm({ ...form, kind: e.target.value as any })}>
              <option value="expense">Dépense</option><option value="revenue">Revenu</option>
            </select>
          </Field>
          <Field label="Montant (€)"><Input type="number" step="0.01" min="0" required value={form.montant} onChange={(e) => setForm({ ...form, montant: e.target.value })} /></Field>
          <Field label="Description"><Input required value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Abonnement, facture client…" /></Field>
          <Button type="submit" variant="primary">Enregistrer</Button>
        </form>
      </Card>
    </div>
  );
}

function DailyBars({ days }: { days: { jour: string; depenses: number; tokens: number }[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const [asTable, setAsTable] = useState(false);
  if (!days.length) return <Empty title="Pas encore de données ce mois-ci" />;
  const max = Math.max(0.01, ...days.map((d) => d.depenses));
  const W = 760, H = 180, PAD_L = 44, PAD_B = 22, gap = 2;
  const bw = Math.max(4, Math.min(28, (W - PAD_L) / days.length - gap));
  const y = (v: number) => (H - PAD_B) - (v / max) * (H - PAD_B - 10);
  const ticks = [0, max / 2, max];
  return (
    <div>
      <div className="flex justify-end -mt-5 mb-2">
        <button className="text-xs text-ink-subtle hover:text-ink" onClick={() => setAsTable((v) => !v)}>{asTable ? "Voir le graphique" : "Voir le tableau"}</button>
      </div>
      {asTable ? (
        <table className="w-full text-xs"><tbody className="divide-y divide-line">
          {days.map((d) => <tr key={d.jour}><td className="py-1.5">{d.jour}</td><td className="text-right tabular-nums">{eur(d.depenses, 4)}</td><td className="text-right tabular-nums text-ink-muted">{(d.tokens ?? 0).toLocaleString("fr-FR")} tk</td></tr>)}
        </tbody></table>
      ) : (
        <div className="relative">
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-48" role="img" aria-label="Dépenses par jour">
            {ticks.map((t) => (
              <g key={t}>
                <line x1={PAD_L} x2={W} y1={y(t)} y2={y(t)} stroke="#232327" strokeWidth={1} />
                <text x={PAD_L - 6} y={y(t) + 3} textAnchor="end" fontSize={10} fill="#71717a">{t.toFixed(2)}</text>
              </g>
            ))}
            {days.map((d, i) => {
              const x = PAD_L + 4 + i * (bw + gap);
              const top = y(d.depenses);
              const h = Math.max(0, H - PAD_B - top);
              return (
                <g key={d.jour} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
                  <rect x={x - gap / 2} y={0} width={bw + gap} height={H - PAD_B} fill="transparent" />
                  {h > 0 && <path d={roundedTop(x, top, bw, h, Math.min(4, bw / 2, h))} fill="#818cf8" opacity={hover === null || hover === i ? 1 : 0.45} />}
                  {(i === 0 || i === days.length - 1 || days.length <= 10) && (
                    <text x={x + bw / 2} y={H - 6} textAnchor="middle" fontSize={10} fill="#71717a">{d.jour.slice(8)}</text>
                  )}
                </g>
              );
            })}
          </svg>
          {hover !== null && (
            <div className="absolute pointer-events-none px-2.5 py-1.5 rounded-md bg-bg-raised border border-line-strong text-xs shadow-lg"
              style={{ left: `${((PAD_L + 4 + hover * (bw + gap) + bw / 2) / W) * 100}%`, top: 0, transform: "translateX(-50%)" }}>
              <div className="text-ink-muted">{days[hover].jour}</div>
              <div className="font-semibold tabular-nums">{eur(days[hover].depenses, 4)}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

const roundedTop = (x: number, y: number, w: number, h: number, r: number) =>
  `M${x},${y + h} V${y + r} Q${x},${y} ${x + r},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${y + h} Z`;
