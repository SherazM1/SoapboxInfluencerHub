create table if not exists campaign_ops_influencer_live_checkpoints (
    id uuid primary key default gen_random_uuid(),
    influencer_campaign_id uuid not null references campaign_ops_influencer_campaigns(id),
    checkpoint_type text null,
    checkpoint_title text not null,
    checkpoint_description text null,
    sequence_order integer not null default 0,
    responsible_party text null,
    assigned_user_id uuid null references campaign_ops_users(id),
    start_date date null,
    due_date date null,
    completed_date date null,
    status text null,
    hard_deadline boolean not null default false,
    waiting_on text null,
    notes text null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint campaign_ops_live_checkpoint_dates check (due_date is null or start_date is null or due_date >= start_date)
);

create table if not exists campaign_ops_influencer_creator_waves (
    id uuid primary key default gen_random_uuid(),
    influencer_campaign_id uuid not null references campaign_ops_influencer_campaigns(id),
    wave_number integer not null check (wave_number > 0),
    wave_name text null,
    planned_start_date date null,
    planned_end_date date null,
    actual_start_date date null,
    actual_end_date date null,
    planned_creator_count integer null check (planned_creator_count is null or planned_creator_count >= 0),
    live_creator_count integer null check (live_creator_count is null or live_creator_count >= 0),
    completed_creator_count integer null check (completed_creator_count is null or completed_creator_count >= 0),
    status text null,
    waiting_on text null,
    notes text null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint campaign_ops_wave_planned_dates check (planned_end_date is null or planned_start_date is null or planned_end_date >= planned_start_date),
    constraint campaign_ops_wave_actual_dates check (actual_end_date is null or actual_start_date is null or actual_end_date >= actual_start_date)
);

create table if not exists campaign_ops_influencer_live_creators (
    id uuid primary key default gen_random_uuid(),
    influencer_campaign_id uuid not null references campaign_ops_influencer_campaigns(id),
    wave_id uuid null references campaign_ops_influencer_creator_waves(id),
    creator_name text not null,
    creator_handle text null,
    platform text null,
    live_status text null,
    draft_status text null,
    approval_status text null,
    scheduled_live_date date null,
    actual_live_date date null,
    paid_live_end_date date null,
    content_url text null,
    click2cart_url text null,
    retailer_url text null,
    impressions_reporting_required boolean not null default false,
    latest_impressions bigint null check (latest_impressions is null or latest_impressions >= 0),
    last_impressions_update_date date null,
    waiting_on text null,
    exception_status text null,
    exception_notes text null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists campaign_ops_influencer_live_exceptions (
    id uuid primary key default gen_random_uuid(),
    influencer_campaign_id uuid not null references campaign_ops_influencer_campaigns(id),
    live_creator_id uuid null references campaign_ops_influencer_live_creators(id),
    exception_type text null,
    exception_title text not null,
    description text null,
    status text null,
    owner_user_id uuid null references campaign_ops_users(id),
    opened_date date null,
    due_date date null,
    resolved_date date null,
    resolution_notes text null,
    is_highlighted boolean not null default false,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint campaign_ops_live_exception_dates check (due_date is null or opened_date is null or due_date >= opened_date)
);

create index if not exists idx_campaign_ops_live_checkpoints_campaign_order on campaign_ops_influencer_live_checkpoints (influencer_campaign_id, sequence_order);
create index if not exists idx_campaign_ops_live_checkpoints_due_status on campaign_ops_influencer_live_checkpoints (due_date, status);
create index if not exists idx_campaign_ops_creator_waves_campaign on campaign_ops_influencer_creator_waves (influencer_campaign_id);
create index if not exists idx_campaign_ops_creator_waves_number on campaign_ops_influencer_creator_waves (influencer_campaign_id, wave_number);
create index if not exists idx_campaign_ops_creator_waves_status on campaign_ops_influencer_creator_waves (status);
create index if not exists idx_campaign_ops_live_creators_campaign on campaign_ops_influencer_live_creators (influencer_campaign_id);
create index if not exists idx_campaign_ops_live_creators_wave on campaign_ops_influencer_live_creators (wave_id);
create index if not exists idx_campaign_ops_live_creators_status on campaign_ops_influencer_live_creators (live_status);
create index if not exists idx_campaign_ops_live_creators_dates on campaign_ops_influencer_live_creators (scheduled_live_date, actual_live_date, paid_live_end_date);
create index if not exists idx_campaign_ops_live_exceptions_campaign on campaign_ops_influencer_live_exceptions (influencer_campaign_id);
create index if not exists idx_campaign_ops_live_exceptions_creator on campaign_ops_influencer_live_exceptions (live_creator_id);
create index if not exists idx_campaign_ops_live_exceptions_status on campaign_ops_influencer_live_exceptions (status);
create index if not exists idx_campaign_ops_live_exceptions_highlight on campaign_ops_influencer_live_exceptions (is_highlighted);

drop trigger if exists set_campaign_ops_influencer_live_checkpoints_updated_at on campaign_ops_influencer_live_checkpoints;
create trigger set_campaign_ops_influencer_live_checkpoints_updated_at before update on campaign_ops_influencer_live_checkpoints for each row execute function campaign_ops_set_updated_at();
drop trigger if exists set_campaign_ops_influencer_creator_waves_updated_at on campaign_ops_influencer_creator_waves;
create trigger set_campaign_ops_influencer_creator_waves_updated_at before update on campaign_ops_influencer_creator_waves for each row execute function campaign_ops_set_updated_at();
drop trigger if exists set_campaign_ops_influencer_live_creators_updated_at on campaign_ops_influencer_live_creators;
create trigger set_campaign_ops_influencer_live_creators_updated_at before update on campaign_ops_influencer_live_creators for each row execute function campaign_ops_set_updated_at();
drop trigger if exists set_campaign_ops_influencer_live_exceptions_updated_at on campaign_ops_influencer_live_exceptions;
create trigger set_campaign_ops_influencer_live_exceptions_updated_at before update on campaign_ops_influencer_live_exceptions for each row execute function campaign_ops_set_updated_at();
