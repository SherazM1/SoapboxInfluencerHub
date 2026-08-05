from __future__ import annotations

from app.campaign_ops.ui.formatting import readable_label


BADGE_LABELS = {
    "active": "Active",
    "inactive": "Inactive",
    "archived": "Archived",
    "planning": "Planning",
    "live": "Live",
    "recapping": "Recapping",
    "complete": "Complete",
    "completed": "Complete",
    "cancelled": "Cancelled",
    "paused": "Paused",
    "on_hold": "On Hold",
    "needs_attention": "Needs Attention",
    "at_risk": "High Risk",
    "overdue": "Overdue",
    "waiting": "Waiting",
    "ready_for_recap": "Ready for Recap",
    "ready_to_close": "Ready to Close",
    "delivered": "Delivered",
    "approved": "Approved",
    "rejected": "Rejected",
    "draft": "Draft",
    "not_started": "Not Started",
    "in_progress": "In Progress",
}


def status_label(value: str | None) -> str:
    if not value:
        return "Not set"
    return BADGE_LABELS.get(str(value), readable_label(value))


def badge_text(value: str | None) -> str:
    return f"[{status_label(value)}]"

