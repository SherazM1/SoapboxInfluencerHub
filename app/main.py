from __future__ import annotations

from pathlib import Path
import sys

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.navigation import hide_default_streamlit_sidebar_nav, switch_to_page


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
            "Select a platform function below. Campaign Operations is active now, "
            "live campaign reporting is available for client-facing updates, and "
            "Influencer Pricing is available as a foundation preview."
        )


def render_module_cards() -> None:
    """Render top-level app module sections for navigation."""
    st.subheader("Select a Function")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.markdown("### Campaign Operations")
        st.caption("Status: Active")
        st.markdown(
            "Manage campaign alignment, team workflows, progress, requests, and "
            "cross-team oversight."
        )
        if st.button("Open Campaign Operations", type="primary", use_container_width=True):
            switch_to_page("pages/campaigns.py")
        st.page_link("pages/campaigns.py", label="Go to Campaign Operations Workspace")

    with col2:
        st.markdown("### Reporting")
        st.caption("Status: Active")
        st.markdown("Create persistent live campaign reports with stable client links.")
        if st.button("Open Reporting", use_container_width=True):
            switch_to_page("pages/reporting.py")
        st.page_link("pages/reporting.py", label="Go to Reporting Workspace")

    with col3:
        st.markdown("### Influencer Pricing")
        st.caption("Status: Foundation / Preview")
        st.markdown(
            "Build campaign pricing, estimate metrics, and organize historical campaign data."
        )
        if st.button("Open Influencer Pricing", use_container_width=True):
            switch_to_page("pages/influencer_pricing.py")
        st.page_link(
            "pages/influencer_pricing.py",
            label="Go to Influencer Pricing Workspace",
        )


def main() -> None:
    """Render multi-function platform hub page."""
    st.set_page_config(page_title="Platform Hub", page_icon="??", layout="wide")
    hide_default_streamlit_sidebar_nav()

    render_header()
    st.divider()
    render_module_cards()


if __name__ == "__main__":
    main()
