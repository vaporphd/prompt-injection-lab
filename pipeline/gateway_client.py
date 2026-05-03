"""
Gateway Client — sends all LLM requests through the Day 13 gateway.
Never calls OpenAI directly; all traffic goes via http://localhost:8000.
"""

import httpx

GATEWAY_URL = "http://localhost:8000"


def chat(
    messages: list[dict],
    model: str = "gpt-4o-mini",
    temperature: float = 0.3,
    max_tokens: int = 2048,
) -> dict:
    response = httpx.post(
        f"{GATEWAY_URL}/v1/chat/completions",
        json={
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        },
        timeout=60.0,
    )
    response.raise_for_status()
    data = response.json()

    if "error" in data:
        raise RuntimeError(f"Gateway error: {data['error']}")

    return data


def chat_text(
    messages: list[dict],
    **kwargs,
) -> str:
    data = chat(messages, **kwargs)
    return data["choices"][0]["message"]["content"]


def get_security_info(data: dict) -> dict:
    return data.get("security", {})


def get_stats() -> dict:
    response = httpx.get(f"{GATEWAY_URL}/stats", timeout=10.0)
    response.raise_for_status()
    return response.json()
