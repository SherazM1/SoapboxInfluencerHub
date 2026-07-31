from __future__ import annotations

import streamlit as st

from app.campaign_ops.formatting import WORKFLOW_LABELS, format_datetime, safe_text
from app.campaign_ops.validation import trim_or_none
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.models import CampaignOpsUser, NoteListRow, ProgramWorkspaceSummary
from core.campaign_ops.service import CampaignOpsService


def render_notes(
    actor: CampaignOpsUser,
    service: CampaignOpsService,
    summary: ProgramWorkspaceSummary,
) -> None:
    st.markdown("### Notes")
    cols = st.columns(4)
    if cols[0].button("Add Note", type="primary", key=f"campaign_ops_note_create_button_{summary.program.id}"):
        st.session_state["campaign_ops_note_create_open"] = True
    if cols[1].button("Refresh", key=f"campaign_ops_note_refresh_{summary.program.id}"):
        st.rerun()
    if cols[2].button("Clear filters", key=f"campaign_ops_note_clear_filters_{summary.program.id}"):
        st.session_state["campaign_ops_note_filters"] = {}
        st.rerun()
    newest_first = cols[3].selectbox(
        "Sort",
        ["Newest first", "Oldest first"],
        key="campaign_ops_note_sort_order",
    ) == "Newest first"

    if st.session_state.get("campaign_ops_note_create_open") and summary.program.is_active:
        render_note_form(actor, service, summary)
        st.divider()

    try:
        notes = service.list_program_notes(actor, summary.program.id, newest_first=newest_first)
    except CampaignOpsError as exc:
        st.error(f"Unable to load notes: {exc}")
        return
    filters = render_note_filters(summary, notes)
    filtered = filter_notes(notes, filters)
    if filtered:
        for note in filtered:
            render_note_card(note)
    else:
        st.info("No notes match this view.")


def render_note_form(
    actor: CampaignOpsUser,
    service: CampaignOpsService,
    summary: ProgramWorkspaceSummary,
) -> None:
    with st.form(f"campaign_ops_note_form_{summary.program.id}"):
        note_text = st.text_area("Note", value="")
        workstream_options = {"Program-level": None, **{WORKFLOW_LABELS.get(w.workstream_type, w.workstream_type): w.id for w in summary.workstreams if w.is_active}}
        workstream_label = st.selectbox("Workstream", list(workstream_options))
        task_options = {"No task": None}
        try:
            tasks = service.list_program_tasks(actor, summary.program.id, include_inactive=False)
        except CampaignOpsError:
            tasks = []
        task_options.update({task.title: task.id for task in tasks})
        task_label = st.selectbox("Task", list(task_options))
        is_internal = st.checkbox("Internal", value=False)
        submitted = st.form_submit_button("Add Note", type="primary")
    if not submitted:
        return
    try:
        service.append_program_note(
            actor,
            summary.program.id,
            trim_or_none(note_text) or "",
            workstream_id=workstream_options[workstream_label],
            task_id=task_options[task_label],
            is_internal=is_internal,
        )
        st.session_state["campaign_ops_note_create_open"] = False
        st.success("Note added.")
    except CampaignOpsError as exc:
        st.error(f"Note was not added: {exc}")
        return
    st.rerun()


def render_note_filters(
    summary: ProgramWorkspaceSummary,
    notes: list[NoteListRow],
) -> dict[str, str]:
    current = st.session_state.get("campaign_ops_note_filters")
    if not isinstance(current, dict):
        current = {}
    with st.expander("Note filters", expanded=True):
        cols = st.columns(3)
        workstream_options = {"Any": "", **{WORKFLOW_LABELS.get(w.workstream_type, w.workstream_type): w.id for w in summary.workstreams}}
        current["workstream_id"] = workstream_options[cols[0].selectbox("Workstream", list(workstream_options), key="campaign_ops_note_filter_workstream")]
        task_values = {note.task_title: note.task_id for note in notes if note.task_id and note.task_title}
        task_options = {"Any": "", **task_values}
        current["task_id"] = task_options[cols[1].selectbox("Task", list(task_options), key="campaign_ops_note_filter_task")]
        current["internal"] = cols[2].selectbox("Visibility", ["All", "Internal only", "Public only"], key="campaign_ops_note_filter_internal")
    st.session_state["campaign_ops_note_filters"] = current
    return current


def render_note_card(note: NoteListRow) -> None:
    badge = "Internal" if note.is_internal else "Shared"
    with st.container(border=True):
        st.caption(
            f"{safe_text(note.author_display_name)} | {format_datetime(note.created_at)} | {badge}"
            f" | Workstream: {WORKFLOW_LABELS.get(note.workstream_type or '', '-')}"
            f" | Task: {safe_text(note.task_title)}"
        )
        st.write(note.note_text)


def filter_notes(notes: list[NoteListRow], filters: dict[str, str]) -> list[NoteListRow]:
    result = notes
    if filters.get("workstream_id"):
        result = [item for item in result if item.workstream_id == filters["workstream_id"]]
    if filters.get("task_id"):
        result = [item for item in result if item.task_id == filters["task_id"]]
    if filters.get("internal") == "Internal only":
        result = [item for item in result if item.is_internal]
    if filters.get("internal") == "Public only":
        result = [item for item in result if not item.is_internal]
    return result
