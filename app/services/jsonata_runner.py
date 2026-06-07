"""Execute JSONata expressions via Node.js subprocess."""
import asyncio
import json
import logging
from pathlib import Path

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class JSONataError(Exception):
    pass


async def evaluate(expression: str, payload: dict) -> dict:
    """Run a JSONata expression against payload. Returns transformed dict."""
    script = Path(settings.jsonata_script)
    if not script.exists():
        raise JSONataError(f"JSONata runner script not found: {script}")

    stdin_data = json.dumps({"expression": expression, "payload": payload})

    try:
        proc = await asyncio.create_subprocess_exec(
            settings.node_binary, str(script),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(stdin_data.encode()),
            timeout=settings.jsonata_timeout,
        )
    except asyncio.TimeoutError:
        raise JSONataError("JSONata evaluation timed out")
    except FileNotFoundError:
        raise JSONataError(f"Node.js binary not found: {settings.node_binary}")

    if proc.returncode != 0:
        err = stderr.decode().strip()
        raise JSONataError(f"JSONata runner error: {err}")

    try:
        return json.loads(stdout.decode())
    except json.JSONDecodeError as exc:
        raise JSONataError(f"Invalid JSON output from runner: {exc}")
