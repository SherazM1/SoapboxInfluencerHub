from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

import pandas as pd
import streamlit as st

from core.campaign_ops.exceptions import CampaignOpsError, CampaignOpsPermissionError
from core.campaign_ops.permissions import can_access_admin
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
    routed = st.session_state.pop("campaign_ops_influencer_route_record", None)
    try:
        if selected:
            service.authorize_campaign(actor, str(selected))
            snapshot = st.session_state.get(f"campaign_ops_influencer_draft_{actor.id}_{selected}")
            if snapshot:
                # A form submission already has a displayed snapshot. The save
                # transaction rechecks authorization and current database values.
                campaign, rows = snapshot["campaign"], snapshot["rows"]
            else:
                prefetched = routed["campaign"] if routed and routed["actor_id"] == actor.id and routed["campaign"].id == selected else None
                campaign, rows = service.workspace(actor, str(selected), routed_campaign=prefetched)
            if campaign.influencer_stage == stage and campaign.is_active:
                render_workspace(actor, service, users, campaign, rows)
                return
            st.session_state.pop(SELECTED, None)
        render_portfolio(actor, service, users, stage)
    except CampaignOpsPermissionError:
        _back_to_campaigns()
        st.warning("You do not have access to this program.")
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
            st.error("Choose a Lead Owner.")
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
    snapshot_key = f"campaign_ops_influencer_draft_{actor.id}_{campaign.id}"
    version_key = f"campaign_ops_influencer_editor_version_{campaign.id}"
    if snapshot_key not in st.session_state:
        ownership = service.workspace_assignments(actor, campaign)
        st.session_state[snapshot_key] = {
            "campaign": deepcopy(campaign), "rows": deepcopy(rows),
            "owner": ownership["lead_id"], "stage": campaign.influencer_stage,
            "ownership": ownership, "editor_manager": ownership["manager_id"],
            "lead_names": {u.id: u.display_name for u in service.list_workflow_role_users("influencer", "lead_owner")},
            "manager_names": {u.id: u.display_name for u in service.list_workflow_role_users("influencer", "manager")},
            "editor_records": [dict(editor_record(row), _draft_id=row.id) for row in rows],
            "editor_owner": ownership["lead_id"],
        }
    snapshot = st.session_state[snapshot_key]
    version = st.session_state.get(version_key, 0)
    owners, managers = snapshot["lead_names"], snapshot["manager_names"]
    if snapshot.get("widget_version") != version:
        snapshot["widget_base"] = deepcopy(snapshot["editor_records"])
        snapshot["widget_version"] = version
        snapshot["added_tokens"] = {}
    owner_key = f"influencer_lead_{campaign.id}_{version}"
    manager_key = f"influencer_manager_{campaign.id}_{version}"
    custom_values = {
        row["_draft_id"]: row.get("Custom Action", "")
        for row in snapshot["editor_records"]
        if row.get("_draft_id")
    }
    owner = st.selectbox("Lead Owner", list(owners), format_func=owners.get,
                         index=list(owners).index(snapshot["editor_owner"]) if snapshot["editor_owner"] in owners else None,
                         placeholder="Choose a Lead Owner", key=owner_key, disabled=not can_access_admin(actor))
    manager = st.selectbox("Manager", list(managers), format_func=managers.get,
                           index=list(managers).index(snapshot["editor_manager"]) if snapshot["editor_manager"] in managers else None,
                           placeholder="Choose a Manager", key=manager_key, disabled=not can_access_admin(actor))
    st.markdown("#### Timeline")
    edited = st.data_editor(
        timeline_frame([], snapshot["widget_base"]),
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
    added_index = 0
    for index, record in enumerate(records, 1):
        # Draft tokens survive validation/rebasing and row deletion. They are
        # UI-only; the save service uses the separate persisted row ID.
        token = record.get("_draft_id")
        if not token:
            token = snapshot["added_tokens"].setdefault(added_index, str(uuid4()))
            added_index += 1
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
    snapshot["editor_owner"] = owner
    snapshot["editor_manager"] = manager
    st.button("Save Changes", type="primary", key=f"influencer_save_{campaign.id}",
              on_click=_save_workspace, args=(actor, service, campaign.id, snapshot_key, version_key, version))
    st.caption("Edits stay unsaved until Save Changes. Save before leaving or moving stages.")
    if any(row.start_date for row in snapshot["rows"]):
        st.caption("Existing row start dates still apply: a date cannot precede that row's start date.")
    render_stage_action(actor, service, campaign)
    st.button("Back to campaigns", key=f"influencer_timeline_back_{campaign.id}", on_click=_back_to_campaigns)


def _save_workspace(actor, service, campaign_id, snapshot_key, version_key, version):
    """Save before the automatic widget-event render; no second full-page rerun."""
    snapshot = st.session_state[snapshot_key]
    records = deepcopy(snapshot["widget_base"])
    delta = st.session_state.get(f"influencer_timeline_table_{campaign_id}_{version}", {})
    for index, changes in delta.get("edited_rows", {}).items():
        records[int(index)].update(changes)
    deleted = set(delta.get("deleted_rows", []))
    records = [row for index, row in enumerate(records) if index not in deleted]
    for index, row in enumerate(delta.get("added_rows", [])):
        records.append({"_row_id": None, "_draft_id": snapshot["added_tokens"].setdefault(index, str(uuid4())), **row})
    owner = st.session_state.get(f"influencer_lead_{campaign_id}_{version}")
    manager = st.session_state.get(f"influencer_manager_{campaign_id}_{version}")
    try:
        if owner is None:
            raise CampaignOpsError("Choose a Lead Owner.")
        if manager is None and snapshot["ownership"]["manager_id"] is not None:
            raise CampaignOpsError("Choose a Manager.")
        for record in records:
            value = record.get("Date")
            if isinstance(value, str):
                record["Date"] = pd.to_datetime(value).date() if value else None
            if record.get("Action") == "Custom":
                custom_key = f"campaign_ops_influencer_draft_custom_{campaign_id}_{version}_{record['_draft_id']}"
                record["Custom Action"] = st.session_state.get(custom_key, record.get("Custom Action", "")).strip()
                if not record["Custom Action"]:
                    raise CampaignOpsError("Enter text for every Custom action.")
            else:
                record["Custom Action"] = ""
        changes = service.save_changes(actor, campaign_id, owner, records,
            snapshot["rows"], snapshot["owner"], snapshot["stage"],
            manager_id=manager, original_assignments=snapshot["ownership"])
    except (CampaignOpsError, ValueError) as exc:
        snapshot["editor_records"] = records
        snapshot["editor_owner"], snapshot["editor_manager"] = owner, manager
        st.session_state[version_key] = version + 1
        st.session_state[FLASH + "_error"] = f"{exc} Nothing saved; complete the form below."
    else:
        st.session_state.pop(snapshot_key, None)
        st.session_state[version_key] = version + 1
        changed = any(changes.get(key) for key in ("updated", "added", "removed", "owner_changed", "manager_changed"))
        st.session_state[FLASH] = "Changes saved." if changed else "No changes to save."


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
