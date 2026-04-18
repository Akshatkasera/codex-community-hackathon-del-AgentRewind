from __future__ import annotations

import threading
import time
from collections import deque
from math import ceil

from fastapi import Request

from .config import get_settings


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._events: dict[tuple[str, str], deque[float]] = {}
        self._lock = threading.RLock()

    def reset(self) -> None:
        with self._lock:
            self._events.clear()

    def check_request(self, request: Request) -> tuple[bool, int, int, int]:
        settings = get_settings()
        bucket = self._bucket_for_path(request.url.path)
        limit = (
            settings.rate_limit_heavy_requests_per_minute
            if bucket == "heavy"
            else settings.rate_limit_requests_per_minute
        )
        if limit <= 0:
            return True, 0, 0, 0
        client_id = self._client_id(request)
        return self._check_bucket(client_id=client_id, bucket=bucket, limit=limit)

    def _check_bucket(
        self,
        *,
        client_id: str,
        bucket: str,
        limit: int,
    ) -> tuple[bool, int, int, int]:
        now = time.monotonic()
        window_seconds = 60.0
        key = (client_id, bucket)
        with self._lock:
            entries = self._events.setdefault(key, deque())
            while entries and entries[0] <= now - window_seconds:
                entries.popleft()
            if len(entries) >= limit:
                retry_after = max(1, ceil(window_seconds - (now - entries[0])))
                return False, limit, 0, retry_after
            entries.append(now)
            remaining = max(0, limit - len(entries))
            return True, limit, remaining, 0

    def _client_id(self, request: Request) -> str:
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            first_ip = forwarded_for.split(",")[0].strip()
            if first_ip:
                return first_ip
        if request.client and request.client.host:
            return request.client.host
        return "unknown"

    def _bucket_for_path(self, path: str) -> str:
        if path.startswith(
            (
                "/api/imports",
                "/api/diagnose",
                "/api/replay",
                "/api/evals",
            )
        ):
            return "heavy"
        return "default"


rate_limiter = SlidingWindowRateLimiter()
