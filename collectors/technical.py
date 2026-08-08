"""
종목 차트·멀티타임프레임 기술분석·RSI 다이버전스 수집기 V2.0

목표
- GitHub Python 엔진에서 Yahoo 5년 일봉을 직접 수집한다.
- 일봉을 주봉·월봉으로 집계하고 Yahoo 1시간봉을 장중 4시간봉으로 집계한다.
- 4시간봉·일봉·주봉·월봉에서 RSI 일반/히든 상승·하락 다이버전스를 독립 탐지한다.
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




DIVERGENCE_CONFIG: Dict[str, Dict[str, Any]] = {
    "4시간봉": {
        "search_bars": 180,
        "validity_bars": 30,
        "minimum_observations": 80,
        "pivot_left": 2,
        "pivot_right": 2,
        "min_pivot_gap": 5,
        "max_pivot_gap": 50,
        "min_price_change_pct": 0.40,
        "min_rsi_delta": 2.0,
        "relative_volume_threshold": 1.50,
        "invalidation_buffer_pct": 0.50,
    },
    "일봉": {
        "search_bars": 150,
        "validity_bars": 20,
        "minimum_observations": 80,
        "pivot_left": 2,
        "pivot_right": 2,
        "min_pivot_gap": 5,
        "max_pivot_gap": 60,
        "min_price_change_pct": 0.60,
        "min_rsi_delta": 2.5,
        "relative_volume_threshold": 1.50,
        "invalidation_buffer_pct": 0.60,
    },
    "주봉": {
        "search_bars": 120,
        "validity_bars": 12,
        "minimum_observations": 52,
        "pivot_left": 2,
        "pivot_right": 2,
        "min_pivot_gap": 3,
        "max_pivot_gap": 40,
        "min_price_change_pct": 1.00,
        "min_rsi_delta": 3.0,
        "relative_volume_threshold": 1.50,
        "invalidation_buffer_pct": 0.80,
    },
    "월봉": {
        "search_bars": 72,
        "validity_bars": 6,
        "minimum_observations": 36,
        "pivot_left": 2,
        "pivot_right": 2,
        "min_pivot_gap": 2,
        "max_pivot_gap": 24,
        "min_price_change_pct": 1.50,
        "min_rsi_delta": 3.0,
        "relative_volume_threshold": 1.50,
        "invalidation_buffer_pct": 1.00,
    },
}

DIVERGENCE_TYPE_META: Dict[str, Dict[str, str]] = {
    "REGULAR_BULLISH": {
        "name": "일반 상승",
        "direction": "상승",
        "nature": "반전",
        "price_structure": "Lower Low",
        "rsi_structure": "Higher Low",
        "meaning": "가격은 더 낮은 저점을 만들었지만 RSI 저점은 높아져 하락 모멘텀이 약해지는 상승 반전 후보 신호입니다.",
    },
    "REGULAR_BEARISH": {
        "name": "일반 하락",
        "direction": "하락",
        "nature": "반전",
        "price_structure": "Higher High",
        "rsi_structure": "Lower High",
        "meaning": "가격은 더 높은 고점을 만들었지만 RSI 고점은 낮아져 상승 모멘텀이 약해지는 하락 반전 후보 신호입니다.",
    },
    "HIDDEN_BULLISH": {
        "name": "히든 상승",
        "direction": "상승",
        "nature": "추세 지속",
        "price_structure": "Higher Low",
        "rsi_structure": "Lower Low",
        "meaning": "가격의 높은 저점 구조는 유지되지만 RSI는 더 낮은 저점을 만들어 기존 상승추세가 이어질 가능성을 보는 추세 지속 후보 신호입니다.",
    },
    "HIDDEN_BEARISH": {
        "name": "히든 하락",
        "direction": "하락",
        "nature": "추세 지속",
        "price_structure": "Lower High",
        "rsi_structure": "Higher High",
        "meaning": "가격의 낮은 고점 구조는 유지되지만 RSI는 더 높은 고점을 만들어 기존 하락추세가 이어질 가능성을 보는 추세 지속 후보 신호입니다.",
    },
}

KST = timezone(timedelta(hours=9))


def calculate_rsi_series(values: List[float], period: int = 14) -> List[Optional[float]]:
    """Wilder RSI series. Only past/current closes are used at each index."""
    result: List[Optional[float]] = [None] * len(values)
    if period <= 0 or len(values) <= period:
        return result

    gains: List[float] = []
    losses: List[float] = []
    for previous, current in zip(values[:period], values[1:period + 1]):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))

    average_gain = sum(gains) / period
    average_loss = sum(losses) / period

    def rsi_value(gain: float, loss: float) -> float:
        if loss <= 0:
            return 100.0 if gain > 0 else 50.0
        if gain <= 0:
            return 0.0
        rs = gain / loss
        return 100.0 - 100.0 / (1.0 + rs)

    result[period] = rsi_value(average_gain, average_loss)

    for index in range(period + 1, len(values)):
        change = values[index] - values[index - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        average_gain = (average_gain * (period - 1) + gain) / period
        average_loss = (average_loss * (period - 1) + loss) / period
        result[index] = rsi_value(average_gain, average_loss)

    return result


def aggregate_four_hour_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Aggregate Yahoo 1h Korean-session rows into 09:00-13:00 and 13:00-close KST candles."""
    grouped: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()

    for row in rows:
        timestamp = int(safe_float(row.get("timestamp"), 0))
        close = safe_float(row.get("종가"))
        if timestamp <= 0 or close <= 0:
            continue

        local_dt = datetime.fromtimestamp(timestamp, tz=timezone.utc).astimezone(KST)
        minute_of_day = local_dt.hour * 60 + local_dt.minute
        market_open = 9 * 60
        market_close = 15 * 60 + 30
        if minute_of_day < market_open or minute_of_day > market_close:
            continue

        session_minutes = minute_of_day - market_open
        bucket = 0 if session_minutes < 240 else 1
        bucket_start_minutes = market_open + bucket * 240
        bucket_end_minutes = min(bucket_start_minutes + 240, market_close)
        end_hour, end_minute = divmod(bucket_end_minutes, 60)
        end_local = local_dt.replace(
            hour=end_hour,
            minute=end_minute,
            second=0,
            microsecond=0,
        )
        end_timestamp = int(end_local.astimezone(timezone.utc).timestamp())
        key = f"{local_dt.date().isoformat()}-{bucket}"

        if key not in grouped:
            grouped[key] = {
                "기간": key,
                "timestamp": timestamp,
                "시각UTC": safe_text(row.get("시각UTC")),
                "시가": safe_float(row.get("시가"), close),
                "고가": safe_float(row.get("고가"), close),
                "저가": safe_float(row.get("저가"), close),
                "종가": close,
                "거래량": safe_float(row.get("거래량")),
                "_bucketEndTimestamp": end_timestamp,
            }
            continue

        item = grouped[key]
        item["timestamp"] = timestamp
        item["시각UTC"] = safe_text(row.get("시각UTC"), item.get("시각UTC", ""))
        item["고가"] = max(item["고가"], safe_float(row.get("고가"), item["고가"]))
        low = safe_float(row.get("저가"), item["저가"])
        item["저가"] = min(item["저가"], low) if low > 0 else item["저가"]
        item["종가"] = close
        item["거래량"] += safe_float(row.get("거래량"))

    return list(grouped.values())


def confirmed_rows(rows: List[Dict[str, Any]], timeframe: str) -> List[Dict[str, Any]]:
    """Remove the currently forming candle when it can be identified conservatively."""
    if not rows:
        return []

    confirmed = list(rows)
    now_utc = datetime.now(timezone.utc)
    now_kst = now_utc.astimezone(KST)
    latest = confirmed[-1]
    latest_ts = int(safe_float(latest.get("timestamp"), 0))
    if latest_ts <= 0:
        return confirmed
    latest_kst = datetime.fromtimestamp(latest_ts, tz=timezone.utc).astimezone(KST)

    if timeframe == "4시간봉":
        bucket_end = int(safe_float(latest.get("_bucketEndTimestamp"), 0))
        if bucket_end > 0 and now_utc.timestamp() < bucket_end:
            confirmed.pop()
    elif timeframe == "일봉":
        if latest_kst.date() == now_kst.date():
            close_minutes = 15 * 60 + 30
            now_minutes = now_kst.hour * 60 + now_kst.minute
            if now_minutes < close_minutes:
                confirmed.pop()
    elif timeframe == "주봉":
        latest_iso = latest_kst.isocalendar()[:2]
        now_iso = now_kst.isocalendar()[:2]
        if latest_iso == now_iso:
            week_finished = now_kst.weekday() >= 5 or (
                now_kst.weekday() == 4 and
                (now_kst.hour * 60 + now_kst.minute) >= (15 * 60 + 30)
            )
            if not week_finished:
                confirmed.pop()
    elif timeframe == "월봉":
        if (latest_kst.year, latest_kst.month) == (now_kst.year, now_kst.month):
            confirmed.pop()

    return confirmed


def _pivot_points(
    rows: List[Dict[str, Any]],
    rsi_values: List[Optional[float]],
    mode: str,
    left: int,
    right: int,
) -> List[Dict[str, Any]]:
    key = "저가" if mode == "low" else "고가"
    pivots: List[Dict[str, Any]] = []

    for index in range(left, len(rows) - right):
        rsi = rsi_values[index]
        if rsi is None:
            continue
        value = safe_float(rows[index].get(key))
        if value <= 0:
            continue
        window = [safe_float(rows[i].get(key)) for i in range(index - left, index + right + 1)]
        if any(item <= 0 for item in window):
            continue
        neighbors = window[:left] + window[left + 1:]
        if mode == "low":
            is_pivot = value <= min(neighbors) and value < max(neighbors)
        else:
            is_pivot = value >= max(neighbors) and value > min(neighbors)
        if not is_pivot:
            continue
        pivots.append({
            "index": index,
            "price": value,
            "rsi": float(rsi),
            "timestamp": int(safe_float(rows[index].get("timestamp"), 0)),
            "time": safe_text(rows[index].get("시각UTC")),
        })

    return pivots


def _pivot_prominence(rows: List[Dict[str, Any]], pivot_index: int, mode: str, radius: int = 3) -> float:
    start = max(0, pivot_index - radius)
    end = min(len(rows), pivot_index + radius + 1)
    if end - start < 3:
        return 0.0
    if mode == "low":
        pivot = safe_float(rows[pivot_index].get("저가"))
        surrounding = [safe_float(rows[i].get("저가")) for i in range(start, end) if i != pivot_index]
        baseline = sum(surrounding) / len(surrounding) if surrounding else 0.0
        return max(0.0, (baseline / pivot - 1.0) * 100.0) if pivot > 0 else 0.0
    pivot = safe_float(rows[pivot_index].get("고가"))
    surrounding = [safe_float(rows[i].get("고가")) for i in range(start, end) if i != pivot_index]
    baseline = sum(surrounding) / len(surrounding) if surrounding else 0.0
    return max(0.0, (pivot / baseline - 1.0) * 100.0) if baseline > 0 else 0.0


def _relative_volume_confirmation(
    rows: List[Dict[str, Any]],
    start_index: int,
    threshold: float,
    average_bars: int = 20,
) -> Dict[str, Any]:
    valid_volume_count = sum(1 for row in rows if safe_float(row.get("거래량")) > 0)
    if valid_volume_count < min(average_bars + 1, len(rows)):
        return {
            "available": False,
            "confirmed": False,
            "ratio": None,
            "index": None,
            "status": "거래량 데이터 없음",
        }

    best_ratio: Optional[float] = None
    best_index: Optional[int] = None
    start = max(start_index, average_bars)
    for index in range(start, len(rows)):
        volume = safe_float(rows[index].get("거래량"))
        previous = [safe_float(rows[i].get("거래량")) for i in range(index - average_bars, index)]
        previous = [value for value in previous if value > 0]
        if volume <= 0 or len(previous) < max(5, average_bars // 2):
            continue
        average = sum(previous) / len(previous)
        if average <= 0:
            continue
        ratio = volume / average
        if best_ratio is None or ratio > best_ratio:
            best_ratio = ratio
            best_index = index

    if best_ratio is None:
        return {
            "available": False,
            "confirmed": False,
            "ratio": None,
            "index": None,
            "status": "거래량 데이터 없음",
        }

    confirmed = best_ratio >= threshold
    return {
        "available": True,
        "confirmed": confirmed,
        "ratio": round(best_ratio, 2),
        "index": best_index,
        "status": (
            f"거래량 증가 확인 · {best_ratio:.2f}배"
            if confirmed
            else f"거래량 증가 미확인 · {best_ratio:.2f}배"
        ),
    }


def _structure_reference(
    rows: List[Dict[str, Any]],
    first_index: int,
    second_index: int,
    direction: str,
) -> float:
    subset = rows[first_index:second_index + 1]
    if not subset:
        return 0.0
    if direction == "상승":
        return max(safe_float(row.get("고가")) for row in subset)
    lows = [safe_float(row.get("저가")) for row in subset if safe_float(row.get("저가")) > 0]
    return min(lows) if lows else 0.0


def _structure_confirmation(
    rows: List[Dict[str, Any]],
    start_index: int,
    level: float,
    direction: str,
) -> Dict[str, Any]:
    if level <= 0:
        return {"confirmed": False, "index": None, "extent_pct": 0.0, "status": "가격구조 기준 없음"}

    confirmed_index: Optional[int] = None
    best_extent = 0.0
    for index in range(max(0, start_index), len(rows)):
        close = safe_float(rows[index].get("종가"))
        if close <= 0:
            continue
        if direction == "상승":
            extent = (close / level - 1.0) * 100.0
            if extent > 0 and confirmed_index is None:
                confirmed_index = index
            best_extent = max(best_extent, extent)
        else:
            extent = (level / close - 1.0) * 100.0 if close > 0 else 0.0
            if close < level and confirmed_index is None:
                confirmed_index = index
            best_extent = max(best_extent, extent)

    confirmed = confirmed_index is not None
    price_text = f"{level:,.0f}원"
    if direction == "상승":
        status = (
            f"직전 스윙 고점 {price_text} 종가 돌파"
            if confirmed
            else f"직전 스윙 고점 {price_text} 미돌파"
        )
    else:
        status = (
            f"직전 스윙 저점 {price_text} 종가 이탈"
            if confirmed
            else f"직전 스윙 저점 {price_text} 유지"
        )

    return {
        "confirmed": confirmed,
        "index": confirmed_index,
        "extent_pct": round(max(0.0, best_extent), 2),
        "status": status,
    }


def _trend_consistency(closes: List[float], second_index: int, signal_type: str) -> bool:
    lookback = min(12, max(4, second_index))
    if second_index - lookback < 0:
        return False
    previous = closes[second_index - lookback]
    current = closes[second_index]
    if previous <= 0:
        return False
    rising = current >= previous
    if signal_type in {"REGULAR_BEARISH", "HIDDEN_BULLISH"}:
        return rising
    return not rising


def _freshness_label(age: int, validity: int) -> str:
    ratio = age / max(validity, 1)
    if ratio <= 0.20:
        return "매우 높음"
    if ratio <= 0.45:
        return "높음"
    if ratio <= 0.70:
        return "보통"
    return "낮음"


def _confidence_grade(score: float) -> str:
    if score < 40:
        return "낮음"
    if score < 60:
        return "보통"
    if score < 80:
        return "높음"
    return "매우 높음"


def _strength_grade(score: float) -> str:
    if score < 20:
        return "매우 약함"
    if score < 40:
        return "약함"
    if score < 60:
        return "보통"
    if score < 80:
        return "강함"
    return "매우 강함"


def _elapsed_text(timeframe: str, age: int) -> str:
    if timeframe == "4시간봉":
        return f"약 {age * 4}시간 전"
    if timeframe == "일봉":
        return f"약 {age}거래일 전"
    if timeframe == "주봉":
        return f"약 {age}주 전"
    return f"약 {age}개월 전"


def _no_signal(direction: str, reason: str) -> Dict[str, Any]:
    return {
        "탐지": False,
        "detected": False,
        "상태": "미탐지",
        "방향": direction,
        "사유": reason,
    }


def _build_divergence_signal(
    timeframe: str,
    rows: List[Dict[str, Any]],
    closes: List[float],
    first: Dict[str, Any],
    second: Dict[str, Any],
    signal_type: str,
    pivot_mode: str,
    config: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    meta = DIVERGENCE_TYPE_META[signal_type]
    right = int(config["pivot_right"])
    confirmation_index = second["index"] + right
    if confirmation_index >= len(rows):
        return None

    age = len(rows) - 1 - confirmation_index
    validity = int(config["validity_bars"])
    if age > validity:
        return None

    direction = meta["direction"]
    invalidation_buffer = float(config["invalidation_buffer_pct"]) / 100.0
    invalidated = False
    invalidated_index: Optional[int] = None
    pivot2_price = float(second["price"])
    for index in range(confirmation_index, len(rows)):
        close = safe_float(rows[index].get("종가"))
        if close <= 0:
            continue
        if direction == "상승" and close < pivot2_price * (1.0 - invalidation_buffer):
            invalidated = True
            invalidated_index = index
            break
        if direction == "하락" and close > pivot2_price * (1.0 + invalidation_buffer):
            invalidated = True
            invalidated_index = index
            break

    if invalidated:
        return None

    volume = _relative_volume_confirmation(
        rows,
        confirmation_index,
        float(config["relative_volume_threshold"]),
    )
    structure_level = _structure_reference(
        rows,
        first["index"],
        second["index"],
        direction,
    )
    structure = _structure_confirmation(
        rows,
        confirmation_index,
        structure_level,
        direction,
    )

    if volume["confirmed"] and structure["confirmed"]:
        stage = "강한 상승 확인" if direction == "상승" else "강한 하락 확인"
    elif volume["confirmed"] or structure["confirmed"]:
        stage = "확인 진행"
    else:
        stage = "초기 신호"

    price_change_pct = abs(float(second["price"]) / float(first["price"]) - 1.0) * 100.0
    rsi_change = abs(float(second["rsi"]) - float(first["rsi"]))
    prominence = (
        _pivot_prominence(rows, first["index"], pivot_mode) +
        _pivot_prominence(rows, second["index"], pivot_mode)
    ) / 2.0
    gap = second["index"] - first["index"]
    min_gap = int(config["min_pivot_gap"])
    max_gap = int(config["max_pivot_gap"])
    ideal_gap = (min_gap + max_gap) / 2.0
    half_span = max((max_gap - min_gap) / 2.0, 1.0)
    distance_quality = max(0.0, 1.0 - abs(gap - ideal_gap) / half_span)
    trend_consistent = _trend_consistency(closes, second["index"], signal_type)
    freshness_score = max(0.0, 1.0 - age / max(validity, 1))

    divergence_quality = (
        15.0 +
        min(8.0, price_change_pct * 1.4) +
        min(7.0, rsi_change * 0.75)
    )
    confidence = (
        divergence_quality +
        min(10.0, prominence * 5.0) +
        distance_quality * 10.0 +
        freshness_score * 15.0 +
        (15.0 if volume["confirmed"] else (4.0 if volume["available"] else 0.0)) +
        (15.0 if structure["confirmed"] else 4.0) +
        (5.0 if trend_consistent else 1.0)
    )
    confidence = round(clamp(confidence, 0.0, 100.0))

    latest_close = closes[-1] if closes else 0.0
    if direction == "상승":
        followthrough_pct = max(0.0, (latest_close / pivot2_price - 1.0) * 100.0) if pivot2_price > 0 else 0.0
    else:
        followthrough_pct = max(0.0, (pivot2_price / latest_close - 1.0) * 100.0) if latest_close > 0 else 0.0
    rvol = float(volume["ratio"] or 0.0)
    strength_score = (
        min(20.0, price_change_pct * 2.0) +
        min(20.0, rsi_change * 1.5) +
        min(20.0, max(0.0, rvol - 0.8) * 18.0) +
        min(20.0, float(structure["extent_pct"]) * 5.0) +
        min(20.0, followthrough_pct * 3.0)
    )
    strength_score = round(clamp(strength_score, 0.0, 100.0))

    confirmation_row = rows[confirmation_index]
    confirmation_time = safe_text(confirmation_row.get("시각UTC"))
    if not confirmation_time:
        confirmation_time = datetime.fromtimestamp(
            int(safe_float(confirmation_row.get("timestamp"), 0)),
            tz=timezone.utc,
        ).isoformat()

    beginner = meta["meaning"]
    if volume["confirmed"] and structure["confirmed"]:
        beginner += " 거래량 증가와 가격구조 확인이 모두 더해져 단순 다이버전스보다 확인 단계가 높습니다."
    elif volume["confirmed"] or structure["confirmed"]:
        beginner += " 거래량 또는 가격구조 중 한 가지 확인이 더해졌지만 아직 두 조건이 모두 확인된 것은 아닙니다."
    else:
        beginner += " 아직 거래량 증가와 가격구조 확인이 부족하므로 선행 경고 성격의 초기 신호로 보는 편이 적절합니다."
    beginner += " 신뢰도 점수는 미래 상승·하락 확률이 아니라 현재 기술적 조건의 충족도와 신호 품질 점수입니다."

    summary = (
        f"{meta['name']} · {age}봉 전 · 신뢰도 {_confidence_grade(confidence)}"
    )

    return {
        "탐지": True,
        "detected": True,
        "상태": "탐지",
        "시간봉": timeframe,
        "신호타입": signal_type,
        "신호명": meta["name"],
        "방향": direction,
        "성격": meta["nature"],
        "가격피벗구조": meta["price_structure"],
        "RSI피벗구조": meta["rsi_structure"],
        "의미": meta["meaning"],
        "요약": summary,
        "발생봉전": age,
        "경과설명": _elapsed_text(timeframe, age),
        "신호확정시각UTC": confirmation_time,
        "피벗1시각UTC": first.get("time", ""),
        "피벗2시각UTC": second.get("time", ""),
        "피벗간격봉": gap,
        "피벗1가격": round(float(first["price"]), 2),
        "피벗2가격": round(float(second["price"]), 2),
        "피벗1RSI": round(float(first["rsi"]), 2),
        "피벗2RSI": round(float(second["rsi"]), 2),
        "가격변화폭퍼센트": round(price_change_pct, 2),
        "RSI변화폭": round(rsi_change, 2),
        "신선도": _freshness_label(age, validity),
        "거래량배수": volume["ratio"],
        "거래량확인": bool(volume["confirmed"]),
        "거래량상태": volume["status"],
        "가격구조기준": round(structure_level, 2) if structure_level > 0 else None,
        "가격구조확인": bool(structure["confirmed"]),
        "가격구조상태": structure["status"],
        "가격구조확인폭퍼센트": structure["extent_pct"],
        "진행단계": stage,
        "신뢰도": int(confidence),
        "신뢰도등급": _confidence_grade(confidence),
        "강도점수": int(strength_score),
        "강도": _strength_grade(strength_score),
        "추세정합": bool(trend_consistent),
        "초보투자자해석": beginner,
        "유효기간봉": validity,
        "탐색기간봉": int(config["search_bars"]),
        "무효화기준": (
            f"종가가 두 번째 피벗 {'저점' if direction == '상승' else '고점'}을 "
            f"{float(config['invalidation_buffer_pct']):.1f}% 이상 {'하회' if direction == '상승' else '상회'}하면 종료"
        ),
    }


def analyze_divergence_timeframe(
    rows: List[Dict[str, Any]],
    timeframe: str,
) -> Dict[str, Any]:
    config = DIVERGENCE_CONFIG[timeframe]
    rows = confirmed_rows(rows, timeframe)
    search_bars = int(config["search_bars"])
    if len(rows) > search_bars:
        rows = rows[-search_bars:]

    minimum = int(config["minimum_observations"])
    if len(rows) < minimum:
        reason = f"분석 데이터 부족 · {len(rows)}/{minimum}봉"
        return {
            "분석가능": False,
            "available": False,
            "시간봉": timeframe,
            "관측봉수": len(rows),
            "탐색기간봉": search_bars,
            "유효기간봉": int(config["validity_bars"]),
            "상승": _no_signal("상승", reason),
            "하락": _no_signal("하락", reason),
            "활성신호": [],
            "사유": reason,
        }

    closes = [safe_float(row.get("종가")) for row in rows]
    rsi_values = calculate_rsi_series(closes, 14)
    left = int(config["pivot_left"])
    right = int(config["pivot_right"])
    low_pivots = _pivot_points(rows, rsi_values, "low", left, right)
    high_pivots = _pivot_points(rows, rsi_values, "high", left, right)

    candidates: List[Dict[str, Any]] = []
    min_gap = int(config["min_pivot_gap"])
    max_gap = int(config["max_pivot_gap"])
    min_price_pct = float(config["min_price_change_pct"])
    min_rsi_delta = float(config["min_rsi_delta"])

    def scan(pivots: List[Dict[str, Any]], mode: str) -> None:
        for second_pos in range(1, len(pivots)):
            second = pivots[second_pos]
            for first_pos in range(second_pos - 1, -1, -1):
                first = pivots[first_pos]
                gap = second["index"] - first["index"]
                if gap < min_gap:
                    continue
                if gap > max_gap:
                    break
                price_change_pct = (float(second["price"]) / float(first["price"]) - 1.0) * 100.0
                rsi_change = float(second["rsi"]) - float(first["rsi"])
                signal_type = None
                if mode == "low":
                    if price_change_pct <= -min_price_pct and rsi_change >= min_rsi_delta:
                        signal_type = "REGULAR_BULLISH"
                    elif price_change_pct >= min_price_pct and rsi_change <= -min_rsi_delta:
                        signal_type = "HIDDEN_BULLISH"
                else:
                    if price_change_pct >= min_price_pct and rsi_change <= -min_rsi_delta:
                        signal_type = "REGULAR_BEARISH"
                    elif price_change_pct <= -min_price_pct and rsi_change >= min_rsi_delta:
                        signal_type = "HIDDEN_BEARISH"
                if not signal_type:
                    continue
                signal = _build_divergence_signal(
                    timeframe,
                    rows,
                    closes,
                    first,
                    second,
                    signal_type,
                    mode,
                    config,
                )
                if signal:
                    candidates.append(signal)

    scan(low_pivots, "low")
    scan(high_pivots, "high")

    def select(direction: str) -> Dict[str, Any]:
        items = [item for item in candidates if item.get("방향") == direction]
        if not items:
            return _no_signal(direction, f"유효기간 내 {direction} 다이버전스 없음")
        items.sort(
            key=lambda item: (
                -int(item.get("발생봉전", 999999)),
                int(item.get("신뢰도", 0)),
                int(item.get("강도점수", 0)),
            ),
            reverse=True,
        )
        # 가장 최근 확정 신호를 우선하며 같은 시점이면 품질이 높은 신호를 선택한다.
        items.sort(key=lambda item: int(item.get("발생봉전", 999999)))
        newest_age = int(items[0].get("발생봉전", 999999))
        newest = [item for item in items if int(item.get("발생봉전", 999999)) == newest_age]
        newest.sort(key=lambda item: (int(item.get("신뢰도", 0)), int(item.get("강도점수", 0))), reverse=True)
        return newest[0]

    bullish = select("상승")
    bearish = select("하락")
    active = [item for item in (bullish, bearish) if item.get("탐지") is True]

    return {
        "분석가능": True,
        "available": True,
        "시간봉": timeframe,
        "관측봉수": len(rows),
        "탐색기간봉": search_bars,
        "유효기간봉": int(config["validity_bars"]),
        "상승": bullish,
        "하락": bearish,
        "활성신호": active,
        "설정": {
            "피벗좌측봉": left,
            "피벗우측확정봉": right,
            "최소피벗간격봉": min_gap,
            "최대피벗간격봉": max_gap,
            "최소가격차퍼센트": min_price_pct,
            "최소RSI차": min_rsi_delta,
            "거래량급증배수": float(config["relative_volume_threshold"]),
        },
    }


def build_divergence_bundle(
    four_hour_rows: List[Dict[str, Any]],
    daily_rows: List[Dict[str, Any]],
    weekly_rows: List[Dict[str, Any]],
    monthly_rows: List[Dict[str, Any]],
) -> Dict[str, Any]:
    timeframes = {
        "4시간봉": analyze_divergence_timeframe(four_hour_rows, "4시간봉"),
        "일봉": analyze_divergence_timeframe(daily_rows, "일봉"),
        "주봉": analyze_divergence_timeframe(weekly_rows, "주봉"),
        "월봉": analyze_divergence_timeframe(monthly_rows, "월봉"),
    }
    active: List[Dict[str, Any]] = []
    for timeframe, item in timeframes.items():
        for signal in item.get("활성신호", []):
            copied = dict(signal)
            copied["시간봉"] = timeframe
            active.append(copied)
    active.sort(key=lambda item: (int(item.get("발생봉전", 999999)), -int(item.get("신뢰도", 0))))
    return {
        "분석상태": "정상" if any(item.get("분석가능") for item in timeframes.values()) else "자료부족",
        "계산방식": "RSI14(Wilder) + 확정 피벗 + Relative Volume(직전20봉) + 종가 가격구조 확인",
        "미래데이터사용": False,
        "확정피벗사용": True,
        "시간봉": timeframes,
        "활성신호": active,
        "활성신호수": len(active),
    }

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
                "4시간봉": {"available": False, "score": 0.0, "trend": "자료 부족", "observations": 0, "confidence": 0},
                "일봉": {"available": False, "score": 0.0, "trend": "자료 부족", "observations": 0, "confidence": 0},
                "주봉": {"available": False, "score": 0.0, "trend": "자료 부족", "observations": 0, "confidence": 0},
                "월봉": {"available": False, "score": 0.0, "trend": "자료 부족", "observations": 0, "confidence": 0},
                "다이버전스": build_divergence_bundle([], [], [], []),
                "수집오류": errors,
            }

    hourly_rows: List[Dict[str, Any]] = []
    four_hour_rows: List[Dict[str, Any]] = []

    if source.startswith("Yahoo") and selected_symbol:
        intraday_chart = parse_chart_result(
            "종목 6개월 1시간 차트",
            selected_symbol,
            "equity",
            "KRW",
            request_chart(selected_symbol, range_value="6mo", interval="1h"),
        )
        if intraday_chart.get("수집상태") == "정상":
            hourly_rows = normalize_yahoo_rows(intraday_chart.get("일별데이터"))
            four_hour_rows = aggregate_four_hour_rows(hourly_rows)
        else:
            errors.append(
                f"{selected_symbol} 4시간봉: {safe_text(intraday_chart.get('응답메시지'), '자료 부족')}"
            )

    weekly_rows = aggregate_rows(rows, "weekly")
    monthly_rows = aggregate_rows(rows, "monthly")

    four_hour = timeframe_summary(
        confirmed_rows(four_hour_rows, "4시간봉"),
        fast_period=5,
        medium_period=20,
        long_period=60,
        momentum_fast_period=5,
        momentum_medium_period=20,
        minimum_observations=60,
    )
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

    divergence = build_divergence_bundle(
        four_hour_rows,
        rows,
        weekly_rows,
        monthly_rows,
    )

    available_count = sum(bool(item.get("available")) for item in (daily, weekly, monthly))
    overall = "정상" if available_count == 3 else "부분성공" if available_count > 0 else "실패"

    if four_hour_rows:
        source = source + " + Yahoo 6개월 1시간봉→4시간봉"

    return {
        "수집상태": overall,
        "심볼": selected_symbol,
        "데이터출처": source,
        "응답메시지": "" if overall == "정상" else "일부 시간축 자료 부족",
        "4시간봉": four_hour,
        "일봉": daily,
        "주봉": weekly,
        "월봉": monthly,
        "다이버전스": divergence,
        "4시간봉데이터개수": len(confirmed_rows(four_hour_rows, "4시간봉")),
        "일봉데이터개수": len(rows),
        "주봉데이터개수": len(weekly_rows),
        "월봉데이터개수": len(monthly_rows),
        "최초일": rows[0].get("시각UTC", "") if rows else "",
        "최종일": rows[-1].get("시각UTC", "") if rows else "",
        "최근일봉": rows[-120:],
        "수집오류": errors,
    }
