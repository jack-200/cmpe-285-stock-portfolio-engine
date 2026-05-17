"""
This file holds all our constant settings and config parameters.
Things like strategy lists, stock risk weights, rounding decimals,
and default time periods are stored here so we don't hardcode them elsewhere.
"""

import typing

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
        "ILTB": 1.6,
        "VTI": 1.1,
        "IXUS": 0.9,
        "BRK-B": 1.2,
        "JNJ": 1.3,
        "PFE": 1.0,
        "MSFT": 1.1,
        "GOOGL": 1.0,
        "V": 1.1,
        "NVDA": 0.7,
        "AMZN": 1.0,
        "TSLA": 0.5,
        "AAPL": 1.1,
        "ADBE": 1.0,
        "NSRGY": 1.3,
    },
    "Moderate": {},
    "Aggressive": {
        "ILTB": 0.5,
        "VTI": 1.0,
        "IXUS": 1.1,
        "BRK-B": 0.9,
        "JNJ": 0.8,
        "PFE": 0.9,
        "MSFT": 1.0,
        "GOOGL": 1.1,
        "V": 1.0,
        "NVDA": 1.5,
        "AMZN": 1.2,
        "TSLA": 1.5,
        "AAPL": 1.1,
        "ADBE": 1.2,
        "NSRGY": 0.8,
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

# Refactored Symbolic Constants
BACKOFF_BASE_DELAY_S = 0.35
BACKOFF_FACTOR = 2
LLM_RATIONALE_TEMPERATURE = 0.35
LLM_REPAIR_TEMPERATURE = 0.2
PERCENTAGE_MULTIPLIER = 100.0
DEFAULT_STRATEGY_WEIGHT = 1.0
DEFAULT_TICKER_TILT = 1.0
