alter table campaign_ops_milestones
    add column if not exists completed_at timestamptz null,
    add column if not exists is_active boolean not null default true;

alter table campaign_ops_resources
    add column if not exists is_active boolean not null default true;

create index if not exists idx_campaign_ops_milestones_program_active
    on campaign_ops_milestones (program_id, is_active, target_date, start_date, end_date);

create index if not exists idx_campaign_ops_resources_program_active
    on campaign_ops_resources (program_id, is_active, resource_type);
