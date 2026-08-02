"""Shared resilient OpenDART HTTP client.

Goals
- Avoid repeating 20-second timeouts for every endpoint when OpenDART is unavailable.
- Retry transient network/5xx failures briefly.
- Reuse successful JSON/document responses from disk cache.
- Never cache API keys in file names or payload metadata.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

CACHE_ROOT = Path(os.getenv("DART_RESPONSE_CACHE_DIR", ".cache/dart_api"))
DEFAULT_TIMEOUT = (8, 30)
JSON_STALE_SECONDS = int(os.getenv("DART_JSON_STALE_SECONDS", str(45 * 24 * 60 * 60)))
DOCUMENT_STALE_SECONDS = int(os.getenv("DART_DOCUMENT_STALE_SECONDS", str(45 * 24 * 60 * 60)))
CIRCUIT_SECONDS = int(os.getenv("DART_CIRCUIT_SECONDS", "45"))

_FAILURES = 0
_OPEN_UNTIL = 0.0


def _session() -> requests.Session:
    retry = Retry(
        total=2,
        connect=2,
        read=1,
        status=2,
        backoff_factor=0.8,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        raise_on_status=False,
    )
    session = requests.Session()
    session.headers.update({"User-Agent": "stock-analysis-engine/6.7 OpenDART client"})
    adapter = HTTPAdapter(max_retries=retry, pool_connections=8, pool_maxsize=8)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


_SESSION = _session()


def _safe_params(params: Dict[str, Any]) -> Dict[str, str]:
    return {
        str(key): str(value)
        for key, value in params.items()
        if key != "crtfc_key" and value is not None
    }


def _cache_key(url: str, params: Dict[str, Any], kind: str) -> str:
    raw = json.dumps(
        {"url": url, "params": _safe_params(params), "kind": kind},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _paths(key: str, kind: str) -> tuple[Path, Path]:
    suffix = ".json" if kind == "json" else ".bin"
    return CACHE_ROOT / f"{key}{suffix}", CACHE_ROOT / f"{key}.meta.json"


def _read_cache(url: str, params: Dict[str, Any], kind: str, max_age: int) -> Optional[Any]:
    key = _cache_key(url, params, kind)
    payload_path, meta_path = _paths(key, kind)
    if not payload_path.exists() or not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        saved_at = float(meta.get("saved_at", 0.0))
        age = time.time() - saved_at
        if age < 0 or age > max_age:
            return None
        if kind == "json":
            value = json.loads(payload_path.read_text(encoding="utf-8"))
            if not isinstance(value, dict):
                return None
        else:
            value = payload_path.read_bytes()
        print(f"DART STALE CACHE FALLBACK: age={int(age)}s key={key[:10]}")
        return value
    except Exception as error:
        print("DART CACHE READ WARNING:", type(error).__name__, error)
        return None


def _write_cache(url: str, params: Dict[str, Any], kind: str, value: Any) -> None:
    key = _cache_key(url, params, kind)
    payload_path, meta_path = _paths(key, kind)
    try:
        CACHE_ROOT.mkdir(parents=True, exist_ok=True)
        if kind == "json":
            payload_path.write_text(
                json.dumps(value, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
        else:
            payload_path.write_bytes(bytes(value))
        meta_path.write_text(
            json.dumps(
                {
                    "saved_at": time.time(),
                    "url": url,
                    "params": _safe_params(params),
                    "kind": kind,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )
    except Exception as error:
        print("DART CACHE WRITE WARNING:", type(error).__name__, error)


def _record_success() -> None:
    global _FAILURES, _OPEN_UNTIL
    _FAILURES = 0
    _OPEN_UNTIL = 0.0


def _record_failure() -> None:
    global _FAILURES, _OPEN_UNTIL
    _FAILURES += 1
    if _FAILURES >= 1:
        _OPEN_UNTIL = max(_OPEN_UNTIL, time.time() + CIRCUIT_SECONDS)


def _circuit_open() -> bool:
    return time.time() < _OPEN_UNTIL


def get_json(
    url: str,
    params: Dict[str, Any],
    *,
    stale_seconds: int = JSON_STALE_SECONDS,
) -> Dict[str, Any]:
    if _circuit_open():
        cached = _read_cache(url, params, "json", stale_seconds)
        if cached is not None:
            return cached
        return {
            "status": "DART_CIRCUIT_OPEN",
            "message": "OpenDART 연결 실패 후 회로차단기가 동작했습니다. 잠시 후 재시도합니다.",
            "list": [],
        }

    try:
        response = _SESSION.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("OpenDART JSON response is not an object")
        _record_success()
        # API-level errors such as invalid key are not useful cache entries.
        if str(data.get("status", "")) == "000":
            _write_cache(url, params, "json", data)
        return data
    except Exception as error:
        _record_failure()
        cached = _read_cache(url, params, "json", stale_seconds)
        if cached is not None:
            return cached
        return {
            "status": "EXCEPTION",
            "message": f"{type(error).__name__}: {error}",
            "list": [],
        }


def get_bytes(
    url: str,
    params: Dict[str, Any],
    *,
    stale_seconds: int = DOCUMENT_STALE_SECONDS,
) -> bytes:
    if _circuit_open():
        cached = _read_cache(url, params, "bytes", stale_seconds)
        if cached is not None:
            return cached
        raise RuntimeError("OpenDART circuit open and no cached document is available")

    try:
        response = _SESSION.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        response.raise_for_status()
        content = response.content
        if not content:
            raise ValueError("OpenDART document response is empty")
        _record_success()
        _write_cache(url, params, "bytes", content)
        return content
    except Exception:
        _record_failure()
        cached = _read_cache(url, params, "bytes", stale_seconds)
        if cached is not None:
            return cached
        raise
