# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "fastapi",
#     "jinja2",
#     "openai",
#     "pandas",
#     "pydantic",
#     "uvicorn",
#     "yfinance",
# ]
# ///

import json
import os
import re
import time
import typing
import datetime

import fastapi
import fastapi.responses
import fastapi.staticfiles
import pandas
import pydantic
import prompts
import uvicorn
import yfinance
from starlette.requests import Request

RationaleOrigin = typing.Literal["all_llm", "partial_llm", "fallback"]
RationaleSource = typing.Literal["llm", "fallback"]
LLMKind = typing.Literal["rationale", "chat"]

# --- Configuration & Constants ---
HISTORY_FILE = "history.json"
STRATEGIES = {
    "Ethical Investing": ["AAPL", "ADBE", "NSRGY"],
    "Growth Investing": ["NVDA", "AMZN", "TSLA"],
    "Index Investing": ["VTI", "IXUS", "ILTB"],
    "Quality Investing": ["MSFT", "GOOGL", "V"],
    "Value Investing": ["BRK-B", "JNJ", "PFE"],
}

# Risk profiles drive (a) how much of the pie each selected strategy gets and
# (b) how the dollars are tilted between tickers inside a strategy. Multipliers
# are normalized so the dollar amounts always sum to the user's input.
RiskProfile = typing.Literal["Conservative", "Moderate", "Aggressive"]
DEFAULT_RISK_PROFILE: RiskProfile = "Moderate"

STRATEGY_RISK_WEIGHTS: typing.Dict[str, typing.Dict[str, float]] = {
    "Conservative": {
        "Ethical Investing": 0.9,
        "Growth Investing": 0.5,
        "Index Investing": 1.4,
        "Quality Investing": 1.3,
        "Value Investing": 1.2,
    },
    "Moderate": {
        "Ethical Investing": 1.0,
        "Growth Investing": 1.0,
        "Index Investing": 1.0,
        "Quality Investing": 1.0,
        "Value Investing": 1.0,
    },
    "Aggressive": {
        "Ethical Investing": 1.1,
        "Growth Investing": 1.7,
        "Index Investing": 0.6,
        "Quality Investing": 0.9,
        "Value Investing": 0.8,
    },
}

# Per-ticker tilt inside a strategy. Missing symbols fall back to 1.0.
# Conservative favors bonds/large caps; Aggressive favors high-beta growth.
TICKER_RISK_TILT: typing.Dict[str, typing.Dict[str, float]] = {
    "Conservative": {
        "ILTB": 1.6, "VTI": 1.1, "IXUS": 0.9,
        "BRK-B": 1.2, "JNJ": 1.3, "PFE": 1.0,
        "MSFT": 1.1, "GOOGL": 1.0, "V": 1.1,
        "NVDA": 0.7, "AMZN": 1.0, "TSLA": 0.5,
        "AAPL": 1.1, "ADBE": 1.0, "NSRGY": 1.3,
    },
    "Moderate": {},
    "Aggressive": {
        "ILTB": 0.5, "VTI": 1.0, "IXUS": 1.1,
        "BRK-B": 0.9, "JNJ": 0.8, "PFE": 0.9,
        "MSFT": 1.0, "GOOGL": 1.1, "V": 1.0,
        "NVDA": 1.5, "AMZN": 1.2, "TSLA": 1.5,
        "AAPL": 1.1, "ADBE": 1.2, "NSRGY": 0.8,
    },
}

# yfinance period strings the UI is allowed to ask for. "5d" preserves the
# original assignment spec (5-day weekly trend) as the default.
HistoryPeriod = typing.Literal["5d", "1mo", "3mo", "1y"]
DEFAULT_HISTORY_PERIOD: HistoryPeriod = "5d"
ALLOWED_HISTORY_PERIODS: typing.Tuple[HistoryPeriod, ...] = ("5d", "1mo", "3mo", "1y")
# Underlying yfinance fetch window — always pull at least a year so any UI
# period can be served from one call, then trimmed for the chart.
YFINANCE_FETCH_PERIOD = "1y"
PERIOD_TRIM_DAYS: typing.Dict[HistoryPeriod, typing.Optional[int]] = {
    "5d": 5,
    "1mo": 22,
    "3mo": 66,
    "1y": None,
}

DEFAULT_SECTOR_LABEL = "Diversified / ETF"

# Fallback blurbs when LLM rationales are off or the local/cloud model fails.
STOCK_SELECTION_RATIONALE: typing.Dict[str, typing.Dict[str, str]] = {
    "Ethical Investing": {
        "AAPL": "Often cited in ESG-focused lists for supply-chain programs and running corporate operations on renewable power.",
        "ADBE": "Software-led model supports paperless workflows and lower direct physical footprint than heavy industry.",
        "NSRGY": "Consumer staples exposure; global nutrition and packaged brands frequently appear in socially tilted defensive sleeves.",
    },
    "Growth Investing": {
        "NVDA": "Datacenter and AI chip demand have driven multiyear revenue growth well above the broad market.",
        "AMZN": "E-commerce and AWS provide scaled platforms where reinvestment has historically supported high growth rates.",
        "TSLA": "Pure-play EV and energy exposure tied to revenue expansion expectations rather than mature cash cows.",
    },
    "Index Investing": {
        "VTI": "Total U.S. market ETF: cheap, diversified beta without picking individual names.",
        "IXUS": "Developed/ex-U.S. equities add geographic diversification next to a U.S. core holding.",
        "ILTB": "Longer-duration Treasury-heavy bond ETF for ballast and diversification versus stocks.",
    },
    "Quality Investing": {
        "MSFT": "Recurring cloud and productivity revenue, strong margins, and a durable balance sheet.",
        "GOOGL": "Dominant consumer internet franchise with deep moats and substantial cash generation.",
        "V": "Asset-light payments network with powerful scale economics and high returns on capital.",
    },
    "Value Investing": {
        "BRK-B": "Diversified operating businesses and equities chosen with a long-term intrinsic-value mindset.",
        "JNJ": "Defensive healthcare cash flows and a long dividend record typical of quality-at-reasonable-price screens.",
        "PFE": "Mature pharma cash generation and valuation spreads that value investors often harvest after volatility.",
    },
}

# Magic Number Constants
MIN_INVESTMENT_AMOUNT = 5000
MIN_STRATEGIES = 1
MAX_STRATEGIES = 2
MAX_HISTORY_ENTRIES = 10
HISTORICAL_DAYS_COUNT = 5
ROUNDING_DECIMALS = 2
DEFAULT_PORT = 8000
DEFAULT_LLM_BACKEND = "ollama"
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2"
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"
OLLAMA_DUMMY_API_KEY = "ollama"
DEFAULT_TIMEOUT_RATIONALES_S = 120.0
DEFAULT_TIMEOUT_CHAT_S = 180.0
CHAT_MAX_MESSAGES = 24
CHAT_MAX_CHARS_PER_MESSAGE = 2500
CHAT_TEMPERATURE = 0.55
YFINANCE_MAX_ATTEMPTS = 3
RATE_SUGGEST_PER_MIN = 30
RATE_CHAT_PER_MIN = 60
RATE_WINDOW_S = 60.0

_rate_buckets: typing.Dict[str, typing.List[float]] = {}


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


def openai_client_and_model(
    kind: LLMKind,
) -> typing.Optional[typing.Tuple[typing.Any, str]]:
    """Return (OpenAI client, model_id), or None if LLM is disabled."""
    from openai import OpenAI

    resolved = resolve_llm_endpoint(kind)
    if not resolved:
        return None
    api_key, base_url, model, timeout_s = resolved
    client_kw: typing.Dict[str, typing.Any] = {
        "api_key": api_key,
        "timeout": timeout_s,
    }
    if base_url:
        client_kw["base_url"] = base_url
    return OpenAI(**client_kw), model


def _ollama_openai_base_url(host: str) -> str:
    h = host.strip().rstrip("/")
    if h.endswith("/v1"):
        return h
    return f"{h}/v1"


def resolve_llm_endpoint(
    kind: LLMKind,
) -> typing.Optional[typing.Tuple[str, typing.Optional[str], str, float]]:
    """Return (api_key, base_url_or_none, model_id, timeout_seconds), or None if LLM disabled."""
    raw = (os.environ.get("LLM_BACKEND") or DEFAULT_LLM_BACKEND).strip().lower()
    if raw in ("none", "off", "0", "false", "disabled"):
        return None

    timeout_r = float(
        os.environ.get("LLM_TIMEOUT_RATIONALES_S", str(DEFAULT_TIMEOUT_RATIONALES_S))
    )
    timeout_c = float(os.environ.get("LLM_TIMEOUT_CHAT_S", str(DEFAULT_TIMEOUT_CHAT_S)))
    timeout_s = timeout_r if kind == "rationale" else timeout_c

    if raw in ("ollama", "local"):
        host = os.environ.get("OLLAMA_HOST", DEFAULT_OLLAMA_HOST).strip() or DEFAULT_OLLAMA_HOST
        base = _ollama_openai_base_url(host)
        if kind == "rationale":
            model = (
                os.environ.get("LLM_MODEL_RATIONALES")
                or os.environ.get("LLM_MODEL")
                or DEFAULT_OLLAMA_MODEL
            ).strip() or DEFAULT_OLLAMA_MODEL
        else:
            model = (
                os.environ.get("LLM_MODEL_CHAT")
                or os.environ.get("LLM_MODEL")
                or DEFAULT_OLLAMA_MODEL
            ).strip() or DEFAULT_OLLAMA_MODEL
        key = os.environ.get("OPENAI_API_KEY", OLLAMA_DUMMY_API_KEY).strip() or OLLAMA_DUMMY_API_KEY
        return (key, base, model, timeout_s)

    if raw == "openai":
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not key:
            return None
        base = os.environ.get("OPENAI_BASE_URL", "").strip() or None
        if kind == "rationale":
            model = (
                os.environ.get("LLM_MODEL_RATIONALES")
                or os.environ.get("LLM_MODEL")
                or DEFAULT_OPENAI_MODEL
            ).strip() or DEFAULT_OPENAI_MODEL
        else:
            model = (
                os.environ.get("LLM_MODEL_CHAT")
                or os.environ.get("LLM_MODEL")
                or DEFAULT_OPENAI_MODEL
            ).strip() or DEFAULT_OPENAI_MODEL
        return (key, base, model, timeout_s)

    return None


def llm_rationales_configured() -> bool:
    return resolve_llm_endpoint("rationale") is not None


def _parse_json_object_from_llm(text: str) -> typing.Dict[str, typing.Any]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```\s*$", "", raw)
    return json.loads(raw)


def _rationale_map_from_llm_text(content: str, symbols: typing.List[str]) -> typing.Dict[str, str]:
    parsed = _parse_json_object_from_llm(content)
    out: typing.Dict[str, str] = {}
    for sym in symbols:
        val = parsed.get(sym)
        if isinstance(val, str) and val.strip():
            out[sym] = val.strip()
    return out


def fetch_selection_rationales_llm(
    symbols: typing.List[str],
    selected_strategies: typing.List[str],
    names_by_symbol: typing.Dict[str, str],
) -> typing.Dict[str, str]:
    """One batched call; keys must match symbols. Uses Ollama (default) or OpenAI-compatible APIs."""
    cm = openai_client_and_model("rationale")
    if not cm:
        return {}
    client, model = cm

    lines = [f"- {sym} ({names_by_symbol.get(sym, sym)})" for sym in symbols]
    user_msg = prompts.rationale_user_message(symbols, selected_strategies, lines)

    params: typing.Dict[str, typing.Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompts.rationale_system_message()},
            {"role": "user", "content": user_msg},
        ],
        "temperature": 0.35,
    }

    content = ""
    try:
        completion = client.chat.completions.create(
            **params, response_format={"type": "json_object"}
        )
        content = (completion.choices[0].message.content or "").strip()
    except Exception:
        try:
            completion = client.chat.completions.create(**params)
            content = (completion.choices[0].message.content or "").strip()
        except Exception:
            return {}

    out: typing.Dict[str, str] = {}
    try:
        out = _rationale_map_from_llm_text(content, symbols)
    except (json.JSONDecodeError, TypeError, ValueError):
        out = {}

    if len(out) >= len(symbols):
        return out

    try:
        repair_msg = prompts.rationale_json_repair_user_message(symbols, content)
        completion2 = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompts.rationale_system_message()},
                {"role": "user", "content": repair_msg},
            ],
            temperature=0.2,
        )
        content2 = (completion2.choices[0].message.content or "").strip()
        out = _rationale_map_from_llm_text(content2, symbols)
    except Exception:
        pass

    return out


def build_selection_rationales(
    symbols: typing.List[str],
    selected_strategies: typing.List[str],
    names_by_symbol: typing.Dict[str, str],
) -> typing.Tuple[typing.Dict[str, str], typing.Dict[str, RationaleSource]]:
    llm_part: typing.Dict[str, str] = {}
    if llm_rationales_configured():
        try:
            llm_part = fetch_selection_rationales_llm(
                symbols, selected_strategies, names_by_symbol
            )
        except Exception:
            llm_part = {}

    merged: typing.Dict[str, str] = {}
    sources: typing.Dict[str, RationaleSource] = {}
    for sym in symbols:
        text = llm_part.get(sym, "").strip()
        if text:
            merged[sym] = text
            sources[sym] = "llm"
        else:
            merged[sym] = fallback_selection_rationale_for_symbol(
                sym, selected_strategies
            )
            sources[sym] = "fallback"
    return merged, sources


def rationale_origin_from_sources(sources: typing.Dict[str, RationaleSource]) -> RationaleOrigin:
    vals = [sources[s] for s in sorted(sources)]
    if not vals:
        return "fallback"
    llm_n = sum(1 for v in vals if v == "llm")
    if llm_n == len(vals):
        return "all_llm"
    if llm_n > 0:
        return "partial_llm"
    return "fallback"


def active_llm_meta() -> typing.Tuple[typing.Optional[str], typing.Optional[str]]:
    """(backend_label, model_id) when LLM path is enabled, else (None, None)."""
    resolved = resolve_llm_endpoint("rationale")
    if not resolved:
        return None, None
    _key, _base, model, _timeout = resolved
    raw = (os.environ.get("LLM_BACKEND") or DEFAULT_LLM_BACKEND).strip().lower()
    if raw in ("ollama", "local"):
        return "ollama", model
    if raw == "openai":
        return "openai", model
    return None, model


# --- Pydantic Models ---
class HistoryEntry(pydantic.BaseModel):
    date: str
    value: float


class StockInfo(pydantic.BaseModel):
    symbol: str
    name: str
    price: float
    shares: float
    allocation_amount: float
    logo_url: typing.Optional[str] = None
    selection_rationale: str = ""
    rationale_source: RationaleSource = "fallback"
    sector: str = DEFAULT_SECTOR_LABEL
    period_return_pct: typing.Optional[float] = None


class SectorAllocation(pydantic.BaseModel):
    sector: str
    amount: float
    pct: float


class PortfolioRequest(pydantic.BaseModel):
    amount: float = pydantic.Field(
        ...,
        ge=MIN_INVESTMENT_AMOUNT,
        description=f"Amount to invest (Min ${MIN_INVESTMENT_AMOUNT})",
    )
    strategies: typing.List[str] = pydantic.Field(
        ...,
        min_length=MIN_STRATEGIES,
        max_length=MAX_STRATEGIES,
        description=f"Select {MIN_STRATEGIES} or {MAX_STRATEGIES} strategies",
    )
    risk_profile: RiskProfile = pydantic.Field(
        default=DEFAULT_RISK_PROFILE,
        description="Conservative / Moderate / Aggressive — drives weighted allocation.",
    )
    history_period: HistoryPeriod = pydantic.Field(
        default=DEFAULT_HISTORY_PERIOD,
        description="Trend window: 5d / 1mo / 3mo / 1y.",
    )


class PortfolioResponse(pydantic.BaseModel):
    stocks: typing.List[StockInfo]
    total_value: float
    weekly_history: typing.List[HistoryEntry]
    rationale_origin: RationaleOrigin = "fallback"
    rationale_llm_backend: typing.Optional[str] = None
    rationale_llm_model: typing.Optional[str] = None
    warnings: typing.List[str] = pydantic.Field(default_factory=list)
    omitted_symbols: typing.List[str] = pydantic.Field(default_factory=list)
    risk_profile: RiskProfile = DEFAULT_RISK_PROFILE
    history_period: HistoryPeriod = DEFAULT_HISTORY_PERIOD
    period_return_pct: typing.Optional[float] = None
    sector_allocations: typing.List[SectorAllocation] = pydantic.Field(default_factory=list)
    selected_strategies: typing.List[str] = pydantic.Field(default_factory=list)
    amount_requested: typing.Optional[float] = None


class ChatMessage(pydantic.BaseModel):
    role: typing.Literal["user", "assistant"]
    content: str = pydantic.Field(..., max_length=CHAT_MAX_CHARS_PER_MESSAGE)


class ChatPortfolioStockSnap(pydantic.BaseModel):
    symbol: str
    name: str = ""
    allocation_amount: typing.Optional[float] = None
    selection_rationale: str = ""
    sector: typing.Optional[str] = None
    period_return_pct: typing.Optional[float] = None


class ChatSectorSnap(pydantic.BaseModel):
    sector: str
    pct: float


class ChatPortfolioSnapshot(pydantic.BaseModel):
    total_value: typing.Optional[float] = None
    stocks: typing.List[ChatPortfolioStockSnap] = pydantic.Field(default_factory=list)
    rationale_origin: typing.Optional[str] = None
    risk_profile: typing.Optional[str] = None
    history_period: typing.Optional[str] = None
    period_return_pct: typing.Optional[float] = None
    sector_allocations: typing.List[ChatSectorSnap] = pydantic.Field(default_factory=list)


class ChatRequest(pydantic.BaseModel):
    messages: typing.List[ChatMessage] = pydantic.Field(
        ...,
        min_length=1,
        max_length=CHAT_MAX_MESSAGES,
    )
    portfolio_context: typing.Optional[ChatPortfolioSnapshot] = None


class ChatResponse(pydantic.BaseModel):
    reply: str
    llm_available: bool = True
    ok: bool = True


def _chat_system_and_messages(request: ChatRequest) -> typing.Tuple[str, typing.List[typing.Dict[str, str]]]:
    strategies_blob = json.dumps(STRATEGIES, indent=2)
    ctx_blob = ""
    if request.portfolio_context is not None:
        ctx_blob = (
            "\n\nOptional snapshot of the user’s latest portfolio result in the UI:\n"
            + request.portfolio_context.model_dump_json(indent=2)
        )
    system_prompt = prompts.chat_system_prompt(strategies_blob, ctx_blob)
    api_messages: typing.List[typing.Dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for msg in request.messages:
        api_messages.append({"role": msg.role, "content": msg.content})
    return system_prompt, api_messages


def chat_reply(request: ChatRequest) -> ChatResponse:
    """Assistant for strategies, app behavior, and optional last-portfolio snapshot."""
    cm = openai_client_and_model("chat")
    if not cm:
        return ChatResponse(
            reply=(
                "Chat needs an LLM. Configure LLM_BACKEND (ollama or openai) and run "
                "./scripts/setup-local-llm.sh or set OPENAI_API_KEY — see .env.example."
            ),
            llm_available=False,
            ok=False,
        )

    client, model = cm
    _, api_messages = _chat_system_and_messages(request)

    try:
        completion = client.chat.completions.create(
            model=model,
            messages=api_messages,
            temperature=CHAT_TEMPERATURE,
        )
        text = completion.choices[0].message.content
        reply = (text or "").strip()
        if not reply:
            reply = "(Empty response from model.)"
        return ChatResponse(reply=reply, llm_available=True, ok=True)
    except Exception as e:
        return ChatResponse(
            reply=f"Model error: {str(e)[:400]}",
            llm_available=True,
            ok=False,
        )


def chat_reply_stream(body: ChatRequest) -> typing.Iterator[str]:
    """SSE chunks: `data: {"t":"..."}\\n\\n` or errors / `[DONE]`."""
    cm = openai_client_and_model("chat")
    if not cm:
        yield f"data: {json.dumps({'error': 'no_llm'})}\n\n"
        return

    client, model = cm
    _, api_messages = _chat_system_and_messages(body)

    try:
        stream = client.chat.completions.create(
            model=model,
            messages=api_messages,
            temperature=CHAT_TEMPERATURE,
            stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta.content or ""
            if delta:
                yield f"data: {json.dumps({'t': delta})}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': 'stream', 'message': str(e)[:400]})}\n\n"


# --- History Management Logic ---
def save_to_history(portfolio_data: dict):
    """Saves a portfolio suggestion to a local JSON file."""
    history = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r") as f:
            try:
                history = json.load(f)
            except json.JSONDecodeError:
                history = []

    entry = {"timestamp": datetime.datetime.now().isoformat(), "data": portfolio_data}
    history.insert(0, entry)
    history = history[:MAX_HISTORY_ENTRIES]

    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=4)


def get_history():
    """Retrieves the last 10 portfolio suggestions."""
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


# --- Stock Data Fetching Logic ---
def _resolve_sector(info: typing.Dict[str, typing.Any]) -> str:
    """ETFs often report empty `sector`; fall back to quoteType-aware label."""
    sec = (info.get("sector") or "").strip()
    if sec:
        return sec
    qt = (info.get("quoteType") or "").strip().upper()
    if qt == "ETF":
        cat = (info.get("category") or "").strip()
        return cat or DEFAULT_SECTOR_LABEL
    return DEFAULT_SECTOR_LABEL


def _try_fetch_single_symbol(symbol: str) -> typing.Optional[typing.Dict[str, typing.Any]]:
    ticker = yfinance.Ticker(symbol)
    info = ticker.info or {}
    current_price = info.get("regularMarketPrice") or info.get("currentPrice")
    hist_full = ticker.history(period=YFINANCE_FETCH_PERIOD)
    if current_price is None:
        if hist_full.empty:
            return None
        current_price = float(hist_full["Close"].iloc[-1])
    else:
        current_price = float(current_price)
    if current_price <= 0:
        return None

    name = info.get("longName") or info.get("shortName") or symbol

    return {
        "name": name,
        "current_price": current_price,
        "history": hist_full["Close"] if not hist_full.empty else None,
        "logo_url": info.get("logo_url"),
        "sector": _resolve_sector(info),
    }


def fetch_stock_data_partitioned(
    symbols: typing.List[str],
) -> typing.Tuple[typing.Dict[str, typing.Any], typing.List[str], typing.List[str]]:
    """Per-symbol retries; omit failures and return warnings (currency + omissions)."""
    results: typing.Dict[str, typing.Any] = {}
    omitted: typing.List[str] = []
    for symbol in symbols:
        row: typing.Optional[typing.Dict[str, typing.Any]] = None
        for attempt in range(YFINANCE_MAX_ATTEMPTS):
            try:
                row = _try_fetch_single_symbol(symbol)
                if row:
                    break
            except Exception:
                row = None
            time.sleep(0.35 * (2**attempt))
        if row:
            results[symbol] = row
        else:
            omitted.append(symbol)

    warnings: typing.List[str] = []
    if omitted:
        warnings.append(
            "No live quote for "
            + ", ".join(omitted)
            + ". Your amount was split only across symbols we could price."
        )
    return results, omitted, warnings


def fallback_selection_rationale_for_symbol(
    symbol: str, selected_strategies: typing.List[str]
) -> str:
    """Static fallback when LLM output is missing."""
    parts: typing.List[str] = []
    seen: typing.Set[str] = set()
    for strategy in selected_strategies:
        blurb = STOCK_SELECTION_RATIONALE.get(strategy, {}).get(symbol)
        if blurb and blurb not in seen:
            seen.add(blurb)
            parts.append(blurb)
    return " ".join(parts)


# --- Allocation & Aggregation Helpers ---
def compute_weighted_allocations(
    amount: float,
    selected_strategies: typing.List[str],
    risk_profile: RiskProfile,
    available_symbols: typing.Set[str],
) -> typing.Dict[str, float]:
    """Split `amount` across `available_symbols` using risk-tilted weights.

    1) Each selected strategy gets a slice proportional to STRATEGY_RISK_WEIGHTS.
       Strategies with zero priceable symbols contribute nothing (their slice
       gets re-normalized into the remaining ones).
    2) Inside a strategy slice, the dollars are split by per-ticker tilt
       (TICKER_RISK_TILT), restricted to priceable symbols.
    3) A symbol that appears in multiple selected strategies sums the slices.

    The returned dict always sums to `amount` (within float epsilon).
    """
    strat_weights = STRATEGY_RISK_WEIGHTS.get(
        risk_profile, STRATEGY_RISK_WEIGHTS[DEFAULT_RISK_PROFILE]
    )
    ticker_tilt = TICKER_RISK_TILT.get(risk_profile, {})

    effective: typing.Dict[str, float] = {}
    for strategy in selected_strategies:
        tickers_alive = [s for s in STRATEGIES.get(strategy, []) if s in available_symbols]
        if not tickers_alive:
            continue
        effective[strategy] = strat_weights.get(strategy, 1.0)

    total_strat_w = sum(effective.values())
    if total_strat_w <= 0:
        return {sym: amount / max(len(available_symbols), 1) for sym in available_symbols}

    allocations: typing.Dict[str, float] = {sym: 0.0 for sym in available_symbols}
    for strategy, strat_w in effective.items():
        strat_amount = amount * (strat_w / total_strat_w)
        tickers_alive = [s for s in STRATEGIES[strategy] if s in available_symbols]
        tilts = [ticker_tilt.get(sym, 1.0) for sym in tickers_alive]
        sum_tilt = sum(tilts) or float(len(tickers_alive))
        for sym, tilt in zip(tickers_alive, tilts):
            share = (tilt / sum_tilt) if sum_tilt > 0 else (1.0 / len(tickers_alive))
            allocations[sym] += strat_amount * share

    return allocations


def trim_history_for_period(
    df: pandas.DataFrame, period: HistoryPeriod
) -> pandas.DataFrame:
    """Trim the full 1y dataframe down to what the UI period asked for."""
    n = PERIOD_TRIM_DAYS.get(period)
    if n is None:
        return df
    return df.tail(n)


def build_sector_allocations(
    stocks: typing.List[StockInfo], total_allocated: float
) -> typing.List[SectorAllocation]:
    bucket: typing.Dict[str, float] = {}
    for s in stocks:
        bucket[s.sector] = bucket.get(s.sector, 0.0) + s.allocation_amount
    out: typing.List[SectorAllocation] = []
    denom = total_allocated if total_allocated > 0 else 1.0
    for sec, amt in sorted(bucket.items(), key=lambda kv: kv[1], reverse=True):
        out.append(
            SectorAllocation(
                sector=sec,
                amount=round(amt, ROUNDING_DECIMALS),
                pct=round((amt / denom) * 100.0, ROUNDING_DECIMALS),
            )
        )
    return out


# --- Core Portfolio Engine Logic ---
def generate_portfolio_suggestion(
    amount: float,
    selected_strategies: typing.List[str],
    risk_profile: RiskProfile = DEFAULT_RISK_PROFILE,
    history_period: HistoryPeriod = DEFAULT_HISTORY_PERIOD,
) -> PortfolioResponse:
    """Core engine logic to map strategies to stocks and calculate allocations."""
    symbols = []
    for strategy in selected_strategies:
        if strategy in STRATEGIES:
            symbols.extend(STRATEGIES[strategy])

    symbols = list(set(symbols))
    market_data, omitted_symbols, fetch_warnings = fetch_stock_data_partitioned(symbols)
    if not market_data:
        raise fastapi.HTTPException(
            status_code=502,
            detail="Could not fetch market data for any symbol. Check your network and try again.",
        )

    symbols_ok = sorted(market_data.keys())
    allocations = compute_weighted_allocations(
        amount=amount,
        selected_strategies=selected_strategies,
        risk_profile=risk_profile,
        available_symbols=set(symbols_ok),
    )

    names_by_symbol = {s: str(market_data[s]["name"]) for s in symbols_ok}
    rationales, rationale_sources = build_selection_rationales(
        symbols_ok, selected_strategies, names_by_symbol
    )
    rationale_origin = rationale_origin_from_sources(rationale_sources)
    llm_backend_meta, llm_model_meta = active_llm_meta()

    portfolio_stocks: typing.List[StockInfo] = []
    total_value = 0.0
    history_agg: typing.Dict[str, typing.Any] = {}

    for symbol in symbols_ok:
        data = market_data[symbol]
        price = float(data["current_price"])
        alloc = float(allocations.get(symbol, 0.0))
        shares = alloc / price if price > 0 else 0.0

        portfolio_stocks.append(
            StockInfo(
                symbol=symbol,
                name=data["name"],
                price=price,
                shares=shares,
                allocation_amount=round(alloc, ROUNDING_DECIMALS),
                logo_url=data.get("logo_url"),
                selection_rationale=rationales.get(symbol, ""),
                rationale_source=rationale_sources.get(symbol, "fallback"),
                sector=data.get("sector") or DEFAULT_SECTOR_LABEL,
            )
        )

        total_value += shares * price
        if data.get("history") is not None and not data["history"].empty:
            history_agg[symbol] = data["history"]

    weekly_history: typing.List[HistoryEntry] = []
    period_return_pct: typing.Optional[float] = None
    if history_agg:
        df_full = pandas.DataFrame(history_agg).dropna()
        df_hist = trim_history_for_period(df_full, history_period)
        if not df_hist.empty:
            stocks_by_sym = {s.symbol: s for s in portfolio_stocks}
            for date, row in df_hist.iterrows():
                day_total = 0.0
                for sym in df_hist.columns:
                    st = stocks_by_sym.get(sym)
                    if st is None:
                        continue
                    day_total += st.shares * float(row[sym])
                weekly_history.append(
                    HistoryEntry(
                        date=date.strftime("%Y-%m-%d"),
                        value=round(day_total, ROUNDING_DECIMALS),
                    )
                )

            first_close = {sym: float(df_hist[sym].iloc[0]) for sym in df_hist.columns}
            for st in portfolio_stocks:
                base = first_close.get(st.symbol)
                if base and base > 0:
                    st.period_return_pct = round(
                        (st.price - base) / base * 100.0, ROUNDING_DECIMALS
                    )

            if len(weekly_history) >= 2:
                start_v = weekly_history[0].value
                end_v = weekly_history[-1].value
                if start_v > 0:
                    period_return_pct = round(
                        (end_v - start_v) / start_v * 100.0, ROUNDING_DECIMALS
                    )

    sector_allocations = build_sector_allocations(portfolio_stocks, amount)

    response = PortfolioResponse(
        stocks=portfolio_stocks,
        total_value=round(total_value, ROUNDING_DECIMALS),
        weekly_history=weekly_history,
        rationale_origin=rationale_origin,
        rationale_llm_backend=llm_backend_meta,
        rationale_llm_model=llm_model_meta,
        warnings=fetch_warnings,
        omitted_symbols=omitted_symbols,
        risk_profile=risk_profile,
        history_period=history_period,
        period_return_pct=period_return_pct,
        sector_allocations=sector_allocations,
        selected_strategies=list(selected_strategies),
        amount_requested=round(amount, ROUNDING_DECIMALS),
    )

    save_to_history(response.model_dump())
    return response


# --- FastAPI App & Routes ---
app = fastapi.FastAPI(title="Stock Portfolio Suggestion Engine")


@app.post("/api/suggest", response_model=PortfolioResponse)
async def get_suggestion(payload: PortfolioRequest, req: Request):
    check_rate_limit(req.client.host or "unknown", "suggest", RATE_SUGGEST_PER_MIN, RATE_WINDOW_S)
    try:
        for strategy in payload.strategies:
            if strategy not in STRATEGIES:
                raise fastapi.HTTPException(
                    status_code=400, detail=f"Invalid strategy: {strategy}"
                )
        return generate_portfolio_suggestion(
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
    return get_history()


@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(body: ChatRequest, req: Request):
    check_rate_limit(req.client.host or "unknown", "chat", RATE_CHAT_PER_MIN, RATE_WINDOW_S)
    return chat_reply(body)


@app.post("/api/chat/stream")
async def chat_stream_endpoint(body: ChatRequest, req: Request):
    check_rate_limit(req.client.host or "unknown", "chat_stream", RATE_CHAT_PER_MIN, RATE_WINDOW_S)
    return fastapi.responses.StreamingResponse(
        chat_reply_stream(body),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/health")
async def health():
    rr = resolve_llm_endpoint("rationale")
    cr = resolve_llm_endpoint("chat")
    return {
        "ok": True,
        "prompt_version": prompts.PROMPT_VERSION,
        "llm_backend": (os.environ.get("LLM_BACKEND") or DEFAULT_LLM_BACKEND).strip().lower(),
        "llm_rationale_configured": rr is not None,
        "llm_chat_configured": cr is not None,
        "rationale_model": rr[2] if rr else None,
        "chat_model": cr[2] if cr else None,
        "rate_limits": {
            "suggest_per_minute": RATE_SUGGEST_PER_MIN,
            "chat_per_minute": RATE_CHAT_PER_MIN,
            "window_seconds": int(RATE_WINDOW_S),
        },
    }


@app.get("/")
async def read_index():
    return fastapi.responses.FileResponse("static/index.html")


@app.get("/style.css")
async def get_css():
    return fastapi.responses.FileResponse("static/style.css")


@app.get("/script.js")
async def get_js():
    return fastapi.responses.FileResponse("static/script.js")


@app.get("/hero.png")
async def get_hero():
    return fastapi.responses.FileResponse("static/hero.png")


@app.get("/favicon.svg")
async def favicon():
    return fastapi.responses.FileResponse(
        "static/favicon.svg",
        media_type="image/svg+xml",
    )


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=DEFAULT_PORT)
