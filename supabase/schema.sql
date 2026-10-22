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

-- ============================================================
-- Travail en équipe : un espace partagé par marque
-- ============================================================

create table if not exists public.workspaces (
  id         uuid primary key default gen_random_uuid(),
  name       text not null default 'Mon espace',
  data       jsonb not null default '{}'::jsonb,
  version    bigint not null default 1,
  updated_at timestamptz not null default now(),
  created_by uuid references auth.users (id) on delete set null
);
create table if not exists public.workspace_members (
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  user_id      uuid not null references auth.users (id) on delete cascade,
  email        text not null,
  role         text not null default 'member' check (role in ('owner', 'member')),
  created_at   timestamptz not null default now(),
  primary key (workspace_id, user_id)
);
create table if not exists public.workspace_invites (
  workspace_id uuid not null references public.workspaces (id) on delete cascade,
  email        text not null,
  invited_by   uuid references auth.users (id) on delete set null,
  created_at   timestamptz not null default now(),
  primary key (workspace_id, email)
);
alter table public.workspaces enable row level security;
alter table public.workspace_members enable row level security;
alter table public.workspace_invites enable row level security;

create or replace function public.is_member(ws uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.workspace_members m where m.workspace_id = ws and m.user_id = auth.uid());
$$;
create or replace function public.is_owner(ws uuid) returns boolean
language sql stable security definer set search_path = public as $$
  select exists (select 1 from public.workspace_members m where m.workspace_id = ws and m.user_id = auth.uid() and m.role = 'owner');
$$;

drop policy if exists "Membres : lire l'espace" on public.workspaces;
drop policy if exists "Membres : voir l'équipe" on public.workspace_members;
drop policy if exists "Membres : voir les invitations" on public.workspace_invites;
-- Lecture réservée aux membres ; toutes les écritures passent par les fonctions ci-dessous.
create policy "Membres : lire l'espace" on public.workspaces
  for select to authenticated using (public.is_member(id));
create policy "Membres : voir l'équipe" on public.workspace_members
  for select to authenticated using (public.is_member(workspace_id));
create policy "Membres : voir les invitations" on public.workspace_invites
  for select to authenticated using (public.is_member(workspace_id));

-- Crée l'espace d'un nouvel utilisateur (il en devient propriétaire)
create or replace function public.create_workspace(p_name text, p_data jsonb) returns uuid
language plpgsql security definer set search_path = public as $$
declare ws uuid;
begin
  if auth.uid() is null then raise exception 'Connecte-toi d''abord.'; end if;
  insert into public.workspaces (name, data, created_by)
    values (coalesce(nullif(trim(p_name), ''), 'Mon espace'), coalesce(p_data, '{}'::jsonb), auth.uid())
    returning id into ws;
  insert into public.workspace_members (workspace_id, user_id, email, role)
    values (ws, auth.uid(), lower(coalesce(auth.jwt() ->> 'email', '')), 'owner');
  return ws;
end $$;

-- À la connexion : rejoint les espaces où l'adresse e-mail a été invitée
create or replace function public.accept_invites() returns integer
language plpgsql security definer set search_path = public as $$
declare n integer;
begin
  if auth.uid() is null then return 0; end if;
  insert into public.workspace_members (workspace_id, user_id, email, role)
    select i.workspace_id, auth.uid(), lower(auth.jwt() ->> 'email'), 'member'
    from public.workspace_invites i
    where lower(i.email) = lower(auth.jwt() ->> 'email')
  on conflict do nothing;
  get diagnostics n = row_count;
  delete from public.workspace_invites where lower(email) = lower(auth.jwt() ->> 'email');
  return n;
end $$;

create or replace function public.invite_member(ws uuid, p_email text) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not public.is_owner(ws) then raise exception 'Seul le propriétaire de l''espace peut inviter.'; end if;
  if trim(p_email) !~* '^[^@\s]+@[^@\s]+\.[^@\s]+$' then raise exception 'Adresse e-mail invalide.'; end if;
  if exists (select 1 from public.workspace_members where workspace_id = ws and lower(email) = lower(trim(p_email))) then
    raise exception 'Cette personne fait déjà partie de l''espace.';
  end if;
  insert into public.workspace_invites (workspace_id, email, invited_by)
    values (ws, lower(trim(p_email)), auth.uid()) on conflict do nothing;
end $$;

create or replace function public.cancel_invite(ws uuid, p_email text) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not public.is_owner(ws) then raise exception 'Seul le propriétaire de l''espace peut annuler une invitation.'; end if;
  delete from public.workspace_invites where workspace_id = ws and email = lower(trim(p_email));
end $$;

create or replace function public.remove_member(ws uuid, p_user uuid) returns void
language plpgsql security definer set search_path = public as $$
begin
  if not public.is_owner(ws) then raise exception 'Seul le propriétaire de l''espace peut retirer un membre.'; end if;
  if p_user = auth.uid() then raise exception 'Tu ne peux pas te retirer toi-même.'; end if;
  delete from public.workspace_members where workspace_id = ws and user_id = p_user;
end $$;

-- Enregistre l'espace seulement s'il n'a pas changé depuis la dernière lecture ;
-- sinon renvoie la version actuelle pour que l'application fusionne les changements.
create or replace function public.save_workspace(ws uuid, p_data jsonb, p_base bigint)
returns table (saved boolean, new_version bigint, current_data jsonb)
language plpgsql security definer set search_path = public as $$
declare v bigint;
begin
  if not public.is_member(ws) then raise exception 'Accès refusé.'; end if;
  update public.workspaces w
     set data = p_data, version = w.version + 1, updated_at = now(),
         name = coalesce(nullif(trim(p_data ->> 'brand'), ''), w.name)
   where w.id = ws and w.version = p_base
   returning w.version into v;
  if v is not null then
    return query select true, v, null::jsonb;
  else
    return query select false, w.version, w.data from public.workspaces w where w.id = ws;
  end if;
end $$;
