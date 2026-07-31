from __future__ import annotations

from datetime import UTC, date, datetime

import streamlit as st

from app.campaign_ops.formatting import TASK_STATUS_LABELS, WORKFLOW_LABELS, format_date, format_datetime, safe_text, title_label
from app.campaign_ops.validation import trim_or_none
from core.campaign_ops.enums import TaskStatus
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.models import CampaignOpsUser, MilestoneListRow, ProgramWorkspaceSummary
from core.campaign_ops.permissions import can_access_admin
from core.campaign_ops.service import CampaignOpsService, WAITING_TASK_STATUSES

MILESTONE_SORT_OPTIONS = {
    "Best available date": "best_date",
    "Target date": "target_date",
    "Start date": "start_date",
    "End date": "end_date",
    "Status": "status",
    "Owner": "owner_user_name",
    "Updated date": "updated_at",
    "Created date": "created_at",
}

MILESTONE_TYPES = [
    "Client Approval",
    "Retailer Submission",
    "Launch",
    "Content Due",
    "Reporting",
    "Billing",
    "Custom",
]


def best_milestone_date(milestone: MilestoneListRow) -> date | None:
    return milestone.target_date or milestone.start_date or milestone.end_date


def milestone_due_state(milestone: MilestoneListRow, today: date | None = None) -> str:
    today = today or datetime.now(UTC).date()
    due = best_milestone_date(milestone)
    if not milestone.is_active:
        return "Inactive"
    if milestone.status == TaskStatus.COMPLETED.value:
        return "Completed"
    if milestone.status == TaskStatus.BLOCKED.value:
        return "Blocked"
    if milestone.status in WAITING_TASK_STATUSES:
        return "Waiting"
    if due is None:
        return "Undated"
    if due < today:
        return "Overdue"
    if due == today:
        return "Due today"
    if due <= date.fromordinal(today.toordinal() + 6):
        return "Due soon"
    return "Open"


def render_timeline(
    actor: CampaignOpsUser,
    service: CampaignOpsService,
    summary: ProgramWorkspaceSummary,
) -> None:
    st.markdown("### Timeline")
    cols = st.columns(4)
    include_inactive = cols[0].checkbox("Show inactive milestones", key="campaign_ops_milestone_show_inactive")
    if cols[1].button("Refresh", key=f"campaign_ops_milestone_refresh_{summary.program.id}"):
        st.rerun()
    if cols[2].button("Clear filters", key=f"campaign_ops_milestone_clear_filters_{summary.program.id}"):
        st.session_state["campaign_ops_milestone_filters"] = {}
        st.rerun()
    can_add = can_access_admin(actor) and summary.program.is_active
    if can_add and cols[3].button("Add Milestone", type="primary", key=f"campaign_ops_milestone_create_button_{summary.program.id}"):
        st.session_state["campaign_ops_milestone_create_open"] = True

    if st.session_state.get("campaign_ops_milestone_create_open") and can_add:
        render_milestone_form(actor, service, summary, None)
        st.divider()

    try:
        milestones = service.list_program_milestones(actor, summary.program.id, include_inactive=include_inactive)
    except CampaignOpsError as exc:
        st.error(f"Unable to load milestones: {exc}")
        return

    filters = render_milestone_filters(summary)
    filtered = sort_milestones(filter_milestones(milestones, filters), filters.get("sort_by", "best_date"))
    if filtered:
        st.dataframe(milestone_table_rows(filtered), hide_index=True, use_container_width=True)
    else:
        st.info("No milestones match this view.")

    for milestone in filtered:
        render_milestone_actions(actor, service, summary, milestone)


def render_milestone_filters(summary: ProgramWorkspaceSummary) -> dict[str, str]:
    current = st.session_state.get("campaign_ops_milestone_filters")
    if not isinstance(current, dict):
        current = {}
    with st.expander("Timeline filters", expanded=True):
        cols = st.columns(4)
        current["search"] = cols[0].text_input("Search", value=str(current.get("search", "")), key="campaign_ops_milestone_filter_search")
        workstream_options = {"Any": "", **{WORKFLOW_LABELS.get(w.workstream_type, w.workstream_type): w.id for w in summary.workstreams}}
        current["workstream_id"] = workstream_options[cols[1].selectbox("Workstream", list(workstream_options), key="campaign_ops_milestone_filter_workstream")]
        owner_options = {"Any": "", **{u.display_name: u.id for u in summary.users if u.is_active}}
        current["owner_user_id"] = owner_options[cols[2].selectbox("Owner", list(owner_options), key="campaign_ops_milestone_filter_owner")]
        current["sort_by"] = MILESTONE_SORT_OPTIONS[cols[3].selectbox("Sort", list(MILESTONE_SORT_OPTIONS), key="campaign_ops_milestone_filter_sort")]
        current["status"] = _enum_filter(st, "Status", TASK_STATUS_LABELS, "campaign_ops_milestone_filter_status")
    st.session_state["campaign_ops_milestone_filters"] = current
    return current


def render_milestone_form(
    actor: CampaignOpsUser,
    service: CampaignOpsService,
    summary: ProgramWorkspaceSummary,
    milestone: MilestoneListRow | None,
) -> None:
    form_key = f"campaign_ops_milestone_form_{milestone.id if milestone else 'new'}"
    with st.form(form_key):
        title = st.text_input("Title", value=milestone.title if milestone else "")
        current_type = milestone.milestone_type or "Custom" if milestone else "Custom"
        type_options = list(dict.fromkeys([current_type, *MILESTONE_TYPES]))
        milestone_type = st.selectbox("Milestone type", type_options, index=type_options.index(current_type))
        workstream_options = {"Program-level": None, **{WORKFLOW_LABELS.get(w.workstream_type, w.workstream_type): w.id for w in summary.workstreams if w.is_active or (milestone and milestone.workstream_id == w.id)}}
        current_ws = next((label for label, value in workstream_options.items() if milestone and value == milestone.workstream_id), "Program-level")
        owner_options = {"Unassigned": None, **{u.display_name: u.id for u in summary.users if u.is_active or (milestone and u.id == milestone.owner_user_id)}}
        current_owner = next((label for label, value in owner_options.items() if milestone and value == milestone.owner_user_id), "Unassigned")
        cols = st.columns(3)
        workstream_label = cols[0].selectbox("Workstream", list(workstream_options), index=list(workstream_options).index(current_ws))
        owner_label = cols[1].selectbox("Owner", list(owner_options), index=list(owner_options).index(current_owner))
        status = _enum_select(cols[2], "Status", TASK_STATUS_LABELS, milestone.status if milestone else TaskStatus.NOT_STARTED.value)
        cols = st.columns(4)
        start_date = cols[0].date_input("Start date", value=milestone.start_date if milestone else None)
        target_date = cols[1].date_input("Target date", value=milestone.target_date if milestone else None)
        end_date = cols[2].date_input("End date", value=milestone.end_date if milestone else None)
        hard_deadline = cols[3].checkbox("Hard deadline", value=milestone.hard_deadline if milestone else False)
        submitted = st.form_submit_button("Save Milestone" if milestone else "Create Milestone", type="primary")
    if not submitted:
        return
    try:
        payload = {
            "milestone_type": trim_or_none(milestone_type),
            "workstream_id": workstream_options[workstream_label],
            "owner_user_id": owner_options[owner_label],
            "status": status,
            "start_date": start_date,
            "target_date": target_date,
            "end_date": end_date,
            "hard_deadline": hard_deadline,
        }
        if milestone:
            service.update_milestone_details(actor, milestone.id, title=title, **payload)
            st.session_state.pop("campaign_ops_milestone_edit_id", None)
            st.success("Milestone updated.")
        else:
            service.create_milestone(actor, summary.program.id, title=title, **payload)
            st.session_state["campaign_ops_milestone_create_open"] = False
            st.success("Milestone created.")
    except CampaignOpsError as exc:
        st.error(f"Milestone was not saved: {exc}")
        return
    st.rerun()


def render_milestone_actions(
    actor: CampaignOpsUser,
    service: CampaignOpsService,
    summary: ProgramWorkspaceSummary,
    milestone: MilestoneListRow,
) -> None:
    with st.expander(f"Milestone actions: {milestone.title}", expanded=False):
        render_milestone_form(actor, service, summary, milestone)
        cols = st.columns(4)
        if milestone.is_active and milestone.status != TaskStatus.COMPLETED.value and cols[0].button("Complete", key=f"campaign_ops_milestone_complete_id_{milestone.id}"):
            _run_milestone_action(service.complete_milestone, actor, milestone.id, "Milestone completed.")
        if milestone.is_active and milestone.status == TaskStatus.COMPLETED.value and cols[1].button("Reopen", key=f"campaign_ops_milestone_reopen_id_{milestone.id}"):
            _run_milestone_action(service.reopen_milestone, actor, milestone.id, "Milestone reopened.")
        if milestone.is_active and cols[2].button("Deactivate", key=f"campaign_ops_milestone_deactivate_id_{milestone.id}"):
            _run_milestone_action(service.deactivate_milestone, actor, milestone.id, "Milestone deactivated.")
        if not milestone.is_active and cols[3].button("Reactivate", key=f"campaign_ops_milestone_reactivate_id_{milestone.id}"):
            _run_milestone_action(service.reactivate_milestone, actor, milestone.id, "Milestone reactivated.")


def milestone_table_rows(milestones: list[MilestoneListRow]) -> list[dict[str, str]]:
    return [
        {
            "Milestone title": milestone.title,
            "Type": safe_text(milestone.milestone_type),
            "Workstream": WORKFLOW_LABELS.get(milestone.workstream_type or "", "-"),
            "Owner": safe_text(milestone.owner_user_name),
            "Status": TASK_STATUS_LABELS.get(milestone.status, title_label(milestone.status)),
            "Start date": format_date(milestone.start_date),
            "Target date": format_date(milestone.target_date),
            "End date": format_date(milestone.end_date),
            "Hard deadline": "Yes" if milestone.hard_deadline else "No",
            "State": milestone_due_state(milestone) + (" / Hard deadline" if milestone.hard_deadline else ""),
            "Active state": "Active" if milestone.is_active else "Inactive",
            "Updated date": format_datetime(milestone.updated_at),
        }
        for milestone in milestones
    ]


def filter_milestones(milestones: list[MilestoneListRow], filters: dict[str, str]) -> list[MilestoneListRow]:
    result = milestones
    search = (filters.get("search") or "").strip().lower()
    if search:
        result = [item for item in result if search in item.title.lower() or search in (item.milestone_type or "").lower()]
    for field in ("workstream_id", "owner_user_id", "status"):
        value = filters.get(field)
        if value:
            result = [item for item in result if getattr(item, field) == value]
    return result


def sort_milestones(milestones: list[MilestoneListRow], sort_by: str) -> list[MilestoneListRow]:
    def key(milestone: MilestoneListRow) -> tuple[object, ...]:
        value = best_milestone_date(milestone) if sort_by == "best_date" else getattr(milestone, sort_by, None)
        return (value is None, value or "", milestone.title.lower())
    return sorted(milestones, key=key)


def _run_milestone_action(action: object, actor: CampaignOpsUser, milestone_id: str, success: str) -> None:
    try:
        action(actor, milestone_id)
    except CampaignOpsError as exc:
        st.error(f"Milestone action failed: {exc}")
        return
    st.success(success)
    st.rerun()


def _enum_filter(container: object, label: str, label_map: dict[str, str], key: str) -> str:
    labels = ["Any", *label_map.values()]
    values = {"Any": "", **{display: value for value, display in label_map.items()}}
    return values[container.selectbox(label, labels, key=key)]


def _enum_select(container: object, label: str, label_map: dict[str, str], current: str | None, key: str | None = None) -> str:
    labels = list(label_map.values())
    values = {display: value for value, display in label_map.items()}
    current_label = label_map.get(current or "", labels[0])
    return values[container.selectbox(label, labels, index=labels.index(current_label), key=key)]
