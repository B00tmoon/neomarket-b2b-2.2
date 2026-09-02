"""Shared pytest fixtures and test helpers for the project."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.models.base import get_db as real_get_db
from src.models.product import Product, ProductStatus

PRODUCT_UUID = UUID("00000000-0000-4000-8000-000000000100")
SELLER_UUID = UUID("00000000-0000-4000-8000-000000000001")
SKU_UUID = UUID("00000000-0000-4000-8000-000000000200")


def _mock_product(
    product_id: UUID = PRODUCT_UUID,
    seller_id: UUID = SELLER_UUID,
    status=ProductStatus.ON_MODERATION,
    deleted: bool = False,
    has_sku: bool = True,
    blocking_comment: str | None = None,
):
    product = MagicMock()
    product.id = product_id
    product.title = "Test Product"
    product.description = "Test description"
    product.status = status
    product.seller_id = seller_id
    product.deleted = deleted
    product.blocking_comment = blocking_comment
    product.category_id = UUID("00000000-0000-4000-8000-000000000010")
    return product


def _mock_sku():
    sku = MagicMock()
    sku.id = SKU_UUID
    sku.sku_code = "TEST-SKU-001"
    sku.name = "Test SKU"
    sku.price = 1000
    sku.active_quantity = 10
    sku.active = True
    return sku


def _mock_session(product, skus=None):
    """Build an AsyncSession mock using AsyncMock side_effect."""
    session = AsyncMock()

    async def mock_get(model, ident):
        if model is Product:
            return product
        return None

    async def mock_execute(query):
        result = AsyncMock()
        scalars_mock = MagicMock()
        scalars_mock.all = MagicMock(return_value=skus if skus is not None else [])
        result.scalars = MagicMock(return_value=scalars_mock)
        return result

    session.get = AsyncMock(side_effect=mock_get)
    session.execute = AsyncMock(side_effect=mock_execute)
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    return session


def make_test_client(product, skus):
    """Create a TestClient with custom product/skus override."""
    session = _mock_session(product, skus)

    async def override_get_db():
        yield session

    app.dependency_overrides[real_get_db] = override_get_db
    return TestClient(app)
