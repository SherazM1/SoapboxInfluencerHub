from __future__ import annotations
from statistics import mean, median
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

METRIC_CALCULATOR_BENCHMARKS = {
    "organic_impressions": {
        "max": 2320675,
        "average": 173300,
        "median": 113771,
    },
    "engagements": {
        "min": 157,
        "max": 2176232,
        "average": 62706,
        "median": 9149,
    },
    "paid_impressions": {
        "max": 3460092,
        "average": 1039225,
        "median": 991389,
        "per_1k": True,
    },
    "paid_clicks": {
        "max": 34368,
        "average": 8399,
        "median": 7679,
        "per_1k": True,
    },
    "paid_engagements": {
        "max": 1929983,
        "average": 230065,
        "median": 196961,
        "per_1k": True,
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


def _valid_benchmark_values(values: list[Any]) -> list[float]:
    """Return finite, non-negative benchmark values."""
    cleaned: list[float] = []
    for value in values:
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            continue
        if numeric_value >= 0 and numeric_value not in (float("inf"), float("-inf")):
            cleaned.append(numeric_value)
    return cleaned


def _row_number(row: dict[str, Any], *keys: str) -> float | None:
    """Read the first usable numeric value from a row."""
    for key in keys:
        if key not in row:
            continue
        try:
            return float(row[key])
        except (TypeError, ValueError):
            continue
    return None


def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
    """Calculate a ratio only when the divisor is valid."""
    if numerator is None or denominator is None or denominator == 0:
        return None
    return numerator / denominator


def load_historical_benchmarks(
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, list[float]]:
    """Load benchmark columns using a shape that can later map to Data rows."""
    benchmark_values: dict[str, list[float]] = {
        "organic_impressions": [],
        "engagements": [],
        "paid_impressions": [],
        "paid_clicks": [],
        "paid_engagements": [],
    }

    if rows:
        for row in rows:
            organic_impressions = _row_number(
                row, "F", "organic_impressions_benchmark"
            )
            if organic_impressions is None:
                organic_impressions = _safe_ratio(
                    _row_number(row, "E", "organic_impressions"),
                    _row_number(row, "C", "influencer_count"),
                )

            engagements = _row_number(row, "G", "engagements_benchmark")
            if engagements is None:
                engagements = _safe_ratio(
                    _row_number(row, "D", "engagements"),
                    _row_number(row, "C", "influencer_count"),
                )

            paid_impressions = _row_number(row, "J", "paid_impressions_benchmark")
            if paid_impressions is None:
                paid_impressions = _safe_ratio(
                    _row_number(row, "H", "paid_impressions"),
                    _row_number(row, "I", "paid_impressions_spend"),
                )

            paid_engagements = _row_number(row, "M", "paid_engagements_benchmark")
            if paid_engagements is None:
                paid_engagements = _safe_ratio(
                    _row_number(row, "K", "paid_engagements"),
                    _row_number(row, "L", "paid_engagements_spend"),
                )

            paid_clicks = _row_number(row, "P", "paid_clicks_benchmark")
            if paid_clicks is None:
                paid_clicks = _safe_ratio(
                    _row_number(row, "N", "paid_clicks"),
                    _row_number(row, "O", "paid_clicks_spend"),
                )

            benchmark_values["organic_impressions"].append(organic_impressions)
            benchmark_values["engagements"].append(engagements)
            benchmark_values["paid_impressions"].append(
                paid_impressions * 1000 if paid_impressions is not None else None
            )
            benchmark_values["paid_clicks"].append(
                paid_clicks * 1000 if paid_clicks is not None else None
            )
            benchmark_values["paid_engagements"].append(
                paid_engagements * 1000 if paid_engagements is not None else None
            )
    else:
        for level_benchmarks in METRICS_BENCHMARKS.values():
            benchmark_values["organic_impressions"].append(
                level_benchmarks["organic_impressions_per_influencer"]
            )
            benchmark_values["engagements"].append(
                level_benchmarks["engagements_per_influencer"]
            )
            benchmark_values["paid_impressions"].append(
                level_benchmarks["paid_impressions_per_1k"] / 1000
            )
            benchmark_values["paid_clicks"].append(
                level_benchmarks["paid_clicks_per_1k"] / 1000
            )
            benchmark_values["paid_engagements"].append(
                level_benchmarks["paid_engagements_per_1k"] / 1000
            )

    return {
        metric_key: _valid_benchmark_values(values)
        for metric_key, values in benchmark_values.items()
    }


def calculate_benchmark_summary(values: list[float]) -> dict[str, float] | None:
    """Calculate min, max, average, and median for one benchmark series."""
    cleaned = _valid_benchmark_values(values)
    if not cleaned:
        return None
    return {
        "min": min(cleaned),
        "max": max(cleaned),
        "average": mean(cleaned),
        "median": median(cleaned),
    }


def calculate_metric_estimates(
    inputs: dict[str, Any],
    benchmarks: dict[str, list[float]] | None = None,
) -> dict[str, Any]:
    """Calculate Excel-style Metrics estimates from current inputs."""
    if benchmarks is None:
        summaries = {
            metric_key: {
                summary_key: float(summary_value)
                for summary_key, summary_value in summary.items()
                if summary_key != "per_1k"
            }
            for metric_key, summary in METRIC_CALCULATOR_BENCHMARKS.items()
        }
    else:
        benchmark_values = benchmarks
        summaries = {
            metric_key: calculate_benchmark_summary(values)
            for metric_key, values in benchmark_values.items()
        }
    if any(summary is None for summary in summaries.values()):
        return {"summaries": summaries, "estimates": None}

    total_influencers = _number(inputs, "total_influencers")
    paid_impressions_spend = _number(inputs, "paid_impressions_spend")
    paid_clicks_spend = _number(inputs, "paid_clicks_spend")
    paid_engagements_spend = _number(inputs, "paid_engagements_spend")

    estimated_organic_impressions = (
        total_influencers * summaries["organic_impressions"]["average"]
    )
    estimated_paid_impressions = (
        paid_impressions_spend * (summaries["paid_impressions"]["average"] / 1000)
    )
    estimated_engagements = total_influencers * summaries["engagements"]["average"]
    estimated_paid_clicks = paid_clicks_spend * (
        summaries["paid_clicks"]["average"] / 1000
    )
    estimated_paid_engagements = (
        paid_engagements_spend * (summaries["paid_engagements"]["average"] / 1000)
    )

    estimates = {
        "organic_impressions": estimated_organic_impressions,
        "paid_impressions": estimated_paid_impressions,
        "engagements": estimated_engagements,
        "paid_clicks": estimated_paid_clicks,
        "paid_engagements": estimated_paid_engagements,
        "total_impressions": (
            estimated_organic_impressions + estimated_paid_impressions
        ),
        "total_engagement_actions": (
            estimated_engagements
            + estimated_paid_clicks
            + estimated_paid_engagements
        ),
    }
    return {"summaries": summaries, "estimates": estimates}
