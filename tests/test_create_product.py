"""Tests for US-B2B-01: create product endpoint (UUID ids, B2B-1 contract)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.models.base import get_db as real_get_db
from src.models.product import Category, Product, ProductStatus

SELLER_UUID = UUID("00000000-0000-4000-8000-000000000042")
SELLER_UUID_ALT = UUID("00000000-0000-4000-8000-000000000999")
CATEGORY_UUID = UUID("00000000-0000-4000-8000-000000000001")
PRODUCT_UUID = UUID("00000000-0000-4000-8000-000000000500")


def _mock_product(
    product_id: UUID = PRODUCT_UUID,
    seller_id: UUID = SELLER_UUID,
    status=ProductStatus.CREATED,
):
    product = MagicMock(spec=Product)
    product.id = product_id
    product.title = "New Product"
    product.description = "Test description"
    product.status = status
    product.seller_id = seller_id
    product.category_id = CATEGORY_UUID
    product.slug = "new-product-abcd1234"
    product.deleted = False
    product.blocking_comment = None
    product.blocking_reason_id = None
    product.field_reports = None
    product.images = []
    product.characteristics = []
    product.skus = []
    product.created_at = datetime.now(timezone.utc)
    product.updated_at = None
    return product


def _mock_category(category_id: UUID = CATEGORY_UUID):
    cat = MagicMock(spec=Category)
    cat.id = category_id
    cat.name = "Test Category"
    cat.slug = "test-category"
    cat.parent_id = None
    return cat


def _mock_session(product, category_exists: bool = True):
    session = AsyncMock()
    cat = _mock_category() if category_exists else None

    async def mock_get(model, ident):
        if model is Product:
            return product
        if model is Category:
            if category_exists and ident == CATEGORY_UUID:
                return cat
            return None
        return None

    async def mock_execute(query):
        result = MagicMock()
        result.scalar_one = MagicMock(return_value=product)
        result.scalars = MagicMock(
            return_value=MagicMock(all=MagicMock(return_value=[]))
        )
        return result

    session.get = AsyncMock(side_effect=mock_get)
    session.execute = AsyncMock(side_effect=mock_execute)
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()

    async def mock_refresh(obj):
        obj.id = product.id
        obj.created_at = product.created_at
        obj.deleted = False
        obj.images = product.images
        obj.characteristics = product.characteristics
        obj.skus = product.skus
        obj.updated_at = None
        obj.status = product.status
        obj.seller_id = product.seller_id
        obj.title = product.title
        obj.description = product.description
        obj.category_id = product.category_id
        obj.slug = product.slug
        obj.blocking_comment = None
        obj.blocking_reason_id = None
        obj.field_reports = None
        return None

    session.refresh = mock_refresh
    return session


def make_test_client(product, seller_id: UUID = SELLER_UUID, category_exists: bool = True):
    session = _mock_session(product, category_exists=category_exists)

    async def override_get_db():
        yield session

    app.dependency_overrides[real_get_db] = override_get_db
    return TestClient(
        app, base_url="http://test", headers={"X-Seller-Id": str(seller_id)}
    )


def _valid_body(**overrides) -> dict:
    """Minimal valid ProductCreate body per B2B-1 (no skus, no seller_id)."""
    body = {
        "title": "New Product",
        "description": "Test description",
        "category_id": str(CATEGORY_UUID),
        "images": [{"url": "https://example.com/img.jpg", "ordering": 0}],
        "characteristics": [],
    }
    body.update(overrides)
    return body


def _assert_flat_error(data: dict) -> None:
    assert "code" in data, f"Expected flat error with 'code', got: {data}"
    assert "message" in data, f"Expected flat error with 'message', got: {data}"


@pytest.mark.asyncio
async def test_create_product_returns_201_with_created_status():
    """Happy path: product created with status=CREATED, skus=[], slug filled."""
    product = _mock_product(seller_id=SELLER_UUID)
    img = MagicMock()
    img.id = uuid4()
    img.product_id = PRODUCT_UUID
    img.url = "https://example.com/img.jpg"
    img.ordering = 0
    product.images = [img]
    client = make_test_client(product, seller_id=SELLER_UUID)

    response = client.post("/api/v1/products", json=_valid_body())

    assert response.status_code == 201, (
        f"Expected 201, got {response.status_code}: {response.text}"
    )
    data = response.json()
    assert data["title"] == "New Product"
    assert data["description"] == "Test description"
    assert data["status"] == "CREATED"
    assert data["skus"] == []
    assert data["slug"], "slug must be non-empty after create"
    assert data["images"], "images must be non-empty after create"
    UUID(data["id"])
    UUID(data["seller_id"])
    UUID(data["category_id"])


@pytest.mark.asyncio
async def test_seller_id_taken_from_jwt():
    """seller_id comes from JWT header, never from body."""
    product = _mock_product(seller_id=SELLER_UUID_ALT)
    img = MagicMock()
    img.id = uuid4()
    img.product_id = PRODUCT_UUID
    img.url = "https://example.com/img.jpg"
    img.ordering = 0
    product.images = [img]
    client = make_test_client(product, seller_id=SELLER_UUID_ALT)

    response = client.post("/api/v1/products", json=_valid_body())

    assert response.status_code == 201, response.text
    assert response.json()["seller_id"] == str(SELLER_UUID_ALT)


@pytest.mark.asyncio
async def test_missing_images_returns_400():
    product = _mock_product()
    client = make_test_client(product)

    response = client.post(
        "/api/v1/products",
        json=_valid_body(images=[]),
    )

    assert response.status_code == 422, response.text
    data = response.json()
    _assert_flat_error(data)
    assert data["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_missing_category_returns_400():
    product = _mock_product()
    client = make_test_client(product)

    body = _valid_body()
    del body["category_id"]
    response = client.post("/api/v1/products", json=body)

    assert response.status_code == 422, response.text
    data = response.json()
    _assert_flat_error(data)
    assert data["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_invalid_category_id_returns_400():
    product = _mock_product()
    client = make_test_client(product, category_exists=False)

    response = client.post(
        "/api/v1/products",
        json=_valid_body(category_id=str(uuid4())),
    )

    assert response.status_code == 400, response.text
    data = response.json()
    _assert_flat_error(data)
    assert data["code"] == "INVALID_CATEGORY"


@pytest.mark.asyncio
async def test_missing_description_returns_422():
    product = _mock_product()
    client = make_test_client(product)

    body = _valid_body()
    del body["description"]
    response = client.post("/api/v1/products", json=body)

    assert response.status_code == 422, response.text
    data = response.json()
    _assert_flat_error(data)
    assert data["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_title_longer_than_255_returns_422():
    """B2B-1: title must be 1-255 characters — longer is rejected."""
    product = _mock_product()
    client = make_test_client(product)

    response = client.post(
        "/api/v1/products",
        json=_valid_body(title="x" * 256),
    )

    assert response.status_code == 422, response.text
    data = response.json()
    _assert_flat_error(data)
    assert data["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_description_longer_than_5000_returns_422():
    """B2B-1: description must be 1-5000 characters — longer is rejected."""
    product = _mock_product()
    client = make_test_client(product)

    response = client.post(
        "/api/v1/products",
        json=_valid_body(description="d" * 5001),
    )

    assert response.status_code == 422, response.text
    data = response.json()
    _assert_flat_error(data)
    assert data["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_skus_in_body_rejected():
    """Product create must not accept skus (separate stage B2B-2)."""
    product = _mock_product()
    client = make_test_client(product)

    body = _valid_body()
    body["skus"] = [{"name": "should-not-be-here"}]
    response = client.post("/api/v1/products", json=body)

    assert response.status_code == 422, response.text
    data = response.json()
    _assert_flat_error(data)
    assert data["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_create_product_does_not_create_skus():
    """CRUD must not insert SKU rows; response skus is always []."""
    product = _mock_product()
    img = MagicMock()
    img.id = uuid4()
    img.product_id = PRODUCT_UUID
    img.url = "https://example.com/img.jpg"
    img.ordering = 0
    product.images = [img]
    product.skus = []
    client = make_test_client(product)

    response = client.post("/api/v1/products", json=_valid_body())

    assert response.status_code == 201, response.text
    assert response.json()["skus"] == []
    assert response.json()["status"] == "CREATED"
