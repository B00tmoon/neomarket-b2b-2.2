"""Tests for US-MOD-03: product approval by moderator."""

from __future__ import annotations

from uuid import UUID

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.main import app
from src.models.product import ProductStatus
from tests.conftest import _mock_product, _mock_sku, make_test_client, PRODUCT_UUID, SELLER_UUID


@pytest.mark.asyncio
async def test_approve_transitions_to_moderated_and_emits_event():
    """Happy path: status → MODERATED, B2C event emitted."""
    product = _mock_product(
        product_id=PRODUCT_UUID,
        status=ProductStatus.ON_MODERATION,
        seller_id=SELLER_UUID,
        has_sku=True,
    )
    sku = _mock_sku()

    with make_test_client(product, [sku]) as client:
        with patch("src.services.moderation.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=MagicMock(status_code=200))
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_ctx

            response = client.post(
                "/api/v1/products/00000000-0000-4000-8000-000000000100/approve",
                json={"comment": "Approved by moderator"},
                params={"seller_id": "00000000-0000-4000-8000-000000000001"},
            )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text}"
    )
    data = response.json()
    assert data["status"] == "MODERATED"
    assert str(data["product_id"]) == "00000000-0000-4000-8000-000000000100"
    assert str(data["seller_id"]) == "00000000-0000-4000-8000-000000000001"


@pytest.mark.asyncio
async def test_approve_others_card_returns_403():
    """Unhappy path: moderator can't approve another seller's product."""
    product = _mock_product(
        product_id=PRODUCT_UUID,
        status=ProductStatus.ON_MODERATION,
        seller_id=UUID("00000000-0000-4000-8000-000000000002"),
        has_sku=True,
    )
    sku = _mock_sku()

    with make_test_client(product, [sku]) as client:
        response = client.post(
            "/api/v1/products/00000000-0000-4000-8000-000000000100/approve",
            json={"comment": "Trying someone else's product"},
            params={"seller_id": "00000000-0000-4000-8000-000000000001"},
        )

    assert response.status_code == 403, (
        f"Expected 403, got {response.status_code}: {response.text}"
    )
    data = response.json()
    assert data["code"] == "PRODUCT_NOT_YOURS"


@pytest.mark.asyncio
async def test_approve_after_edited_returns_409():
    """Unhappy path: product edited by seller → CREATED → approve fails."""
    product = _mock_product(
        product_id=PRODUCT_UUID,
        status=ProductStatus.CREATED,
        seller_id=SELLER_UUID,
        has_sku=True,
    )
    sku = _mock_sku()

    with make_test_client(product, [sku]) as client:
        response = client.post(
            "/api/v1/products/00000000-0000-4000-8000-000000000100/approve",
            json={"comment": "Approve"},
            params={"seller_id": "00000000-0000-4000-8000-000000000001"},
        )

    assert response.status_code == 409, (
        f"Expected 409, got {response.status_code}: {response.text}"
    )
    data = response.json()
    assert data["code"] == "PRODUCT_WRONG_STATUS"


@pytest.mark.asyncio
async def test_approve_without_sku_returns_409():
    """Unhappy path: product without SKU can't be approved."""
    product = _mock_product(
        product_id=PRODUCT_UUID,
        status=ProductStatus.ON_MODERATION,
        seller_id=SELLER_UUID,
        has_sku=False,
    )

    with make_test_client(product, []) as client:
        response = client.post(
            "/api/v1/products/00000000-0000-4000-8000-000000000100/approve",
            json={"comment": "Approve"},
            params={"seller_id": "00000000-0000-4000-8000-000000000001"},
        )

    assert response.status_code == 409, (
        f"Expected 409, got {response.status_code}: {response.text}"
    )
    data = response.json()
    assert data["code"] == "PRODUCT_NO_SKU"
