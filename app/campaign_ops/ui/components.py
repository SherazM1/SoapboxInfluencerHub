from __future__ import annotations

from collections.abc import Callable
from html import escape

import streamlit as st

from app.campaign_ops.ui.badges import badge_text, status_label
from app.campaign_ops.ui.formatting import display_record_title


def render_page_header(
    title: str,
    subtitle: str | None = None,
    viewer_context: str | None = None,
    active_module: str | None = None,
    status: str | None = None,
) -> None:
    meta = " | ".join(item for item in (active_module, viewer_context, badge_text(status) if status else None) if item)
    safe_title = escape(display_record_title(title))
    safe_subtitle = escape(subtitle) if subtitle else ""
    safe_meta = escape(meta) if meta else ""
    st.markdown(
        "<div class='campaign-ops-page-header'>"
        f"<h1>{safe_title}</h1>"
        f"{f'<div>{safe_subtitle}</div>' if safe_subtitle else ''}"
        f"{f'<div class=\"campaign-ops-filter-note\">{safe_meta}</div>' if safe_meta else ''}"
        "</div>",
        unsafe_allow_html=True,
    )


def render_section_header(title: str, description: str | None = None, count: int | None = None) -> None:
    count_text = f" ({count})" if count is not None else ""
    safe_title = escape(title)
    safe_description = escape(description) if description else ""
    st.markdown(
        "<div class='campaign-ops-section-header'>"
        f"<strong>{safe_title}{count_text}</strong>"
        f"{f'<div>{safe_description}</div>' if safe_description else ''}"
        "</div>",
        unsafe_allow_html=True,
    )


def render_empty_state(kind: str = "no records", detail: str | None = None) -> None:
    defaults = {
        "no records": "No records are available.",
        "no filter matches": "No records match the selected filters.",
        "no access": "No accessible records are available for this viewer.",
        "module not initialized": "This module is not initialized yet.",
        "no tasks": "No tasks are available.",
        "no milestones": "No milestones are available.",
        "no resources": "No resources are available.",
        "no activity": "No activity is available.",
        "no workflow-specific records": "No workflow-specific records match this view.",
    }
    message = escape(detail or defaults.get(kind, defaults["no records"]))
    st.markdown(
        f"<div class='campaign-ops-empty'>{message}</div>",
        unsafe_allow_html=True,
    )


def render_status_badges(*values: str | None) -> None:
    badges = "".join(f"<span class='campaign-ops-badge'>{status_label(value)}</span>" for value in values if value)
    if badges:
        st.markdown(badges, unsafe_allow_html=True)


def render_action_row(actions: list[tuple[str, Callable[[], None], str, str]]) -> None:
    columns = st.columns(max(len(actions), 1))
    for column, (label, callback, key, button_type) in zip(columns, actions):
        if column.button(label, key=key, type=button_type, use_container_width=True):
            callback()
