"""Pydantic schemas for moderation events."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field


class ModerationEventRequest(BaseModel):
    """
    Schema for receiving moderation events from Moderation Service.
    Matches B2B OpenAPI: ModerationEventRequest.
    """

    idempotency_key: str = Field(..., description="Idempotency key, TTL 24h")
    product_id: UUID
    event_type: str = Field(..., description="MODERATED or BLOCKED")
    moderator_id: Optional[str] = None
    moderator_comment: Optional[str] = None
    blocking_reason_id: Optional[UUID] = None
    blocking_reason: Optional[str] = None
    hard_block: bool = False
    field_reports: Optional[list] = None
    occurred_at: datetime = Field(..., description="Event occurrence timestamp")


class ModerationEventResponse(BaseModel):
    """Response for accepted moderation event."""

    product_id: UUID
    event_type: str
    status: str = "accepted"


class ProductApproveRequest(BaseModel):
    """
    Request body for product approval endpoint.
    Matches Moderation OpenAPI approve endpoint optional comment.
    """

    comment: Optional[str] = Field(None, max_length=2000)


class ProductApproveResponse(BaseModel):
    """Response for approved product."""

    product_id: UUID
    status: str
    seller_id: UUID
    approved_at: datetime
    approved_by: Optional[str] = None
    comment: Optional[str] = None


# Re-export unified flat error contract (single format for the whole service)
from src.schemas.errors import ErrorResponse  # noqa: E402, F401
