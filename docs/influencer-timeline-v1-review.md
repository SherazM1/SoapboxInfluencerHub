# Influencer timeline workspace V1 review

## PRE-CHANGE STATE

Branch `main`; commit `9b44dadc6127980b0aeb606548af1655ef1e9a73`. Working tree was clean. The preceding Campaign Operations cleanup was already committed. Initial status, full diff and diff-stat were empty; no unrelated changes were present.

## ARCHITECTURE REUSED

One existing campaign record and its existing Influencer planning-step records power every stage. Existing repository CRUD, transaction handling, active-state semantics, user records, assignment authorization and activity events are reused. The shared compact_date helper remains unchanged for other workflows.

## PERSISTENCE DECISION

Rows use `campaign_ops_influencer_planning_steps`: `influencer_campaign_id`, `step_title`, `due_date`, `notes`, `sequence_order`, `is_active`. Ownership uses the campaign?s existing `manager_user_id`; stage uses `influencer_stage`. Other row fields, including descriptions, statuses and historical dates, are preserved. No new table, schema change or migration was needed.

## IMPLEMENTATION SUMMARY

Replaced the three Influencer workspaces with one timeline renderer and lean stage lists. Added an Influencer-specific service facade that composes existing persistence methods. The core product is Owner, Date / Action / Program Notes, row editing and confirmed forward-stage movement.

## INFLUENCER NAVIGATION

Planning, Live and Recapping remain under Influencer. Each list selects active campaigns at exactly that stage. Lists display Campaign, Owner, Next Date, Next Action and Open, plus a small search field. There are no internal workspace tabs or secondary subpages. Completed campaigns leave the active Recapping list.

## NEW CAMPAIGN

The creation form requires an existing accessible program, campaign name and canonical active T/L owner. It always starts in Planning and opens the timeline. Campaign creation and all nine default rows are in one database transaction. A program-row lock serializes creation before the existing duplicate-title check. Defaults have no reseed-on-open path, so refresh, rename, deactivate, owner changes and transitions cannot recreate them.

## PLANNING DEFAULT ROWS

1. Application out to influencers
2. Soapbox to send first round of influencers & brief for review
3. Client to send brief and influencer feedback / approvals
4. Soapbox to hire influencers
5. Influencer drafts are due
6. Influencer resubmissions are due
7. Soapbox to send first round of influencer content for review
8. Client to send content feedback / approvals
9. Influencers begin going live in waves

Exactly nine rows, blank dates and blank Program Notes, with stable template sequence 1?9.

## MASTER ACTION DROPDOWN

1. Application out to influencers
2. Soapbox to send first round of influencers & brief for review
3. Client to send brief and influencer feedback / approvals
4. Soapbox to hire influencers
5. Client to send content / messaging guidelines
6. Soapbox to ship product(s) to influencers
7. Influencer approvals due
8. Scripts & captions due from influencers
9. Soapbox to provide scripts & captions for review
10. Script / caption feedback due
11. Influencer drafts are due
12. Influencer drafts due for internal review
13. Influencer resubmissions are due
14. Soapbox to send first round of influencer content for review
15. Client to send content feedback / approvals
16. Soapbox to send second round of influencer content for review, if needed
17. Final content approval due
18. Display creative sent for approval
19. Display creative approval due
20. Influencers begin going live in waves
21. Campaign Launch
22. Wave Launch
23. Paid Live End
24. Campaign Wrap
25. Ready for Recap
26. EOP Survey Due
27. Reporting Due
28. Recap Draft Due
29. Internal Review
30. Client Review
31. Client Recap
32. Invoice Due
33. Final Close
34. Custom

One centralized library is used by all stages. Optional actions are not seeded. Custom text is stored as the row?s action, so the normal timeline never gains a fourth column. No client-specific reusable labels were added.

## TIMELINE WORKSPACE

The table has exactly Date, Action and Program Notes, with its index hidden. + Add Row opens a compact editor with an action dropdown, a calendar picker, manual notes and Save Row. Existing rows use Edit / Remove Row. Custom conditionally reveals a text input. Save updates the same row; Remove soft-deactivates it. Form-submit callbacks persist before rendering the sorted result and show concise feedback. Blank custom actions fail without partial writes. No separate Program Notes panel, Status, Source or internal ID column is shown.

## DATE SORTING

Active rows sort by (date is blank, date ascending, sequence_order ascending, ID as final deterministic tie-breaker). Dated rows come first; same-date rows retain sequence order. Undated rows come last in template/manual sequence order. Changing dates or inserting a dated row repositions it automatically on save. No manual date reordering is required.

## OWNER

Owner is the first editable campaign control and accepts only existing active T/L records. No Taylor/Lauren users or new ownership persistence are created. Save Owner uses existing campaign update behavior. It never creates assignments or grants program access. The new facade uses existing can_view_program authorization for reads and existing Influencer write checks; it deliberately does not use legacy manager-only read shortcuts to grant access through an owner change.

## PLANNING ? LIVE

Move to Live requires Confirm, with Cancel available. The same locked campaign record changes stage and compatible legacy status. Owner, timeline rows, IDs, dates and notes are preserved. No Live template, checkpoint or campaign copy is created. Stale or repeated confirmations are rejected by the expected-stage check.

## LIVE ? RECAPPING

Move to Recapping requires Confirm. The same campaign changes stage; its timeline remains unchanged. No recap template or second campaign is created. Retired checkpoint, creator-wave, creator and exception readiness prerequisites are intentionally bypassed by this facade. The old readiness-driven transition method remains unchanged for legacy consumers.

## RECAPPING ? COMPLETE

Mark Complete requires Confirm. The campaign?s stage/status becomes complete without deleting or deactivating the campaign or its rows. It leaves the active Recapping list. Old required checkpoints/requirements, creator paid-live completion, final-link/impression completeness and open exceptions are intentionally no longer prerequisites in this UI. Historical recap records and their statuses are not rewritten to pretend those old obligations were completed. An activity event records each simplified forward transition. No backward-stage control was added.

## OLD UI REMOVED

Planning: filter matrices, sequence previews/full-sequence controls, date/status overview form, step management grid and separate notes/activity/timeline tabs. Live: separate renderer, source sequence architecture, waves/checkpoints/exceptions/creator grids and blocker editor. Recapping: separate renderer, filter matrices, checklist/requirements/financial/closeout surfaces and blocker editors. All now share one table workspace. Orphaned Influencer formatting, Live/Recap baseline helpers and renderers were deleted after reference checks.

## OLD BACKEND DATA PRESERVED

Existing creators, summaries, checkpoints, waves, exceptions, approval/content rounds, recap records, requirements, resource relationships and historical activity remain. Existing planning rows are shown without cloning. Campaigns without planning rows display an empty timeline and allow manual additions. Old event timestamps and unrelated workflow records are never imported as timeline obligations. Legacy service/model logic remains unchanged.

## PERMISSIONS

No roles, assignment rules or permission helpers changed. All new writes reuse the existing active-program/Influencer access checks; row IDs are checked against their campaign before edit/removal. Owner changes do not create access. Unauthorized reads, row writes, owner changes and stage changes are covered by tests. Existing database date constraints remain: a legacy row?s due date cannot precede its start date; the editor explains this when applicable.

## PERFORMANCE

A lightweight campaign query filters active rows by stage without creator/resource/recap joins. Planning rows are fetched once in a batch for each list. A workspace reads only its campaign and planning rows plus required authorization data. There are no reads per rendered timeline row. Program authorization lookups are reused within each list for campaigns sharing a program. Row-add ordering and forward transitions use transaction-scoped campaign locks. Default seeding does not re-read authorization for each row.

## FILES CHANGED

Production files:

- `app/campaign_ops/influencer/planning_baseline.py`
- `app/campaign_ops/influencer/views.py`
- `core/campaign_ops/repository.py`

Test files:

- `tests/test_campaign_ops_cleanup.py`
- `tests/test_campaign_ops_import_integrity.py`
- `tests/test_influencer_live_baseline.py`
- `tests/test_influencer_planning_runtime.py`
- `tests/test_influencer_recap_baseline.py`

## FILES DELETED

- `app/campaign_ops/influencer/formatting.py`
- `app/campaign_ops/influencer/live_baseline.py`
- `app/campaign_ops/influencer/live_views.py`
- `app/campaign_ops/influencer/recap_baseline.py`
- `app/campaign_ops/influencer/recap_views.py`

No database, model, legacy service or migration files were deleted.

## FILES NEW / TRACKED STATE

- `core/campaign_ops/influencer_timeline.py`
- `tests/test_influencer_timeline.py`
- `docs/influencer-timeline-v1-review.md`

The existing changed/deleted files remain tracked and unstaged; these three new files are untracked. No commit, push or deployment was performed.

## TESTS

Full pytest: **127 passed, 23 subtests passed**. Full unittest discovery: **127 tests, OK**. New tests cover exact defaults/library, blank dates/notes, T/L ownership, idempotency, CRUD, custom validation, sorting, all stage lists, confirmations/cancel, same-record transitions, history preservation, permission boundaries, lightweight queries, locks and transaction rollback signaling. Existing Campaign Ops foundation, import integrity, performance and other workflow tests pass. Obsolete Influencer presentation tests were replaced; meaningful legacy business-rule tests in the foundation suite remain unchanged.

## VALIDATION

Compiled 63 Python sources in memory. Full pytest and unittest discovery passed. git diff --check passed. Diff review confirmed all production UI edits are within app/campaign_ops/influencer; the only other production edits are the isolated Influencer service facade and three repository methods. Protected schema/config, legacy services/models/permissions, app/main and page routing have no diff.

## DIFF REVIEW

Reviewed status, full diff, diff-stat, removed-module references, new service writes and UI callbacks. Five orphaned Influencer production files were deleted. Three new files are listed above. No unrelated changes, dependencies or bytecode edits are included. The implementation intentionally changes stage-movement business rules only through the new Influencer facade; the old readiness methods are preserved.

## UNCHANGED SYSTEMS

All Programs, My Programs, Retail Media, eCommerce / Content, Insights, Influencer Pricing and standalone Reporting are unchanged. CAMPAIGN_OPS_DATABASE_URL and DATABASE_URL are untouched. No migration or production database operation was run. Existing historical Influencer data is preserved.

## MANUAL DEPLOYMENT CHECK

Streamlit AppTest exercised creation, reopening, owner edits, calendar-date inputs, custom rows, note changes, row removal, confirmation/cancel and all forward transitions. This is local interaction validation, not a live-browser or production-database validation; no browser automation tool was available. After deployment, repeat those actions with an authorized test campaign, verify the same rows/notes/dates across stages, and confirm completion removes it from the active Recapping list while preserving database history.
