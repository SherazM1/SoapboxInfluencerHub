from __future__ import annotations

import base64
import html
from pathlib import Path
from urllib.parse import urlparse

import streamlit as st


def render_client_report(report: dict) -> None:
    inject_report_css()
    st.markdown(build_report_html(report), unsafe_allow_html=True)


def inject_report_css() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Raleway:wght@400;500;600;700;800&display=swap');
        .stApp {
            background: #ffffff;
        }
        header, [data-testid="stToolbar"], [data-testid="stSidebar"], [data-testid="stSidebarNav"] {
            display: none;
        }
        .block-container {
            max-width: 1180px;
            padding: 34px 42px 28px;
        }
        .soapbox-report, .soapbox-report * {
            box-sizing: border-box;
            font-family: 'Raleway', sans-serif;
            letter-spacing: 0;
        }
        .soapbox-report {
            color: #10243d;
        }
        .report-shell {
            border: 1px solid #dceef0;
            border-radius: 28px;
            padding: 34px;
            background: linear-gradient(180deg, #ffffff 0%, #fbfefe 100%);
            box-shadow: 0 18px 60px rgba(19, 55, 75, 0.08);
        }
        .report-header {
            align-items: flex-start;
            display: flex;
            gap: 24px;
            justify-content: space-between;
            margin-bottom: 30px;
        }
        .brand-kicker {
            color: #27aeb7;
            font-size: 15px;
            font-weight: 800;
            margin-bottom: 8px;
            text-transform: uppercase;
        }
        .report-title {
            color: #10243d;
            font-size: 46px;
            font-weight: 800;
            line-height: 1.03;
            margin: 0 0 10px;
        }
        .report-date {
            color: #5b6d80;
            font-size: 17px;
            font-weight: 600;
        }
        .logo-wrap {
            align-items: center;
            background: #ffffff;
            border: 1px solid #e5f1f3;
            border-radius: 18px;
            display: flex;
            justify-content: center;
            min-height: 82px;
            min-width: 170px;
            padding: 16px 20px;
        }
        .logo-wrap img {
            max-height: 56px;
            max-width: 150px;
            object-fit: contain;
        }
        .kpi-grid {
            display: grid;
            gap: 16px;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            margin-bottom: 34px;
        }
        .kpi-card {
            border-radius: 22px;
            padding: 20px;
            min-height: 142px;
        }
        .kpi-teal {
            background: rgba(39, 174, 183, 0.12);
            border: 1px solid rgba(39, 174, 183, 0.38);
        }
        .kpi-navy {
            background: rgba(16, 36, 61, 0.07);
            border: 1px solid rgba(16, 36, 61, 0.22);
        }
        .kpi-icon {
            border-radius: 999px;
            display: inline-flex;
            height: 34px;
            margin-bottom: 20px;
            width: 34px;
        }
        .kpi-teal .kpi-icon {
            background: #27aeb7;
            box-shadow: inset 0 0 0 9px rgba(255, 255, 255, 0.38);
        }
        .kpi-navy .kpi-icon {
            background: #10243d;
            box-shadow: inset 0 0 0 9px rgba(255, 255, 255, 0.28);
        }
        .kpi-value {
            color: #10243d;
            font-size: 32px;
            font-weight: 800;
            line-height: 1;
            margin-bottom: 9px;
        }
        .kpi-label {
            color: #526579;
            font-size: 14px;
            font-weight: 700;
        }
        .section-title-row {
            align-items: center;
            border-top: 1px solid #e6eff1;
            display: flex;
            justify-content: space-between;
            margin: 4px 0 18px;
            padding-top: 28px;
        }
        .section-title {
            color: #10243d;
            font-size: 29px;
            font-weight: 800;
            margin: 0;
        }
        .section-rule {
            background: #27aeb7;
            border-radius: 999px;
            height: 5px;
            width: 84px;
        }
        .content-list {
            display: grid;
            gap: 18px;
        }
        .content-card {
            align-items: stretch;
            background: #ffffff;
            border: 1px solid #dfecee;
            border-radius: 24px;
            display: grid;
            gap: 0;
            grid-template-columns: 236px minmax(0, 1fr);
            min-height: 188px;
            overflow: hidden;
            box-shadow: 0 12px 34px rgba(16, 36, 61, 0.06);
        }
        .content-image {
            background-color: #e9f7f8;
            background-position: center;
            background-size: cover;
            min-height: 188px;
        }
        .content-placeholder {
            align-items: center;
            background: linear-gradient(135deg, #dff6f7 0%, #f4fbfc 100%);
            color: #27aeb7;
            display: flex;
            font-size: 42px;
            font-weight: 800;
            justify-content: center;
            min-height: 188px;
        }
        .content-body {
            padding: 22px 24px 20px;
        }
        .content-meta {
            align-items: center;
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-bottom: 12px;
        }
        .creator {
            color: #10243d;
            font-size: 15px;
            font-weight: 800;
        }
        .platform-pill {
            background: rgba(39, 174, 183, 0.12);
            border: 1px solid rgba(39, 174, 183, 0.30);
            border-radius: 999px;
            color: #178c95;
            font-size: 12px;
            font-weight: 800;
            padding: 6px 10px;
            text-transform: uppercase;
        }
        .content-title {
            color: #10243d;
            font-size: 23px;
            font-weight: 800;
            line-height: 1.18;
            margin: 0 0 8px;
        }
        .content-description {
            color: #607286;
            font-size: 15px;
            font-weight: 500;
            line-height: 1.48;
            margin: 0 0 18px;
        }
        .cta {
            background: #10243d;
            border-radius: 999px;
            color: #ffffff !important;
            display: inline-flex;
            font-size: 13px;
            font-weight: 800;
            padding: 10px 16px;
            text-decoration: none !important;
        }
        .cta-disabled {
            background: #d8e3e6;
            color: #667784 !important;
        }
        .empty-content {
            border: 1px dashed #b9dfe3;
            border-radius: 22px;
            color: #607286;
            font-weight: 600;
            padding: 28px;
            text-align: center;
        }
        .report-footer {
            color: #000000;
            font-size: 14px;
            font-weight: 700;
            padding-top: 26px;
            text-align: center;
        }
        @media (max-width: 900px) {
            .block-container {
                padding: 18px;
            }
            .report-shell {
                padding: 22px;
                border-radius: 22px;
            }
            .report-header {
                flex-direction: column;
            }
            .report-title {
                font-size: 34px;
            }
            .kpi-grid {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .content-card {
                grid-template-columns: 1fr;
            }
        }
        @media (max-width: 560px) {
            .kpi-grid {
                grid-template-columns: 1fr;
            }
            .section-title-row {
                align-items: flex-start;
                flex-direction: column;
                gap: 12px;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def build_report_html(report: dict) -> str:
    logo_html = build_logo_html()
    kpis = [
        ("Organic Impressions", report.get("organic_impressions", 0), "teal"),
        ("Paid Impressions", report.get("paid_impressions", 0), "navy"),
        ("Organic Engagements", report.get("organic_engagements", 0), "teal"),
        ("Paid Engagements", report.get("paid_engagements", 0), "navy"),
    ]
    kpi_html = "".join(
        f"""
        <div class="kpi-card kpi-{accent}">
            <span class="kpi-icon"></span>
            <div class="kpi-value">{format_number(value)}</div>
            <div class="kpi-label">{escape(label)}</div>
        </div>
        """
        for label, value, accent in kpis
    )
    content_items = report.get("content_items") or []
    content_html = (
        "".join(build_content_card(item) for item in content_items)
        if content_items
        else '<div class="empty-content">Featured content will appear here once live posts are added.</div>'
    )

    return f"""
    <div class="soapbox-report">
        <main class="report-shell">
            <section class="report-header">
                <div>
                    <div class="brand-kicker">{escape(report.get("client_name", "Client"))}</div>
                    <h1 class="report-title">Weekly Campaign Metrics</h1>
                    <div class="report-date">{escape(report.get("report_date", ""))}</div>
                </div>
                <div class="logo-wrap">{logo_html}</div>
            </section>
            <section class="kpi-grid">{kpi_html}</section>
            <section class="section-title-row">
                <h2 class="section-title">Featured Live Content</h2>
                <span class="section-rule"></span>
            </section>
            <section class="content-list">{content_html}</section>
            <footer class="report-footer">Generated by Soapbox Retail</footer>
        </main>
    </div>
    """


def build_content_card(item: dict) -> str:
    image_html = build_image_html(item.get("image_url"))
    live_url = (item.get("live_url") or "").strip()
    if is_valid_url(live_url):
        cta = f'<a class="cta" href="{escape(live_url)}" target="_blank" rel="noopener noreferrer">View Live Post</a>'
    else:
        cta = '<span class="cta cta-disabled">View Live Post</span>'
    return f"""
    <article class="content-card">
        {image_html}
        <div class="content-body">
            <div class="content-meta">
                <span class="creator">{escape(item.get("creator_handle", ""))}</span>
                <span class="platform-pill">{escape(item.get("platform", ""))}</span>
            </div>
            <h3 class="content-title">{escape(item.get("content_title", ""))}</h3>
            <p class="content-description">{escape(item.get("content_description", ""))}</p>
            {cta}
        </div>
    </article>
    """


def build_image_html(image_url: str | None) -> str:
    if image_url and is_valid_url(image_url.strip()):
        safe_url = escape(image_url.strip())
        return f'<div class="content-image" style="background-image: url({safe_url});"></div>'
    return '<div class="content-placeholder">SB</div>'


def build_logo_html() -> str:
    logo_path = Path(__file__).resolve().parents[1] / "assets" / "logo.png"
    if not logo_path.exists():
        return "<strong>Soapbox Retail</strong>"
    encoded = base64.b64encode(logo_path.read_bytes()).decode("ascii")
    return f'<img src="data:image/png;base64,{encoded}" alt="Soapbox Retail logo" />'


def is_valid_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def escape(value: object) -> str:
    return html.escape(str(value or ""), quote=True)


def format_number(value: object) -> str:
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "0"
