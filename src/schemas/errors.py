"""Unified flat error response for the whole service.

All unsuccessful responses (validation, domain, auth) use this shape:

    {"code": "VALIDATION_ERROR", "message": "...", "details": {...} | null}

Never wrap under FastAPI's default ``{"detail": ...}``.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    """Single flat error contract for every non-2xx response."""

    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")
    details: Optional[dict[str, Any]] = Field(
        None, description="Optional structured context (field, errors, …)"
    )


# Canonical error codes used across the service
class ErrorCode:
    VALIDATION_ERROR = "VALIDATION_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    CONFLICT = "CONFLICT"
    INVALID_CATEGORY = "INVALID_CATEGORY"
    PRODUCT_HARD_BLOCKED = "PRODUCT_HARD_BLOCKED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
