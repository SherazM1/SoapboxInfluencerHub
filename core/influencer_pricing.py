from __future__ import annotations

from typing import Any

METRICS_BENCHMARKS = {
    "Good": {
        "organic_impressions_per_influencer": 113771,
        "engagements_per_influencer": 9149,
        "paid_impressions_per_1k": 991389,
        "paid_clicks_per_1k": 7679,
        "paid_engagements_per_1k": 196961,
    },
    "Better": {
        "organic_impressions_per_influencer": 173300,
        "engagements_per_influencer": 62706,
        "paid_impressions_per_1k": 1039225,
        "paid_clicks_per_1k": 8399,
        "paid_engagements_per_1k": 230065,
    },
    "Best": {
        "organic_impressions_per_influencer": 2320675,
        "engagements_per_influencer": 2176232,
        "paid_impressions_per_1k": 3460092,
        "paid_clicks_per_1k": 34368,
        "paid_engagements_per_1k": 1929983,
    },
}


def _number(inputs: dict[str, Any], key: str) -> float:
    """Read a numeric pricing input as a float."""
    return float(inputs.get(key, 0) or 0)


def _brand_ambassador_number(inputs: dict[str, Any], key: str) -> float:
    """Read renamed Brand Ambassador fields with older session fallback."""
    legacy_key = key.replace("brand_ambassadors", "home_gatherings")
    return float(inputs.get(key, inputs.get(legacy_key, 0)) or 0)


def calculate_pricing(inputs: dict[str, Any]) -> dict[str, float]:
    """Calculate the main Influencer Pricing estimate."""
    total_influencers = (
        _brand_ambassador_number(inputs, "brand_ambassadors_count")
        + _number(inputs, "video_creators_count")
        + _number(inputs, "social_stories_count")
        + _number(inputs, "social_story_video_count")
        + _number(inputs, "macro_influencers_count")
    )

    compensation_total = (
        _brand_ambassador_number(inputs, "brand_ambassadors_count")
        * _brand_ambassador_number(inputs, "brand_ambassadors_rate")
        + _number(inputs, "video_creators_count")
        * _number(inputs, "video_creators_rate")
        + _number(inputs, "social_stories_count")
        * _number(inputs, "social_stories_rate")
        + _number(inputs, "social_story_video_count")
        * _number(inputs, "social_story_video_rate")
        + _number(inputs, "macro_influencers_count")
        * _number(inputs, "macro_influencers_rate")
    )

    paid_media_c2c_total = _number(inputs, "click_2_cart_cost") + _number(
        inputs, "paid_media_spend"
    )
    product_shipping_total = total_influencers * (
        _number(inputs, "product_cost_per_influencer")
        + _number(inputs, "shipping_cost_per_influencer")
    )
    time_management_cost = (
        _number(inputs, "time_management_hours")
        + _number(inputs, "influencer_review_hours")
        + _number(inputs, "content_review_hours")
    ) * _number(inputs, "hourly_internal_rate")

    raw_subtotal = (
        compensation_total
        + paid_media_c2c_total
        + product_shipping_total
        + _number(inputs, "analytics_software_cost")
        + _number(inputs, "community_cost")
        + _number(inputs, "hiring_leeway_cost")
        + time_management_cost
    )
    subtotal_after_markup = raw_subtotal * _number(inputs, "markup_multiplier")
    withholding_amount = subtotal_after_markup * _number(inputs, "withholding_rate")
    program_total = subtotal_after_markup + withholding_amount
    budget_remaining = _number(inputs, "budget") - program_total

    return {
        "total_influencers": total_influencers,
        "compensation_total": compensation_total,
        "paid_media_c2c_total": paid_media_c2c_total,
        "product_shipping_total": product_shipping_total,
        "time_management_cost": time_management_cost,
        "raw_subtotal": raw_subtotal,
        "subtotal_after_markup": subtotal_after_markup,
        "withholding_amount": withholding_amount,
        "program_total": program_total,
        "budget_remaining": budget_remaining,
        "is_over_budget": program_total > _number(inputs, "budget"),
    }


def calculate_metrics(
    inputs: dict[str, Any],
    benchmarks: dict[str, dict[str, float]] = METRICS_BENCHMARKS,
) -> dict[str, dict[str, float]]:
    """Calculate Good, Better, and Best campaign performance estimates."""
    total_influencers = _number(inputs, "total_influencers")
    paid_impressions_spend = _number(inputs, "paid_impressions_spend")
    paid_clicks_spend = _number(inputs, "paid_clicks_spend")
    paid_engagements_spend = _number(inputs, "paid_engagements_spend")
    results: dict[str, dict[str, float]] = {}

    for level in ("Good", "Better", "Best"):
        level_benchmarks = benchmarks[level]
        organic_impressions = (
            total_influencers
            * level_benchmarks["organic_impressions_per_influencer"]
        )
        organic_engagements = (
            total_influencers * level_benchmarks["engagements_per_influencer"]
        )
        paid_impressions = (
            paid_impressions_spend
            / 1000
            * level_benchmarks["paid_impressions_per_1k"]
        )
        paid_clicks = (
            paid_clicks_spend / 1000 * level_benchmarks["paid_clicks_per_1k"]
        )
        paid_engagements = (
            paid_engagements_spend
            / 1000
            * level_benchmarks["paid_engagements_per_1k"]
        )

        results[level] = {
            "organic_impressions": organic_impressions,
            "organic_engagements": organic_engagements,
            "paid_impressions": paid_impressions,
            "paid_clicks": paid_clicks,
            "paid_engagements": paid_engagements,
            "organic_paid_impressions": organic_impressions + paid_impressions,
            "organic_engagements_paid_clicks_paid_engagements": (
                organic_engagements + paid_clicks + paid_engagements
            ),
        }

    return results
