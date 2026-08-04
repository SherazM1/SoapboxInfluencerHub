alter table campaign_ops_milestones
    add column if not exists is_highlighted boolean not null default false;

create table if not exists campaign_ops_insights_projects (
    id uuid primary key default gen_random_uuid(),
    program_id uuid not null references campaign_ops_programs(id),
    workstream_id uuid null references campaign_ops_workstreams(id),
    job_number text null,
    project_title text not null,
    insights_status text null,
    latest_update text null,
    total_program_cost numeric null,
    sample_size integer null,
    budget numeric null,
    owner_user_id uuid null references campaign_ops_users(id),
    is_active boolean not null default true,
    created_by_user_id uuid null references campaign_ops_users(id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (total_program_cost is null or total_program_cost >= 0),
    check (sample_size is null or sample_size >= 0),
    check (budget is null or budget >= 0)
);

alter table campaign_ops_insights_projects
    drop constraint if exists campaign_ops_insights_projects_program_id_key;

create table if not exists campaign_ops_insights_objectives (
    id uuid primary key default gen_random_uuid(),
    insights_project_id uuid not null references campaign_ops_insights_projects(id),
    objective_text text not null,
    sort_order integer not null default 0,
    is_active boolean not null default true,
    created_by_user_id uuid null references campaign_ops_users(id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_campaign_ops_insights_projects_program
    on campaign_ops_insights_projects (program_id);
create index if not exists idx_campaign_ops_insights_projects_workstream
    on campaign_ops_insights_projects (workstream_id);
create index if not exists idx_campaign_ops_insights_projects_owner
    on campaign_ops_insights_projects (owner_user_id);
create index if not exists idx_campaign_ops_insights_projects_status
    on campaign_ops_insights_projects (insights_status);
create index if not exists idx_campaign_ops_insights_projects_active
    on campaign_ops_insights_projects (is_active);
create index if not exists idx_campaign_ops_insights_projects_updated
    on campaign_ops_insights_projects (updated_at desc);
create index if not exists idx_campaign_ops_insights_objectives_project
    on campaign_ops_insights_objectives (insights_project_id, is_active, sort_order);

drop trigger if exists set_campaign_ops_insights_projects_updated_at on campaign_ops_insights_projects;
create trigger set_campaign_ops_insights_projects_updated_at
before update on campaign_ops_insights_projects
for each row execute function campaign_ops_set_updated_at();

drop trigger if exists set_campaign_ops_insights_objectives_updated_at on campaign_ops_insights_objectives;
create trigger set_campaign_ops_insights_objectives_updated_at
before update on campaign_ops_insights_objectives
for each row execute function campaign_ops_set_updated_at();
