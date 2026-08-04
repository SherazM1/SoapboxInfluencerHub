create table if not exists campaign_ops_content_programs (
    id uuid primary key default gen_random_uuid(),
    program_id uuid not null references campaign_ops_programs(id),
    workstream_id uuid null references campaign_ops_workstreams(id),
    content_program_title text not null,
    content_status text null,
    latest_update text null,
    waiting_on text null,
    owner_user_id uuid null references campaign_ops_users(id),
    total_sku_count integer null,
    default_graphics_per_sku integer null,
    monitoring_start_date date null,
    maintenance_end_date date null,
    reporting_cadence text null,
    is_invoiced boolean not null default false,
    invoice_status text null,
    is_active boolean not null default true,
    created_by_user_id uuid null references campaign_ops_users(id),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (total_sku_count is null or total_sku_count >= 0),
    check (default_graphics_per_sku is null or default_graphics_per_sku >= 0),
    check (maintenance_end_date is null or monitoring_start_date is null or maintenance_end_date >= monitoring_start_date)
);

create table if not exists campaign_ops_content_sku_groups (
    id uuid primary key default gen_random_uuid(),
    content_program_id uuid not null references campaign_ops_content_programs(id),
    group_name text not null,
    brand_name text null,
    expected_sku_count integer null,
    graphics_per_sku integer null,
    status text null,
    latest_update text null,
    waiting_on text null,
    sort_order integer not null default 0,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (expected_sku_count is null or expected_sku_count >= 0),
    check (graphics_per_sku is null or graphics_per_sku >= 0)
);

create table if not exists campaign_ops_content_skus (
    id uuid primary key default gen_random_uuid(),
    content_program_id uuid not null references campaign_ops_content_programs(id),
    sku_group_id uuid null references campaign_ops_content_sku_groups(id),
    sku_code text null,
    product_name text not null,
    retailer_sku text null,
    upc text null,
    variant text null,
    content_status text null,
    copy_status text null,
    attribute_status text null,
    graphics_status text null,
    submission_status text null,
    publication_status text null,
    live_url text null,
    last_checked_at timestamptz null,
    issue_status text null,
    waiting_on text null,
    maintenance_required boolean not null default false,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists campaign_ops_content_deliverables (
    id uuid primary key default gen_random_uuid(),
    content_program_id uuid not null references campaign_ops_content_programs(id),
    sku_group_id uuid null references campaign_ops_content_sku_groups(id),
    sku_id uuid null references campaign_ops_content_skus(id),
    deliverable_name text not null,
    deliverable_type text null,
    status text null,
    approval_status text null,
    due_date date null,
    delivered_date date null,
    approved_date date null,
    required_quantity integer null,
    completed_quantity integer null,
    waiting_on text null,
    notes text null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (required_quantity is null or required_quantity >= 0),
    check (completed_quantity is null or completed_quantity >= 0)
);

create table if not exists campaign_ops_content_submissions (
    id uuid primary key default gen_random_uuid(),
    content_program_id uuid not null references campaign_ops_content_programs(id),
    sku_group_id uuid null references campaign_ops_content_sku_groups(id),
    sku_id uuid null references campaign_ops_content_skus(id),
    retailer_or_platform text null,
    submission_type text null,
    status text null,
    submitted_date date null,
    approved_date date null,
    published_date date null,
    expected_live_date date null,
    live_url text null,
    issue_text text null,
    waiting_on text null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists campaign_ops_content_monitoring_updates (
    id uuid primary key default gen_random_uuid(),
    content_program_id uuid not null references campaign_ops_content_programs(id),
    sku_group_id uuid null references campaign_ops_content_sku_groups(id),
    sku_id uuid null references campaign_ops_content_skus(id),
    update_date date not null,
    update_type text null,
    update_text text not null,
    live_review_count integer null,
    publication_state text null,
    created_by_user_id uuid null references campaign_ops_users(id),
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (live_review_count is null or live_review_count >= 0)
);

create table if not exists campaign_ops_content_invoice_checkpoints (
    id uuid primary key default gen_random_uuid(),
    content_program_id uuid not null references campaign_ops_content_programs(id),
    checkpoint_name text not null,
    invoice_date date null,
    due_date date null,
    status text null,
    amount numeric null,
    notes text null,
    is_active boolean not null default true,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (amount is null or amount >= 0)
);

create index if not exists idx_campaign_ops_content_programs_program on campaign_ops_content_programs (program_id);
create index if not exists idx_campaign_ops_content_programs_workstream on campaign_ops_content_programs (workstream_id);
create index if not exists idx_campaign_ops_content_programs_owner on campaign_ops_content_programs (owner_user_id);
create index if not exists idx_campaign_ops_content_programs_status on campaign_ops_content_programs (content_status);
create index if not exists idx_campaign_ops_content_programs_active on campaign_ops_content_programs (is_active);
create index if not exists idx_campaign_ops_content_group_program on campaign_ops_content_sku_groups (content_program_id);
create index if not exists idx_campaign_ops_content_group_name on campaign_ops_content_sku_groups (content_program_id, lower(group_name));
create index if not exists idx_campaign_ops_content_skus_program on campaign_ops_content_skus (content_program_id);
create index if not exists idx_campaign_ops_content_skus_group on campaign_ops_content_skus (sku_group_id);
create index if not exists idx_campaign_ops_content_skus_code on campaign_ops_content_skus (content_program_id, sku_code);
create index if not exists idx_campaign_ops_content_skus_product on campaign_ops_content_skus (product_name);
create index if not exists idx_campaign_ops_content_skus_copy on campaign_ops_content_skus (copy_status);
create index if not exists idx_campaign_ops_content_skus_graphics on campaign_ops_content_skus (graphics_status);
create index if not exists idx_campaign_ops_content_skus_submission on campaign_ops_content_skus (submission_status);
create index if not exists idx_campaign_ops_content_skus_publication on campaign_ops_content_skus (publication_status);
create index if not exists idx_campaign_ops_content_skus_issue on campaign_ops_content_skus (issue_status);
create index if not exists idx_campaign_ops_content_deliverables_program on campaign_ops_content_deliverables (content_program_id);
create index if not exists idx_campaign_ops_content_deliverables_due on campaign_ops_content_deliverables (due_date);
create index if not exists idx_campaign_ops_content_submissions_program on campaign_ops_content_submissions (content_program_id);
create index if not exists idx_campaign_ops_content_submissions_dates on campaign_ops_content_submissions (submitted_date, expected_live_date, published_date);
create index if not exists idx_campaign_ops_content_monitoring_program_date on campaign_ops_content_monitoring_updates (content_program_id, update_date desc);
create index if not exists idx_campaign_ops_content_invoice_program on campaign_ops_content_invoice_checkpoints (content_program_id);
create index if not exists idx_campaign_ops_content_invoice_date_status on campaign_ops_content_invoice_checkpoints (invoice_date, status);

drop trigger if exists set_campaign_ops_content_programs_updated_at on campaign_ops_content_programs;
create trigger set_campaign_ops_content_programs_updated_at before update on campaign_ops_content_programs for each row execute function campaign_ops_set_updated_at();
drop trigger if exists set_campaign_ops_content_sku_groups_updated_at on campaign_ops_content_sku_groups;
create trigger set_campaign_ops_content_sku_groups_updated_at before update on campaign_ops_content_sku_groups for each row execute function campaign_ops_set_updated_at();
drop trigger if exists set_campaign_ops_content_skus_updated_at on campaign_ops_content_skus;
create trigger set_campaign_ops_content_skus_updated_at before update on campaign_ops_content_skus for each row execute function campaign_ops_set_updated_at();
drop trigger if exists set_campaign_ops_content_deliverables_updated_at on campaign_ops_content_deliverables;
create trigger set_campaign_ops_content_deliverables_updated_at before update on campaign_ops_content_deliverables for each row execute function campaign_ops_set_updated_at();
drop trigger if exists set_campaign_ops_content_submissions_updated_at on campaign_ops_content_submissions;
create trigger set_campaign_ops_content_submissions_updated_at before update on campaign_ops_content_submissions for each row execute function campaign_ops_set_updated_at();
drop trigger if exists set_campaign_ops_content_monitoring_updates_updated_at on campaign_ops_content_monitoring_updates;
create trigger set_campaign_ops_content_monitoring_updates_updated_at before update on campaign_ops_content_monitoring_updates for each row execute function campaign_ops_set_updated_at();
drop trigger if exists set_campaign_ops_content_invoice_checkpoints_updated_at on campaign_ops_content_invoice_checkpoints;
create trigger set_campaign_ops_content_invoice_checkpoints_updated_at before update on campaign_ops_content_invoice_checkpoints for each row execute function campaign_ops_set_updated_at();
