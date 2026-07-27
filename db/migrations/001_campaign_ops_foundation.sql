create extension if not exists pgcrypto;

create table if not exists campaign_ops_users (
    id uuid primary key default gen_random_uuid(),
    display_name text not null,
    email text null,
    role text not null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists campaign_ops_clients (
    id uuid primary key default gen_random_uuid(),
    name text not null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by uuid null references campaign_ops_users(id),
    updated_by uuid null references campaign_ops_users(id)
);

create table if not exists campaign_ops_programs (
    id uuid primary key default gen_random_uuid(),
    program_name text not null,
    client_id uuid null references campaign_ops_clients(id),
    primary_workstream_type text null,
    status text not null,
    cross_stage text not null,
    risk_level text not null,
    priority text null,
    description text null,
    latest_update text null,
    start_date date null,
    target_end_date date null,
    archived_at timestamptz null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by uuid null references campaign_ops_users(id),
    updated_by uuid null references campaign_ops_users(id)
);

create table if not exists campaign_ops_workstreams (
    id uuid primary key default gen_random_uuid(),
    program_id uuid not null references campaign_ops_programs(id),
    workstream_type text not null,
    status text not null,
    cross_stage text not null,
    risk_level text not null,
    owner_user_id uuid null references campaign_ops_users(id),
    next_action text null,
    next_due_date date null,
    waiting_on text not null,
    latest_update text null,
    metadata_json jsonb not null default '{}'::jsonb,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by uuid null references campaign_ops_users(id),
    updated_by uuid null references campaign_ops_users(id)
);

create table if not exists campaign_ops_assignments (
    id uuid primary key default gen_random_uuid(),
    program_id uuid not null references campaign_ops_programs(id),
    workstream_id uuid null references campaign_ops_workstreams(id),
    user_id uuid not null references campaign_ops_users(id),
    assignment_role text not null,
    is_primary boolean not null default false,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by uuid null references campaign_ops_users(id),
    updated_by uuid null references campaign_ops_users(id)
);

create table if not exists campaign_ops_tasks (
    id uuid primary key default gen_random_uuid(),
    program_id uuid not null references campaign_ops_programs(id),
    workstream_id uuid null references campaign_ops_workstreams(id),
    title text not null,
    description text null,
    assigned_user_id uuid null references campaign_ops_users(id),
    responsible_party text null,
    status text not null,
    risk_level text not null,
    waiting_on text not null,
    due_date date null,
    start_date date null,
    completed_at timestamptz null,
    hard_deadline boolean not null default false,
    priority text null,
    sort_order integer not null default 0,
    metadata_json jsonb not null default '{}'::jsonb,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by uuid null references campaign_ops_users(id),
    updated_by uuid null references campaign_ops_users(id)
);

create table if not exists campaign_ops_milestones (
    id uuid primary key default gen_random_uuid(),
    program_id uuid not null references campaign_ops_programs(id),
    workstream_id uuid null references campaign_ops_workstreams(id),
    title text not null,
    milestone_type text null,
    target_date date null,
    start_date date null,
    end_date date null,
    status text not null,
    owner_user_id uuid null references campaign_ops_users(id),
    hard_deadline boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by uuid null references campaign_ops_users(id),
    updated_by uuid null references campaign_ops_users(id)
);

create table if not exists campaign_ops_resources (
    id uuid primary key default gen_random_uuid(),
    program_id uuid not null references campaign_ops_programs(id),
    workstream_id uuid null references campaign_ops_workstreams(id),
    resource_type text not null,
    title text not null,
    url text null,
    notes text null,
    is_required boolean not null default false,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by uuid null references campaign_ops_users(id),
    updated_by uuid null references campaign_ops_users(id)
);

create table if not exists campaign_ops_notes (
    id uuid primary key default gen_random_uuid(),
    program_id uuid not null references campaign_ops_programs(id),
    workstream_id uuid null references campaign_ops_workstreams(id),
    task_id uuid null references campaign_ops_tasks(id),
    author_user_id uuid null references campaign_ops_users(id),
    note_text text not null,
    note_type text null,
    is_internal boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists campaign_ops_task_dependencies (
    id uuid primary key default gen_random_uuid(),
    task_id uuid not null references campaign_ops_tasks(id),
    depends_on_task_id uuid not null references campaign_ops_tasks(id),
    dependency_type text null,
    created_at timestamptz not null default now(),
    created_by uuid null references campaign_ops_users(id),
    check (task_id <> depends_on_task_id),
    unique (task_id, depends_on_task_id)
);

create table if not exists campaign_ops_activity (
    id uuid primary key default gen_random_uuid(),
    program_id uuid null references campaign_ops_programs(id),
    workstream_id uuid null references campaign_ops_workstreams(id),
    task_id uuid null references campaign_ops_tasks(id),
    actor_user_id uuid null references campaign_ops_users(id),
    event_type text not null,
    entity_type text not null,
    entity_id uuid null,
    old_value_json jsonb null,
    new_value_json jsonb null,
    message text null,
    created_at timestamptz not null default now()
);

create unique index if not exists idx_campaign_ops_users_display_name_active
    on campaign_ops_users (lower(display_name))
    where is_active = true;

create unique index if not exists idx_campaign_ops_clients_name_active
    on campaign_ops_clients (lower(name))
    where is_active = true;

create unique index if not exists idx_campaign_ops_workstreams_type_active
    on campaign_ops_workstreams (program_id, workstream_type)
    where is_active = true;

create unique index if not exists idx_campaign_ops_primary_program_owner
    on campaign_ops_assignments (program_id)
    where is_active = true
      and is_primary = true
      and assignment_role = 'program_owner';

create index if not exists idx_campaign_ops_programs_active
    on campaign_ops_programs (is_active, updated_at desc);
create index if not exists idx_campaign_ops_programs_status
    on campaign_ops_programs (status);
create index if not exists idx_campaign_ops_programs_cross_stage
    on campaign_ops_programs (cross_stage);
create index if not exists idx_campaign_ops_programs_risk_level
    on campaign_ops_programs (risk_level);
create index if not exists idx_campaign_ops_programs_client
    on campaign_ops_programs (client_id);
create index if not exists idx_campaign_ops_workstreams_program
    on campaign_ops_workstreams (program_id);
create index if not exists idx_campaign_ops_workstreams_owner
    on campaign_ops_workstreams (owner_user_id);
create index if not exists idx_campaign_ops_tasks_assigned_user
    on campaign_ops_tasks (assigned_user_id);
create index if not exists idx_campaign_ops_tasks_due_date
    on campaign_ops_tasks (due_date);
create index if not exists idx_campaign_ops_tasks_status
    on campaign_ops_tasks (status);
create index if not exists idx_campaign_ops_assignments_user
    on campaign_ops_assignments (user_id);
create index if not exists idx_campaign_ops_notes_program_created
    on campaign_ops_notes (program_id, created_at);
create index if not exists idx_campaign_ops_activity_program_created
    on campaign_ops_activity (program_id, created_at);

create or replace function campaign_ops_set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists set_campaign_ops_users_updated_at on campaign_ops_users;
create trigger set_campaign_ops_users_updated_at
before update on campaign_ops_users
for each row execute function campaign_ops_set_updated_at();

drop trigger if exists set_campaign_ops_clients_updated_at on campaign_ops_clients;
create trigger set_campaign_ops_clients_updated_at
before update on campaign_ops_clients
for each row execute function campaign_ops_set_updated_at();

drop trigger if exists set_campaign_ops_programs_updated_at on campaign_ops_programs;
create trigger set_campaign_ops_programs_updated_at
before update on campaign_ops_programs
for each row execute function campaign_ops_set_updated_at();

drop trigger if exists set_campaign_ops_workstreams_updated_at on campaign_ops_workstreams;
create trigger set_campaign_ops_workstreams_updated_at
before update on campaign_ops_workstreams
for each row execute function campaign_ops_set_updated_at();

drop trigger if exists set_campaign_ops_assignments_updated_at on campaign_ops_assignments;
create trigger set_campaign_ops_assignments_updated_at
before update on campaign_ops_assignments
for each row execute function campaign_ops_set_updated_at();

drop trigger if exists set_campaign_ops_tasks_updated_at on campaign_ops_tasks;
create trigger set_campaign_ops_tasks_updated_at
before update on campaign_ops_tasks
for each row execute function campaign_ops_set_updated_at();

drop trigger if exists set_campaign_ops_milestones_updated_at on campaign_ops_milestones;
create trigger set_campaign_ops_milestones_updated_at
before update on campaign_ops_milestones
for each row execute function campaign_ops_set_updated_at();

drop trigger if exists set_campaign_ops_resources_updated_at on campaign_ops_resources;
create trigger set_campaign_ops_resources_updated_at
before update on campaign_ops_resources
for each row execute function campaign_ops_set_updated_at();

drop trigger if exists set_campaign_ops_notes_updated_at on campaign_ops_notes;
create trigger set_campaign_ops_notes_updated_at
before update on campaign_ops_notes
for each row execute function campaign_ops_set_updated_at();
