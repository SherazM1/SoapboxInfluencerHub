from __future__ import annotations


from app.campaign_ops.formatting import title_label


def retail_status_label(value: str | None) -> str:
    return title_label(value)


def channel_mix_label(values: list[str] | tuple[str, ...] | None) -> str:
    return ", ".join(values) if values else "-"
