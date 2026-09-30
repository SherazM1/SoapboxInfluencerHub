create table if not exists campaign_ops_smm_programs (
    id uuid primary key default gen_random_uuid(),
    program_id uuid not null references campaign_ops_programs(id),
    workstream_id uuid not null references campaign_ops_workstreams(id),
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by uuid null references campaign_ops_users(id),
    updated_by uuid null references campaign_ops_users(id)
);

create unique index if not exists idx_campaign_ops_smm_programs_program_active
    on campaign_ops_smm_programs (program_id)
    where is_active = true;

create index if not exists idx_campaign_ops_smm_programs_workstream
    on campaign_ops_smm_programs (workstream_id, is_active);

create table if not exists campaign_ops_smm_timeline_rows (
    id uuid primary key default gen_random_uuid(),
    smm_program_id uuid not null references campaign_ops_smm_programs(id),
    due_date date null,
    action text not null,
    done boolean not null default false,
    program_notes text null,
    sequence_order integer not null default 0,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    created_by uuid null references campaign_ops_users(id),
    updated_by uuid null references campaign_ops_users(id)
);

create index if not exists idx_campaign_ops_smm_timeline_rows_program_order
    on campaign_ops_smm_timeline_rows (smm_program_id, is_active, due_date nulls last, sequence_order, id);

create trigger set_campaign_ops_smm_programs_updated_at
before update on campaign_ops_smm_programs
for each row execute function campaign_ops_set_updated_at();

create trigger set_campaign_ops_smm_timeline_rows_updated_at
before update on campaign_ops_smm_timeline_rows
for each row execute function campaign_ops_set_updated_at();
