from __future__ import annotations

import streamlit as st

from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.influencer_timeline import (
    ACTION_LIBRARY, FORWARD_STAGES, STAGE_LABELS, InfluencerTimelineService, sort_timeline,
)

SELECTED = "campaign_ops_selected_influencer_campaign_id"
PENDING = "campaign_ops_influencer_timeline_navigation"
FLASH = "campaign_ops_influencer_timeline_message"


def _saved(message):
    st.session_state[FLASH] = message
    st.rerun()


def _open_campaign(campaign_id):
    st.session_state[SELECTED] = campaign_id


def _back_to_campaigns():
    st.session_state.pop(SELECTED, None)


def render_influencer(actor, service, users):
    service = InfluencerTimelineService(service.repository)
    pending = st.session_state.pop(PENDING, None)
    if pending:
        st.session_state["campaign_ops_influencer_view"] = pending
    st.subheader("Influencer")
    label = st.radio("Influencer workspace", list(STAGE_LABELS.values()), horizontal=True,
                     key="campaign_ops_influencer_view")
    stage = next(key for key, value in STAGE_LABELS.items() if value == label)
    error = st.session_state.pop(FLASH + "_error", None)
    if error:
        st.error(error)
    message = st.session_state.pop(FLASH, None)
    if message:
        st.success(message)
    selected = st.session_state.get(SELECTED)
    try:
        if selected:
            campaign, rows = service.workspace(actor, str(selected))
            if campaign.influencer_stage == stage and campaign.is_active:
                render_workspace(actor, service, users, campaign, rows)
                return
            st.session_state.pop(SELECTED, None)
        render_portfolio(actor, service, users, stage)
    except CampaignOpsError as exc:
        st.error(str(exc))
        if selected and st.button("Back to campaigns"):
            st.session_state.pop(SELECTED, None)
            st.rerun()


def render_portfolio(actor, service, users, stage):
    if stage == "planning":
        with st.expander("New Campaign", expanded=False):
            render_new_campaign(actor, service, users)
    search = st.text_input("Search campaigns", key=f"influencer_timeline_search_{stage}").strip().casefold()
    campaigns, timelines = service.list_campaigns(actor, stage)
    campaigns = [campaign for campaign in campaigns if search in campaign.campaign_title.casefold()]
    owners = {user.id: user.display_name for user in users}
    columns = st.columns([4, 1, 2, 5, 1])
    for column, label in zip(columns, ("Campaign", "Owner", "Next Date", "Next Action", "Open")):
        column.markdown(f"**{label}**")
    if not campaigns:
        st.info("No campaigns in this view.")
    for campaign in campaigns:
        timeline = sort_timeline(timelines.get(campaign.id, []))
        # Existing completion statuses remain meaningful for next-action summaries,
        # while every active row remains visible in the historical timeline.
        upcoming = next((row for row in timeline if row.status not in ("complete", "cancelled")), None)
        columns = st.columns([4, 1, 2, 5, 1])
        columns[0].write(campaign.campaign_title)
        columns[1].write(owners.get(campaign.manager_user_id, "Unassigned"))
        columns[2].write(upcoming.due_date.strftime("%m/%d/%Y") if upcoming and upcoming.due_date else "?")
        columns[3].write(upcoming.step_title if upcoming else "?")
        columns[4].button("Open", key=f"influencer_timeline_open_{campaign.id}",
                          on_click=_open_campaign, args=(campaign.id,))


def _owners(users):
    return {user.display_name: user.id for user in users if user.is_active and user.display_name in ("T", "L")}


def render_new_campaign(actor, service, users):
    owners = _owners(users)
    programs = service.list_program_portfolio(actor, {"active_state": "active"})
    by_id = {program.id: program for program in programs}
    if not owners or not by_id:
        st.info("An accessible active program and an active T or L owner are required.")
        return
    with st.form("influencer_timeline_create"):
        owner = st.selectbox("Owner", list(owners), index=None, placeholder="Choose T or L")
        title = st.text_input("Campaign")
        program_id = st.selectbox("Program", list(by_id), format_func=lambda key: by_id[key].program_name)
        submitted = st.form_submit_button("Create Campaign", type="primary")
    if submitted:
        if owner is None:
            st.error("Choose T or L.")
            return
        try:
            campaign = service.create_campaign(actor, program_id, title, owners[owner])
        except CampaignOpsError as exc:
            st.error(str(exc))
            return
        st.session_state[SELECTED] = campaign.id
        _saved("Campaign created.")


def render_workspace(actor, service, users, campaign, rows):
    st.markdown(f"### {campaign.campaign_title}")
    owners = _owners(users)
    current = next((label for label, key in owners.items() if key == campaign.manager_user_id), None)
    with st.form(f"influencer_timeline_owner_{campaign.id}"):
        owner = st.selectbox("Owner", list(owners), index=list(owners).index(current) if current else None,
                             placeholder="Choose T or L")
        submitted = st.form_submit_button("Save Owner")
    if submitted:
        if owner is None:
            st.error("Choose T or L.")
        else:
            try:
                service.change_owner(actor, campaign.id, owners[owner])
            except CampaignOpsError as exc:
                st.error(str(exc))
            else:
                _saved("Owner saved.")
    st.markdown("#### Timeline")
    st.dataframe(
        [{"Date": row.due_date, "Action": row.step_title, "Program Notes": row.notes or ""} for row in rows]
        or {"Date": [], "Action": [], "Program Notes": []},
        column_config={"Date": st.column_config.DateColumn("Date", format="MM/DD/YYYY")},
        column_order=["Date", "Action", "Program Notes"], hide_index=True, width="stretch",
    )
    editor_key = f"influencer_timeline_editor_{campaign.id}"
    if st.button("+ Add Row", key=f"influencer_timeline_add_{campaign.id}"):
        st.session_state[editor_key] = "new"
    if rows:
        with st.expander("Edit / Remove Row", expanded=False):
            by_id = {row.id: row for row in rows}
            row_id = st.selectbox("Row", list(by_id),
                format_func=lambda key: f"{by_id[key].due_date or 'Undated'} ? {by_id[key].step_title}",
                key=f"influencer_timeline_row_select_{campaign.id}")
            if st.button("Edit Row", key=f"influencer_timeline_edit_{campaign.id}"):
                st.session_state[editor_key] = row_id
    editing = st.session_state.get(editor_key)
    if editing:
        row = next((item for item in rows if item.id == editing), None)
        if editing == "new" or row is not None:
            render_row_editor(actor, service, campaign.id, row, editor_key)
        else:
            st.session_state.pop(editor_key, None)
    render_stage_action(actor, service, campaign)
    st.button("Back to campaigns", key=f"influencer_timeline_back_{campaign.id}", on_click=_back_to_campaigns)


def _save_row(actor, service, campaign_id, row_id, token, editor_key):
    try:
        service.save_row(actor, campaign_id, st.session_state[f"action_{token}"],
            st.session_state.get(f"custom_{token}", ""), st.session_state[f"date_{token}"],
            st.session_state[f"notes_{token}"], row_id)
    except CampaignOpsError as exc:
        st.session_state[FLASH + "_error"] = str(exc)
    else:
        st.session_state.pop(editor_key, None)
        st.session_state[FLASH] = "Timeline row saved."


def _remove_row(actor, service, campaign_id, row_id, editor_key):
    try:
        service.remove_row(actor, campaign_id, row_id)
    except CampaignOpsError as exc:
        st.session_state[FLASH + "_error"] = str(exc)
    else:
        st.session_state.pop(editor_key, None)
        st.session_state[FLASH] = "Timeline row removed."


def _cancel_edit(editor_key):
    st.session_state.pop(editor_key, None)


def render_row_editor(actor, service, campaign_id, row, editor_key):
    token = f"{campaign_id}_{row.id if row else 'new'}"
    selected = row.step_title if row and row.step_title in ACTION_LIBRARY else "Custom" if row else ACTION_LIBRARY[0]
    with st.container(border=True):
        st.caption("Edit row" if row else "Add row")
        action = st.selectbox("Action", ACTION_LIBRARY, index=ACTION_LIBRARY.index(selected), key=f"action_{token}")
        if row and row.start_date:
            st.caption(f"Date must be on or after {row.start_date:%m/%d/%Y}, or left blank.")
        with st.form(f"influencer_timeline_row_form_{token}"):
            if action == "Custom":
                st.text_input("Custom action", value=row.step_title if row and selected == "Custom" else "", key=f"custom_{token}")
            st.date_input("Date", value=row.due_date if row else None, key=f"date_{token}")
            st.text_area("Program Notes", value=row.notes or "" if row else "", key=f"notes_{token}")
            st.form_submit_button("Save Row", type="primary", on_click=_save_row,
                args=(actor, service, campaign_id, row.id if row else None, token, editor_key))
        if row:
            st.button("Remove Row", key=f"remove_{token}", on_click=_remove_row,
                      args=(actor, service, campaign_id, row.id, editor_key))
        st.button("Cancel edit", key=f"cancel_{token}", on_click=_cancel_edit, args=(editor_key,))


def render_stage_action(actor, service, campaign):
    stage = campaign.influencer_stage
    if stage not in FORWARD_STAGES:
        return
    label = {"planning": "Move to Live", "live": "Move to Recapping", "recapping": "Mark Complete"}[stage]
    confirm_key = f"influencer_timeline_confirm_{campaign.id}_{stage}"
    if st.button(label, key=f"stage_{campaign.id}_{stage}"):
        st.session_state[confirm_key] = True
    if st.session_state.get(confirm_key):
        st.info(f"{label}?")
        confirm, cancel = st.columns(2)
        if confirm.button("Confirm", key=f"confirm_{campaign.id}_{stage}"):
            try:
                updated = service.advance(actor, campaign.id, stage)
            except CampaignOpsError as exc:
                st.error(str(exc))
            else:
                st.session_state.pop(confirm_key, None)
                target = updated.influencer_stage
                if target == "complete":
                    st.session_state.pop(SELECTED, None)
                else:
                    st.session_state[PENDING] = STAGE_LABELS[target]
                _saved("Campaign marked Complete." if target == "complete" else f"Campaign moved to {STAGE_LABELS[target]}.")
        if cancel.button("Cancel", key=f"cancel_stage_{campaign.id}_{stage}"):
            st.session_state.pop(confirm_key, None)
            st.rerun()
