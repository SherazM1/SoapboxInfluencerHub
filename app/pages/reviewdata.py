from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.campaign_service import build_campaign_preview

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None


def safe_get(value: Any, field_name: str, default: Any = None) -> Any:
    """Safely read object or dict fields without raising attribute errors."""
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(field_name, default)
    return getattr(value, field_name, default)


def get_review_result() -> Any:
    """Return reviewed source result from session state when available."""
    return st.session_state.get("review_result")


def get_available_influencer_names(review_result: Any) -> list[str]:
    """Build canonical influencer name options from reviewed parsed records."""
    records = safe_get(review_result, "records", []) or []
    names: list[str] = []
    seen: set[str] = set()
    for record in records:
        name = str(safe_get(record, "canonical_name", "") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def build_parsed_records_dataframe(records: list[Any]) -> Any:
    """Convert parsed records into a compact source-review table."""
    rows: list[dict[str, str]] = []
    for record in records:
        phone_display = safe_get(record, "phone_display", "")
        phone_raw = safe_get(record, "phone_raw", "")
        rows.append(
            {
                "canonical_name": str(safe_get(record, "canonical_name", "") or ""),
                "email": str(safe_get(record, "email", "") or ""),
                "phone": str(phone_display or phone_raw or ""),
                "location_display": str(safe_get(record, "location_display", "") or ""),
                "instagram_handle": str(safe_get(record, "instagram_handle", "") or ""),
                "tiktok_handle": str(safe_get(record, "tiktok_handle", "") or ""),
                "platform_display_candidate": str(
                    safe_get(record, "platform_display_candidate", "") or ""
                ),
            }
        )
    if pd is not None:
        return pd.DataFrame(rows)
    return rows


def build_section_dataframe(rows: list[Any]) -> Any:
    """Convert mapped row objects into a preview-friendly tabular structure."""
    table_rows: list[dict[str, Any]] = []
    for row in rows:
        if isinstance(row, dict):
            table_rows.append(dict(row))
            continue
        if hasattr(row, "__dict__"):
            table_rows.append(
                {key: value for key, value in vars(row).items() if not key.startswith("_")}
            )
            continue
        keys = [
            key
            for key in dir(row)
            if not key.startswith("_") and not callable(getattr(row, key, None))
        ]
        table_rows.append({key: getattr(row, key, None) for key in keys})

    if pd is not None:
        return pd.DataFrame(table_rows)
    return table_rows


def clear_population_state() -> None:
    """Clear only downstream generation state that becomes stale after preview rebuild."""
    for key in ("template_path", "population_result"):
        if key in st.session_state:
            del st.session_state[key]


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


def render_bottom_navigation(preview_result: Any) -> None:
    """Render guided back/next page controls for workflow progression."""
    st.subheader("Navigation")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("<- Back to Upload", use_container_width=True):
            switch_to_page("pages/uploadcsv.py")
    with col2:
        can_continue = preview_result is not None
        if st.button(
            "Next -> Generate Workbook",
            use_container_width=True,
            disabled=not can_continue,
        ):
            switch_to_page("pages/generateworkbook.py")
    if preview_result is None:
        st.caption("Build a preview before continuing to workbook generation.")


def render_preview_sections(preview_result: Any) -> None:
    """Render all mapped preview sections for workflow and influencer rounds."""
    mapping_result = safe_get(preview_result, "mapping_result", None)
    st.subheader("Mapped Preview Sections")

    if mapping_result is None:
        st.info("No mapped preview sections available yet.")
        return

    workflow_tab, rounds_tab = st.tabs(["Workflow", "Influencer Rounds"])

    with workflow_tab:
        workflow_sections = [
            (
                "Workflow Influencer Details",
                safe_get(mapping_result, "workflow_influencer_details_rows", []) or [],
            ),
            (
                "Workflow Draft Stages",
                safe_get(mapping_result, "workflow_draft_stage_rows", []) or [],
            ),
            (
                "Workflow Live Content",
                safe_get(mapping_result, "workflow_live_content_rows", []) or [],
            ),
            (
                "Workflow Content Checks",
                safe_get(mapping_result, "workflow_content_check_rows", []) or [],
            ),
        ]

        for section_title, rows in workflow_sections:
            with st.expander(section_title, expanded=False):
                if not rows:
                    st.caption("No rows in this section.")
                else:
                    st.dataframe(build_section_dataframe(rows), use_container_width=True)

    with rounds_tab:
        rounds_sections = [
            ("Influencer Rounds Round 1", safe_get(mapping_result, "round_1_rows", []) or []),
            (
                "Influencer Rounds Recruiting",
                safe_get(mapping_result, "recruiting_rows", []) or [],
            ),
        ]

        for section_title, rows in rounds_sections:
            with st.expander(section_title, expanded=False):
                if not rows:
                    st.caption("No rows in this section.")
                else:
                    st.dataframe(build_section_dataframe(rows), use_container_width=True)


def render_next_step_guidance(preview_result: Any) -> None:
    """Show next-step guidance based on preview validity and blocking issues."""
    st.subheader("Next Step")

    preview_valid = bool(safe_get(preview_result, "is_valid", False))
    unresolved_selected = safe_get(preview_result, "unresolved_selected_identifiers", []) or []
    unresolved_recruiting = safe_get(
        preview_result,
        "unresolved_recruiting_identifiers",
        [],
    ) or []

    combined_validation = safe_get(preview_result, "combined_validation", None)
    has_validation_errors = bool(safe_get(combined_validation, "has_errors", False))

    if preview_valid and not unresolved_selected and not unresolved_recruiting:
        st.success(
            "Preview is valid. Continue to **generateworkbook** to select/upload the "
            "template and produce the campaign workbook."
        )
    elif has_validation_errors or unresolved_selected or unresolved_recruiting:
        st.warning(
            "Fix unresolved identifiers or blocking validation errors, then rebuild preview "
            "before proceeding to workbook generation."
        )
    else:
        st.info("Build or rebuild preview, then continue to **generateworkbook** when ready.")


def render_source_summary(review_result: Any) -> None:
    """Render concise reviewed-source summary metrics."""
    st.subheader("Parsed Source Summary")

    review_succeeded = bool(safe_get(review_result, "is_successful", False))
    records = safe_get(review_result, "records", []) or []
    parsed_count = len(records) if isinstance(records, list) else 0

    parsed_validation = safe_get(review_result, "parsed_validation", None)
    warning_count = safe_get(parsed_validation, "warning_count", "Not available")
    error_count = safe_get(parsed_validation, "error_count", "Not available")

    st.markdown(
        f"- **Source review succeeded:** {'Yes' if review_succeeded else 'No'}\n"
        f"- **Parsed influencer count:** {parsed_count}\n"
        f"- **Validation warnings:** {warning_count}\n"
        f"- **Validation errors:** {error_count}"
    )


def render_parsed_records_table(review_result: Any) -> None:
    """Render compact parsed-record influencer pool table."""
    st.subheader("Parsed Influencer Pool")
    records = safe_get(review_result, "records", []) or []
    if not records:
        st.info("No parsed records available in this reviewed source.")
        return

    table = build_parsed_records_dataframe(records)
    st.dataframe(table, use_container_width=True, hide_index=True)


def default_multiselect_values(options: list[str], stored_values: Any) -> list[str]:
    """Return valid default multiselect values while preserving stored order."""
    if not isinstance(stored_values, list):
        return []
    option_set = set(options)
    return [value for value in stored_values if value in option_set]


def main() -> None:
    """Render review, selection, and preview page for campaign workflow."""
    st.set_page_config(page_title="Review Data", page_icon="??", layout="wide")
    hide_default_streamlit_sidebar_nav()

    st.title("Review Data and Build Campaign Preview")
    st.markdown(
        "Inspect the reviewed **Later Excel source data**, select influencers, and build a "
        "mapped campaign preview before workbook generation."
    )
    st.divider()

    review_result = get_review_result()
    if review_result is None:
        st.error("No reviewed source found in session.")
        st.info("Go to **uploadcsv** first to upload and review the Later Excel export.")
        st.stop()

    render_source_summary(review_result)
    st.divider()

    render_parsed_records_table(review_result)
    st.divider()

    available_names = get_available_influencer_names(review_result)

    st.subheader("Selected Influencer Controls")
    selected_defaults = default_multiselect_values(
        available_names,
        st.session_state.get("selected_identifiers"),
    )
    selected_identifiers = st.multiselect(
        "Select campaign influencers (canonical names)",
        options=available_names,
        default=selected_defaults,
        help="Selected influencers drive Workflow and Round 1 preview sections.",
    )
    st.session_state["selected_identifiers"] = selected_identifiers

    st.subheader("Recruiting Controls")
    use_selected_for_recruiting = st.checkbox(
        "Use selected influencers for recruiting",
        value=not bool(st.session_state.get("recruiting_identifiers")),
    )

    if use_selected_for_recruiting:
        recruiting_identifiers = list(selected_identifiers)
        st.session_state["recruiting_identifiers"] = recruiting_identifiers
        st.caption("Recruiting list mirrors selected influencers.")
    else:
        recruiting_defaults = default_multiselect_values(
            available_names,
            st.session_state.get("recruiting_identifiers"),
        )
        recruiting_identifiers = st.multiselect(
            "Select recruiting influencers (optional separate list)",
            options=available_names,
            default=recruiting_defaults,
        )
        st.session_state["recruiting_identifiers"] = recruiting_identifiers

    st.divider()
    st.subheader("Preview Trigger")

    if st.button("Build Campaign Preview", type="primary"):
        if not selected_identifiers:
            st.warning("Select at least one influencer before building preview.")
        else:
            parsed_records = safe_get(review_result, "records", []) or []
            recruiting_arg = None if use_selected_for_recruiting else recruiting_identifiers

            preview_result = build_campaign_preview(
                parsed_records=parsed_records,
                selected_identifiers=selected_identifiers,
                recruiting_identifiers=recruiting_arg,
            )

            st.session_state["preview_result"] = preview_result
            clear_population_state()

            if bool(safe_get(preview_result, "is_valid", False)):
                st.success("Preview built successfully.")
            else:
                st.warning("Preview built with issues. Review unresolved identifiers and validation.")

    preview_result = st.session_state.get("preview_result")
    if preview_result is None:
        st.info("Build a preview to review mapped sections and validation status.")
        st.divider()
        render_bottom_navigation(None)
        return

    runtime_errors = safe_get(preview_result, "errors", []) or []
    if runtime_errors:
        st.subheader("Runtime / Service Errors")
        for error in runtime_errors:
            st.error(str(error))

    st.divider()
    render_preview_sections(preview_result)
    st.divider()
    render_next_step_guidance(preview_result)
    st.divider()
    render_bottom_navigation(preview_result)


if __name__ == "__main__":
    main()
