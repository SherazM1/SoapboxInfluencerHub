from __future__ import annotations

from pathlib import Path
from typing import Any

import streamlit as st

WORKFLOW_SESSION_KEYS = [
    "review_result",
    "later_export_path",
    "selected_identifiers",
    "recruiting_identifiers",
    "preview_result",
    "template_path",
    "population_result",
]


def safe_get(value: Any, field_name: str, default: Any = None) -> Any:
    """Safely fetch object or dict fields without raising errors."""
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(field_name, default)
    return getattr(value, field_name, default)


def switch_to_page(page_path: str) -> None:
    """Navigate to a target Streamlit page using native page switching when available."""
    switch_page = getattr(st, "switch_page", None)
    if callable(switch_page):
        switch_page(page_path)


def clear_workflow_session_state() -> None:
    """Clear only workbook-automation workflow session keys."""
    for key in WORKFLOW_SESSION_KEYS:
        if key in st.session_state:
            del st.session_state[key]


def hide_default_streamlit_sidebar_nav() -> None:
    """Hide Streamlit's default multipage sidebar navigation list."""
    st.markdown(
        """
        <style>
        [data-testid="stSidebarNav"] {
            display: none;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def get_logo_path() -> Path:
    """Resolve logo path from app root."""
    return Path(__file__).resolve().parents[1] / "assets" / "logo.png"


def render_header() -> None:
    """Render hub header with logo and platform intro."""
    logo_col, title_col = st.columns([1, 5])
    with logo_col:
        logo_path = get_logo_path()
        if logo_path.exists() and logo_path.is_file():
            st.image(str(logo_path), width=120)
    with title_col:
        st.title("Soapbox Influencer Hub")
        st.markdown(
            "Select a platform function below. Workbook Automation is active now, "
            "and Reporting is planned next."
        )


def render_module_cards() -> None:
    """Render top-level app module sections for navigation."""
    st.subheader("Select a Function")
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Workbook Automation")
        st.caption("Status: Active")
        st.markdown(
            "Automate campaign workbook population from reviewed Later Excel exports."
        )
        if st.button("Open Workbook Automation", type="primary", use_container_width=True):
            switch_to_page("pages/campaigns.py")
        st.page_link("pages/campaigns.py", label="Go to Workbook Automation Workspace")

    with col2:
        st.markdown("### Reporting")
        st.caption("Status: Coming Soon")
        st.markdown("Reporting dashboards and exports will be added in a future release.")
        if st.button("Open Reporting", use_container_width=True):
            st.info("Reporting module coming soon. This flow will be added later.")


def render_workflow_summary() -> None:
    """Render compact workbook-automation run summary from current session."""
    st.subheader("Workbook Automation Session")
    review_result = st.session_state.get("review_result")
    preview_result = st.session_state.get("preview_result")
    population_result = st.session_state.get("population_result")

    source_reviewed = review_result is not None and bool(
        safe_get(review_result, "is_successful", False)
    )
    preview_built = preview_result is not None
    workbook_generated = bool(safe_get(population_result, "is_successful", False))

    st.markdown(
        f"- **Source reviewed:** {'Yes' if source_reviewed else 'No'}\n"
        f"- **Preview built:** {'Yes' if preview_built else 'No'}\n"
        f"- **Workbook generated:** {'Yes' if workbook_generated else 'No'}"
    )


def render_workflow_actions() -> None:
    """Render primary workbook entry and workflow reset actions."""
    st.subheader("Workbook Actions")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Go to Workbook Automation", use_container_width=True):
            switch_to_page("pages/campaigns.py")
    with col2:
        if st.button("Start New Run", use_container_width=True):
            clear_workflow_session_state()
            switch_to_page("pages/campaigns.py")
            st.rerun()


def main() -> None:
    """Render multi-function platform hub page."""
    st.set_page_config(page_title="Platform Hub", page_icon="??", layout="wide")
    hide_default_streamlit_sidebar_nav()

    render_header()
    st.divider()
    render_module_cards()
    st.divider()
    render_workflow_summary()
    st.divider()
    render_workflow_actions()


if __name__ == "__main__":
    main()
