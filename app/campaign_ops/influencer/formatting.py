from __future__ import annotations


from app.campaign_ops.formatting import title_label


def status_label(value: str | None) -> str:
    return title_label(value)
