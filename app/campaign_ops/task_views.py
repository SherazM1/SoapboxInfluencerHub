from __future__ import annotations

from datetime import UTC, date, datetime

import streamlit as st

from app.campaign_ops.formatting import RISK_LABELS, STATUS_LABELS, WORKFLOW_LABELS, format_date, format_datetime, safe_text
from app.campaign_ops.validation import trim_or_none, validate_date_order
from core.campaign_ops.enums import RiskLevel, TaskStatus, WaitingOn
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.models import CampaignOpsUser, ProgramWorkspaceSummary, TaskListRow
from core.campaign_ops.permissions import can_access_admin
from core.campaign_ops.service import CampaignOpsService, WAITING_TASK_STATUSES

TASK_SORT_OPTIONS = {
    "Sort order": "sort_order",
    "Due date": "due_date",
    "Priority": "priority",
    "Status": "status",
    "Updated date": "updated_at",
    "Created date": "created_at",
    "Assigned user": "assigned_user_name",
    "Workstream": "workstream_type",
}


def due_state(task: TaskListRow, today: date | None = None) -> str:
    today = today or datetime.now(UTC).date()
    if not task.is_active:
        return "Inactive"
    if task.status == TaskStatus.COMPLETED.value:
        return "Completed"
    if task.status == TaskStatus.BLOCKED.value:
        return "Blocked"
    if task.due_date and task.due_date < today:
        return "Overdue"
    if task.due_date == today:
        return "Due today"
    if task.due_date and today < task.due_date <= date.fromordinal(today.toordinal() + 6):
        return "Due soon"
    if task.status in WAITING_TASK_STATUSES or task.waiting_on != WaitingOn.NONE.value:
        return "Waiting"
    if not task.assigned_user_id:
        return "Unassigned"
    return "Open"


def task_table_rows(tasks: list[TaskListRow]) -> list[dict[str, str]]:
    return [
        {
            "Task title": task.title,
            "Workstream": WORKFLOW_LABELS.get(task.workstream_type or "", "-"),
            "Assigned user": safe_text(task.assigned_user_name),
            "Responsible party": _waiting_label(task.responsible_party),
            "Status": STATUS_LABELS.get(task.status, task.status),
            "Risk": RISK_LABELS.get(task.risk_level, task.risk_level),
            "Waiting on": _waiting_label(task.waiting_on),
            "Start date": format_date(task.start_date),
            "Due date": format_date(task.due_date),
            "Hard deadline": "Yes" if task.hard_deadline else "No",
            "Priority": safe_text(task.priority),
            "State": due_state(task),
            "Active": "Yes" if task.is_active else "No",
            "Updated date": format_datetime(task.updated_at),
        }
        for task in tasks
    ]


def render_program_tasks(
    actor: CampaignOpsUser,
    service: CampaignOpsService,
    summary: ProgramWorkspaceSummary,
) -> None:
    st.markdown("### Tasks")
    include_inactive = st.checkbox("Show inactive tasks", key="campaign_ops_task_show_inactive")
    cols = st.columns(3)
    if cols[0].button("Refresh", key=f"campaign_ops_task_refresh_{summary.program.id}"):
        st.rerun()
    if cols[1].button("Clear filters", key=f"campaign_ops_task_clear_filters_{summary.program.id}"):
        st.session_state["campaign_ops_task_filters"] = {}
        st.rerun()
    can_add = can_access_admin(actor) and summary.program.is_active
    if can_add and cols[2].button("Add Task", type="primary", key=f"campaign_ops_task_create_open_{summary.program.id}"):
        st.session_state["campaign_ops_task_create_open"] = True

    if st.session_state.get("campaign_ops_task_create_open") and can_add:
        render_task_form(actor, service, summary, None)
        st.divider()

    try:
        tasks = service.list_program_tasks(actor, summary.program.id, include_inactive=include_inactive)
    except CampaignOpsError as exc:
        st.error(f"Unable to load tasks: {exc}")
        return

    filters = render_task_filters(summary)
    filtered = filter_tasks(tasks, filters)
    sorted_tasks = sort_tasks(filtered, filters.get("sort_by", "sort_order"))
    if sorted_tasks:
        st.dataframe(task_table_rows(sorted_tasks), hide_index=True, use_container_width=True)
    else:
        st.info("No tasks match this view.")

    for task in sorted_tasks:
        render_task_actions(actor, service, summary, task)


def render_task_filters(summary: ProgramWorkspaceSummary) -> dict[str, str]:
    current = st.session_state.get("campaign_ops_task_filters")
    if not isinstance(current, dict):
        current = {}
    with st.expander("Task filters", expanded=True):
        cols = st.columns(4)
        current["search"] = cols[0].text_input("Search", value=str(current.get("search", "")), key="campaign_ops_task_filter_search")
        workstream_options = {"Any": "", **{WORKFLOW_LABELS.get(w.workstream_type, w.workstream_type): w.id for w in summary.workstreams}}
        current["workstream_id"] = workstream_options[cols[1].selectbox("Workstream", list(workstream_options), key="campaign_ops_task_filter_workstream")]
        user_options = {"Any": "", **{u.display_name: u.id for u in summary.users if u.is_active}}
        current["assigned_user_id"] = user_options[cols[2].selectbox("Assigned user", list(user_options), key="campaign_ops_task_filter_user")]
        current["sort_by"] = TASK_SORT_OPTIONS[cols[3].selectbox("Sort", list(TASK_SORT_OPTIONS), key="campaign_ops_task_filter_sort")]
        cols = st.columns(4)
        current["status"] = _enum_filter(cols[0], "Status", STATUS_LABELS, "campaign_ops_task_filter_status")
        current["risk_level"] = _enum_filter(cols[1], "Risk", RISK_LABELS, "campaign_ops_task_filter_risk")
        current["responsible_party"] = _enum_filter(cols[2], "Responsible party", _waiting_labels(), "campaign_ops_task_filter_party")
    st.session_state["campaign_ops_task_filters"] = current
    return current


def render_task_form(
    actor: CampaignOpsUser,
    service: CampaignOpsService,
    summary: ProgramWorkspaceSummary,
    task: TaskListRow | None,
) -> None:
    form_key = f"campaign_ops_task_form_{task.id if task else 'new'}"
    with st.form(form_key):
        title = st.text_input("Title", value=task.title if task else "")
        description = st.text_area("Description", value=task.description or "" if task else "")
        workstream_options = {"Program-level": None, **{WORKFLOW_LABELS.get(w.workstream_type, w.workstream_type): w.id for w in summary.workstreams if w.is_active or (task and task.workstream_id == w.id)}}
        current_ws = next((label for label, value in workstream_options.items() if task and value == task.workstream_id), "Program-level")
        assigned_options = {"Unassigned": None, **{u.display_name: u.id for u in summary.users if u.is_active}}
        current_assignee = next((label for label, value in assigned_options.items() if task and value == task.assigned_user_id), "Unassigned")
        cols = st.columns(3)
        workstream_label = cols[0].selectbox("Workstream", list(workstream_options), index=list(workstream_options).index(current_ws))
        assigned_label = cols[1].selectbox("Assigned user", list(assigned_options), index=list(assigned_options).index(current_assignee))
        responsible_party = _enum_select(cols[2], "Responsible party", _waiting_labels(), task.responsible_party if task else WaitingOn.INTERNAL_TEAM.value)
        cols = st.columns(3)
        status = _enum_select(cols[0], "Status", STATUS_LABELS, task.status if task else TaskStatus.NOT_STARTED.value)
        risk = _enum_select(cols[1], "Risk", RISK_LABELS, task.risk_level if task else RiskLevel.UNRATED.value)
        waiting_on = _enum_select(cols[2], "Waiting on", _waiting_labels(), task.waiting_on if task else WaitingOn.NONE.value)
        cols = st.columns(4)
        start_date = cols[0].date_input("Start date", value=task.start_date if task else None)
        due_date = cols[1].date_input("Due date", value=task.due_date if task else None)
        hard_deadline = cols[2].checkbox("Hard deadline", value=task.hard_deadline if task else False)
        sort_order = cols[3].number_input("Sort order", min_value=0, max_value=100000, value=task.sort_order if task else 0)
        priority = st.text_input("Priority", value=task.priority or "" if task else "")
        submitted = st.form_submit_button("Save Task" if task else "Create Task", type="primary")
    if not submitted:
        return
    error = validate_date_order(start_date, due_date)
    if error:
        st.error(error)
        return
    try:
        payload = {
            "description": trim_or_none(description),
            "workstream_id": workstream_options[workstream_label],
            "assigned_user_id": assigned_options[assigned_label],
            "responsible_party": responsible_party,
            "status": status,
            "risk_level": risk,
            "waiting_on": waiting_on,
            "start_date": start_date,
            "due_date": due_date,
            "hard_deadline": hard_deadline,
            "priority": trim_or_none(priority),
            "sort_order": int(sort_order),
        }
        if task:
            service.update_task_details(actor, task.id, title=title, **payload)
            st.session_state.pop("campaign_ops_task_edit_id", None)
            st.success("Task updated.")
        else:
            service.create_task_record(actor, summary.program.id, title=title, **payload)
            st.session_state["campaign_ops_task_create_open"] = False
            st.success("Task created.")
    except CampaignOpsError as exc:
        st.error(f"Task was not saved: {exc}")
        return
    st.rerun()


def render_task_actions(
    actor: CampaignOpsUser,
    service: CampaignOpsService,
    summary: ProgramWorkspaceSummary,
    task: TaskListRow,
) -> None:
    with st.expander(f"Task actions: {task.title}", expanded=False):
        render_task_form(actor, service, summary, task)
        cols = st.columns(4)
        next_status = _enum_select(cols[0], "Move to", STATUS_LABELS, task.status, key=f"campaign_ops_task_status_action_id_{task.id}")
        if task.is_active and cols[1].button("Update status", key=f"campaign_ops_task_status_submit_{task.id}"):
            try:
                service.change_task_status(actor, task.id, next_status)
            except CampaignOpsError as exc:
                st.error(f"Status was not updated: {exc}")
                return
            st.success("Task status updated.")
            st.rerun()
        if task.is_active and task.status != TaskStatus.COMPLETED.value and cols[2].button("Complete", key=f"campaign_ops_task_complete_{task.id}"):
            try:
                service.complete_task_record(actor, task.id)
            except CampaignOpsError as exc:
                st.error(f"Task was not completed: {exc}")
                return
            st.success("Task completed.")
            st.rerun()
        if task.is_active and task.status in {TaskStatus.COMPLETED.value, TaskStatus.NOT_APPLICABLE.value} and cols[2].button("Reopen", key=f"campaign_ops_task_reopen_id_{task.id}"):
            try:
                service.reopen_task(actor, task.id)
            except CampaignOpsError as exc:
                st.error(f"Task was not reopened: {exc}")
                return
            st.success("Task reopened.")
            st.rerun()
        if task.is_active and cols[3].button("Deactivate", key=f"campaign_ops_task_deactivate_id_{task.id}"):
            try:
                service.deactivate_task_record(actor, task.id)
            except CampaignOpsError as exc:
                st.error(f"Task was not deactivated: {exc}")
                return
            st.success("Task deactivated.")
            st.rerun()
        if not task.is_active and cols[3].button("Reactivate", key=f"campaign_ops_task_reactivate_id_{task.id}"):
            try:
                service.reactivate_task_record(actor, task.id)
            except CampaignOpsError as exc:
                st.error(f"Task was not reactivated: {exc}")
                return
            st.success("Task reactivated.")
            st.rerun()


def filter_tasks(tasks: list[TaskListRow], filters: dict[str, str]) -> list[TaskListRow]:
    result = tasks
    search = (filters.get("search") or "").strip().lower()
    if search:
        result = [task for task in result if search in task.title.lower()]
    for field in ("workstream_id", "assigned_user_id", "status", "risk_level", "responsible_party"):
        value = filters.get(field)
        if value:
            result = [task for task in result if getattr(task, field) == value]
    return result


def sort_tasks(tasks: list[TaskListRow], sort_by: str) -> list[TaskListRow]:
    return sorted(
        tasks,
        key=lambda task: (
            getattr(task, sort_by, None) is None,
            str(getattr(task, sort_by, "") or ""),
            task.title.lower(),
        ),
    )


def _waiting_labels() -> dict[str, str]:
    return {item.value: item.value.replace("_", " ").title() for item in WaitingOn}


def _enum_filter(container: object, label: str, label_map: dict[str, str], key: str) -> str:
    labels = ["Any", *label_map.values()]
    values = {"Any": "", **{display: value for value, display in label_map.items()}}
    return values[container.selectbox(label, labels, key=key)]


def _enum_select(container: object, label: str, label_map: dict[str, str], current: str | None, key: str | None = None) -> str:
    labels = list(label_map.values())
    values = {display: value for value, display in label_map.items()}
    current_label = label_map.get(current or "", labels[0])
    return values[container.selectbox(label, labels, index=labels.index(current_label), key=key)]
