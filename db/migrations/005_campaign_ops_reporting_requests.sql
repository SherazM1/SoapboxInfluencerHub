create table if not exists campaign_ops_reporting_requests (
    id uuid primary key default gen_random_uuid(),
    program_id uuid not null references campaign_ops_programs(id),
    workstream_id uuid null references campaign_ops_workstreams(id),
    request_category text not null,
    request_type text not null,
    am_user_id uuid not null references campaign_ops_users(id),
    assigned_user_id uuid null references campaign_ops_users(id),
    due_date date null,
    recap_date_with_client date null,
    recap_date_text text null,
    brief_url text null,
    brief_status_text text null,
    delivered boolean not null default false,
    review_required boolean not null default false,
    review_complete boolean not null default false,
    approval_required boolean not null default false,
    approved boolean not null default false,
    questions_requested text null,
    special_requests text null,
    status text not null default 'requested',
    risk text not null default 'unrated',
    waiting_on text null,
    completed_at timestamptz null,
    is_active boolean not null default true,
    created_by_user_id uuid null references campaign_ops_users(id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (request_category in ('survey', 'report'))
);

create index if not exists idx_campaign_ops_reporting_requests_program
    on campaign_ops_reporting_requests (program_id);
create index if not exists idx_campaign_ops_reporting_requests_category
    on campaign_ops_reporting_requests (request_category);
create index if not exists idx_campaign_ops_reporting_requests_am
    on campaign_ops_reporting_requests (am_user_id);
create index if not exists idx_campaign_ops_reporting_requests_assigned
    on campaign_ops_reporting_requests (assigned_user_id);
create index if not exists idx_campaign_ops_reporting_requests_due
    on campaign_ops_reporting_requests (due_date);
create index if not exists idx_campaign_ops_reporting_requests_status
    on campaign_ops_reporting_requests (status);
create index if not exists idx_campaign_ops_reporting_requests_active
    on campaign_ops_reporting_requests (is_active);

drop trigger if exists set_campaign_ops_reporting_requests_updated_at on campaign_ops_reporting_requests;
create trigger set_campaign_ops_reporting_requests_updated_at
before update on campaign_ops_reporting_requests
for each row execute function campaign_ops_set_updated_at();
