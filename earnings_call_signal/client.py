from __future__ import annotations

import uuid
from typing import Any
from urllib.parse import quote

import httpx

from .config import get_settings


class QverisClient:
    """Small async client for QVeris search and execute APIs."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout_s: float = 180.0,
    ) -> None:
        settings = get_settings()
        self._api_key = (api_key or settings.qveris_api_key).strip()
        self._base_url = (base_url or settings.qveris_base_url).rstrip("/")
        self._timeout_s = timeout_s
        if not self._api_key:
            raise ValueError("Missing QVERIS_API_KEY. Copy .env.example to .env and fill it.")

    @property
    def base_url(self) -> str:
        return self._base_url

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def search(
        self,
        query: str,
        *,
        limit: int = 10,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        sid = session_id or str(uuid.uuid4())
        payload = {"query": query, "limit": limit, "session_id": sid}
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            response = await client.post(
                f"{self._base_url}/search",
                json=payload,
                headers=self._headers(),
            )
        response.raise_for_status()
        data = response.json()
        data["_session_id"] = sid
        return data

    async def execute(
        self,
        tool_id: str,
        *,
        search_id: str,
        parameters: dict[str, Any],
        session_id: str | None = None,
        max_response_size: int = 120000,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "search_id": search_id,
            "parameters": parameters,
            "max_response_size": max_response_size,
        }
        if session_id:
            payload["session_id"] = session_id

        encoded_tool_id = quote(tool_id, safe="")
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            response = await client.post(
                f"{self._base_url}/tools/execute?tool_id={encoded_tool_id}",
                json=payload,
                headers=self._headers(),
            )
        response.raise_for_status()
        return response.json()

