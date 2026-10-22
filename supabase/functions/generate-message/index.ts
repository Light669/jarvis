// Créapilot : rédige un message sur mesure pour un créateur TikTok avec Claude.
// La clé ANTHROPIC_API_KEY reste côté serveur (secret de la fonction), jamais dans le navigateur.
// Déploiement : voir SUPABASE.md, section « Rédaction par IA ».
import Anthropic from "npm:@anthropic-ai/sdk";
import { createClient } from "npm:@supabase/supabase-js@2.45.4";

const MODEL = "claude-opus-5-5";
const DAILY_LIMIT = Number(Deno.env.get("AI_DAILY_LIMIT") ?? "60"); // messages par compte et par jour

const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

const KINDS: Record<string, string> = {
  invite: "un premier message d’invitation : proposer d’envoyer le produit gratuitement et expliquer la commission d’affiliation TikTok Shop",
  relance: "une relance courte et sympathique, sans pression, adaptée à l’étape où en est le créateur",
  brief: "un brief vidéo clair : accroche des 3 premières secondes, ce qu’il faut montrer, l’appel à l’action vers la vitrine TikTok Shop, format conseillé",
  merci: "un remerciement après la vidéo, qui cite les ventes générées si elles existent et propose de continuer la collaboration",
};

const STAGES: Record<string, string> = {
  trouve: "repéré, pas encore contacté",
  contacte: "contacté, pas encore de réponse ou en discussion",
  echantillon: "échantillon envoyé, vidéo pas encore publiée",
  video: "vidéo publiée",
  vend: "génère des ventes",
};

const SYSTEM = `Tu rédiges des messages pour une marque française qui travaille avec des créateurs TikTok affiliés (TikTok Shop).
Le message sera copié tel quel dans les messages privés TikTok ou Instagram du créateur.

Règles :
- Écris en français, en tutoyant le créateur, sur un ton chaleureux et naturel, comme une vraie personne de la marque.
- Reste court : 60 à 120 mots pour une invitation, une relance ou un remerciement ; un brief peut aller jusqu’à 180 mots et utiliser des puces.
- Personnalise avec les informations fournies (catégorie, produit, notes, ventes). N’invente jamais de chiffres, de faits sur le créateur ou de vidéos qu’il aurait faites.
- Quand une information manque (nom de la marque, prénom), écris le texte sans elle plutôt que de laisser un crochet.
- Pas d’objet d’e-mail, pas de guillemets autour du message, pas d’explication : renvoie uniquement le message.`;

function json(status: number, body: unknown) {
  return new Response(JSON.stringify(body), { status, headers: { ...CORS, "Content-Type": "application/json" } });
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json(405, { error: "Méthode non autorisée." });

  // 1. Vérifier que l'appel vient d'un utilisateur connecté
  const admin = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
  const token = (req.headers.get("Authorization") ?? "").replace(/^Bearer\s+/i, "");
  const { data: userData, error: userError } = await admin.auth.getUser(token);
  if (userError || !userData?.user) return json(401, { error: "Connecte-toi pour utiliser la rédaction par IA." });
  const userId = userData.user.id;

  // 2. Limite quotidienne par compte, pour maîtriser les coûts
  const day = new Date().toISOString().slice(0, 10);
  const { data: usage } = await admin.from("ai_usage").select("count").eq("user_id", userId).eq("day", day).maybeSingle();
  const used = usage?.count ?? 0;
  if (used >= DAILY_LIMIT) return json(429, { error: `Tu as atteint la limite de ${DAILY_LIMIT} messages rédigés par l’IA aujourd’hui. Elle se réinitialise demain.` });

  // 3. Lire la demande
  let body: any;
  try { body = await req.json(); } catch { return json(400, { error: "Demande illisible." }); }
  const kind = KINDS[body?.kind] ? body.kind : "invite";
  const c = body?.creator ?? {};
  const details = {
    type_de_message: KINDS[kind],
    createur: {
      pseudo: String(c.handle ?? "").slice(0, 60),
      categorie: String(c.cat ?? "").slice(0, 40),
      abonnes: Number(c.followers) || null,
      etape: STAGES[c.stage] ?? null,
      jours_depuis_derniere_action: Number(c.daysSince) || 0,
      notes: String(c.notes ?? "").slice(0, 800),
      ventes_generees_euros: Number(c.sales) || 0,
    },
    offre: {
      produit: String(c.product ?? "").slice(0, 120),
      commission_pourcent: Number(c.commission) || null,
    },
    expediteur: {
      marque: String(body?.brand ?? "").slice(0, 80),
      prenom: String(body?.name ?? "").slice(0, 40),
    },
    consigne_supplementaire: String(body?.instruction ?? "").slice(0, 300),
  };

  // 4. Appeler Claude (repli automatique sur un autre modèle si la demande est refusée par un filtre de sécurité)
  const client = new Anthropic({ apiKey: Deno.env.get("ANTHROPIC_API_KEY") });
  try {
    const response = await client.beta.messages.create({
      model: MODEL,
      max_tokens: 16000,
      output_config: { effort: "low" },
      betas: ["server-side-fallback-2026-07-01"],
      fallbacks: "default",
      system: SYSTEM,
      messages: [{
        role: "user",
        content: `Rédige le message à partir de ces informations :\n\n${JSON.stringify(details, null, 2)}`,
      }],
    } as any);

    if (response.stop_reason === "refusal") {
      return json(422, { error: "L’IA n’a pas pu rédiger ce message. Reformule la consigne ou les notes, puis réessaie." });
    }
    const text = response.content
      .filter((b: any) => b.type === "text")
      .map((b: any) => b.text)
      .join("")
      .trim();
    if (!text) return json(502, { error: "L’IA n’a renvoyé aucun texte. Réessaie." });

    await admin.from("ai_usage").upsert({ user_id: userId, day, count: used + 1 });
    return json(200, { text, remaining: Math.max(0, DAILY_LIMIT - used - 1) });
  } catch (err) {
    if (err instanceof Anthropic.RateLimitError) return json(429, { error: "L’IA est très sollicitée en ce moment. Réessaie dans une minute." });
    if (err instanceof Anthropic.APIConnectionError) return json(503, { error: "Impossible de joindre l’IA pour le moment. Réessaie dans quelques instants." });
    if (err instanceof Anthropic.AuthenticationError) return json(500, { error: "La clé d’API de l’IA est invalide. Vérifie le secret ANTHROPIC_API_KEY." });
    if (err instanceof Anthropic.APIError) return json(502, { error: `L’IA a renvoyé une erreur (${err.status}). Réessaie plus tard.` });
    return json(500, { error: "Erreur inattendue pendant la rédaction." });
  }
});
