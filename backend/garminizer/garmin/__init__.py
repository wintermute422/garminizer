"""Garmin Connect access: a read-only client wrapper and the token-based login flow."""

from garminizer.garmin.client import (
    READ_METHODS,
    GarminAuthError,
    GarminClient,
    GarminConnectionError,
    GarminError,
    GarminNotFoundError,
    GarminRateLimitError,
    GarminRequestError,
    Identity,
    MethodNotAllowedError,
)

__all__ = [
    "READ_METHODS",
    "GarminAuthError",
    "GarminClient",
    "GarminConnectionError",
    "GarminError",
    "GarminNotFoundError",
    "GarminRateLimitError",
    "GarminRequestError",
    "Identity",
    "MethodNotAllowedError",
]
