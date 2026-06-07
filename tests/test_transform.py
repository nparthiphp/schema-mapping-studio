import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient

SAMPLE_PAYLOAD = {
    "id": 9823,
    "created_at": "2026-06-07T09:14:33Z",
    "description": "Card declined",
    "status": "solved",
    "requester_id": "USR-4421",
    "satisfaction_rating": {"score": "bad"},
}

MOCK_EXPRESSION = (
    '{\n'
    '  "event_id": $string(id),\n'
    '  "source": "zendesk",\n'
    '  "timestamp_utc": $toMillis(created_at),\n'
    '  "channel": "chat",\n'
    '  "raw_intent": (description & ""),\n'
    '  "intent_category": null,\n'
    '  "sentiment_score": -1.0,\n'
    '  "handle_time_seconds": 0,\n'
    '  "resolved": true,\n'
    '  "escalated": false,\n'
    '  "customer_id": $string(requester_id),\n'
    '  "metadata": $\n'
    '}'
)

MOCK_CANONICAL = {
    "event_id": "9823", "source": "zendesk", "timestamp_utc": 1749291273000,
    "channel": "chat", "raw_intent": "Card declined", "intent_category": None,
    "sentiment_score": -1.0, "handle_time_seconds": 0, "resolved": True,
    "escalated": False, "customer_id": "USR-4421", "metadata": {},
}


@pytest.mark.asyncio
async def test_transform_unapproved_fails(client: AsyncClient):
    with patch("app.services.llm.generate_mapping", new=AsyncMock(return_value=(MOCK_EXPRESSION, "api"))):
        r = await client.post("/sources", json={
            "source_name": "ZD-Transform",
            "source_category": "CRM",
            "sample_payload": SAMPLE_PAYLOAD,
        })
    sid = r.json()["id"]
    r2 = await client.post("/transform", json={"source_id": sid, "payload": SAMPLE_PAYLOAD})
    assert r2.status_code == 422


@pytest.mark.asyncio
async def test_transform_approved_source(client: AsyncClient):
    with patch("app.services.llm.generate_mapping", new=AsyncMock(return_value=(MOCK_EXPRESSION, "api"))):
        r = await client.post("/sources", json={
            "source_name": "ZD-TransformOK",
            "source_category": "CRM",
            "sample_payload": SAMPLE_PAYLOAD,
        })
    sid = r.json()["id"]
    await client.put(f"/sources/{sid}/approve", json={"expression": MOCK_EXPRESSION})

    with patch("app.services.jsonata_runner.evaluate", new=AsyncMock(return_value=MOCK_CANONICAL)):
        r2 = await client.post("/transform", json={"source_id": sid, "payload": SAMPLE_PAYLOAD})
    assert r2.status_code == 200
    data = r2.json()
    assert data["source_name"] == "ZD-TransformOK"
    assert "canonical" in data
    assert "duration_ms" in data
