from __future__ import annotations

from copy import deepcopy

import streamlit as st

from app.campaign_ops.state import begin_new_program
from app.campaign_ops.operational_editor import collect_rows, editor_styles, render_rows

from core.campaign_ops.exceptions import CampaignOpsError, CampaignOpsPermissionError
from core.campaign_ops.permissions import can_access_admin
from core.campaign_ops.influencer_timeline import (
    ACTION_LIBRARY, FORWARD_STAGES, STAGE_LABELS, InfluencerTimelineService, editor_record, sort_timeline,
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
    if st.session_state.pop(FLASH + "_denied", False):
        st.warning("You do not have access to this program.")
    selected = st.session_state.get(SELECTED)
    st.session_state.pop("campaign_ops_influencer_route_record", None)
    if selected:
        render_workspace(actor, service, users, str(selected), stage)
        snapshot = st.session_state.get(f"campaign_ops_influencer_draft_{actor.id}_{selected}")
        if snapshot:
            render_stage_action(actor, service, snapshot["campaign"])
        st.button("Back to campaigns", key=f"influencer_timeline_back_{selected}", on_click=_back_to_campaigns)
    else:
        render_portfolio(actor, service, users, stage)


def render_portfolio(actor, service, users, stage):
    if stage == "planning" and can_access_admin(actor):
        st.button("New Program", type="primary", key="influencer_new_program",
                  on_click=begin_new_program, args=(st.session_state, "influencer"))
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


@st.fragment
def render_workspace(actor, service, users, campaign_id, stage):
    snapshot_key = f"campaign_ops_influencer_draft_{actor.id}_{campaign_id}"
    version_key = f"campaign_ops_influencer_editor_version_{campaign_id}"
    try:
        snapshot = st.session_state.get(snapshot_key)
        if snapshot:
            campaign = service.authorize_campaign(actor, campaign_id)
            if campaign.influencer_stage != snapshot["stage"]:
                raise CampaignOpsError("Campaign stage changed. Reopen the campaign before editing.")
        else:
            campaign, rows = service.workspace(actor, campaign_id)
            ownership = service.workspace_assignments(actor, campaign)
            snapshot = {
                "campaign": deepcopy(campaign), "rows": deepcopy(rows),
                "owner": ownership["lead_id"], "stage": campaign.influencer_stage,
                "ownership": ownership, "editor_manager": ownership["manager_id"],
                "lead_names": {u.id: u.display_name for u in service.list_workflow_role_users("influencer", "lead_owner")},
                "manager_names": {u.id: u.display_name for u in service.list_workflow_role_users("influencer", "manager")},
                "editor_records": [dict(editor_record(row), _draft_id=row.id) for row in rows],
                "editor_owner": ownership["lead_id"],
            }
            st.session_state[snapshot_key] = snapshot
        if not campaign.is_active:
            raise CampaignOpsError("Campaign is unavailable. Reopen the campaign list.")
        if campaign.influencer_stage != stage:
            _back_to_campaigns()
            st.rerun()  # Exceptional navigation out of the editor fragment.
    except CampaignOpsPermissionError:
        _back_to_campaigns()
        st.session_state[FLASH + "_denied"] = True
        st.rerun()  # The permitted list belongs to the full page, not this fragment.
    except CampaignOpsError as exc:
        st.error(str(exc))
        return
    editor_styles()
    with st.container(key="ops_editor"):
        st.markdown(f"### {campaign.campaign_title}")
        for suffix, display in (("_error", st.error), ("", st.success)):
            message = st.session_state.pop(FLASH + suffix, None)
            if message:
                display(message)
        version = st.session_state.get(version_key, 0)
        prefix = f"influencer_rows_{actor.id}_{campaign_id}_{version}"
        owners, managers = snapshot["lead_names"], snapshot["manager_names"]
        for label, options, field, key in (
            ("Lead Owner", owners, "editor_owner", f"influencer_lead_{campaign_id}_{version}"),
            ("Manager", managers, "editor_manager", f"influencer_manager_{campaign_id}_{version}"),
        ):
            snapshot[field] = st.selectbox(label, list(options), format_func=options.get,
                index=list(options).index(snapshot[field]) if snapshot[field] in options else None,
                placeholder=f"Choose a {label}", key=key, disabled=not can_access_admin(actor))
        st.markdown("#### Timeline")
        render_rows(snapshot, prefix, actions=ACTION_LIBRARY)
        st.button("Save Changes", type="primary", key=f"influencer_save_{campaign_id}",
            on_click=_save_workspace, args=(actor, service, campaign_id, snapshot_key, version_key, version, prefix))
        st.caption("Edits stay unsaved until Save Changes. Save before leaving or moving stages.")
        if any(row.start_date for row in snapshot["rows"]):
            st.caption("Existing row start dates still apply: a date cannot precede that row's start date.")


def _save_workspace(actor, service, campaign_id, snapshot_key, version_key, version, prefix):
    """One transaction before the automatic fragment refresh; no explicit rerun."""
    snapshot = st.session_state[snapshot_key]
    records = deepcopy(collect_rows(snapshot, prefix))
    owner = st.session_state.get(f"influencer_lead_{campaign_id}_{version}")
    manager = st.session_state.get(f"influencer_manager_{campaign_id}_{version}")
    try:
        if owner is None:
            raise CampaignOpsError("Choose a Lead Owner.")
        if manager is None and snapshot["ownership"]["manager_id"] is not None:
            raise CampaignOpsError("Choose a Manager.")
        changes = service.save_changes(actor, campaign_id, owner, records,
            snapshot["rows"], snapshot["owner"], snapshot["stage"],
            manager_id=manager, original_assignments=snapshot["ownership"])
    except (CampaignOpsError, ValueError) as exc:
        snapshot["editor_owner"], snapshot["editor_manager"] = owner, manager
        st.session_state[FLASH + "_error"] = f"{exc} Nothing saved."
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
