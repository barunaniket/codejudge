"""Thin async wrapper around the Ollama HTTP API.

Every LLM interaction in CodeJudge goes through `chat_json`, which asks the
model to answer in a fixed JSON schema (Ollama "structured outputs").
"""
import json

import httpx

from .config import KEEP_ALIVE, NUM_CTX, OLLAMA_URL

TIMEOUT = httpx.Timeout(600.0, connect=5.0)


async def is_up() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3) as c:
            r = await c.get(f"{OLLAMA_URL}/api/version")
            return r.status_code == 200
    except httpx.HTTPError:
        return False


async def list_installed() -> list[str]:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{OLLAMA_URL}/api/tags")
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]


async def running() -> list[dict]:
    """Models currently loaded in memory, with how much sits in VRAM."""
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"{OLLAMA_URL}/api/ps")
        r.raise_for_status()
        return r.json().get("models", [])


async def pull_stream(model: str):
    """Download a model, yielding Ollama's progress messages."""
    async with httpx.AsyncClient(timeout=None) as c:
        async with c.stream("POST", f"{OLLAMA_URL}/api/pull", json={"model": model}) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if line.strip():
                    msg = json.loads(line)
                    if "error" in msg:
                        raise RuntimeError(msg["error"])
                    yield msg


async def load(model: str) -> None:
    """Load a model into GPU memory and keep it there (empty prompt = load only)."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": model, "keep_alive": KEEP_ALIVE, "options": {"num_ctx": NUM_CTX}},
        )
        r.raise_for_status()


async def unload(model: str) -> None:
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        await c.post(f"{OLLAMA_URL}/api/generate", json={"model": model, "keep_alive": 0})


async def chat_json(model: str, system: str, user: str, schema: dict) -> dict:
    """Send one chat turn and get back a dict that matches `schema`."""
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "format": schema,
        "keep_alive": KEEP_ALIVE,
        "options": {"temperature": 0, "seed": 42, "num_ctx": NUM_CTX},
    }
    async with httpx.AsyncClient(timeout=TIMEOUT) as c:
        r = await c.post(f"{OLLAMA_URL}/api/chat", json=payload)
        r.raise_for_status()
        content = r.json()["message"]["content"]
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        return {}
