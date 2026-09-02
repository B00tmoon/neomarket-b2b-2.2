"""SKU routes — US-B2B-02: POST /api/v1/skus (canon B2B-2)."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.base import get_db
from src.models.product import Product, ProductStatus
from src.models.sku import SKU, SKUCharacteristic
from src.schemas.errors import ErrorCode
from src.schemas.product import SKUCreate, SKUResponse
from src.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()


def _parse_seller_id(request: Request) -> UUID | None:
    seller_id = getattr(request.state, "user", None)
    if seller_id is None:
        seller_id = request.headers.get("X-Seller-Id")
    if seller_id is None:
        return None
    try:
        return UUID(str(seller_id))
    except (ValueError, TypeError, AttributeError):
        return None


async def _emit_moderation_event(
    *,
    product_id: UUID,
    seller_id: UUID,
    event: str,
) -> None:
    """
    Fire-and-forget POST to Moderation Service.

    Canon payload:
      POST {moderation_url}/api/v1/events/product
      X-Service-Key: {b2b_to_mod_key}
      {idempotency_key, product_id, seller_id, event, date}
    """
    url = f"{settings.moderation_service_url.rstrip('/')}/api/v1/events/product"
    payload = {
        "idempotency_key": str(uuid.uuid4()),
        "product_id": str(product_id),
        "seller_id": str(seller_id),
        "event": event,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z",
    }
    headers = {"X-Service-Key": settings.b2b_to_mod_key}
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            logger.info(
                "moderation event %s for product %s → %s",
                event,
                product_id,
                resp.status_code,
            )
    except Exception as exc:  # noqa: BLE001 — fire-and-forget
        logger.warning(
            "failed to emit moderation event %s for product %s: %s",
            event,
            product_id,
            exc,
        )


@router.post("/skus", response_model=SKUResponse, status_code=201)
async def create_sku(
    body: SKUCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> SKUResponse:
    """
    POST /api/v1/skus — create a product variant (US-B2B-02 / B2B-2).

    Side effects (canon):
    - First SKU on CREATED product → status ON_MODERATION + event CREATED
    - SKU on MODERATED/BLOCKED product → status ON_MODERATION + event EDITED
    - HARD_BLOCKED → 403
    - Second+ SKU while already ON_MODERATION → no status change, no CREATED event
    """
    seller_id = _parse_seller_id(request)
    if seller_id is None:
        raise HTTPException(
            status_code=401,
            detail={
                "code": ErrorCode.UNAUTHORIZED,
                "message": "JWT token required",
            },
        )

    product = await db.get(Product, body.product_id)
    if product is None or product.deleted:
        raise HTTPException(
            status_code=404,
            detail={
                "code": ErrorCode.NOT_FOUND,
                "message": "Product not found",
            },
        )

    # IDOR: seller may only add SKUs to own products
    if product.seller_id != seller_id:
        raise HTTPException(
            status_code=404,
            detail={
                "code": ErrorCode.NOT_FOUND,
                "message": "Product not found",
            },
        )

    if product.status == ProductStatus.HARD_BLOCKED:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "FORBIDDEN",
                "message": "Cannot add SKU to hard-blocked product",
            },
        )

    # Count existing SKUs before insert
    existing = await db.execute(
        select(SKU).where(SKU.product_id == body.product_id)
    )
    existing_skus = list(existing.scalars().all())
    is_first_sku = len(existing_skus) == 0
    previous_status = product.status

    sku_id = uuid.uuid4()
    db_sku = SKU(
        id=sku_id,
        product_id=body.product_id,
        sku_code=f"SKU-{sku_id.hex[:12]}",
        name=body.name,
        price=body.price,
        cost_price=body.cost_price,
        discount=body.discount,
        image=body.image,
        active_quantity=0,
        blocked_quantity=0,
        active=True,
    )
    db.add(db_sku)
    await db.flush()

    for char in body.characteristics:
        db.add(
            SKUCharacteristic(
                id=uuid.uuid4(),
                sku_id=db_sku.id,
                name=char.name,
                value=char.value,
            )
        )

    emit_event: str | None = None

    if is_first_sku and previous_status == ProductStatus.CREATED:
        # First SKU on a draft product → submit to moderation
        product.status = ProductStatus.ON_MODERATION
        emit_event = "CREATED"
    elif previous_status in (ProductStatus.MODERATED, ProductStatus.BLOCKED):
        # Significant change → re-moderation (canon since 2026-05-27)
        product.status = ProductStatus.ON_MODERATION
        emit_event = "EDITED"
    # else: already ON_MODERATION (or CREATED with existing SKUs — edge) → no change

    await db.commit()

    # Reload with characteristics for response
    result = await db.execute(
        select(SKU)
        .where(SKU.id == db_sku.id)
        .options(selectinload(SKU.characteristics))
    )
    db_sku = result.scalar_one()

    if emit_event:
        await _emit_moderation_event(
            product_id=product.id,
            seller_id=product.seller_id,
            event=emit_event,
        )

    return SKUResponse.from_orm_sku(db_sku)


# ── remaining SKU utilities (reserve / batch) keep working ──────────────


@router.get("/skus/{sku_id}", response_model=SKUResponse)
async def get_sku(sku_id: UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SKU)
        .where(SKU.id == sku_id)
        .options(selectinload(SKU.characteristics))
    )
    sku = result.scalar_one_or_none()
    if not sku:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.NOT_FOUND, "message": "SKU not found"},
        )
    return SKUResponse.from_orm_sku(sku)


@router.post("/skus/{sku_id}/reserve")
async def reserve_sku(
    sku_id: UUID, quantity: int, db: AsyncSession = Depends(get_db)
):
    sku = await db.get(SKU, sku_id)
    if not sku:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.NOT_FOUND, "message": "SKU not found"},
        )
    if sku.active_quantity < quantity:
        raise HTTPException(
            status_code=400,
            detail={
                "code": ErrorCode.VALIDATION_ERROR,
                "message": (
                    f"Insufficient quantity. Available: {sku.active_quantity}, "
                    f"requested: {quantity}"
                ),
            },
        )
    sku.active_quantity -= quantity
    sku.blocked_quantity += quantity
    await db.commit()
    return {
        "sku_id": str(sku_id),
        "reserved": quantity,
        "remaining": sku.active_quantity,
    }


@router.post("/skus/{sku_id}/release")
async def release_sku(
    sku_id: UUID, quantity: int, db: AsyncSession = Depends(get_db)
):
    sku = await db.get(SKU, sku_id)
    if not sku:
        raise HTTPException(
            status_code=404,
            detail={"code": ErrorCode.NOT_FOUND, "message": "SKU not found"},
        )
    if sku.blocked_quantity < quantity:
        raise HTTPException(
            status_code=400,
            detail={
                "code": ErrorCode.VALIDATION_ERROR,
                "message": (
                    f"Cannot release more than reserved. "
                    f"Reserved: {sku.blocked_quantity}"
                ),
            },
        )
    sku.blocked_quantity -= quantity
    sku.active_quantity += quantity
    await db.commit()
    return {
        "sku_id": str(sku_id),
        "released": quantity,
        "active": sku.active_quantity,
    }


@router.post("/inventory/reserve")
async def reserve_stock(
    reservations: list[dict],
    x_service_key: str = Header(..., alias="X-Service-Key"),
    db: AsyncSession = Depends(get_db),
):
    if not x_service_key or x_service_key != "b2c-service-key":
        raise HTTPException(
            status_code=401,
            detail={
                "code": ErrorCode.UNAUTHORIZED,
                "message": "X-Service-Key is required",
            },
        )
    try:
        results = []
        for res in reservations:
            raw_id = res.get("sku_id")
            quantity = res.get("quantity", 1)
            try:
                sku_id = UUID(str(raw_id))
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": ErrorCode.VALIDATION_ERROR,
                        "message": f"Invalid sku_id UUID: {raw_id}",
                    },
                )
            sku = await db.get(SKU, sku_id, with_for_update=True)
            if not sku:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "code": ErrorCode.NOT_FOUND,
                        "message": f"SKU {sku_id} not found",
                    },
                )
            if sku.active_quantity < quantity:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "INSUFFICIENT_STOCK",
                        "message": "Partial insufficient - rollback",
                    },
                )
            sku.active_quantity -= quantity
            sku.blocked_quantity += quantity
            results.append(
                {
                    "sku_id": str(sku_id),
                    "reserved": quantity,
                    "remaining": sku.active_quantity,
                }
            )
        await db.commit()
        return {"success": results, "total_reserved": len(results)}
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail={"code": ErrorCode.INTERNAL_ERROR, "message": str(e)},
        )


@router.post("/inventory/unreserve")
async def unreserve_stock(
    unreservations: list[dict],
    x_service_key: str = Header(..., alias="X-Service-Key"),
    db: AsyncSession = Depends(get_db),
):
    if not x_service_key or x_service_key != "b2c-service-key":
        raise HTTPException(
            status_code=401,
            detail={
                "code": ErrorCode.UNAUTHORIZED,
                "message": "X-Service-Key is required",
            },
        )
    try:
        for unres in unreservations:
            raw_id = unres.get("sku_id")
            quantity = unres.get("quantity", 1)
            try:
                sku_id = UUID(str(raw_id))
            except (ValueError, TypeError):
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": ErrorCode.VALIDATION_ERROR,
                        "message": f"Invalid sku_id UUID: {raw_id}",
                    },
                )
            sku = await db.get(SKU, sku_id, with_for_update=True)
            if not sku:
                raise HTTPException(
                    status_code=404,
                    detail={
                        "code": ErrorCode.NOT_FOUND,
                        "message": f"SKU {sku_id} not found",
                    },
                )
            if sku.blocked_quantity < quantity:
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": ErrorCode.CONFLICT,
                        "message": "Insufficient reserved quantity",
                    },
                )
            sku.blocked_quantity -= quantity
            sku.active_quantity += quantity
        await db.commit()
        return {"status": "UNRESERVED", "unreserved_count": len(unreservations)}
    except HTTPException:
        await db.rollback()
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail={"code": ErrorCode.INTERNAL_ERROR, "message": str(e)},
        )
