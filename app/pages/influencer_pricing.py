from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from core.influencer_pricing import calculate_metric_estimates, calculate_pricing


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
            value=1000.0,
            step=100.0,
            help=VIDEO_CREATORS_HELP,
        )
        social_stories_rate = st.number_input(
            "Social + Stories Rate",
            min_value=0.0,
            value=600.0,
            step=100.0,
            help=SOCIAL_STORIES_HELP,
        )
        social_story_video_rate = st.number_input(
            "Social + Story + Video Rate",
            min_value=0.0,
            value=1600.0,
            step=100.0,
            help=SOCIAL_STORY_VIDEO_HELP,
        )
        macro_influencers_rate = st.number_input(
            "Macro Influencers Rate",
            min_value=0.0,
            value=10000.0,
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
            value=500.0,
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
        client_name = st.text_input("Client Name")
        campaign_name = st.text_input("Campaign Name")
        budget = 0.0
        if pricing_mode == "Budget Planner":
            budget = st.number_input(
                "Budget", min_value=0.0, value=0.0, step=1000.0
            )

        inputs: dict[str, str | float | int] = {
            "pricing_mode": pricing_mode,
            "client_name": client_name,
            "campaign_name": campaign_name,
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


def render_metric_calculator_card(
    title: str,
    summary: dict[str, float],
    estimate: float,
    per_1k: bool = False,
) -> None:
    """Render one compact calculator result block."""
    multiplier = 1000 if per_1k else 1
    labels = {
        "min": "Min Per $1k" if per_1k else "Min",
        "max": "Max Per $1k" if per_1k else "Max",
        "average": "Average Per $1k" if per_1k else "Average",
        "median": "Median Per $1k" if per_1k else "Median",
    }
    rows = [
        {
            "Benchmark": labels[key],
            "Value": format_number(summary[key] * multiplier),
        }
        for key in ("min", "max", "average", "median")
    ]

    with st.container(border=True):
        st.markdown(f"##### {title}")
        st.metric("Estimate", format_number(round(estimate)))
        st.dataframe(rows, width="stretch", hide_index=True)


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
    for row_start in range(0, len(cards), 2):
        cols = st.columns(2)
        for col, (title, key, per_1k) in zip(cols, cards[row_start : row_start + 2]):
            with col:
                render_metric_calculator_card(
                    title,
                    summaries[key],
                    estimates[key],
                    per_1k=per_1k,
                )

    rollup_cols = st.columns(2)
    rollup_cols[0].metric(
        "Total Impressions", format_number(round(estimates["total_impressions"]))
    )
    rollup_cols[1].metric(
        "Total Engagement Actions",
        format_number(round(estimates["total_engagement_actions"])),
    )


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
    """Render the Historical Data foundation placeholder."""
    st.subheader("Historical Data")
    st.markdown("Historical campaigns will eventually power the Metrics benchmarks.")

    sample_rows = [
        {
            "Program": "Spring Refresh",
            "Date": "2025-03-15",
            "Influencers": 12,
            "Organic Impressions": 1450000,
            "Engagements": 118000,
            "Paid Impressions": 820000,
            "Paid Spend": 7500,
            "Paid Clicks": 6200,
        },
        {
            "Program": "Summer Entertaining",
            "Date": "2025-06-20",
            "Influencers": 18,
            "Organic Impressions": 2380000,
            "Engagements": 205000,
            "Paid Impressions": 1250000,
            "Paid Spend": 12000,
            "Paid Clicks": 10100,
        },
        {
            "Program": "Back to School",
            "Date": "2025-08-10",
            "Influencers": 24,
            "Organic Impressions": 3150000,
            "Engagements": 286000,
            "Paid Impressions": 1900000,
            "Paid Spend": 18000,
            "Paid Clicks": 15800,
        },
        {
            "Program": "Holiday Hosting",
            "Date": "2025-11-05",
            "Influencers": 30,
            "Organic Impressions": 4720000,
            "Engagements": 410000,
            "Paid Impressions": 2650000,
            "Paid Spend": 25000,
            "Paid Clicks": 22400,
        },
    ]
    st.dataframe(sample_rows, width="stretch", hide_index=True)

    st.markdown("#### Future supported fields")
    st.markdown(
        """
- program_name
- campaign_date
- influencer_count
- engagements
- organic_impressions
- paid_impressions
- paid_impressions_spend
- paid_engagements
- paid_engagements_spend
- paid_clicks
- paid_clicks_spend
- notes
        """
    )
    st.info(
        "Database-backed add/edit/delete and Excel import will be added in a later phase."
    )


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
