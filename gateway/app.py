"""
LLM Gateway — HTTP proxy between users and OpenAI API.
Enforces input/output guards, rate limiting, cost tracking, and audit logging.

Usage:
    uvicorn gateway.app:app --reload
"""

import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from openai import OpenAI
from pydantic import BaseModel

from gateway.guards import input_guard, output_guard
from gateway.middleware.rate_limiter import RateLimiter
from gateway.middleware.cost_tracker import CostTracker
from gateway.logging_config import log_request

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEFAULT_MODEL = os.getenv("MODEL", "gpt-4o-mini")
GUARD_MODE = os.getenv("GUARD_MODE", "mask")  # "block" or "mask"

client = OpenAI(api_key=OPENAI_API_KEY)
rate_limiter = RateLimiter(max_requests=int(os.getenv("RATE_LIMIT", "30")), window_seconds=60)
cost_tracker = CostTracker()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield

app = FastAPI(
    title="LLM Gateway",
    description="Secure proxy for OpenAI API with input/output guards",
    version="0.1.0",
    lifespan=lifespan,
)


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str | None = None
    messages: list[Message]
    temperature: float = 0.7
    max_tokens: int = 1024


class GuardWarning(BaseModel):
    warning: str
    detections: list[dict]
    masked_prompt: str | None = None


@app.post("/v1/chat/completions")
async def chat_completions(request: Request, body: ChatRequest):
    client_ip = request.client.host if request.client else "unknown"
    model = body.model or DEFAULT_MODEL

    # --- Rate Limiting ---
    allowed, rate_info = rate_limiter.is_allowed(client_ip)
    if not allowed:
        log_request(client_ip, [], blocked=True, block_reason="rate_limit")
        return JSONResponse(
            status_code=429,
            content={"error": "Rate limit exceeded", "retry_after": rate_info["retry_after"]},
            headers={"Retry-After": str(rate_info["retry_after"])},
        )

    # --- Input Guard ---
    messages_dicts = [m.model_dump() for m in body.messages]
    user_messages = [m for m in messages_dicts if m["role"] == "user"]

    all_detections = []
    for msg in user_messages:
        result = input_guard.guard(msg["content"], mode=GUARD_MODE)
        if not result.is_clean:
            all_detections.extend(result.detections)
            if GUARD_MODE == "block":
                log_request(
                    client_ip, messages_dicts, blocked=True,
                    block_reason="input_guard",
                    input_guard_result={
                        "mode": "block",
                        "detections": [{"category": d.category, "value": d.value[:20] + "..."} for d in result.detections],
                    },
                )
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": "Request blocked by Input Guard",
                        "warning": "Sensitive data detected in prompt. Remove secrets before sending.",
                        "detections": [{"category": d.category, "masked": d.masked} for d in result.detections],
                    },
                )
            else:
                msg["content"] = result.masked_text

    # --- Proxy to OpenAI ---
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages_dicts,
            temperature=body.temperature,
            max_tokens=body.max_tokens,
        )
    except Exception as e:
        log_request(client_ip, messages_dicts, blocked=True, block_reason=f"openai_error: {e}")
        return JSONResponse(status_code=502, content={"error": f"LLM API error: {e}"})

    response_text = response.choices[0].message.content
    usage = response.usage

    # --- Cost Tracking ---
    cost_entry = None
    if usage:
        cost_entry = cost_tracker.track(model, usage.prompt_tokens, usage.completion_tokens)

    # --- Output Guard ---
    system_prompt = next((m["content"] for m in messages_dicts if m["role"] == "system"), None)
    output_result = output_guard.guard(response_text, system_prompt=system_prompt)

    output_guard_log = None
    if not output_result.is_clean:
        output_guard_log = {
            "findings": [{"category": f.category, "severity": f.severity} for f in output_result.findings],
            "blocked": output_result.blocked,
        }
        if output_result.blocked:
            log_request(
                client_ip, messages_dicts,
                blocked=True, block_reason="output_guard",
                output_guard_result=output_guard_log,
                cost={"tokens": cost_entry.total_tokens, "cost_usd": cost_entry.cost_usd} if cost_entry else None,
            )
            return JSONResponse(
                status_code=200,
                content={
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "content": "Response blocked by security filter. The model's response contained potentially sensitive content.",
                        },
                        "finish_reason": "content_filter",
                    }],
                    "usage": {
                        "prompt_tokens": usage.prompt_tokens if usage else 0,
                        "completion_tokens": usage.completion_tokens if usage else 0,
                    },
                    "security": {"output_guard": "triggered", "severity": output_result.severity},
                },
            )

    # --- Log & Return ---
    input_guard_log = None
    if all_detections:
        input_guard_log = {
            "mode": GUARD_MODE,
            "detections": [{"category": d.category} for d in all_detections],
        }

    log_request(
        client_ip, messages_dicts,
        input_guard_result=input_guard_log,
        output_guard_result=output_guard_log,
        response_text=response_text,
        cost={"tokens": cost_entry.total_tokens, "cost_usd": cost_entry.cost_usd} if cost_entry else None,
    )

    return {
        "choices": [{
            "message": {"role": "assistant", "content": response_text},
            "finish_reason": response.choices[0].finish_reason,
        }],
        "model": model,
        "usage": {
            "prompt_tokens": usage.prompt_tokens if usage else 0,
            "completion_tokens": usage.completion_tokens if usage else 0,
            "total_tokens": usage.total_tokens if usage else 0,
        },
        "security": {
            "input_guard": "masked" if all_detections else "clean",
            "output_guard": "clean" if output_result.is_clean else "flagged",
        },
    }


@app.get("/stats")
async def stats():
    return cost_tracker.stats()


@app.get("/health")
async def health():
    return {"status": "ok", "guard_mode": GUARD_MODE}
