from __future__ import annotations

from pathlib import Path

import streamlit as st


def switch_to_page(page_path: str) -> None:
    """Navigate to a target Streamlit page using native page switching when available."""
    switch_page = getattr(st, "switch_page", None)
    if callable(switch_page):
        switch_page(page_path)


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


def main() -> None:
    """Render multi-function platform hub page."""
    st.set_page_config(page_title="Platform Hub", page_icon="??", layout="wide")
    hide_default_streamlit_sidebar_nav()

    render_header()
    st.divider()
    render_module_cards()


if __name__ == "__main__":
    main()
