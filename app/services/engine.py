"""
This is the brain of the application.
It contains the math that splits the user's money across their chosen
investment strategies, calculates the return rates, and tilts allocations
based on conservative or aggressive risk levels.
"""

import typing
import pandas
import app.config
import app.schemas
import app.services.market_data
import app.services.llm
import app.database


def compute_weighted_allocations(
    amount: float,
    selected_strategies: typing.List[str],
    risk_profile: app.config.RiskProfile,
    available_symbols: typing.Set[str],
) -> typing.Dict[str, float]:
    """Split `amount` across `available_symbols` using risk-tilted weights.

    1) Each selected strategy gets a slice proportional to STRATEGY_RISK_WEIGHTS.
       Strategies with zero priceable symbols contribute nothing (their slice
       gets redistributed to the active ones).
    2) The strategy slice is allocated among its active symbols, tilted by TICKER_RISK_TILT.
    """
    strat_weights = app.config.STRATEGY_RISK_WEIGHTS.get(risk_profile, {})
    ticker_tilt = app.config.TICKER_RISK_TILT.get(risk_profile, {})

    effective: typing.Dict[str, float] = {}
    for strategy in selected_strategies:
        tickers_alive = [
            s for s in app.config.STRATEGIES.get(strategy, []) if s in available_symbols
        ]
        if not tickers_alive:
            continue
        effective[strategy] = strat_weights.get(
            strategy, app.config.DEFAULT_STRATEGY_WEIGHT
        )

    total_strat_w = sum(effective.values())
    if total_strat_w <= 0:
        return {
            sym: amount / max(len(available_symbols), 1) for sym in available_symbols
        }

    allocations: typing.Dict[str, float] = {sym: 0.0 for sym in available_symbols}
    for strategy, strat_w in effective.items():
        strat_amount = amount * (strat_w / total_strat_w)
        tickers_alive = [
            s for s in app.config.STRATEGIES[strategy] if s in available_symbols
        ]
        tilts = [
            ticker_tilt.get(sym, app.config.DEFAULT_TICKER_TILT)
            for sym in tickers_alive
        ]
        sum_tilt = sum(tilts) or float(len(tickers_alive))
        for sym, tilt in zip(tickers_alive, tilts):
            share = (tilt / sum_tilt) if sum_tilt > 0 else (1.0 / len(tickers_alive))
            allocations[sym] += strat_amount * share

    return allocations


def trim_history_for_period(
    df: pandas.DataFrame, period: app.config.HistoryPeriod
) -> pandas.DataFrame:
    """Trim the full 1y dataframe down to what the UI period asked for."""
    n = app.config.PERIOD_TRIM_DAYS.get(period)
    if n is None:
        return df
    return df.tail(n)


def build_sector_allocations(
    stocks: typing.List[app.schemas.StockInfo], total_allocated: float
) -> typing.List[app.schemas.SectorAllocation]:
    bucket: typing.Dict[str, float] = {}
    for s in stocks:
        bucket[s.sector] = bucket.get(s.sector, 0.0) + s.allocation_amount
    out: typing.List[app.schemas.SectorAllocation] = []
    denom = total_allocated if total_allocated > 0 else 1.0
    for sec, amt in sorted(bucket.items(), key=lambda kv: kv[1], reverse=True):
        out.append(
            app.schemas.SectorAllocation(
                sector=sec,
                amount=round(amt, app.config.ROUNDING_DECIMALS),
                pct=round(
                    (amt / denom) * app.config.PERCENTAGE_MULTIPLIER,
                    app.config.ROUNDING_DECIMALS,
                ),
            )
        )
    return out


def generate_portfolio_suggestion(
    amount: float,
    selected_strategies: typing.List[str],
    risk_profile: app.config.RiskProfile = app.config.DEFAULT_RISK_PROFILE,
    history_period: app.config.HistoryPeriod = app.config.DEFAULT_HISTORY_PERIOD,
) -> app.schemas.PortfolioResponse:
    """Core engine logic to map strategies to stocks and calculate allocations."""
    symbols = []
    for strategy in selected_strategies:
        if strategy in app.config.STRATEGIES:
            symbols.extend(app.config.STRATEGIES[strategy])

    symbols = list(set(symbols))
    market_data, omitted_symbols, fetch_warnings = (
        app.services.market_data.fetch_stock_data_partitioned(symbols)
    )
    if not market_data:
        raise Exception(
            "Could not fetch market data for any symbol. Check your network and try again."
        )

    symbols_ok = sorted(market_data.keys())
    allocations = compute_weighted_allocations(
        amount=amount,
        selected_strategies=selected_strategies,
        risk_profile=risk_profile,
        available_symbols=set(symbols_ok),
    )

    names_by_symbol = {s: str(market_data[s]["name"]) for s in symbols_ok}
    rationales, rationale_sources = app.services.llm.build_selection_rationales(
        symbols_ok, selected_strategies, names_by_symbol
    )
    rationale_origin = app.services.llm.rationale_origin_from_sources(rationale_sources)
    llm_backend_meta, llm_model_meta = app.services.llm.active_llm_meta()

    portfolio_stocks: typing.List[app.schemas.StockInfo] = []
    total_value = 0.0
    history_agg: typing.Dict[str, typing.Any] = {}

    for symbol in symbols_ok:
        data = market_data[symbol]
        price = float(data["current_price"])
        alloc = float(allocations.get(symbol, 0.0))
        shares = alloc / price if price > 0 else 0.0

        portfolio_stocks.append(
            app.schemas.StockInfo(
                symbol=symbol,
                name=data["name"],
                price=price,
                shares=shares,
                allocation_amount=round(alloc, app.config.ROUNDING_DECIMALS),
                logo_url=data.get("logo_url"),
                selection_rationale=rationales.get(symbol, ""),
                rationale_source=rationale_sources.get(symbol, "fallback"),
                sector=data.get("sector") or app.config.DEFAULT_SECTOR_LABEL,
            )
        )

        total_value += shares * price
        if data.get("history") is not None and not data["history"].empty:
            history_agg[symbol] = data["history"]

    weekly_history: typing.List[app.schemas.HistoryEntry] = []
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
                    app.schemas.HistoryEntry(
                        date=date.strftime("%Y-%m-%d"),
                        value=round(day_total, app.config.ROUNDING_DECIMALS),
                    )
                )

            first_close = {sym: float(df_hist[sym].iloc[0]) for sym in df_hist.columns}
            for st in portfolio_stocks:
                base = first_close.get(st.symbol)
                if base and base > 0:
                    st.period_return_pct = round(
                        (st.price - base) / base * app.config.PERCENTAGE_MULTIPLIER,
                        app.config.ROUNDING_DECIMALS,
                    )

            if len(weekly_history) >= 2:
                start_v = weekly_history[0].value
                end_v = weekly_history[-1].value
                if start_v > 0:
                    period_return_pct = round(
                        (end_v - start_v) / start_v * app.config.PERCENTAGE_MULTIPLIER,
                        app.config.ROUNDING_DECIMALS,
                    )

    sector_allocations = build_sector_allocations(portfolio_stocks, amount)

    response = app.schemas.PortfolioResponse(
        stocks=portfolio_stocks,
        total_value=round(total_value, app.config.ROUNDING_DECIMALS),
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
        amount_requested=round(amount, app.config.ROUNDING_DECIMALS),
    )

    app.database.save_to_history(response.model_dump())
    return response
