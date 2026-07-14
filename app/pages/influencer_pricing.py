from __future__ import annotations

import sys
import uuid
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.influencer_pricing import calculate_metric_estimates, calculate_pricing
from core.proposal_ppt import build_proposal_payload, generate_powerpoint_proposal
from core.db import get_database_status
from core.historical_data import (
    EXCEL_DATA_COLUMNS,
    archive_campaign,
    fetch_active_campaign_rows,
    fetch_campaign_by_id,
    fetch_campaign_years,
    format_historical_campaign_rows,
    insert_campaign_with_metrics,
    update_campaign_with_metrics,
)

PROPOSAL_TEMPLATE_PATH = (
    ROOT_DIR / "Soapbox 2026 Influencer Campaign Test and Learn Proposal Template.pptx"
)


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


def format_currency(value: float) -> str:
    """Format a numeric value as whole-dollar currency."""
    return f"${value:,.0f}"


def format_number(value: float) -> str:
    """Format a numeric value with comma separators."""
    if float(value).is_integer():
        return f"{int(value):,}"
    return f"{value:,.2f}"


def format_whole_number(value: float) -> str:
    """Format a numeric value as a rounded whole number."""
    rounded = Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{int(rounded):,}"


BRAND_AMBASSADORS_HELP = (
    "Typically includes an influencer hosting an event with other influencers "
    "or friends in the specific niche. The gathering is centered around "
    "featured products/brand and includes several posts during and after the "
    "gathering/event. Rates typically range from $2,000-$4,000 depending on "
    "deliverables/posts included."
)
VIDEO_CREATORS_HELP = (
    "Typically posts a TikTok or IG Reel and 2 stories. Rates typically range "
    "from $800-$2,000."
)
SOCIAL_STORIES_HELP = (
    "IG carousel post and 3 stories. Rates typically range from $500-$1,000."
)
SOCIAL_STORY_VIDEO_HELP = (
    "Combined deliverable package using social/story/video content. Default "
    "planning rate is $1,600."
)
MACRO_INFLUENCERS_HELP = (
    "Typically posts an IG Reel or TikTok and has over 500K followers. "
    "$10,000 is a planning default and can be adjusted based on follower "
    "size/classification."
)
CLICK_2_CART_HELP = (
    "Click2Cart links start at $4,500 for one link and up to 6 items for a "
    "6-week campaign. Additional links, more than 6 items, or additional "
    "flight time may require additional cost."
)
PAID_MEDIA_SPEND_HELP = (
    "Paid media spend can fluctuate based on overall goals and total spend."
)
PRODUCT_COST_HELP = (
    "Product cost is only included when needed in the overall budget, "
    "typically for higher-end items or if influencers need compensation to "
    "purchase the product."
)
SHIPPING_COST_HELP = (
    "Shipping cost is used if Soapbox ships products to influencers. This "
    "usually is not needed if influencers purchase in-store."
)
ANALYTICS_SOFTWARE_HELP = "Does not change; included to cover agency fees."
COMMUNITY_COST_HELP = "Does not change; included to cover agency fees."
HIRING_LEEWAY_HELP = (
    "Included to negotiate with influencers on compensation, usage rights, "
    "and performance incentives."
)
HOURLY_INTERNAL_RATE_HELP = "Does not change unless approved."


def render_influencer_mix_inputs() -> dict[str, float | int]:
    """Render influencer count and rate inputs."""
    st.markdown("#### Influencer Mix")
    count_col, rate_col = st.columns(2)
    with count_col:
        brand_ambassadors_count = st.number_input(
            "Brand Ambassadors Count",
            min_value=0,
            value=0,
            step=1,
            help=BRAND_AMBASSADORS_HELP,
        )
        video_creators_count = st.number_input(
            "Video Creators Count",
            min_value=0,
            value=0,
            step=1,
            help=VIDEO_CREATORS_HELP,
        )
        social_stories_count = st.number_input(
            "Social + Stories Count",
            min_value=0,
            value=0,
            step=1,
            help=SOCIAL_STORIES_HELP,
        )
        social_story_video_count = st.number_input(
            "Social + Story + Video Count",
            min_value=0,
            value=0,
            step=1,
            help=SOCIAL_STORY_VIDEO_HELP,
        )
        macro_influencers_count = st.number_input(
            "Macro Influencers Count",
            min_value=0,
            value=0,
            step=1,
            help=MACRO_INFLUENCERS_HELP,
        )
    with rate_col:
        brand_ambassadors_rate = st.number_input(
            "Brand Ambassadors Rate",
            min_value=0.0,
            value=2000.0,
            step=100.0,
            help=BRAND_AMBASSADORS_HELP,
        )
        video_creators_rate = st.number_input(
            "Video Creators Rate",
            min_value=0.0,
            value=1200.0,
            step=100.0,
            help=VIDEO_CREATORS_HELP,
        )
        social_stories_rate = st.number_input(
            "Social + Stories Rate",
            min_value=0.0,
            value=800.0,
            step=100.0,
            help=SOCIAL_STORIES_HELP,
        )
        social_story_video_rate = st.number_input(
            "Social + Story + Video Rate",
            min_value=0.0,
            value=1800.0,
            step=100.0,
            help=SOCIAL_STORY_VIDEO_HELP,
        )
        macro_influencers_rate = st.number_input(
            "Macro Influencers Rate",
            min_value=0.0,
            value=12000.0,
            step=500.0,
            help=MACRO_INFLUENCERS_HELP,
        )

    return {
        "brand_ambassadors_count": brand_ambassadors_count,
        "brand_ambassadors_rate": brand_ambassadors_rate,
        "video_creators_count": video_creators_count,
        "video_creators_rate": video_creators_rate,
        "social_stories_count": social_stories_count,
        "social_stories_rate": social_stories_rate,
        "social_story_video_count": social_story_video_count,
        "social_story_video_rate": social_story_video_rate,
        "macro_influencers_count": macro_influencers_count,
        "macro_influencers_rate": macro_influencers_rate,
    }


def render_advanced_assumptions() -> dict[str, float]:
    """Render advanced pricing assumptions."""
    with st.expander("Advanced Assumptions"):
        analytics_software_cost = st.number_input(
            "Analytics Software Cost",
            min_value=0.0,
            value=1000.0,
            step=100.0,
            help=ANALYTICS_SOFTWARE_HELP,
        )
        community_cost = st.number_input(
            "Community Cost",
            min_value=0.0,
            value=500.0,
            step=100.0,
            help=COMMUNITY_COST_HELP,
        )
        hiring_leeway_cost = st.number_input(
            "Hiring Leeway Cost",
            min_value=0.0,
            value=750.0,
            step=100.0,
            help=HIRING_LEEWAY_HELP,
        )
        hourly_internal_rate = st.number_input(
            "Hourly Internal Rate",
            min_value=0.0,
            value=250.0,
            step=25.0,
            help=HOURLY_INTERNAL_RATE_HELP,
        )

        hours_col1, hours_col2, hours_col3 = st.columns(3)
        with hours_col1:
            time_management_hours = st.number_input(
                "Time Management Hours", min_value=0.0, value=10.0, step=1.0
            )
        with hours_col2:
            influencer_review_hours = st.number_input(
                "Influencer Review Hours", min_value=0.0, value=0.0, step=1.0
            )
        with hours_col3:
            content_review_hours = st.number_input(
                "Content Review Hours", min_value=0.0, value=0.0, step=1.0
            )

        markup_multiplier = st.number_input(
            "Markup Multiplier", min_value=0.0, value=1.8, step=0.1
        )
        withholding_rate = st.number_input(
            "Withholding Rate (decimal)",
            min_value=0.0,
            max_value=1.0,
            value=0.06,
            step=0.01,
            format="%.2f",
            help="Enter 0.06 for 6%.",
        )

    return {
        "analytics_software_cost": analytics_software_cost,
        "community_cost": community_cost,
        "hiring_leeway_cost": hiring_leeway_cost,
        "hourly_internal_rate": hourly_internal_rate,
        "time_management_hours": time_management_hours,
        "influencer_review_hours": influencer_review_hours,
        "content_review_hours": content_review_hours,
        "markup_multiplier": markup_multiplier,
        "withholding_rate": withholding_rate,
    }


def render_pricing_summary(
    pricing_mode: str,
    inputs: dict[str, str | float | int],
    outputs: dict[str, float],
) -> None:
    """Render the running pricing summary."""
    st.markdown("#### Running Program Summary")
    st.metric("Total Influencers", format_number(outputs["total_influencers"]))
    st.metric("Compensation Total", format_currency(outputs["compensation_total"]))
    st.metric("Paid Media + C2C", format_currency(outputs["paid_media_c2c_total"]))
    st.metric("Product + Shipping", format_currency(outputs["product_shipping_total"]))
    st.metric("Time Management Cost", format_currency(outputs["time_management_cost"]))
    st.divider()
    st.metric("Running Raw Subtotal", format_currency(outputs["raw_subtotal"]))

    markup_label = f"Cost with {inputs['markup_multiplier']:g}x Markup"
    withholding_percent = inputs["withholding_rate"] * 100
    withholding_label = f"Withholding {withholding_percent:g}%"
    st.metric(markup_label, format_currency(outputs["subtotal_after_markup"]))
    st.metric(withholding_label, format_currency(outputs["withholding_amount"]))
    st.metric("Final Program Total", format_currency(outputs["program_total"]))

    if pricing_mode == "Budget Planner":
        st.divider()
        st.metric("Budget", format_currency(float(inputs["budget"])))
        st.metric("Budget Remaining", format_currency(outputs["budget_remaining"]))
        difference = abs(outputs["budget_remaining"])
        if outputs["is_over_budget"]:
            st.warning(f"This plan is over budget by {format_currency(difference)}.")
        else:
            st.success(f"This plan is within budget by {format_currency(difference)}.")


def build_proposal_filename(pricing_state: dict[str, object] | None) -> str:
    inputs = pricing_state.get("inputs", {}) if isinstance(pricing_state, dict) else {}
    brand = str(inputs.get("brand") or "Influencer Proposal")
    safe_brand = "".join(
        char if char.isalnum() or char in {" ", "-", "_"} else "" for char in brand
    ).strip()
    safe_brand = safe_brand or "Influencer Proposal"
    return f"{safe_brand} Proposal.pptx"


def render_powerpoint_proposal_export() -> None:
    pricing_state = st.session_state.get("influencer_pricing_current")
    scenario_snapshots = st.session_state.get("metrics_snapshots")

    if st.button("Generate PowerPoint Proposal", type="primary"):
        if not PROPOSAL_TEMPLATE_PATH.exists():
            st.error(f"Proposal template was not found: {PROPOSAL_TEMPLATE_PATH}")
            return
        payload = build_proposal_payload(pricing_state, scenario_snapshots)
        output_path = (
            ROOT_DIR
            / "outputs"
            / "proposals"
            / f"proposal_{uuid.uuid4().hex[:10]}.pptx"
        )
        try:
            result = generate_powerpoint_proposal(
                PROPOSAL_TEMPLATE_PATH,
                payload,
                output_path,
            )
        except Exception as exc:
            st.error(f"PowerPoint proposal could not be generated: {exc}")
            return
        st.session_state["proposal_pptx_bytes"] = result.pptx_bytes
        st.session_state["proposal_pptx_filename"] = build_proposal_filename(
            pricing_state
        )
        st.session_state["proposal_pptx_warnings"] = result.warnings
        st.success("PowerPoint proposal generated.")

    pptx_bytes = st.session_state.get("proposal_pptx_bytes")
    if pptx_bytes:
        warnings = st.session_state.get("proposal_pptx_warnings") or []
        for warning in warnings:
            st.warning(warning)
        st.download_button(
            "Download PowerPoint Proposal",
            data=pptx_bytes,
            file_name=st.session_state.get(
                "proposal_pptx_filename", "Influencer Proposal.pptx"
            ),
            mime=(
                "application/vnd.openxmlformats-officedocument."
                "presentationml.presentation"
            ),
        )


def render_pricing_tool() -> None:
    """Render the main Pricing Tool calculator."""
    st.subheader("Pricing Tool")
    st.markdown("Build a campaign cost estimate and view the running program total.")

    pricing_mode = st.radio(
        "Pricing Mode",
        ["Budget Planner", "Build Estimate"],
        horizontal=True,
    )

    input_col, summary_col = st.columns([3, 2], gap="large")
    with input_col:
        st.markdown("#### Campaign Setup")
        brand = st.text_input("Brand")
        retailer = st.text_input("Retailer")
        campaign_name = st.text_input("Campaign Name")
        campaign_flight = st.text_input("Campaign Flight", value="6 - 8 weeks")
        budget = 0.0
        if pricing_mode == "Budget Planner":
            budget = st.number_input(
                "Budget", min_value=0.0, value=0.0, step=1000.0
            )

        inputs: dict[str, str | float | int] = {
            "pricing_mode": pricing_mode,
            "brand": brand,
            "client_name": brand,
            "retailer": retailer,
            "campaign_name": campaign_name,
            "campaign_flight": campaign_flight,
            "budget": budget,
        }
        inputs.update(render_influencer_mix_inputs())

        st.markdown("#### Media + Product Costs")
        click_2_cart_cost = st.number_input(
            "Click-2-Cart Cost",
            min_value=0.0,
            value=4500.0,
            step=100.0,
            help=CLICK_2_CART_HELP,
        )
        paid_media_spend = st.number_input(
            "Paid Media Spend",
            min_value=0.0,
            value=0.0,
            step=1000.0,
            help=PAID_MEDIA_SPEND_HELP,
        )
        product_cost_per_influencer = st.number_input(
            "Product Cost per Influencer",
            min_value=0.0,
            value=0.0,
            step=10.0,
            help=PRODUCT_COST_HELP,
        )
        shipping_cost_per_influencer = st.number_input(
            "Shipping Cost per Influencer",
            min_value=0.0,
            value=0.0,
            step=10.0,
            help=SHIPPING_COST_HELP,
        )
        inputs.update(
            {
                "click_2_cart_cost": click_2_cart_cost,
                "paid_media_spend": paid_media_spend,
                "product_cost_per_influencer": product_cost_per_influencer,
                "shipping_cost_per_influencer": shipping_cost_per_influencer,
            }
        )
        inputs.update(render_advanced_assumptions())

    outputs = calculate_pricing(inputs)
    st.session_state["influencer_pricing_current"] = {
        "inputs": inputs,
        "outputs": outputs,
        "total_influencers": outputs["total_influencers"],
        "paid_media_spend": inputs["paid_media_spend"],
        "budget": inputs["budget"],
        "program_total": outputs["program_total"],
        "raw_subtotal": outputs["raw_subtotal"],
        "brand_ambassadors_count": inputs["brand_ambassadors_count"],
        "brand_ambassadors_rate": inputs["brand_ambassadors_rate"],
        "video_creators_count": inputs["video_creators_count"],
        "video_creators_rate": inputs["video_creators_rate"],
        "social_stories_count": inputs["social_stories_count"],
        "social_stories_rate": inputs["social_stories_rate"],
        "social_story_video_count": inputs["social_story_video_count"],
        "social_story_video_rate": inputs["social_story_video_rate"],
        "macro_influencers_count": inputs["macro_influencers_count"],
        "macro_influencers_rate": inputs["macro_influencers_rate"],
    }

    with summary_col:
        render_pricing_summary(pricing_mode, inputs, outputs)

    st.divider()
    with st.expander("Pricing Option 2"):
        st.markdown("Coming later — reserved for alternate pricing route.")
    with st.expander("Pricing Option 3"):
        st.markdown("Coming later — reserved for alternate pricing route.")

    st.divider()
    render_powerpoint_proposal_export()


def render_metric_calculator_card(
    title: str,
    summary: dict[str, float],
    estimate: float,
    per_1k: bool = False,
) -> None:
    """Render one compact calculator result block."""
    labels = {
        "min": "Min Per $1k" if per_1k else "Min",
        "max": "Max Per $1k" if per_1k else "Max",
        "average": "Average Per $1k" if per_1k else "Average",
        "median": "Median Per $1k" if per_1k else "Median",
    }
    rows = [
        {
            "Benchmark": labels[key],
            "Value": format_whole_number(summary[key]),
        }
        for key in ("min", "max", "average", "median")
        if key in summary
    ]

    with st.container(border=True):
        st.markdown(f"##### {title}")
        st.metric("Estimate", format_whole_number(estimate))
        st.dataframe(
            rows,
            width="stretch",
            height=35 * (len(rows) + 1),
            hide_index=True,
        )


def initialize_metrics_snapshots() -> dict[str, dict[str, object] | None]:
    """Ensure A/B/C metrics snapshots exist in session state."""
    if "metrics_snapshots" not in st.session_state:
        st.session_state["metrics_snapshots"] = {"A": None, "B": None, "C": None}
    return st.session_state["metrics_snapshots"]


def save_metrics_snapshot(bucket: str, estimates: dict[str, float]) -> None:
    """Save the current rollup outputs into one snapshot bucket."""
    snapshots = initialize_metrics_snapshots()
    pricing_state = st.session_state.get("influencer_pricing_current")
    pricing_inputs = (
        pricing_state.get("inputs", {})
        if isinstance(pricing_state, dict)
        and isinstance(pricing_state.get("inputs"), dict)
        else {}
    )
    pricing_outputs = (
        pricing_state.get("outputs", {})
        if isinstance(pricing_state, dict)
        and isinstance(pricing_state.get("outputs"), dict)
        else {}
    )
    snapshots[bucket] = {
        "organic_paid_impressions": estimates["total_impressions"],
        "organic_paid_engagements_clicks": estimates["total_engagement_actions"],
        "campaign_flight": pricing_inputs.get("campaign_flight", ""),
        "budget": pricing_inputs.get(
            "budget", pricing_state.get("budget", "")
            if isinstance(pricing_state, dict)
            else ""
        ),
        "total_influencers": pricing_outputs.get(
            "total_influencers", pricing_state.get("total_influencers", 0)
            if isinstance(pricing_state, dict)
            else 0
        ),
        "social_stories_count": pricing_inputs.get("social_stories_count", 0),
        "video_creators_count": pricing_inputs.get("video_creators_count", 0),
        "click_2_cart_cost": pricing_inputs.get("click_2_cart_cost", 0),
        "paid_media_spend": pricing_inputs.get("paid_media_spend", 0),
        "program_total": pricing_outputs.get(
            "program_total", pricing_state.get("program_total", 0)
            if isinstance(pricing_state, dict)
            else 0
        ),
    }


def clear_metrics_snapshots() -> None:
    """Clear all A/B/C metrics snapshots."""
    st.session_state["metrics_snapshots"] = {"A": None, "B": None, "C": None}


def render_metrics_snapshot_table() -> None:
    """Render saved A/B/C rollup snapshots as a compact comparison table."""
    snapshots = initialize_metrics_snapshots()
    rows = []
    row_specs = [
        ("Budget", "budget", "currency"),
        ("Organic + Paid Impressions", "organic_paid_impressions"),
        ("Organic + Paid Engagements/Clicks", "organic_paid_engagements_clicks"),
    ]
    for spec in row_specs:
        label, key = spec[:2]
        formatter = spec[2] if len(spec) > 2 else "whole_number"
        row = {"Metric": label}
        for bucket in ("A", "B", "C"):
            snapshot = snapshots.get(bucket)
            if not isinstance(snapshot, dict) or key not in snapshot:
                row[bucket] = "-"
                continue
            value = snapshot.get(key)
            if formatter == "currency":
                row[bucket] = (
                    format_currency(float(value)) if value not in ("", None) else "-"
                )
            else:
                row[bucket] = format_whole_number(value)
        rows.append(row)

    st.dataframe(
        rows,
        width="stretch",
        height=147,
        hide_index=True,
        column_order=["Metric", "A", "B", "C"],
    )


def render_metric_calculator_cards(
    calculator_results: dict[str, object],
) -> None:
    """Render compact Excel-style metric calculator outputs."""
    summaries = calculator_results["summaries"]
    estimates = calculator_results["estimates"]
    if estimates is None:
        st.info("Metric benchmark data is not available yet.")
        return

    st.markdown("#### Metric Calculators")
    cards = [
        ("Organic Impressions", "organic_impressions", False),
        ("Paid Impressions", "paid_impressions", True),
        ("Engagements", "engagements", False),
        ("Paid Clicks", "paid_clicks", True),
        ("Paid Engagements", "paid_engagements", True),
    ]
    cols = st.columns(5)
    for col, (title, key, per_1k) in zip(cols, cards):
        with col:
            render_metric_calculator_card(
                title,
                summaries[key],
                estimates[key],
                per_1k=per_1k,
            )

    rollup_cols = st.columns(2)
    rollup_cols[0].metric(
        "Organic + Paid Impressions",
        format_whole_number(estimates["total_impressions"]),
    )
    rollup_cols[1].metric(
        "Organic + Paid Engagements/Clicks",
        format_whole_number(estimates["total_engagement_actions"]),
    )

    action_cols = st.columns(4)
    for col, bucket in zip(action_cols[:3], ("A", "B", "C")):
        if col.button(f"Save as {bucket}", use_container_width=True):
            save_metrics_snapshot(bucket, estimates)
    if action_cols[3].button("Clear All", use_container_width=True):
        clear_metrics_snapshots()

    render_metrics_snapshot_table()


def _date_value(value: object | None = None) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return date.today()
    return date.today()


def _text_value(value: object | None) -> str:
    return "" if value is None else str(value)


def _campaign_label(row: dict[str, object]) -> str:
    return f"{row['campaign_date']} - {row['program_name']}"


def render_campaign_form(
    form_key: str,
    submit_label: str,
    initial: dict[str, object] | None = None,
) -> tuple[bool, dict[str, object]]:
    initial = initial or {}
    with st.form(form_key):
        top_cols = st.columns([2, 1, 1])
        with top_cols[0]:
            program_name = st.text_input(
                "Program",
                value=_text_value(initial.get("program_name")),
                key=f"{form_key}_program",
            )
        with top_cols[1]:
            campaign_date = st.date_input(
                "Date",
                value=_date_value(initial.get("campaign_date")),
                key=f"{form_key}_date",
            )
        with top_cols[2]:
            client_name = st.text_input(
                "Client",
                value=_text_value(initial.get("client_name")),
                key=f"{form_key}_client",
            )

        notes = st.text_area(
            "Notes",
            value=_text_value(initial.get("notes")),
            height=80,
            key=f"{form_key}_notes",
        )

        required_cols = st.columns(3)
        with required_cols[0]:
            influencer_count = st.number_input(
                "# of Influencers",
                min_value=0.0,
                value=float(initial.get("influencer_count") or 0),
                step=1.0,
                key=f"{form_key}_influencers",
            )
        with required_cols[1]:
            engagements = st.number_input(
                "Engagements",
                min_value=0.0,
                value=float(initial.get("engagements") or 0),
                step=1.0,
                key=f"{form_key}_engagements",
            )
        with required_cols[2]:
            organic_impressions = st.number_input(
                "Organic Impressions",
                min_value=0.0,
                value=float(initial.get("organic_impressions") or 0),
                step=1.0,
                key=f"{form_key}_organic_impressions",
            )

        paid_cols = st.columns(3)
        with paid_cols[0]:
            paid_impressions = st.text_input(
                "Paid Impressions",
                value=_text_value(initial.get("paid_impressions")),
                key=f"{form_key}_paid_impressions",
            )
            paid_spend_impressions = st.text_input(
                "Paid Spend (Impressions)",
                value=_text_value(initial.get("paid_spend_impressions")),
                key=f"{form_key}_paid_spend_impressions",
            )
        with paid_cols[1]:
            paid_engagements = st.text_input(
                "Paid Engagement",
                value=_text_value(initial.get("paid_engagements")),
                key=f"{form_key}_paid_engagements",
            )
            paid_spend_engagements = st.text_input(
                "Paid Spend (Engagement)",
                value=_text_value(initial.get("paid_spend_engagements")),
                key=f"{form_key}_paid_spend_engagements",
            )
        with paid_cols[2]:
            paid_clicks = st.text_input(
                "Paid Clicks",
                value=_text_value(initial.get("paid_clicks")),
                key=f"{form_key}_paid_clicks",
            )
            paid_spend_clicks = st.text_input(
                "Paid Spend (Clicks)",
                value=_text_value(initial.get("paid_spend_clicks")),
                key=f"{form_key}_paid_spend_clicks",
            )

        submitted = st.form_submit_button(submit_label, type="primary")

    payload: dict[str, object] = {
        "Program": program_name,
        "Date": campaign_date,
        "Client": client_name,
        "Notes": notes,
        "# of Influencers": influencer_count,
        "Engagements": engagements,
        "Organic Impressions": organic_impressions,
        "Paid Impressions": paid_impressions,
        "Paid Spend (Impressions)": paid_spend_impressions,
        "Paid Engagement": paid_engagements,
        "Paid Spend (Engagement)": paid_spend_engagements,
        "Paid Clicks": paid_clicks,
        "Paid Spend (Clicks)": paid_spend_clicks,
    }
    return submitted, payload


def show_campaign_action_result(
    success: bool, errors: list[str], success_message: str
) -> None:
    if success:
        st.success(success_message)
        st.rerun()
    for error in errors:
        st.error(error)


def render_add_campaign() -> None:
    with st.expander("Add Campaign"):
        submitted, payload = render_campaign_form(
            "historical_add_campaign",
            "Add Campaign",
        )
        if submitted:
            success, errors = insert_campaign_with_metrics(payload)
            show_campaign_action_result(success, errors, "Campaign added.")


def render_edit_campaign(active_rows: list[dict[str, object]]) -> None:
    with st.expander("Edit Campaign"):
        if not active_rows:
            st.info("No active campaigns are available to edit.")
            return
        options = {str(row["id"]): _campaign_label(row) for row in active_rows}
        selected_id = st.selectbox(
            "Campaign",
            list(options.keys()),
            format_func=lambda value: options[value],
            key="historical_edit_campaign_id",
        )
        selected_row = fetch_campaign_by_id(selected_id)
        if selected_row is None:
            st.warning("Selected campaign could not be loaded.")
            return
        submitted, payload = render_campaign_form(
            f"historical_edit_campaign_{selected_id}",
            "Save Changes",
            selected_row,
        )
        if submitted:
            success, errors = update_campaign_with_metrics(selected_id, payload)
            show_campaign_action_result(success, errors, "Campaign updated.")


def render_archive_campaign(active_rows: list[dict[str, object]]) -> None:
    with st.expander("Archive Campaign"):
        if not active_rows:
            st.info("No active campaigns are available to archive.")
            return
        options = {str(row["id"]): _campaign_label(row) for row in active_rows}
        selected_id = st.selectbox(
            "Campaign to Archive",
            list(options.keys()),
            format_func=lambda value: options[value],
            key="historical_archive_campaign_id",
        )
        confirmed = st.checkbox(
            "Archive this campaign",
            key="historical_archive_confirmed",
        )
        if st.button(
            "Archive Campaign",
            disabled=not confirmed,
            type="secondary",
            use_container_width=True,
        ):
            success, errors = archive_campaign(selected_id)
            show_campaign_action_result(success, errors, "Campaign archived.")


def render_metrics() -> None:
    """Render the benchmark-based Metrics foundation."""
    st.subheader("Metrics")
    st.markdown(
        "Estimate Good / Better / Best campaign performance using pricing inputs "
        "and historical benchmarks."
    )

    use_pricing_values = st.checkbox("Use Pricing Tool Values", value=True)
    pricing_state = st.session_state.get("influencer_pricing_current")
    has_pricing_values = bool(
        isinstance(pricing_state, dict)
        and isinstance(pricing_state.get("inputs"), dict)
        and isinstance(pricing_state.get("outputs"), dict)
    )
    using_pricing_values = use_pricing_values and has_pricing_values

    if use_pricing_values and not has_pricing_values:
        st.info("Build a pricing estimate first, or enter values manually.")

    if using_pricing_values:
        st.session_state["metrics_total_influencers"] = int(
            pricing_state["outputs"].get(
                "total_influencers", pricing_state.get("total_influencers", 0)
            )
            or 0
        )
        st.session_state["metrics_total_paid_media_spend"] = float(
            pricing_state["inputs"].get(
                "paid_media_spend", pricing_state.get("paid_media_spend", 0)
            )
            or 0
        )

    input_cols = st.columns(2)
    with input_cols[0]:
        total_influencers = st.number_input(
            "Total Influencers",
            min_value=0,
            value=0,
            step=1,
            key="metrics_total_influencers",
            disabled=using_pricing_values,
        )
    with input_cols[1]:
        total_paid_media_spend = st.number_input(
            "Total Paid Media Spend",
            min_value=0.0,
            value=0.0,
            step=1000.0,
            key="metrics_total_paid_media_spend",
            disabled=using_pricing_values,
        )

    st.markdown("#### Paid Spend Distribution")
    distribution_cols = st.columns(3)
    with distribution_cols[0]:
        paid_impressions_percent = st.number_input(
            "Paid Impressions %",
            min_value=0,
            max_value=100,
            value=50,
            step=5,
            key="metrics_paid_impressions_percent",
        )
    with distribution_cols[1]:
        paid_clicks_percent = st.number_input(
            "Paid Clicks %",
            min_value=0,
            max_value=100,
            value=25,
            step=5,
            key="metrics_paid_clicks_percent",
        )
    with distribution_cols[2]:
        paid_engagements_percent = st.number_input(
            "Paid Engagements %",
            min_value=0,
            max_value=100,
            value=25,
            step=5,
            key="metrics_paid_engagements_percent",
        )

    distribution_total = (
        paid_impressions_percent + paid_clicks_percent + paid_engagements_percent
    )
    if distribution_total != 100:
        st.warning("Paid media distribution should total 100%.")

    paid_impressions_spend = total_paid_media_spend * (
        paid_impressions_percent / 100
    )
    paid_clicks_spend = total_paid_media_spend * (paid_clicks_percent / 100)
    paid_engagements_spend = total_paid_media_spend * (
        paid_engagements_percent / 100
    )

    inputs = {
        "total_influencers": total_influencers,
        "paid_impressions_spend": paid_impressions_spend,
        "paid_clicks_spend": paid_clicks_spend,
        "paid_engagements_spend": paid_engagements_spend,
    }
    calculator_results = calculate_metric_estimates(inputs)

    st.caption(
        "Using Pricing Tool values" if using_pricing_values else "Using manual values"
    )
    summary_cols = st.columns(5)
    summary_cols[0].metric("Total Influencers", format_number(total_influencers))
    summary_cols[1].metric(
        "Total Paid Media Spend", format_currency(total_paid_media_spend)
    )
    summary_cols[2].metric(
        "Paid Impression Spend", format_currency(paid_impressions_spend)
    )
    summary_cols[3].metric(
        "Paid Click Spend", format_currency(paid_clicks_spend)
    )
    summary_cols[4].metric(
        "Paid Engagement Spend", format_currency(paid_engagements_spend)
    )

    render_metric_calculator_cards(calculator_results)


def render_historical_data() -> None:
    """Render the Historical Data management page."""
    st.subheader("Historical Data")
    st.markdown("Manage campaign history used by Metrics benchmarks.")

    database_status = get_database_status()
    st.caption(
        "DB config: "
        f"DATABASE_URL detected={database_status['database_url_detected']}; "
        f"connection succeeded={database_status['connection_succeeded']}; "
        f"status={database_status['message']}"
    )

    active_rows = fetch_active_campaign_rows()
    years = fetch_campaign_years()
    view_mode = st.radio(
        "View",
        ["Full View", "Baseline View by Year"],
        horizontal=True,
        key="historical_data_view_mode",
    )

    selected_year = None
    if view_mode == "Baseline View by Year":
        if years:
            selected_year = st.selectbox(
                "Year",
                years,
                index=len(years) - 1,
                key="historical_data_year",
            )
        else:
            st.info("No active campaign years are available yet.")

    table_rows = active_rows
    if selected_year is not None:
        table_rows = fetch_active_campaign_rows(selected_year)

    historical_rows = format_historical_campaign_rows(table_rows)
    if historical_rows:
        st.dataframe(
            historical_rows,
            width="stretch",
            hide_index=True,
            column_order=EXCEL_DATA_COLUMNS,
        )
    else:
        st.info(
            "No active historical campaign rows are available for this view. "
            "Configure DATABASE_URL and load campaigns to power this view and "
            "Metrics benchmarks."
        )

    st.divider()
    action_cols = st.columns(3)
    with action_cols[0]:
        render_add_campaign()
    with action_cols[1]:
        render_edit_campaign(active_rows)
    with action_cols[2]:
        render_archive_campaign(active_rows)


def main() -> None:
    """Render the Influencer Pricing foundation workspace."""
    st.set_page_config(
        page_title="Influencer Pricing",
        page_icon="??",
        layout="wide",
    )
    hide_default_streamlit_sidebar_nav()

    st.title("Influencer Pricing")
    st.markdown(
        "Build campaign pricing, estimate metrics, and organize historical campaign data."
    )
    st.divider()

    pricing_tab, metrics_tab, historical_data_tab = st.tabs(
        ["Pricing Tool", "Metrics", "Historical Data"]
    )

    with pricing_tab:
        render_pricing_tool()

    with metrics_tab:
        render_metrics()

    with historical_data_tab:
        render_historical_data()


if __name__ == "__main__":
    main()
