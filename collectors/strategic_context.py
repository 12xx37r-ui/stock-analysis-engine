"""별도 글로벌 거시 엔진의 결과 JSON을 저부하 방식으로 재사용한다.

원칙
- 주식엔진이 글로벌 매크로/Fed 데이터를 다시 계산하거나 재수집하지 않는다.
- 글로벌 매크로 엔진이 만든 cards_8_12_bundle.json 한 파일만 필요할 때 읽는다.
- 같은 프로세스 메모리 캐시 -> 디스크 TTL 캐시 -> 조건부 HTTP 순으로 사용한다.
- ETag/Last-Modified를 보관해 stale cache 갱신 시 가능하면 304 응답만 받는다.
- 네트워크 실패 시 일정 기간 last-known-good를 재사용한다.
- 요청 재시도 루프를 두지 않는다. 한 번 실패하면 캐시/중립 fallback으로 끝낸다.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator, Optional

import requests


DEFAULT_GLOBAL_MACRO_URL = (
    "https://raw.githubusercontent.com/12xx37r-ui/"
    "global-macro-data-collector/main/public/data/cards_8_12_bundle.json"
)
CACHE_TTL_SECONDS = int(os.getenv("STRATEGIC_MACRO_CACHE_TTL_SECONDS", "21600"))  # 6h
STALE_IF_ERROR_SECONDS = int(os.getenv("STRATEGIC_MACRO_STALE_IF_ERROR_SECONDS", "259200"))  # 72h
CACHE_FILE = Path(os.getenv("STRATEGIC_MACRO_CACHE_FILE", ".cache/strategic_macro_context.json"))
LOCK_FILE = Path(os.getenv("STRATEGIC_MACRO_LOCK_FILE", ".cache/strategic_macro_context.lock"))
LOCK_WAIT_SECONDS = float(os.getenv("STRATEGIC_MACRO_LOCK_WAIT_SECONDS", "2"))
_CACHE: Dict[str, Any] = {"at": 0.0, "payload": None, "source": ""}


def _load_local(path: str) -> Dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _read_disk_cache() -> Dict[str, Any]:
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        try:
            if os.path.exists(temp_name):
                os.remove(temp_name)
        except OSError:
            pass


@contextmanager
def _best_effort_file_lock() -> Iterator[bool]:
    """여러 프로세스가 동시에 stale cache를 갱신하는 중복 요청을 줄인다.

    Linux/GitHub Actions와 Windows 모두에서 동작하도록 O_EXCL lock file을 쓴다.
    lock을 못 잡아도 분석 자체를 막지 않는다.
    """
    LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + max(0.0, LOCK_WAIT_SECONDS)
    acquired = False
    fd: Optional[int] = None
    while time.time() <= deadline:
        try:
            fd = os.open(str(LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode("ascii", errors="ignore"))
            acquired = True
            break
        except FileExistsError:
            time.sleep(0.05)
        except OSError:
            break
    try:
        yield acquired
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        if acquired:
            try:
                LOCK_FILE.unlink(missing_ok=True)
            except OSError:
                pass


def _payload_from_cache_record(record: Dict[str, Any]) -> Dict[str, Any]:
    payload = record.get("payload") if isinstance(record, dict) else None
    return payload if isinstance(payload, dict) else {}


def _age_seconds(record: Dict[str, Any], now: float) -> float:
    try:
        return max(0.0, now - float(record.get("fetched_at") or 0.0))
    except Exception:
        return float("inf")


def _result(status: str, source: str, payload: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {"수집상태": status, "출처": source, "payload": payload}
    out.update(extra)
    return out


def get_strategic_macro_context() -> Dict[str, Any]:
    """전략미래가치에 필요한 글로벌 매크로 bundle을 최소 호출로 반환한다."""
    local_file = os.getenv("STRATEGIC_MACRO_LOCAL_FILE", "").strip()
    if local_file:
        try:
            return _result("정상", "local_file", _load_local(local_file), 캐시="local")
        except Exception as exc:
            return _result("실패", "local_file", {}, 오류=str(exc))

    now = time.time()
    cached = _CACHE.get("payload")
    if isinstance(cached, dict) and now - float(_CACHE.get("at") or 0.0) <= CACHE_TTL_SECONDS:
        return _result("정상", "memory_cache", cached, 캐시="memory")

    disk = _read_disk_cache()
    disk_payload = _payload_from_cache_record(disk)
    disk_age = _age_seconds(disk, now)
    if disk_payload and disk_age <= CACHE_TTL_SECONDS:
        _CACHE.update({"at": now, "payload": disk_payload, "source": "disk_cache"})
        return _result("정상", "disk_cache", disk_payload, 캐시="disk", 캐시나이초=round(disk_age, 1))

    url = os.getenv("GLOBAL_MACRO_BUNDLE_URL", DEFAULT_GLOBAL_MACRO_URL).strip()
    if not url:
        if disk_payload and disk_age <= STALE_IF_ERROR_SECONDS:
            return _result("캐시사용", "stale_disk_cache", disk_payload, 캐시="stale", 캐시나이초=round(disk_age, 1))
        return _result("미사용", "disabled", {})

    # 다른 분석 프로세스가 동시에 갱신 중이면 lock 획득 후 디스크를 한 번 더 확인한다.
    with _best_effort_file_lock() as acquired:
        if acquired:
            disk = _read_disk_cache()
            disk_payload = _payload_from_cache_record(disk)
            disk_age = _age_seconds(disk, time.time())
            if disk_payload and disk_age <= CACHE_TTL_SECONDS:
                _CACHE.update({"at": time.time(), "payload": disk_payload, "source": "disk_cache"})
                return _result("정상", "disk_cache", disk_payload, 캐시="disk_after_lock", 캐시나이초=round(disk_age, 1))

        headers = {"User-Agent": "StockStrategicForward/0.2"}
        etag = str(disk.get("etag") or "").strip() if isinstance(disk, dict) else ""
        last_modified = str(disk.get("last_modified") or "").strip() if isinstance(disk, dict) else ""
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        try:
            # 정확도보다 호출량을 희생하지 않도록 자동 retry를 두지 않는다.
            response = requests.get(url, headers=headers, timeout=8)
            if response.status_code == 304 and disk_payload:
                refreshed = dict(disk)
                refreshed["fetched_at"] = now
                try:
                    _atomic_write_json(CACHE_FILE, refreshed)
                except Exception:
                    pass
                _CACHE.update({"at": now, "payload": disk_payload, "source": "http_304"})
                return _result("정상", "http_304_cache", disk_payload, 캐시="conditional_304")

            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("global macro payload is not an object")

            record = {
                "schema": "strategic-macro-cache-v2",
                "fetched_at": now,
                "url": url,
                "etag": response.headers.get("ETag", ""),
                "last_modified": response.headers.get("Last-Modified", ""),
                "payload": payload,
            }
            try:
                _atomic_write_json(CACHE_FILE, record)
            except Exception:
                pass
            _CACHE.update({"at": now, "payload": payload, "source": url})
            return _result("정상", url, payload, 캐시="network_refresh")
        except Exception as exc:
            # 네트워크 장애 때 짧은 간격으로 재호출하지 않고 last-known-good로 종료한다.
            if disk_payload and disk_age <= STALE_IF_ERROR_SECONDS:
                _CACHE.update({"at": now, "payload": disk_payload, "source": "stale_disk_cache"})
                return _result(
                    "캐시사용",
                    "stale_disk_cache",
                    disk_payload,
                    오류=str(exc),
                    캐시="stale_if_error",
                    캐시나이초=round(disk_age, 1),
                )
            return _result("실패", url, {}, 오류=str(exc))
