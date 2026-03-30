from __future__ import annotations

from pathlib import Path
import sys
import re
from typing import Any

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.campaign_service import populate_campaign_template

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


def get_project_root() -> Path:
    """Resolve project root from nested page location."""
    return Path(__file__).resolve().parents[2]


def get_templates_directory() -> Path:
    """Return workflow template upload directory path."""
    return get_project_root() / "templates"


def get_outputs_directory() -> Path:
    """Return workflow output workbook directory path."""
    return get_project_root() / "outputs"


def sanitize_filename(filename: str, default_name: str) -> str:
    """Return a filesystem-safe filename with fallback default."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", filename or "").strip("._")
    return cleaned or default_name


def ensure_xlsx_extension(filename: str) -> str:
    """Ensure filename ends in .xlsx extension."""
    return filename if filename.lower().endswith(".xlsx") else f"{filename}.xlsx"


def get_preview_result() -> Any:
    """Retrieve preview result from session state."""
    return st.session_state.get("preview_result")


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


def save_uploaded_template_file(uploaded_file: Any) -> Path | None:
    """Persist uploaded template workbook under templates workflow directory."""
    if uploaded_file is None:
        return None

    templates_dir = get_templates_directory()
    templates_dir.mkdir(parents=True, exist_ok=True)

    uploaded_name = str(safe_get(uploaded_file, "name", "template.xlsx"))
    safe_name = ensure_xlsx_extension(sanitize_filename(uploaded_name, "template.xlsx"))
    destination = templates_dir / safe_name
    destination.write_bytes(uploaded_file.getvalue())
    return destination


def build_default_output_filename(template_name: str) -> str:
    """Build default generated workbook filename from template name."""
    template_base = Path(template_name).stem if template_name else "campaign_template"
    safe_base = sanitize_filename(template_base, "campaign_template")
    return f"{safe_base}_populated.xlsx"


def build_output_path(output_filename: str) -> Path:
    """Build stable output file path under outputs workflow directory."""
    outputs_dir = get_outputs_directory()
    outputs_dir.mkdir(parents=True, exist_ok=True)

    safe_name = sanitize_filename(output_filename, "campaign_output.xlsx")
    safe_name = ensure_xlsx_extension(safe_name)
    return outputs_dir / safe_name


def display_preview_readiness(preview_result: Any) -> None:
    """Render compact final readiness summary from preview result."""
    st.subheader("Preview Readiness Summary")

    selected_records = safe_get(preview_result, "selected_records", []) or []
    recruiting_records = safe_get(preview_result, "recruiting_records", []) or []
    preview_valid = bool(safe_get(preview_result, "is_valid", False))

    unresolved_selected = safe_get(preview_result, "unresolved_selected_identifiers", []) or []
    unresolved_recruiting = (
        safe_get(preview_result, "unresolved_recruiting_identifiers", []) or []
    )

    combined_validation = safe_get(preview_result, "combined_validation", None)
    error_count = safe_get(combined_validation, "error_count", "Not available")
    warning_count = safe_get(combined_validation, "warning_count", "Not available")

    st.markdown(
        f"- **Selected influencer count:** {len(selected_records)}\n"
        f"- **Recruiting count:** {len(recruiting_records)}\n"
        f"- **Preview valid:** {'Yes' if preview_valid else 'No'}\n"
        f"- **Unresolved selected identifiers:** {len(unresolved_selected)}\n"
        f"- **Unresolved recruiting identifiers:** {len(unresolved_recruiting)}\n"
        f"- **Validation errors:** {error_count}\n"
        f"- **Validation warnings:** {warning_count}"
    )


def display_blocking_issues(preview_result: Any) -> None:
    """Display potential blocking issues from preview state clearly."""
    st.subheader("Blocking Issues")

    runtime_errors = safe_get(preview_result, "errors", []) or []
    unresolved_selected = safe_get(preview_result, "unresolved_selected_identifiers", []) or []
    unresolved_recruiting = (
        safe_get(preview_result, "unresolved_recruiting_identifiers", []) or []
    )

    combined_validation = safe_get(preview_result, "combined_validation", None)
    issues = safe_get(combined_validation, "issues", []) or []

    validation_error_lines: list[str] = []
    for issue in issues:
        if str(safe_get(issue, "severity", "")).lower() != "error":
            continue
        message = str(safe_get(issue, "message", "Validation error") or "Validation error")
        code = str(safe_get(issue, "code", "") or "")
        record_identifier = str(safe_get(issue, "record_identifier", "") or "")

        details: list[str] = []
        if code:
            details.append(f"code={code}")
        if record_identifier:
            details.append(f"record={record_identifier}")
        suffix = f" ({', '.join(details)})" if details else ""
        validation_error_lines.append(f"- {message}{suffix}")

    has_blocking_content = False

    if runtime_errors:
        has_blocking_content = True
        st.error("Runtime / Service Errors")
        for error in runtime_errors:
            st.markdown(f"- {error}")

    if unresolved_selected:
        has_blocking_content = True
        st.error("Unresolved selected identifiers")
        for identifier in unresolved_selected:
            st.markdown(f"- {identifier}")

    if unresolved_recruiting:
        has_blocking_content = True
        st.error("Unresolved recruiting identifiers")
        for identifier in unresolved_recruiting:
            st.markdown(f"- {identifier}")

    if validation_error_lines:
        has_blocking_content = True
        st.error("Combined validation errors")
        for line in validation_error_lines:
            st.markdown(line)

    if not has_blocking_content:
        st.success("No obvious blocking issues detected from current preview state.")


def display_population_result(population_result: Any) -> None:
    """Render blocked/failed/successful generation outcome details."""
    if population_result is None:
        return

    st.subheader("Generation Result")

    is_successful = bool(safe_get(population_result, "is_successful", False))
    blocked_reason = safe_get(population_result, "blocked_reason", None)
    errors = safe_get(population_result, "errors", []) or []
    output_path = safe_get(population_result, "output_path", None)
    write_result = safe_get(population_result, "write_result", None)

    if is_successful:
        st.success("Workbook generation completed successfully.")
    elif blocked_reason:
        st.warning(f"Generation was blocked: {blocked_reason}")
    else:
        st.error("Workbook generation failed.")

    if errors:
        st.error("Generation messages")
        for error in errors:
            st.markdown(f"- {error}")

    if output_path:
        st.info(f"Output path: `{output_path}`")

    sections_written = safe_get(write_result, "sections_written", None)
    if sections_written:
        st.markdown("**Write summary**")
        for section_name, count in sections_written.items():
            st.markdown(f"- {section_name}: {count} rows written")


def render_download_section(population_result: Any) -> None:
    """Render generated workbook download access when output exists."""
    if population_result is None:
        return

    is_successful = bool(safe_get(population_result, "is_successful", False))
    output_path_value = safe_get(population_result, "output_path", None)
    if not is_successful or not output_path_value:
        return

    output_path = Path(str(output_path_value))
    st.subheader("Download Generated Workbook")

    if not output_path.exists() or not output_path.is_file():
        st.warning("Generation reported success, but output file was not found on disk.")
        return

    file_bytes = output_path.read_bytes()
    st.download_button(
        label="Download Populated Workbook",
        data=file_bytes,
        file_name=output_path.name,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=False,
    )


def render_next_step_guidance(population_result: Any) -> None:
    """Render post-generation guidance based on result state."""
    st.subheader("Next Step")

    if population_result is None:
        st.info("Upload template and run generation when ready.")
        return

    is_successful = bool(safe_get(population_result, "is_successful", False))
    blocked_reason = safe_get(population_result, "blocked_reason", None)

    if is_successful:
        st.success("Download the generated workbook or start a new run from the main page.")
    elif blocked_reason:
        st.warning(
            "Fix blocking issues in **reviewdata** and rebuild preview before trying generation again."
        )
    else:
        st.warning("Resolve generation errors and retry template population.")


def render_bottom_navigation(population_result: Any) -> None:
    """Render guided back/start-new-run controls for final step."""
    st.subheader("Navigation")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("<- Back to Review Data", use_container_width=True):
            switch_to_page("pages/reviewdata.py")
    with col2:
        generation_success = bool(safe_get(population_result, "is_successful", False))
        if st.button(
            "Start New Run",
            use_container_width=True,
            disabled=not generation_success,
        ):
            clear_workflow_session_state()
            switch_to_page("pages/campaigns.py")
            st.rerun()
    if not bool(safe_get(population_result, "is_successful", False)):
        st.caption("Start New Run becomes available after successful generation.")


def main() -> None:
    """Render final workbook generation page."""
    st.set_page_config(page_title="Generate Workbook", page_icon="??", layout="wide")
    hide_default_streamlit_sidebar_nav()

    st.title("Generate Populated Campaign Workbook")
    st.markdown(
        "Use the current campaign preview to populate an **Excel template workbook**. "
        "This step uses your reviewed source and preview state from earlier pages."
    )
    st.caption(
        "Template upload here is separate from the Later source workbook uploaded earlier."
    )
    st.divider()

    preview_result = get_preview_result()
    if preview_result is None:
        st.error("No campaign preview found in session.")
        st.info("Go to **reviewdata** first to build a campaign preview before generation.")
        st.stop()

    display_preview_readiness(preview_result)
    st.divider()

    display_blocking_issues(preview_result)
    st.divider()

    st.subheader("Template Upload")
    uploaded_template = st.file_uploader(
        "Upload Campaign Template Workbook (.xlsx)",
        type=["xlsx"],
        accept_multiple_files=False,
        help="Upload the Excel template workbook that will be populated from preview data.",
    )

    template_name = str(safe_get(uploaded_template, "name", ""))
    if uploaded_template is None:
        st.caption("No template workbook uploaded yet.")
    else:
        template_type = str(safe_get(uploaded_template, "type", "Unknown") or "Unknown")
        template_size = safe_get(uploaded_template, "size", 0)
        size_kb = (
            round(template_size / 1024, 1)
            if isinstance(template_size, (int, float))
            else "Unknown"
        )
        st.caption(
            f"Template file: **{template_name}** | Type: **{template_type}** | "
            f"Size: **{size_kb} KB**"
        )

    st.divider()
    st.subheader("Output Settings")

    default_output_name = build_default_output_filename(template_name)
    output_filename = st.text_input(
        "Output filename",
        value=default_output_name,
        help="Generated workbook will be saved under the outputs workflow directory.",
    )

    st.divider()
    st.subheader("Generation Trigger")

    if st.button("Generate Workbook", type="primary"):
        if uploaded_template is None:
            st.warning("Upload a template workbook (.xlsx) before generation.")
        else:
            try:
                template_path = save_uploaded_template_file(uploaded_template)
            except Exception as exc:
                st.error(f"Failed to save uploaded template: {exc}")
                template_path = None

            if template_path is not None:
                output_path = build_output_path(output_filename)

                selected_identifiers = st.session_state.get("selected_identifiers", [])
                recruiting_identifiers = st.session_state.get("recruiting_identifiers", None)

                review_result = st.session_state.get("review_result")
                parsed_records = safe_get(review_result, "records", []) or []

                population_result = populate_campaign_template(
                    template_path=template_path,
                    parsed_records=parsed_records,
                    selected_identifiers=selected_identifiers,
                    output_path=output_path,
                    recruiting_identifiers=recruiting_identifiers,
                )

                st.session_state["template_path"] = str(template_path)
                st.session_state["population_result"] = population_result

                if bool(safe_get(population_result, "is_successful", False)):
                    st.success("Workbook generation completed.")
                else:
                    st.warning("Workbook generation did not complete successfully.")

    population_result = st.session_state.get("population_result")
    if population_result is not None:
        st.divider()
        display_population_result(population_result)
        st.divider()
        render_download_section(population_result)

    st.divider()
    render_next_step_guidance(population_result)
    st.divider()
    render_bottom_navigation(population_result)


if __name__ == "__main__":
    main()
