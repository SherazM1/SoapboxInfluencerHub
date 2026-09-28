# Campaign Operations cleanup review

## PRE-CHANGE STATE

Branch: `main`. Commit: `6595cc0a5366d8c3fed6c2eb8b56f9f31a51faa6`. The only pre-existing change was `app/main.py` (hub card renamed to Program Tracker). Its bytes remain unchanged; SHA-256: `EFE2E7C1F789A6813066F06EBA4D912C6380597A48002604C1A1E96C3BC808BC`.

## IMPLEMENTATION SUMMARY

Completed the UI cleanup. Removed obsolete pages, internal tracker surfaces, link-heavy panels, duplicate portfolio presentations, and orphaned UI helpers. No new timeline editor, deadline model, schema, or replacement page was built.

## NAVIGATION AFTER CLEANUP

Programs: All Programs, My Programs. Workflows: Influencer, Retail Media, eCommerce / Content, Insights. These six buttons are verified by Streamlit AppTest. Bailey can access My Programs; existing service permissions remain authoritative.

## REMOVED SECTIONS

Cross-Team, My Work, Requests (Survey Requests, Reporting Requests, All Requests, New Request), and Administration. Removed routing/import integration and orphan UI modules. The existing New Program action remains administrator-only; its state now survives reruns.

## PROGRAM WORKSPACE CLEANUP

One portfolio table replaces Table/Cards duplication. Workspace tabs are Overview, Tasks, Timeline, Notes, Team, Activity. Workstreams and lightweight read-only Links moved to collapsed Overview expanders. Notes and activity are collapsed. Program access and assignments retain existing semantics.

## INFLUENCER PLANNING CLEANUP

Retained Overview, Planning Sequence, Timeline, Program Notes, Activity. Removed approvals/content-round/creator-summary tracker UI, resources, linked sheets, counts and invoice amount controls, and duplicate portfolio summary. Existing planning dates and sequence editors remain.

## INFLUENCER LIVE CLEANUP

Retained Overview, Live Checkpoints, Creator Waves, Exceptions, Timeline, Program Notes, Activity. Removed creator grid, impression-heavy browsing, resources, quick links, and duplicate summary. A collapsed Advanced / Resolve creator blocker editor updates one existing creator through the existing authorized service, including status, required impressions, final link, and live dates.

## INFLUENCER RECAPPING CLEANUP

Retained Overview, Recap Checklist, Timeline, Program Notes, Activity and compact collapsed Financial status. Removed full requirements, creator closeout, product/retailer launch and resources grids. A collapsed requirement editor preserves relationship IDs and required flags. Blocked recap campaigns can explicitly return to Live to resolve creator/exception blockers; existing recap records survive the round trip. The financial form no longer references invoice_amount, which was absent from its portfolio summary model. Readiness and completion rules are unchanged.

## CONTENT MANAGEMENT CLEANUP

Retained Overview, Deliverables, Submission & Publication, Invoicing, Timeline, Notes, Activity. Removed SKU groups/products, Copy & Attributes, Graphics / Assets, Monitoring & Maintenance detail, resource panels, redundant baseline tracker, and summary. Preserved dated editors, monitoring/maintenance dates, next action and issue summaries. Removed fields are omitted from updates so existing stored values remain.

## RETAIL MEDIA CLEANUP

Retained Overview, Activations / Flights, Creative & Approvals, Timeline, Notes, Activity. Removed channel-detail, Budget & Spend, Optimization Log, resource, baseline tracker and duplicate summary surfaces. Budget attention calculations remain. Existing activation and approval date editors remain.

## INSIGHTS CLEANUP

Retained Overview, Timeline, Activity, project identity, ownership/status and next milestone date. Removed research objectives, budget/sample/program-cost controls, resource UI, workbook/baseline tables and duplicate summary. Shared milestone infrastructure remains.

## EXTERNAL / LINKED SHEETS REMOVED

Removed specialized workflow Quick Links / Linked Sheets and resource-heavy editors. Existing program links remain available only as lightweight read-only buttons in a collapsed Links area. Stored URLs/resources remain.

## INTERNAL TRACKER UI REMOVED

See the exact removed tabs and renderer inventory below. Minimal creator and recap requirement resolution remains available without restoring full trackers.

## DUPLICATE SUMMARIES REMOVED

Removed the secondary portfolio summaries/selectors from Planning, Live, Recapping, Content, Retail Media and Insights. Open actions remain on the primary cards. All Programs/My Programs use one table presentation.

## BACKEND LOGIC PRESERVED

No core/campaign_ops files changed. Models, repository/services, assignments, authorization, ownership, lifecycle transitions, influencer creator readiness and recap completion, reporting-request relationships, SKU-derived calculations, retail budget attention, shared tasks/milestones/timeline, resources, notes and activity persistence remain.

## DATA / SCHEMA PRESERVED

No database configuration, schema, migrations or production data were changed. No migrations, deployment, production edits, commit or push were performed. CAMPAIGN_OPS_DATABASE_URL and DATABASE_URL remain separate and untouched.

## ROUTING / STATE CLEANUP

Retired section values reset to a valid default before querying/rendering. Legacy request/cross-team/My Work state is discarded. Unsupported specialized routes are rejected. Obsolete state declarations were removed; legacy editor keys remain solely for clearing older sessions. Historical activity filtering for Reporting Requests remains because history is intentionally preserved.

## FILES DELETED

- `app/campaign_ops/cross_team/__init__.py`
- `app/campaign_ops/cross_team/formatting.py`
- `app/campaign_ops/cross_team/views.py`
- `app/campaign_ops/influencer/recap_formatting.py`
- `app/campaign_ops/personal_views.py`
- `app/campaign_ops/reporting_requests/__init__.py`
- `app/campaign_ops/reporting_requests/formatting.py`
- `app/campaign_ops/reporting_requests/views.py`

## FILES CHANGED

- `app/campaign_ops/components.py`
- `app/campaign_ops/content_management/baseline.py`
- `app/campaign_ops/content_management/formatting.py`
- `app/campaign_ops/content_management/views.py`
- `app/campaign_ops/influencer/formatting.py`
- `app/campaign_ops/influencer/live_baseline.py`
- `app/campaign_ops/influencer/live_views.py`
- `app/campaign_ops/influencer/planning_baseline.py`
- `app/campaign_ops/influencer/recap_baseline.py`
- `app/campaign_ops/influencer/recap_views.py`
- `app/campaign_ops/influencer/views.py`
- `app/campaign_ops/insights/baseline.py`
- `app/campaign_ops/insights/formatting.py`
- `app/campaign_ops/insights/views.py`
- `app/campaign_ops/program_list.py`
- `app/campaign_ops/program_workspace.py`
- `app/campaign_ops/resource_views.py`
- `app/campaign_ops/retail_media/baseline.py`
- `app/campaign_ops/retail_media/formatting.py`
- `app/campaign_ops/retail_media/views.py`
- `app/campaign_ops/state.py`
- `app/campaign_ops/ui/navigation.py`
- `app/pages/campaigns.py`
- `tests/test_campaign_ops_foundation.py`
- `tests/test_campaign_ops_import_integrity.py`
- `tests/test_content_management_baseline.py`
- `tests/test_influencer_live_baseline.py`
- `tests/test_influencer_planning_runtime.py`
- `tests/test_influencer_recap_baseline.py`
- `tests/test_insights_baseline.py`
- `tests/test_retail_media_baseline.py`

## FILES NEW / UNTRACKED

- `tests/test_campaign_ops_cleanup.py`
- `docs/campaign-ops-cleanup-review.md`

## TESTS

Full pytest: **126 passed, 32 subtests passed**. Full unittest discovery: **126 tests, OK**. Coverage includes foundation, permissions/ownership, import integrity, performance, Planning, Live, Recap/readiness, Content, Retail and Insights. New Streamlit checks cover seven workspaces, eight portfolios, four creation forms, exact navigation, stale routes, creator/requirement saves and recap-to-Live record preservation. Removed tests asserted intentionally deleted UI; backend lifecycle and relationship tests remain. Test setup was isolated from the real database.

## VALIDATION

Compiled 66 Python sources in memory without writing bytecode. Full pytest and unittest passed. git diff --check passed. Protected core/db/Pricing/Reporting paths have no diff. Pre-existing app/main.py hash is unchanged. Pytest was installed into the local virtual environment with approved package access; dependency manifests were not changed.

## DIFF REVIEW

Reviewed the complete diff, removed definitions, surviving tabs, imports, partial-update payloads, routing and status. The only unrelated change is the pre-existing app/main.py edit, left untouched. Generated tracked bytecode was restored to its original bytes. Changes remain uncommitted. The two new files listed above are the only intended untracked files.

## UNCHANGED SYSTEMS

CAMPAIGN_OPS_DATABASE_URL, DATABASE_URL, Influencer Pricing, standalone Reporting, schema, migrations, production data, assignments/permissions, Tasks, Milestones, Timeline and lifecycle readiness are unchanged.

## MANUAL DEPLOYMENT CHECK

Local Streamlit test rendering confirms exactly All Programs, My Programs, Influencer, Retail Media, eCommerce / Content, Insights; removed entries are absent. Surviving workspaces and portfolio screens render with the reduced tabs/panels. No deployment or live-browser production check was performed. After deployment, verify the six menu entries for Bailey/T/L, open each workflow with representative existing records, check dates/tasks/milestones, and exercise creator/requirement blocker resolution with authorized test records.

## Exact removed tabs

- `app/campaign_ops/content_management/views.py`: SKU Groups, SKUs / Products, Copy & Attributes, Graphics / Assets, Monitoring & Maintenance, Resources.
- `app/campaign_ops/influencer/live_views.py`: Creator Live Status, Resources.
- `app/campaign_ops/influencer/recap_views.py`: Reporting & Analysis, Product / Retailer Launches, Creator Closeout, Invoice & Financial Close, Resources.
- `app/campaign_ops/influencer/views.py`: Approvals, Content Rounds, Creator Summary, Resources.
- `app/campaign_ops/insights/views.py`: Research Objectives, Resources.
- `app/campaign_ops/program_workspace.py`: Workstreams, Resources.
- `app/campaign_ops/retail_media/views.py`: Channels, Budget & Spend, Optimization Log, Resources.

## Exact removed renderer definitions

- `app/campaign_ops/components.py`: `render_placeholder`.
- `app/campaign_ops/content_management/views.py`: `render_content_baseline_tracker`, `render_copy_attributes`, `render_graphics`, `render_monitoring`, `render_program_block`, `render_resources`, `render_sku_groups`, `render_skus`.
- `app/campaign_ops/cross_team/views.py`: `render_cross_team_dashboard`.
- `app/campaign_ops/influencer/live_views.py`: `render_creators`, `render_resources`.
- `app/campaign_ops/influencer/recap_views.py`: `render_creator_closeout`, `render_launch_items`, `render_requirements`, `render_resources`.
- `app/campaign_ops/influencer/views.py`: `render_approvals`, `render_content_rounds`, `render_creator_summary`, `render_resources`.
- `app/campaign_ops/insights/views.py`: `render_insights_baseline_tracker`, `render_insights_resource_form`, `render_objectives`, `render_resources`, `render_workbook_table`.
- `app/campaign_ops/personal_views.py`: `render_my_work`, `render_my_work_actions`.
- `app/campaign_ops/reporting_requests/views.py`: `render_deadline_summary`, `render_detail_text_blocks`, `render_filters`, `render_reporting_requests`, `render_request_detail`, `render_request_form`, `render_request_selector`, `render_request_state_actions`, `render_section_table`, `render_workbook_css`.
- `app/campaign_ops/resource_views.py`: `render_resource_actions`, `render_resource_filters`, `render_resource_form`.
- `app/campaign_ops/retail_media/views.py`: `render_budget`, `render_campaign_block`, `render_channels`, `render_optimization`, `render_resources`, `render_retail_media_baseline_tracker`.
- `app/pages/campaigns.py`: `render_cross_team_intro`.
