"""Korea Industry Environment Engine bridge collector.

Design goals
- Reuse one published ``stock_prediction_bridge.json`` instead of recollecting
  the same industry market inputs per stock.
- Memory cache first. Across processes, disk cache is conditionally revalidated
  against the published bridge before reuse so a just-finished industry-engine run
  is visible immediately to the next company run.
- No retry loop. On failure, only a fresh last-known-good cache may be reused.
- Reject stale/malformed/low-quality bridge data rather than inventing neutral
  values.
- Keep the bridge auxiliary-only until the upstream contract explicitly allows
  primary use. The stock predictor consumes only the upstream bounded overlay.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

import requests


DEFAULT_BRIDGE_URL = (
    "https://raw.githubusercontent.com/12xx37r-ui/"
    "KOREA_INDUSTRY_ENVIRONMENT_ENGINE/main/output/stock_prediction_bridge.json"
)
CACHE_TTL_SECONDS = int(os.getenv("INDUSTRY_ENV_CACHE_TTL_SECONDS", "21600"))  # 6h
STALE_IF_ERROR_SECONDS = int(os.getenv("INDUSTRY_ENV_STALE_IF_ERROR_SECONDS", "432000"))  # 120h
MAX_SOURCE_AGE_SECONDS = int(os.getenv("INDUSTRY_ENV_MAX_SOURCE_AGE_SECONDS", "432000"))  # 120h
MIN_QUALITY_SCORE = float(os.getenv("INDUSTRY_ENV_MIN_QUALITY_SCORE", "50"))
CACHE_FILE = Path(os.getenv("INDUSTRY_ENV_CACHE_FILE", ".cache/industry_environment_bridge.json"))

# Stock valuation profiles that are unambiguous equivalents of the new industry
# environment profiles. Broad/ambiguous profiles are intentionally not guessed.
PROFILE_COMPATIBILITY = {
    "pharmaceutical": "biotechnology",
    "consumer_staples": "food_beverage",
    "utilities": "utilities_power",
    "industrial": "industrial_machinery",
    "transportation": "transport_logistics",
    "energy": "refining_energy",
}

DIRECT_PROFILE_HINTS = {
    "semiconductor",
    "electronic_components",
    "display",
    "automotive",
    "battery",
    "shipbuilding",
    "construction",
    "industrial_machinery",
    "defense_aerospace",
    "steel_materials",
    "chemicals",
    "refining_energy",
    "finance",
    "insurance",
    "securities",
    "biotechnology",
    "medical_devices",
    "software_platform",
    "gaming",
    "media_entertainment",
    "retail",
    "food_beverage",
    "transport_logistics",
    "utilities_power",
    "telecom",
}

_MEMORY: Dict[str, Any] = {
    "at": 0.0,
    "payload": None,
    "source": "",
    "mode": "",
}
_NETWORK_CALLS = 0


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _normalize_code(value: Any) -> str:
    return str(value or "").strip()


def can_use_bridge_hint(industry_code: Any) -> bool:
    """Return False for profiles that cannot be safely mapped without guessing.

    This check happens before any network access, so broad profiles such as
    ``materials`` or ``services`` do not trigger a pointless GitHub request.
    """
    code = _normalize_code(industry_code)
    return code in DIRECT_PROFILE_HINTS or code in PROFILE_COMPATIBILITY


def _parse_generated_at(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _source_age_seconds(payload: Dict[str, Any], now: Optional[datetime] = None) -> Optional[float]:
    generated = _parse_generated_at(payload.get("generated_at_utc"))
    if generated is None:
        return None
    current = now or datetime.now(timezone.utc)
    return max(0.0, (current - generated).total_seconds())


def _read_json(path: Path) -> Dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            if os.path.exists(temporary_name):
                os.remove(temporary_name)
        except OSError:
            pass


def _cache_payload(record: Dict[str, Any]) -> Dict[str, Any]:
    payload = record.get("payload") if isinstance(record, dict) else None
    return payload if isinstance(payload, dict) else {}


def _cache_age(record: Dict[str, Any], now: float) -> float:
    try:
        return max(0.0, now - float(record.get("fetched_at") or 0.0))
    except Exception:
        return float("inf")


def _validate_payload_shape(payload: Dict[str, Any]) -> Tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, "bridge payload is not an object"
    if not isinstance(payload.get("by_profile_key"), dict):
        return False, "by_profile_key missing"
    if not isinstance(payload.get("alias_to_profile_key"), dict):
        return False, "alias_to_profile_key missing"
    if not str(payload.get("generated_at_utc") or "").strip():
        return False, "generated_at_utc missing"
    return True, ""


def _payload_fresh_enough(payload: Dict[str, Any]) -> Tuple[bool, Optional[float], str]:
    age = _source_age_seconds(payload)
    if age is None:
        return False, None, "generated_at_utc parse failed"
    if age > MAX_SOURCE_AGE_SECONDS:
        return False, age, f"bridge source stale: {age / 3600.0:.1f}h"
    return True, age, ""


def _payload_result(status: str, source: str, mode: str, payload: Dict[str, Any], **extra: Any) -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "수집상태": status,
        "출처": source,
        "캐시모드": mode,
        "payload": payload,
        "HTTP호출수": int(extra.pop("http_calls", 0)),
    }
    result.update(extra)
    return result


def _load_local_file(path_text: str) -> Dict[str, Any]:
    payload = _read_json(Path(path_text))
    valid, error = _validate_payload_shape(payload)
    if not valid:
        return _payload_result("실패", "local_file", "local", {}, 오류=error)
    fresh, age, stale_error = _payload_fresh_enough(payload)
    if not fresh:
        return _payload_result(
            "연결대기",
            "local_file",
            "local_stale",
            payload,
            오류=stale_error,
            소스나이시간=round((age or 0.0) / 3600.0, 2) if age is not None else None,
        )
    return _payload_result(
        "정상",
        "local_file",
        "local",
        payload,
        소스나이시간=round((age or 0.0) / 3600.0, 2),
    )


def get_industry_environment_bridge() -> Dict[str, Any]:
    """Load the published bridge with at most one network call per process.

    Memory reuse prevents duplicate calls inside one process. A disk cache is not
    trusted solely because its TTL is fresh: every new process performs one cheap
    conditional GET (ETag/Last-Modified) so a newly published industry-engine bridge
    replaces stale disk data immediately.
    """
    global _NETWORK_CALLS

    local_file = os.getenv("INDUSTRY_ENV_BRIDGE_LOCAL_FILE", "").strip()
    if local_file:
        return _load_local_file(local_file)

    now = time.time()
    memory_payload = _MEMORY.get("payload")
    if isinstance(memory_payload, dict) and now - float(_MEMORY.get("at") or 0.0) <= CACHE_TTL_SECONDS:
        fresh, age, error = _payload_fresh_enough(memory_payload)
        if fresh:
            return _payload_result(
                "정상",
                str(_MEMORY.get("source") or "memory_cache"),
                "memory_cache",
                memory_payload,
                소스나이시간=round((age or 0.0) / 3600.0, 2),
            )
        return _payload_result(
            "연결대기",
            str(_MEMORY.get("source") or "memory_cache"),
            "memory_stale",
            memory_payload,
            오류=error,
            소스나이시간=round((age or 0.0) / 3600.0, 2) if age is not None else None,
        )

    disk = _read_json(CACHE_FILE)
    disk_payload = _cache_payload(disk)
    disk_age = _cache_age(disk, now)

    # IMPORTANT: do not return a fresh disk cache here. The industry engine may
    # have published a newer stock_prediction_bridge.json seconds after this
    # cache was written. Each new company-engine process therefore revalidates
    # the disk copy once against GitHub using ETag/Last-Modified. If unchanged,
    # GitHub returns 304 and the cached payload is reused cheaply.
    url = os.getenv("INDUSTRY_ENV_BRIDGE_URL", DEFAULT_BRIDGE_URL).strip()
    if not url:
        return _payload_result("미사용", "disabled", "disabled", {}, 오류="bridge URL disabled")

    headers = {"User-Agent": "StockAnalysisIndustryBridge/1.1", "Cache-Control": "no-cache"}
    if isinstance(disk, dict):
        etag = str(disk.get("etag") or "").strip()
        last_modified = str(disk.get("last_modified") or "").strip()
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

    try:
        _NETWORK_CALLS += 1
        response = requests.get(url, headers=headers, timeout=8)

        if response.status_code == 304 and disk_payload:
            valid, shape_error = _validate_payload_shape(disk_payload)
            fresh, source_age, stale_error = _payload_fresh_enough(disk_payload) if valid else (False, None, shape_error)
            if not valid or not fresh:
                return _payload_result(
                    "연결대기",
                    url,
                    "http_304_stale",
                    disk_payload,
                    http_calls=1,
                    오류=stale_error or shape_error,
                    소스나이시간=round((source_age or 0.0) / 3600.0, 2) if source_age is not None else None,
                )
            refreshed = dict(disk)
            refreshed["fetched_at"] = now
            try:
                _atomic_write_json(CACHE_FILE, refreshed)
            except Exception:
                pass
            _MEMORY.update({"at": now, "payload": disk_payload, "source": url, "mode": "http_304"})
            return _payload_result(
                "정상",
                url,
                "http_304_cache",
                disk_payload,
                http_calls=1,
                소스나이시간=round((source_age or 0.0) / 3600.0, 2),
            )

        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("industry environment bridge response is not an object")

        valid, shape_error = _validate_payload_shape(payload)
        if not valid:
            raise ValueError(shape_error)
        fresh, source_age, stale_error = _payload_fresh_enough(payload)
        if not fresh:
            return _payload_result(
                "연결대기",
                url,
                "network_stale",
                payload,
                http_calls=1,
                오류=stale_error,
                소스나이시간=round((source_age or 0.0) / 3600.0, 2) if source_age is not None else None,
            )

        record = {
            "schema": "industry-environment-bridge-cache-v1",
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
        _MEMORY.update({"at": now, "payload": payload, "source": url, "mode": "network_refresh"})
        return _payload_result(
            "정상",
            url,
            "network_refresh",
            payload,
            http_calls=1,
            소스나이시간=round((source_age or 0.0) / 3600.0, 2),
        )

    except Exception as exc:
        # No retry loop. A recent last-known-good cache is the only fallback.
        if disk_payload and disk_age <= STALE_IF_ERROR_SECONDS:
            valid, shape_error = _validate_payload_shape(disk_payload)
            fresh, source_age, stale_error = _payload_fresh_enough(disk_payload) if valid else (False, None, shape_error)
            if valid and fresh:
                _MEMORY.update({"at": now, "payload": disk_payload, "source": "stale_if_error", "mode": "stale_if_error"})
                return _payload_result(
                    "캐시사용",
                    "stale_if_error",
                    "stale_if_error",
                    disk_payload,
                    http_calls=1,
                    오류=str(exc),
                    캐시나이초=round(disk_age, 1),
                    소스나이시간=round((source_age or 0.0) / 3600.0, 2),
                )
        return _payload_result("실패", url, "network_error", {}, http_calls=1, 오류=str(exc))


def _resolve_profile_key(payload: Dict[str, Any], candidates: Iterable[Any]) -> str:
    by_profile = payload.get("by_profile_key") if isinstance(payload, dict) else {}
    alias_map = payload.get("alias_to_profile_key") if isinstance(payload, dict) else {}
    by_profile = by_profile if isinstance(by_profile, dict) else {}
    alias_map = alias_map if isinstance(alias_map, dict) else {}

    normalized = [_normalize_code(value) for value in candidates if _normalize_code(value)]

    for candidate in normalized:
        if candidate in by_profile:
            return candidate
        mapped = str(alias_map.get(candidate) or "").strip()
        if mapped in by_profile:
            return mapped
        compatibility = PROFILE_COMPATIBILITY.get(candidate, "")
        if compatibility in by_profile:
            return compatibility

    return ""


def get_industry_environment(industry_code: Any, aliases: Optional[Iterable[Any]] = None) -> Dict[str, Any]:
    """Return one validated profile from the published 25-industry bridge."""
    requested = _normalize_code(industry_code)
    alias_values = list(aliases or [])

    if not can_use_bridge_hint(requested) and not any(can_use_bridge_hint(value) for value in alias_values):
        return {
            "수집상태": "미적용",
            "사용가능": False,
            "요청산업코드": requested,
            "매핑산업코드": "",
            "오류": "안전하게 매핑할 수 없는 광범위 산업프로필",
            "HTTP호출수": 0,
        }

    bridge = get_industry_environment_bridge()
    payload = bridge.get("payload") if isinstance(bridge, dict) else {}
    payload = payload if isinstance(payload, dict) else {}

    if bridge.get("수집상태") not in {"정상", "캐시사용"} or not payload:
        return {
            "수집상태": bridge.get("수집상태", "실패"),
            "사용가능": False,
            "요청산업코드": requested,
            "매핑산업코드": "",
            "출처": bridge.get("출처", ""),
            "캐시모드": bridge.get("캐시모드", ""),
            "소스나이시간": bridge.get("소스나이시간"),
            "HTTP호출수": bridge.get("HTTP호출수", 0),
            "오류": bridge.get("오류", "bridge unavailable"),
        }

    profile_key = _resolve_profile_key(payload, [requested, *alias_values])
    by_profile = payload.get("by_profile_key") if isinstance(payload.get("by_profile_key"), dict) else {}
    profile = by_profile.get(profile_key) if profile_key else None
    profile = profile if isinstance(profile, dict) else {}

    if not profile:
        return {
            "수집상태": "미적용",
            "사용가능": False,
            "요청산업코드": requested,
            "매핑산업코드": "",
            "출처": bridge.get("출처", ""),
            "캐시모드": bridge.get("캐시모드", ""),
            "소스나이시간": bridge.get("소스나이시간"),
            "HTTP호출수": bridge.get("HTTP호출수", 0),
            "오류": "bridge profile mapping not found",
        }

    current_score = _safe_float(profile.get("current_score"))
    forecast_score = _safe_float(profile.get("forecast_3m_score"))
    delta_points = _safe_float(profile.get("delta_points"))
    quality_score = _safe_float(profile.get("quality_score"))
    adjustment = _safe_float(profile.get("bounded_direction_adjustment_points"))
    upstream_max_adjustment = _safe_float(profile.get("max_abs_adjustment_points"))
    # The published stock bridge may omit the upstream max because the adjustment
    # is already bounded. In that case, never invent extra headroom: use the
    # absolute published adjustment itself as the local defensive ceiling.
    max_adjustment = (
        upstream_max_adjustment
        if upstream_max_adjustment is not None
        else (abs(adjustment) if adjustment is not None else None)
    )
    allowed_aux = profile.get("allowed_as_auxiliary") is True
    allowed_primary = profile.get("allowed_as_primary") is True

    numeric_valid = (
        current_score is not None
        and forecast_score is not None
        and delta_points is not None
        and quality_score is not None
        and adjustment is not None
        and max_adjustment is not None
        and 0.0 <= current_score <= 100.0
        and 0.0 <= forecast_score <= 100.0
        and 0.0 <= quality_score <= 100.0
        and max_adjustment >= 0.0
    )

    # Contract-aligned environment gate: quality >= 50 is enough to use the
    # current/3M industry environment as context/display. The stock-direction
    # overlay remains separately gated by upstream OOS validation.
    display_usable = bool(
        numeric_valid
        and quality_score >= MIN_QUALITY_SCORE
    )
    environment_usable = display_usable
    overlay_usable = bool(display_usable and allowed_aux)
    error = ""
    if not numeric_valid:
        error = "bridge profile numeric contract invalid"
    elif quality_score < MIN_QUALITY_SCORE:
        error = f"quality below threshold: {quality_score:.1f} < {MIN_QUALITY_SCORE:.1f}"
    elif not allowed_aux:
        error = "environment usable; stock-direction overlay awaiting upstream OOS validation"

    bounded_adjustment = None
    if adjustment is not None and max_adjustment is not None:
        bounded_adjustment = _clamp(adjustment, -abs(max_adjustment), abs(max_adjustment))

    return {
        "수집상태": "정상" if environment_usable else "연결대기",
        "사용가능": environment_usable,
        "자료표시가능": display_usable,
        "표시상태": "정상" if display_usable else "연결대기",
        "모형사용가능": overlay_usable,
        "모형사용상태": "정상" if overlay_usable else "검증대기",
        "요청산업코드": requested,
        "매핑산업코드": profile_key,
        "산업명": str(profile.get("industry_label") or profile_key),
        "생성시각UTC": str(payload.get("generated_at_utc") or ""),
        "현재점수": round(current_score, 2) if current_score is not None else None,
        "현재구간": str(profile.get("current_band") or ""),
        "3개월점수": round(forecast_score, 2) if forecast_score is not None else None,
        "3개월구간": str(profile.get("forecast_3m_band") or ""),
        "변화점수": round(delta_points, 2) if delta_points is not None else None,
        "방향": str(profile.get("direction") or ""),
        "품질점수": round(quality_score, 2) if quality_score is not None else None,
        "개별종목방향보정점수": round(bounded_adjustment, 4) if bounded_adjustment is not None else None,
        "보정최대절대값": round(abs(max_adjustment), 4) if max_adjustment is not None else None,
        "보정상한출처": (
            "upstream max_abs_adjustment_points"
            if upstream_max_adjustment is not None
            else "published bounded adjustment itself"
        ),
        "보조사용허용": allowed_aux,
        "주신호사용허용": allowed_primary,
        "사용규칙": str(payload.get("usage_rule") or ""),
        "출처": bridge.get("출처", DEFAULT_BRIDGE_URL),
        "캐시모드": bridge.get("캐시모드", ""),
        "소스나이시간": bridge.get("소스나이시간"),
        "HTTP호출수": bridge.get("HTTP호출수", 0),
        "오류": error,
    }


def build_environment_replacement(industry_code: Any, environment: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Build a backward-compatible industry summary without turning 3M data primary.

    ``중기산업선행`` and ``장기산업사이클`` intentionally stay empty. This
    prevents the unvalidated 3M bridge from entering valuation or the legacy
    25-point direction factors as a primary signal. Predictor code consumes the
    bounded auxiliary overlay separately.
    """
    requested = _normalize_code(industry_code)
    if not isinstance(environment, dict) or environment.get("사용가능") is not True:
        return (
            {
                "전체수집상태": "미적용",
                "산업코드": requested,
                "산업명": requested or "미분류",
                "자산": {},
                "수집오류": [str(environment.get("오류") or "industry environment unavailable")] if isinstance(environment, dict) else [],
                "데이터출처": "",
            },
            {
                "분석상태": "미적용",
                "산업명": requested or "미분류",
                "중기산업선행": {},
                "장기산업사이클": {},
                "산업국면": "미분류",
            },
        )

    current_score = float(environment["현재점수"])
    forecast_score = float(environment["3개월점수"])
    quality = float(environment["품질점수"])
    current_signal = _clamp((current_score - 50.0) * 2.0, -100.0, 100.0)
    forecast_signal = _clamp((forecast_score - 50.0) * 2.0, -100.0, 100.0)
    label = str(environment.get("산업명") or requested)

    analysis = {
        "분석상태": "정상",
        "산업명": label,
        "산업환경브리지모드": "보조전용",
        "산업환경현재": {
            "점수": round(current_score, 2),
            "신호": round(current_signal, 2),
            "구간": environment.get("현재구간", ""),
            "데이터품질": round(quality, 2),
            "출처": environment.get("출처", ""),
        },
        "산업환경3개월": {
            "점수": round(forecast_score, 2),
            "신호": round(forecast_signal, 2),
            "구간": environment.get("3개월구간", ""),
            "변화점수": environment.get("변화점수"),
            "방향": environment.get("방향", ""),
            "데이터품질": round(quality, 2),
            "출처": environment.get("출처", ""),
        },
        "개별종목방향보정": {
            "보조사용허용": environment.get("보조사용허용") is True,
            "주신호사용허용": environment.get("주신호사용허용") is True,
            "보정점수": environment.get("개별종목방향보정점수"),
            "최대절대값": environment.get("보정최대절대값"),
        },
        # Deliberately empty: 3M environment is not promoted into legacy primary axes.
        "중기산업선행": {},
        "장기산업사이클": {},
        "산업국면": f"{environment.get('3개월구간', '')} · {environment.get('방향', '')}".strip(" ·"),
    }

    bundle = {
        "전체수집상태": "정상",
        "산업코드": requested,
        "산업명": label,
        "자산": {},
        "수집오류": [],
        "수집시각": environment.get("생성시각UTC", ""),
        "데이터출처": "Korea Industry Environment Engine / stock_prediction_bridge.json",
    }
    return bundle, analysis


def reset_runtime_cache_for_tests() -> None:
    global _NETWORK_CALLS
    _MEMORY.update({"at": 0.0, "payload": None, "source": "", "mode": ""})
    _NETWORK_CALLS = 0
