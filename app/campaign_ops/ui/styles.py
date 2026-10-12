"""Centralized Program Tracker visual system."""
import streamlit as st

EDITOR_CSS = """
.st-key-ops_editor {border-top:2px solid #33B2C1;padding-top:.6rem;}
.st-key-ops_editor [data-testid="stVerticalBlock"] {gap:.5rem;}
.st-key-ops_table {border:1px solid #dce3e8;border-radius:4px;padding:.4rem .6rem;background:#FFFFFF;overflow-x:auto;}
.st-key-ops_table [class*="st-key-ops_row_"] {border-bottom:1px solid #e6ebef;padding:.25rem 0;}
.st-key-ops_table [data-testid="stVerticalBlock"] {gap:.25rem;}
.st-key-ops_table [data-testid="stHorizontalBlock"] {align-items:center;gap:.5rem;}
.st-key-ops_table > [data-testid="stVerticalBlock"] > [data-testid="stHorizontalBlock"] {background:#f3f6f8;color:#002C47;border-bottom:1px solid #dce3e8;}
.st-key-ops_table [data-testid="stCheckbox"] {display:flex;justify-content:center;}
.st-key-ops_table button {padding:.2rem .4rem;min-height:2rem;}
.st-key-ops_table p {font-size:.85rem;margin:0;}
.st-key-ops_editor input {font-size:.875rem;}
.st-key-ops_editor [data-testid="stHorizontalBlock"]:has(button[kind="primary"]) > [data-testid="stColumn"]:last-child [data-testid="stButton"] {display:flex;justify-content:flex-end;}
.st-key-ops_editor h4 {color:#002C47;font-size:1rem;padding-bottom:.35rem;border-bottom:1px solid #33B2C1;}
@media(max-width:760px) {
.st-key-ops_table [data-testid="stHorizontalBlock"] {min-width:680px;flex-wrap:nowrap;}
.st-key-ops_table [data-testid="stColumn"] {min-width:0;}
}
"""

APP_CSS = """
[data-testid="stMainBlockContainer"], .main .block-container {max-width:1320px;width:100%;margin-inline:auto;padding:1.8rem 2rem 3rem;}
[data-testid="stMain"] {background:#FFFFFF;color:#172b3a;}
[data-testid="stMain"] [data-testid="stVerticalBlock"] {gap:1rem;}
[data-testid="stMain"] h1, [data-testid="stMain"] h2, [data-testid="stMain"] h3 {color:#002C47;letter-spacing:-.025em;}
[data-testid="stMain"] h1 {font-size:2rem;}
[data-testid="stMain"] h3 {font-size:1.35rem;padding:.2rem 0;}
[data-testid="stMain"] h4 {font-size:1.05rem;color:#002C47;font-weight:700;}
[data-testid="stMain"] .block-container {padding-top:1.4rem;}
[data-testid="stMain"] button {border:1px solid #cbd5dd;border-radius:4px;min-height:2.15rem;padding:.3rem .75rem;color:#002C47;box-shadow:none;}
[data-testid="stMain"] button[kind="primary"] {background:#33B2C1;border-color:#33B2C1;color:#002C47;font-weight:600;}
[data-testid="stMain"] button:hover {border-color:#33B2C1;background:#edf8f9;color:#002C47;}
[data-testid="stMain"] button[kind="primary"]:hover {background:#2ca3b1;}
[data-testid="stMain"] button:focus-visible {outline:2px solid #002C47;outline-offset:2px;}
[data-testid="stMain"] [data-baseweb="input"], [data-testid="stMain"] [data-baseweb="select"] > div, [data-testid="stMain"] [data-baseweb="textarea"] {border-radius:4px;border-color:#cbd5dd;background:#FFFFFF;min-height:2.1rem;}
[data-testid="stMain"] [data-baseweb="input"]:focus-within, [data-testid="stMain"] [data-baseweb="select"]:focus-within > div, [data-testid="stMain"] [data-baseweb="textarea"]:focus-within {border-color:#33B2C1;box-shadow:0 0 0 1px #33B2C1;}
[data-testid="stMain"] [data-baseweb="base-input"] {background:#FFFFFF;}
[data-testid="stMain"] [data-baseweb="radio"]:has(input:checked) > div:first-child, [data-testid="stMain"] [data-baseweb="checkbox"]:has(input:checked) > div:first-child {background:#002C47;border-color:#002C47;}
[data-testid="stMain"] [data-baseweb="radio"] {display:flex;align-items:center;gap:.4rem;}
[data-testid="stMain"] [data-baseweb="radio"] > div:first-child {border-radius:999px;}
[data-testid="stMain"] input {padding:.4rem .6rem;color:#172b3a;}
[data-testid="stMain"] label p {font-size:.875rem;color:#002C47;}
[data-testid="stMain"] hr {margin:.25rem 0;border-color:#e2e8ed;}
[data-testid="stMain"] .stExpander {border:1px solid #dfe7ec;border-radius:4px;background:#f9fbfc;}
[data-testid="stMain"] .stExpander summary {color:#002C47;font-size:.82rem;padding:.4rem .75rem;}
.campaign-ops-page-header {padding:.15rem 0 .8rem;border-bottom:2px solid #33B2C1;margin-bottom:.3rem;}
.campaign-ops-page-header h1 {margin:0;color:#002C47;line-height:1.15;}
.campaign-ops-page-header > div {font-size:.9rem;color:#586875;margin-top:.2rem;}
.campaign-ops-section-header {margin:.9rem 0 .4rem;padding:.35rem 0 .25rem;border-bottom:1px solid #dce3e8;color:#002C47;}
.campaign-ops-section-header > div {font-size:.875rem;color:#002C47;font-weight:700;letter-spacing:.01em;}
.campaign-ops-empty {padding:.85rem;border:1px dashed #cbd5dd;border-radius:4px;background:#f7f9fa;color:#586875;}
.campaign-ops-filter-note {font-size:.85rem;color:#586875;}
.campaign-ops-badge {display:inline-block;padding:.1rem .4rem;border:1px solid #dce3e8;border-radius:3px;background:#f3f6f8;color:#002C47;font-size:.8rem;margin-right:.25rem;}
.campaign-ops-card {border:1px solid #dce3e8;border-radius:4px;padding:.75rem;background:#FFFFFF;}
.campaign-ops-quick-panel {border:1px solid #dce3e8;border-left:3px solid #33B2C1;background:#f3f6f8;color:#002C47;padding:.7rem;border-radius:4px;}
.st-key-campaign_ops_viewer_context {max-width:320px;margin-top:.15rem;}
.st-key-campaign_ops_viewer_context [data-testid="stVerticalBlock"] {gap:.2rem;}
.st-key-campaign_ops_viewer_context [data-testid="stSelectbox"] {max-width:240px;}
.st-key-campaign_ops_navigation {margin-top:.2rem;margin-bottom:.3rem;}
.st-key-campaign_ops_navigation [data-testid="stHorizontalBlock"] {justify-content:flex-start;flex-wrap:wrap;gap:.45rem;}
.st-key-campaign_ops_navigation [data-testid="stColumn"] {flex:0 0 auto !important;width:auto !important;min-width:0 !important;}
.st-key-campaign_ops_navigation button {min-height:2.2rem;padding:.42rem .8rem;font-size:.875rem;}
.st-key-campaign_ops_navigation button[kind="primary"] {background:#002C47;color:#FFFFFF;border-color:#002C47;border-bottom:3px solid #33B2C1;}
.st-key-campaign_ops_navigation .campaign-ops-section-header {border:0;font-size:.78rem;color:#002C47;font-weight:700;padding:0;margin:.15rem 0 .2rem;}
.st-key-program_registry {border:1px solid #dce3e8;border-radius:4px;padding:.4rem .65rem;overflow-x:auto;background:#fff;}
.st-key-program_registry [data-testid="stHorizontalBlock"] {gap:.65rem;align-items:center;border-bottom:1px solid #e6ebef;padding:.3rem 0;}
.st-key-program_registry > [data-testid="stVerticalBlock"] > [data-testid="stHorizontalBlock"]:first-child {background:#f3f6f8;color:#002C47;}
.st-key-program_registry [data-testid="stVerticalBlock"] {gap:.2rem;}
.st-key-program_registry_header {background:#f3f6f8;color:#002C47;border-bottom:1px solid #dce3e8;}
.st-key-program_registry p {font-size:.875rem;margin:0;overflow-wrap:anywhere;}
.st-key-program_registry button {min-height:1.8rem;padding:.2rem .55rem;}
.st-key-program_registry [data-testid="stButton"] button {border-color:#c5d0d8;}
.st-key-program_section_actions [data-testid="stHorizontalBlock"] {align-items:center;gap:.5rem;}
.st-key-program_section_actions [data-testid="stColumn"]:last-child [data-testid="stButton"] {display:flex;justify-content:flex-end;}
.st-key-program_creation_form [data-testid="stHorizontalBlock"] {flex-wrap:nowrap;align-items:center;}
.st-key-program_creation_form [data-testid="stColumn"]:last-child {display:flex;justify-content:flex-end;}
.st-key-program_creation_form {max-width:800px;border:1px solid #dce3e8;border-top:2px solid #33B2C1;border-radius:4px;padding:1rem;}
[data-testid="stMain"] .stRadioGroup {padding:.2rem .3rem;border:1px solid #dfe7ec;border-radius:6px;background:#f5f9fa;}
[data-testid="stMain"] .stRadioGroup > div {gap:.35rem;}
[data-testid="stMain"] .stRadio [data-baseweb="radio"] {border-radius:999px;padding:.35rem .7rem;}
[data-testid="stMain"] .stRadio [data-baseweb="radio"]:has(input:checked) {background:#002C47;color:#FFFFFF;border-radius:999px;}
@media(max-width:760px) {
[data-testid="stMainBlockContainer"], .main .block-container {padding:1rem .75rem 2rem;}
.st-key-program_registry [data-testid="stHorizontalBlock"] {min-width:700px;flex-wrap:nowrap;}
.st-key-program_registry [data-testid="stColumn"] {min-width:0;}
}
"""

def apply_editor_styles():
    st.html(f"<style>{APP_CSS}{EDITOR_CSS}</style>")

def apply_campaign_ops_styles():
    st.markdown(f"<style>{APP_CSS}{EDITOR_CSS}</style>", unsafe_allow_html=True)
