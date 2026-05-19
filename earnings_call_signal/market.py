from __future__ import annotations

import asyncio
import datetime as dt
import json
from dataclasses import dataclass
from typing import Any

from .client import QverisClient

MARKET_DISCOVER_QUERY = "Financial Modeling Prep historical price EOD light symbol close"
MARKET_TOOL_ID = "financialmodelingprep.historical_price_eod.light.retrieve.v1.3f860211"
MARKET_SYMBOL_TIMEOUT_S = 25.0


@dataclass(frozen=True)
class DailyClose:
    date: dt.date
    close: float


def _parse_date(value: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(value[:10])
    except (TypeError, ValueError):
        return None


async def fetch_market_context(
    periods: list[dict[str, Any]],
    *,
    client: QverisClient,
    session_id: str,
) -> list[dict[str, Any]]:
    """Fetch post-call price context through QVeris-discovered market-data tools."""

    by_symbol: dict[str, list[dt.date]] = {}
    for period in periods:
        symbol = str(period.get("symbol") or "").strip().upper()
        event_date = _parse_date(str(period.get("date") or ""))
        if symbol and event_date:
            by_symbol.setdefault(symbol, []).append(event_date)

    if not by_symbol:
        return []

    search_payload = await client.search(MARKET_DISCOVER_QUERY, limit=8, session_id=session_id)
    search_id = search_payload.get("search_id")
    if not search_id:
        return [
            _unavailable_row(symbol, event_date, "QVeris market tool search did not return search_id.")
            for symbol, dates in by_symbol.items()
            for event_date in dates
        ]

    tasks = [
        _fetch_symbol_context_safe(client, symbol, dates, search_id=search_id, session_id=session_id)
        for symbol, dates in by_symbol.items()
    ]
    rows = await asyncio.gather(*tasks)
    out = [row for group in rows for row in group]
    return sorted(out, key=lambda row: (row["symbol"], row["event_date"]), reverse=True)


async def _fetch_symbol_context_safe(
    client: QverisClient,
    symbol: str,
    event_dates: list[dt.date],
    *,
    search_id: str,
    session_id: str,
) -> list[dict[str, Any]]:
    try:
        return await asyncio.wait_for(
            _fetch_symbol_context(
                client,
                symbol,
                event_dates,
                search_id=search_id,
                session_id=session_id,
            ),
            timeout=MARKET_SYMBOL_TIMEOUT_S,
        )
    except Exception as exc:
        return [_unavailable_row(symbol, event_date, f"{type(exc).__name__}: {exc}") for event_date in event_dates]


async def _fetch_symbol_context(
    client: QverisClient,
    symbol: str,
    event_dates: list[dt.date],
    *,
    search_id: str,
    session_id: str,
) -> list[dict[str, Any]]:
    execution = await client.execute(
        MARKET_TOOL_ID,
        search_id=search_id,
        parameters={"symbol": symbol},
        session_id=session_id,
        max_response_size=120000,
    )
    closes = _extract_closes(_result_data(execution))
    rows = [_reaction_row(symbol, event_date, closes) for event_date in event_dates]
    meta = _compact_execute_meta(execution)
    return [{**row, **meta} for row in rows]


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


def _extract_closes(data: Any) -> list[DailyClose]:
    rows: list[DailyClose] = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        date = _parse_date(str(item.get("date") or ""))
        close = item.get("close", item.get("price"))
        if date is None or close is None:
            continue
        try:
            rows.append(DailyClose(date=date, close=round(float(close), 4)))
        except (TypeError, ValueError):
            continue
    return rows


def _reaction_row(symbol: str, event_date: dt.date, closes: list[DailyClose]) -> dict[str, Any]:
    ordered = sorted(closes, key=lambda row: row.date)
    previous = [row for row in ordered if row.date <= event_date]
    after = [row for row in ordered if row.date > event_date]
    base = previous[-1] if previous else None
    next_day = after[0] if after else None
    fifth_day = after[4] if len(after) >= 5 else (after[-1] if after else None)
    status = "ok" if base and next_day else "no_price_data"
    return {
        "symbol": symbol,
        "event_date": event_date.isoformat(),
        "status": status,
        "error": None if status == "ok" else "No QVeris market-data row found around event date.",
        "price_source": "QVeris",
        "market_tool_id": MARKET_TOOL_ID,
        "base_trading_date": base.date.isoformat() if base else None,
        "base_close": base.close if base else None,
        "next_trading_date": next_day.date.isoformat() if next_day else None,
        "next_close": next_day.close if next_day else None,
        "next_return_pct": _return_pct(base, next_day),
        "fifth_trading_date": fifth_day.date.isoformat() if fifth_day else None,
        "fifth_close": fifth_day.close if fifth_day else None,
        "fifth_return_pct": _return_pct(base, fifth_day),
    }


def _unavailable_row(symbol: str, event_date: dt.date, error: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "event_date": event_date.isoformat(),
        "status": "unavailable",
        "error": " ".join(error.split()),
        "price_source": "QVeris",
        "market_tool_id": MARKET_TOOL_ID,
        "execution_id": None,
        "success": None,
        "cost": None,
        "base_trading_date": None,
        "base_close": None,
        "next_trading_date": None,
        "next_close": None,
        "next_return_pct": None,
        "fifth_trading_date": None,
        "fifth_close": None,
        "fifth_return_pct": None,
    }


def _compact_execute_meta(execution: dict[str, Any]) -> dict[str, Any]:
    return {
        "execution_id": execution.get("execution_id"),
        "success": execution.get("success"),
        "cost": execution.get("cost"),
    }


def _return_pct(base: DailyClose | None, target: DailyClose | None) -> float | None:
    if not base or not target or base.close == 0:
        return None
    return round((target.close - base.close) / base.close * 100, 3)
