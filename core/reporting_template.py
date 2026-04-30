# core/reporting_template.py
from __future__ import annotations

import base64
import html
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st


NAVY = "#10243d"
TEAL = "#27aeb7"
TEXT_MUTED = "#5f7185"
BORDER = "#dcecee"
SOFT_TEAL = "rgba(39, 174, 183, 0.105)"
SOFT_NAVY = "rgba(16, 36, 61, 0.060)"


def render_client_report(report: dict) -> None:
    """Render the client-facing campaign report."""
    inject_report_css()
    st.markdown(build_report_html(report), unsafe_allow_html=True)


def inject_report_css() -> None:
    """Inject report-specific CSS."""
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Raleway:wght@400;500;600;700;800;900&display=swap');

        .stApp {{
            background: #ffffff;
        }}

        header,
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stSidebar"],
        [data-testid="stSidebarNav"] {{
            display: none !important;
        }}

        .block-container {{
            max-width: 1120px !important;
            padding: 34px 36px 30px !important;
        }}

        .soapbox-report,
        .soapbox-report * {{
            box-sizing: border-box;
            font-family: 'Raleway', sans-serif;
        }}

        .soapbox-report {{
            width: 100%;
            color: {NAVY};
        }}

        .report-page {{
            width: 100%;
            max-width: 1040px;
            margin: 0 auto;
            padding: 30px 34px 28px;
            background:
                radial-gradient(circle at top right, rgba(39, 174, 183, 0.055), transparent 32%),
                linear-gradient(180deg, #ffffff 0%, #fbfefe 100%);
            border: 1px solid #e3f0f2;
            border-radius: 30px;
            box-shadow: 0 18px 58px rgba(16, 36, 61, 0.075);
        }}

        .report-header {{
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 28px;
            margin-bottom: 26px;
        }}

        .brand-name {{
            color: {TEAL};
            font-size: 21px;
            font-weight: 800;
            line-height: 1.1;
            margin: 0 0 7px;
        }}

        .report-title {{
            color: {NAVY};
            font-size: 46px;
            font-weight: 900;
            letter-spacing: -1.3px;
            line-height: 1.02;
            margin: 0 0 9px;
        }}

        .report-date {{
            color: {TEXT_MUTED};
            font-size: 16px;
            font-weight: 700;
        }}

        .logo-box {{
            display: flex;
            align-items: center;
            justify-content: center;
            min-width: 142px;
            max-width: 190px;
            padding-top: 2px;
        }}

        .logo-box img {{
            display: block;
            max-width: 176px;
            max-height: 82px;
            object-fit: contain;
        }}

        .logo-fallback {{
            color: {NAVY};
            font-size: 22px;
            font-weight: 900;
            line-height: 0.95;
            text-align: right;
            text-transform: uppercase;
        }}

        .logo-fallback span {{
            display: block;
            color: {TEAL};
            font-size: 10px;
            font-weight: 800;
            letter-spacing: 1.4px;
            line-height: 1.2;
            margin-top: 7px;
        }}

        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 15px;
            margin: 0 0 30px;
        }}

        .kpi-card {{
            position: relative;
            min-height: 134px;
            padding: 18px 17px 17px;
            border-radius: 22px;
            overflow: hidden;
        }}

        .kpi-card::after {{
            content: "";
            position: absolute;
            inset: 0;
            pointer-events: none;
            border-radius: inherit;
            background: linear-gradient(145deg, rgba(255,255,255,0.46), rgba(255,255,255,0));
        }}

        .kpi-teal {{
            background: {SOFT_TEAL};
            border: 1.5px solid rgba(39, 174, 183, 0.42);
        }}

        .kpi-navy {{
            background: {SOFT_NAVY};
            border: 1.5px solid rgba(16, 36, 61, 0.30);
        }}

        .kpi-icon {{
            position: relative;
            z-index: 1;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 36px;
            height: 36px;
            margin-bottom: 17px;
            border-radius: 999px;
            font-size: 17px;
            font-weight: 900;
        }}

        .kpi-teal .kpi-icon {{
            color: {TEAL};
            background: rgba(39, 174, 183, 0.13);
            border: 1px solid rgba(39, 174, 183, 0.20);
        }}

        .kpi-navy .kpi-icon {{
            color: {NAVY};
            background: rgba(16, 36, 61, 0.075);
            border: 1px solid rgba(16, 36, 61, 0.13);
        }}

        .kpi-value {{
            position: relative;
            z-index: 1;
            margin: 0 0 7px;
            font-size: 31px;
            font-weight: 900;
            line-height: 1;
            letter-spacing: -0.7px;
        }}

        .kpi-teal .kpi-value {{
            color: {TEAL};
        }}

        .kpi-navy .kpi-value {{
            color: {NAVY};
        }}

        .kpi-label {{
            position: relative;
            z-index: 1;
            color: #52667a;
            font-size: 13px;
            font-weight: 800;
            line-height: 1.25;
        }}

        .section-heading {{
            display: flex;
            align-items: center;
            gap: 18px;
            margin: 2px 0 18px;
        }}

        .section-heading h2 {{
            flex: 0 0 auto;
            color: {NAVY};
            font-size: 29px;
            font-weight: 900;
            letter-spacing: -0.55px;
            line-height: 1;
            margin: 0;
        }}

        .section-line {{
            flex: 1;
            height: 2px;
            min-width: 90px;
            background-image: linear-gradient(to right, rgba(39, 174, 183, 0.55) 35%, rgba(39, 174, 183, 0) 0%);
            background-position: center;
            background-repeat: repeat-x;
            background-size: 12px 2px;
        }}

        .content-list {{
            display: grid;
            gap: 16px;
        }}

        .content-card {{
            display: grid;
            grid-template-columns: 285px minmax(0, 1fr);
            min-height: 178px;
            overflow: hidden;
            background: #ffffff;
            border: 1px solid {BORDER};
            border-radius: 23px;
            box-shadow: 0 12px 32px rgba(16, 36, 61, 0.055);
        }}

        .content-media-link {{
            display: block;
            min-height: 178px;
            color: inherit !important;
            text-decoration: none !important;
        }}

        .content-image {{
            display: block;
            width: 100%;
            height: 100%;
            min-height: 178px;
            object-fit: cover;
            background: #eaf8f9;
        }}

        .content-placeholder {{
            display: flex;
            align-items: center;
            justify-content: center;
            width: 100%;
            height: 100%;
            min-height: 178px;
            background:
                radial-gradient(circle at 20% 18%, rgba(255,255,255,0.9), transparent 30%),
                linear-gradient(135deg, #dff7f8 0%, #f7fcfd 100%);
            color: {TEAL};
            font-size: 15px;
            font-weight: 900;
            letter-spacing: 1.2px;
            text-transform: uppercase;
        }}

        .content-body {{
            display: flex;
            flex-direction: column;
            justify-content: center;
            padding: 21px 24px 20px;
        }}

        .content-topline {{
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            gap: 10px;
            margin-bottom: 13px;
        }}

        .platform-pill {{
            display: inline-flex;
            align-items: center;
            width: fit-content;
            max-width: 100%;
            padding: 7px 11px;
            border-radius: 999px;
            background: rgba(39, 174, 183, 0.105);
            border: 1px solid rgba(39, 174, 183, 0.22);
            color: #178c95;
            font-size: 12px;
            font-weight: 900;
            line-height: 1;
            letter-spacing: 0.7px;
            text-transform: uppercase;
        }}

        .content-title {{
            color: {NAVY};
            font-size: 22px;
            font-weight: 900;
            letter-spacing: -0.3px;
            line-height: 1.16;
            margin: 0 0 9px;
        }}

        .content-copy {{
            color: {TEXT_MUTED};
            font-size: 14.5px;
            font-weight: 600;
            line-height: 1.42;
            margin: 0 0 16px;
        }}

        .cta {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: fit-content;
            padding: 10px 16px;
            border-radius: 999px;
            background: {TEAL};
            color: #ffffff !important;
            font-size: 13px;
            font-weight: 900;
            line-height: 1;
            text-decoration: none !important;
            box-shadow: 0 8px 18px rgba(39, 174, 183, 0.22);
        }}

        .cta-disabled {{
            background: #d7e3e6;
            box-shadow: none;
            color: #697b88 !important;
        }}

        .empty-content {{
            padding: 30px;
            border: 1.5px dashed #b7dfe4;
            border-radius: 22px;
            background: rgba(39, 174, 183, 0.055);
            color: {TEXT_MUTED};
            font-size: 15px;
            font-weight: 700;
            text-align: center;
        }}

        .report-footer {{
            margin-top: 24px;
            padding-top: 6px;
            color: #000000;
            font-size: 14px;
            font-weight: 800;
            text-align: center;
        }}

        @media (max-width: 900px) {{
            .block-container {{
                padding: 18px !important;
            }}

            .report-page {{
                padding: 24px;
                border-radius: 24px;
            }}

            .report-header {{
                flex-direction: column;
            }}

            .report-title {{
                font-size: 36px;
            }}

            .kpi-grid {{
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }}

            .content-card {{
                grid-template-columns: 1fr;
            }}

            .content-media-link,
            .content-image,
            .content-placeholder {{
                min-height: 240px;
            }}
        }}

        @media (max-width: 560px) {{
            .report-page {{
                padding: 20px;
            }}

            .report-title {{
                font-size: 31px;
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
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def build_report_html(report: dict) -> str:
    """Build the complete report HTML."""
    client_name = escape(report.get("client_name") or "Client")
    report_date = escape(report.get("report_date") or "")
    logo_html = build_logo_html()

    kpi_html = build_kpi_grid(report)
    content_html = build_content_list(report.get("content_items") or [])

    return f"""
    <div class="soapbox-report">
        <main class="report-page" aria-label="Weekly Campaign Metrics Report">
            <header class="report-header">
                <div>
                    <p class="brand-name">{client_name}</p>
                    <h1 class="report-title">Weekly Campaign Metrics</h1>
                    <div class="report-date">{report_date}</div>
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
    """


def build_kpi_grid(report: dict) -> str:
    """Build KPI cards."""
    kpis = [
        {
            "label": "Organic Impressions",
            "value": report.get("organic_impressions", 0),
            "accent": "teal",
            "icon": "◉",
        },
        {
            "label": "Paid Impressions",
            "value": report.get("paid_impressions", 0),
            "accent": "navy",
            "icon": "↗",
        },
        {
            "label": "Organic Engagements",
            "value": report.get("organic_engagements", 0),
            "accent": "teal",
            "icon": "♡",
        },
        {
            "label": "Paid Engagements",
            "value": report.get("paid_engagements", 0),
            "accent": "navy",
            "icon": "…",
        },
    ]

    cards = []
    for kpi in kpis:
        cards.append(
            f"""
            <article class="kpi-card kpi-{escape(kpi["accent"])}">
                <div class="kpi-icon" aria-hidden="true">{escape(kpi["icon"])}</div>
                <div class="kpi-value">{format_number(kpi["value"])}</div>
                <div class="kpi-label">{escape(kpi["label"])}</div>
            </article>
            """
        )

    return f'<section class="kpi-grid" aria-label="Campaign metrics">{"".join(cards)}</section>'


def build_content_list(content_items: list[dict]) -> str:
    """Build content-card list."""
    if not content_items:
        return """
        <section class="content-list">
            <div class="empty-content">
                Featured content will appear here once live posts are added.
            </div>
        </section>
        """

    cards = "".join(build_content_card(item, index) for index, item in enumerate(content_items, start=1))
    return f'<section class="content-list" aria-label="Featured content cards">{cards}</section>'


def build_content_card(item: dict, index: int = 1) -> str:
    """Build one featured content card."""
    live_url = clean_text(item.get("live_url"))
    platform = clean_text(item.get("platform")) or infer_platform(live_url) or "Live Content"
    image_ref = item.get("image_path") or item.get("image_url") or item.get("uploaded_image_path")
    image_html = build_image_html(image_ref=image_ref, live_url=live_url, platform=platform, index=index)

    platform_label = escape(platform)
    content_title = f"{platform_label} Campaign Content"
    content_copy = "Tap through to view the live campaign content."

    if is_valid_url(live_url):
        cta = (
            f'<a class="cta" href="{escape(live_url)}" target="_blank" '
            f'rel="noopener noreferrer" aria-label="Open live {platform_label} post">'
            "View Live Post</a>"
        )
    else:
        cta = '<span class="cta cta-disabled" aria-disabled="true">View Live Post</span>'

    return f"""
    <article class="content-card">
        {image_html}
        <div class="content-body">
            <div class="content-topline">
                <span class="platform-pill">{platform_label}</span>
            </div>
            <h3 class="content-title">{content_title}</h3>
            <p class="content-copy">{escape(content_copy)}</p>
            {cta}
        </div>
    </article>
    """


def build_image_html(image_ref: str | None, live_url: str, platform: str, index: int = 1) -> str:
    """Build clickable image or placeholder."""
    image_src = resolve_image_src(image_ref)
    alt_text = f"{platform} live content preview {index}"

    if image_src:
        media = f'<img class="content-image" src="{escape(image_src)}" alt="{escape(alt_text)}" loading="lazy" />'
    else:
        media = (
            f'<div class="content-placeholder" role="img" aria-label="{escape(alt_text)}">'
            f"{escape(platform)}</div>"
        )

    if not is_valid_url(live_url):
        return f'<div class="content-media-link">{media}</div>'

    return (
        f'<a class="content-media-link" href="{escape(live_url)}" target="_blank" '
        f'rel="noopener noreferrer" aria-label="Open live {escape(platform)} post">'
        f"{media}</a>"
    )


def resolve_image_src(image_ref: str | None) -> str:
    """Resolve URL, data URI, or local image path into a browser-ready source."""
    if not image_ref:
        return ""

    value = str(image_ref).strip()
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
    """Build logo image HTML from assets, with fallback text."""
    logo_path = find_logo_path()
    if not logo_path:
        return """
        <div class="logo-fallback">
            SOAP<br />BOX
            <span>Influence + Retail Media</span>
        </div>
        """

    mime_type = mimetypes.guess_type(logo_path.name)[0] or "image/png"
    encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    return f'<img src="data:{mime_type};base64,{encoded}" alt="Soapbox Retail logo" />'


def find_logo_path() -> Path | None:
    """Find an existing logo asset without requiring a specific filename."""
    root_dir = Path(__file__).resolve().parents[1]
    candidates = [
        root_dir / "assets" / "logo.png",
        root_dir / "assets" / "logo.jpg",
        root_dir / "assets" / "logo.jpeg",
        root_dir / "assets" / "soapbox_logo.png",
        root_dir / "assets" / "soapbox-logo.png",
        root_dir / "app" / "assets" / "logo.png",
        root_dir / "app" / "assets" / "soapbox_logo.png",
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate

    return None


def infer_platform(live_url: str) -> str:
    """Infer platform from URL domain."""
    if not live_url:
        return ""

    parsed = urlparse(live_url)
    domain = parsed.netloc.lower()

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
    """Return whether a value is a valid HTTP(S) URL."""
    if not value:
        return False

    parsed = urlparse(str(value).strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def clean_text(value: object) -> str:
    """Normalize optional text values."""
    return str(value or "").strip()


def escape(value: object) -> str:
    """HTML-escape a value."""
    return html.escape(str(value or ""), quote=True)


def format_number(value: object) -> str:
    """Format numeric metrics with commas."""
    try:
        return f"{int(float(value or 0)):,}"
    except (TypeError, ValueError):
        return "0"