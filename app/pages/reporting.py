from __future__ import annotations

import re
import sys
import uuid
from datetime import date
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlsplit, urlunsplit
from urllib.request import Request, urlopen

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.reporting_db import generate_report_id, get_report, init_db, list_reports, save_report
from core.reporting_template import render_client_report

REPORT_IMAGE_DIR = ROOT_DIR / "data" / "report_images"
PLATFORM_OPTIONS = ["Instagram", "TikTok", "Facebook", "YouTube", "Other"]
EMPTY_ITEM = {
    "platform": "",
    "live_url": "",
    "image_url": "",
    "image_path": "",
}


def hide_default_streamlit_sidebar_nav() -> None:
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


def get_query_value(name: str) -> str | None:
    params = getattr(st, "query_params", {})
    value = params.get(name)
    if isinstance(value, list):
        return value[0] if value else None
    return value


def set_query_params(**params: str) -> None:
    if hasattr(st, "query_params"):
        st.query_params.clear()
        for key, value in params.items():
            st.query_params[key] = value
    else:
        st.experimental_set_query_params(**params)


def get_current_page_url() -> str:
    context = getattr(st, "context", None)
    current_url = getattr(context, "url", "") if context else ""
    if current_url:
        parts = urlsplit(current_url)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    return ""


def build_client_url(report_id: str) -> str:
    base_url = get_current_page_url()
    query = urlencode({"mode": "view", "report_id": report_id})
    return f"{base_url}?{query}" if base_url else f"?{query}"


def normalize_item(item: dict | None = None) -> dict:
    normalized = EMPTY_ITEM.copy()
    if item:
        normalized.update({key: item.get(key) or "" for key in EMPTY_ITEM})
    # Normalize the live_url in the item
    normalized["live_url"] = normalize_live_url(normalized["live_url"])
    # Auto-detect platform if not set
    if not normalized["platform"] and normalized["live_url"]:
        normalized["platform"] = detect_platform(normalized["live_url"])
    return normalized


def reset_editor(report: dict | None = None) -> None:
    if report:
        st.session_state["reporting_report_id"] = report["report_id"]
        st.session_state["reporting_content_items"] = [
            normalize_item(item) for item in report.get("content_items", [])
        ] or [normalize_item() for _ in range(3)]
    else:
        st.session_state["reporting_report_id"] = ""
        st.session_state["reporting_content_items"] = [normalize_item() for _ in range(3)]


def ensure_editor_state() -> None:
    if "reporting_content_items" not in st.session_state:
        reset_editor()


def normalize_live_url(value: str) -> str:
    """Normalize a live URL for storage and validation.
    
    - Strip whitespace
    - Return empty string if empty
    - Keep URLs that already have http(s):// scheme
    - Prepend https:// to domain-like strings (with dots)
    - Do not prepend to obvious garbage
    """
    value = (value or "").strip()
    if not value:
        return ""
    
    # Already has a scheme, keep it
    if value.startswith(("http://", "https://")):
        return value
    
    # Check if it looks like a domain/path (has a dot in the netloc)
    # This works by trying to parse it as if https:// were prepended
    parsed = urlparse(f"https://{value}")
    if "." in parsed.netloc:
        return f"https://{value}"
    
    # Otherwise, return as-is (don't auto-prepend to garbage)
    return value


def detect_platform(live_url: str) -> str:
    """Detect platform from a live URL.
    
    Resilient to URLs with or without scheme, www prefix, mixed case, etc.
    """
    # Normalize the URL first for detection
    normalized = normalize_live_url(live_url)
    host = urlparse((normalized or "").strip()).netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    if "instagram.com" in host:
        return "Instagram"
    if "tiktok.com" in host:
        return "TikTok"
    if "facebook.com" in host or "fb.watch" in host:
        return "Facebook"
    if "youtube.com" in host or "youtu.be" in host:
        return "YouTube"
    return ""


def is_http_url(value: str) -> bool:
    parsed = urlparse((value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_preview_image_url(live_url: str) -> str:
    if not is_http_url(live_url):
        return ""
    try:
        request = Request(
            live_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; SoapboxInfluencerHub/1.0; "
                    "+https://soapboxretail.com)"
                )
            },
        )
        with urlopen(request, timeout=4) as response:
            content_type = response.headers.get("content-type", "")
            if "text/html" not in content_type:
                return ""
            html = response.read(500_000).decode("utf-8", errors="ignore")
    except Exception:
        return ""

    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
    ]
    for pattern in patterns:
        match = re.search(pattern, html, flags=re.IGNORECASE)
        if match:
            image_url = match.group(1).strip()
            return image_url if is_http_url(image_url) else ""
    return ""


def save_uploaded_image(report_id: str, row_index: int, uploaded_file) -> str:
    if uploaded_file is None:
        return ""
    REPORT_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(uploaded_file.name).suffix.lower() or ".png"
    filename = f"{report_id}_{row_index}_{uuid.uuid4().hex[:8]}{suffix}"
    path = REPORT_IMAGE_DIR / filename
    path.write_bytes(uploaded_file.getbuffer())
    return str(path.relative_to(ROOT_DIR))


def render_view_mode(report_id: str | None) -> None:
    if not report_id:
        st.error("Missing report_id. Use a valid client report link.")
        return
    report = get_report(report_id)
    if not report:
        st.error("Report not found. Check the report link and try again.")
        return
    render_client_report(report)


def render_reporting_header() -> None:
    st.title("Reporting")
    st.markdown(
        "Create and update persistent live campaign reports with stable client links."
    )


def render_report_picker() -> None:
    reports = list_reports()
    left, right = st.columns([2, 1])
    with left:
        if reports:
            options = {
                f"{r['client_name']} - {r['report_date']} ({r['report_id']})": r["report_id"]
                for r in reports
            }
            selected_label = st.selectbox("Load Existing Report", list(options.keys()))
            if st.button("Load Selected Report", use_container_width=True):
                report = get_report(options[selected_label])
                reset_editor(report)
                set_query_params(mode="edit", report_id=options[selected_label])
                st.rerun()
        else:
            st.info("No saved reports yet. Create the first report below.")
    with right:
        st.write("")
        st.write("")
        if st.button("Create New Report", type="primary", use_container_width=True):
            reset_editor()
            set_query_params(mode="edit")
            st.rerun()


def render_report_fields(report: dict | None) -> dict:
    st.subheader("Report Details")
    col1, col2 = st.columns(2)
    with col1:
        client_name = st.text_input(
            "Client Name",
            value=(report or {}).get("client_name", ""),
        )
    with col2:
        report_date = st.date_input(
            "Report Date",
            value=parse_report_date((report or {}).get("report_date")),
        )

    st.subheader("KPI Metrics")
    kpi_cols = st.columns(4)
    with kpi_cols[0]:
        organic_impressions = st.number_input(
            "Organic Impressions",
            min_value=0,
            step=100,
            value=int((report or {}).get("organic_impressions", 0) or 0),
        )
    with kpi_cols[1]:
        paid_impressions = st.number_input(
            "Paid Impressions",
            min_value=0,
            step=100,
            value=int((report or {}).get("paid_impressions", 0) or 0),
        )
    with kpi_cols[2]:
        organic_engagements = st.number_input(
            "Organic Engagements",
            min_value=0,
            step=10,
            value=int((report or {}).get("organic_engagements", 0) or 0),
        )
    with kpi_cols[3]:
        paid_engagements = st.number_input(
            "Paid Engagements",
            min_value=0,
            step=10,
            value=int((report or {}).get("paid_engagements", 0) or 0),
        )

    return {
        "report_id": st.session_state.get("reporting_report_id", ""),
        "client_name": client_name,
        "report_date": report_date.isoformat(),
        "organic_impressions": organic_impressions,
        "paid_impressions": paid_impressions,
        "organic_engagements": organic_engagements,
        "paid_engagements": paid_engagements,
    }


def parse_report_date(value: str | None) -> date:
    if not value:
        return date.today()
    try:
        return date.fromisoformat(value)
    except ValueError:
        return date.today()


def image_ref_for_preview(item: dict, auto_image_url: str, uploaded_file) -> str:
    if uploaded_file is not None:
        return uploaded_file
    return item.get("image_path") or item.get("image_url") or auto_image_url


def render_image_preview(image_ref) -> None:
    if image_ref:
        if isinstance(image_ref, str) and image_ref.startswith("data/"):
            image_ref = ROOT_DIR / image_ref
        st.image(image_ref, use_container_width=True)
    else:
        st.markdown(
            """
            <div style="
                align-items:center;
                background:#effafb;
                border:1px dashed #9bd7dc;
                border-radius:14px;
                color:#247f87;
                display:flex;
                font-weight:700;
                height:148px;
                justify-content:center;">
                Image preview unavailable
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_platform_input(index: int, live_url: str, current_platform: str) -> str:
    detected_platform = detect_platform(live_url)
    default_platform = current_platform or detected_platform
    selected_value = default_platform if default_platform in PLATFORM_OPTIONS else "Other"
    select_key = f"content_platform_select_{index}"
    if detected_platform and not current_platform and st.session_state.get(select_key) in {None, "", "Other"}:
        st.session_state[select_key] = detected_platform
    selected = st.selectbox(
        "Platform",
        PLATFORM_OPTIONS,
        index=PLATFORM_OPTIONS.index(selected_value),
        key=select_key,
    )
    if selected == "Other":
        return st.text_input(
            "Custom Platform",
            value="" if default_platform in PLATFORM_OPTIONS else default_platform,
            key=f"content_platform_custom_{index}",
        )
    return selected


def sync_content_items_from_widgets(report_id: str | None = None) -> list[dict]:
    items = []
    for index, item in enumerate(st.session_state["reporting_content_items"]):
        # Read and normalize the live URL immediately
        raw_live_url = st.session_state.get(f"content_live_url_{index}", item["live_url"])
        live_url = normalize_live_url(raw_live_url)
        
        # Auto-detect platform from normalized URL if not explicitly set
        selected_platform = st.session_state.get(
            f"content_platform_select_{index}",
            item["platform"] or detect_platform(live_url),
        )
        if selected_platform == "Other":
            platform = st.session_state.get(f"content_platform_custom_{index}", "").strip()
        else:
            platform = selected_platform
        
        # If platform is still blank after UI interaction, try again from normalized URL
        if not platform:
            platform = detect_platform(live_url)
        
        uploaded_file = st.session_state.get(f"content_image_upload_{index}")
        image_path = item.get("image_path", "")
        image_url = item.get("image_url", "")
        if report_id and uploaded_file is not None:
            image_path = save_uploaded_image(report_id, index, uploaded_file)
            image_url = ""
        elif not image_path and not image_url:
            # Use normalized URL for preview image fetching
            image_url = fetch_preview_image_url(live_url)
        items.append(
            {
                "platform": platform.strip(),
                "live_url": live_url,
                "image_url": image_url.strip(),
                "image_path": image_path.strip(),
            }
        )
    st.session_state["reporting_content_items"] = items
    return items


def render_content_editor() -> None:
    st.subheader("Featured Content Items")
    st.caption("Paste live post links. Platform and preview image are filled in when the URL provides enough metadata.")

    for index, item in enumerate(st.session_state["reporting_content_items"]):
        with st.expander(f"Content Item {index + 1}", expanded=index < 3):
            top_cols = st.columns([2, 1, 1])
            with top_cols[0]:
                live_url = st.text_input(
                    "Live URL",
                    value=item["live_url"],
                    key=f"content_live_url_{index}",
                    placeholder="https://www.instagram.com/...",
                )
            with top_cols[1]:
                platform = render_platform_input(index, live_url, item["platform"])
            with top_cols[2]:
                st.write("")
                st.write("")
                if st.button("Remove Row", key=f"remove_content_{index}", use_container_width=True):
                    sync_content_items_from_widgets()
                    st.session_state["reporting_content_items"].pop(index)
                    if not st.session_state["reporting_content_items"]:
                        st.session_state["reporting_content_items"].append(normalize_item())
                    st.rerun()

            detected_platform = detect_platform(live_url)
            if detected_platform and detected_platform == platform:
                st.caption(f"Platform detected from URL: {detected_platform}")
            elif not detected_platform and live_url:
                st.caption("Platform could not be detected confidently. Choose one from the dropdown.")

            auto_image_url = fetch_preview_image_url(live_url)
            upload_cols = st.columns([1, 1])
            with upload_cols[0]:
                uploaded_file = st.file_uploader(
                    "Image upload fallback",
                    type=["png", "jpg", "jpeg", "webp"],
                    key=f"content_image_upload_{index}",
                )
                if auto_image_url and not item.get("image_path") and not uploaded_file:
                    st.caption("Preview image found from page metadata.")
                elif live_url and not auto_image_url and not item.get("image_path") and not uploaded_file:
                    st.caption("No preview image found. Upload an image or leave the placeholder.")
            with upload_cols[1]:
                render_image_preview(image_ref_for_preview(item, auto_image_url, uploaded_file))

    if st.button("Add Content Row", use_container_width=True):
        sync_content_items_from_widgets()
        st.session_state["reporting_content_items"].append(normalize_item())
        st.rerun()


def clean_content_items(items: list[dict]) -> list[dict]:
    cleaned = []
    for item in items:
        normalized = normalize_item(item)
        if normalized["live_url"].strip():
            cleaned.append(normalized)
    return cleaned


def validate_report(report: dict, content_items: list[dict]) -> list[str]:
    errors = []
    if not report["client_name"].strip():
        errors.append("Client Name is required.")
    for index, item in enumerate(content_items, start=1):
        # Normalize the URL and check if it's valid
        live_url = normalize_live_url(item["live_url"])
        if not live_url.strip():
            errors.append(f"Content item {index} needs a valid Live URL.")
        # Try to detect platform from normalized URL if not set
        platform = item["platform"].strip() or detect_platform(live_url)
        if not platform:
            errors.append(f"Content item {index} needs a Platform (could not auto-detect from URL).")
    return errors


def render_save_controls(report: dict) -> None:
    st.divider()
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Save Report", type="primary", use_container_width=True):
            if not report.get("report_id"):
                report["report_id"] = generate_report_id()
            content_items = clean_content_items(sync_content_items_from_widgets(report["report_id"]))
            errors = validate_report(report, content_items)
            if errors:
                for error in errors:
                    st.error(error)
                return
            report_id = save_report(report, content_items)
            st.session_state["reporting_report_id"] = report_id
            st.success("Report saved.")
            set_query_params(mode="edit", report_id=report_id)
            st.rerun()
    with col2:
        current_report_id = st.session_state.get("reporting_report_id")
        if current_report_id:
            if st.button("Preview Client View", use_container_width=True):
                set_query_params(mode="view", report_id=current_report_id)
                st.rerun()
        else:
            st.caption("Save the report to generate a client link.")


def render_client_link(report_id: str | None) -> None:
    if not report_id:
        return
    client_url = build_client_url(report_id)
    st.subheader("Client Link")
    st.text_input("Stable Client URL", value=client_url)
    st.caption("This URL stays the same after future saves and always loads the latest saved report data.")


def render_edit_mode(report_id: str | None) -> None:
    ensure_editor_state()
    loaded_report = get_report(report_id) if report_id else None
    if report_id and not loaded_report:
        st.warning("That report_id was not found. Create a new report or load an existing one.")
    if loaded_report and st.session_state.get("reporting_report_id") != report_id:
        reset_editor(loaded_report)
        st.rerun()

    render_reporting_header()
    st.divider()
    render_report_picker()
    st.divider()
    report_data = render_report_fields(loaded_report)
    st.divider()
    render_content_editor()
    render_save_controls(report_data)
    render_client_link(st.session_state.get("reporting_report_id"))


def main() -> None:
    st.set_page_config(page_title="Reporting", page_icon="??", layout="wide")
    hide_default_streamlit_sidebar_nav()
    init_db()

    mode = get_query_value("mode") or "edit"
    report_id = get_query_value("report_id")
    if mode == "view":
        render_view_mode(report_id)
    else:
        render_edit_mode(report_id)


if __name__ == "__main__":
    main()
