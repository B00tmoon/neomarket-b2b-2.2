from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.base import get_db
from src.models.product import Product, ProductStatus
from src.models.sku import SKU
from src.schemas.product import (
    ProductCreate,
    ProductResponse,
    ProductStatusEnum,
    ProductUpdate,
)

router = APIRouter()


def _parse_seller_id(request: Request) -> UUID | None:
    """Extract seller_id from JWT / request.state.user / X-Seller-Id as UUID."""
    seller_id = getattr(request.state, "user", None)
    if seller_id is None:
        seller_id = request.headers.get("X-Seller-Id")
    if seller_id is None:
        return None
    try:
        return UUID(str(seller_id))
    except (ValueError, TypeError, AttributeError):
        return None


def _check_hard_blocked(product: Product) -> None:
    """Raise 403 if product is HARD_BLOCKED."""
    if product.status == ProductStatus.HARD_BLOCKED:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "PRODUCT_HARD_BLOCKED",
                "message": "Product is HARD_BLOCKED — modification is forbidden",
                "details": {"field": "status"},
            },
        )


@router.post("/products", response_model=ProductResponse, status_code=201)
async def create_product(
    product_data: ProductCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ProductResponse:
    """
    Create a product card only (US-B2B-01 / B2B-1).

    seller_id is taken from JWT / request.state.user / X-Seller-Id — never from body.
    Body: title (1-255), description (1-5000), category_id, images (≥1),
    optional characteristics. SKUs are NOT accepted and NOT created
    (use POST /api/v1/skus). On success: status=CREATED, skus=[], HTTP 201.
    """
    seller_id = _parse_seller_id(request)
    if seller_id is None:
        raw = getattr(request.state, "user", None) or request.headers.get("X-Seller-Id")
        if raw is None:
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "UNAUTHORIZED",
                    "message": "JWT token required",
                },
            )
        raise HTTPException(
            status_code=401,
            detail={
                "code": "UNAUTHORIZED",
                "message": "Invalid JWT seller_id (must be UUID)",
            },
        )

    from src.cruds.products import create_product as crud_create_product

    db_product = await crud_create_product(product_data, seller_id, db)
    return db_product


@router.get("/products", response_model=List[ProductResponse])
async def list_products(
    request: Request,
    seller_id: Optional[UUID] = Query(None, description="Фильтр по продавцу"),
    x_service_key: Optional[str] = Header(None, alias="X-Service-Key"),
    status: Optional[ProductStatusEnum] = Query(None, description="Фильтр по статусу"),
    category_id: Optional[UUID] = Query(None, description="Фильтр по категории"),
    ids: Optional[str] = Query(
        None, description="Batch IDs for B2C catalog, comma-separated UUIDs"
    ),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """
    GET /products with two modes:
    - Seller mode (with JWT/X-Seller-Id): full view
    - B2C catalog mode (X-Service-Key): only visible MODERATED in stock products
    """
    service_key = request.headers.get("X-Service-Key")
    is_catalog_mode = bool(service_key and service_key == "b2c-service-key")

    if is_catalog_mode and not service_key:
        raise HTTPException(status_code=401, detail={"code": "MISSING_SERVICE_KEY"})

    query = select(Product).where(Product.deleted == False)  # noqa: E712

    if is_catalog_mode:
        query = query.where(Product.status == ProductStatus.MODERATED)
    elif seller_id:
        query = query.where(Product.seller_id == seller_id)
    if status and not is_catalog_mode:
        query = query.where(Product.status == ProductStatus(status.value))
    if category_id:
        query = query.where(Product.category_id == category_id)

    if ids:
        id_list: list[UUID] = []
        for part in ids.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                id_list.append(UUID(part))
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail={"code": "INVALID_ID", "message": f"Invalid UUID: {part}"},
                )
        query = query.where(Product.id.in_(id_list))

    query = query.offset((page - 1) * size).limit(size)

    result = await db.execute(query)
    return result.scalars().all()


@router.post("/products/batch")
async def get_products_batch(
    product_ids: list[UUID], db: AsyncSession = Depends(get_db)
):
    """Получить несколько товаров по списку UUID (batch запрос для B2C)."""
    products = await db.execute(select(Product).where(Product.id.in_(product_ids)))
    product_list = products.scalars().all()

    result = {}
    for product in product_list:
        min_price = min([sku.price for sku in product.skus], default=0)
        result[str(product.id)] = {
            "product_id": str(product.id),
            "title": product.title,
            "description": product.description,
            "category_id": str(product.category_id),
            "status": product.status.value,
            "main_image_url": product.images[0].url if product.images else "",
            "images": [img.url for img in product.images],
            "min_price": min_price,
            "is_available": product.status == ProductStatus.MODERATED
            and not product.deleted,
            "characteristics": {
                char.name: char.value for char in product.characteristics
            },
            "skus": [
                {
                    "sku_id": str(sku.id),
                    "sku_code": sku.sku_code,
                    "name": sku.name,
                    "price": sku.price,
                    "active_quantity": sku.active_quantity,
                    "blocked_quantity": sku.blocked_quantity,
                    "active": sku.active,
                    "characteristics": [
                        {"name": c.name, "value": c.value} for c in sku.characteristics
                    ],
                }
                for sku in product.skus
            ],
        }
    return result


@router.get("/products/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: UUID, request: Request, db: AsyncSession = Depends(get_db)
):
    """
    Получить товар по UUID с IDOR защитой (для продавца).
    Для BLOCKED возвращает blocking_reason и field_reports.
    """
    seller_id = _parse_seller_id(request)

    result = await db.get(Product, product_id)
    if not result or result.deleted:
        raise HTTPException(status_code=404, detail="Product not found")

    if seller_id and result.seller_id != seller_id:
        raise HTTPException(status_code=404, detail="Product not found")

    return result


@router.put("/products/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: UUID,
    product_update: ProductUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Обновить товар."""
    db_product = await db.get(Product, product_id)
    if not db_product or db_product.deleted:
        raise HTTPException(status_code=404, detail="Product not found")

    _check_hard_blocked(db_product)

    update_data = product_update.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_product, field, value)

    await db.commit()
    await db.refresh(db_product)
    return db_product


@router.post("/products/{product_id}/submit-moderation", status_code=204)
async def submit_for_moderation(
    product_id: UUID, db: AsyncSession = Depends(get_db)
):
    """Отправить товар на модерацию."""
    db_product = await db.get(Product, product_id)
    if not db_product or db_product.deleted:
        raise HTTPException(status_code=404, detail="Product not found")

    _check_hard_blocked(db_product)

    if db_product.status != ProductStatus.CREATED:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot submit product with status {db_product.status.value}",
        )

    db_product.status = ProductStatus.ON_MODERATION
    await db.commit()
    return None


@router.post("/products/{product_id}/delete", status_code=204)
async def delete_product(product_id: UUID, db: AsyncSession = Depends(get_db)):
    """Удалить товар (мягкое удаление)."""
    db_product = await db.get(Product, product_id)
    if not db_product or db_product.deleted:
        raise HTTPException(status_code=404, detail="Product not found")

    _check_hard_blocked(db_product)

    db_product.deleted = True
    await db.commit()
    return None
