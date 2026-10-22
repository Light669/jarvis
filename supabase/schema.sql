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

-- Inscriptions au programme fondateur (formulaire de la page de vente).
create table if not exists public.leads (
  id          bigint generated always as identity primary key,
  created_at  timestamptz not null default now(),
  first_name  text not null check (char_length(first_name) between 1 and 80),
  email       text not null check (char_length(email) between 3 and 200 and position('@' in email) > 1),
  brand       text check (char_length(brand) <= 120),
  creators    text check (char_length(creators) <= 20),
  tiktok_shop text check (char_length(tiktok_shop) <= 20),
  message     text check (char_length(message) <= 1000)
);
alter table public.leads enable row level security;

-- Comptes autorisés à voir les inscrits dans l’application (onglet « Inscrits »).
create table if not exists public.admins (
  email text primary key
);
alter table public.admins enable row level security;

drop policy if exists "Formulaire public" on public.leads;
drop policy if exists "Les admins lisent les inscrits" on public.leads;
drop policy if exists "Voir son statut admin" on public.admins;

-- Tout le monde peut s’inscrire, personne ne peut lire la liste sauf les admins.
create policy "Formulaire public" on public.leads
  for insert to anon, authenticated with check (true);
create policy "Les admins lisent les inscrits" on public.leads
  for select to authenticated
  using (exists (select 1 from public.admins a where a.email = auth.jwt() ->> 'email'));
create policy "Voir son statut admin" on public.admins
  for select to authenticated using (email = auth.jwt() ->> 'email');

-- À faire une fois, avec TON adresse e-mail (celle de ta connexion à Créapilot) :
-- insert into public.admins (email) values ('ton.adresse@exemple.fr') on conflict do nothing;
