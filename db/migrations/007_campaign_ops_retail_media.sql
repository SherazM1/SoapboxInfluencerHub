create table if not exists campaign_ops_retail_media_campaigns (
    id uuid primary key default gen_random_uuid(),
    program_id uuid not null references campaign_ops_programs(id),
    workstream_id uuid null references campaign_ops_workstreams(id),
    campaign_title text not null,
    retail_media_status text null,
    latest_update text null,
    waiting_on text null,
    owner_user_id uuid null references campaign_ops_users(id),
    launch_date date null,
    wrap_date date null,
    reporting_cadence text null,
    overall_budget numeric null,
    total_spend numeric null,
    is_paused boolean not null default false,
    pause_reason text null,
    is_active boolean not null default true,
    created_by_user_id uuid null references campaign_ops_users(id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (overall_budget is null or overall_budget >= 0),
    check (total_spend is null or total_spend >= 0),
    check (wrap_date is null or launch_date is null or wrap_date >= launch_date)
);

create table if not exists campaign_ops_retail_media_channels (
    id uuid primary key default gen_random_uuid(),
    retail_media_campaign_id uuid not null references campaign_ops_retail_media_campaigns(id),
    channel_type text not null,
    platform_name text null,
    status text null,
    budget numeric null,
    spend_to_date numeric null,
    launch_date date null,
    end_date date null,
    reporting_requirement text null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (budget is null or budget >= 0),
    check (spend_to_date is null or spend_to_date >= 0),
    check (end_date is null or launch_date is null or end_date >= launch_date)
);

create table if not exists campaign_ops_retail_media_activations (
    id uuid primary key default gen_random_uuid(),
    retail_media_campaign_id uuid not null references campaign_ops_retail_media_campaigns(id),
    channel_id uuid null references campaign_ops_retail_media_channels(id),
    activation_name text not null,
    activation_type text null,
    status text null,
    start_date date null,
    end_date date null,
    hard_deadline boolean not null default false,
    waiting_on text null,
    latest_update text null,
    completed_at timestamptz null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (end_date is null or start_date is null or end_date >= start_date)
);

create table if not exists campaign_ops_retail_media_creative_items (
    id uuid primary key default gen_random_uuid(),
    retail_media_campaign_id uuid not null references campaign_ops_retail_media_campaigns(id),
    channel_id uuid null references campaign_ops_retail_media_channels(id),
    creative_name text not null,
    creative_type text null,
    approval_status text null,
    submission_status text null,
    platform_status text null,
    due_date date null,
    submitted_date date null,
    approved_date date null,
    notes text null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists campaign_ops_retail_media_optimization_updates (
    id uuid primary key default gen_random_uuid(),
    retail_media_campaign_id uuid not null references campaign_ops_retail_media_campaigns(id),
    channel_id uuid null references campaign_ops_retail_media_channels(id),
    update_date date not null,
    update_text text not null,
    optimization_type text null,
    created_by_user_id uuid null references campaign_ops_users(id),
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_campaign_ops_rm_campaign_active_title
    on campaign_ops_retail_media_campaigns (program_id, lower(campaign_title))
    where is_active = true;
create index if not exists idx_campaign_ops_rm_campaign_program on campaign_ops_retail_media_campaigns (program_id);
create index if not exists idx_campaign_ops_rm_campaign_workstream on campaign_ops_retail_media_campaigns (workstream_id);
create index if not exists idx_campaign_ops_rm_campaign_owner on campaign_ops_retail_media_campaigns (owner_user_id);
create index if not exists idx_campaign_ops_rm_campaign_status on campaign_ops_retail_media_campaigns (retail_media_status);
create index if not exists idx_campaign_ops_rm_campaign_paused on campaign_ops_retail_media_campaigns (is_paused);
create index if not exists idx_campaign_ops_rm_campaign_active on campaign_ops_retail_media_campaigns (is_active);
create index if not exists idx_campaign_ops_rm_campaign_launch on campaign_ops_retail_media_campaigns (launch_date);
create index if not exists idx_campaign_ops_rm_channel_active_type
    on campaign_ops_retail_media_channels (retail_media_campaign_id, lower(channel_type))
    where is_active = true;
create index if not exists idx_campaign_ops_rm_channel_campaign on campaign_ops_retail_media_channels (retail_media_campaign_id);
create index if not exists idx_campaign_ops_rm_channel_type on campaign_ops_retail_media_channels (channel_type);
create index if not exists idx_campaign_ops_rm_channel_dates on campaign_ops_retail_media_channels (launch_date, end_date);
create index if not exists idx_campaign_ops_rm_activation_campaign on campaign_ops_retail_media_activations (retail_media_campaign_id);
create index if not exists idx_campaign_ops_rm_activation_channel on campaign_ops_retail_media_activations (channel_id);
create index if not exists idx_campaign_ops_rm_activation_status on campaign_ops_retail_media_activations (status);
create index if not exists idx_campaign_ops_rm_activation_dates on campaign_ops_retail_media_activations (start_date, end_date);
create index if not exists idx_campaign_ops_rm_creative_campaign on campaign_ops_retail_media_creative_items (retail_media_campaign_id);
create index if not exists idx_campaign_ops_rm_creative_channel on campaign_ops_retail_media_creative_items (channel_id);
create index if not exists idx_campaign_ops_rm_creative_approval on campaign_ops_retail_media_creative_items (approval_status);
create index if not exists idx_campaign_ops_rm_optimization_campaign on campaign_ops_retail_media_optimization_updates (retail_media_campaign_id);
create index if not exists idx_campaign_ops_rm_optimization_channel on campaign_ops_retail_media_optimization_updates (channel_id);
create index if not exists idx_campaign_ops_rm_optimization_date on campaign_ops_retail_media_optimization_updates (update_date desc);

drop trigger if exists set_campaign_ops_retail_media_campaigns_updated_at on campaign_ops_retail_media_campaigns;
create trigger set_campaign_ops_retail_media_campaigns_updated_at
before update on campaign_ops_retail_media_campaigns
for each row execute function campaign_ops_set_updated_at();

drop trigger if exists set_campaign_ops_retail_media_channels_updated_at on campaign_ops_retail_media_channels;
create trigger set_campaign_ops_retail_media_channels_updated_at
before update on campaign_ops_retail_media_channels
for each row execute function campaign_ops_set_updated_at();

drop trigger if exists set_campaign_ops_retail_media_activations_updated_at on campaign_ops_retail_media_activations;
create trigger set_campaign_ops_retail_media_activations_updated_at
before update on campaign_ops_retail_media_activations
for each row execute function campaign_ops_set_updated_at();

drop trigger if exists set_campaign_ops_retail_media_creative_items_updated_at on campaign_ops_retail_media_creative_items;
create trigger set_campaign_ops_retail_media_creative_items_updated_at
before update on campaign_ops_retail_media_creative_items
for each row execute function campaign_ops_set_updated_at();

drop trigger if exists set_campaign_ops_retail_media_optimization_updates_updated_at on campaign_ops_retail_media_optimization_updates;
create trigger set_campaign_ops_retail_media_optimization_updates_updated_at
before update on campaign_ops_retail_media_optimization_updates
for each row execute function campaign_ops_set_updated_at();
