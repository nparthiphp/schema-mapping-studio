import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient

SAMPLE_PAYLOAD = {
    "id": 9823,
    "created_at": "2026-06-07T09:14:33Z",
    "subject": "Payment not going through",
    "description": "My card keeps getting declined.",
    "status": "solved",
    "requester_id": "USR-4421",
    "satisfaction_rating": {"score": "bad"},
    "custom_fields": [{"id": 360001, "value": "8"}],
}

MOCK_EXPRESSION = (
    '{\n'
    '  "event_id": $string(id),\n'
    '  "source": "zendesk",\n'
    '  "timestamp_utc": $toMillis(created_at),\n'
    '  "channel": "chat",\n'
    '  "raw_intent": (description & ""),\n'
    '  "intent_category": null,\n'
    '  "sentiment_score": satisfaction_rating.score = "bad" ? -1.0 : 1.0,\n'
    '  "handle_time_seconds": 0,\n'
    '  "resolved": $lowercase(status) = "solved" ? true : false,\n'
    '  "escalated": false,\n'
    '  "customer_id": $string(requester_id),\n'
    '  "metadata": $\n'
    '}'
)


@pytest.mark.asyncio
async def test_onboard_source(client: AsyncClient):
    with patch("app.services.llm.generate_mapping", new=AsyncMock(return_value=(MOCK_EXPRESSION, "api"))):
        r = await client.post("/sources", json={
            "source_name": "Zendesk",
            "source_category": "CRM",
            "sample_payload": SAMPLE_PAYLOAD,
        })
    assert r.status_code == 201
    data = r.json()
    assert data["source_name"] == "Zendesk"
    assert data["status"] == "pending"
    assert data["coverage_pct"] > 0
    assert "expression" in data
    return data["id"]


@pytest.mark.asyncio
async def test_list_sources(client: AsyncClient):
    r = await client.get("/sources")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_approve_reject_low_coverage(client: AsyncClient):
    """Approving a mapping with < 60% coverage should fail."""
    with patch("app.services.llm.generate_mapping", new=AsyncMock(return_value=('{"event_id": "x"}', "local"))):
        r = await client.post("/sources", json={
            "source_name": "Tiny",
            "source_category": "Custom",
            "sample_payload": {"id": 1},
        })
    assert r.status_code == 201
    source_id = r.json()["id"]
    r2 = await client.put(f"/sources/{source_id}/approve", json={})
    assert r2.status_code == 422


@pytest.mark.asyncio
async def test_deactivate_source(client: AsyncClient):
    with patch("app.services.llm.generate_mapping", new=AsyncMock(return_value=(MOCK_EXPRESSION, "api"))):
        r = await client.post("/sources", json={
            "source_name": "ToDelete",
            "source_category": "CRM",
            "sample_payload": SAMPLE_PAYLOAD,
        })
    sid = r.json()["id"]
    r2 = await client.delete(f"/sources/{sid}")
    assert r2.status_code == 204


@pytest.mark.asyncio
async def test_auth_required(client: AsyncClient):
    from httpx import AsyncClient as AC, ASGITransport
    from app.main import app
    async with AC(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/sources")
    assert r.status_code == 401
