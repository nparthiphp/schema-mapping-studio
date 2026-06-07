"""Anthropic API integration with retry and local fallback."""
import asyncio
import json
import logging
import re
from typing import Literal

import anthropic

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

SYSTEM_PROMPT = """You are a senior data integration engineer specialising in JSONata transformations.
Given a source JSON payload and target canonical schema, output ONLY a valid JSONata object expression.
STRICT RULES:
1. Output ONLY the raw JSONata — no markdown, no backticks, no prose
2. Use null for fields that cannot be mapped
3. timestamp_utc: convert any date/epoch to UTC milliseconds integer
4. sentiment_score: map survey/rating to float -1.0 to +1.0
5. handle_time_seconds: always integer seconds
6. resolved / escalated: must evaluate to boolean
7. event_id: most unique identifier available
8. customer_id: any customer/user identifier"""

CANONICAL_DESCRIPTION = {
    "event_id": "Unique event identifier (string)",
    "source": "Source system name (string)",
    "timestamp_utc": "UTC epoch milliseconds (integer)",
    "channel": "voice|chat|email|social|web (string)",
    "raw_intent": "Raw customer issue text (string)",
    "intent_category": "Classified intent label (string)",
    "sentiment_score": "Customer sentiment -1.0 to +1.0 (float)",
    "handle_time_seconds": "Total handle time in seconds (integer)",
    "resolved": "Issue resolved (boolean)",
    "escalated": "Contact escalated (boolean)",
    "customer_id": "Customer identifier (string)",
    "metadata": "Source-specific extras (object)",
}


async def generate_mapping(
    sample_payload: dict,
    source_name: str,
) -> tuple[str, Literal["api", "local"]]:
    """Returns (jsonata_expression, mode). Falls back to local generator on failure."""
    for attempt in range(settings.llm_max_retries):
        try:
            expr = await _call_anthropic(sample_payload, source_name)
            logger.info("LLM mapping generated via API", extra={"attempt": attempt + 1, "source": source_name})
            return expr, "api"
        except Exception as exc:
            logger.warning("LLM attempt failed", extra={"attempt": attempt + 1, "error": str(exc)})
            if attempt < settings.llm_max_retries - 1:
                await asyncio.sleep(1.5 * (attempt + 1))

    logger.warning("All LLM retries exhausted — using local generator", extra={"source": source_name})
    expr = _local_generate(sample_payload, source_name)
    return expr, "local"


async def _call_anthropic(payload: dict, source_name: str) -> str:
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    user_msg = (
        f"SOURCE PAYLOAD ({source_name}):\n{json.dumps(payload, indent=2)}\n\n"
        f"TARGET CANONICAL SCHEMA:\n{json.dumps(CANONICAL_DESCRIPTION, indent=2)}\n\n"
        "Generate the JSONata expression:"
    )
    message = await asyncio.wait_for(
        client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.anthropic_max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        ),
        timeout=settings.anthropic_timeout,
    )
    raw = message.content[0].text.strip()
    clean = re.sub(r"```[\w]*\n?", "", raw).replace("```", "").strip()
    if len(clean) < 20:
        raise ValueError("Expression too short")
    return clean


def _local_generate(payload: dict, source_name: str) -> str:
    """Heuristic JSONata fallback when API is unavailable."""
    keys = list(payload.keys())

    def find(patterns):
        for p in patterns:
            for k in keys:
                if p.lower() in k.lower():
                    return k
        return None

    id_key     = find(["session_id", "case_number", "id", "number"])
    ts_key     = find(["created_at", "createddate", "end_epoch", "timestamp", "date"])
    cust_key   = find(["customer_id", "requester_id", "accountid", "contactid", "ani"])
    chan_key   = find(["channel", "origin", "via", "queue"])
    text_key   = find(["description", "subject", "wrap_up", "notes", "reason"])
    handle_key = find(["handle_time", "talk_time", "duration", "time_seconds", "time__c"])
    status_key = find(["status", "disposition", "resolution"])
    escal_key  = find(["escalat", "supervisor", "transferred"])
    sent_key   = find(["satisfaction", "survey_score", "csat", "rating", "score"])

    id_expr = f"$string({id_key})" if id_key else '"EVT-" & $string($millis())'

    if ts_key:
        v = payload.get(ts_key)
        ts_expr = (f"{ts_key} * ({ts_key} < 9999999999 ? 1000 : 1)"
                   if isinstance(v, (int, float))
                   else f"$toMillis({ts_key})")
    else:
        ts_expr = "$millis()"

    default_chan = "voice" if any(x in source_name.lower() for x in ["genesys", "ivr", "avaya"]) else "chat"
    if chan_key and isinstance(payload.get(chan_key), str):
        chan_expr = (f'$lowercase({chan_key}) = "phone" ? "voice" : '
                     f'$lowercase({chan_key}) = "email" ? "email" : "chat"')
    elif chan_key and isinstance(payload.get(chan_key), dict):
        chan_expr = (f'$lowercase({chan_key}.channel) = "phone" ? "voice" : '
                     f'$lowercase({chan_key}.channel) = "email" ? "email" : "chat"')
    else:
        chan_expr = f'"{default_chan}"'

    if sent_key:
        sv = payload.get(sent_key)
        if isinstance(sv, (int, float)):
            m = 5 if sv <= 5 else 10
            sent_expr = f"($number({sent_key}) - {m/2}) / {m/2}"
        elif isinstance(sv, dict):
            sent_expr = f'{sent_key}.score = "good" ? 1.0 : {sent_key}.score = "bad" ? -1.0 : 0.0'
        else:
            sent_expr = f'{sent_key} = "good" ? 1.0 : {sent_key} = "bad" ? -1.0 : 0.0'
    else:
        sent_expr = "0.0"

    handle_expr = (f"$number({handle_key}) * 60"
                   if handle_key and handle_key.lower().endswith("minutes")
                   else f"$number({handle_key})" if handle_key else "0")

    if status_key:
        resolved_expr = (f'$lowercase({status_key}) = "solved" ? true : '
                         f'$lowercase({status_key}) = "closed" ? true : '
                         f'$lowercase({status_key}) = "resolved" ? true : false')
    else:
        resolved_expr = "false"

    if escal_key:
        ev = payload.get(escal_key)
        escal_expr = escal_key if isinstance(ev, bool) else f"$boolean({escal_key})"
    else:
        escal_expr = "false"

    raw_expr  = f'({text_key} & "")' if text_key else '""'
    cust_expr = f"$string({cust_key})" if cust_key else '"UNKNOWN"'

    return (
        "{\n"
        f'  "event_id": {id_expr},\n'
        f'  "source": "{source_name.lower()}",\n'
        f'  "timestamp_utc": {ts_expr},\n'
        f'  "channel": {chan_expr},\n'
        f'  "raw_intent": {raw_expr},\n'
        f'  "intent_category": null,\n'
        f'  "sentiment_score": {sent_expr},\n'
        f'  "handle_time_seconds": {handle_expr},\n'
        f'  "resolved": {resolved_expr},\n'
        f'  "escalated": {escal_expr},\n'
        f'  "customer_id": {cust_expr},\n'
        '  "metadata": $\n'
        "}"
    )
