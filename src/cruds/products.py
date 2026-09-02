"""CRUD operations for products."""

from __future__ import annotations

import re
import uuid
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.product import (
    Category,
    Product,
    ProductCharacteristic,
    ProductImage,
    ProductStatus,
)
from src.models.sku import SKU
from src.schemas.errors import ErrorCode
from src.schemas.product import ProductCreate


def _make_slug(title: str) -> str:
    """Build a non-empty unique slug from title (required by response contract)."""
    raw = title.lower().strip()
    raw = re.sub(r"[^\w\s-]", "", raw, flags=re.UNICODE)
    raw = re.sub(r"[-\s]+", "-", raw).strip("-")
    base = raw[:150] if raw else "product"
    return f"{base}-{uuid.uuid4().hex[:8]}"


async def create_product(
    product_create: ProductCreate,
    seller_id: UUID,
    db: AsyncSession,
) -> Product:
    """
    Create a product **card only** (US-B2B-01 / B2B-1).

    - seller_id from caller (JWT / X-Seller-Id), never from body.
    - status always CREATED; no moderation event.
    - category_id must exist (checked before insert).
    - images (≥1) and optional characteristics are stored.
    - SKUs are NOT created here — only via POST /api/v1/skus (B2B-2).
    """
    if not product_create.images:
        raise HTTPException(
            status_code=400,
            detail={
                "code": ErrorCode.VALIDATION_ERROR,
                "message": "At least one image is required",
                "details": {"field": "images"},
            },
        )

    category = await db.get(Category, product_create.category_id)
    if category is None:
        raise HTTPException(
            status_code=400,
            detail={
                "code": ErrorCode.INVALID_CATEGORY,
                "message": (
                    f"Category with id={product_create.category_id} does not exist"
                ),
                "details": {"field": "category_id"},
            },
        )

    db_product = Product(
        id=uuid.uuid4(),
        title=product_create.title,
        description=product_create.description,
        category_id=product_create.category_id,
        seller_id=seller_id,
        status=ProductStatus.CREATED,
        slug=_make_slug(product_create.title),
        deleted=False,
    )
    db.add(db_product)
    await db.flush()

    for img_data in product_create.images:
        db.add(
            ProductImage(
                id=uuid.uuid4(),
                product_id=db_product.id,
                url=img_data.url,
                ordering=img_data.ordering,
            )
        )

    for char_data in product_create.characteristics:
        db.add(
            ProductCharacteristic(
                id=uuid.uuid4(),
                product_id=db_product.id,
                name=char_data.name,
                value=char_data.value,
            )
        )

    # Explicitly: do not create any SKU rows here.
    await db.commit()

    result = await db.execute(
        select(Product)
        .where(Product.id == db_product.id)
        .options(
            selectinload(Product.images),
            selectinload(Product.characteristics),
            selectinload(Product.skus).selectinload(SKU.characteristics),
        )
    )
    product = result.scalar_one()
    # Guarantee empty SKU list on a freshly created card
    assert list(product.skus) == [] or len(list(product.skus)) == 0
    return product
