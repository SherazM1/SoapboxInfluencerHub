do $$
begin
    if exists (
        select 1 from campaign_ops_users
        where lower(display_name) = 'taylor'
          and id <> '22222222-2222-4222-8222-222222222222'::uuid
          and is_active = true
    ) then
        raise exception 'Active Taylor identity conflicts with the existing T user; resolve before applying roster migration.';
    end if;
    if exists (
        select 1 from campaign_ops_users
        where lower(display_name) = 'lauren'
          and id <> '33333333-3333-4333-8333-333333333333'::uuid
          and is_active = true
    ) then
        raise exception 'Active Lauren identity conflicts with the existing L user; resolve before applying roster migration.';
    end if;
    if exists (
        select 1 from campaign_ops_users
        where lower(display_name) = 't'
          and id <> '22222222-2222-4222-8222-222222222222'::uuid
          and is_active = true
    ) then
        raise exception 'An additional active T identity exists; resolve before applying roster migration.';
    end if;
    if exists (
        select 1 from campaign_ops_users
        where lower(display_name) = 'l'
          and id <> '33333333-3333-4333-8333-333333333333'::uuid
          and is_active = true
    ) then
        raise exception 'An additional active L identity exists; resolve before applying roster migration.';
    end if;
end;
$$;

update campaign_ops_users
set display_name = 'Taylor', role = 'team_member', is_active = true
where id = '22222222-2222-4222-8222-222222222222'::uuid;

update campaign_ops_users
set display_name = 'Lauren', role = 'team_member', is_active = true
where id = '33333333-3333-4333-8333-333333333333'::uuid;

insert into campaign_ops_users (id, display_name, role, is_active)
select seed.id, seed.display_name, seed.role, true
from (values
    ('11111111-1111-4111-8111-111111111111'::uuid, 'Bailey', 'administrator'),
    (gen_random_uuid(), 'Jordon', 'administrator'),
    (gen_random_uuid(), 'Taylor', 'team_member'),
    (gen_random_uuid(), 'Lauren', 'team_member'),
    (gen_random_uuid(), 'Ava', 'team_member'),
    (gen_random_uuid(), 'Allyn', 'team_member'),
    (gen_random_uuid(), 'Maren', 'team_member'),
    (gen_random_uuid(), 'Carly', 'team_member'),
    (gen_random_uuid(), 'Emma', 'team_member'),
    (gen_random_uuid(), 'Kate', 'team_member'),
    (gen_random_uuid(), 'Chloe', 'team_member')
) as seed(id, display_name, role)
where not exists (
    select 1 from campaign_ops_users existing
    where lower(existing.display_name) = lower(seed.display_name)
      and existing.is_active = true
)
on conflict (id) do update
set display_name = excluded.display_name,
    role = excluded.role,
    is_active = true,
    updated_at = now();

update campaign_ops_users u
set role = seed.role, updated_at = now()
from (values
        ('Bailey', 'administrator'),
        ('Jordon', 'administrator'),
        ('Taylor', 'team_member'),
        ('Lauren', 'team_member'),
        ('Ava', 'team_member'),
        ('Allyn', 'team_member'),
        ('Maren', 'team_member'),
        ('Carly', 'team_member'),
        ('Emma', 'team_member'),
        ('Kate', 'team_member'),
        ('Chloe', 'team_member')
) as seed(display_name, role)
where lower(u.display_name) = lower(seed.display_name)
    and u.is_active = true;

create table if not exists campaign_ops_user_workflow_roles (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references campaign_ops_users(id),
    workflow_key text not null,
    workflow_role text not null check (workflow_role in ('lead_owner', 'manager')),
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by uuid null references campaign_ops_users(id),
    updated_by uuid null references campaign_ops_users(id)
);

create unique index if not exists idx_campaign_ops_user_workflow_roles_active_unique
    on campaign_ops_user_workflow_roles (user_id, workflow_key, workflow_role)
    where is_active = true;

create index if not exists idx_campaign_ops_user_workflow_roles_lookup
    on campaign_ops_user_workflow_roles (workflow_key, workflow_role, is_active, user_id);

drop trigger if exists set_campaign_ops_user_workflow_roles_updated_at
    on campaign_ops_user_workflow_roles;
create trigger set_campaign_ops_user_workflow_roles_updated_at
before update on campaign_ops_user_workflow_roles
for each row execute function campaign_ops_set_updated_at();

with roster(display_name, workflow_key, workflow_role) as (
    values
        ('Taylor', 'influencer', 'lead_owner'),
        ('Lauren', 'influencer', 'lead_owner'),
        ('Ava', 'influencer', 'lead_owner'),
        ('Allyn', 'influencer', 'manager'),
        ('Maren', 'influencer', 'manager'),
        ('Carly', 'influencer', 'manager'),
        ('Emma', 'ecommerce', 'lead_owner'),
        ('Kate', 'ecommerce', 'lead_owner'),
        ('Emma', 'ecommerce', 'manager'),
        ('Kate', 'ecommerce', 'manager'),
        ('Chloe', 'retail_media', 'lead_owner'),
        ('Chloe', 'retail_media', 'manager'),
        ('Taylor', 'smm', 'lead_owner'),
        ('Ava', 'smm', 'lead_owner'),
        ('Ava', 'smm', 'manager'),
        ('Maren', 'smm', 'manager')
)
insert into campaign_ops_user_workflow_roles (user_id, workflow_key, workflow_role)
select u.id, roster.workflow_key, roster.workflow_role
from roster
join campaign_ops_users u
  on lower(u.display_name) = lower(roster.display_name)
 and u.is_active = true
on conflict (user_id, workflow_key, workflow_role) where is_active = true
 do nothing;
