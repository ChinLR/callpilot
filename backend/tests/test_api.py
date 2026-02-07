"""Tests for the API endpoints (mocked telephony)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.store import store


@pytest.fixture(autouse=True)
def _clear_store() -> None:
    """Reset in-memory store between tests."""
    store.campaigns.clear()
    store.calls.clear()


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_health() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@pytest.mark.anyio
async def test_create_campaign_returns_202() -> None:
    """POST /campaigns should return 202 with a campaign_id."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/campaigns",
            json={
                "service": "dentist",
                "location": "San Francisco",
                "date_range_start": "2025-03-15T08:00:00Z",
                "date_range_end": "2025-03-20T18:00:00Z",
                "duration_min": 30,
                "max_providers": 5,
                "max_parallel": 3,
            },
        )

    assert resp.status_code == 202
    data = resp.json()
    assert "campaign_id" in data
    assert data["status"] == "running"


@pytest.mark.anyio
async def test_get_campaign_running_then_completed() -> None:
    """GET /campaigns/{id} returns running immediately, completed after task finishes."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Create campaign
        resp = await client.post(
            "/campaigns",
            json={
                "service": "dentist",
                "location": "San Francisco",
                "date_range_start": "2025-03-15T08:00:00Z",
                "date_range_end": "2025-03-20T18:00:00Z",
            },
        )
        campaign_id = resp.json()["campaign_id"]

        # Poll — should be running initially
        resp2 = await client.get(f"/campaigns/{campaign_id}")
        assert resp2.status_code == 200
        data = resp2.json()
        assert data["status"] in ("running", "completed")

        # Wait for background task to finish (simulated calls are fast)
        for _ in range(20):
            await asyncio.sleep(0.5)
            resp3 = await client.get(f"/campaigns/{campaign_id}")
            if resp3.json()["status"] == "completed":
                break

        final = resp3.json()
        assert final["status"] == "completed"
        assert "ranked" in final
        assert isinstance(final["ranked"], list)


@pytest.mark.anyio
async def test_get_campaign_not_found() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/campaigns/nonexistent123")
    assert resp.status_code == 404


@pytest.mark.anyio
async def test_confirm_slot_not_found() -> None:
    """Confirming a slot for a nonexistent campaign returns 404."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/campaigns/nonexistent/confirm",
            json={
                "provider_id": "prov_bright_smile",
                "start": "2025-03-15T10:00:00Z",
                "end": "2025-03-15T10:30:00Z",
                "user_contact": {"name": "John", "phone": "+15559999999"},
            },
        )
    assert resp.status_code == 404
