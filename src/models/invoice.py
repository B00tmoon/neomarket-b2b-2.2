from __future__ import annotations

import enum
import uuid

from sqlalchemy import (
    Column,
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.models.base import Base


class InvoiceStatus(str, enum.Enum):
    CREATED = "CREATED"
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    seller_id = Column(UUID(as_uuid=True), nullable=False, index=True)
    status = Column(
        SQLEnum(InvoiceStatus, name="invoicestatus", create_constraint=True),
        default=InvoiceStatus.CREATED,
        nullable=False,
    )
    total_amount = Column(Integer, nullable=True)
    comment = Column(Text, nullable=True)
    description = Column(Text, nullable=True)

    items = relationship(
        "InvoiceItem", back_populates="invoice", cascade="all, delete-orphan"
    )

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<Invoice(id={self.id}, seller_id={self.seller_id}, "
            f"status={self.status.value})>"
        )


class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    invoice_id = Column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sku_id = Column(
        UUID(as_uuid=True), ForeignKey("skus.id"), nullable=False
    )
    quantity = Column(Integer, nullable=False)
    price = Column(Integer, nullable=False, server_default="0")

    invoice = relationship("Invoice", back_populates="items")
    sku = relationship("SKU")

    def __repr__(self) -> str:
        return (
            f"<InvoiceItem(invoice_id={self.invoice_id}, "
            f"sku_id={self.sku_id}, qty={self.quantity})>"
        )
