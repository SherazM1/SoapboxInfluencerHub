create table if not exists campaign_ops_influencer_recap_records (
    id uuid primary key default gen_random_uuid(),
    influencer_campaign_id uuid not null unique references campaign_ops_influencer_campaigns(id),
    recap_status text null,
    latest_update text null,
    waiting_on text null,
    reporting_due_date date null,
    draft_recap_due_date date null,
    internal_review_date date null,
    client_review_date date null,
    client_recap_date date null,
    recap_delivered_date date null,
    final_close_date date null,
    final_invoice_sent_date date null,
    sales_lift_analysis_required boolean not null default false,
    sales_lift_analysis_status text null,
    final_performance_data_status text null,
    creator_closeout_status text null,
    eop_survey_status text null,
    invoice_status text null,
    financial_close_status text null,
    lessons_learned text null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint campaign_ops_recap_dates check (
        final_close_date is null
        or recap_delivered_date is null
        or final_close_date >= recap_delivered_date
    )
);

create table if not exists campaign_ops_influencer_recap_checkpoints (
    id uuid primary key default gen_random_uuid(),
    influencer_campaign_id uuid not null references campaign_ops_influencer_campaigns(id),
    checkpoint_type text null,
    checkpoint_title text not null,
    sequence_order integer not null default 0,
    responsible_party text null,
    assigned_user_id uuid null references campaign_ops_users(id),
    due_date date null,
    completed_date date null,
    status text null,
    waiting_on text null,
    notes text null,
    hard_deadline boolean not null default false,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists campaign_ops_influencer_recap_requirements (
    id uuid primary key default gen_random_uuid(),
    influencer_campaign_id uuid not null references campaign_ops_influencer_campaigns(id),
    requirement_type text not null,
    requirement_title text not null,
    status text null,
    required boolean not null default true,
    due_date date null,
    received_date date null,
    completed_date date null,
    waiting_on text null,
    resource_id uuid null references campaign_ops_resources(id),
    reporting_request_id uuid null references campaign_ops_reporting_requests(id),
    notes text null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint campaign_ops_recap_requirement_dates check (
        completed_date is null
        or received_date is null
        or completed_date >= received_date
    )
);

create table if not exists campaign_ops_influencer_recap_launch_items (
    id uuid primary key default gen_random_uuid(),
    influencer_campaign_id uuid not null references campaign_ops_influencer_campaigns(id),
    group_name text null,
    product_name text not null,
    retailer_name text null,
    online_launch_date date null,
    in_store_launch_date date null,
    launch_status text null,
    product_url text null,
    retailer_url text null,
    notes text null,
    sort_order integer not null default 0,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_campaign_ops_recap_records_campaign on campaign_ops_influencer_recap_records (influencer_campaign_id);
create index if not exists idx_campaign_ops_recap_records_status on campaign_ops_influencer_recap_records (recap_status);
create index if not exists idx_campaign_ops_recap_records_dates on campaign_ops_influencer_recap_records (reporting_due_date, client_recap_date, final_close_date);
create index if not exists idx_campaign_ops_recap_records_active on campaign_ops_influencer_recap_records (is_active);
create index if not exists idx_campaign_ops_recap_checkpoints_campaign_order on campaign_ops_influencer_recap_checkpoints (influencer_campaign_id, sequence_order);
create index if not exists idx_campaign_ops_recap_checkpoints_due_status on campaign_ops_influencer_recap_checkpoints (due_date, status);
create index if not exists idx_campaign_ops_recap_requirements_campaign on campaign_ops_influencer_recap_requirements (influencer_campaign_id);
create index if not exists idx_campaign_ops_recap_requirements_type_status on campaign_ops_influencer_recap_requirements (requirement_type, status);
create index if not exists idx_campaign_ops_recap_requirements_resource on campaign_ops_influencer_recap_requirements (resource_id);
create index if not exists idx_campaign_ops_recap_requirements_request on campaign_ops_influencer_recap_requirements (reporting_request_id);
create index if not exists idx_campaign_ops_recap_launch_campaign_order on campaign_ops_influencer_recap_launch_items (influencer_campaign_id, sort_order);
create index if not exists idx_campaign_ops_recap_launch_group on campaign_ops_influencer_recap_launch_items (group_name);

drop trigger if exists set_campaign_ops_influencer_recap_records_updated_at on campaign_ops_influencer_recap_records;
create trigger set_campaign_ops_influencer_recap_records_updated_at before update on campaign_ops_influencer_recap_records for each row execute function campaign_ops_set_updated_at();
drop trigger if exists set_campaign_ops_influencer_recap_checkpoints_updated_at on campaign_ops_influencer_recap_checkpoints;
create trigger set_campaign_ops_influencer_recap_checkpoints_updated_at before update on campaign_ops_influencer_recap_checkpoints for each row execute function campaign_ops_set_updated_at();
drop trigger if exists set_campaign_ops_influencer_recap_requirements_updated_at on campaign_ops_influencer_recap_requirements;
create trigger set_campaign_ops_influencer_recap_requirements_updated_at before update on campaign_ops_influencer_recap_requirements for each row execute function campaign_ops_set_updated_at();
drop trigger if exists set_campaign_ops_influencer_recap_launch_items_updated_at on campaign_ops_influencer_recap_launch_items;
create trigger set_campaign_ops_influencer_recap_launch_items_updated_at before update on campaign_ops_influencer_recap_launch_items for each row execute function campaign_ops_set_updated_at();
