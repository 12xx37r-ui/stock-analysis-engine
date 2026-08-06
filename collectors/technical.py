"""
종목 5년 차트·멀티타임프레임 기술분석 수집기 V1.0

목표
- GitHub Python 엔진에서 Yahoo 5년 일봉을 직접 수집한다.
- 일봉을 주봉·월봉으로 집계한다.
- GAS가 별도 Yahoo 수집에 실패해도 일봉·주봉·월봉 카드가 대기 상태에 머물지 않도록
  엔진 JSON에 완성된 기술분석 요약을 넣는다.
- Yahoo 실패 시 KIS 일봉을 보조자료로 사용한다.
"""

from collections import OrderedDict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from collectors.global_market import parse_chart_result, request_chart


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, "", "-", "--"):
            return default
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def moving_average(values: List[float], period: int) -> float:
    if period <= 0 or len(values) < period:
        return 0.0
    return sum(values[-period:]) / period


def rate_of_change(values: List[float], period: int) -> Optional[float]:
    if period <= 0 or len(values) <= period:
        return None
    previous = values[-period - 1]
    current = values[-1]
    if previous <= 0:
        return None
    return current / previous - 1.0


def calculate_rsi(values: List[float], period: int = 14) -> Optional[float]:
    if period <= 0 or len(values) <= period:
        return None

    gains: List[float] = []
    losses: List[float] = []
    recent = values[-(period + 1):]

    for previous, current in zip(recent, recent[1:]):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    average_gain = sum(gains) / period
    average_loss = sum(losses) / period

    if average_loss == 0:
        return 100.0

    relative_strength = average_gain / average_loss
    return 100.0 - 100.0 / (1.0 + relative_strength)


def normalize_yahoo_rows(rows: Any) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        return []

    normalized: List[Dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        timestamp = int(safe_float(row.get("timestamp"), 0))
        close = safe_float(row.get("종가"))

        if timestamp <= 0 or close <= 0:
            continue

        normalized.append(
            {
                "timestamp": timestamp,
                "시각UTC": safe_text(row.get("시각UTC")),
                "시가": safe_float(row.get("시가"), close),
                "고가": safe_float(row.get("고가"), close),
                "저가": safe_float(row.get("저가"), close),
                "종가": close,
                "거래량": safe_float(row.get("거래량")),
            }
        )

    normalized.sort(key=lambda item: item["timestamp"])
    return normalized


def normalize_kis_rows(rows: Any) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        return []

    normalized: List[Dict[str, Any]] = []

    for row in rows:
        if not isinstance(row, dict):
            continue

        date_text = safe_text(row.get("날짜"))
        close = safe_float(row.get("종가"))

        if len(date_text) != 8 or close <= 0:
            continue

        try:
            timestamp = int(datetime.strptime(date_text, "%Y%m%d").timestamp())
        except ValueError:
            continue

        normalized.append(
            {
                "timestamp": timestamp,
                "시각UTC": datetime.utcfromtimestamp(timestamp).isoformat() + "Z",
                "시가": safe_float(row.get("시가"), close),
                "고가": safe_float(row.get("고가"), close),
                "저가": safe_float(row.get("저가"), close),
                "종가": close,
                "거래량": safe_float(row.get("거래량")),
            }
        )

    normalized.sort(key=lambda item: item["timestamp"])
    return normalized


def aggregate_rows(rows: List[Dict[str, Any]], mode: str) -> List[Dict[str, Any]]:
    grouped: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()

    for row in rows:
        timestamp = int(safe_float(row.get("timestamp"), 0))
        if timestamp <= 0:
            continue

        date_value = datetime.utcfromtimestamp(timestamp)

        if mode == "weekly":
            iso_year, iso_week, _ = date_value.isocalendar()
            key = f"{iso_year:04d}-W{iso_week:02d}"
        elif mode == "monthly":
            key = f"{date_value.year:04d}-{date_value.month:02d}"
        else:
            raise ValueError("mode must be weekly or monthly")

        if key not in grouped:
            grouped[key] = {
                "기간": key,
                "timestamp": timestamp,
                "시가": safe_float(row.get("시가"), safe_float(row.get("종가"))),
                "고가": safe_float(row.get("고가"), safe_float(row.get("종가"))),
                "저가": safe_float(row.get("저가"), safe_float(row.get("종가"))),
                "종가": safe_float(row.get("종가")),
                "거래량": safe_float(row.get("거래량")),
            }
            continue

        item = grouped[key]
        item["timestamp"] = timestamp
        item["고가"] = max(item["고가"], safe_float(row.get("고가"), item["고가"]))
        low = safe_float(row.get("저가"), item["저가"])
        item["저가"] = min(item["저가"], low) if low > 0 else item["저가"]
        item["종가"] = safe_float(row.get("종가"), item["종가"])
        item["거래량"] += safe_float(row.get("거래량"))

    return list(grouped.values())


def trend_label(score: float) -> str:
    if score >= 60:
        return "강한 상승"
    if score >= 20:
        return "상승 우위"
    if score <= -60:
        return "강한 하락"
    if score <= -20:
        return "하락 우위"
    return "중립"


def timeframe_summary(
    rows: List[Dict[str, Any]],
    fast_period: int,
    medium_period: int,
    long_period: int,
    momentum_fast_period: int,
    momentum_medium_period: int,
    minimum_observations: int,
) -> Dict[str, Any]:
    closes = [safe_float(row.get("종가")) for row in rows if safe_float(row.get("종가")) > 0]
    volumes = [safe_float(row.get("거래량")) for row in rows if safe_float(row.get("종가")) > 0]
    observations = len(closes)

    if observations < max(5, minimum_observations):
        return {
            "available": False,
            "score": 0.0,
            "trend": "자료 부족",
            "rsi14": None,
            "maFast": None,
            "maMedium": None,
            "maLong": None,
            "momentumFast": None,
            "momentumMedium": None,
            "observations": observations,
            "confidence": round(clamp(observations / max(minimum_observations, 1) * 70.0, 0.0, 70.0), 1),
        }

    latest = closes[-1]
    ma_fast = moving_average(closes, fast_period)
    ma_medium = moving_average(closes, medium_period)
    ma_long = moving_average(closes, long_period)
    momentum_fast = rate_of_change(closes, momentum_fast_period)
    momentum_medium = rate_of_change(closes, momentum_medium_period)
    rsi_period = min(14, max(5, observations // 4))
    rsi = calculate_rsi(closes, rsi_period)

    score = 0.0

    if ma_fast > 0:
        score += 12.0 if latest >= ma_fast else -12.0
    if ma_medium > 0:
        score += 18.0 if latest >= ma_medium else -18.0
    if ma_long > 0:
        score += 18.0 if latest >= ma_long else -18.0

    if ma_fast > 0 and ma_medium > 0:
        score += 10.0 if ma_fast >= ma_medium else -10.0
    if ma_medium > 0 and ma_long > 0:
        score += 10.0 if ma_medium >= ma_long else -10.0

    if momentum_fast is not None:
        score += clamp(momentum_fast * 120.0, -16.0, 16.0)
    if momentum_medium is not None:
        score += clamp(momentum_medium * 90.0, -18.0, 18.0)

    if rsi is not None:
        if 52 <= rsi <= 72:
            score += 8.0
        elif rsi >= 80:
            score -= 7.0
        elif 28 <= rsi <= 48:
            score -= 6.0
        elif rsi < 22:
            score += 3.0

    if len(volumes) >= 20:
        volume_fast = moving_average(volumes, min(5, len(volumes)))
        volume_medium = moving_average(volumes, min(20, len(volumes)))
        if volume_medium > 0 and momentum_fast is not None:
            volume_ratio = volume_fast / volume_medium
            if momentum_fast > 0 and volume_ratio >= 1.15:
                score += 5.0
            elif momentum_fast < 0 and volume_ratio >= 1.15:
                score -= 5.0

    score = round(clamp(score, -100.0, 100.0), 2)
    coverage = clamp(observations / max(long_period * 2.0, minimum_observations), 0.0, 1.0)
    confidence = round(55.0 + coverage * 40.0, 1)

    return {
        "available": True,
        "score": score,
        "trend": trend_label(score),
        "rsi14": round(rsi, 2) if rsi is not None else None,
        "maFast": round(ma_fast, 2) if ma_fast > 0 else None,
        "maMedium": round(ma_medium, 2) if ma_medium > 0 else None,
        "maLong": round(ma_long, 2) if ma_long > 0 else None,
        "momentumFast": round(momentum_fast, 6) if momentum_fast is not None else None,
        "momentumMedium": round(momentum_medium, 6) if momentum_medium is not None else None,
        "observations": observations,
        "confidence": confidence,
        "latestClose": round(latest, 2),
    }


def yahoo_symbol_candidates(stock_code: str, market_code: str = "") -> List[str]:
    stock_code = safe_text(stock_code)
    market_code = safe_text(market_code).upper()

    if market_code in {"Q", "KQ", "KOSDAQ", "KOSDAQ GLOBAL"}:
        return [f"{stock_code}.KQ", f"{stock_code}.KS"]

    if market_code in {"Y", "KS", "KOSPI", "KSE"}:
        return [f"{stock_code}.KS", f"{stock_code}.KQ"]

    return [f"{stock_code}.KS", f"{stock_code}.KQ"]


def latest_rows_are_fresh(
    rows: List[Dict[str, Any]],
    maximum_age_days: int = 10,
) -> bool:
    if not rows:
        return False

    latest_timestamp = int(
        safe_float(
            rows[-1].get("timestamp"),
            0,
        )
    )

    if latest_timestamp <= 0:
        return False

    observed = datetime.fromtimestamp(
        latest_timestamp,
        tz=timezone.utc,
    )
    now = datetime.now(timezone.utc)

    if observed > now + timedelta(days=1):
        return False

    return now - observed <= timedelta(
        days=max(1, maximum_age_days)
    )


def get_stock_technical_bundle(
    stock_code: str,
    market_code: str = "K",
    history_bundle: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    errors: List[str] = []
    selected_symbol = ""
    rows: List[Dict[str, Any]] = []
    source = ""

    for symbol in yahoo_symbol_candidates(stock_code, market_code):
        chart = parse_chart_result(
            "종목 5년 차트",
            symbol,
            "equity",
            "KRW",
            request_chart(symbol, range_value="5y", interval="1d"),
        )

        if chart.get("수집상태") == "정상":
            candidate_rows = normalize_yahoo_rows(chart.get("일별데이터"))
            if (
                len(candidate_rows) >= 240
                and latest_rows_are_fresh(candidate_rows)
            ):
                selected_symbol = symbol
                rows = candidate_rows
                source = "Yahoo Finance Chart API 5년 일봉"
                break

            if len(candidate_rows) >= 240:
                errors.append(
                    f"{symbol}: 최신 거래일이 오래되어 기술자료에서 제외"
                )
                continue

        errors.append(f"{symbol}: {safe_text(chart.get('응답메시지'), '자료 부족')}")

    if not rows:
        history_bundle = history_bundle if isinstance(history_bundle, dict) else {}
        price_history = history_bundle.get("가격추세", {})
        if isinstance(price_history, dict):
            rows = normalize_kis_rows(price_history.get("일봉"))

        if rows:
            selected_symbol = stock_code
            source = "KIS 일봉 보조자료"
        else:
            return {
                "수집상태": "실패",
                "심볼": "",
                "데이터출처": "",
                "응답메시지": "; ".join(errors) or "Yahoo·KIS 차트자료 없음",
                "일봉": {"available": False, "score": 0.0, "trend": "자료 부족", "observations": 0, "confidence": 0},
                "주봉": {"available": False, "score": 0.0, "trend": "자료 부족", "observations": 0, "confidence": 0},
                "월봉": {"available": False, "score": 0.0, "trend": "자료 부족", "observations": 0, "confidence": 0},
                "수집오류": errors,
            }

    weekly_rows = aggregate_rows(rows, "weekly")
    monthly_rows = aggregate_rows(rows, "monthly")

    daily = timeframe_summary(
        rows,
        fast_period=5,
        medium_period=20,
        long_period=60,
        momentum_fast_period=5,
        momentum_medium_period=20,
        minimum_observations=60,
    )
    weekly = timeframe_summary(
        weekly_rows,
        fast_period=4,
        medium_period=13,
        long_period=26,
        momentum_fast_period=4,
        momentum_medium_period=13,
        minimum_observations=26,
    )
    monthly = timeframe_summary(
        monthly_rows,
        fast_period=3,
        medium_period=12,
        long_period=24,
        momentum_fast_period=3,
        momentum_medium_period=12,
        minimum_observations=24,
    )

    available_count = sum(bool(item.get("available")) for item in (daily, weekly, monthly))
    overall = "정상" if available_count == 3 else "부분성공" if available_count > 0 else "실패"

    return {
        "수집상태": overall,
        "심볼": selected_symbol,
        "데이터출처": source,
        "응답메시지": "" if overall == "정상" else "일부 시간축 자료 부족",
        "일봉": daily,
        "주봉": weekly,
        "월봉": monthly,
        "일봉데이터개수": len(rows),
        "주봉데이터개수": len(weekly_rows),
        "월봉데이터개수": len(monthly_rows),
        "최초일": rows[0].get("시각UTC", "") if rows else "",
        "최종일": rows[-1].get("시각UTC", "") if rows else "",
        "최근일봉": rows[-120:],
        "수집오류": errors,
    }
