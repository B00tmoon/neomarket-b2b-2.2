"""Routes for moderation events and product approval."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.base import get_db
from src.models.product import Product, ProductStatus
from src.models.sku import SKU
from src.schemas.moderation import (
    ModerationEventRequest,
    ModerationEventResponse,
    ProductApproveRequest,
    ProductApproveResponse,
    ErrorResponse,
)
from src.services.moderation import (
    ModerationService,
    ModeratorApproveService,
    ProductNotFoundError,
    ProductWrongStatusError,
    ProductNoSKUError,
    ProductAlreadyModeratedError,
    ModerationEventError,
)

router = APIRouter()
approve_router = APIRouter()


def _get_moderation_service() -> ModerationService:
    return ModerationService()


def _get_approve_service() -> ModeratorApproveService:
    return ModeratorApproveService()


# ──────────────────────── /moderation/events ────────────────────────


@router.post(
    "/moderation/events",
    status_code=204,
    responses={
        400: {"model": ErrorResponse, "description": "Invalid event payload"},
        401: {"model": ErrorResponse, "description": "Unauthorized"},
        409: {"model": ErrorResponse, "description": "Duplicate event"},
    },
)
async def receive_moderation_event(
    event: ModerationEventRequest,
    x_service_key: str = Header(..., alias="X-Service-Key"),
    db: AsyncSession = Depends(get_db),
):
    """
    Receive moderation events from Moderation Service.
    Implements B2B OpenAPI: POST /api/v1/moderation/events

    Events accepted:
    - MODERATED → product transitions ON_MODERATION → MODERATED
    - BLOCKED → product transitions ON_MODERATION → BLOCKED/HARD_BLOCKED

    Idempotent by idempotency_key (TTL 24h).
    Requires X-Service-Key header.
    """
    # Validate X-Service-Key
    if (
        not x_service_key or x_service_key != "b2b-moderation-key"
    ):  # from env in production
        raise HTTPException(
            status_code=401,
            detail={
                "code": "INVALID_SERVICE_KEY",
                "message": "X-Service-Key is required and must be valid",
            },
        )

    service = _get_moderation_service()

    try:
        if event.event_type == "MODERATED":
            product = await service.process_moderated_event(
                db=db,
                product_id=event.product_id,
                idempotency_key=event.idempotency_key,
                moderator_id=event.moderator_id,
                moderator_comment=event.moderator_comment,
            )
            # Push to B2C catalog so product becomes visible
            await service.push_to_b2c_catalog(
                product_id=event.product_id,
                idempotency_key=event.idempotency_key,
            )
            # 204 No Content for success

        elif event.event_type == "BLOCKED":
            product = await service.process_blocked_event(
                db=db,
                product_id=event.product_id,
                idempotency_key=event.idempotency_key,
                hard_block=event.hard_block,
                blocking_reason=event.blocking_reason,
                moderator_comment=event.moderator_comment,
                field_reports=event.field_reports,
            )
            # 204 No Content for success

        elif event.event_type == "EDITED":
            # For HARD_BLOCKED, ignore silently (idempotent)
            product = await db.get(Product, event.product_id)
            if product and product.status == ProductStatus.HARD_BLOCKED:
                pass  # ignore, success 204
            else:
                # Let other logic handle if needed
                pass

        else:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "UNKNOWN_EVENT_TYPE",
                    "message": f"Unknown event type: {event.event_type}",
                },
            )

    except (ProductNotFoundError, ProductWrongStatusError, ProductNoSKUError) as e:
        raise HTTPException(
            status_code=e.status_code, detail={"code": e.code, "message": e.message}
        )
    except ProductAlreadyModeratedError as e:
        # Already moderated — idempotent success (204 No Content)
        pass
    except ModerationEventError as e:
        raise HTTPException(
            status_code=e.status_code, detail={"code": e.code, "message": e.message}
        )


# ──────────────────────── /products/{product_id}/approve ────────────────────────


@approve_router.post(
    "/products/{product_id}/approve",
    response_model=ProductApproveResponse,
    status_code=200,
    responses={
        403: {"model": ErrorResponse, "description": "Forbidden — not your product"},
        409: {
            "model": ErrorResponse,
            "description": "Conflict — wrong status or no SKU",
        },
        404: {"model": ErrorResponse, "description": "Product not found"},
    },
)
async def approve_product(
    product_id: UUID,
    body: ProductApproveRequest = ProductApproveRequest(),
    seller_id: UUID | None = None,  # from auth context in real system
    db: AsyncSession = Depends(get_db),
) -> ProductApproveResponse:
    """
    Approve a product: ON_MODERATION → MODERATED.

    Validates:
    - Product belongs to the seller (IDOR prevention).
    - Product is in ON_MODERATION status.
    - Product has at least one active SKU.

    After approval:
    - Product status becomes MODERATED.
    - MODERATED event is pushed to B2C catalog.
    """
    service = _get_approve_service()

    try:
        product = await service.approve_product(
            db=db,
            product_id=product_id,
            moderator_id=0,  # not used in B2B approve
            seller_id=seller_id,
            comment=body.comment,
        )
        await service.push_to_b2c_catalog(product_id)

        return ProductApproveResponse(
            product_id=product.id,
            status=product.status.value,
            seller_id=product.seller_id,
            approved_at=datetime.now(timezone.utc),
            comment=body.comment,
        )

    except ProductNotFoundError as e:
        raise HTTPException(
            status_code=e.status_code, detail={"code": e.code, "message": e.message}
        )
    except ModerationEventError as e:
        if e.status_code == 403:
            raise HTTPException(
                status_code=403, detail={"code": e.code, "message": e.message}
            )
        raise HTTPException(
            status_code=e.status_code, detail={"code": e.code, "message": e.message}
        )
