"""Korean stock price validation and cache helpers.

This module is intentionally isolated from valuation and KIS token management.
Collectors provide price candidates; this module validates freshness, market,
corporate-action consistency, and cache eligibility before a candidate is
published as the current price.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

PRICE_SCHEMA_VERSION = "3.0.0"
PRICE_CACHE_DIR = Path(os.getenv("PRICE_CACHE_DIR", ".cache/prices/v3"))
KST = ZoneInfo("Asia/Seoul")
UTC = timezone.utc

# Large enough to tolerate Korean long weekends, but never months-old prices.
MAX_FALLBACK_CALENDAR_AGE_DAYS = 7
CAP_TOLERANCE_RATIO = 0.35
CAP_HARD_REJECT_RATIO = 0.60
SHARE_CHANGE_WARN_RATIO = 0.20
SHARE_CHANGE_REJECT_RATIO = 0.45
PRICE_MULTIPLE_SUSPECT_RATIO = 0.45


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return default


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def now_kst() -> datetime:
    return datetime.now(tz=KST)


def iso_kst(value: Optional[datetime] = None) -> str:
    target = value or now_kst()
    if target.tzinfo is None:
        target = target.replace(tzinfo=KST)
    return target.astimezone(KST).isoformat(timespec="seconds")


def parse_datetime(value: Any, default_tz=KST) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        try:
            parsed = datetime.fromtimestamp(float(value), tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            for pattern in ("%Y%m%d", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
                try:
                    parsed = datetime.strptime(text, pattern)
                    break
                except ValueError:
                    parsed = None
            if parsed is None:
                return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=default_tz)
    return parsed.astimezone(KST)


def parse_date(value: Any) -> Optional[date]:
    parsed = parse_datetime(value)
    if parsed:
        return parsed.date()
    if isinstance(value, date):
        return value
    return None


def market_status(at: Optional[datetime] = None) -> str:
    current = (at or now_kst()).astimezone(KST)
    if current.weekday() >= 5:
        return "장마감"
    clock = current.time().replace(tzinfo=None)
    if time(9, 0) <= clock < time(15, 30):
        return "장중"
    if time(15, 30) <= clock < time(20, 0):
        return "애프터마켓"
    return "장마감"


def _calendar_latest_session(current: date) -> Optional[date]:
    """Return the latest XKRX session when exchange_calendars is available."""
    try:
        import exchange_calendars as xcals  # optional runtime dependency

        calendar = xcals.get_calendar("XKRX")
        start = current - timedelta(days=15)
        sessions = calendar.sessions_in_range(start.isoformat(), current.isoformat())
        if len(sessions):
            latest = sessions[-1]
            return latest.tz_convert(KST).date() if getattr(latest, "tz", None) else latest.date()
    except Exception:
        pass
    probe = current
    while probe.weekday() >= 5:
        probe -= timedelta(days=1)
    return probe


def latest_allowed_trade_date(at: Optional[datetime] = None) -> date:
    current = (at or now_kst()).astimezone(KST)
    latest_session = _calendar_latest_session(current.date()) or current.date()
    clock = current.time().replace(tzinfo=None)
    # Before the KRX opening bell, today's session has not produced a price yet.
    if latest_session == current.date() and clock < time(9, 0):
        previous = _calendar_latest_session(current.date() - timedelta(days=1))
        if previous is not None:
            return previous
    return latest_session


def previous_allowed_trade_date(current_session: date) -> date:
    previous = _calendar_latest_session(current_session - timedelta(days=1))
    return previous or (current_session - timedelta(days=1))


def evaluate_freshness(
    price_date: Optional[date],
    at: Optional[datetime] = None,
    suspended: bool = False,
) -> Tuple[bool, str, int]:
    current = (at or now_kst()).astimezone(KST)
    if price_date is None:
        return False, "가격 기준일 없음 또는 파싱 실패", 99999
    if price_date > current.date():
        return False, "미래 날짜 가격", -1
    latest = latest_allowed_trade_date(current)
    age = (current.date() - price_date).days
    if suspended:
        return True, "거래정지 · 마지막 거래일 명시", age
    if price_date == latest:
        return True, "최신 거래일", age
    if market_status(current) == "장중" and price_date == previous_allowed_trade_date(latest):
        return True, "장중 직전 거래일 종가", age
    if age <= MAX_FALLBACK_CALENDAR_AGE_DAYS:
        # Only accept if there is no known XKRX session after the candidate.
        try:
            import exchange_calendars as xcals

            calendar = xcals.get_calendar("XKRX")
            later = calendar.sessions_in_range(
                (price_date + timedelta(days=1)).isoformat(),
                current.date().isoformat(),
            )
            if len(later) == 0:
                return True, "연휴·휴장 직전 최신 거래일", age
        except Exception:
            if price_date.weekday() < 5 and latest <= price_date:
                return True, "주말 직전 최신 거래일", age
    return False, f"오래된 가격({age}일 경과)", age


def normalize_yahoo_market(exchange_name: Any) -> str:
    text = str(exchange_name or "").strip().upper()
    if text in {"KOE", "KOSDAQ", "KQ", "XKOS"} or "KOSDAQ" in text:
        return "KOSDAQ"
    if text in {"KSC", "KSE", "KOSPI", "KS", "XKRX"} or "KOSPI" in text:
        return "KOSPI"
    return ""


def suffix_market(symbol: str) -> str:
    text = str(symbol or "").upper()
    if text.endswith(".KQ"):
        return "KOSDAQ"
    if text.endswith(".KS"):
        return "KOSPI"
    return ""


def normalized_market_code(value: Any) -> str:
    text = str(value or "").strip().upper()
    if text in {"Q", "KQ", "KOSDAQ", "KOE"}:
        return "KOSDAQ"
    if text in {"K", "P", "KS", "KOSPI", "KSC", "KSE"}:
        return "KOSPI"
    return ""


def _diagnostic_defaults(stock_code: str) -> Dict[str, Any]:
    return {
        "가격스키마버전": PRICE_SCHEMA_VERSION,
        "종목코드": str(stock_code).zfill(6),
        "시장구분": "",
        "거래시장": "KRX",
        "가격": 0.0,
        "가격기준일": "",
        "가격기준시각": "",
        "수집시각": iso_kst(),
        "가격수집시각": iso_kst(),
        "가격출처": "",
        "가격종류": "",
        "실시간가종가애프터마켓": "",
        "조정주가여부": False,
        "캐시사용여부": False,
        "캐시생성시각": "",
        "캐시버전": PRICE_SCHEMA_VERSION,
        "가격신선도": "검증 전",
        "검증상태": "검증 전",
        "최종채택": False,
        "거부사유": [],
        "발행주식수": 0,
        "시가총액": 0.0,
        "가격곱하기발행주식수": 0.0,
        "시가총액일관성결과": "검증 불가",
        "발행주식수검증결과": "검증 불가",
        "기업행위의심여부": False,
        "시장상태": market_status(),
    }


def candidate(
    stock_code: str,
    *,
    market: str,
    trading_market: str,
    price: float,
    price_date: Any,
    price_time: Any,
    collected_at: Any,
    source: str,
    price_type: str,
    adjusted: bool,
    volume: int,
    market_cap: float = 0.0,
    source_share_count: int = 0,
    symbol: str = "",
    exchange: str = "",
    status: str = "",
    open_price: float = 0.0,
    high_price: float = 0.0,
    low_price: float = 0.0,
    previous_close: float = 0.0,
    cache_hit: bool = False,
    cache_created_at: str = "",
) -> Dict[str, Any]:
    date_parsed = parse_date(price_date)
    dt_collected = parse_datetime(collected_at) or now_kst()
    date_text = date_parsed.isoformat() if date_parsed else ""
    time_text = str(price_time or "").strip()
    return {
        "종목코드": str(stock_code).zfill(6),
        "시장구분": normalized_market_code(market) or str(market or ""),
        "거래시장": str(trading_market or "KRX").upper(),
        "가격": safe_float(price),
        "가격기준일": date_text,
        "가격기준시각": time_text,
        "수집시각": iso_kst(dt_collected),
        "가격수집시각": iso_kst(dt_collected),
        "가격출처": str(source or ""),
        "가격종류": str(price_type or ""),
        "실시간가종가애프터마켓": str(price_type or ""),
        "조정주가여부": bool(adjusted),
        "거래량": safe_int(volume),
        "시가총액": safe_float(market_cap),
        "출처발행주식수": safe_int(source_share_count),
        "심볼": str(symbol or ""),
        "거래소": str(exchange or ""),
        "시장상태": str(status or market_status(dt_collected)),
        "시가": safe_float(open_price),
        "고가": safe_float(high_price),
        "저가": safe_float(low_price),
        "전일종가": safe_float(previous_close),
        "캐시사용여부": bool(cache_hit),
        "캐시생성시각": str(cache_created_at or ""),
        "캐시버전": PRICE_SCHEMA_VERSION,
        "가격스키마버전": PRICE_SCHEMA_VERSION,
    }


def _cache_filename(c: Dict[str, Any]) -> Path:
    raw_key = "|".join(
        [
            str(c.get("종목코드", "")),
            str(c.get("시장구분", "")),
            str(c.get("거래시장", "")),
            str(c.get("가격출처", "")),
            str(c.get("가격기준일", "")),
            str(bool(c.get("조정주가여부"))),
            PRICE_SCHEMA_VERSION,
        ]
    )
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:24]
    return PRICE_CACHE_DIR / f"{c.get('종목코드', '000000')}-{digest}.json"


def write_price_cache(c: Dict[str, Any], share_count: int = 0) -> None:
    if not c or not c.get("최종채택") or c.get("기업행위의심여부"):
        return
    payload = dict(c)
    payload["캐시생성시각"] = iso_kst()
    payload["캐시버전"] = PRICE_SCHEMA_VERSION
    payload["캐시당시발행주식수"] = safe_int(share_count)
    path = _cache_filename(payload)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(path)
    except OSError as error:
        print("PRICE CACHE WRITE ERROR:", type(error).__name__, error)


def read_price_cache(
    stock_code: str,
    market: str,
    trading_market: str = "KRX",
    share_count: int = 0,
) -> Optional[Dict[str, Any]]:
    if not PRICE_CACHE_DIR.exists():
        return None
    code = str(stock_code).zfill(6)
    for path in sorted(PRICE_CACHE_DIR.glob(f"{code}-*.json"), reverse=True):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(payload.get("캐시버전", "")) != PRICE_SCHEMA_VERSION:
            continue
        if normalized_market_code(payload.get("시장구분")) != normalized_market_code(market):
            continue
        if str(payload.get("거래시장", "")).upper() != str(trading_market).upper():
            continue
        if payload.get("조정주가여부") is not False:
            continue
        if payload.get("기업행위의심여부") is True:
            continue
        valid, _, _ = evaluate_freshness(parse_date(payload.get("가격기준일")))
        if not valid:
            continue
        cached_shares = safe_int(payload.get("캐시당시발행주식수"))
        if share_count > 0 and cached_shares > 0:
            change = abs(share_count / cached_shares - 1.0)
            if change >= SHARE_CHANGE_WARN_RATIO:
                continue
        payload["캐시사용여부"] = True
        payload["가격출처"] = str(payload.get("가격출처", "")) + " (검증 캐시)"
        return payload
    return None


def _extract_latest_technical(technical_bundle: Dict[str, Any]) -> Tuple[float, Optional[date], int]:
    rows = safe_list(safe_dict(technical_bundle).get("최근일봉"))
    if rows:
        row = safe_dict(rows[-1])
        value = safe_float(row.get("종가"))
        row_date = parse_date(row.get("시각UTC") or row.get("timestamp"))
        volume = safe_int(row.get("거래량"))
        if value > 0:
            return value, row_date, volume
    daily = safe_dict(safe_dict(technical_bundle).get("일봉"))
    return (
        safe_float(daily.get("latestClose")),
        parse_date(safe_dict(technical_bundle).get("최종일")),
        0,
    )


def _normalize_market_cap(raw_market_cap: float, computed: float) -> float:
    raw = safe_float(raw_market_cap)
    if raw <= 0:
        return 0.0
    if computed <= 0:
        return raw
    options = [raw, raw * 1_000, raw * 1_000_000, raw * 100_000_000]
    return min(options, key=lambda value: abs(value / computed - 1.0) if value > 0 else 999999)


def validate_candidate(
    c: Dict[str, Any],
    *,
    stock_code: str,
    expected_market: str,
    share_count: int = 0,
    technical_bundle: Optional[Dict[str, Any]] = None,
    at: Optional[datetime] = None,
) -> Dict[str, Any]:
    result = _diagnostic_defaults(stock_code)
    result.update(c or {})
    reasons: List[str] = []
    warnings: List[str] = []
    result["가격스키마버전"] = PRICE_SCHEMA_VERSION
    result["캐시버전"] = PRICE_SCHEMA_VERSION
    result["종목코드"] = str(result.get("종목코드") or stock_code).zfill(6)
    expected_code = str(stock_code).zfill(6)

    if result["종목코드"] != expected_code:
        reasons.append("반환 종목코드 불일치")
    if safe_float(result.get("가격")) <= 0:
        reasons.append("가격이 0 이하")
    if result.get("조정주가여부") is not False:
        reasons.append("Adjusted Close 또는 조정주가")
    if not str(result.get("가격기준일", "")):
        reasons.append("가격 기준일 없음")
    if not str(result.get("가격기준시각", "")):
        reasons.append("가격 기준시각 없음")
    if str(result.get("거래시장", "")).upper() not in {"KRX", "NXT"}:
        reasons.append("거래시장 미식별")
    if str(result.get("거래시장", "")).upper() == "NXT" and "NXT" not in str(result.get("가격종류", "")).upper():
        reasons.append("NXT 가격종류 미표기")

    expected = normalized_market_code(expected_market)
    actual = normalized_market_code(result.get("시장구분"))
    if expected and actual and expected != actual:
        reasons.append(f"시장구분 불일치({expected}/{actual})")

    symbol = str(result.get("심볼", ""))
    exchange_market = normalize_yahoo_market(result.get("거래소"))
    suffix = suffix_market(symbol)
    if symbol and suffix and exchange_market and suffix != exchange_market:
        reasons.append(f"Yahoo 심볼·거래소 불일치({symbol}/{result.get('거래소')})")
    if expected and suffix and expected != suffix:
        reasons.append(f"Yahoo 심볼 시장 불일치({symbol}/{expected})")

    fresh, freshness_text, age = evaluate_freshness(parse_date(result.get("가격기준일")), at=at)
    result["가격신선도"] = freshness_text
    result["가격경과일수"] = age
    if not fresh:
        reasons.append(freshness_text)

    if safe_int(result.get("거래량")) <= 0 and result.get("시장상태") != "거래정지":
        reasons.append("거래량 없음 또는 비정상")

    financial_shares = safe_int(share_count)
    source_shares = safe_int(result.get("출처발행주식수"))
    price = safe_float(result.get("가격"))
    financial_computed_cap = price * financial_shares if price > 0 and financial_shares > 0 else 0.0
    source_computed_cap = price * source_shares if price > 0 and source_shares > 0 else 0.0
    reference_cap = source_computed_cap or financial_computed_cap
    market_cap = _normalize_market_cap(safe_float(result.get("시가총액")), reference_cap)

    corporate_action = False
    validation_shares = financial_shares or source_shares
    result["재무발행주식수"] = financial_shares
    result["출처발행주식수"] = source_shares

    source_cap_gap = (
        abs(market_cap / source_computed_cap - 1.0)
        if market_cap > 0 and source_computed_cap > 0
        else None
    )
    financial_cap_gap = (
        abs(market_cap / financial_computed_cap - 1.0)
        if market_cap > 0 and financial_computed_cap > 0
        else None
    )

    if financial_shares > 0 and source_shares > 0:
        share_change = abs(financial_shares / source_shares - 1.0)
        if share_change >= SHARE_CHANGE_WARN_RATIO:
            corporate_action = True
            warnings.append(f"발행주식 수 차이 {share_change:.1%}")

        # A current market source can legitimately contain post-corporate-action
        # shares while the latest annual DART filing is still stale. Keep DART
        # shares untouched for valuation, but validate the price against the
        # internally coherent current market-cap/share pair.
        if source_cap_gap is not None and source_cap_gap < CAP_TOLERANCE_RATIO:
            validation_shares = source_shares
            if share_change >= SHARE_CHANGE_WARN_RATIO:
                result["발행주식수검증결과"] = (
                    "시장 출처 주식 수와 시가총액 일치 · 재무 주식 수 차이로 기업행위 의심"
                )
            elif share_change > 0.01:
                result["발행주식수검증결과"] = (
                    f"시장 출처 주식 수 사용 · 재무 대비 {share_change:.1%} 차이"
                )
            else:
                result["발행주식수검증결과"] = "시장·재무 주식 수 일치"
        elif financial_cap_gap is not None and financial_cap_gap < CAP_TOLERANCE_RATIO:
            validation_shares = financial_shares
            result["발행주식수검증결과"] = "재무 주식 수와 시가총액 일치 · 출처 주식 수 주의"
        elif share_change >= SHARE_CHANGE_REJECT_RATIO:
            reasons.append("발행주식 수 급변과 시가총액을 일관되게 검증할 수 없음")
            result["발행주식수검증결과"] = "불일치"
        else:
            result["발행주식수검증결과"] = "주의"
    elif source_shares > 0:
        validation_shares = source_shares
        result["발행주식수검증결과"] = "시장 출처 주식 수 사용"
    elif financial_shares > 0:
        validation_shares = financial_shares
        result["발행주식수검증결과"] = "재무 주식 수 사용"
    else:
        result["발행주식수검증결과"] = "검증 불가"

    computed_cap = price * validation_shares if price > 0 and validation_shares > 0 else 0.0
    result["발행주식수"] = validation_shares
    result["가격곱하기발행주식수"] = computed_cap
    result["시가총액"] = market_cap

    if computed_cap > 0 and market_cap > 0:
        cap_gap = abs(market_cap / computed_cap - 1.0)
        result["시가총액차이율"] = cap_gap
        if cap_gap >= CAP_HARD_REJECT_RATIO:
            reasons.append(f"시가총액 배수 불일치({cap_gap:.1%})")
            result["시가총액일관성결과"] = "실패"
            corporate_action = True
        elif cap_gap >= CAP_TOLERANCE_RATIO:
            warnings.append(f"시가총액 차이 큼({cap_gap:.1%})")
            result["시가총액일관성결과"] = "주의"
            corporate_action = True
        else:
            result["시가총액일관성결과"] = "통과"
    elif computed_cap > 0:
        result["시가총액일관성결과"] = "수집 시가총액 없음 · 계산값만 기록"
    else:
        result["시가총액일관성결과"] = "검증 불가"

    technical_price, technical_date, technical_volume = _extract_latest_technical(technical_bundle or {})
    if technical_price > 0 and technical_date:
        result["기술분석교차가격"] = technical_price
        result["기술분석교차일"] = technical_date.isoformat()
        if parse_date(result.get("가격기준일")) == technical_date:
            gap = abs(price / technical_price - 1.0) if technical_price else 0.0
            result["기술분석가격차이율"] = gap
            if gap >= PRICE_MULTIPLE_SUSPECT_RATIO:
                reasons.append(f"동일 거래일 비조정 종가와 배수 불일치({gap:.1%})")
                corporate_action = True
        elif technical_date > (parse_date(result.get("가격기준일")) or date.min):
            reasons.append("기술분석에 더 최신 거래일 존재")
        if technical_volume > 0 and safe_int(result.get("거래량")) <= 0:
            reasons.append("현재가 후보 거래량 없음")

    result["기업행위의심여부"] = corporate_action
    result["경고사유"] = list(dict.fromkeys(warnings))
    result["거부사유"] = list(dict.fromkeys(reasons))
    result["최종채택"] = not reasons
    result["검증상태"] = "통과" if not reasons else "거부"
    return result


def choose_candidate(
    candidates: Iterable[Dict[str, Any]],
    *,
    stock_code: str,
    expected_market: str,
    share_count: int = 0,
    technical_bundle: Optional[Dict[str, Any]] = None,
    at: Optional[datetime] = None,
) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    checked = [
        validate_candidate(
            c,
            stock_code=stock_code,
            expected_market=expected_market,
            share_count=share_count,
            technical_bundle=technical_bundle,
            at=at,
        )
        for c in candidates
        if isinstance(c, dict) and c
    ]
    accepted = [item for item in checked if item.get("최종채택")]
    if not accepted:
        return None, checked

    source_rank = {
        "한국투자증권 KIS": 0,
        "Yahoo Finance Chart API": 1,
        "GoogleFinance": 2,
    }

    def rank(item: Dict[str, Any]):
        price_dt = parse_datetime(
            f"{item.get('가격기준일', '')} {item.get('가격기준시각', '')}"
        ) or datetime.min.replace(tzinfo=KST)
        base_source = str(item.get("가격출처", "")).split(" (")[0]
        return (price_dt, -source_rank.get(base_source, 9))

    accepted.sort(key=rank, reverse=True)
    return accepted[0], checked


def price_log(diagnostic: Dict[str, Any]) -> None:
    fields = [
        ("PRICE SOURCE", diagnostic.get("가격출처", "")),
        ("PRICE VALUE", diagnostic.get("가격", 0)),
        ("PRICE DATE", diagnostic.get("가격기준일", "")),
        ("PRICE TIME", diagnostic.get("가격기준시각", "")),
        ("PRICE COLLECTED AT", diagnostic.get("수집시각", "")),
        ("PRICE REALTIME OR CLOSE OR NXT", diagnostic.get("가격종류", "")),
        ("PRICE ADJUSTED", str(bool(diagnostic.get("조정주가여부"))).lower()),
        ("PRICE CACHE HIT OR MISS", "HIT" if diagnostic.get("캐시사용여부") else "MISS"),
        ("PRICE CACHE DATE", diagnostic.get("캐시생성시각", "")),
        ("PRICE CACHE VERSION", diagnostic.get("캐시버전", PRICE_SCHEMA_VERSION)),
        ("PRICE FRESHNESS", diagnostic.get("가격신선도", "")),
        ("PRICE MARKET", diagnostic.get("거래시장", "")),
        ("MARKET STATUS", diagnostic.get("시장상태", "")),
        ("MARKET CAP VALUE", diagnostic.get("시가총액", 0)),
        ("MARKET CAP VALIDATION", diagnostic.get("시가총액일관성결과", "")),
        ("SHARE COUNT VALUE", diagnostic.get("발행주식수", 0)),
        ("SHARE COUNT VALIDATION", diagnostic.get("발행주식수검증결과", "")),
        ("CORPORATE ACTION SUSPECTED", str(bool(diagnostic.get("기업행위의심여부"))).lower()),
        ("FINAL PRICE ACCEPTED OR REJECTED", "ACCEPTED" if diagnostic.get("최종채택") else "REJECTED"),
        ("PRICE REJECTION REASON", " / ".join(diagnostic.get("거부사유", []) or [])),
    ]
    for label, value in fields:
        print(f"{label}: {value}")


def apply_price_to_market(
    market: Dict[str, Any],
    selected: Optional[Dict[str, Any]],
    checked: List[Dict[str, Any]],
) -> Dict[str, Any]:
    target = dict(market or {})
    diagnostic = selected or _diagnostic_defaults(str(target.get("종목코드", "")))
    if selected is None:
        rejected = []
        for item in checked:
            rejected.extend(safe_list(item.get("거부사유")))
        diagnostic["거부사유"] = list(dict.fromkeys(str(item) for item in rejected if item)) or ["검증 가능한 최신 가격 없음"]
        diagnostic["검증상태"] = "거부"
        diagnostic["최종채택"] = False
        target["현재가"] = 0.0
        target["전일대비"] = 0.0
        target["등락률"] = 0.0
        target["현재가수집상태"] = "현재가 확인 불가"
        target["현재가응답메시지"] = " / ".join(diagnostic["거부사유"])
        target["데이터출처"] = "현재가 검증 실패"
    else:
        price = safe_float(selected.get("가격"))
        previous = safe_float(selected.get("전일종가"))
        target["현재가"] = price
        target["전일대비"] = price - previous if previous > 0 else safe_float(target.get("전일대비"))
        target["등락률"] = ((price / previous - 1.0) * 100.0) if previous > 0 else safe_float(target.get("등락률"))
        target["거래량"] = safe_int(selected.get("거래량"))
        target["시가"] = safe_float(selected.get("시가"))
        target["고가"] = safe_float(selected.get("고가"))
        target["저가"] = safe_float(selected.get("저가"))
        if safe_float(selected.get("시가총액")) > 0:
            target["시가총액"] = safe_float(selected.get("시가총액"))
        target["현재가수집상태"] = "정상"
        target["현재가응답메시지"] = "최신 비조정 실제 가격 검증 통과"
        target["데이터출처"] = str(selected.get("가격출처", ""))
        target["Yahoo심볼"] = str(selected.get("심볼", ""))
        target["Yahoo거래소"] = str(selected.get("거래소", ""))
        target["거래시장"] = str(selected.get("거래시장", "KRX"))
        target["가격종류"] = str(selected.get("가격종류", ""))
        target["가격기준일"] = str(selected.get("가격기준일", ""))
        target["가격기준시각"] = str(selected.get("가격기준시각", ""))
        target["가격수집시각"] = str(selected.get("수집시각", ""))
    target["가격진단"] = diagnostic
    target["가격후보진단"] = checked
    price_log(diagnostic)
    return target


def suppress_unverified_price_judgment(
    valuation: Dict[str, Any],
    market: Dict[str, Any],
) -> Dict[str, Any]:
    """Suppress only price-derived conclusions when current price is unverified.

    Financial valuation values and formulas remain untouched.  This prevents a
    missing current price (stored as zero for backward compatibility) from
    being presented as a zero-gap/"적정" market judgment or contributing a
    price valuation signal downstream.
    """
    result = dict(valuation or {})
    if str(safe_dict(market).get("현재가수집상태", "")) == "정상":
        return result
    result["현재가"] = 0.0
    result["현재가대비"] = 0.0
    result["판단"] = "현재가 확인 불가"
    result["가격기반판정가능"] = False
    result["가격기반판정사유"] = str(
        safe_dict(market).get("현재가응답메시지") or "검증된 최신 현재가 없음"
    )
    return result
