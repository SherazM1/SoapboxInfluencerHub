from __future__ import annotations

import streamlit as st

from app.campaign_ops.formatting import RISK_LABELS, STATUS_LABELS, WORKFLOW_LABELS, format_date, safe_text
from app.campaign_ops.state import set_selected_program
from app.campaign_ops.task_views import due_state
from core.campaign_ops.enums import TaskStatus
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.models import CampaignOpsUser, TaskListRow
from core.campaign_ops.permissions import can_access_admin
from core.campaign_ops.service import CampaignOpsService


def render_my_work(
    actor: CampaignOpsUser,
    service: CampaignOpsService,
    users: list[CampaignOpsUser],
) -> None:
    st.subheader("My Work")
    include_inactive = st.checkbox("Show inactive tasks", key="campaign_ops_my_work_show_inactive")
    target_user = actor
    if can_access_admin(actor):
        options = {"Me": actor.id, **{user.display_name: user.id for user in users if user.is_active}}
        selected = st.selectbox("Assigned user", list(options), key="campaign_ops_my_work_user_filter")
        target_user_id = options[selected]
    else:
        target_user_id = actor.id
    try:
        tasks = service.list_user_tasks(actor, target_user_id, include_inactive=include_inactive)
    except CampaignOpsError as exc:
        st.error(f"Unable to load My Work: {exc}")
        return
    groups = service.group_user_tasks(tasks)
    rendered_any = False
    for group_name, group_tasks in groups.items():
        with st.expander(f"{group_name} ({len(group_tasks)})", expanded=bool(group_tasks)):
            if not group_tasks:
                st.info("No tasks in this group.")
                continue
            rendered_any = True
            st.dataframe(my_work_rows(group_tasks), hide_index=True, use_container_width=True)
            for task in group_tasks:
                render_my_work_actions(actor, service, task)
    if not rendered_any:
        st.info("No assigned tasks are available for this view.")


def my_work_rows(tasks: list[TaskListRow]) -> list[dict[str, str]]:
    return [
        {
            "Task": task.title,
            "Program": task.program_name,
            "Client": safe_text(task.client_name),
            "Workstream": WORKFLOW_LABELS.get(task.workstream_type or "", "-"),
            "Status": STATUS_LABELS.get(task.status, task.status),
            "Risk": RISK_LABELS.get(task.risk_level, task.risk_level),
            "Due date": format_date(task.due_date),
            "Hard deadline": "Yes" if task.hard_deadline else "No",
            "Priority": safe_text(task.priority),
            "Waiting on": task.waiting_on.replace("_", " ").title(),
            "Responsible party": safe_text(task.responsible_party).replace("_", " ").title(),
            "State": due_state(task),
        }
        for task in tasks
    ]


def render_my_work_actions(
    actor: CampaignOpsUser,
    service: CampaignOpsService,
    task: TaskListRow,
) -> None:
    with st.expander(f"Actions: {task.title}", expanded=False):
        cols = st.columns(4)
        if cols[0].button("Open Program", key=f"campaign_ops_my_work_open_program_{task.id}"):
            set_selected_program(st.session_state, task.program_id)
            st.rerun()
        if task.is_active and task.status != TaskStatus.COMPLETED.value and cols[1].button("Complete", key=f"campaign_ops_my_work_complete_{task.id}"):
            try:
                service.complete_task_record(actor, task.id)
            except CampaignOpsError as exc:
                st.error(f"Task was not completed: {exc}")
                return
            st.success("Task completed.")
            st.rerun()
        if task.is_active and task.status == TaskStatus.COMPLETED.value and cols[2].button("Reopen", key=f"campaign_ops_my_work_reopen_{task.id}"):
            try:
                service.reopen_task(actor, task.id)
            except CampaignOpsError as exc:
                st.error(f"Task was not reopened: {exc}")
                return
            st.success("Task reopened.")
            st.rerun()
        next_status = cols[3].selectbox(
            "Status",
            [item.value for item in TaskStatus],
            index=[item.value for item in TaskStatus].index(task.status),
            format_func=lambda value: value.replace("_", " ").title(),
            key=f"campaign_ops_my_work_status_{task.id}",
        )
        if task.is_active and st.button("Update status", key=f"campaign_ops_my_work_status_submit_{task.id}"):
            try:
                service.change_task_status(actor, task.id, next_status)
            except CampaignOpsError as exc:
                st.error(f"Status was not updated: {exc}")
                return
            st.success("Task status updated.")
            st.rerun()
