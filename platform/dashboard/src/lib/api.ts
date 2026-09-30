// Client de l'API locale Orchestra. Le jeton est lu dans le fragment d'URL (#token=…) puis gardé
// en sessionStorage : il n'est jamais envoyé ailleurs qu'à 127.0.0.1.

const KEY = "orchestra-token";

export function captureToken(): void {
  const m = window.location.hash.match(/token=([A-Za-z0-9._-]+)/);
  if (m) {
    sessionStorage.setItem(KEY, m[1]);
    history.replaceState(null, "", window.location.pathname);
  }
}

export const getToken = () => sessionStorage.getItem(KEY) ?? "";
export const setToken = (t: string) => sessionStorage.setItem(KEY, t.trim());
export const clearToken = () => sessionStorage.removeItem(KEY);

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function api<T = any>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<T> {
  const res = await fetch(path, {
    method: opts.method ?? (opts.body !== undefined ? "POST" : "GET"),
    headers: { Authorization: `Bearer ${getToken()}`, "Content-Type": "application/json" },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      msg = (await res.json()).detail ?? msg;
    } catch {
      /* corps non JSON */
    }
    if (typeof msg !== "string") msg = JSON.stringify(msg);
    throw new ApiError(res.status, msg);
  }
  return res.json();
}

export async function download(path: string, filename: string): Promise<void> {
  const res = await fetch(path, { headers: { Authorization: `Bearer ${getToken()}` } });
  if (!res.ok) throw new ApiError(res.status, res.statusText);
  const url = URL.createObjectURL(await res.blob());
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  a.click();
  URL.revokeObjectURL(url);
}

export const qs = (params: Record<string, string | number | boolean | undefined | null>) => {
  const u = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v !== undefined && v !== null && v !== "" && u.set(k, String(v)));
  const s = u.toString();
  return s ? `?${s}` : "";
};

// ---------------------------------------------------------------- types
export type Level = "chef" | "responsable" | "salarie" | "apprenti";
export type Status = "brouillon" | "actif" | "pause" | "archive";

export interface Agent {
  id: string;
  nom: string;
  niveau: Level;
  parent_id: string | null;
  statut: Status;
  modele: string;
  budget_jour_eur: number;
  budget_mois_eur: number | null;
  outils: string[];
  skills: string[];
  kpi: string[];
  role: string;
  contexte: string;
  instructions: string;
  objectif: string;
  interdits: string;
  journal: string;
  cree_par: string;
  cree_le: string;
  modifie_le: string;
  version: number;
  vault_path: string;
  archive_raison: string | null;
  activite: "inactif" | "travail" | "attente" | "erreur" | "gele";
  activite_detail: string;
  jour_eur?: number;
  equipe?: string | null;
}

export interface Overview {
  agents: Agent[];
  pairs: [string, string][];
  emergency: boolean;
  budget: { plafond_eur: number; depense_eur: number; ratio: number; alerte_ratio: number; bloque: boolean };
  alertes_non_lues: number;
  demandes_en_attente: number;
}

export const LEVELS: Level[] = ["chef", "responsable", "salarie", "apprenti"];
export const LEVEL_LABEL: Record<Level, string> = {
  chef: "Chef d'Orchestre",
  responsable: "Responsable",
  salarie: "Salarié",
  apprenti: "Apprenti",
};
export const STATUS_LABEL: Record<Status, string> = { brouillon: "Brouillon", actif: "Actif", pause: "En pause", archive: "Archivé" };

export const eur = (n: number | null | undefined, d = 2) =>
  `${(n ?? 0).toLocaleString("fr-FR", { minimumFractionDigits: d, maximumFractionDigits: d })} €`;
export const dateFr = (iso?: string | null) =>
  iso ? new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "medium" }) : "—";
