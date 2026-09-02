from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.models.base import Base


class ProductStatus(str, enum.Enum):
    CREATED = "CREATED"
    ON_MODERATION = "ON_MODERATION"
    MODERATED = "MODERATED"
    BLOCKED = "BLOCKED"
    HARD_BLOCKED = "HARD_BLOCKED"


class Product(Base):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    seller_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(
        SQLEnum(ProductStatus, name="productstatus", create_constraint=True),
        default=ProductStatus.CREATED,
        nullable=False,
    )
    category_id = Column(
        UUID(as_uuid=True), ForeignKey("categories.id"), nullable=False
    )
    slug = Column(String(200), nullable=True)

    images = relationship(
        "ProductImage", back_populates="product", cascade="all, delete-orphan"
    )
    characteristics = relationship(
        "ProductCharacteristic", back_populates="product", cascade="all, delete-orphan"
    )
    skus = relationship("SKU", back_populates="product", cascade="all, delete-orphan")
    category = relationship("Category", back_populates="products")

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    deleted = Column(Boolean, default=False, nullable=False, server_default="false")

    blocking_reason_id = Column(
        UUID(as_uuid=True),
        ForeignKey("product_blocking_reasons.id"),
        nullable=True,
    )
    blocking_comment = Column(Text, nullable=True)
    field_reports = Column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<Product(id={self.id}, title='{self.title}', status={self.status.value})>"
        )


class ProductImage(Base):
    __tablename__ = "product_images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    url = Column(String(500), nullable=False)
    ordering = Column(Integer, default=0, server_default="0")

    product = relationship("Product", back_populates="images")

    def __repr__(self) -> str:
        return (
            f"<ProductImage(id={self.id}, product_id={self.product_id}, "
            f"ordering={self.ordering})>"
        )


class ProductCharacteristic(Base):
    __tablename__ = "product_characteristics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
    )
    name = Column(String(200), nullable=False)
    value = Column(String(500), nullable=False)

    product = relationship("Product", back_populates="characteristics")

    def __repr__(self) -> str:
        return (
            f"<ProductCharacteristic(product_id={self.product_id}, "
            f"name='{self.name}', value='{self.value}')>"
        )


class Category(Base):
    __tablename__ = "categories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("categories.id"), nullable=True)
    name = Column(String(200), nullable=False, unique=True)
    slug = Column(String(200), unique=True, nullable=False)

    parent = relationship("Category", remote_side="Category.id", backref="children")
    products = relationship("Product", back_populates="category")

    def __repr__(self) -> str:
        return f"<Category(id={self.id}, name='{self.name}', slug='{self.slug}')>"


class ProductBlockingReason(Base):
    __tablename__ = "product_blocking_reasons"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ProductBlockingReason(id={self.id}, name='{self.name}')>"
