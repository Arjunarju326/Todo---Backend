"""DRF throttle classes for Niva chat / search endpoints."""

from __future__ import annotations

from rest_framework.throttling import UserRateThrottle


class NivaChatThrottle(UserRateThrottle):
    scope = "niva_chat"


class NivaSearchThrottle(UserRateThrottle):
    scope = "niva_search"
