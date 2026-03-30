from __future__ import annotations

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
        "Automate campaign template population from reviewed Later Excel exports."
    )


def render_primary_cta() -> None:
    """Render primary start action for workbook flow."""
    if st.button("Go to Upload Later Export", type="primary", use_container_width=True):
        switch_to_page("pages/uploadcsv.py")


def render_reset_action() -> None:
    """Render start-new-run action for workbook flow."""
    if st.button("Start New Run", use_container_width=True):
        clear_workflow_session_state()
        switch_to_page("pages/uploadcsv.py")
        st.rerun()


def main() -> None:
    """Render workbook automation module entry page."""
    st.set_page_config(page_title="Workbook Automation", page_icon="??", layout="wide")
    hide_default_streamlit_sidebar_nav()

    render_header()
    st.divider()
    render_primary_cta()
    st.divider()
    render_reset_action()


if __name__ == "__main__":
    main()
