from __future__ import annotations

from dataclasses import dataclass
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
UPLOAD_PAGE_PATH = "pages/uploadcsv.py"
REVIEW_PAGE_PATH = "pages/reviewdata.py"
GENERATE_PAGE_PATH = "pages/generateworkbook.py"


@dataclass(slots=True)
class WorkflowStatus:
    """Computed workflow progression state for landing-page guidance."""

    review_complete: bool
    preview_complete: bool
    template_selected: bool
    population_attempted: bool
    population_success: bool
    next_step_page: str | None
    next_step_message: str


def safe_get(obj: Any, attribute: str, default: Any = None) -> Any:
    """Safely fetch a field from a dict-like or object-like value."""
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(attribute, default)
    return getattr(obj, attribute, default)


def normalize_bool(value: Any) -> bool:
    """Normalize unknown value into a boolean without raising errors."""
    return bool(value)


def get_workflow_status() -> WorkflowStatus:
    """Inspect session state and compute progress plus recommended next step."""
    review_result = st.session_state.get("review_result")
    preview_result = st.session_state.get("preview_result")
    template_path = st.session_state.get("template_path")
    population_result = st.session_state.get("population_result")

    review_complete = review_result is not None
    preview_complete = preview_result is not None
    template_selected = normalize_bool(template_path)
    population_attempted = population_result is not None
    population_success = normalize_bool(safe_get(population_result, "is_successful", False))

    if not review_complete:
        return WorkflowStatus(
            review_complete=review_complete,
            preview_complete=preview_complete,
            template_selected=template_selected,
            population_attempted=population_attempted,
            population_success=population_success,
            next_step_page="uploadcsv",
            next_step_message="Upload and review the Later export workbook.",
        )

    if not preview_complete:
        return WorkflowStatus(
            review_complete=review_complete,
            preview_complete=preview_complete,
            template_selected=template_selected,
            population_attempted=population_attempted,
            population_success=population_success,
            next_step_page="reviewdata",
            next_step_message="Review parsed data, select influencers, and build preview.",
        )

    if not population_success:
        return WorkflowStatus(
            review_complete=review_complete,
            preview_complete=preview_complete,
            template_selected=template_selected,
            population_attempted=population_attempted,
            population_success=population_success,
            next_step_page="generateworkbook",
            next_step_message="Select/upload a template and generate the campaign workbook.",
        )

    return WorkflowStatus(
        review_complete=review_complete,
        preview_complete=preview_complete,
        template_selected=template_selected,
        population_attempted=population_attempted,
        population_success=population_success,
        next_step_page=None,
        next_step_message="Workbook generated. Review output or start a new run.",
    )


def get_logo_path() -> Path:
    """Resolve the root-level logo path from the nested app directory."""
    return Path(__file__).resolve().parents[1] / "assets" / "logo.png"


def render_header() -> None:
    """Render the landing-page header with logo, title, and introduction."""
    logo_col, title_col = st.columns([1, 5])
    with logo_col:
        logo_path = get_logo_path()
        if logo_path.exists() and logo_path.is_file():
            st.image(str(logo_path), width=120)
    with title_col:
        st.title("Soapbox - Influencer Campaign Hub")
        st.markdown(
            "Use this app to move from a Later export to a validated, template-ready "
            "campaign workbook with a guided step-by-step workflow."
        )


def render_workflow_overview() -> None:
    """Render the high-level phase-1 workflow orientation."""
    st.subheader("Workflow Overview")
    st.markdown(
        "1. **Upload Later export**  \n"
        "2. **Review parsed data and build preview**  \n"
        "3. **Generate workbook from template**"
    )


def render_required_inputs() -> None:
    """Render required file/input callouts for the workflow."""
    st.subheader("Required Inputs")
    st.info(
        "- Later export workbook\n"
        "- Excel campaign template\n"
        "- Selected influencers from the preview step"
    )


def render_session_status(status: WorkflowStatus) -> None:
    """Render current workflow completion status from session state."""
    st.subheader("Current Session Status")

    if status.review_complete:
        st.success("Later export uploaded/reviewed: Complete")
    else:
        st.warning("Later export uploaded/reviewed: Not started")

    if status.preview_complete:
        st.success("Influencer preview built: Complete")
    else:
        st.warning("Influencer preview built: Not started")

    if status.template_selected:
        st.success("Template selected: Complete")
    else:
        st.warning("Template selected: Not selected yet")

    if status.population_success:
        st.success("Workbook generated: Complete")
    elif status.population_attempted:
        st.warning("Workbook generated: Attempted but not successful")
    else:
        st.warning("Workbook generated: Not started")


def render_next_step(status: WorkflowStatus) -> None:
    """Render recommended next navigation target based on progress."""
    st.subheader("Next Recommended Step")
    if status.next_step_page is None:
        st.success(status.next_step_message)
    else:
        st.info(
            f"Go to **{status.next_step_page}** next. "
            f"{status.next_step_message}"
        )


def switch_to_page(page_path: str) -> None:
    """Navigate to a target Streamlit page using native page switching when available."""
    switch_page = getattr(st, "switch_page", None)
    if callable(switch_page):
        switch_page(page_path)


def render_workflow_cta(status: WorkflowStatus) -> None:
    """Render direct workflow navigation calls to action."""
    st.subheader("Workflow Actions")

    col1, col2 = st.columns(2)
    with col1:
        if st.button("Go to Upload Later Export", type="primary", use_container_width=True):
            switch_to_page(UPLOAD_PAGE_PATH)
    with col2:
        next_page_path = {
            "uploadcsv": UPLOAD_PAGE_PATH,
            "reviewdata": REVIEW_PAGE_PATH,
            "generateworkbook": GENERATE_PAGE_PATH,
        }.get(status.next_step_page)
        if next_page_path:
            st.page_link(next_page_path, label="Open Recommended Step")


def render_quick_summary() -> None:
    """Render concise summary values from available session data."""
    st.subheader("Quick Summary")

    review_result = st.session_state.get("review_result")
    preview_result = st.session_state.get("preview_result")
    population_result = st.session_state.get("population_result")

    parsed_records = safe_get(review_result, "records", None)
    parsed_count = len(parsed_records) if isinstance(parsed_records, list) else None

    selected_records = safe_get(preview_result, "selected_records", None)
    if isinstance(selected_records, list):
        selected_count: int | None = len(selected_records)
    else:
        selected_identifiers = st.session_state.get("selected_identifiers")
        selected_count = (
            len(selected_identifiers) if isinstance(selected_identifiers, list) else None
        )

    preview_valid_value = safe_get(preview_result, "is_valid", None)
    if preview_valid_value is None:
        preview_valid_display = "Not available"
    else:
        preview_valid_display = "Valid" if bool(preview_valid_value) else "Needs review"

    population_success = safe_get(population_result, "is_successful", None)
    if population_success is None:
        workbook_status = "Not started"
    else:
        workbook_status = "Generated" if bool(population_success) else "Not generated"

    st.markdown(
        f"- **Parsed influencer count:** {parsed_count if parsed_count is not None else 'Not available'}\n"
        f"- **Selected influencer count:** {selected_count if selected_count is not None else 'Not available'}\n"
        f"- **Preview validity:** {preview_valid_display}\n"
        f"- **Workbook generation status:** {workbook_status}"
    )


def clear_workflow_session_state() -> None:
    """Clear only workflow-related session keys."""
    for key in WORKFLOW_SESSION_KEYS:
        if key in st.session_state:
            del st.session_state[key]


def render_reset_action() -> None:
    """Render reset button to start a clean workflow run."""
    st.subheader("Reset / Start New Run")
    st.caption("Clears workflow data from this session only.")
    if st.button("Start New Run", use_container_width=False):
        clear_workflow_session_state()
        switch_to_page(UPLOAD_PAGE_PATH)
        st.rerun()


def main() -> None:
    """Render landing-page dashboard for workflow orientation and status."""
    st.set_page_config(
        page_title="KKG Campaign Automation",
        page_icon="??",
        layout="wide",
    )

    render_header()
    st.divider()

    render_workflow_overview()
    st.divider()

    render_required_inputs()
    st.divider()

    workflow_status = get_workflow_status()
    render_session_status(workflow_status)
    st.divider()

    render_next_step(workflow_status)
    st.divider()
    render_workflow_cta(workflow_status)
    st.divider()

    render_quick_summary()
    st.divider()

    render_reset_action()


if __name__ == "__main__":
    main()
