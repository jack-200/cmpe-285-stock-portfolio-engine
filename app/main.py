"""
This is the main entry point for the FastAPI server.
It handles the web routes (endpoints), serves the static dashboard pages,
and does some basic rate limiting so users don't spam the server.
"""

import os
import time
import fastapi
import fastapi.responses
import fastapi.staticfiles
import uvicorn
import starlette.requests
from app import prompts
from app import config
from app import schemas
from app import database
from app.services import engine
from app.services import llm

app = fastapi.FastAPI(title="Stock Portfolio Suggestion Engine")

_rate_buckets = {}


def check_rate_limit(host: str, route: str, max_requests: int, window_s: float) -> None:
    now = time.time()
    key = f"{host}:{route}"
    bucket = _rate_buckets.setdefault(key, [])
    bucket[:] = [t for t in bucket if now - t < window_s]
    if len(bucket) >= max_requests:
        raise fastapi.HTTPException(
            status_code=429,
            detail="Too many requests for this endpoint; wait up to a minute and try again.",
        )
    bucket.append(now)


@app.post("/api/suggest", response_model=schemas.PortfolioResponse)
async def get_suggestion(
    payload: schemas.PortfolioRequest, req: starlette.requests.Request
):
    check_rate_limit(
        req.client.host or "unknown",
        "suggest",
        config.RATE_SUGGEST_PER_MIN,
        config.RATE_WINDOW_S,
    )
    try:
        for strategy in payload.strategies:
            if strategy not in config.STRATEGIES:
                raise fastapi.HTTPException(
                    status_code=400, detail=f"Invalid strategy: {strategy}"
                )
        return engine.generate_portfolio_suggestion(
            payload.amount,
            payload.strategies,
            payload.risk_profile,
            payload.history_period,
        )
    except fastapi.HTTPException:
        raise
    except Exception as e:
        raise fastapi.HTTPException(status_code=500, detail=str(e))


@app.get("/api/history")
async def get_portfolio_history():
    return database.get_history()


@app.post("/api/chat", response_model=schemas.ChatResponse)
async def chat_endpoint(body: schemas.ChatRequest, req: starlette.requests.Request):
    check_rate_limit(
        req.client.host or "unknown",
        "chat",
        config.RATE_CHAT_PER_MIN,
        config.RATE_WINDOW_S,
    )
    return llm.chat_reply(body)


@app.post("/api/chat/stream")
async def chat_stream_endpoint(
    body: schemas.ChatRequest, req: starlette.requests.Request
):
    check_rate_limit(
        req.client.host or "unknown",
        "chat_stream",
        config.RATE_CHAT_PER_MIN,
        config.RATE_WINDOW_S,
    )
    return fastapi.responses.StreamingResponse(
        llm.chat_reply_stream(body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/health")
async def health():
    rr = llm.resolve_llm_endpoint("rationale")
    cr = llm.resolve_llm_endpoint("chat")
    return {
        "ok": True,
        "prompt_version": prompts.PROMPT_VERSION,
        "llm_backend": (os.environ.get("LLM_BACKEND") or config.DEFAULT_LLM_BACKEND)
        .strip()
        .lower(),
        "llm_rationale_configured": rr is not None,
        "llm_chat_configured": cr is not None,
        "rationale_model": rr[2] if rr else None,
        "chat_model": cr[2] if cr else None,
        "rate_limits": {
            "suggest_per_minute": config.RATE_SUGGEST_PER_MIN,
            "chat_per_minute": config.RATE_CHAT_PER_MIN,
            "window_seconds": int(config.RATE_WINDOW_S),
        },
    }


@app.get("/")
async def read_index():
    return fastapi.responses.FileResponse("static/index.html")


@app.get("/{filename}")
async def get_static_asset(filename: str):
    # This single handler covers style.css, script.js, hero.png, and favicon.svg dynamically!
    path = os.path.join("static", filename)
    if os.path.exists(path):
        return fastapi.responses.FileResponse(path)
    raise fastapi.HTTPException(status_code=404)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=config.DEFAULT_PORT)
