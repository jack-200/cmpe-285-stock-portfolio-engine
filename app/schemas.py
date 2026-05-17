"""
This module defines our Pydantic data schemas.
It acts as the API contract, validating the shape of JSON requests
that come in and formatting the suggestions that go back out.
"""

import typing
import pydantic
import app.config

RationaleOrigin = typing.Literal["all_llm", "partial_llm", "fallback"]
RationaleSource = typing.Literal["llm", "fallback"]
LLMKind = typing.Literal["rationale", "chat"]


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
    sector: str = app.config.DEFAULT_SECTOR_LABEL
    period_return_pct: typing.Optional[float] = None


class SectorAllocation(pydantic.BaseModel):
    sector: str
    amount: float
    pct: float


class PortfolioRequest(pydantic.BaseModel):
    amount: float = pydantic.Field(
        ...,
        ge=app.config.MIN_INVESTMENT_AMOUNT,
        description=f"Amount to invest (Min ${app.config.MIN_INVESTMENT_AMOUNT})",
    )
    strategies: typing.List[str] = pydantic.Field(
        ...,
        min_length=app.config.MIN_STRATEGIES,
        max_length=app.config.MAX_STRATEGIES,
        description=f"Select {app.config.MIN_STRATEGIES} or {app.config.MAX_STRATEGIES} strategies",
    )
    risk_profile: app.config.RiskProfile = pydantic.Field(
        default=app.config.DEFAULT_RISK_PROFILE,
        description="Conservative / Moderate / Aggressive — drives weighted allocation.",
    )
    history_period: app.config.HistoryPeriod = pydantic.Field(
        default=app.config.DEFAULT_HISTORY_PERIOD,
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
    risk_profile: app.config.RiskProfile = app.config.DEFAULT_RISK_PROFILE
    history_period: app.config.HistoryPeriod = app.config.DEFAULT_HISTORY_PERIOD
    period_return_pct: typing.Optional[float] = None
    sector_allocations: typing.List[SectorAllocation] = pydantic.Field(
        default_factory=list
    )
    selected_strategies: typing.List[str] = pydantic.Field(default_factory=list)
    amount_requested: typing.Optional[float] = None


class ChatMessage(pydantic.BaseModel):
    role: typing.Literal["user", "assistant"]
    content: str = pydantic.Field(..., max_length=app.config.CHAT_MAX_CHARS_PER_MESSAGE)


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
    sector_allocations: typing.List[ChatSectorSnap] = pydantic.Field(
        default_factory=list
    )


class ChatRequest(pydantic.BaseModel):
    messages: typing.List[ChatMessage] = pydantic.Field(
        ...,
        min_length=1,
        max_length=app.config.CHAT_MAX_MESSAGES,
    )
    portfolio_context: typing.Optional[ChatPortfolioSnapshot] = None


class ChatResponse(pydantic.BaseModel):
    reply: str
    llm_available: bool = True
    ok: bool = True
