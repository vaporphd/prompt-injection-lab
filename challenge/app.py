"""
Red Team Challenge — MedPlus AI CTF
Participants try to extract secrets from the hardened bot via prompt injection.
"""

import os
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel

from challenge.rate_limiter import RateLimiter
from challenge.cost_guard import CostGuard
from challenge.audit import AuditLog, log_attempt
from challenge.bot import SYSTEM_PROMPT, SECRETS, check_leaks

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = os.getenv("MODEL", "gpt-4o-mini")
ADMIN_KEY = os.getenv("ADMIN_KEY", "changeme-admin-key")
COST_CAP = float(os.getenv("COST_CAP", "2.0"))

rate_limiter = RateLimiter(max_requests=5, window_seconds=60)
cost_guard = CostGuard(max_cost_usd=COST_CAP)
audit = AuditLog()


@asynccontextmanager
async def lifespan(app: FastAPI):
    cost_guard.load()
    yield
    cost_guard.save()

app = FastAPI(title="MedPlus AI Challenge", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="challenge/static"), name="static")


class ChatRequest(BaseModel):
    message: str


@app.get("/", response_class=HTMLResponse)
async def index():
    return FileResponse("challenge/static/index.html")


@app.post("/api/chat")
async def chat(request: Request, body: ChatRequest):
    client_ip = request.client.host if request.client else "unknown"
    request_id = str(uuid.uuid4())[:8]

    if cost_guard.is_exhausted():
        return JSONResponse(status_code=503, content={
            "error": "Challenge paused — budget exhausted. Try again later.",
            "request_id": request_id,
        })

    allowed, rate_info = rate_limiter.is_allowed(client_ip)
    if not allowed:
        return JSONResponse(status_code=429, content={
            "error": f"Rate limit exceeded. Retry in {rate_info['retry_after']}s.",
            "request_id": request_id,
        }, headers={"Retry-After": str(rate_info["retry_after"])})

    if len(body.message) > 2000:
        return JSONResponse(status_code=400, content={
            "error": "Message too long (max 2000 chars).",
            "request_id": request_id,
        })

    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": body.message},
            ],
            temperature=0.7,
            max_tokens=512,
        )
    except Exception as e:
        return JSONResponse(status_code=502, content={
            "error": "LLM API error",
            "request_id": request_id,
        })

    response_text = response.choices[0].message.content
    usage = response.usage

    tokens = usage.total_tokens if usage else 0
    cost = cost_guard.track(MODEL, usage.prompt_tokens or 0, usage.completion_tokens or 0) if usage else 0

    leaks = check_leaks(response_text)

    if leaks:
        blocked_response = "Извините, произошла ошибка обработки запроса. Пожалуйста, переформулируйте ваш вопрос."
        log_attempt(
            audit=audit,
            request_id=request_id,
            client_ip=client_ip,
            message=body.message,
            response=f"[BLOCKED: {leaks}] {response_text}",
            tokens=tokens,
            cost=cost,
            leaks=leaks,
        )
        return {
            "response": blocked_response,
            "request_id": request_id,
            "leaked": False,
            "flags_found": [],
        }

    log_attempt(
        audit=audit,
        request_id=request_id,
        client_ip=client_ip,
        message=body.message,
        response=response_text,
        tokens=tokens,
        cost=cost,
        leaks=leaks,
    )

    return {
        "response": response_text,
        "request_id": request_id,
        "leaked": False,
        "flags_found": [],
    }


@app.get("/api/scoreboard")
async def scoreboard():
    stats = audit.get_stats()
    return {
        "total_attempts": stats["total"],
        "unique_ips": stats["unique_ips"],
        "successful_extractions": stats["successful"],
        "flags_found": stats["flags_found"],
        "budget_remaining_usd": round(cost_guard.remaining(), 4),
        "budget_total_usd": COST_CAP,
    }


@app.get("/api/audit/download")
async def download_audit(key: str = ""):
    if key != ADMIN_KEY:
        return JSONResponse(status_code=403, content={"error": "Invalid admin key"})
    return FileResponse(
        audit.log_path,
        media_type="application/jsonl",
        filename="challenge_audit.jsonl",
    )


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "budget_remaining": round(cost_guard.remaining(), 4),
        "total_attempts": audit.get_stats()["total"],
    }
