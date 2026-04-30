# core/reporting_template.py
from __future__ import annotations

import base64
import html
import mimetypes
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st
import streamlit.components.v1 as components


NAVY = "#10243D"
TEAL = "#27AEB7"
MUTED = "#5F7185"
BORDER = "#DDEEEF"


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

        .block-container {
            max-width: 1160px !important;
            padding: 24px 24px 32px !important;
        }

        .stApp {
            background: #ffffff;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    html_doc = build_report_document(report)
    item_count = len(report.get("content_items") or [])
    height = 1040 + max(0, item_count - 3) * 220
    components.html(html_doc, height=height, scrolling=True)


def build_report_document(report: dict) -> str:
    """Build a full HTML document for the report."""
    body = build_report_html(report)

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
        {body}
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
    }}

    * {{
        box-sizing: border-box;
    }}

    html,
    body {{
        margin: 0;
        padding: 0;
        background: #ffffff;
        color: var(--navy);
        font-family: "Raleway", Arial, sans-serif;
    }}

    body {{
        padding: 14px;
    }}

    .report-page {{
        width: min(1080px, 100%);
        margin: 0 auto;
        padding: 36px 38px 30px;
        border: 1px solid #e0eff1;
        border-radius: 30px;
        background:
            radial-gradient(circle at 93% 5%, rgba(39, 174, 183, 0.055), transparent 26%),
            linear-gradient(180deg, #ffffff 0%, #fbfefe 100%);
        box-shadow: 0 18px 60px rgba(16, 36, 61, 0.08);
    }}

    .report-header {{
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 32px;
        margin-bottom: 28px;
    }}

    .brand-name {{
        margin: 0 0 8px;
        color: var(--teal);
        font-size: 22px;
        font-weight: 800;
        line-height: 1.1;
    }}

    .report-title {{
        margin: 0 0 10px;
        color: var(--navy);
        font-size: 48px;
        font-weight: 900;
        letter-spacing: -1.4px;
        line-height: 1.02;
    }}

    .report-date {{
        color: var(--muted);
        font-size: 16px;
        font-weight: 700;
    }}

    .logo-box {{
        display: flex;
        align-items: flex-start;
        justify-content: flex-end;
        min-width: 178px;
        padding-top: 2px;
    }}

    .logo-box img {{
        display: block;
        max-width: 174px;
        max-height: 84px;
        object-fit: contain;
    }}

    .logo-fallback {{
        color: var(--navy);
        font-size: 32px;
        font-weight: 900;
        letter-spacing: -1px;
        line-height: 0.85;
        text-align: right;
    }}

    .logo-fallback small {{
        display: block;
        margin-top: 8px;
        color: var(--teal);
        font-size: 9px;
        font-weight: 800;
        letter-spacing: 1.3px;
        line-height: 1.25;
        text-transform: uppercase;
    }}

    .kpi-grid {{
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 15px;
        margin-bottom: 31px;
    }}

    .kpi-card {{
        min-height: 138px;
        padding: 18px 17px 16px;
        border-radius: 22px;
        position: relative;
        overflow: hidden;
    }}

    .kpi-card::after {{
        content: "";
        position: absolute;
        inset: 0;
        border-radius: inherit;
        background: linear-gradient(145deg, rgba(255,255,255,0.55), rgba(255,255,255,0));
        pointer-events: none;
    }}

    .kpi-card > * {{
        position: relative;
        z-index: 1;
    }}

    .kpi-teal {{
        background: rgba(39, 174, 183, 0.11);
        border: 1.5px solid rgba(39, 174, 183, 0.42);
    }}

    .kpi-navy {{
        background: rgba(16, 36, 61, 0.06);
        border: 1.5px solid rgba(16, 36, 61, 0.28);
    }}

    .kpi-icon {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 37px;
        height: 37px;
        margin-bottom: 17px;
        border-radius: 999px;
        font-size: 18px;
        font-weight: 900;
    }}

    .kpi-teal .kpi-icon {{
        color: var(--teal);
        background: rgba(39, 174, 183, 0.12);
        border: 1px solid rgba(39, 174, 183, 0.22);
    }}

    .kpi-navy .kpi-icon {{
        color: var(--navy);
        background: rgba(16, 36, 61, 0.075);
        border: 1px solid rgba(16, 36, 61, 0.14);
    }}

    .kpi-value {{
        margin-bottom: 8px;
        font-size: 31px;
        font-weight: 900;
        letter-spacing: -0.7px;
        line-height: 1;
    }}

    .kpi-teal .kpi-value {{
        color: var(--teal);
    }}

    .kpi-navy .kpi-value {{
        color: var(--navy);
    }}

    .kpi-label {{
        color: #52667a;
        font-size: 13px;
        font-weight: 800;
        line-height: 1.25;
    }}

    .section-heading {{
        display: flex;
        align-items: center;
        gap: 18px;
        margin: 0 0 18px;
    }}

    .section-heading h2 {{
        flex: 0 0 auto;
        margin: 0;
        color: var(--navy);
        font-size: 30px;
        font-weight: 900;
        letter-spacing: -0.65px;
        line-height: 1;
    }}

    .section-line {{
        flex: 1;
        height: 2px;
        min-width: 80px;
        background-image: linear-gradient(
            to right,
            rgba(39, 174, 183, 0.52) 35%,
            rgba(39, 174, 183, 0) 0%
        );
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
        grid-template-columns: 305px minmax(0, 1fr);
        min-height: 184px;
        overflow: hidden;
        border: 1px solid var(--border);
        border-radius: 24px;
        background: #ffffff;
        box-shadow: 0 12px 34px rgba(16, 36, 61, 0.055);
    }}

    .media-link {{
        display: block;
        min-height: 184px;
        color: inherit;
        text-decoration: none;
    }}

    .content-image {{
        display: block;
        width: 100%;
        height: 100%;
        min-height: 184px;
        object-fit: cover;
        background: #e9f7f8;
    }}

    .placeholder {{
        display: flex;
        align-items: center;
        justify-content: center;
        width: 100%;
        height: 100%;
        min-height: 184px;
        background:
            radial-gradient(circle at 24% 18%, rgba(255,255,255,0.92), transparent 30%),
            linear-gradient(135deg, #dff7f8 0%, #f8fcfd 100%);
        color: var(--teal);
        font-size: 16px;
        font-weight: 900;
        letter-spacing: 1.3px;
        text-transform: uppercase;
    }}

    .content-body {{
        display: flex;
        flex-direction: column;
        justify-content: center;
        padding: 22px 26px 21px;
    }}

    .platform-pill {{
        display: inline-flex;
        width: fit-content;
        margin-bottom: 13px;
        padding: 7px 11px;
        border: 1px solid rgba(39, 174, 183, 0.22);
        border-radius: 999px;
        background: rgba(39, 174, 183, 0.105);
        color: #178c95;
        font-size: 12px;
        font-weight: 900;
        letter-spacing: 0.75px;
        line-height: 1;
        text-transform: uppercase;
    }}

    .content-title {{
        margin: 0 0 9px;
        color: var(--navy);
        font-size: 23px;
        font-weight: 900;
        letter-spacing: -0.35px;
        line-height: 1.14;
    }}

    .content-copy {{
        margin: 0 0 17px;
        color: var(--muted);
        font-size: 14.5px;
        font-weight: 600;
        line-height: 1.45;
    }}

    .cta {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: fit-content;
        padding: 10px 16px;
        border-radius: 999px;
        background: var(--teal);
        color: #ffffff;
        font-size: 13px;
        font-weight: 900;
        line-height: 1;
        text-decoration: none;
        box-shadow: 0 8px 18px rgba(39, 174, 183, 0.22);
    }}

    .cta-disabled {{
        background: #d7e3e6;
        color: #697b88;
        box-shadow: none;
    }}

    .empty-content {{
        padding: 32px;
        border: 1.5px dashed #b7dfe4;
        border-radius: 22px;
        background: rgba(39, 174, 183, 0.055);
        color: var(--muted);
        font-size: 15px;
        font-weight: 700;
        text-align: center;
    }}

    .report-footer {{
        margin-top: 25px;
        color: #000000;
        font-size: 14px;
        font-weight: 800;
        text-align: center;
    }}

    @media (max-width: 850px) {{
        body {{
            padding: 8px;
        }}

        .report-page {{
            padding: 24px;
            border-radius: 24px;
        }}

        .report-header {{
            flex-direction: column;
            gap: 18px;
        }}

        .report-title {{
            font-size: 36px;
        }}

        .logo-box {{
            justify-content: flex-start;
        }}

        .kpi-grid {{
            grid-template-columns: repeat(2, minmax(0, 1fr));
        }}

        .content-card {{
            grid-template-columns: 1fr;
        }}

        .media-link,
        .content-image,
        .placeholder {{
            min-height: 245px;
        }}
    }}

    @media (max-width: 520px) {{
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
    """


def build_report_html(report: dict) -> str:
    """Build the report body HTML."""
    client_name = escape(report.get("client_name") or "Client")
    report_date = format_date(report.get("report_date") or "")
    logo_html = build_logo_html()
    kpi_html = build_kpi_grid(report)
    content_html = build_content_list(report.get("content_items") or [])

    return f"""
    <main class="report-page" aria-label="Weekly Campaign Metrics Report">
        <header class="report-header">
            <div>
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
    """


def build_kpi_grid(report: dict) -> str:
    """Build the four KPI cards."""
    kpis = [
        ("Organic Impressions", report.get("organic_impressions", 0), "teal", "◉"),
        ("Paid Impressions", report.get("paid_impressions", 0), "navy", "↗"),
        ("Organic Engagements", report.get("organic_engagements", 0), "teal", "♡"),
        ("Paid Engagements", report.get("paid_engagements", 0), "navy", "…"),
    ]

    cards = []
    for label, value, accent, icon in kpis:
        cards.append(
            f"""
            <article class="kpi-card kpi-{escape(accent)}">
                <div class="kpi-icon" aria-hidden="true">{escape(icon)}</div>
                <div class="kpi-value">{format_number(value)}</div>
                <div class="kpi-label">{escape(label)}</div>
            </article>
            """
        )

    return f"""
    <section class="kpi-grid" aria-label="Campaign KPI metrics">
        {"".join(cards)}
    </section>
    """


def build_content_list(content_items: list[dict]) -> str:
    """Build featured content cards."""
    cleaned_items = [item for item in content_items if (item.get("live_url") or "").strip()]

    if not cleaned_items:
        return """
        <section class="content-list">
            <div class="empty-content">
                Featured content will appear here once live posts are added.
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
    platform = clean_text(item.get("platform")) or infer_platform(live_url) or "Live Content"
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

    title = f"{platform} Campaign Content"
    copy = "Tap through to view the live campaign content."

    if is_valid_url(live_url):
        cta_html = (
            f'<a class="cta" href="{escape(live_url)}" target="_blank" '
            f'rel="noopener noreferrer" aria-label="Open live {escape(platform)} post">'
            "View Live Post</a>"
        )
    else:
        cta_html = '<span class="cta cta-disabled" aria-disabled="true">View Live Post</span>'

    return f"""
    <article class="content-card">
        {image_html}
        <div class="content-body">
            <span class="platform-pill">{escape(platform)}</span>
            <h3 class="content-title">{escape(title)}</h3>
            <p class="content-copy">{escape(copy)}</p>
            {cta_html}
        </div>
    </article>
    """


def build_image_html(image_ref: str | None, live_url: str, platform: str, index: int) -> str:
    """Build the clickable image area."""
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
            f"{escape(platform)}</div>"
        )

    if not is_valid_url(live_url):
        return f'<div class="media-link">{media_html}</div>'

    return (
        f'<a class="media-link" href="{escape(live_url)}" target="_blank" '
        f'rel="noopener noreferrer" aria-label="Open live {escape(platform)} post">'
        f"{media_html}</a>"
    )


def resolve_image_src(image_ref: str | None) -> str:
    """Resolve a URL, data URI, or local image path into a browser-safe src."""
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
    """Build the Soapbox logo image or fallback wordmark."""
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
    """Find an existing logo file."""
    root_dir = Path(__file__).resolve().parents[1]

    candidates = [
        root_dir / "assets" / "logo.png",
        root_dir / "assets" / "logo.jpg",
        root_dir / "assets" / "logo.jpeg",
        root_dir / "assets" / "soapbox_logo.png",
        root_dir / "assets" / "soapbox-logo.png",
        root_dir / "app" / "assets" / "logo.png",
        root_dir / "app" / "assets" / "logo.jpg",
        root_dir / "app" / "assets" / "soapbox_logo.png",
        root_dir / "app" / "assets" / "soapbox-logo.png",
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate

    return None


def infer_platform(live_url: str) -> str:
    """Infer the content platform from the URL."""
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
    """Normalize text."""
    return str(value or "").strip()


def escape(value: object) -> str:
    """Escape a value for HTML."""
    return html.escape(str(value or ""), quote=True)


def format_number(value: object) -> str:
    """Format a metric number."""
    try:
        return f"{int(float(value or 0)):,}"
    except (TypeError, ValueError):
        return "0"


def format_date(value: object) -> str:
    """Format ISO dates into a cleaner report date when possible."""
    raw = clean_text(value)
    if not raw:
        return ""

    try:
        year, month, day = raw.split("-")
        return f"{int(month)}/{int(day)}/{year}"
    except ValueError:
        return raw