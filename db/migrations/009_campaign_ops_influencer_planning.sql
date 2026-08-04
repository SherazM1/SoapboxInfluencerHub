create table if not exists campaign_ops_influencer_campaigns (
    id uuid primary key default gen_random_uuid(),
    program_id uuid not null references campaign_ops_programs(id),
    workstream_id uuid null references campaign_ops_workstreams(id),
    campaign_title text not null,
    manager_user_id uuid null references campaign_ops_users(id),
    influencer_stage text not null default 'planning',
    planning_status text null,
    latest_update text null,
    waiting_on text null,
    is_on_hold boolean not null default false,
    hold_reason text null,
    application_open_date date null,
    application_close_date date null,
    influencer_approval_due_date date null,
    scripts_due_date date null,
    first_content_due_date date null,
    launch_date date null,
    wrap_date date null,
    invoice_date date null,
    invoice_status text null,
    invoice_amount numeric null check (invoice_amount is null or invoice_amount >= 0),
    target_creator_count integer null check (target_creator_count is null or target_creator_count >= 0),
    approved_creator_count integer null check (approved_creator_count is null or approved_creator_count >= 0),
    contracted_creator_count integer null check (contracted_creator_count is null or contracted_creator_count >= 0),
    is_active boolean not null default true,
    created_by_user_id uuid null references campaign_ops_users(id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint campaign_ops_influencer_campaign_dates check (wrap_date is null or launch_date is null or wrap_date >= launch_date),
    constraint campaign_ops_influencer_hold_reason check (is_on_hold = false or nullif(btrim(coalesce(hold_reason, '')), '') is not null)
);

create table if not exists campaign_ops_influencer_planning_steps (
    id uuid primary key default gen_random_uuid(),
    influencer_campaign_id uuid not null references campaign_ops_influencer_campaigns(id),
    step_type text null,
    step_title text not null,
    step_description text null,
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
    constraint campaign_ops_influencer_step_dates check (due_date is null or start_date is null or due_date >= start_date)
);

create table if not exists campaign_ops_influencer_approval_rounds (
    id uuid primary key default gen_random_uuid(),
    influencer_campaign_id uuid not null references campaign_ops_influencer_campaigns(id),
    approval_type text not null,
    round_number integer not null default 1 check (round_number > 0),
    approval_scope text null,
    requested_date date null,
    feedback_due_date date null,
    feedback_received_date date null,
    approved_date date null,
    status text null,
    waiting_on text null,
    notes text null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint campaign_ops_influencer_approval_dates check (
        (feedback_due_date is null or requested_date is null or feedback_due_date >= requested_date)
        and (feedback_received_date is null or requested_date is null or feedback_received_date >= requested_date)
        and (approved_date is null or requested_date is null or approved_date >= requested_date)
    )
);

create table if not exists campaign_ops_influencer_content_rounds (
    id uuid primary key default gen_random_uuid(),
    influencer_campaign_id uuid not null references campaign_ops_influencer_campaigns(id),
    round_number integer not null check (round_number > 0),
    content_type text null,
    internal_review_due_date date null,
    client_review_sent_date date null,
    client_feedback_due_date date null,
    feedback_received_date date null,
    resubmission_due_date date null,
    approved_date date null,
    status text null,
    waiting_on text null,
    notes text null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists campaign_ops_influencer_creator_summary (
    id uuid primary key default gen_random_uuid(),
    influencer_campaign_id uuid not null unique references campaign_ops_influencer_campaigns(id),
    target_creator_count integer null check (target_creator_count is null or target_creator_count >= 0),
    applicants_count integer null check (applicants_count is null or applicants_count >= 0),
    vetted_count integer null check (vetted_count is null or vetted_count >= 0),
    submitted_for_approval_count integer null check (submitted_for_approval_count is null or submitted_for_approval_count >= 0),
    approved_count integer null check (approved_count is null or approved_count >= 0),
    contracted_count integer null check (contracted_count is null or contracted_count >= 0),
    content_submitted_count integer null check (content_submitted_count is null or content_submitted_count >= 0),
    content_approved_count integer null check (content_approved_count is null or content_approved_count >= 0),
    notes text null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_campaign_ops_influencer_campaigns_program on campaign_ops_influencer_campaigns (program_id);
create index if not exists idx_campaign_ops_influencer_campaigns_workstream on campaign_ops_influencer_campaigns (workstream_id);
create index if not exists idx_campaign_ops_influencer_campaigns_manager on campaign_ops_influencer_campaigns (manager_user_id);
create index if not exists idx_campaign_ops_influencer_campaigns_stage on campaign_ops_influencer_campaigns (influencer_stage);
create index if not exists idx_campaign_ops_influencer_campaigns_status on campaign_ops_influencer_campaigns (planning_status);
create index if not exists idx_campaign_ops_influencer_campaigns_hold on campaign_ops_influencer_campaigns (is_on_hold);
create index if not exists idx_campaign_ops_influencer_campaigns_launch on campaign_ops_influencer_campaigns (launch_date);
create index if not exists idx_campaign_ops_influencer_campaigns_wrap on campaign_ops_influencer_campaigns (wrap_date);
create index if not exists idx_campaign_ops_influencer_campaigns_invoice on campaign_ops_influencer_campaigns (invoice_date);
create index if not exists idx_campaign_ops_influencer_campaigns_active on campaign_ops_influencer_campaigns (is_active);
create index if not exists idx_campaign_ops_influencer_steps_campaign_order on campaign_ops_influencer_planning_steps (influencer_campaign_id, sequence_order);
create index if not exists idx_campaign_ops_influencer_steps_due_status on campaign_ops_influencer_planning_steps (due_date, status);
create index if not exists idx_campaign_ops_influencer_approval_type_status on campaign_ops_influencer_approval_rounds (approval_type, status);
create index if not exists idx_campaign_ops_influencer_approval_campaign on campaign_ops_influencer_approval_rounds (influencer_campaign_id);
create index if not exists idx_campaign_ops_influencer_content_status on campaign_ops_influencer_content_rounds (status);
create index if not exists idx_campaign_ops_influencer_content_campaign on campaign_ops_influencer_content_rounds (influencer_campaign_id);

drop trigger if exists set_campaign_ops_influencer_campaigns_updated_at on campaign_ops_influencer_campaigns;
create trigger set_campaign_ops_influencer_campaigns_updated_at before update on campaign_ops_influencer_campaigns for each row execute function campaign_ops_set_updated_at();
drop trigger if exists set_campaign_ops_influencer_planning_steps_updated_at on campaign_ops_influencer_planning_steps;
create trigger set_campaign_ops_influencer_planning_steps_updated_at before update on campaign_ops_influencer_planning_steps for each row execute function campaign_ops_set_updated_at();
drop trigger if exists set_campaign_ops_influencer_approval_rounds_updated_at on campaign_ops_influencer_approval_rounds;
create trigger set_campaign_ops_influencer_approval_rounds_updated_at before update on campaign_ops_influencer_approval_rounds for each row execute function campaign_ops_set_updated_at();
drop trigger if exists set_campaign_ops_influencer_content_rounds_updated_at on campaign_ops_influencer_content_rounds;
create trigger set_campaign_ops_influencer_content_rounds_updated_at before update on campaign_ops_influencer_content_rounds for each row execute function campaign_ops_set_updated_at();
drop trigger if exists set_campaign_ops_influencer_creator_summary_updated_at on campaign_ops_influencer_creator_summary;
create trigger set_campaign_ops_influencer_creator_summary_updated_at before update on campaign_ops_influencer_creator_summary for each row execute function campaign_ops_set_updated_at();
