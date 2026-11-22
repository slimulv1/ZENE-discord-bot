"""Minimal DMM Web API v3 client (MIT, patched for modern Python)."""

from __future__ import annotations

from typing import Any

import requests

BASE_URL = "https://api.dmm.com/affiliate/v3/"


class DMM:
    def __init__(
        self,
        api_id: str,
        affiliate_id: str,
        timeout: float = 10.0,
        session: requests.Session | None = None,
    ) -> None:
        self.api_id = api_id
        self.affiliate_id = affiliate_id
        self.timeout = timeout
        self._session = session or requests.Session()

    def search(self, req: str, **kwargs: Any) -> dict:
        query = {
            "api_id": self.api_id,
            "affiliate_id": self.affiliate_id,
            "site": "FANZA",
        }
        query.update(kwargs)
        response = self._session.get(BASE_URL + req, params=query, timeout=self.timeout)
        response.raise_for_status()
        # Return the full payload so callers can inspect ``result.items``.
        return response.json()

    def item_search(self, **kwargs: Any) -> dict:
        return self.search("item_search", **kwargs)

    def actress_search(self, **kwargs: Any) -> dict:
        return self.search("actress_search", **kwargs)


# Backwards-compatible alias used by the original bot code.
API = DMM
