from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit

import streamlit as st

from app.campaign_ops.formatting import WORKFLOW_LABELS, format_datetime, safe_text
from app.campaign_ops.validation import trim_or_none
from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.models import CampaignOpsUser, ProgramWorkspaceSummary, ResourceListRow
from core.campaign_ops.permissions import can_access_admin
from core.campaign_ops.service import CampaignOpsService

RESOURCE_SORT_OPTIONS = {
    "Updated date": "updated_at",
    "Title": "title",
    "Resource type": "resource_type",
    "Workstream": "workstream_type",
    "Created date": "created_at",
}

RESOURCE_TYPES = [
    "Track Sheet",
    "Brief",
    "Invoice",
    "EOP Survey",
    "Content Folder",
    "Client Tracker",
    "Live Tracker",
    "Media Plan",
    "Budget Tracker",
    "SKU List",
    "Submission Tracker",
    "Keyword Insights",
    "Photography Folder",
    "Custom",
]


def render_resources(
    actor: CampaignOpsUser,
    service: CampaignOpsService,
    summary: ProgramWorkspaceSummary,
) -> None:
    st.markdown("### Resources")
    cols = st.columns(4)
    include_inactive = cols[0].checkbox("Show inactive resources", key="campaign_ops_resource_show_inactive")
    if cols[1].button("Refresh", key=f"campaign_ops_resource_refresh_{summary.program.id}"):
        st.rerun()
    if cols[2].button("Clear filters", key=f"campaign_ops_resource_clear_filters_{summary.program.id}"):
        st.session_state["campaign_ops_resource_filters"] = {}
        st.rerun()
    can_add = can_access_admin(actor) and summary.program.is_active
    if can_add and cols[3].button("Add Resource", type="primary", key=f"campaign_ops_resource_create_button_{summary.program.id}"):
        st.session_state["campaign_ops_resource_create_open"] = True

    if st.session_state.get("campaign_ops_resource_create_open") and can_add:
        render_resource_form(actor, service, summary, None)
        st.divider()

    try:
        resources = service.list_program_resources(actor, summary.program.id, include_inactive=include_inactive)
    except CampaignOpsError as exc:
        st.error(f"Unable to load resources: {exc}")
        return
    filters = render_resource_filters(summary, resources)
    filtered = sort_resources(filter_resources(resources, filters), filters.get("sort_by", "updated_at"))
    if filtered:
        st.dataframe(resource_table_rows(filtered), hide_index=True, use_container_width=True)
    else:
        st.info("No resources match this view.")

    for resource in filtered:
        render_resource_actions(actor, service, summary, resource)


def render_resource_filters(
    summary: ProgramWorkspaceSummary,
    resources: list[ResourceListRow],
) -> dict[str, object]:
    current = st.session_state.get("campaign_ops_resource_filters")
    if not isinstance(current, dict):
        current = {}
    with st.expander("Resource filters", expanded=True):
        cols = st.columns(4)
        current["search"] = cols[0].text_input("Search", value=str(current.get("search", "")), key="campaign_ops_resource_filter_search")
        type_values = sorted({item.resource_type for item in resources if item.resource_type})
        type_options = {"Any": "", **{item: item for item in type_values}}
        current["resource_type"] = type_options[cols[1].selectbox("Resource type", list(type_options), key="campaign_ops_resource_filter_type")]
        workstream_options = {"Any": "", **{WORKFLOW_LABELS.get(w.workstream_type, w.workstream_type): w.id for w in summary.workstreams}}
        current["workstream_id"] = workstream_options[cols[2].selectbox("Workstream", list(workstream_options), key="campaign_ops_resource_filter_workstream")]
        current["sort_by"] = RESOURCE_SORT_OPTIONS[cols[3].selectbox("Sort", list(RESOURCE_SORT_OPTIONS), key="campaign_ops_resource_filter_sort")]
        cols = st.columns(2)
        current["required_only"] = cols[0].checkbox("Required only", value=bool(current.get("required_only", False)), key="campaign_ops_resource_filter_required_only")
        current["missing_url_only"] = cols[1].checkbox("Missing URL only", value=bool(current.get("missing_url_only", False)), key="campaign_ops_resource_filter_missing_url")
    st.session_state["campaign_ops_resource_filters"] = current
    return current


def render_resource_form(
    actor: CampaignOpsUser,
    service: CampaignOpsService,
    summary: ProgramWorkspaceSummary,
    resource: ResourceListRow | None,
) -> None:
    form_key = f"campaign_ops_resource_form_{resource.id if resource else 'new'}"
    with st.form(form_key):
        title = st.text_input("Title", value=resource.title if resource else "")
        current_type = resource.resource_type if resource else "Custom"
        type_options = list(dict.fromkeys([current_type, *RESOURCE_TYPES]))
        resource_type = st.selectbox("Resource type", type_options, index=type_options.index(current_type))
        workstream_options = {"Program-level": None, **{WORKFLOW_LABELS.get(w.workstream_type, w.workstream_type): w.id for w in summary.workstreams if w.is_active or (resource and resource.workstream_id == w.id)}}
        current_ws = next((label for label, value in workstream_options.items() if resource and value == resource.workstream_id), "Program-level")
        workstream_label = st.selectbox("Workstream", list(workstream_options), index=list(workstream_options).index(current_ws))
        url = st.text_input("URL", value=resource.url or "" if resource else "")
        is_required = st.checkbox("Required", value=resource.is_required if resource else False)
        notes = st.text_area("Notes", value=resource.notes or "" if resource else "")
        submitted = st.form_submit_button("Save Resource" if resource else "Create Resource", type="primary")
    if not submitted:
        return
    try:
        payload = {
            "resource_type": resource_type,
            "workstream_id": workstream_options[workstream_label],
            "url": trim_or_none(url),
            "is_required": is_required,
            "notes": trim_or_none(notes),
        }
        if resource:
            service.update_resource_details(actor, resource.id, title=title, **payload)
            st.session_state.pop("campaign_ops_resource_edit_id", None)
            st.success("Resource updated.")
        else:
            service.create_resource(actor, summary.program.id, title=title, **payload)
            st.session_state["campaign_ops_resource_create_open"] = False
            st.success("Resource created.")
    except CampaignOpsError as exc:
        st.error(f"Resource was not saved: {exc}")
        return
    st.rerun()


def render_resource_actions(
    actor: CampaignOpsUser,
    service: CampaignOpsService,
    summary: ProgramWorkspaceSummary,
    resource: ResourceListRow,
) -> None:
    with st.expander(f"Resource actions: {resource.title}", expanded=False):
        render_resource_form(actor, service, summary, resource)
        cols = st.columns(3)
        if resource.url:
            cols[0].link_button("Open link", sanitize_link(resource.url), key=f"campaign_ops_resource_open_link_{resource.id}")
        else:
            cols[0].caption("No URL")
        if resource.is_active and cols[1].button("Deactivate", key=f"campaign_ops_resource_deactivate_id_{resource.id}"):
            _run_resource_action(service.deactivate_resource, actor, resource.id, "Resource deactivated.")
        if not resource.is_active and cols[2].button("Reactivate", key=f"campaign_ops_resource_reactivate_id_{resource.id}"):
            _run_resource_action(service.reactivate_resource, actor, resource.id, "Resource reactivated.")


def sanitize_link(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))


def resource_table_rows(resources: list[ResourceListRow]) -> list[dict[str, str]]:
    return [
        {
            "Title": resource.title,
            "Resource type": resource.resource_type,
            "Workstream": WORKFLOW_LABELS.get(resource.workstream_type or "", "-"),
            "Required": "Yes" if resource.is_required else "No",
            "URL status": url_status(resource),
            "Notes preview": safe_text((resource.notes or "")[:80]),
            "Active state": "Active" if resource.is_active else "Inactive",
            "Updated date": format_datetime(resource.updated_at),
        }
        for resource in resources
    ]


def url_status(resource: ResourceListRow) -> str:
    if not resource.is_active:
        return "Inactive"
    if resource.is_required and not resource.url:
        return "Missing required URL"
    if resource.url:
        return "Link available"
    return "No URL"


def filter_resources(resources: list[ResourceListRow], filters: dict[str, object]) -> list[ResourceListRow]:
    result = resources
    search = str(filters.get("search") or "").strip().lower()
    if search:
        result = [item for item in result if search in item.title.lower() or search in item.resource_type.lower()]
    if filters.get("resource_type"):
        result = [item for item in result if item.resource_type == filters["resource_type"]]
    if filters.get("workstream_id"):
        result = [item for item in result if item.workstream_id == filters["workstream_id"]]
    if filters.get("required_only"):
        result = [item for item in result if item.is_required]
    if filters.get("missing_url_only"):
        result = [item for item in result if item.is_required and not item.url]
    return result


def sort_resources(resources: list[ResourceListRow], sort_by: str) -> list[ResourceListRow]:
    return sorted(
        resources,
        key=lambda item: (
            getattr(item, sort_by, None) is None,
            str(getattr(item, sort_by, "") or ""),
            item.title.lower(),
        ),
        reverse=sort_by in {"updated_at", "created_at"},
    )


def _run_resource_action(action: object, actor: CampaignOpsUser, resource_id: str, success: str) -> None:
    try:
        action(actor, resource_id)
    except CampaignOpsError as exc:
        st.error(f"Resource action failed: {exc}")
        return
    st.success(success)
    st.rerun()
