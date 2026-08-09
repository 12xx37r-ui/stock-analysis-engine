"""Strategic macro low-load cache regression tests."""

from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from unittest import mock

import collectors.strategic_context as sc


class FakeResponse:
    def __init__(self, payload=None, status_code=200, headers=None):
        self._payload = payload or {}
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


def reset_memory():
    sc._CACHE.clear()
    sc._CACHE.update({"at": 0.0, "payload": None, "source": ""})


def main():
    with tempfile.TemporaryDirectory() as td:
        cache = Path(td) / "macro.json"
        lock = Path(td) / "macro.lock"
        old_cache, old_lock = sc.CACHE_FILE, sc.LOCK_FILE
        old_ttl, old_stale = sc.CACHE_TTL_SECONDS, sc.STALE_IF_ERROR_SECONDS
        sc.CACHE_FILE, sc.LOCK_FILE = cache, lock
        sc.CACHE_TTL_SECONDS, sc.STALE_IF_ERROR_SECONDS = 3600, 86400
        try:
            reset_memory()
            payload = {"cards": {"11": {"score": 10}}}
            calls = []

            def first_get(url, headers=None, timeout=None):
                calls.append((url, dict(headers or {}), timeout))
                return FakeResponse(payload, 200, {"ETag": '"abc"', "Last-Modified": "Sun, 09 Aug 2026 00:00:00 GMT"})

            with mock.patch.object(sc.requests, "get", side_effect=first_get):
                a = sc.get_strategic_macro_context()
                b = sc.get_strategic_macro_context()
            assert a["payload"] == payload
            assert b["payload"] == payload
            assert len(calls) == 1, calls
            assert b.get("캐시") == "memory"

            # 새 프로세스처럼 메모리만 비워도 fresh disk cache면 네트워크 0회.
            reset_memory()
            with mock.patch.object(sc.requests, "get", side_effect=AssertionError("network must not be called")):
                c = sc.get_strategic_macro_context()
            assert c["payload"] == payload
            assert c.get("캐시") in {"disk", "disk_after_lock"}

            # stale cache는 conditional header를 보내고 304면 payload를 재사용한다.
            record = json.loads(cache.read_text(encoding="utf-8"))
            record["fetched_at"] = time.time() - 7200
            cache.write_text(json.dumps(record), encoding="utf-8")
            reset_memory()
            conditional = []

            def not_modified(url, headers=None, timeout=None):
                conditional.append(dict(headers or {}))
                return FakeResponse({}, 304, {})

            with mock.patch.object(sc.requests, "get", side_effect=not_modified):
                d = sc.get_strategic_macro_context()
            assert d["payload"] == payload
            assert conditional and conditional[0].get("If-None-Match") == '"abc"'
            assert d.get("캐시") == "conditional_304"

            # 네트워크 오류면 last-known-good를 쓰고 즉시 종료한다.
            record = json.loads(cache.read_text(encoding="utf-8"))
            record["fetched_at"] = time.time() - 7200
            cache.write_text(json.dumps(record), encoding="utf-8")
            reset_memory()
            with mock.patch.object(sc.requests, "get", side_effect=RuntimeError("offline")) as mocked:
                e = sc.get_strategic_macro_context()
            assert mocked.call_count == 1
            assert e["payload"] == payload
            assert e.get("캐시") == "stale_if_error"
            assert e["수집상태"] == "캐시사용"
        finally:
            sc.CACHE_FILE, sc.LOCK_FILE = old_cache, old_lock
            sc.CACHE_TTL_SECONDS, sc.STALE_IF_ERROR_SECONDS = old_ttl, old_stale
            reset_memory()

    print("STRATEGIC CONTEXT LOW-LOAD CACHE: PASS")


if __name__ == "__main__":
    main()
