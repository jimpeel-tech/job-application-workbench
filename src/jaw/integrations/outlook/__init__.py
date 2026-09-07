"""Outlook/Microsoft Graph integration for Job Application Workbench."""

from .auth import OutlookAuth
from .classifier import OutlookEmailClassifier
from .graph import JAW_CATEGORIES, OutlookGraphClient
from .service import OutlookSyncService, transition_for

__all__ = [
    "JAW_CATEGORIES",
    "OutlookAuth",
    "OutlookEmailClassifier",
    "OutlookGraphClient",
    "OutlookSyncService",
    "transition_for",
]
