from __future__ import annotations


class CampaignOpsError(Exception):
    """Base exception for Campaign Operations failures."""


class CampaignOpsDatabaseError(CampaignOpsError):
    """Raised when Campaign Operations persistence fails."""


class CampaignOpsValidationError(CampaignOpsError):
    """Raised when Campaign Operations input is invalid."""


class CampaignOpsPermissionError(CampaignOpsError):
    """Raised when a user cannot perform an operation."""


class CampaignOpsNotFoundError(CampaignOpsError):
    """Raised when a requested Campaign Operations record is missing."""
