# core/reporting_template.py
from __future__ import annotations

import base64
import html
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st
import streamlit.components.v1 as components


NAVY = "#002C47"
TEAL = "#33B2C1"
MUTED = "#5D7282"
BORDER = "#DCEAF1"
SOFT_BG = "#F7FBFD"


def render_client_report(report: dict) -> None:
    """Render the client-facing campaign report in an isolated HTML component."""
    st.markdown(
        """
        <style>
        header,
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stSidebar"],
        [data-testid="stSidebarNav"] {
            display: none !important;
        }

        .stApp {
            background: #ffffff !important;
        }

        .block-container {
            max-width: 1120px !important;
            padding: 4px 14px 18px !important;
        }

        iframe,
        div[data-testid="stIFrame"],
        div[data-testid="stIFrame"] iframe {
            border: 0 !important;
            box-shadow: none !important;
            outline: 0 !important;
        }

        div[data-testid="stIFrame"] {
            overflow: hidden !important;
            background: #ffffff !important;
        }

        iframe[title="streamlit_component"] {
            display: block !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    content_items = report.get("content_items") or []
    visible_item_count = len([item for item in content_items if clean_text(item.get("live_url"))])
    visible_item_count = max(visible_item_count, 1)
    if visible_item_count <= 3:
        height = 720
    else:
        height = 720 + (visible_item_count - 3) * 118

    components.html(
        build_report_document(report),
        height=height,
        scrolling=False,
    )


def build_report_document(report: dict) -> str:
    """Build the isolated HTML document."""
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Raleway:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
        {build_css()}
    </head>
    <body>
        {build_report_html(report)}
        <script>
            function resetReportScroll() {{
                window.scrollTo(0, 0);
                try {{
                    window.parent.scrollTo(0, 0);
                }} catch (error) {{}}
            }}
            resetReportScroll();
            window.addEventListener("load", resetReportScroll);
            window.requestAnimationFrame(resetReportScroll);
            window.setTimeout(resetReportScroll, 75);
        </script>
    </body>
    </html>
    """


def build_css() -> str:
    """Build isolated report CSS."""
    return f"""
    <style>
    :root {{
        --navy: {NAVY};
        --teal: {TEAL};
        --muted: {MUTED};
        --border: {BORDER};
        --soft-bg: {SOFT_BG};
        --font: "Raleway", Arial, sans-serif;
    }}

    html,
    body {{
        margin: 0;
        padding: 0;
        overflow: hidden;
        background: #ffffff;
        scroll-behavior: auto;
        border: 0;
    }}

    body,
    body * {{
        box-sizing: border-box;
        font-family: var(--font);
    }}

    a {{
        color: inherit;
    }}

    .soapbox-report {{
        width: 100%;
        padding: 0;
        color: var(--navy);
        background: #ffffff;
        overflow: hidden;
        border: 0;
        caret-color: transparent;
        cursor: default;
        user-select: none;
    }}

    .soapbox-report a {{
        cursor: pointer;
    }}

    .report-shell {{
        width: 100%;
        max-width: 960px;
        margin: 0 auto;
        padding: 0;
        border: 0;
    }}

    .report-page {{
        width: 100%;
        padding: 18px 30px 18px;
        background: #ffffff;
        border: 0;
    }}

    .report-header {{
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 24px;
        margin-bottom: 17px;
    }}

    .report-heading {{
        flex: 1;
        min-width: 0;
    }}

    .brand-name {{
        margin: 0 0 4px;
        color: var(--teal);
        font-size: 31px;
        font-weight: 800;
        letter-spacing: 0;
        line-height: 1.03;
    }}

    .report-title {{
        margin: 0 0 6px;
        color: var(--navy);
        font-size: 32px;
        font-weight: 800;
        letter-spacing: 0;
        line-height: 1.04;
    }}

    .report-date {{
        color: var(--muted);
        font-size: 16px;
        font-weight: 700;
        line-height: 1.2;
    }}

    .report-updated {{
        margin-top: 3px;
        color: rgba(93, 114, 130, 0.72);
        font-size: 11.5px;
        font-weight: 500;
        line-height: 1.2;
    }}

    .logo-box {{
        display: flex;
        align-items: flex-start;
        justify-content: flex-end;
        min-width: 170px;
        padding-top: 0;
        background: transparent;
        border: 0;
        box-shadow: none;
    }}

    .logo-box img {{
        display: block;
        max-width: 170px;
        max-height: 88px;
        object-fit: contain;
        background: transparent;
        border: 0;
        box-shadow: none;
    }}

    .logo-fallback {{
        color: var(--navy);
        font-size: 30px;
        font-weight: 900;
        letter-spacing: 0;
        line-height: 0.84;
        text-align: right;
    }}

    .logo-fallback small {{
        display: block;
        margin-top: 7px;
        color: var(--teal);
        font-size: 8.5px;
        font-weight: 800;
        letter-spacing: 0;
        text-transform: uppercase;
    }}

    .kpi-grid {{
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 13px;
        width: 100%;
        max-width: 860px;
        margin: 0 auto 17px;
    }}

    .kpi-card {{
        position: relative;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        min-height: 126px;
        padding: 14px 12px 13px;
        border-radius: 23px;
        text-align: center;
        overflow: hidden;
        box-shadow: 0 5px 14px rgba(0, 44, 71, 0.035);
    }}

    .kpi-card::after {{
        content: "";
        position: absolute;
        inset: 0;
        background:
            radial-gradient(circle at 50% 18%, rgba(255, 255, 255, 0.52), transparent 34%),
            linear-gradient(150deg, rgba(255, 255, 255, 0.28), rgba(255, 255, 255, 0));
        pointer-events: none;
    }}

    .kpi-card > * {{
        position: relative;
        z-index: 1;
    }}

    .kpi-teal {{
        background: rgba(51, 178, 193, 0.085);
        border: 1.5px solid rgba(51, 178, 193, 0.60);
    }}

    .kpi-navy {{
        background: rgba(0, 44, 71, 0.06);
        border: 1.5px solid rgba(0, 44, 71, 0.66);
    }}

    .kpi-icon {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 43px;
        height: 43px;
        margin-bottom: 10px;
        border-radius: 999px;
    }}

    .kpi-icon svg {{
        width: 21px;
        height: 21px;
        display: block;
    }}

    .kpi-teal .kpi-icon {{
        color: var(--teal);
        background: rgba(51, 178, 193, 0.13);
        border: 1px solid rgba(51, 178, 193, 0.26);
    }}

    .kpi-navy .kpi-icon {{
        color: var(--navy);
        background: rgba(0, 44, 71, 0.075);
        border: 1px solid rgba(0, 44, 71, 0.18);
    }}

    .kpi-value {{
        margin: 0 0 6px;
        font-size: 33px;
        font-weight: 900;
        letter-spacing: 0;
        line-height: 0.95;
    }}

    .kpi-teal .kpi-value {{
        color: var(--teal);
    }}

    .kpi-navy .kpi-value {{
        color: var(--navy);
    }}

    .kpi-label {{
        color: rgba(0, 44, 71, 0.82);
        font-size: 12px;
        font-weight: 600;
        line-height: 1.18;
    }}

    .section-heading {{
        display: flex;
        align-items: center;
        gap: 14px;
        margin: 0 0 8px;
    }}

    .section-heading h2 {{
        flex: 0 0 auto;
        margin: 0;
        color: var(--navy);
        font-size: 22px;
        font-weight: 900;
        letter-spacing: 0;
        line-height: 1;
    }}

    .section-line {{
        flex: 1;
        height: 2px;
        min-width: 80px;
        background-image: linear-gradient(
            to right,
            rgba(51, 178, 193, 0.52) 35%,
            rgba(51, 178, 193, 0) 0%
        );
        background-position: center;
        background-repeat: repeat-x;
        background-size: 13px 2px;
    }}

    .content-list {{
        display: grid;
        gap: 8px;
    }}

    .content-card {{
        display: grid;
        grid-template-columns: 235px minmax(0, 1fr);
        height: 112px;
        min-height: 112px;
        max-height: 112px;
        overflow: hidden;
        border: 1px solid var(--border);
        border-radius: 19px;
        background: #ffffff;
        box-shadow: 0 8px 22px rgba(0, 44, 71, 0.045);
    }}

    .media-link {{
        display: block;
        width: 235px;
        height: 112px;
        min-height: 112px;
        max-height: 112px;
        overflow: hidden;
        color: inherit;
        text-decoration: none;
        background: #f3fafc;
    }}

    .media-link:focus-visible,
    .cta:focus-visible {{
        outline: 2px solid rgba(51, 178, 193, 0.6);
        outline-offset: 3px;
    }}

    .content-image {{
        display: block;
        width: 100%;
        height: 100%;
        min-height: 112px;
        max-height: 112px;
        object-fit: cover;
        object-position: center center;
        background: #e8f6f8;
    }}

    .placeholder {{
        position: relative;
        display: flex;
        align-items: center;
        justify-content: center;
        width: 100%;
        height: 112px;
        min-height: 112px;
        max-height: 112px;
        overflow: hidden;
        padding: 14px;
        background:
            radial-gradient(circle at 24% 20%, rgba(255, 255, 255, 0.95), transparent 24%),
            radial-gradient(circle at 78% 86%, rgba(51, 178, 193, 0.14), transparent 30%),
            linear-gradient(135deg, rgba(51, 178, 193, 0.10) 0%, rgba(247, 251, 253, 1) 100%);
        color: rgba(51, 178, 193, 0.78);
        font-size: 11px;
        font-weight: 800;
        letter-spacing: 0;
        text-align: center;
        text-transform: uppercase;
    }}

    .placeholder::before {{
        content: "";
        position: absolute;
        width: 30px;
        height: 30px;
        border-radius: 999px;
        background: rgba(51, 178, 193, 0.10);
        border: 1px solid rgba(51, 178, 193, 0.18);
        transform: translateY(-26px);
    }}

    .placeholder-fallback {{
        display: none;
    }}

    .content-body {{
        display: flex;
        flex-direction: column;
        justify-content: center;
        padding: 12px 17px;
    }}

    .content-meta {{
        display: flex;
        align-items: center;
        gap: 8px;
        flex-wrap: wrap;
        margin-bottom: 5px;
    }}

    .platform-pill {{
        display: inline-flex;
        width: fit-content;
        padding: 4px 8px;
        border: 1px solid rgba(51, 178, 193, 0.26);
        border-radius: 999px;
        background: rgba(51, 178, 193, 0.10);
        color: #178C95;
        font-size: 9.5px;
        font-weight: 700;
        letter-spacing: 0;
        line-height: 1;
        text-transform: uppercase;
    }}

    .content-handle {{
        color: var(--muted);
        font-size: 11px;
        font-weight: 600;
        line-height: 1.2;
    }}

    .content-title {{
        margin: 0 0 4px;
        color: var(--navy);
        font-size: 16px;
        font-weight: 900;
        letter-spacing: 0;
        line-height: 1.12;
    }}

    .content-copy {{
        margin: 0 0 7px;
        color: var(--muted);
        font-size: 11.5px;
        font-weight: 500;
        line-height: 1.28;
    }}

    .content-actions {{
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
    }}

    .cta {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 8px;
        width: fit-content;
        padding: 6.5px 12px;
        border-radius: 999px;
        background: var(--teal);
        color: #ffffff !important;
        font-size: 11.5px;
        font-weight: 800;
        line-height: 1;
        text-decoration: none;
        box-shadow: 0 4px 10px rgba(51, 178, 193, 0.15);
    }}

    .cta::after {{
        content: "\\2197";
        font-size: 12px;
        line-height: 1;
    }}

    .cta-disabled {{
        background: #D7E3E6;
        color: #697B88 !important;
        box-shadow: none;
    }}

    .cta-disabled::after {{
        content: "";
    }}

    .content-url-note {{
        color: rgba(93, 114, 130, 0.8);
        font-size: 12px;
        font-weight: 600;
        line-height: 1.3;
    }}

    .empty-content {{
        padding: 34px 28px;
        border: 1.5px dashed rgba(51, 178, 193, 0.34);
        border-radius: 22px;
        background: rgba(51, 178, 193, 0.05);
        color: var(--muted);
        text-align: center;
    }}

    .empty-content-title {{
        margin: 0 0 8px;
        color: var(--navy);
        font-size: 18px;
        font-weight: 800;
    }}

    .empty-content-copy {{
        margin: 0;
        font-size: 14px;
        font-weight: 600;
        line-height: 1.5;
    }}

    .report-footer {{
        margin-top: 12px;
        padding-bottom: 0;
        color: rgba(0, 44, 71, 0.72);
        font-size: 11.5px;
        font-weight: 600;
        text-align: center;
    }}

    @media (max-width: 920px) {{
        .report-page {{
            padding: 18px 18px 20px;
        }}

        .report-header {{
            flex-direction: column;
            gap: 18px;
        }}

        .logo-box {{
            justify-content: flex-start;
        }}

        .kpi-grid {{
            max-width: 100%;
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }}

        .content-card {{
            grid-template-columns: 1fr;
            height: auto;
            max-height: none;
        }}

        .media-link,
        .content-image,
        .placeholder {{
            width: 100%;
            height: 150px;
            min-height: 150px;
            max-height: 150px;
        }}
    }}

    @media (max-width: 560px) {{
        .report-page {{
            padding: 24px 18px 30px;
        }}

        .brand-name {{
            font-size: 25px;
        }}

        .report-title {{
            font-size: 28px;
        }}

        .report-date {{
            font-size: 14px;
        }}

        .report-updated {{
            font-size: 11px;
        }}

        .kpi-grid {{
            grid-template-columns: 1fr;
        }}

        .section-heading {{
            align-items: flex-start;
            flex-direction: column;
            gap: 10px;
        }}

        .section-line {{
            width: 100%;
        }}

        .content-body {{
            padding: 14px 14px;
        }}
    }}
    </style>
    """


def build_report_html(report: dict) -> str:
    """Build the report HTML."""
    client_name = escape(report.get("client_name") or "Client")
    report_date = format_date(report.get("report_date") or "")
    updated_date = format_updated_date(report.get("updated_at") or "")
    updated_html = (
        f'<div class="report-updated">Last updated {escape(updated_date)}</div>'
        if updated_date
        else ""
    )
    logo_html = build_logo_html()
    kpi_html = build_kpi_grid(report)
    content_html = build_content_list(report.get("content_items") or [])

    return f"""
    <div class="soapbox-report">
        <div class="report-shell">
            <main class="report-page" aria-label="Weekly Campaign Metrics Report">
                <header class="report-header">
                    <div class="report-heading">
                        <p class="brand-name">{client_name}</p>
                        <h1 class="report-title">Weekly Campaign Metrics</h1>
                        <div class="report-date">{escape(report_date)}</div>
                        {updated_html}
                    </div>
                    <div class="logo-box">
                        {logo_html}
                    </div>
                </header>

                {kpi_html}

                <section class="section-heading" aria-label="Featured Live Content">
                    <h2>Featured Live Content</h2>
                    <div class="section-line" aria-hidden="true"></div>
                </section>

                {content_html}

                <footer class="report-footer">Generated by Soapbox Retail</footer>
            </main>
        </div>
    </div>
    """


def build_kpi_grid(report: dict) -> str:
    """Build the KPI cards."""
    kpis = [
        ("Organic Impressions", report.get("organic_impressions", 0), "teal", icon_eye()),
        ("Paid Impressions", report.get("paid_impressions", 0), "navy", icon_megaphone()),
        ("Organic Engagements", report.get("organic_engagements", 0), "teal", icon_heart()),
        ("Paid Engagements", report.get("paid_engagements", 0), "navy", icon_chat()),
    ]

    cards = []
    for label, value, accent, icon in kpis:
        cards.append(
            f"""
            <article class="kpi-card kpi-{escape(accent)}">
                <div class="kpi-icon" aria-hidden="true">{icon}</div>
                <div class="kpi-value">{format_number(value)}</div>
                <div class="kpi-label">{escape(label)}</div>
            </article>
            """
        )

    return f"""
    <section class="kpi-grid" aria-label="Campaign KPI metrics">
        {''.join(cards)}
    </section>
    """


def build_content_list(content_items: list[dict]) -> str:
    """Build featured content cards."""
    cleaned_items = [item for item in content_items if clean_text(item.get("live_url"))]

    if not cleaned_items:
        return """
        <section class="content-list">
            <div class="empty-content">
                <p class="empty-content-title">Featured content will appear here.</p>
                <p class="empty-content-copy">
                    Add live post links and images in edit mode to populate the campaign highlights.
                </p>
            </div>
        </section>
        """

    cards = "".join(
        build_content_card(item=item, index=index)
        for index, item in enumerate(cleaned_items, start=1)
    )

    return f"""
    <section class="content-list" aria-label="Featured live content cards">
        {cards}
    </section>
    """


def build_content_card(item: dict, index: int) -> str:
    """Build a single content card."""
    live_url = ensure_normalized_url(clean_text(item.get("live_url")))
    platform = normalize_platform(clean_text(item.get("platform")) or infer_platform(live_url) or "Live Content")
    creator_handle = clean_text(item.get("creator_handle"))
    title = clean_text(item.get("content_title")) or default_content_title(platform)
    description = clean_text(item.get("content_description")) or default_content_description(platform)

    image_ref = (
        item.get("image_path")
        or item.get("image_url")
        or item.get("uploaded_image_path")
        or ""
    )

    image_html = build_image_html(
        image_ref=image_ref,
        live_url=live_url,
        platform=platform,
        index=index,
    )

    handle_html = (
        f'<span class="content-handle">{escape(creator_handle)}</span>'
        if creator_handle
        else ""
    )

    if is_valid_url(live_url):
        cta_html = (
            f'<a class="cta" href="{escape(live_url)}" target="_blank" '
            f'rel="noopener noreferrer" aria-label="Open live {escape(platform)} post">'
            "View Live Post</a>"
        )
        note_html = ""
    else:
        cta_html = '<span class="cta cta-disabled" aria-disabled="true">View Live Post</span>'
        note_html = '<span class="content-url-note">No live URL available</span>'

    return f"""
    <article class="content-card">
        {image_html}
        <div class="content-body">
            <div class="content-meta">
                <span class="platform-pill">{escape(platform)}</span>
                {handle_html}
            </div>
            <h3 class="content-title">{escape(title)}</h3>
            <p class="content-copy">{escape(description)}</p>
            <div class="content-actions">
                {cta_html}
                {note_html}
            </div>
        </div>
    </article>
    """


def build_image_html(image_ref: str | None, live_url: str, platform: str, index: int) -> str:
    """Build the clickable media area."""
    image_src = resolve_image_src(image_ref)
    alt_text = f"{platform} live content preview {index}"

    if image_src:
        fallback_html = (
            f'<div class="placeholder placeholder-fallback" role="img" '
            f'aria-label="{escape(alt_text)}">{escape(platform)} Preview</div>'
        )
        media_html = (
            f'<img class="content-image" src="{escape(image_src)}" '
            f'alt="{escape(alt_text)}" loading="lazy" '
            "onerror=\"this.style.display='none'; "
            "var fallback=this.parentElement.querySelector('.placeholder-fallback'); "
            "if (fallback) { fallback.style.display='flex'; }\" />"
            f"{fallback_html}"
        )
    else:
        media_html = (
            f'<div class="placeholder" role="img" aria-label="{escape(alt_text)}">'
            f"{escape(platform)} Preview</div>"
        )

    if not is_valid_url(live_url):
        return f'<div class="media-link">{media_html}</div>'

    return (
        f'<a class="media-link" href="{escape(live_url)}" target="_blank" '
        f'rel="noopener noreferrer" aria-label="Open live {escape(platform)} post">'
        f"{media_html}</a>"
    )


def resolve_image_src(image_ref: str | None) -> str:
    """Resolve a browser-safe image source."""
    value = clean_text(image_ref)
    if not value:
        return ""

    if value.startswith("data:image/"):
        return value

    if is_valid_url(value):
        return ensure_normalized_url(value)

    path = Path(value)
    if not path.is_absolute():
        root_dir = Path(__file__).resolve().parents[1]
        path = root_dir / value

    if not path.exists() or not path.is_file():
        return ""

    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def build_logo_html() -> str:
    """Build the Soapbox logo image or fallback."""
    logo_path = find_logo_path()

    if not logo_path:
        return """
        <div class="logo-fallback">
            SOAP<br />BOX
            <small>Influence + Retail Media</small>
        </div>
        """

    mime_type = mimetypes.guess_type(logo_path.name)[0] or "image/png"
    encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    return f'<img src="data:{mime_type};base64,{encoded}" alt="Soapbox Retail logo" />'


def find_logo_path() -> Path | None:
    """Find a logo asset, preferring transparent versions."""
    root_dir = Path(__file__).resolve().parents[1]
    candidates = [
        root_dir / "assets" / "logo-transparent.png",
        root_dir / "assets" / "logo_transparent.png",
        root_dir / "assets" / "soapbox_logo_transparent.png",
        root_dir / "assets" / "soapbox-logo-transparent.png",
        root_dir / "assets" / "logo.png",
        root_dir / "assets" / "logo.jpg",
        root_dir / "assets" / "logo.jpeg",
        root_dir / "assets" / "soapbox_logo.png",
        root_dir / "assets" / "soapbox-logo.png",
        root_dir / "app" / "assets" / "logo-transparent.png",
        root_dir / "app" / "assets" / "logo_transparent.png",
        root_dir / "app" / "assets" / "soapbox_logo_transparent.png",
        root_dir / "app" / "assets" / "soapbox-logo-transparent.png",
        root_dir / "app" / "assets" / "logo.png",
        root_dir / "app" / "assets" / "logo.jpg",
        root_dir / "app" / "assets" / "soapbox_logo.png",
        root_dir / "app" / "assets" / "soapbox-logo.png",
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate

    return None


def normalize_platform(platform: str) -> str:
    """Normalize platform display text."""
    value = clean_text(platform).lower()
    mapping = {
        "instagram": "Instagram",
        "ig": "Instagram",
        "tiktok": "TikTok",
        "tik tok": "TikTok",
        "facebook": "Facebook",
        "fb": "Facebook",
        "youtube": "YouTube",
        "yt": "YouTube",
    }
    return mapping.get(value, clean_text(platform) or "Live Content")


def default_content_title(platform: str) -> str:
    """Build a sensible fallback content title."""
    platform_name = normalize_platform(platform)
    mapping = {
        "Instagram": "Featured Instagram Content",
        "TikTok": "Featured TikTok Content",
        "Facebook": "Featured Facebook Content",
        "YouTube": "Featured YouTube Content",
    }
    return mapping.get(platform_name, f"{platform_name} Campaign Content")


def default_content_description(platform: str) -> str:
    """Build a sensible fallback description."""
    platform_name = normalize_platform(platform)
    mapping = {
        "Instagram": "Live campaign content currently featured on Instagram.",
        "TikTok": "Live campaign content currently featured on TikTok.",
        "Facebook": "Live campaign content currently featured on Facebook.",
        "YouTube": "Live campaign content currently featured on YouTube.",
    }
    return mapping.get(platform_name, "Tap through to view the live campaign content.")


def icon_eye() -> str:
    return """
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M2.8 12s3.4-5.7 9.2-5.7 9.2 5.7 9.2 5.7-3.4 5.7-9.2 5.7S2.8 12 2.8 12Z"
              stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>
        <circle cx="12" cy="12" r="2.8" stroke="currentColor" stroke-width="1.9"/>
    </svg>
    """


def icon_megaphone() -> str:
    return """
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M4.4 10.4h3.3l8.2-4v11.2l-8.2-4H4.4a1.4 1.4 0 0 1-1.4-1.4v-.4a1.4 1.4 0 0 1 1.4-1.4Z"
              stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M8 13.6 9.4 18a1.2 1.2 0 0 0 1.2.8h1.2l-1.6-5.2"
              stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M18.4 9.2c.9.7 1.4 1.65 1.4 2.8s-.5 2.1-1.4 2.8"
              stroke="currentColor" stroke-width="1.9" stroke-linecap="round"/>
    </svg>
    """


def icon_heart() -> str:
    return """
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M12 20s-7.3-4.35-8.65-9.05C2.45 7.8 4.35 5.2 7.25 5.2c1.95 0 3.45 1.1 4.2 2.45.75-1.35 2.25-2.45 4.2-2.45 2.9 0 4.8 2.6 3.9 5.75C18.2 15.65 12 20 12 20Z"
              stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"/>
    </svg>
    """


def icon_chat() -> str:
    return """
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M5.4 5.4h13.2a2 2 0 0 1 2 2v6.8a2 2 0 0 1-2 2H9.5L5.2 19v-2.8a2 2 0 0 1-1.8-2V7.4a2 2 0 0 1 2-2Z"
              fill="currentColor"/>
        <circle cx="9.1" cy="10.9" r="1" fill="#FFFFFF"/>
        <circle cx="12" cy="10.9" r="1" fill="#FFFFFF"/>
        <circle cx="14.9" cy="10.9" r="1" fill="#FFFFFF"/>
    </svg>
    """


def infer_platform(live_url: str) -> str:
    """Infer platform from a live URL."""
    if not live_url:
        return ""

    normalized = ensure_normalized_url(live_url)
    domain = urlparse(normalized).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]

    if "instagram.com" in domain:
        return "Instagram"
    if "tiktok.com" in domain:
        return "TikTok"
    if "facebook.com" in domain or "fb.watch" in domain:
        return "Facebook"
    if "youtube.com" in domain or "youtu.be" in domain:
        return "YouTube"

    return ""


def ensure_normalized_url(value: str) -> str:
    """Ensure a URL is normalized with https:// scheme if it looks like a domain."""
    value = clean_text(value)
    if not value:
        return ""

    if value.startswith(("http://", "https://")):
        return value

    parsed = urlparse(f"https://{value}")
    if "." in parsed.netloc:
        return f"https://{value}"

    return value


def is_valid_url(value: str) -> bool:
    """Check whether a value is a valid HTTP(S) URL."""
    normalized = ensure_normalized_url(value)
    parsed = urlparse(normalized)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def clean_text(value: object) -> str:
    """Normalize text input."""
    return str(value or "").strip()


def escape(value: object) -> str:
    """Escape text for HTML."""
    return html.escape(str(value or ""), quote=True)


def format_number(value: object) -> str:
    """Format metric values."""
    try:
        return f"{int(float(value or 0)):,}"
    except (TypeError, ValueError):
        return "0"


def format_date(value: object) -> str:
    """Format ISO dates into m/d/yyyy."""
    raw = clean_text(value)

    if not raw:
        return ""

    try:
        year, month, day = raw.split("-")
        return f"{int(month)}/{int(day)}/{year}"
    except ValueError:
        return raw


def format_updated_date(value: object) -> str:
    """Format an existing ISO timestamp into m/d/yyyy."""
    raw = clean_text(value)
    if not raw:
        return ""

    date_part = raw.split("T", 1)[0].split(" ", 1)[0]
    return format_date(date_part)
