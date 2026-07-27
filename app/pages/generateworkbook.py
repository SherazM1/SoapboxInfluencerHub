from __future__ import annotations

from pathlib import Path
import sys

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.navigation import (
    clear_legacy_workflow_session_state,
    hide_default_streamlit_sidebar_nav,
    switch_to_page,
)

CAMPAIGNS_PAGE_PATH = "pages/campaigns.py"


def main() -> None:
    """Render compatibility notice for the deprecated generation page."""
    st.set_page_config(page_title="Campaign Operations", page_icon="??", layout="wide")
    hide_default_streamlit_sidebar_nav()
    clear_legacy_workflow_session_state()

    st.title("Campaign Operations")
    st.info("Workbook Automation has been replaced by Campaign Operations.")
    if st.button("Open Campaign Operations", type="primary"):
        switch_to_page(CAMPAIGNS_PAGE_PATH)


if __name__ == "__main__":
    main()
