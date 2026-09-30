import dagre from "@dagrejs/dagre";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  ViewportPortal,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { AnimatePresence, motion } from "framer-motion";
import { Cpu, Snowflake } from "lucide-react";
import { memo, useEffect, useMemo, useRef, useState } from "react";
import { eur, type Agent } from "../lib/api";
import { useStore, type LiveEvent } from "../lib/store";
import { Gauge, LevelBadge, cx } from "./ui";

const W = 236;
const H = 118;

type AgentData = { agent: Agent; flash: boolean; fading: boolean; isNew: boolean };
type TeamData = { label: string; w: number; h: number };

const ACTIVITY_LABEL: Record<string, string> = {
  travail: "Travaille",
  attente: "En attente",
  erreur: "Erreur",
  gele: "Gelé",
  inactif: "Inactif",
};

const AgentNode = memo(({ data, selected }: NodeProps<Node<AgentData>>) => {
  const a = data.agent;
  const budget = a.budget_jour_eur > 0 ? (a.jour_eur ?? 0) / a.budget_jour_eur : 0;
  const act = a.statut === "pause" ? "inactif" : a.activite;
  return (
    <motion.div
      initial={data.isNew ? { scale: 0.4, opacity: 0 } : false}
      animate={{ scale: 1, opacity: data.fading ? 0 : 1 }}
      transition={data.fading ? { duration: 0.9 } : { type: "spring", stiffness: 260, damping: 20 }}
      className={cx(
        "agent-node relative bg-bg-raised border border-line-strong px-3.5 py-3",
        a.niveau === "chef" ? "rounded-2xl" : a.niveau === "responsable" ? "rounded-xl" : "rounded-lg",
        `st-${act}`,
        a.statut === "pause" && "is-pause",
        a.statut === "brouillon" && "is-draft",
        data.flash && "flash-refus",
        selected && "ring-2 ring-accent",
      )}
      style={{ width: W }}
      data-testid={`node-${a.id}`}
    >
      <Handle type="target" position={Position.Top} className="!opacity-0" />
      <div className="text-sm font-semibold truncate" title={a.nom}>{a.nom}</div>
      <div className="flex items-center justify-between gap-2 mt-1">
        <span className="text-[11px] text-ink-subtle font-mono truncate">{a.id} · v{a.version}</span>
        <LevelBadge level={a.niveau} short />
      </div>
      <div className="flex items-center gap-1.5 mt-2 text-[11px] text-ink-muted min-w-0">
        {act === "gele" ? <Snowflake size={11} className="text-sky-300 shrink-0" /> : <Cpu size={11} className="shrink-0" />}
        <span className={cx("shrink-0", act === "travail" && "text-indigo-300", act === "attente" && "text-amber-300", act === "erreur" && "text-red-400")}>
          {a.statut === "pause" ? "En pause" : a.statut === "brouillon" ? "Brouillon" : ACTIVITY_LABEL[act] ?? act}
        </span>
        {a.activite_detail && <span className="truncate text-ink-subtle">· {a.activite_detail}</span>}
      </div>
      <div className="flex items-center gap-2 mt-2">
        <Gauge ratio={budget} className="flex-1" />
        <span className="text-[10px] tabular-nums text-ink-subtle">
          {eur(a.jour_eur, 2)}/{eur(a.budget_jour_eur, 2)}
        </span>
      </div>
      <Handle type="source" position={Position.Bottom} className="!opacity-0" />
    </motion.div>
  );
});

const TeamNode = memo(({ data }: NodeProps<Node<TeamData>>) => (
  <div className="rounded-2xl border border-dashed border-indigo-400/20 bg-indigo-400/[0.03]" style={{ width: data.w, height: data.h }}>
    <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-indigo-300/60">Équipe {data.label}</div>
  </div>
));

const nodeTypes = { agent: AgentNode, team: TeamNode };

function layout(agents: Agent[], groupTeams: boolean) {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "TB", nodesep: 36, ranksep: 90, marginx: 20, marginy: 20 });
  g.setDefaultEdgeLabel(() => ({}));
  const ids = new Set(agents.map((a) => a.id));
  agents.forEach((a) => g.setNode(a.id, { width: W, height: H }));
  agents.forEach((a) => a.parent_id && ids.has(a.parent_id) && g.setEdge(a.parent_id, a.id));
  dagre.layout(g);
  const pos: Record<string, { x: number; y: number }> = {};
  agents.forEach((a) => {
    const n = g.node(a.id);
    pos[a.id] = { x: n.x - W / 2, y: n.y - H / 2 };
  });
  const teams: Node<TeamData>[] = [];
  if (groupTeams) {
    agents
      .filter((a) => a.niveau === "responsable")
      .forEach((r) => {
        const members = agents.filter((a) => a.id === r.id || a.equipe === r.id);
        const xs = members.map((m) => pos[m.id].x);
        const ys = members.map((m) => pos[m.id].y);
        const pad = 18;
        const x = Math.min(...xs) - pad;
        const y = Math.min(...ys) - pad - 16;
        teams.push({
          id: `team-${r.id}`,
          type: "team",
          position: { x, y },
          data: { label: r.nom, w: Math.max(...xs) + W + pad - x, h: Math.max(...ys) + H + pad - y },
          draggable: false,
          selectable: false,
          zIndex: -1,
        });
      });
  }
  return { pos, teams };
}

type Particle = { id: number; from: string; to: string; color: string };

const COLORS = { message: "#818cf8", demande: "#fbbf24", refus: "#ef4444", validation: "#34d399" };

function Particles({ particles }: { particles: Particle[] }) {
  const rf = useReactFlow();
  const center = (id: string) => {
    const n = rf.getInternalNode(id);
    if (!n) return null;
    const p = n.internals.positionAbsolute;
    return { x: p.x + (n.measured.width ?? W) / 2, y: p.y + (n.measured.height ?? H) / 2 };
  };
  return (
    <ViewportPortal>
      <svg style={{ position: "absolute", left: 0, top: 0, overflow: "visible", pointerEvents: "none" }} width={1} height={1}>
        <AnimatePresence>
          {particles.map((pt) => {
            const a = center(pt.from);
            const b = center(pt.to);
            if (!a || !b) return null;
            return (
              <g key={pt.id}>
                <motion.line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={pt.color} strokeWidth={1.5} strokeOpacity={0.25}
                  initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.9 }} />
                {[0, 0.12, 0.24].map((delay) => (
                  <motion.circle key={delay} r={delay === 0 ? 5 : 3} fill={pt.color}
                    style={{ filter: `drop-shadow(0 0 6px ${pt.color})` }}
                    initial={{ cx: a.x, cy: a.y, opacity: 0 }}
                    animate={{ cx: b.x, cy: b.y, opacity: [0, 1, 1, 0] }}
                    transition={{ duration: 1.2, delay, ease: "easeInOut" }} />
                ))}
              </g>
            );
          })}
        </AnimatePresence>
      </svg>
    </ViewportPortal>
  );
}

function MapInner({ selected, onSelect, groupTeams, showArchived }: { selected: string | null; onSelect: (id: string | null) => void; groupTeams: boolean; showArchived: boolean }) {
  const { overview, subscribe, reducedMotion } = useStore();
  const [particles, setParticles] = useState<Particle[]>([]);
  const [flash, setFlash] = useState<Set<string>>(new Set());
  const [fading, setFading] = useState<Set<string>>(new Set());
  const known = useRef<Set<string> | null>(null);
  const prevStatus = useRef<Record<string, string>>({});
  const seq = useRef(0);
  const rf = useReactFlow();

  const agents = overview?.agents ?? [];
  const visible = agents.filter((a) => showArchived || a.statut !== "archive" || fading.has(a.id));

  // animations de création / archivage
  const newIds = useMemo(() => {
    const out = new Set<string>();
    if (known.current) agents.forEach((a) => !known.current!.has(a.id) && out.add(a.id));
    known.current = new Set(agents.map((a) => a.id));
    return out;
  }, [agents]);

  useEffect(() => {
    agents.forEach((a) => {
      const prev = prevStatus.current[a.id];
      if (prev && prev !== "archive" && a.statut === "archive") {
        setFading((f) => new Set(f).add(a.id));
        setTimeout(() => setFading((f) => {
          const n = new Set(f);
          n.delete(a.id);
          return n;
        }), 1000);
      }
      prevStatus.current[a.id] = a.statut;
    });
  }, [agents]);

  useEffect(
    () =>
      subscribe((e: LiveEvent) => {
        if (reducedMotion) return;
        const add = (from: string, to: string, color: string) => {
          const id = ++seq.current;
          setParticles((p) => [...p.slice(-30), { id, from, to, color }]);
          setTimeout(() => setParticles((p) => p.filter((x) => x.id !== id)), 1700);
        };
        if (e.type === "message") add(e.de, e.a, e.kind === "demande" ? COLORS.demande : COLORS.message);
        if (e.type === "request" && e.statut === "refusee") add(e.de, e.a, COLORS.refus);
        if (e.type === "request" && e.statut === "acceptee") add(e.de, e.a, COLORS.validation);
        if (e.type === "log" && e.entry?.type_evenement === "permission_refusee" && e.entry.agent_id) {
          const id = e.entry.agent_id;
          setFlash((f) => new Set(f).add(id));
          const parent = agents.find((a) => a.id === id)?.parent_id;
          if (parent) add(id, parent, COLORS.refus);
          setTimeout(() => setFlash((f) => {
            const n = new Set(f);
            n.delete(id);
            return n;
          }), 900);
        }
      }),
    [subscribe, reducedMotion, agents],
  );

  const structureKey = visible.map((a) => `${a.id}:${a.parent_id}:${a.niveau}`).join("|") + groupTeams;
  const { pos, teams } = useMemo(() => layout(visible, groupTeams), [structureKey]); // eslint-disable-line

  const nodes: Node[] = useMemo(
    () => [
      ...teams,
      ...visible.map((a) => ({
        id: a.id,
        type: "agent",
        position: pos[a.id] ?? { x: 0, y: 0 },
        data: { agent: a, flash: flash.has(a.id), fading: fading.has(a.id), isNew: newIds.has(a.id) },
        selected: a.id === selected,
      })),
    ],
    [visible, pos, teams, flash, fading, newIds, selected],
  );

  const ids = new Set(visible.map((a) => a.id));
  const edges: Edge[] = [
    ...visible
      .filter((a) => a.parent_id && ids.has(a.parent_id))
      .map((a) => ({ id: `h-${a.id}`, source: a.parent_id!, target: a.id, type: "smoothstep" })),
    ...(overview?.pairs ?? [])
      .filter(([x, y]) => ids.has(x) && ids.has(y))
      .map(([x, y]) => ({ id: `p-${x}-${y}`, source: x, target: y, className: "peer", type: "straight" })),
  ];

  useEffect(() => {
    const t = setTimeout(() => rf.fitView({ padding: 0.2, duration: reducedMotion ? 0 : 400 }), 60);
    return () => clearTimeout(t);
  }, [structureKey]); // eslint-disable-line

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      nodeTypes={nodeTypes}
      onNodeClick={(_, n) => n.type === "agent" && onSelect(n.id)}
      onPaneClick={() => onSelect(null)}
      nodesDraggable={false}
      nodesConnectable={false}
      minZoom={0.15}
      maxZoom={1.8}
      fitView
      proOptions={{ hideAttribution: true }}
    >
      <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="#27272a" />
      <Controls showInteractive={false} position="bottom-left" />
      <MiniMap
        pannable
        zoomable
        position="bottom-right"
        nodeColor={(n) => {
          const a = (n.data as AgentData)?.agent;
          if (!a) return "transparent";
          return a.activite === "erreur" ? "#ef4444" : a.activite === "attente" ? "#fbbf24" : a.activite === "travail" ? "#818cf8" : "#71717a";
        }}
        maskColor="rgba(10,10,11,0.55)"
        nodeBorderRadius={6}
      />
      <Particles particles={particles} />
    </ReactFlow>
  );
}

export function AgentMap(props: { selected: string | null; onSelect: (id: string | null) => void; groupTeams: boolean; showArchived: boolean }) {
  return (
    <ReactFlowProvider>
      <MapInner {...props} />
    </ReactFlowProvider>
  );
}

export const PARTICLE_COLORS = COLORS;
