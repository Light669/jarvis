-- Créapilot : stockage des données de chaque compte.
-- À coller dans Supabase > SQL Editor, puis « Run ».

create table if not exists public.app_state (
  user_id    uuid primary key references auth.users (id) on delete cascade,
  data       jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);

-- Chaque utilisateur ne peut lire et modifier que ses propres données.
alter table public.app_state enable row level security;

drop policy if exists "Lire ses données" on public.app_state;
drop policy if exists "Créer ses données" on public.app_state;
drop policy if exists "Modifier ses données" on public.app_state;
drop policy if exists "Supprimer ses données" on public.app_state;

create policy "Lire ses données" on public.app_state
  for select using (auth.uid() = user_id);
create policy "Créer ses données" on public.app_state
  for insert with check (auth.uid() = user_id);
create policy "Modifier ses données" on public.app_state
  for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "Supprimer ses données" on public.app_state
  for delete using (auth.uid() = user_id);

-- Compteur d’utilisation de la rédaction par IA (limite quotidienne par compte).
-- Seule la fonction serveur (clé service_role) y accède : aucune règle d’accès pour les utilisateurs.
create table if not exists public.ai_usage (
  user_id uuid not null references auth.users (id) on delete cascade,
  day     date not null,
  count   integer not null default 0,
  primary key (user_id, day)
);
alter table public.ai_usage enable row level security;
