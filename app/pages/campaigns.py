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


def clear_workflow_session_state() -> None:
    """Clear only workflow-related keys for a new run."""
    for key in WORKFLOW_SESSION_KEYS:
        if key in st.session_state:
            del st.session_state[key]


def switch_to_page(page_path: str) -> None:
    """Navigate to a target Streamlit page using native page switching when available."""
    switch_page = getattr(st, "switch_page", None)
    if callable(switch_page):
        switch_page(page_path)


def render_workflow_summary() -> None:
    """Render concise campaign workspace summary from current session state."""
    review_result = st.session_state.get("review_result")
    preview_result = st.session_state.get("preview_result")
    population_result = st.session_state.get("population_result")

    records = safe_get(review_result, "records", []) or []
    selected_records = safe_get(preview_result, "selected_records", []) or []

    st.subheader("Current Session Summary")
    st.markdown(
        f"- **Reviewed source records:** {len(records)}\n"
        f"- **Selected influencers:** {len(selected_records)}\n"
        f"- **Preview valid:** {'Yes' if bool(safe_get(preview_result, 'is_valid', False)) else 'No'}\n"
        f"- **Workbook generated:** {'Yes' if bool(safe_get(population_result, 'is_successful', False)) else 'No'}"
    )


def render_workflow_links() -> None:
    """Render quick navigation links for workflow steps."""
    st.subheader("Workflow Links")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.page_link("pages/uploadcsv.py", label="Step 1: Upload Later Export")
    with col2:
        st.page_link("pages/reviewdata.py", label="Step 2: Review Data")
    with col3:
        st.page_link("pages/generateworkbook.py", label="Step 3: Generate Workbook")


def render_reset_action() -> None:
    """Render start-new-run action with workflow reset and navigation."""
    st.subheader("Reset")
    st.caption("Clears workflow session state and returns to Step 1.")
    if st.button("Start New Run", type="primary"):
        clear_workflow_session_state()
        switch_to_page("pages/uploadcsv.py")
        st.rerun()


def main() -> None:
    """Render campaign workspace page with flow links and reset action."""
    st.set_page_config(page_title="Campaign Workspace", page_icon="??", layout="wide")

    st.title("Campaign Workspace")
    st.markdown(
        "Use this page for quick workflow navigation and a concise session summary."
    )
    st.divider()

    render_workflow_summary()
    st.divider()
    render_workflow_links()
    st.divider()
    render_reset_action()


if __name__ == "__main__":
    main()
