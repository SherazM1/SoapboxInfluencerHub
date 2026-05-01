# core/reporting_template.py
from __future__ import annotations

import base64
import html
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st


NAVY = "#002C47"
TEAL = "#33B2C1"
MUTED = "#5D7282"
BORDER = "#DCEAF1"
SOFT_BG = "#F7FBFD"


def render_client_report(report: dict) -> None:
    """Render the client-facing campaign report directly in Streamlit."""
    st.markdown(
        f"""
        <style>
        header,
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stSidebar"],
        [data-testid="stSidebarNav"] {{
            display: none !important;
        }}

        .stApp {{
            background: #ffffff !important;
        }}

        .block-container {{
            max-width: 1140px !important;
            padding: 18px 24px 40px !important;
        }}
        </style>
        {build_font_faces()}
        {build_css()}
        """,
        unsafe_allow_html=True,
    )
    st.markdown(build_report_html(report), unsafe_allow_html=True)


def build_font_faces() -> str:
    """Embed local Raleway assets when present."""
    regular = encode_font_asset("Raleway-Regular.ttf")
    bold = encode_font_asset("Raleway-Bold.ttf")

    rules = ["<style>"]

    if regular:
        rules.append(
            f"""
            @font-face {{
                font-family: "RalewayLocal";
                src: url("data:font/ttf;base64,{regular}") format("truetype");
                font-weight: 400 600;
                font-style: normal;
                font-display: swap;
            }}
            """
        )

    if bold:
        rules.append(
            f"""
            @font-face {{
                font-family: "RalewayLocal";
                src: url("data:font/ttf;base64,{bold}") format("truetype");
                font-weight: 700 900;
                font-style: normal;
                font-display: swap;
            }}
            """
        )

    rules.append("</style>")
    return "\n".join(rules)


def encode_font_asset(filename: str) -> str:
    """Return a base64 encoded font asset if available."""
    root_dir = Path(__file__).resolve().parents[1]
    candidates = [
        root_dir / "assets" / filename,
        root_dir / "app" / "assets" / filename,
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return base64.b64encode(candidate.read_bytes()).decode("ascii")

    return ""


def build_css() -> str:
    """Build the client report CSS."""
    return f"""
    <style>
    :root {{
        --navy: {NAVY};
        --teal: {TEAL};
        --muted: {MUTED};
        --border: {BORDER};
        --soft-bg: {SOFT_BG};
        --font: "RalewayLocal", "Raleway", Arial, sans-serif;
    }}

    .soapbox-report,
    .soapbox-report * {{
        box-sizing: border-box;
        font-family: var(--font);
    }}

    .soapbox-report {{
        width: 100%;
        color: var(--navy);
    }}

    .report-shell {{
        max-width: 1040px;
        margin: 0 auto;
        padding: 0;
    }}

    .report-page {{
        position: relative;
        width: 100%;
        padding: 36px 42px 30px;
        border: 1px solid rgba(0, 44, 71, 0.08);
        border-radius: 28px;
        background:
            radial-gradient(circle at top right, rgba(51, 178, 193, 0.06), transparent 24%),
            linear-gradient(180deg, #ffffff 0%, #fcfeff 100%);
        box-shadow: 0 18px 45px rgba(0, 44, 71, 0.045);
        overflow: hidden;
    }}

    .report-page::before {{
        content: "";
        position: absolute;
        inset: 0 auto auto 0;
        width: 100%;
        height: 6px;
        background: linear-gradient(90deg, rgba(51, 178, 193, 0.16), rgba(0, 44, 71, 0.04));
        opacity: 0.55;
    }}

    .report-header {{
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 28px;
        margin-bottom: 28px;
    }}

    .report-heading {{
        flex: 1;
        min-width: 0;
    }}

    .brand-name {{
        margin: 0 0 4px;
        color: var(--teal);
        font-size: 28px;
        font-weight: 800;
        line-height: 1.05;
    }}

    .report-title {{
        margin: 0 0 10px;
        color: var(--navy);
        font-size: 31px;
        font-weight: 800;
        letter-spacing: -0.9px;
        line-height: 1.04;
    }}

    .report-date {{
        color: var(--muted);
        font-size: 15px;
        font-weight: 700;
        line-height: 1.2;
    }}

    .logo-box {{
        display: flex;
        align-items: flex-start;
        justify-content: flex-end;
        min-width: 170px;
        padding-top: 2px;
        background: transparent;
        border: 0;
        box-shadow: none;
    }}

    .logo-box img {{
        display: block;
        max-width: 150px;
        max-height: 76px;
        object-fit: contain;
        background: transparent;
        border: 0;
        box-shadow: none;
    }}

    .logo-fallback {{
        color: var(--navy);
        font-size: 30px;
        font-weight: 900;
        letter-spacing: -1.2px;
        line-height: 0.84;
        text-align: right;
    }}

    .logo-fallback small {{
        display: block;
        margin-top: 7px;
        color: var(--teal);
        font-size: 8.5px;
        font-weight: 800;
        letter-spacing: 1.2px;
        text-transform: uppercase;
    }}

    .kpi-grid {{
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 14px;
        max-width: 840px;
        margin: 0 0 30px;
    }}

    .kpi-card {{
        position: relative;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        min-height: 150px;
        padding: 16px 14px 15px;
        border-radius: 18px;
        text-align: center;
        overflow: hidden;
    }}

    .kpi-card::after {{
        content: "";
        position: absolute;
        inset: 0;
        background: linear-gradient(160deg, rgba(255, 255, 255, 0.32), rgba(255, 255, 255, 0));
        pointer-events: none;
    }}

    .kpi-card > * {{
        position: relative;
        z-index: 1;
    }}

    .kpi-teal {{
        background: rgba(51, 178, 193, 0.08);
        border: 1.4px solid rgba(51, 178, 193, 0.42);
    }}

    .kpi-navy {{
        background: rgba(0, 44, 71, 0.045);
        border: 1.4px solid rgba(0, 44, 71, 0.32);
    }}

    .kpi-icon {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 46px;
        height: 46px;
        margin-bottom: 14px;
        border-radius: 999px;
    }}

    .kpi-icon svg {{
        width: 22px;
        height: 22px;
        display: block;
    }}

    .kpi-teal .kpi-icon {{
        color: var(--teal);
        background: rgba(51, 178, 193, 0.12);
        border: 1px solid rgba(51, 178, 193, 0.24);
    }}

    .kpi-navy .kpi-icon {{
        color: var(--navy);
        background: rgba(0, 44, 71, 0.06);
        border: 1px solid rgba(0, 44, 71, 0.12);
    }}

    .kpi-value {{
        margin: 0 0 8px;
        font-size: 31px;
        font-weight: 900;
        letter-spacing: -0.8px;
        line-height: 0.95;
    }}

    .kpi-teal .kpi-value {{
        color: var(--teal);
    }}

    .kpi-navy .kpi-value {{
        color: var(--navy);
    }}

    .kpi-label {{
        color: rgba(0, 44, 71, 0.78);
        font-size: 11.5px;
        font-weight: 700;
        line-height: 1.25;
    }}

    .section-heading {{
        display: flex;
        align-items: center;
        gap: 18px;
        margin: 0 0 16px;
    }}

    .section-heading h2 {{
        flex: 0 0 auto;
        margin: 0;
        color: var(--navy);
        font-size: 28px;
        font-weight: 900;
        letter-spacing: -0.55px;
        line-height: 1;
    }}

    .section-line {{
        flex: 1;
        height: 2px;
        min-width: 80px;
        background-image: linear-gradient(
            to right,
            rgba(51, 178, 193, 0.55) 38%,
            rgba(51, 178, 193, 0) 0%
        );
        background-position: center;
        background-repeat: repeat-x;
        background-size: 13px 2px;
    }}

    .content-list {{
        display: grid;
        gap: 16px;
    }}

    .content-card {{
        display: grid;
        grid-template-columns: 285px minmax(0, 1fr);
        min-height: 188px;
        overflow: hidden;
        border: 1px solid var(--border);
        border-radius: 24px;
        background: #ffffff;
        box-shadow: 0 10px 28px rgba(0, 44, 71, 0.05);
    }}

    .media-link {{
        display: block;
        min-height: 188px;
        color: inherit;
        text-decoration: none !important;
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
        min-height: 188px;
        object-fit: cover;
        background: #e8f6f8;
    }}

    .placeholder {{
        display: flex;
        align-items: center;
        justify-content: center;
        width: 100%;
        min-height: 188px;
        padding: 18px;
        background:
            radial-gradient(circle at 22% 20%, rgba(255, 255, 255, 0.95), transparent 28%),
            linear-gradient(135deg, rgba(51, 178, 193, 0.14) 0%, #f8fcfd 100%);
        color: var(--teal);
        font-size: 16px;
        font-weight: 900;
        letter-spacing: 1.1px;
        text-align: center;
        text-transform: uppercase;
    }}

    .content-body {{
        display: flex;
        flex-direction: column;
        justify-content: center;
        padding: 22px 24px 22px;
    }}

    .content-meta {{
        display: flex;
        align-items: center;
        gap: 10px;
        flex-wrap: wrap;
        margin-bottom: 12px;
    }}

    .platform-pill {{
        display: inline-flex;
        align-items: center;
        gap: 7px;
        width: fit-content;
        padding: 7px 12px;
        border-radius: 999px;
        border: 1px solid rgba(51, 178, 193, 0.22);
        font-size: 11.5px;
        font-weight: 900;
        letter-spacing: 0.8px;
        line-height: 1;
        text-transform: uppercase;
    }}

    .platform-pill::before {{
        content: "";
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: currentColor;
        opacity: 0.85;
    }}

    .platform-instagram {{
        color: #C045A0;
        background: rgba(192, 69, 160, 0.08);
        border-color: rgba(192, 69, 160, 0.18);
    }}

    .platform-tiktok {{
        color: #0B6E7D;
        background: rgba(11, 110, 125, 0.08);
        border-color: rgba(11, 110, 125, 0.18);
    }}

    .platform-facebook {{
        color: #2C6DD8;
        background: rgba(44, 109, 216, 0.08);
        border-color: rgba(44, 109, 216, 0.18);
    }}

    .platform-youtube {{
        color: #D33030;
        background: rgba(211, 48, 48, 0.08);
        border-color: rgba(211, 48, 48, 0.18);
    }}

    .platform-default {{
        color: #178C95;
        background: rgba(51, 178, 193, 0.09);
        border-color: rgba(51, 178, 193, 0.18);
    }}

    .content-handle {{
        color: var(--muted);
        font-size: 13px;
        font-weight: 700;
        line-height: 1.2;
    }}

    .content-title {{
        margin: 0 0 8px;
        color: var(--navy);
        font-size: 19px;
        font-weight: 900;
        letter-spacing: -0.25px;
        line-height: 1.18;
    }}

    .content-copy {{
        margin: 0 0 16px;
        color: var(--muted);
        font-size: 14px;
        font-weight: 600;
        line-height: 1.5;
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
        padding: 10px 16px;
        border-radius: 999px;
        background: var(--teal);
        color: #ffffff !important;
        font-size: 13px;
        font-weight: 900;
        line-height: 1;
        text-decoration: none !important;
        box-shadow: 0 8px 18px rgba(51, 178, 193, 0.2);
    }}

    .cta::after {{
        content: "↗";
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
        font-weight: 700;
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
        margin: 0 0 6px;
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
        margin-top: 24px;
        color: #000000;
        font-size: 14px;
        font-weight: 800;
        text-align: center;
    }}

    @media (max-width: 920px) {{
        .report-page {{
            padding: 28px 24px 24px;
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
        }}

        .media-link,
        .content-image,
        .placeholder {{
            min-height: 230px;
        }}
    }}

    @media (max-width: 560px) {{
        .report-page {{
            border-radius: 22px;
            padding: 24px 18px 22px;
        }}

        .brand-name {{
            font-size: 24px;
        }}

        .report-title {{
            font-size: 27px;
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
            padding: 20px 18px 20px;
        }}
    }}
    </style>
    """


def build_report_html(report: dict) -> str:
    """Build the report HTML."""
    client_name = escape(report.get("client_name") or "Client")
    report_date = format_date(report.get("report_date") or "")
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
    live_url = clean_text(item.get("live_url"))
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

    platform_class = platform_class_name(platform)
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
                <span class="platform-pill {escape(platform_class)}">{escape(platform)}</span>
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
        media_html = (
            f'<img class="content-image" src="{escape(image_src)}" '
            f'alt="{escape(alt_text)}" loading="lazy" />'
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

    if is_valid_url(value) or value.startswith("data:image/"):
        return value

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


def platform_class_name(platform: str) -> str:
    """Return a CSS class name for platform pill styling."""
    value = normalize_platform(platform).lower()
    mapping = {
        "instagram": "platform-instagram",
        "tiktok": "platform-tiktok",
        "facebook": "platform-facebook",
        "youtube": "platform-youtube",
    }
    return mapping.get(value, "platform-default")


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
        <path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"
              stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"/>
        <circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.9"/>
    </svg>
    """


def icon_megaphone() -> str:
    return """
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M4.5 13.2h3.2l8.1 4.1V6.7l-8.1 4.1H4.5v2.4Z" fill="currentColor"/>
        <path d="M7.6 13.2 9.2 18.7h2.4L10 13.2"
              stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
        <path d="M18.1 9.2c.95.7 1.5 1.66 1.5 2.8 0 1.13-.55 2.1-1.5 2.8"
              stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
    </svg>
    """


def icon_heart() -> str:
    return """
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M12 20.1s-7.4-4.5-8.9-9.3c-1-3.3 1-5.9 4-5.9 1.9 0 3.4 1 4.2 2.4.8-1.4 2.3-2.4 4.2-2.4 3 0 5 2.6 4 5.9-1.5 4.8-8.9 9.3-8.9 9.3Z"
              stroke="currentColor" stroke-width="1.9" stroke-linejoin="round"/>
    </svg>
    """


def icon_chat() -> str:
    return """
    <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
        <path d="M5.2 5.4h13.6a1.9 1.9 0 0 1 1.9 1.9v7.1a1.9 1.9 0 0 1-1.9 1.9H9.4L5.2 19v-2.7a1.9 1.9 0 0 1-1.9-1.9V7.3a1.9 1.9 0 0 1 1.9-1.9Z"
              fill="currentColor"/>
        <circle cx="9.1" cy="10.9" r="1.1" fill="#FFFFFF"/>
        <circle cx="12" cy="10.9" r="1.1" fill="#FFFFFF"/>
        <circle cx="14.9" cy="10.9" r="1.1" fill="#FFFFFF"/>
    </svg>
    """


def infer_platform(live_url: str) -> str:
    """Infer platform from a live URL."""
    if not live_url:
        return ""

    domain = urlparse(live_url).netloc.lower()
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


def is_valid_url(value: str) -> bool:
    """Check whether a value is a valid HTTP(S) URL."""
    parsed = urlparse(clean_text(value))
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