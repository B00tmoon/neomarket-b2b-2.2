"""Tests for US-B2B-02: create SKU endpoint (POST /api/v1/skus)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.models.base import get_db as real_get_db
from src.models.product import Product, ProductStatus
from src.models.sku import SKU

SELLER_UUID = UUID("00000000-0000-4000-8000-000000000042")
OTHER_SELLER = UUID("00000000-0000-4000-8000-000000000099")
PRODUCT_UUID = UUID("00000000-0000-4000-8000-000000000500")
SKU_UUID = UUID("00000000-0000-4000-8000-000000000600")


def _mock_product(
    product_id: UUID = PRODUCT_UUID,
    seller_id: UUID = SELLER_UUID,
    status=ProductStatus.CREATED,
):
    product = MagicMock(spec=Product)
    product.id = product_id
    product.seller_id = seller_id
    product.status = status
    product.deleted = False
    product.title = "Test Product"
    return product


def _mock_sku(sku_id: UUID = SKU_UUID, product_id: UUID = PRODUCT_UUID):
    sku = MagicMock(spec=SKU)
    sku.id = sku_id
    sku.product_id = product_id
    sku.name = "256GB Black"
    sku.price = 12999000
    sku.cost_price = 9500000
    sku.discount = 0
    sku.image = "/s3/iphone15-black-256.jpg"
    sku.active_quantity = 0
    sku.blocked_quantity = 0
    sku.active = True
    sku.sku_code = f"SKU-{sku_id.hex[:12]}"
    sku.characteristics = []
    return sku


def _mock_session(*, product, existing_skus=None):
    """AsyncSession mock for create_sku flow."""
    session = AsyncMock()
    existing_skus = existing_skus if existing_skus is not None else []
    created_sku_holder: dict = {}

    async def mock_get(model, ident, **kwargs):
        if model is Product:
            return product if ident == product.id else None
        if model is SKU:
            return created_sku_holder.get("sku")
        return None

    async def mock_execute(query):
        result = MagicMock()
        # Distinguish count-of-existing vs reload-after-create by heuristics:
        # if we already created a sku, return it for scalar_one
        if created_sku_holder.get("sku") is not None:
            result.scalar_one = MagicMock(return_value=created_sku_holder["sku"])
            result.scalar_one_or_none = MagicMock(return_value=created_sku_holder["sku"])
            result.scalars = MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=existing_skus))
            )
        else:
            result.scalar_one = MagicMock(side_effect=Exception("no scalar yet"))
            result.scalar_one_or_none = MagicMock(return_value=None)
            result.scalars = MagicMock(
                return_value=MagicMock(all=MagicMock(return_value=existing_skus))
            )
        return result

    def mock_add(obj):
        if isinstance(obj, SKU) or (hasattr(obj, "__tablename__") and getattr(obj, "__tablename__", None) == "skus"):
            created_sku_holder["sku"] = obj
            # ensure response fields
            if not getattr(obj, "characteristics", None):
                obj.characteristics = []
        # Also accept MagicMock SKUs
        if hasattr(obj, "product_id") and hasattr(obj, "price") and hasattr(obj, "name"):
            if not hasattr(obj, "characteristics") or obj.characteristics is None:
                try:
                    obj.characteristics = []
                except Exception:
                    pass
            created_sku_holder["sku"] = obj

    session.get = AsyncMock(side_effect=mock_get)
    session.execute = AsyncMock(side_effect=mock_execute)
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock(side_effect=mock_add)
    session.rollback = AsyncMock()
    return session


def make_client(product, seller_id: UUID = SELLER_UUID, existing_skus=None):
    session = _mock_session(product=product, existing_skus=existing_skus or [])

    async def override_get_db():
        yield session

    app.dependency_overrides[real_get_db] = override_get_db
    client = TestClient(
        app, base_url="http://test", headers={"X-Seller-Id": str(seller_id)}
    )
    return client, session


def _valid_body(product_id: UUID = PRODUCT_UUID, **overrides) -> dict:
    body = {
        "product_id": str(product_id),
        "name": "256GB Black",
        "price": 12999000,
        "cost_price": 9500000,
        "discount": 0,
        "image": "/s3/iphone15-black-256.jpg",
        "characteristics": [
            {"name": "Цвет", "value": "Чёрный"},
            {"name": "Объём памяти", "value": "256 ГБ"},
        ],
    }
    body.update(overrides)
    return body


@pytest.mark.asyncio
async def test_first_sku_transitions_product_to_on_moderation():
    """First SKU on CREATED product → product.status = ON_MODERATION."""
    product = _mock_product(status=ProductStatus.CREATED)
    client, session = make_client(product, existing_skus=[])

    with patch("src.routes.skus.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=MagicMock(status_code=204))
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_ctx

        response = client.post("/api/v1/skus", json=_valid_body())

    assert response.status_code == 201, (
        f"Expected 201, got {response.status_code}: {response.text}"
    )
    assert product.status == ProductStatus.ON_MODERATION
    data = response.json()
    assert data["name"] == "256GB Black"
    assert data["price"] == 12999000
    assert data["cost_price"] == 9500000
    assert data["image"] == "/s3/iphone15-black-256.jpg"
    assert data["product_id"] == str(PRODUCT_UUID)


@pytest.mark.asyncio
async def test_first_sku_emits_created_event_to_moderation():
    """First SKU → POST Moderation /events/product with event=CREATED, X-Service-Key, idempotency_key."""
    product = _mock_product(status=ProductStatus.CREATED)
    client, session = make_client(product, existing_skus=[])

    captured = {}

    async def mock_post(url, json=None, headers=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return MagicMock(status_code=204)

    with patch("src.routes.skus.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = mock_post
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_ctx

        response = client.post("/api/v1/skus", json=_valid_body())

    assert response.status_code == 201, response.text
    assert "json" in captured, "Moderation event was not sent"
    payload = captured["json"]
    assert payload["event"] == "CREATED"
    assert payload["product_id"] == str(PRODUCT_UUID)
    assert payload["seller_id"] == str(SELLER_UUID)
    assert "idempotency_key" in payload and payload["idempotency_key"]
    assert "date" in payload
    headers = captured["headers"] or {}
    assert headers.get("X-Service-Key") == "b2b-moderation-key"
    assert "/api/v1/events/product" in captured["url"]


@pytest.mark.asyncio
async def test_second_sku_no_state_change():
    """Second SKU on product already ON_MODERATION → status unchanged, no CREATED event."""
    product = _mock_product(status=ProductStatus.ON_MODERATION)
    existing = [_mock_sku()]
    client, session = make_client(product, existing_skus=existing)

    with patch("src.routes.skus.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=MagicMock(status_code=204))
        mock_ctx = AsyncMock()
        mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ctx.__aexit__ = AsyncMock(return_value=None)
        mock_cls.return_value = mock_ctx

        response = client.post("/api/v1/skus", json=_valid_body())

    assert response.status_code == 201, response.text
    assert product.status == ProductStatus.ON_MODERATION
    # No event for second SKU while ON_MODERATION
    mock_client.post.assert_not_called()


@pytest.mark.asyncio
async def test_add_sku_to_hard_blocked_returns_403():
    """Adding SKU to HARD_BLOCKED product → 403 FORBIDDEN."""
    product = _mock_product(status=ProductStatus.HARD_BLOCKED)
    client, _ = make_client(product, existing_skus=[])

    response = client.post("/api/v1/skus", json=_valid_body())

    assert response.status_code == 403, response.text
    data = response.json()
    assert data["code"] in ("FORBIDDEN", "PRODUCT_HARD_BLOCKED")
    assert "hard-blocked" in data["message"].lower() or "hard_blocked" in data[
        "message"
    ].lower() or "HARD_BLOCKED" in data["message"]


@pytest.mark.asyncio
async def test_missing_image_returns_400():
    """Missing image → 422 validation (flat VALIDATION_ERROR)."""
    product = _mock_product(status=ProductStatus.CREATED)
    client, _ = make_client(product, existing_skus=[])

    body = _valid_body()
    del body["image"]

    response = client.post("/api/v1/skus", json=body)

    assert response.status_code == 422, response.text
    data = response.json()
    assert data["code"] == "VALIDATION_ERROR"
    assert "image" in data["message"].lower() or (
        (data.get("details") or {}).get("field") == "image"
    )


@pytest.mark.asyncio
async def test_price_must_be_positive():
    """price <= 0 → 422 VALIDATION_ERROR."""
    product = _mock_product(status=ProductStatus.CREATED)
    client, _ = make_client(product, existing_skus=[])

    response = client.post("/api/v1/skus", json=_valid_body(price=0))

    assert response.status_code == 422, response.text
    data = response.json()
    assert data["code"] == "VALIDATION_ERROR"
