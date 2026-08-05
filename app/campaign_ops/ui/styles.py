from __future__ import annotations

import streamlit as st


def apply_campaign_ops_styles() -> None:
    if st.session_state.get("campaign_ops_styles_applied"):
        return
    st.session_state["campaign_ops_styles_applied"] = True
    st.markdown(
        """
        <style>
        [data-testid="stAppViewContainer"] .campaign-ops-page-header {
            border-left: 6px solid #0f766e;
            padding: .65rem .85rem;
            margin: .15rem 0 1rem 0;
            background: #f8fafc;
            border-bottom: 1px solid #d7dee8;
        }
        [data-testid="stAppViewContainer"] .campaign-ops-page-header h1,
        [data-testid="stAppViewContainer"] .campaign-ops-page-header h2 {
            margin: 0;
            color: #0f3f46;
            letter-spacing: 0;
        }
        [data-testid="stAppViewContainer"] .campaign-ops-section-header {
            margin: 1rem 0 .35rem 0;
            padding: .35rem .55rem;
            border: 1px solid #d7dee8;
            border-left: 5px solid #0f766e;
            background: #ffffff;
        }
        [data-testid="stAppViewContainer"] .campaign-ops-section-header strong {
            color: #0f3f46;
        }
        [data-testid="stAppViewContainer"] .campaign-ops-empty {
            padding: .65rem .8rem;
            border: 1px dashed #b7c4d4;
            background: #fbfdff;
            color: #475569;
            margin: .35rem 0;
        }
        [data-testid="stAppViewContainer"] .campaign-ops-badge {
            display: inline-block;
            padding: .1rem .45rem;
            border: 1px solid #b7c4d4;
            border-radius: 999px;
            background: #f8fafc;
            color: #0f172a;
            font-size: .82rem;
            line-height: 1.35;
            margin-right: .25rem;
        }
        [data-testid="stAppViewContainer"] .campaign-ops-card {
            border: 1px solid #d7dee8;
            border-radius: 6px;
            padding: .75rem;
            background: #ffffff;
            min-height: 13rem;
        }
        [data-testid="stAppViewContainer"] .campaign-ops-quick-panel {
            border: 1px solid #123142;
            background: #0f2433;
            color: #f8fafc;
            padding: .7rem;
            border-radius: 6px;
        }
        [data-testid="stAppViewContainer"] .campaign-ops-filter-note {
            font-size: .9rem;
            color: #475569;
        }
        [data-testid="stAppViewContainer"] div[data-testid="stMetric"] {
            border: 1px solid #d7dee8;
            border-radius: 6px;
            padding: .45rem .65rem;
            background: #ffffff;
        }
        [data-testid="stAppViewContainer"] .stDataFrame {
            border: 1px solid #d7dee8;
        }
        [data-testid="stAppViewContainer"] p, 
        [data-testid="stAppViewContainer"] span,
        [data-testid="stAppViewContainer"] div {
            overflow-wrap: anywhere;
        }
        @media (max-width: 760px) {
            [data-testid="stAppViewContainer"] .campaign-ops-card {
                min-height: auto;
            }
            [data-testid="stAppViewContainer"] .campaign-ops-page-header {
                padding: .55rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

