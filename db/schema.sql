create extension if not exists pgcrypto;

create table if not exists campaigns (
    id uuid primary key default gen_random_uuid(),
    program_name text not null,
    campaign_date date not null,
    campaign_year integer generated always as (
        extract(year from campaign_date)::integer
    ) stored,
    client_name text null,
    notes text null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists campaign_metrics (
    id uuid primary key default gen_random_uuid(),
    campaign_id uuid not null references campaigns(id),
    influencer_count numeric not null check (influencer_count >= 0),
    engagements numeric not null check (engagements >= 0),
    organic_impressions numeric not null check (organic_impressions >= 0),
    paid_impressions numeric null check (paid_impressions >= 0),
    paid_spend_impressions numeric null check (paid_spend_impressions >= 0),
    paid_engagements numeric null check (paid_engagements >= 0),
    paid_spend_engagements numeric null check (paid_spend_engagements >= 0),
    paid_clicks numeric null check (paid_clicks >= 0),
    paid_spend_clicks numeric null check (paid_spend_clicks >= 0),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (campaign_id)
);

create index if not exists idx_campaigns_active_date
    on campaigns (is_active, campaign_date desc);

create index if not exists idx_campaigns_year
    on campaigns (campaign_year);

create index if not exists idx_campaign_metrics_campaign_id
    on campaign_metrics (campaign_id);

alter table campaign_metrics
    alter column paid_impressions drop not null,
    alter column paid_spend_impressions drop not null,
    alter column paid_engagements drop not null,
    alter column paid_spend_engagements drop not null,
    alter column paid_clicks drop not null,
    alter column paid_spend_clicks drop not null;

create or replace function set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists set_campaigns_updated_at on campaigns;
create trigger set_campaigns_updated_at
before update on campaigns
for each row execute function set_updated_at();

drop trigger if exists set_campaign_metrics_updated_at on campaign_metrics;
create trigger set_campaign_metrics_updated_at
before update on campaign_metrics
for each row execute function set_updated_at();
