from __future__ import annotations

import streamlit as st

LEGACY_WORKFLOW_SESSION_KEYS = [
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
    else:
        st.error(f"Unable to navigate to {page_path} in this Streamlit version.")


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


def clear_legacy_workflow_session_state() -> None:
    """Clear only deprecated workbook workflow session keys."""
    for key in LEGACY_WORKFLOW_SESSION_KEYS:
        if key in st.session_state:
            del st.session_state[key]
