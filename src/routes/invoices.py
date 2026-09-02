from __future__ import annotations

import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.base import get_db
from src.models.invoice import Invoice, InvoiceItem, InvoiceStatus
from src.models.sku import SKU

router = APIRouter()


@router.post("/invoices", response_model=dict, status_code=201)
async def create_invoice(
    items: list[dict],
    seller_id: UUID,
    description: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Создать накладную. seller_id — UUID."""
    invoice = Invoice(
        id=uuid.uuid4(),
        seller_id=seller_id,
        status=InvoiceStatus.CREATED,
        description=description,
    )
    db.add(invoice)
    await db.flush()

    for item_data in items:
        raw_sku = item_data["sku_id"]
        try:
            sku_id = UUID(str(raw_sku))
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=400, detail=f"Invalid sku_id UUID: {raw_sku}"
            )
        sku = await db.get(SKU, sku_id)
        if not sku:
            raise HTTPException(status_code=404, detail=f"SKU {sku_id} not found")

        item = InvoiceItem(
            id=uuid.uuid4(),
            invoice_id=invoice.id,
            sku_id=sku_id,
            quantity=item_data["quantity"],
            price=sku.price,
        )
        db.add(item)

    await db.commit()
    await db.refresh(invoice)

    return {
        "id": str(invoice.id),
        "seller_id": str(invoice.seller_id),
        "status": invoice.status.value,
        "items_count": len(invoice.items),
    }


@router.post("/invoices/{invoice_id}/submit", response_model=dict)
async def submit_invoice(invoice_id: UUID, db: AsyncSession = Depends(get_db)):
    """Отправить накладную на склад."""
    invoice = await db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status not in (InvoiceStatus.CREATED, InvoiceStatus.DRAFT):
        raise HTTPException(
            status_code=400,
            detail=f"Invoice status is {invoice.status.value}, cannot submit",
        )

    invoice.status = InvoiceStatus.SUBMITTED
    await db.commit()
    await db.refresh(invoice)

    return {"id": str(invoice.id), "status": invoice.status.value}


@router.post("/invoices/accept", response_model=dict)
async def accept_invoice(invoice_id: UUID, db: AsyncSession = Depends(get_db)):
    """Склад принимает накладную (увеличивает activeQuantity)."""
    invoice = await db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    if invoice.status != InvoiceStatus.SUBMITTED:
        raise HTTPException(
            status_code=400,
            detail=f"Invoice status is {invoice.status.value}, cannot accept",
        )

    for item in invoice.items:
        sku = await db.get(SKU, item.sku_id)
        if sku:
            sku.active_quantity += item.quantity

    invoice.status = InvoiceStatus.ACCEPTED
    await db.commit()
    await db.refresh(invoice)

    return {"id": str(invoice.id), "status": invoice.status.value}


@router.get("/invoices", response_model=list)
async def list_invoices(
    seller_id: UUID | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Список накладных."""
    query = select(Invoice)

    if seller_id:
        query = query.where(Invoice.seller_id == seller_id)
    if status:
        query = query.where(Invoice.status == InvoiceStatus(status))

    result = await db.execute(query.order_by(Invoice.created_at.desc()))
    invoices = result.scalars().all()
    return invoices
