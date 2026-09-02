from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from src.models.base import Base


class SKU(Base):
    __tablename__ = "skus"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    product_id = Column(
        UUID(as_uuid=True),
        ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Internal unique code (auto-generated if not provided by API)
    sku_code = Column(String(100), nullable=False, unique=True, index=True)
    name = Column(String(200), nullable=False)
    price = Column(Integer, nullable=False)  # sale price, kopecks, > 0
    cost_price = Column(Integer, nullable=False, server_default="0")  # cost, kopecks
    discount = Column(Integer, nullable=False, server_default="0")  # absolute discount, kopecks
    image = Column(String(500), nullable=False, server_default="")  # SKU photo URL
    active_quantity = Column(Integer, default=0, nullable=False, server_default="0")
    blocked_quantity = Column(Integer, default=0, nullable=False, server_default="0")  # reserved
    active = Column(Boolean, default=True, nullable=False, server_default="true")

    characteristics = relationship(
        "SKUCharacteristic", back_populates="sku", cascade="all, delete-orphan"
    )
    product = relationship("Product", back_populates="skus")

    def __repr__(self) -> str:
        return (
            f"<SKU(id={self.id}, code='{self.sku_code}', "
            f"price={self.price}, qty={self.active_quantity})>"
        )


class SKUCharacteristic(Base):
    __tablename__ = "sku_characteristics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    sku_id = Column(
        UUID(as_uuid=True),
        ForeignKey("skus.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = Column(String(200), nullable=False)
    value = Column(String(500), nullable=False)

    sku = relationship("SKU", back_populates="characteristics")

    def __repr__(self) -> str:
        return (
            f"<SKUCharacteristic(sku_id={self.sku_id}, "
            f"name='{self.name}', value='{self.value}')>"
        )
