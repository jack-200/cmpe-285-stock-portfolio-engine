# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "fastapi",
#     "jinja2",
#     "pandas",
#     "pydantic",
#     "uvicorn",
#     "yfinance",
# ]
# ///

import json
import os
import typing
import datetime

import fastapi
import fastapi.responses
import fastapi.staticfiles
import pandas
import pydantic
import uvicorn
import yfinance

# --- Configuration & Constants ---
HISTORY_FILE = "history.json"
STRATEGIES = {
    "Ethical Investing": ["AAPL", "ADBE", "NSRGY"],
    "Growth Investing": ["NVDA", "AMZN", "TSLA"],
    "Index Investing": ["VTI", "IXUS", "ILTB"],
    "Quality Investing": ["MSFT", "GOOGL", "V"],
    "Value Investing": ["BRK-B", "JNJ", "PFE"],
}

# Magic Number Constants
MIN_INVESTMENT_AMOUNT = 5000
MIN_STRATEGIES = 1
MAX_STRATEGIES = 2
MAX_HISTORY_ENTRIES = 10
HISTORICAL_DAYS_COUNT = 5
ROUNDING_DECIMALS = 2
DEFAULT_PORT = 8000


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


class PortfolioResponse(pydantic.BaseModel):
    stocks: typing.List[StockInfo]
    total_value: float
    weekly_history: typing.List[HistoryEntry]


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
def fetch_stock_data(symbols: typing.List[str]) -> typing.Dict[str, typing.Any]:
    """Fetches current info and historical data for a list of symbols."""
    tickers = yfinance.Tickers(" ".join(symbols))
    results = {}

    for symbol in symbols:
        ticker = tickers.tickers[symbol]
        info = ticker.info

        current_price = info.get("regularMarketPrice") or info.get("currentPrice")
        if current_price is None:
            hist = ticker.history(period="1d")
            current_price = hist["Close"].iloc[-1] if not hist.empty else 0.0

        name = info.get("longName", symbol)
        hist_1mo = ticker.history(period="1mo")
        history = hist_1mo["Close"].tail(HISTORICAL_DAYS_COUNT)

        results[symbol] = {
            "name": name,
            "current_price": current_price,
            "history": history,
            "logo_url": info.get("logo_url"),
        }
    return results


# --- Core Portfolio Engine Logic ---
def generate_portfolio_suggestion(
    amount: float, selected_strategies: typing.List[str]
) -> PortfolioResponse:
    """Core engine logic to map strategies to stocks and calculate allocations."""
    symbols = []
    for strategy in selected_strategies:
        if strategy in STRATEGIES:
            symbols.extend(STRATEGIES[strategy])

    symbols = list(set(symbols))
    num_stocks = len(symbols)
    amount_per_stock = amount / num_stocks

    market_data = fetch_stock_data(symbols)

    portfolio_stocks = []
    total_value = 0
    history_agg = {}

    for symbol in symbols:
        data = market_data[symbol]
        price = data["current_price"]
        shares = amount_per_stock / price if price > 0 else 0

        portfolio_stocks.append(
            StockInfo(
                symbol=symbol,
                name=data["name"],
                price=price,
                shares=shares,
                allocation_amount=amount_per_stock,
                logo_url=data.get("logo_url"),
            )
        )

        total_value += shares * price
        history_agg[symbol] = data["history"]

    weekly_history = []
    if history_agg:
        df_hist = pandas.DataFrame(history_agg).dropna().tail(HISTORICAL_DAYS_COUNT)
        for date, row in df_hist.iterrows():
            day_total = 0
            for stock in portfolio_stocks:
                day_total += stock.shares * row[stock.symbol]

            weekly_history.append(
                HistoryEntry(
                    date=date.strftime("%Y-%m-%d"),
                    value=round(day_total, ROUNDING_DECIMALS),
                )
            )

    response = PortfolioResponse(
        stocks=portfolio_stocks,
        total_value=round(total_value, ROUNDING_DECIMALS),
        weekly_history=weekly_history,
    )

    save_to_history(response.model_dump())
    return response


# --- FastAPI App & Routes ---
app = fastapi.FastAPI(title="Stock Portfolio Suggestion Engine")


@app.post("/api/suggest", response_model=PortfolioResponse)
async def get_suggestion(request: PortfolioRequest):
    try:
        for strategy in request.strategies:
            if strategy not in STRATEGIES:
                raise fastapi.HTTPException(
                    status_code=400, detail=f"Invalid strategy: {strategy}"
                )
        return generate_portfolio_suggestion(request.amount, request.strategies)
    except Exception as e:
        raise fastapi.HTTPException(status_code=500, detail=str(e))


@app.get("/api/history")
async def get_portfolio_history():
    return get_history()


@app.get("/")
async def read_index():
    return fastapi.responses.FileResponse("index.html")


@app.get("/style.css")
async def get_css():
    return fastapi.responses.FileResponse("style.css")


@app.get("/script.js")
async def get_js():
    return fastapi.responses.FileResponse("script.js")


@app.get("/hero.png")
async def get_hero():
    return fastapi.responses.FileResponse("hero.png")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=DEFAULT_PORT)
