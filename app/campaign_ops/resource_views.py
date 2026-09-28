from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit
import streamlit as st

from core.campaign_ops.exceptions import CampaignOpsError
from core.campaign_ops.models import CampaignOpsUser, ProgramWorkspaceSummary
from core.campaign_ops.service import CampaignOpsService


def render_resources(actor: CampaignOpsUser, service: CampaignOpsService, summary: ProgramWorkspaceSummary) -> None:
    try:
        resources = service.list_program_resources(actor, summary.program.id)
    except CampaignOpsError as exc:
        st.error(f"Unable to load links: {exc}")
        return
    links = [resource for resource in resources if resource.url and urlsplit(resource.url).scheme.lower() in {"http", "https"}]
    if not links:
        st.caption("No links added.")
    for resource in links:
        st.link_button(resource.title, sanitize_link(resource.url))


def sanitize_link(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.port:
        host = f"{host}:{parts.port}"
    return urlunsplit((parts.scheme, host, parts.path, parts.query, parts.fragment))
