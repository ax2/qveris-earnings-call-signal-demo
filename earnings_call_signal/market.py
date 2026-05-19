from __future__ import annotations

import asyncio
import datetime as dt
import time
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class DailyClose:
    date: dt.date
    close: float


def _parse_date(value: str) -> dt.date | None:
    try:
        return dt.date.fromisoformat(value[:10])
    except (TypeError, ValueError):
        return None


def _timestamp(date: dt.date) -> int:
    return int(time.mktime(dt.datetime.combine(date, dt.time.min).timetuple()))


async def fetch_market_context(periods: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fetch lightweight post-call price reactions from Yahoo Finance chart data.

    This is intentionally optional. The transcript workflow still runs even if
    the market data endpoint is unavailable.
    """

    by_symbol: dict[str, list[dt.date]] = {}
    for period in periods:
        symbol = str(period.get("symbol") or "").strip().upper()
        event_date = _parse_date(str(period.get("date") or ""))
        if symbol and event_date:
            by_symbol.setdefault(symbol, []).append(event_date)

    async with httpx.AsyncClient(timeout=30.0) as client:
        rows = await asyncio.gather(
            *[_fetch_symbol_context_safe(client, symbol, dates) for symbol, dates in by_symbol.items()]
        )

    out = [row for group in rows for row in group]
    return sorted(out, key=lambda row: (row["symbol"], row["event_date"]), reverse=True)


async def _fetch_symbol_context_safe(
    client: httpx.AsyncClient,
    symbol: str,
    event_dates: list[dt.date],
) -> list[dict[str, Any]]:
    try:
        return await _fetch_symbol_context(client, symbol, event_dates)
    except Exception as exc:
        return [_unavailable_row(symbol, event_date, f"{type(exc).__name__}: {exc}") for event_date in event_dates]


async def _fetch_symbol_context(
    client: httpx.AsyncClient,
    symbol: str,
    event_dates: list[dt.date],
) -> list[dict[str, Any]]:
    start = min(event_dates) - dt.timedelta(days=12)
    end = max(event_dates) + dt.timedelta(days=14)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    response = await client.get(
        url,
        params={
            "period1": _timestamp(start),
            "period2": _timestamp(end),
            "interval": "1d",
            "events": "history",
        },
    )
    response.raise_for_status()
    closes = _extract_closes(response.json())
    return [_reaction_row(symbol, event_date, closes) for event_date in event_dates]


def _extract_closes(payload: dict[str, Any]) -> list[DailyClose]:
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not isinstance(result, dict):
        return []
    timestamps = result.get("timestamp") or []
    quote = (((result.get("indicators") or {}).get("quote") or [None])[0]) or {}
    close_values = quote.get("close") or []
    rows: list[DailyClose] = []
    for ts, close in zip(timestamps, close_values, strict=False):
        if close is None:
            continue
        date = dt.datetime.fromtimestamp(int(ts), tz=dt.UTC).date()
        rows.append(DailyClose(date=date, close=round(float(close), 4)))
    return rows


def _reaction_row(symbol: str, event_date: dt.date, closes: list[DailyClose]) -> dict[str, Any]:
    ordered = sorted(closes, key=lambda row: row.date)
    previous = [row for row in ordered if row.date <= event_date]
    after = [row for row in ordered if row.date > event_date]
    base = previous[-1] if previous else None
    next_day = after[0] if after else None
    fifth_day = after[4] if len(after) >= 5 else (after[-1] if after else None)
    return {
        "symbol": symbol,
        "event_date": event_date.isoformat(),
        "status": "ok" if base and next_day else "no_price_data",
        "error": None if base and next_day else "No daily close data found around event date.",
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
    clean_error = " ".join(error.split())
    return {
        "symbol": symbol,
        "event_date": event_date.isoformat(),
        "status": "unavailable",
        "error": clean_error,
        "base_trading_date": None,
        "base_close": None,
        "next_trading_date": None,
        "next_close": None,
        "next_return_pct": None,
        "fifth_trading_date": None,
        "fifth_close": None,
        "fifth_return_pct": None,
    }


def _return_pct(base: DailyClose | None, target: DailyClose | None) -> float | None:
    if not base or not target or base.close == 0:
        return None
    return round((target.close - base.close) / base.close * 100, 3)
