from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

import pandas as pd
import streamlit as st

from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.influencer_timeline import (
    ACTION_LIBRARY, EDITOR_COLUMNS, FORWARD_STAGES, STAGE_LABELS, InfluencerTimelineService, editor_record, sort_timeline,
)

SELECTED = "campaign_ops_selected_influencer_campaign_id"
PENDING = "campaign_ops_influencer_timeline_navigation"
FLASH = "campaign_ops_influencer_timeline_message"


def _saved(message, *, error=False):
    st.session_state[FLASH + ("_error" if error else "")] = message
    st.rerun()


def _discard_drafts():
    for key in list(st.session_state):
        if key.startswith("campaign_ops_influencer_draft_"):
            st.session_state.pop(key, None)


def _open_campaign(campaign_id):
    _discard_drafts()
    st.session_state[SELECTED] = campaign_id


def _back_to_campaigns():
    _discard_drafts()
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
            snapshot = st.session_state.get(f"campaign_ops_influencer_draft_{actor.id}_{selected}")
            if snapshot:
                # A form submission already has a displayed snapshot. The save
                # transaction rechecks authorization and current database values.
                campaign, rows = snapshot["campaign"], snapshot["rows"]
            else:
                campaign, rows = service.workspace(actor, str(selected))
            if campaign.influencer_stage == stage and campaign.is_active:
                render_workspace(actor, service, users, campaign, rows)
                return
            st.session_state.pop(SELECTED, None)
        render_portfolio(actor, service, users, stage)
    except CampaignOpsError as exc:
        st.error(str(exc))
        if selected:
            st.button("Back to campaigns", on_click=_back_to_campaigns)

def _editor_display_records(records):
    """Show saved custom text in the single visible Action column."""
    display_records = []
    custom_options = []

    for source in records:
        record = dict(source)

        if record.get("Action") == "Custom":
            custom_text = (record.get("Custom Action") or "").strip()

            if custom_text:
                record["Action"] = custom_text

                if (
                    custom_text not in ACTION_LIBRARY
                    and custom_text not in custom_options
                ):
                    custom_options.append(custom_text)

        display_records.append(record)

    return display_records, custom_options


def _normalize_editor_action(record, saved_custom_values):
    """
    Convert the single visible Action column back into the persisted
    standard/custom representation.
    """
    token = record["_draft_id"]
    selected_action = record.get("Action")
    prior_custom = (saved_custom_values.get(token) or "").strip()

    # Existing saved custom rows are displayed using their custom text.
    # If the user leaves that value unchanged, preserve it internally as Custom.
    if prior_custom and selected_action == prior_custom:
        record["Action"] = "Custom"
        record["Custom Action"] = prior_custom
        return True

    # User explicitly selected Custom from the dropdown.
    if selected_action == "Custom":
        record["Custom Action"] = prior_custom
        return True

    # Standard dropdown action.
    record["Custom Action"] = ""
    return False


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


def _owners(service):
    return {
        user.display_name: user.id
        for user in service.list_workflow_role_users("influencer", "lead_owner")
    }


def render_new_campaign(actor, service, users):
    owners = _owners(service)
    programs = service.list_program_portfolio(actor, {"active_state": "active"})
    by_id = {program.id: program for program in programs}
    if not owners or not by_id:
        st.info("An accessible active program and an active Influencer Lead Owner are required.")
        return
    with st.form("influencer_timeline_create"):
        owner = st.selectbox("Owner", list(owners), index=None, placeholder="Choose a Lead Owner")
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


def timeline_frame(rows, records=None):
    records = records if records is not None else [dict(editor_record(row), _draft_id=row.id) for row in rows]
    frame = pd.DataFrame(records, columns=["_row_id", "_draft_id", *EDITOR_COLUMNS])
    # Explicit nullable types keep the empty/all-undated editor editable too.
    frame["Date"] = pd.to_datetime(frame["Date"])
    for column in ("_row_id", "_draft_id", "Action", "Program Notes"):
        frame[column] = frame[column].astype("string")
    return frame


def frame_records(frame):
    return [{key: None if pd.isna(value) else value for key, value in row.items()}
            for row in frame.to_dict("records")]


def render_workspace(actor, service, users, campaign, rows):
    st.markdown(f"### {campaign.campaign_title}")
    owners = _owners(service)
    snapshot_key = f"campaign_ops_influencer_draft_{actor.id}_{campaign.id}"
    version_key = f"campaign_ops_influencer_editor_version_{campaign.id}"
    if snapshot_key not in st.session_state:
        st.session_state[snapshot_key] = {
            "campaign": deepcopy(campaign), "rows": deepcopy(rows),
            "owner": campaign.manager_user_id, "stage": campaign.influencer_stage,
            "editor_records": [dict(editor_record(row), _draft_id=row.id) for row in rows],
            "editor_owner": campaign.manager_user_id,
        }
    snapshot = st.session_state[snapshot_key]
    version = st.session_state.get(version_key, 0)
    current = next((label for label, key in owners.items() if key == snapshot["editor_owner"]), None)
    custom_values = {
        row["_draft_id"]: row.get("Custom Action", "")
        for row in snapshot["editor_records"]
        if row.get("_draft_id")
    }
    owner = st.selectbox("Owner", list(owners), index=list(owners).index(current) if current else None,
                         placeholder="Choose T or L")
    st.markdown("#### Timeline")
    edited = st.data_editor(
        timeline_frame([], snapshot["editor_records"]),
        key=f"influencer_timeline_table_{campaign.id}_{version}",
        num_rows="dynamic", hide_index=True, width="stretch",
        column_order=list(EDITOR_COLUMNS), disabled=["_row_id", "_draft_id"],
        column_config={
            "_row_id": None,
            "_draft_id": None,
            "Date": st.column_config.DateColumn("Date", format="MM/DD/YYYY", required=False),
            "Action": st.column_config.SelectboxColumn("Action", options=list(ACTION_LIBRARY), required=True, width="large"),
            "Program Notes": st.column_config.TextColumn("Program Notes", width="large"),
        },
    )
    records = frame_records(edited)
    custom_heading = False
    for index, record in enumerate(records, 1):
        # Draft tokens survive validation/rebasing and row deletion. They are
        # UI-only; the save service uses the separate persisted row ID.
        token = record.get("_draft_id") or str(uuid4())
        record["_draft_id"] = token
        record["Custom Action"] = custom_values.get(token, "") if record.get("Action") == "Custom" else ""
        if record.get("Action") == "Custom":
            if not custom_heading:
                st.markdown("#### Custom Actions")
                custom_heading = True
            context = record["Date"].strftime("%m/%d/%Y") if record["Date"] is not None else "No date"
            st.caption(f"Row {index} · {context}")
            record["Custom Action"] = st.text_input(
                "Custom action",
                value=record["Custom Action"],
                key=f"campaign_ops_influencer_draft_custom_{campaign.id}_{version}_{token}",
            )

    snapshot["editor_records"] = records
    snapshot["editor_owner"] = owners.get(owner)
    submitted = st.button("Save Changes", type="primary", key=f"influencer_save_{campaign.id}")
    st.caption("Edits stay unsaved until Save Changes. Save before leaving or moving stages.")
    if any(row.start_date for row in snapshot["rows"]):
        st.caption("Existing row start dates still apply: a date cannot precede that row's start date.")
    if submitted:
        try:
            if owner is None:
                raise CampaignOpsError("Choose T or L.")
            for record in records:
                if record.get("Action") == "Custom":
                    custom_text = (record.get("Custom Action") or "").strip()
                    if not custom_text:
                        raise CampaignOpsError("Enter text for every Custom action.")
                    record["Custom Action"] = custom_text
            changes = service.save_changes(actor, campaign.id, owners[owner], records,
                    snapshot["rows"], snapshot["owner"], snapshot["stage"])
        except CampaignOpsError as exc:
            # Rebase the buffered editor after validation, never the original
            # database snapshot used for concurrency checks. New rows now have
            # stable helper tokens even when another new row is removed.
            snapshot["editor_records"] = records
            snapshot["editor_owner"] = owners.get(owner)
            st.session_state[version_key] = version + 1
            _saved(f"{exc} Nothing saved; complete the form below.", error=True)
        else:
            st.session_state.pop(snapshot_key, None)
            st.session_state[version_key] = version + 1
            _saved("Changes saved." if any(changes[key] for key in ("updated", "added", "removed", "owner_changed")) else "No changes to save.")
    render_stage_action(actor, service, campaign)
    st.button("Back to campaigns", key=f"influencer_timeline_back_{campaign.id}", on_click=_back_to_campaigns)


def _cancel_stage(confirm_key):
    st.session_state.pop(confirm_key, None)


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
                _discard_drafts()
                target = updated.influencer_stage
                if target == "complete":
                    st.session_state.pop(SELECTED, None)
                else:
                    st.session_state[PENDING] = STAGE_LABELS[target]
                _saved("Campaign marked Complete." if target == "complete" else f"Campaign moved to {STAGE_LABELS[target]}.")
        cancel.button("Cancel", key=f"cancel_stage_{campaign.id}_{stage}",
                      on_click=_cancel_stage, args=(confirm_key,))
