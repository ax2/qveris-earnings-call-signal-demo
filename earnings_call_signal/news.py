from __future__ import annotations

import asyncio
import datetime as dt
import json
from collections import Counter
from typing import Any

from .client import QverisClient

NEWS_QUERY = "Financial Modeling Prep stock news symbol latest articles"
NEWS_TOOL_ID = "financialmodelingprep.stable.news.stock.retrieve.v1.675e0f32"
NEWS_SYMBOL_TIMEOUT_S = 20.0


async def fetch_news_context(
    symbols: list[str],
    *,
    client: QverisClient,
    session_id: str,
    limit_per_symbol: int = 8,
) -> list[dict[str, Any]]:
    clean_symbols = sorted({symbol.strip().upper() for symbol in symbols if symbol.strip()})
    if not clean_symbols:
        return []

    search_payload = await client.search(NEWS_QUERY, limit=8, session_id=session_id)
    search_id = search_payload.get("search_id")
    if not search_id:
        return [_unavailable_row(symbol, "QVeris news tool search did not return search_id.") for symbol in clean_symbols]

    tasks = [
        _fetch_symbol_news_safe(
            client,
            symbol,
            search_id=search_id,
            session_id=session_id,
            limit=limit_per_symbol,
        )
        for symbol in clean_symbols
    ]
    rows = await asyncio.gather(*tasks)
    return [row for group in rows for row in group]


async def _fetch_symbol_news_safe(
    client: QverisClient,
    symbol: str,
    *,
    search_id: str,
    session_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    try:
        return await asyncio.wait_for(
            _fetch_symbol_news(client, symbol, search_id=search_id, session_id=session_id, limit=limit),
            timeout=NEWS_SYMBOL_TIMEOUT_S,
        )
    except Exception as exc:
        return [_unavailable_row(symbol, f"{type(exc).__name__}: {exc}")]


async def _fetch_symbol_news(
    client: QverisClient,
    symbol: str,
    *,
    search_id: str,
    session_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    execution = await client.execute(
        NEWS_TOOL_ID,
        search_id=search_id,
        parameters={"symbols": symbol},
        session_id=session_id,
        max_response_size=80000,
    )
    rows: list[dict[str, Any]] = []
    for item in _result_rows(execution)[:limit]:
        title = str(item.get("title") or "")
        text = str(item.get("text") or "")
        rows.append(
            {
                "symbol": symbol,
                "published_at": item.get("publishedDate"),
                "publisher": item.get("publisher") or item.get("site"),
                "title": title,
                "url": item.get("url"),
                "news_topics": ",".join(classify_news_topics(f"{title} {text}")),
                "execution_id": execution.get("execution_id"),
                "cost": execution.get("cost"),
            }
        )
    return rows or [_unavailable_row(symbol, "QVeris news tool returned no rows.")]


def build_news_summary(news_rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_symbol: dict[str, Counter[str]] = {}
    latest: dict[str, list[dict[str, Any]]] = {}
    for row in news_rows:
        symbol = str(row.get("symbol") or "")
        if not symbol or row.get("status") == "unavailable":
            continue
        by_symbol.setdefault(symbol, Counter())
        for topic in str(row.get("news_topics") or "").split(","):
            if topic:
                by_symbol[symbol][topic] += 1
        latest.setdefault(symbol, []).append(row)

    return {
        "topic_counts_by_symbol": {symbol: dict(counter.most_common()) for symbol, counter in by_symbol.items()},
        "latest_titles_by_symbol": {
            symbol: [
                {
                    "published_at": item.get("published_at"),
                    "publisher": item.get("publisher"),
                    "title": item.get("title"),
                    "topics": item.get("news_topics"),
                }
                for item in sorted(items, key=lambda row: str(row.get("published_at") or ""), reverse=True)[:5]
            ]
            for symbol, items in latest.items()
        },
    }


def classify_news_topics(text: str) -> list[str]:
    lower = text.lower()
    rules = {
        "AI": [" ai ", "artificial intelligence", "siri", "gemini", "agentic"],
        "MarketReaction": ["stock", "shares", "market", "investor", "buffett"],
        "Product": ["iphone", "gpu", "chip", "data center", "product", "platform"],
        "Competition": ["competition", "competitor", "versus", "vs", "market share"],
        "Regulation": ["regulation", "regulatory", "antitrust", "tariff", "export"],
        "Financials": ["revenue", "earnings", "margin", "profit", "cash flow"],
    }
    hits = [topic for topic, needles in rules.items() if any(needle in f" {lower} " for needle in needles)]
    return hits or ["General"]


def _result_rows(execution: dict[str, Any]) -> list[dict[str, Any]]:
    result = execution.get("result")
    if not isinstance(result, dict):
        return []
    data = result.get("data")
    if data is None:
        data = result.get("truncated_content")
    for _ in range(2):
        if isinstance(data, str) and data.strip():
            try:
                data = json.loads(data)
            except json.JSONDecodeError:
                break
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _unavailable_row(symbol: str, error: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "published_at": dt.datetime.now(dt.UTC).isoformat(),
        "publisher": None,
        "title": None,
        "url": None,
        "news_topics": None,
        "status": "unavailable",
        "error": " ".join(error.split()),
    }

