"""
This service talks to Yahoo Finance using the 'yfinance' library.
It grabs live stock prices and historical data to feed our main portfolio engine.
"""

import time
import typing
import yfinance
import app.config


def _resolve_sector(info: typing.Dict[str, typing.Any]) -> str:
    """ETFs often report empty `sector`; fall back to quoteType-aware label."""
    sec = (info.get("sector") or "").strip()
    if sec:
        return sec
    qt = (info.get("quoteType") or "").strip().upper()
    if qt == "ETF":
        cat = (info.get("category") or "").strip()
        return cat or app.config.DEFAULT_SECTOR_LABEL
    return app.config.DEFAULT_SECTOR_LABEL


def _try_fetch_single_symbol(
    symbol: str,
) -> typing.Optional[typing.Dict[str, typing.Any]]:
    ticker = yfinance.Ticker(symbol)
    info = ticker.info or {}
    current_price = info.get("regularMarketPrice") or info.get("currentPrice")
    hist_full = ticker.history(period=app.config.YFINANCE_FETCH_PERIOD)
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
        for attempt in range(app.config.YFINANCE_MAX_ATTEMPTS):
            try:
                row = _try_fetch_single_symbol(symbol)
                if row:
                    break
            except Exception:
                row = None
            time.sleep(
                app.config.BACKOFF_BASE_DELAY_S * (app.config.BACKOFF_FACTOR**attempt)
            )
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
