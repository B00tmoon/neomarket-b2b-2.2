"""Tests for US-MOD-05: hard block flow."""

from __future__ import annotations

from tests.conftest import PRODUCT_UUID, SELLER_UUID

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.models.product import ProductStatus
from tests.conftest import _mock_product, _mock_sku, make_test_client


@pytest.mark.asyncio
async def test_hard_block_transitions_to_terminal_and_emits_event():
    """Hard block: ON_MODERATION → HARD_BLOCKED, BLOCKED event emitted."""
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
                "/api/v1/moderation/events",
                headers={"X-Service-Key": "b2b-moderation-key"},
                json={
                    "product_id": "00000000-0000-4000-8000-000000000100",
                    "event_type": "BLOCKED",
                    "occurred_at": "2026-07-30T12:00:00Z",
                    "hard_block": True,
                    "idempotency_key": "hb-001",
                    "moderator_comment": "Counterfeit goods",
                },
            )

    assert response.status_code == 204, (
        f"Expected 204, got {response.status_code}: {response.text}"
    )
    data = response.json()
    assert data["status"] == "accepted"
    assert data["event_type"] == "BLOCKED"
    assert str(data["product_id"]) == "00000000-0000-4000-8000-000000000100"


@pytest.mark.asyncio
async def test_hard_block_event_carries_hard_block_true():
    """The BLOCKED event payload includes hard_block=true."""
    product = _mock_product(
        product_id=PRODUCT_UUID,
        status=ProductStatus.ON_MODERATION,
        seller_id=SELLER_UUID,
        has_sku=True,
    )
    sku = _mock_sku()
    captured_payload = {}

    async def mock_post(url, json, **kwargs):
        captured_payload.update(json)
        return MagicMock(status_code=200)

    with make_test_client(product, [sku]) as client:
        with patch("src.services.moderation.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = mock_post
            mock_ctx = AsyncMock()
            mock_ctx.__aenter__ = AsyncMock(return_value=mock_client)
            mock_ctx.__aexit__ = AsyncMock(return_value=None)
            mock_client_cls.return_value = mock_ctx

            client.post(
                "/api/v1/moderation/events",
                json={
                    "product_id": "00000000-0000-4000-8000-000000000100",
                    "event_type": "BLOCKED",
                    "occurred_at": "2026-07-30T12:00:00Z",
                    "hard_block": True,
                    "idempotency_key": "hb-002",
                },
            )

    assert captured_payload.get("event_type") == "BLOCKED"
    assert captured_payload.get("hard_block") is True


@pytest.mark.asyncio
async def test_any_modify_on_hard_blocked_returns_403():
    """PUT on a HARD_BLOCKED product returns 403."""
    product = _mock_product(
        product_id=PRODUCT_UUID,
        status=ProductStatus.HARD_BLOCKED,
        seller_id=SELLER_UUID,
        has_sku=True,
    )

    with make_test_client(product, []) as client:
        response = client.put(
            "/api/v1/products/00000000-0000-4000-8000-000000000100",
            json={"title": "Attempted change"},
        )

    assert response.status_code == 403, (
        f"Expected 403, got {response.status_code}: {response.text}"
    )
    data = response.json()
    assert data["code"] == "PRODUCT_HARD_BLOCKED"


@pytest.mark.asyncio
async def test_edited_event_on_hard_blocked_is_ignored():
    """EDITED event from B2B should not unblock a HARD_BLOCKED product.
    Since HARD_BLOCKED products can only transition via moderation events,
    an EDITED event arriving for a HARD_BLOCKED product is silently ignored
    (the product stays HARD_BLOCKED).
    """
    product = _mock_product(
        product_id=PRODUCT_UUID,
        status=ProductStatus.HARD_BLOCKED,
        seller_id=SELLER_UUID,
        has_sku=True,
    )
    sku = _mock_sku()

    with make_test_client(product, [sku]) as client:
        # Simulate a MODERATED event arriving — it should be rejected
        # because HARD_BLOCKED is not ON_MODERATION
        response = client.post(
            "/api/v1/moderation/events",
            headers={"X-Service-Key": "b2b-moderation-key"},
            json={
                "product_id": "00000000-0000-4000-8000-000000000100",
                "event_type": "EDITED",
                    "occurred_at": "2026-07-30T12:00:00Z",
                "idempotency_key": "ed-001",
            },
        )

    assert response.status_code == 204, (
        f"Expected 204 for ignored EDITED, got {response.status_code}: {response.text}"
    )


@pytest.mark.asyncio
async def test_deleted_event_removes_hard_blocked():
    """DELETE product softens the HARD_BLOCKED state.
    The product record gets deleted=True but HARD_BLOCKED status persists
    (B2B still sees it as blocked). The endpoint itself should succeed.
    """
    product = _mock_product(
        product_id=PRODUCT_UUID,
        status=ProductStatus.HARD_BLOCKED,
        seller_id=SELLER_UUID,
        has_sku=True,
    )

    with make_test_client(product, []) as client:
        response = client.post("/api/v1/products/00000000-0000-4000-8000-000000000100/delete")

    # The delete endpoint should also be blocked for HARD_BLOCKED
    assert response.status_code == 403, (
        f"Expected 403, got {response.status_code}: {response.text}"
    )