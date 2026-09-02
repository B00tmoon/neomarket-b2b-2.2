from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProductStatusEnum(str, Enum):
    CREATED = "CREATED"
    ON_MODERATION = "ON_MODERATION"
    MODERATED = "MODERATED"
    BLOCKED = "BLOCKED"
    HARD_BLOCKED = "HARD_BLOCKED"


class ProductImageBase(BaseModel):
    url: str = Field(..., min_length=1, max_length=500, description="Image URL (S3 path or URI)")
    ordering: int = Field(..., ge=0, description="Display order (0 = main photo)")


class ProductImageCreate(ProductImageBase):
    pass


class ProductImageResponse(ProductImageBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID


class ProductCharacteristicBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    value: str = Field(..., min_length=1, max_length=500)


class ProductCharacteristicCreate(ProductCharacteristicBase):
    pass


class ProductCharacteristicResponse(ProductCharacteristicBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID


class SKUCharacteristicValue(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    value: str = Field(..., min_length=1, max_length=500)


class SKUCreate(BaseModel):
    """Request body for POST /api/v1/skus (B2B-2 canon)."""

    product_id: UUID = Field(..., description="Product this SKU belongs to")
    name: str = Field(..., min_length=1, max_length=255)
    price: int = Field(..., gt=0, description="Sale price in kopecks, must be > 0")
    cost_price: int = Field(..., gt=0, description="Cost price in kopecks, must be > 0")
    discount: int = Field(0, ge=0, description="Absolute discount in kopecks")
    image: str = Field(..., min_length=1, max_length=500, description="SKU photo URL")
    characteristics: List[SKUCharacteristicValue] = Field(default_factory=list)

    @field_validator("name", "image")
    @classmethod
    def strip_non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be empty or whitespace-only")
        return v


class SKUResponse(BaseModel):
    """Response for created/fetched SKU — matches B2B-2 Response 201."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    name: str
    price: int
    cost_price: int = 0
    discount: int = 0
    image: str = ""
    active_quantity: int = 0
    reserved_quantity: int = 0
    characteristics: List[SKUCharacteristicValue] = []

    @classmethod
    def from_orm_sku(cls, sku: object) -> "SKUResponse":
        chars = [
            SKUCharacteristicValue(name=c.name, value=c.value)
            for c in (getattr(sku, "characteristics", None) or [])
        ]
        return cls(
            id=sku.id,
            product_id=sku.product_id,
            name=sku.name,
            price=sku.price,
            cost_price=int(getattr(sku, "cost_price", 0) or 0),
            discount=int(getattr(sku, "discount", 0) or 0),
            image=str(getattr(sku, "image", "") or ""),
            active_quantity=int(getattr(sku, "active_quantity", 0) or 0),
            reserved_quantity=int(getattr(sku, "blocked_quantity", 0) or 0),
            characteristics=chars,
        )


class ProductCreate(BaseModel):
    """Request body for POST /api/v1/products (B2B-1 canon).

    Allowed fields only (extra forbidden):
      title (1-255), description (1-5000), category_id, images (≥1),
      characteristics (optional).

    seller_id is NEVER accepted from body (JWT / X-Seller-Id).
    skus are NEVER accepted here — use POST /api/v1/skus (B2B-2).
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Product title, 1-255 characters",
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Product description, 1-5000 characters",
    )
    category_id: UUID = Field(..., description="Category ID (UUID) is required")
    images: List[ProductImageCreate] = Field(
        ...,
        min_length=1,
        description="At least one image is required",
    )
    characteristics: List[ProductCharacteristicCreate] = Field(default_factory=list)

    @field_validator("title", "description")
    @classmethod
    def strip_non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be empty or whitespace-only")
        return v


class ProductUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, min_length=1, max_length=5000)
    category_id: Optional[UUID] = None


class ProductResponse(BaseModel):
    """Full product response — required fields always present after create.

    Spec-required non-null fields: id, seller_id, title, description,
    category_id, status, slug, images, created_at.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    seller_id: UUID
    title: str
    description: str
    category_id: UUID
    status: str
    slug: str
    images: List[ProductImageResponse]
    characteristics: List[ProductCharacteristicResponse] = []
    skus: List[SKUResponse] = []
    created_at: datetime
    updated_at: Optional[datetime] = None
    deleted: bool = False
    blocking_comment: Optional[str] = None
    blocking_reason_id: Optional[UUID] = None
    moderator_comment: Optional[str] = None
    blocking_reason: Optional[dict] = None
    field_reports: Optional[list] = None
