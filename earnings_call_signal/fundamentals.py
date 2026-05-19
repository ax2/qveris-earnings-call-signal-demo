from __future__ import annotations

import asyncio
import json
from typing import Any

from .client import QverisClient

KEY_METRICS_QUERY = "Financial Modeling Prep key metrics company financial ratios symbol annual"
INCOME_STATEMENT_QUERY = "Financial Modeling Prep income statement revenue net income symbol annual"
KEY_METRICS_TOOL_ID = "financialmodelingprep.stable.keymetrics.retrieve.v1.b8d43d84"
INCOME_STATEMENT_TOOL_ID = "financialmodelingprep.stable.incomestatement.retrieve.v1.dd6d583f"
FUNDAMENTALS_SYMBOL_TIMEOUT_S = 25.0


async def fetch_fundamentals_context(
    symbols: list[str],
    *,
    client: QverisClient,
    session_id: str,
    years: int = 3,
) -> list[dict[str, Any]]:
    clean_symbols = sorted({symbol.strip().upper() for symbol in symbols if symbol.strip()})
    if not clean_symbols:
        return []

    metrics_search, income_search = await asyncio.gather(
        client.search(KEY_METRICS_QUERY, limit=8, session_id=session_id),
        client.search(INCOME_STATEMENT_QUERY, limit=8, session_id=session_id),
    )
    metrics_search_id = metrics_search.get("search_id")
    income_search_id = income_search.get("search_id")
    if not metrics_search_id or not income_search_id:
        return [_unavailable_row(symbol, "QVeris fundamentals tool search did not return search_id.") for symbol in clean_symbols]

    tasks = [
        _fetch_symbol_fundamentals_safe(
            client,
            symbol,
            metrics_search_id=metrics_search_id,
            income_search_id=income_search_id,
            session_id=session_id,
            years=years,
        )
        for symbol in clean_symbols
    ]
    rows = await asyncio.gather(*tasks)
    return [row for group in rows for row in group]


async def _fetch_symbol_fundamentals_safe(
    client: QverisClient,
    symbol: str,
    *,
    metrics_search_id: str,
    income_search_id: str,
    session_id: str,
    years: int,
) -> list[dict[str, Any]]:
    try:
        return await asyncio.wait_for(
            _fetch_symbol_fundamentals(
                client,
                symbol,
                metrics_search_id=metrics_search_id,
                income_search_id=income_search_id,
                session_id=session_id,
                years=years,
            ),
            timeout=FUNDAMENTALS_SYMBOL_TIMEOUT_S,
        )
    except Exception as exc:
        return [_unavailable_row(symbol, f"{type(exc).__name__}: {exc}")]


async def _fetch_symbol_fundamentals(
    client: QverisClient,
    symbol: str,
    *,
    metrics_search_id: str,
    income_search_id: str,
    session_id: str,
    years: int,
) -> list[dict[str, Any]]:
    metrics_ex, income_ex = await asyncio.gather(
        client.execute(
            KEY_METRICS_TOOL_ID,
            search_id=metrics_search_id,
            parameters={"symbol": symbol},
            session_id=session_id,
            max_response_size=80000,
        ),
        client.execute(
            INCOME_STATEMENT_TOOL_ID,
            search_id=income_search_id,
            parameters={"symbol": symbol},
            session_id=session_id,
            max_response_size=80000,
        ),
    )
    metrics_rows = _rows_by_year(_result_data(metrics_ex))
    income_rows = _rows_by_year(_result_data(income_ex))
    selected_years = sorted(set(metrics_rows) | set(income_rows), reverse=True)[:years]
    out: list[dict[str, Any]] = []
    for fiscal_year in selected_years:
        metrics = metrics_rows.get(fiscal_year) or {}
        income = income_rows.get(fiscal_year) or {}
        revenue = _num(income.get("revenue"))
        gross_profit = _num(income.get("grossProfit"))
        operating_income = _num(income.get("operatingIncome"))
        net_income = _num(income.get("netIncome"))
        out.append(
            {
                "symbol": symbol,
                "fiscal_year": fiscal_year,
                "period": income.get("period") or metrics.get("period"),
                "date": income.get("date") or metrics.get("date"),
                "status": "ok",
                "revenue": revenue,
                "gross_margin_pct": _pct(gross_profit, revenue),
                "operating_margin_pct": _pct(operating_income, revenue),
                "net_margin_pct": _pct(net_income, revenue),
                "return_on_invested_capital_pct": _ratio_pct(metrics.get("returnOnInvestedCapital")),
                "capex_to_revenue_pct": _ratio_pct(metrics.get("capexToRevenue")),
                "free_cash_flow_yield_pct": _ratio_pct(metrics.get("freeCashFlowYield")),
                "market_cap": _num(metrics.get("marketCap")),
                "metrics_execution_id": metrics_ex.get("execution_id"),
                "income_execution_id": income_ex.get("execution_id"),
                "metrics_cost": metrics_ex.get("cost"),
                "income_cost": income_ex.get("cost"),
            }
        )
    return out


def _result_data(execution: dict[str, Any]) -> Any:
    result = execution.get("result")
    if not isinstance(result, dict):
        return None
    data = result.get("data")
    if data is None:
        data = result.get("truncated_content")
    for _ in range(2):
        if isinstance(data, str) and data.strip():
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                break
    return data


def _rows_by_year(data: Any) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in data if isinstance(data, list) else []:
        if not isinstance(row, dict):
            continue
        year = str(row.get("fiscalYear") or row.get("calendarYear") or "")[:4]
        if year:
            out[year] = row
    return out


def _num(value: Any) -> float | None:
    try:
        return round(float(value), 4)
    except (TypeError, ValueError):
        return None


def _pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return round(numerator / denominator * 100, 3)


def _ratio_pct(value: Any) -> float | None:
    number = _num(value)
    if number is None:
        return None
    return round(number * 100, 3)


def _unavailable_row(symbol: str, error: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "fiscal_year": None,
        "period": None,
        "date": None,
        "status": "unavailable",
        "error": " ".join(error.split()),
    }

