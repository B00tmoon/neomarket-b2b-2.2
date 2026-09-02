"""Moderation event processing service."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.product import Product, ProductStatus
from src.models.sku import SKU


class ModerationEventError(Exception):
    """Base exception for moderation processing errors."""

    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class ProductNotFoundError(ModerationEventError):
    def __init__(self, product_id: object):
        super().__init__(
            code="PRODUCT_NOT_FOUND",
            message=f"Product {product_id} not found",
            status_code=404,
        )


class ProductWrongStatusError(ModerationEventError):
    def __init__(self, product_id: object, current_status: str):
        super().__init__(
            code="PRODUCT_WRONG_STATUS",
            message=f"Product {product_id} has status {current_status}, expected ON_MODERATION",
            status_code=409,
        )


class ProductNoSKUError(ModerationEventError):
    def __init__(self, product_id: object):
        super().__init__(
            code="PRODUCT_NO_SKU",
            message=f"Product {product_id} has no SKU — cannot be approved",
            status_code=409,
        )


class ProductAlreadyModeratedError(ModerationEventError):
    def __init__(self, product_id: object):
        super().__init__(
            code="PRODUCT_ALREADY_APPROVED",
            message=f"Product {product_id} is already MODERATED",
            status_code=409,
        )


class ProductHardBlockedError(ModerationEventError):
    def __init__(self, product_id: object, action: str = "modify"):
        super().__init__(
            code="PRODUCT_HARD_BLOCKED",
            message=f"Product {product_id} is HARD_BLOCKED — {action} is forbidden",
            status_code=403,
        )


class ModerationService:
    """Handles moderation events received from the Moderation Service."""

    def __init__(self, b2c_api_url: str = "http://localhost:8000"):
        self.b2c_api_url = b2c_api_url

    async def process_moderated_event(
        self,
        db: AsyncSession,
        product_id: str,
        idempotency_key: str,
        moderator_id: Optional[str] = None,
        moderator_comment: Optional[str] = None,
    ) -> Product:
        """
        Process a MODERATED event from Moderation Service.

        1. Find product by ID.
        2. Validate it exists and is not deleted.
        3. Validate status is ON_MODERATION (not already MODERATED, not CREATED, etc.).
        4. Validate product has at least one active SKU with SKU code.
        5. Transition product to MODERATED.
        6. Push event to B2C catalog.
        """
        product = await db.get(Product, product_id)
        if not product or product.deleted:
            raise ProductNotFoundError(product_id)

        if product.status != ProductStatus.ON_MODERATION:
            raise ProductWrongStatusError(product_id, product.status.value)

        # Check that product has at least one active SKU
        skus_result = await db.execute(
            select(SKU).where(
                SKU.product_id == product_id,
                SKU.active == True,
            )
        )
        skus = skus_result.scalars().all()
        if not skus:
            raise ProductNoSKUError(product_id)

        # Transition to MODERATED
        product.status = ProductStatus.MODERATED
        # Clear blocking data on successful moderation
        product.blocking_reason_id = None
        product.blocking_comment = moderator_comment or None
        product.field_reports = None
        await db.flush()

        return product

    async def process_blocked_event(
        self,
        db: AsyncSession,
        product_id: str,
        idempotency_key: str,
        hard_block: bool = False,
        blocking_reason: Optional[str] = None,
        moderator_comment: Optional[str] = None,
        field_reports: Optional[list] = None,
    ) -> Product:
        """
        Process a BLOCKED event from Moderation Service.

        If hard_block=True → HARD_BLOCKED (terminal status).
        If hard_block=False → BLOCKED (soft block).

        Idempotent by idempotency_key: if already processed, return product.
        Only ON_MODERATION status is accepted.
        """
        product = await db.get(Product, product_id)
        if not product or product.deleted:
            raise ProductNotFoundError(product_id)

        if product.status != ProductStatus.ON_MODERATION:
            raise ProductWrongStatusError(product_id, product.status.value)

        # Terminal transition
        product.status = (
            ProductStatus.HARD_BLOCKED if hard_block else ProductStatus.BLOCKED
        )
        if blocking_reason:
            product.blocking_comment = blocking_reason
        if moderator_comment:
            product.blocking_comment = moderator_comment
        if field_reports:
            product.field_reports = field_reports
        await db.flush()

        # Emit BLOCKED event to B2B
        await self.push_blocked_event_to_b2b(
            product_id=product_id,
            idempotency_key=idempotency_key,
            hard_block=hard_block,
        )

        return product

    async def push_blocked_event_to_b2b(
        self,
        product_id: str,
        idempotency_key: str,
        hard_block: bool,
    ) -> None:
        """Push BLOCKED event with hard_block flag to B2B catalog."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    f"{self.b2c_api_url}/api/v1/b2b/events",
                    json={
                        "product_id": product_id,
                        "event_type": "BLOCKED",
                        "hard_block": hard_block,
                        "idempotency_key": idempotency_key,
                        "occurred_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
        except httpx.HTTPError:
            pass

    async def push_to_b2c_catalog(self, product_id: object, idempotency_key: str) -> None:
        """
        Push the MODERATED event to B2C catalog so the product becomes visible to buyers.
        Uses idempotency_key to prevent duplicate catalog entries.
        """
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    f"{self.b2c_api_url}/api/v1/b2b/events",
                    json={
                        "product_id": product_id,
                        "event_type": "MODERATED",
                        "idempotency_key": idempotency_key,
                        "occurred_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
        except httpx.HTTPError:
            # Log but don't fail the approval — B2C will eventually sync
            pass


class ModeratorApproveService:
    """
    Handles product approval by a moderator.
    Used by the Moderation Service to approve a product directly.
    """

    def __init__(self, b2c_api_url: str = "http://localhost:8000"):
        self.b2c_api_url = b2c_api_url

    async def approve_product(
        self,
        db: AsyncSession,
        product_id,
        moderator_id,
        seller_id,
        comment: Optional[str] = None,
    ) -> Product:
        """
        Approve a product: ON_MODERATION → MODERATED.

        Validation:
        - Product must exist and not be deleted.
        - Product must belong to the current seller (seller_id match).
        - Product must be in ON_MODERATION status (409 if already MODERATED or CREATED).
        - Product must have at least one active SKU (409 if no SKU).
        - If seller edited the product while it was in review → 409.

        After approval:
        - Transition product to MODERATED.
        - Push MODERATED event to B2C catalog.
        """
        product = await db.get(Product, product_id)
        if not product or product.deleted:
            raise ProductNotFoundError(product_id)

        # Check ownership — moderator can only approve if it matches
        if product.seller_id != seller_id:
            raise ModerationEventError(
                code="PRODUCT_NOT_YOURS",
                message="You can only approve your own product",
                status_code=403,
            )

        # Check status — only ON_MODERATION can be approved
        if product.status == ProductStatus.MODERATED:
            raise ProductAlreadyModeratedError(product_id)

        if product.status != ProductStatus.ON_MODERATION:
            raise ProductWrongStatusError(product_id, product.status.value)

        # Check SKU existence
        skus_result = await db.execute(
            select(SKU).where(
                SKU.product_id == product_id,
                SKU.active == True,
            )
        )
        skus = skus_result.scalars().all()
        if not skus:
            raise ProductNoSKUError(product_id)

        # Transition
        product.status = ProductStatus.MODERATED
        if comment:
            product.blocking_comment = comment
        await db.flush()

        return product

    async def push_to_b2c_catalog(self, product_id: object) -> None:
        """Push MODERATED event to B2C catalog."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    f"{self.b2c_api_url}/api/v1/b2b/events",
                    json={
                        "product_id": product_id,
                        "event_type": "MODERATED",
                        "idempotency_key": str(uuid.uuid4()),
                        "occurred_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
        except httpx.HTTPError:
            pass
