from __future__ import annotations

from pathlib import Path
import sys
import re
from typing import Any

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.campaign_service import review_later_export

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None


DOWNSTREAM_SESSION_KEYS = [
    "selected_identifiers",
    "recruiting_identifiers",
    "preview_result",
    "template_path",
    "population_result",
]
REVIEW_PAGE_PATH = "pages/reviewdata.py"
CAMPAIGNS_PAGE_PATH = "pages/campaigns.py"


def safe_get(value: Any, field_name: str, default: Any = None) -> Any:
    """Safely read object or dict fields without raising attribute errors."""
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(field_name, default)
    return getattr(value, field_name, default)


def get_project_root() -> Path:
    """Return project root path from nested page file location."""
    return Path(__file__).resolve().parents[2]


def get_uploads_directory() -> Path:
    """Return workflow uploads directory path under project root."""
    return get_project_root() / "uploads"


def sanitize_filename(file_name: str) -> str:
    """Normalize uploaded file name into a safe local filename."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", file_name).strip("._")
    if not cleaned:
        cleaned = "later_export.xlsx"
    if not cleaned.lower().endswith(".xlsx"):
        cleaned = f"{cleaned}.xlsx"
    return cleaned


def save_uploaded_source_file(uploaded_file: Any) -> Path | None:
    """Save uploaded Later workbook to disk and return the saved path."""
    if uploaded_file is None:
        return None

    uploads_dir = get_uploads_directory()
    uploads_dir.mkdir(parents=True, exist_ok=True)

    safe_name = sanitize_filename(safe_get(uploaded_file, "name", "later_export.xlsx"))
    destination = uploads_dir / safe_name
    destination.write_bytes(uploaded_file.getvalue())
    return destination


def clear_downstream_session_state() -> None:
    """Clear stale downstream workflow state after successful source review."""
    for key in DOWNSTREAM_SESSION_KEYS:
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


def render_bottom_navigation(review_result: Any) -> None:
    """Render guided bottom navigation for workflow progression."""
    st.subheader("Navigation")
    is_ready = bool(safe_get(review_result, "is_successful", False))
    col1, col2 = st.columns(2)
    with col1:
        if st.button("<- Back to Workbook Automation", use_container_width=True):
            switch_to_page(CAMPAIGNS_PAGE_PATH)
    with col2:
        if st.button(
            "Next -> Review Data",
            disabled=not is_ready,
            use_container_width=True,
        ):
            switch_to_page(REVIEW_PAGE_PATH)

    if not is_ready:
        st.caption("Complete a successful review on this page to continue.")


def get_issue_severity(issue: Any) -> str:
    """Read severity from validation issue object safely."""
    severity = safe_get(issue, "severity", "").lower()
    return severity if severity in {"error", "warning", "info"} else "info"


def get_issue_message(issue: Any) -> str:
    """Build a readable validation issue message from issue payload."""
    code = safe_get(issue, "code", "")
    message = safe_get(issue, "message", "")
    field_name = safe_get(issue, "field_name", "")
    identifier = safe_get(issue, "record_identifier", "")

    extras: list[str] = []
    if code:
        extras.append(f"code={code}")
    if field_name:
        extras.append(f"field={field_name}")
    if identifier:
        extras.append(f"record={identifier}")

    suffix = f" ({', '.join(extras)})" if extras else ""
    return f"{message}{suffix}" if message else f"Validation issue{suffix}"


def display_validation_messages(parsed_validation: Any, errors: list[str] | None = None) -> None:
    """Render runtime/service errors and parsed validation issues."""
    st.subheader("Review Issues")

    has_content = False

    if errors:
        has_content = True
        for error in errors:
            st.error(error)

    issues = safe_get(parsed_validation, "issues", [])
    if issues:
        error_messages: list[str] = []
        warning_messages: list[str] = []
        info_messages: list[str] = []

        for issue in issues:
            severity = get_issue_severity(issue)
            message = get_issue_message(issue)
            if severity == "error":
                error_messages.append(message)
            elif severity == "warning":
                warning_messages.append(message)
            else:
                info_messages.append(message)

        if error_messages:
            has_content = True
            st.error("Validation Errors")
            for message in error_messages:
                st.markdown(f"- {message}")

        if warning_messages:
            has_content = True
            st.warning("Validation Warnings")
            for message in warning_messages:
                st.markdown(f"- {message}")

        if info_messages:
            has_content = True
            st.info("Validation Notes")
            for message in info_messages:
                st.markdown(f"- {message}")

    if not has_content:
        st.success("No runtime or validation issues to display.")


def build_records_preview_rows(records: list[Any]) -> list[dict[str, str]]:
    """Build compact parsed-record preview rows from record objects."""
    preview_rows: list[dict[str, str]] = []

    for record in records:
        phone_display = safe_get(record, "phone_display", "")
        phone_raw = safe_get(record, "phone_raw", "")
        preview_rows.append(
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

    return preview_rows


def display_records_preview(records: list[Any]) -> None:
    """Render compact parsed records preview table safely."""
    st.subheader("Parsed Records Preview")

    if not records:
        st.info("No parsed records available to preview.")
        return

    preview_rows = build_records_preview_rows(records)
    if pd is not None:
        st.dataframe(pd.DataFrame(preview_rows), use_container_width=True, hide_index=True)
    else:
        st.dataframe(preview_rows, use_container_width=True)


def render_next_step_guidance(review_result: Any) -> None:
    """Show next page recommendation after source review completion."""
    st.subheader("Next Step")
    if bool(safe_get(review_result, "is_successful", False)):
        st.success(
            "Source review is complete. Continue to **reviewdata** to select influencers "
            "and build the campaign preview."
        )
    else:
        st.warning("Resolve review issues on this page before moving to the next step.")


def render_page_header() -> None:
    """Render page title and high-level explanation."""
    st.title("Upload Later Excel Export")
    st.markdown(
        "Upload and review the **Later Excel workbook (.xlsx)** used as the source "
        "data for this workflow."
    )


def render_uploaded_file_info(uploaded_file: Any) -> None:
    """Render uploaded file metadata when a file is currently selected."""
    if uploaded_file is None:
        st.caption("No file uploaded yet.")
        return

    file_name = safe_get(uploaded_file, "name", "Unknown")
    file_type = safe_get(uploaded_file, "type", "Unknown")
    file_size = safe_get(uploaded_file, "size", 0)
    size_kb = round(file_size / 1024, 1) if isinstance(file_size, (int, float)) else "Unknown"

    st.caption(
        f"Uploaded file: **{file_name}** | Type: **{file_type}** | Size: **{size_kb} KB**"
    )


def main() -> None:
    """Render source upload/review page and persist results to session state."""
    st.set_page_config(page_title="Upload Later Export", page_icon="??", layout="wide")
    hide_default_streamlit_sidebar_nav()

    render_page_header()
    st.divider()

    st.subheader("Upload File")
    uploaded_file = st.file_uploader(
        "Upload Later Excel Workbook (.xlsx)",
        type=["xlsx"],
        accept_multiple_files=False,
        help="Phase-1 requires the Later Excel export workbook.",
    )
    render_uploaded_file_info(uploaded_file)

    review_result_to_display = st.session_state.get("review_result")

    if st.button("Review Uploaded Export", type="primary"):
        if uploaded_file is None:
            st.warning("Upload a Later Excel workbook (.xlsx) before running review.")
        else:
            try:
                saved_path = save_uploaded_source_file(uploaded_file)
            except Exception as exc:
                st.error(f"Failed to save uploaded file: {exc}")
                saved_path = None

            if saved_path is not None:
                service_result = review_later_export(saved_path)
                review_result_to_display = service_result

                if bool(safe_get(service_result, "is_successful", False)):
                    clear_downstream_session_state()
                    st.session_state["review_result"] = service_result
                    st.session_state["later_export_path"] = str(saved_path)
                    st.success("Later export reviewed successfully.")
                else:
                    st.error("Review failed. Check issues below.")

    if review_result_to_display is not None:
        st.divider()
        display_validation_messages(
            parsed_validation=safe_get(review_result_to_display, "parsed_validation", None),
            errors=safe_get(review_result_to_display, "errors", []) or None,
        )
        st.divider()
        display_records_preview(safe_get(review_result_to_display, "records", []) or [])
        st.divider()
        render_next_step_guidance(review_result_to_display)

    st.divider()
    render_bottom_navigation(review_result_to_display)


if __name__ == "__main__":
    main()
