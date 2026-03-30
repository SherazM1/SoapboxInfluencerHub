from __future__ import annotations

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


def render_header() -> None:
    """Render module workspace header and orientation."""
    st.title("Workbook Automation")
    st.markdown(
        "Automate campaign template population from reviewed Later Excel exports. "
        "Use the guided steps below to complete the workflow."
    )


def render_workflow_overview() -> None:
    """Render workbook-automation workflow steps."""
    st.subheader("Workflow Steps")
    st.markdown(
        "1. **Upload Later Export**\n"
        "2. **Review Data and Build Preview**\n"
        "3. **Generate Workbook**"
    )


def render_session_summary() -> None:
    """Render compact workbook-automation session summary."""
    review_result = st.session_state.get("review_result")
    preview_result = st.session_state.get("preview_result")
    population_result = st.session_state.get("population_result")

    records = safe_get(review_result, "records", []) or []
    selected_records = safe_get(preview_result, "selected_records", []) or []

    source_reviewed = review_result is not None and bool(
        safe_get(review_result, "is_successful", False)
    )
    preview_valid = bool(safe_get(preview_result, "is_valid", False))
    workbook_generated = bool(safe_get(population_result, "is_successful", False))

    st.subheader("Current Session")
    st.markdown(
        f"- **Source reviewed:** {'Yes' if source_reviewed else 'No'}\n"
        f"- **Parsed record count:** {len(records)}\n"
        f"- **Selected influencer count:** {len(selected_records)}\n"
        f"- **Preview valid:** {'Yes' if preview_valid else 'No'}\n"
        f"- **Workbook generated:** {'Yes' if workbook_generated else 'No'}"
    )


def render_primary_cta() -> None:
    """Render primary start action for workbook flow."""
    st.subheader("Start")
    if st.button("Go to Upload Later Export", type="primary", use_container_width=True):
        switch_to_page("pages/uploadcsv.py")


def render_quick_navigation() -> None:
    """Render quick links across workbook-automation steps."""
    st.subheader("Quick Navigation")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.page_link("pages/uploadcsv.py", label="Step 1: Upload")
    with col2:
        st.page_link("pages/reviewdata.py", label="Step 2: Review")
    with col3:
        st.page_link("pages/generateworkbook.py", label="Step 3: Generate")


def render_reset_action() -> None:
    """Render start-new-run action for workbook flow."""
    st.subheader("Reset Run")
    st.caption("Clears workflow state and starts at Step 1.")
    if st.button("Start New Run", use_container_width=True):
        clear_workflow_session_state()
        switch_to_page("pages/uploadcsv.py")
        st.rerun()


def main() -> None:
    """Render workbook automation module workspace page."""
    st.set_page_config(page_title="Workbook Automation", page_icon="??", layout="wide")
    hide_default_streamlit_sidebar_nav()

    render_header()
    st.divider()
    render_workflow_overview()
    st.divider()
    render_session_summary()
    st.divider()
    render_primary_cta()
    st.divider()
    render_quick_navigation()
    st.divider()
    render_reset_action()


if __name__ == "__main__":
    main()
