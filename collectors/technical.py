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
                "거래일수": 1,
            }
            continue

        item = grouped[key]
        item["timestamp"] = timestamp
        item["고가"] = max(item["고가"], safe_float(row.get("고가"), item["고가"]))
        low = safe_float(row.get("저가"), item["저가"])
        item["저가"] = min(item["저가"], low) if low > 0 else item["저가"]
        item["종가"] = safe_float(row.get("종가"), item["종가"])
        item["거래량"] += safe_float(row.get("거래량"))
        item["거래일수"] = int(safe_float(item.get("거래일수"), 0)) + 1

    return list(grouped.values())




DIVERGENCE_CONFIG: Dict[str, Dict[str, Any]] = {
    "4시간봉": {
        "search_bars": 180,
        "validity_bars": 12,
        "minimum_observations": 80,
        "pivot_left": 2,
        "pivot_right": 1,
        "min_pivot_gap": 5,
        "max_pivot_gap": 50,
        "min_price_change_pct": 0.40,
        "min_rsi_delta": 2.0,
        "volume_increase_threshold": 1.20,
        "relative_volume_threshold": 1.50,
        "clear_volume_threshold": 2.00,
        "strong_volume_threshold": 4.00,
        "confirmation_window_bars": 4,
        "invalidation_buffer_pct": 0.50,
    },
    "일봉": {
        "search_bars": 150,
        "validity_bars": 10,
        "minimum_observations": 80,
        "pivot_left": 2,
        "pivot_right": 1,
        "min_pivot_gap": 5,
        "max_pivot_gap": 60,
        "min_price_change_pct": 0.60,
        "min_rsi_delta": 2.5,
        "volume_increase_threshold": 1.20,
        "relative_volume_threshold": 1.50,
        "clear_volume_threshold": 2.00,
        "strong_volume_threshold": 4.00,
        "confirmation_window_bars": 4,
        "invalidation_buffer_pct": 0.60,
    },
    "주봉": {
        "search_bars": 120,
        "validity_bars": 8,
        "minimum_observations": 52,
        "pivot_left": 2,
        "pivot_right": 1,
        "min_pivot_gap": 3,
        "max_pivot_gap": 40,
        "min_price_change_pct": 1.00,
        "min_rsi_delta": 3.0,
        "volume_increase_threshold": 1.20,
        "relative_volume_threshold": 1.50,
        "clear_volume_threshold": 2.00,
        "strong_volume_threshold": 4.00,
        "confirmation_window_bars": 3,
        "invalidation_buffer_pct": 0.80,
    },
    "월봉": {
        "search_bars": 72,
        "validity_bars": 6,
        "minimum_observations": 36,
        "pivot_left": 2,
        "pivot_right": 1,
        "min_pivot_gap": 2,
        "max_pivot_gap": 24,
        "min_price_change_pct": 1.50,
        "min_rsi_delta": 3.0,
        "volume_increase_threshold": 1.20,
        "relative_volume_threshold": 1.50,
        "clear_volume_threshold": 2.00,
        "strong_volume_threshold": 4.00,
        "confirmation_window_bars": 2,
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
    """
    Aggregate Yahoo 1h Korean-session rows using the KRX 09:00 KST session anchor.

    Buckets are 09:00-13:00 and 13:00-15:30 KST.  The second candle is a
    shortened end-of-session candle because the regular KRX session is 6.5h.
    The public timestamp is the *bucket close time*, not the start time of the
    last 1h source bar; this prevents a 09:00-13:00 candle from being displayed
    misleadingly as 12:00.
    """
    grouped: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()

    for row in rows:
        source_timestamp = int(safe_float(row.get("timestamp"), 0))
        close = safe_float(row.get("종가"))
        if source_timestamp <= 0 or close <= 0:
            continue

        local_dt = datetime.fromtimestamp(source_timestamp, tz=timezone.utc).astimezone(KST)
        minute_of_day = local_dt.hour * 60 + local_dt.minute
        market_open = 9 * 60
        market_close = 15 * 60 + 30
        if minute_of_day < market_open or minute_of_day > market_close:
            continue

        session_minutes = minute_of_day - market_open
        bucket = 0 if session_minutes < 240 else 1
        bucket_start_minutes = market_open + bucket * 240
        bucket_end_minutes = min(bucket_start_minutes + 240, market_close)

        start_hour, start_minute = divmod(bucket_start_minutes, 60)
        end_hour, end_minute = divmod(bucket_end_minutes, 60)
        start_local = local_dt.replace(
            hour=start_hour,
            minute=start_minute,
            second=0,
            microsecond=0,
        )
        end_local = local_dt.replace(
            hour=end_hour,
            minute=end_minute,
            second=0,
            microsecond=0,
        )
        start_timestamp = int(start_local.astimezone(timezone.utc).timestamp())
        end_timestamp = int(end_local.astimezone(timezone.utc).timestamp())
        end_iso = datetime.fromtimestamp(end_timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        start_iso = datetime.fromtimestamp(start_timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")
        key = f"{local_dt.date().isoformat()}-{bucket}"

        slot_label = "오전" if bucket == 0 else "오후"

        if key not in grouped:
            grouped[key] = {
                "기간": key,
                "timestamp": end_timestamp,
                "시각UTC": end_iso,
                "봉시작시각UTC": start_iso,
                "봉종료시각UTC": end_iso,
                "시가": safe_float(row.get("시가"), close),
                "고가": safe_float(row.get("고가"), close),
                "저가": safe_float(row.get("저가"), close),
                "종가": close,
                "거래량": safe_float(row.get("거래량")),
                "세션슬롯": slot_label,
                "거래일수": 1,
                "_bucketEndTimestamp": end_timestamp,
                "_lastSourceTimestamp": source_timestamp,
            }
            continue

        item = grouped[key]
        item["timestamp"] = end_timestamp
        item["시각UTC"] = end_iso
        item["봉종료시각UTC"] = end_iso
        item["_lastSourceTimestamp"] = source_timestamp
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
    confirmation_window_bars: Optional[int] = None,
    increase_threshold: float = 1.20,
    clear_threshold: float = 2.00,
    strong_threshold: float = 4.00,
    timeframe: str = "",
    direction: str = "",
) -> Dict[str, Any]:
    """Evaluate relative volume close to the divergence detection point.

    Improvements in v8:
    - 4시간봉은 오전/오후 슬롯을 섞지 않고 같은 세션 슬롯끼리 비교한다.
    - 주봉/월봉은 총거래량이 아니라 거래일수로 보정한 일평균 거래량으로 비교한다.
    - 거래량 증가가 있어도 신호 방향과 반대 가격행동이면 확인 통과로 보지 않는다.
    """
    valid_volume_count = sum(1 for row in rows if safe_float(row.get("거래량")) > 0)
    if valid_volume_count < min(average_bars + 1, len(rows)):
        return {
            "available": False,
            "confirmed": False,
            "ratio": None,
            "index": None,
            "status": "거래량 데이터 없음",
            "grade": "데이터 없음",
            "surge_confirmed": False,
            "direction_aligned": False,
        }

    def row_volume_metric(index: int) -> Optional[float]:
        if index < 0 or index >= len(rows):
            return None
        row = rows[index]
        volume = safe_float(row.get("거래량"))
        if volume <= 0:
            return None
        if timeframe in {"주봉", "월봉"}:
            trading_days = max(1.0, safe_float(row.get("거래일수"), 0.0))
            return volume / trading_days
        return volume

    def previous_metrics(index: int) -> List[float]:
        metrics: List[float] = []
        if timeframe == "4시간봉":
            current_slot = safe_text(rows[index].get("세션슬롯"))
            for i in range(index - 1, -1, -1):
                if current_slot and safe_text(rows[i].get("세션슬롯")) != current_slot:
                    continue
                metric = row_volume_metric(i)
                if metric and metric > 0:
                    metrics.append(metric)
                if len(metrics) >= average_bars:
                    break
        else:
            begin = max(0, index - average_bars)
            for i in range(begin, index):
                metric = row_volume_metric(i)
                if metric and metric > 0:
                    metrics.append(metric)
        return metrics

    def direction_supportive(index: int) -> bool:
        if index < 0 or index >= len(rows):
            return False
        row = rows[index]
        close = safe_float(row.get("종가"))
        open_ = safe_float(row.get("시가"), close)
        prev_close = safe_float(rows[index - 1].get("종가"), close) if index > 0 else close
        if direction == "상승":
            return (close >= prev_close) or (close > open_)
        if direction == "하락":
            return (close <= prev_close) or (close < open_)
        return True

    best_aligned_ratio: Optional[float] = None
    best_aligned_index: Optional[int] = None
    best_any_ratio: Optional[float] = None
    best_any_index: Optional[int] = None
    best_any_aligned = False

    start = max(start_index, 1 if direction else 0)
    stop = len(rows)
    if confirmation_window_bars is not None and confirmation_window_bars > 0:
        stop = min(stop, start_index + int(confirmation_window_bars) + 1)

    for index in range(start, stop):
        metric = row_volume_metric(index)
        previous = previous_metrics(index)
        if metric is None or len(previous) < max(5, average_bars // 2):
            continue
        average = sum(previous) / len(previous)
        if average <= 0:
            continue
        ratio = metric / average
        aligned = direction_supportive(index)

        if best_any_ratio is None or ratio > best_any_ratio:
            best_any_ratio = ratio
            best_any_index = index
            best_any_aligned = aligned

        if aligned and (best_aligned_ratio is None or ratio > best_aligned_ratio):
            best_aligned_ratio = ratio
            best_aligned_index = index

    if best_any_ratio is None:
        return {
            "available": False,
            "confirmed": False,
            "ratio": None,
            "index": None,
            "status": "거래량 데이터 없음",
            "grade": "데이터 없음",
            "surge_confirmed": False,
            "direction_aligned": False,
        }

    use_ratio = best_aligned_ratio if best_aligned_ratio is not None else best_any_ratio
    use_index = best_aligned_index if best_aligned_index is not None else best_any_index
    aligned = best_aligned_ratio is not None if best_aligned_ratio is not None else best_any_aligned
    ratio = float(use_ratio)
    increased = ratio >= increase_threshold
    surge_confirmed = ratio >= threshold
    confirmed = increased and aligned

    if not aligned and ratio >= increase_threshold:
        grade = "거래량 증가 있으나 방향 미일치"
    elif ratio >= strong_threshold:
        grade = "강한 거래량 확증"
    elif ratio >= clear_threshold:
        grade = "뚜렷한 거래량 증가"
    elif ratio >= threshold:
        grade = "거래량 증가 확인"
    elif ratio >= increase_threshold:
        grade = "약한 증가"
    else:
        grade = "거래량 증가 미확인"

    return {
        "available": True,
        "confirmed": confirmed,
        "ratio": round(ratio, 2),
        "index": use_index,
        "status": grade,
        "grade": grade,
        "surge_confirmed": surge_confirmed and aligned,
        "direction_aligned": aligned,
    }

def _structure_reference(
    rows: List[Dict[str, Any]],
    first_index: int,
    second_index: int,
    direction: str,
    left: int = 2,
    right: int = 1,
) -> Dict[str, Any]:
    """Select the nearest meaningful swing between the two divergence pivots.

    For a bullish divergence, use the most recent confirmed swing high before
    the second low. For a bearish divergence, use the most recent confirmed
    swing low before the second high. Only the interval between the two
    divergence pivots is considered, so a distant historical swing cannot be
    imported accidentally.
    """
    start = first_index + 1
    stop = second_index
    if start >= stop:
        return {"level": 0.0, "index": None, "time": "", "method": "없음"}

    key = "고가" if direction == "상승" else "저가"
    mode = "high" if direction == "상승" else "low"
    candidate_indices: List[int] = []

    # Search backwards so the nearest confirmed swing is chosen first.
    for index in range(stop - 1, start - 1, -1):
        if index - left < start or index + right >= stop:
            continue
        value = safe_float(rows[index].get(key))
        if value <= 0:
            continue
        window = [safe_float(rows[i].get(key)) for i in range(index - left, index + right + 1)]
        if any(item <= 0 for item in window):
            continue
        neighbors = window[:left] + window[left + 1:]
        if mode == "high":
            is_pivot = value >= max(neighbors) and value > min(neighbors)
        else:
            is_pivot = value <= min(neighbors) and value < max(neighbors)
        if is_pivot:
            candidate_indices.append(index)
            break

    if not candidate_indices:
        # No confirmed local swing exists between the pivots. Do not fall back
        # to an older external swing because that would distort the confirmation line.
        return {"level": 0.0, "index": None, "time": "", "method": "두 피벗 사이 유효 스윙 없음"}

    selected_index = candidate_indices[0]
    level = safe_float(rows[selected_index].get(key))
    row = rows[selected_index]
    return {
        "level": level,
        "index": selected_index,
        "time": safe_text(row.get("봉종료시각UTC") or row.get("시각UTC")),
        "method": "두 피벗 사이 가장 가까운 유효 스윙",
    }

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


def _elapsed_text_from_timestamp(timestamp: int) -> str:
    if timestamp <= 0:
        return ""
    observed = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    now = datetime.now(timezone.utc)
    if observed > now:
        return "0분"
    total_minutes = int((now - observed).total_seconds() // 60)
    days, remainder = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remainder, 60)
    if days > 0:
        return f"{days}일 {hours}시간" if hours else f"{days}일"
    if hours > 0:
        return f"{hours}시간 {minutes}분" if minutes else f"{hours}시간"
    return f"{max(0, minutes)}분"


def _bar_age_text(age: int) -> str:
    return f"{max(0, int(age))}개 거래봉 전"


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
    # "최근 N봉"은 현재 확정봉을 0봉 전으로 볼 때 0..N-1만 포함한다.
    # 예: 최근 12봉이면 발생봉전 0~11만 유효하고 12봉 전은 만료다.
    if age >= validity:
        return None

    direction = meta["direction"]
    invalidation_buffer = float(config["invalidation_buffer_pct"]) / 100.0
    pivot2_price = float(second["price"])
    for index in range(confirmation_index, len(rows)):
        close = safe_float(rows[index].get("종가"))
        if close <= 0:
            continue
        if direction == "상승" and close < pivot2_price * (1.0 - invalidation_buffer):
            return None
        if direction == "하락" and close > pivot2_price * (1.0 + invalidation_buffer):
            return None

    volume = _relative_volume_confirmation(
        rows,
        confirmation_index,
        float(config["relative_volume_threshold"]),
        confirmation_window_bars=int(config.get("confirmation_window_bars", 0)) or None,
        increase_threshold=float(config.get("volume_increase_threshold", 1.20)),
        clear_threshold=float(config.get("clear_volume_threshold", 2.00)),
        strong_threshold=float(config.get("strong_volume_threshold", 4.00)),
        timeframe=timeframe,
        direction=direction,
    )
    structure_reference = _structure_reference(
        rows,
        first["index"],
        second["index"],
        direction,
        left=int(config.get("pivot_left", 2)),
        right=int(config.get("pivot_right", 1)),
    )
    structure_level = safe_float(structure_reference.get("level"))
    structure = _structure_confirmation(
        rows,
        confirmation_index,
        structure_level,
        direction,
    )

    if volume["confirmed"] and structure["confirmed"]:
        stage = "강한 확인 신호"
    elif volume["confirmed"]:
        stage = "거래량 확인 신호"
    elif structure["confirmed"]:
        stage = "구조 확인 신호"
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

    minimum_price_change = max(float(config["min_price_change_pct"]), 0.01)
    minimum_rsi_delta = max(float(config["min_rsi_delta"]), 0.01)
    divergence_quality_score = round(clamp(
        min(20.0, (price_change_pct / minimum_price_change) * 10.0) +
        min(20.0, (rsi_change / minimum_rsi_delta) * 10.0) +
        min(20.0, prominence * 5.0) +
        distance_quality * 20.0 +
        (20.0 if trend_consistent else 8.0),
        0.0,
        100.0,
    ))

    latest_close = closes[-1] if closes else 0.0
    if direction == "상승":
        followthrough_pct = max(0.0, (latest_close / pivot2_price - 1.0) * 100.0) if pivot2_price > 0 else 0.0
    else:
        followthrough_pct = max(0.0, (pivot2_price / latest_close - 1.0) * 100.0) if latest_close > 0 else 0.0

    rvol = float(volume["ratio"] or 0.0)
    increase_threshold = max(float(config.get("volume_increase_threshold", 1.20)), 0.01)
    if volume["confirmed"]:
        volume_confirmation_points = 22.0 + min(8.0, max(0.0, rvol / increase_threshold - 1.0) * 10.0)
    elif volume["available"]:
        volume_confirmation_points = min(8.0, max(0.0, rvol / increase_threshold) * 8.0)
    else:
        volume_confirmation_points = 0.0

    structure_confirmation_points = (
        35.0 + min(5.0, max(0.0, float(structure["extent_pct"])) * 2.0)
        if structure["confirmed"] else 0.0
    )
    confirmation_score = (
        12.0 +
        freshness_score * 10.0 +
        volume_confirmation_points +
        structure_confirmation_points +
        min(10.0, followthrough_pct * 1.5)
    )
    if stage == "초기 신호":
        confirmation_score = min(39.0, confirmation_score)
    elif stage in {"거래량 확인 신호", "구조 확인 신호"}:
        confirmation_score = clamp(confirmation_score, 40.0, 79.0)
    else:
        confirmation_score = clamp(confirmation_score, 70.0, 100.0)
    confirmation_score = round(clamp(confirmation_score, 0.0, 100.0))

    strength_score = (
        min(20.0, price_change_pct * 2.0) +
        min(20.0, rsi_change * 1.5) +
        min(20.0, max(0.0, rvol - 0.8) * 18.0) +
        min(20.0, float(structure["extent_pct"]) * 5.0) +
        min(20.0, followthrough_pct * 3.0)
    )
    strength_score = round(clamp(strength_score, 0.0, 100.0))

    def row_time(index: Optional[int]) -> str:
        if index is None or index < 0 or index >= len(rows):
            return ""
        row = rows[index]
        text = safe_text(row.get("봉종료시각UTC") or row.get("시각UTC"))
        if text:
            return text
        timestamp = int(safe_float(row.get("timestamp"), 0))
        if timestamp <= 0:
            return ""
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat().replace("+00:00", "Z")

    detection_row = rows[confirmation_index]
    detection_timestamp = int(safe_float(detection_row.get("timestamp"), 0))
    detection_time = row_time(confirmation_index)
    structure_confirmation_time = row_time(structure.get("index")) if structure["confirmed"] else ""
    volume_confirmation_time = row_time(volume.get("index")) if volume.get("confirmed") else ""
    signal_confirmation_time = structure_confirmation_time if structure["confirmed"] else ""
    actual_elapsed = _elapsed_text_from_timestamp(detection_timestamp)

    confirmation_label = "반전 확인도" if meta["nature"] == "반전" else "추세 지속 확인도"
    beginner = meta["meaning"]
    if stage == "강한 확인 신호":
        beginner += " 거래량 증가와 가장 가까운 유효 가격구조 확인선 돌파·이탈이 모두 확인된 강한 확인 단계입니다."
    elif stage == "거래량 확인 신호":
        beginner += " 거래량 증가는 확인됐지만 가격구조 돌파·이탈은 아직 확인되지 않았습니다."
    elif stage == "구조 확인 신호":
        beginner += " 가격구조 돌파·이탈은 확인됐지만 거래량 증가는 아직 확인되지 않았습니다."
    else:
        beginner += " 거래량 증가와 가격구조 확인이 모두 부족한 초기 후보 신호입니다."
    beginner += (
        f" 다이버전스 품질 {divergence_quality_score}/100은 피벗 자체의 품질이고, "
        f"신뢰도 {confirmation_score}/100은 현재 후속 확인 정도입니다. 둘 다 미래 확률을 뜻하지 않습니다."
    )

    summary = f"{meta['name']} · {_bar_age_text(age)} · {stage} · 신뢰도 {_confidence_grade(confirmation_score)}"

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
        "거래봉설명": _bar_age_text(age),
        "경과설명": actual_elapsed,
        "실제경과설명": actual_elapsed,
        "다이버전스탐지시각UTC": detection_time,
        "피벗확정시각UTC": detection_time,
        "신호확정시각UTC": signal_confirmation_time,
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
        "거래량급증기준충족": bool(volume.get("surge_confirmed")),
        "거래량방향일치": bool(volume.get("direction_aligned")),
        "거래량상태": volume["status"],
        "거래량확인시각UTC": volume_confirmation_time,
        "가격구조기준": round(structure_level, 2) if structure_level > 0 else None,
        "가격구조기준시각UTC": safe_text(structure_reference.get("time")),
        "가격구조기준선정방식": safe_text(structure_reference.get("method")),
        "가격구조확인": bool(structure["confirmed"]),
        "가격구조상태": structure["status"],
        "가격구조확인폭퍼센트": structure["extent_pct"],
        "가격구조확인시각UTC": structure_confirmation_time,
        "진행단계": stage,
        "다이버전스품질": int(divergence_quality_score),
        "다이버전스품질등급": _confidence_grade(divergence_quality_score),
        "확인도명": confirmation_label,
        "방향확인도": int(confirmation_score),
        "방향확인도등급": _confidence_grade(confirmation_score),
        "신뢰도": int(confirmation_score),
        "신뢰도등급": _confidence_grade(confirmation_score),
        "강도점수": int(strength_score),
        "강도": _strength_grade(strength_score),
        "추세정합": bool(trend_consistent),
        "초보투자자해석": beginner,
        "유효기간봉": validity,
        "탐색기간봉": int(config["search_bars"]),
        "거래량확인창봉": int(config.get("confirmation_window_bars", 0)),
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
    validity = int(config["validity_bars"])
    if len(rows) < minimum:
        reason = f"분석 데이터 부족 · {len(rows)}/{minimum}봉"
        no_signal = _no_signal("", reason)
        return {
            "분석가능": False,
            "available": False,
            "시간봉": timeframe,
            "관측봉수": len(rows),
            "탐색기간봉": search_bars,
            "유효기간봉": validity,
            "대표신호": no_signal,
            "상승": _no_signal("상승", reason),
            "하락": _no_signal("하락", reason),
            "활성신호": [],
            "과거신호": [],
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

    # 핵심 원칙: 상승/하락을 각각 뽑지 않는다. 네 종류 전체에서
    # 최근 유효 범위 안의 가장 최근 확정 다이버전스 한 개만 대표 신호로 선정한다.
    candidates.sort(
        key=lambda item: (
            int(item.get("발생봉전", 999999)),
            -int(item.get("신뢰도", 0)),
            -int(item.get("다이버전스품질", 0)),
            -int(item.get("강도점수", 0)),
        )
    )

    representative: Dict[str, Any]
    if candidates:
        representative = dict(candidates[0])
        representative["신호상태"] = "현재 대표 신호"
        representative["대표신호"] = True
        representative["요약"] = (
            f"{representative.get('신호명', '')} · "
            f"{representative.get('거래봉설명', '')} · "
            f"{representative.get('진행단계', '')} · "
            f"신뢰도 {representative.get('신뢰도', 0)}/100"
        )
    else:
        representative = _no_signal("", f"최근 {validity}봉 내 RSI 다이버전스 없음")
        representative["대표신호"] = False

    # 과거 후보는 기록용으로만 보존하며 활성 신호/UI에는 노출하지 않는다.
    history = []
    for item in candidates[1:]:
        copied = dict(item)
        copied["신호상태"] = "과거 유효 신호"
        copied["대표신호"] = False
        history.append(copied)
    history = history[:12]

    bullish = _no_signal("상승", f"현재 대표 신호가 {'상승' if representative.get('방향') == '상승' else '상승이 아님'}")
    bearish = _no_signal("하락", f"현재 대표 신호가 {'하락' if representative.get('방향') == '하락' else '하락이 아님'}")
    if representative.get("탐지") is True:
        if representative.get("방향") == "상승":
            bullish = representative
        elif representative.get("방향") == "하락":
            bearish = representative

    active = [representative] if representative.get("탐지") is True else []

    return {
        "분석가능": True,
        "available": True,
        "시간봉": timeframe,
        "관측봉수": len(rows),
        "탐색기간봉": search_bars,
        "유효기간봉": validity,
        "대표신호": representative,
        "상승": bullish,
        "하락": bearish,
        "활성신호": active,
        "과거신호": history,
        "설정": {
            "대표신호선정": "일반상승·일반하락·히든상승·히든하락 전체 중 가장 최근 확정 1개",
            "피벗좌측봉": left,
            "피벗우측확정봉": right,
            "최소피벗간격봉": min_gap,
            "최대피벗간격봉": max_gap,
            "최소가격차퍼센트": min_price_pct,
            "최소RSI차": min_rsi_delta,
            "거래량증가기준배수": float(config.get("volume_increase_threshold", 1.20)),
            "기존거래량급증배수": float(config["relative_volume_threshold"]),
            "뚜렷한거래량배수": float(config.get("clear_volume_threshold", 2.00)),
            "강한거래량확증배수": float(config.get("strong_volume_threshold", 4.00)),
            "거래량확인창봉": int(config.get("confirmation_window_bars", 0)),
            "거래량비교방식": (
                "같은 세션 슬롯 20봉 평균 대비" if timeframe == "4시간봉"
                else "최근 20일 평균 대비" if timeframe == "일봉"
                else "최근 20주 일평균 거래량 대비" if timeframe == "주봉"
                else "최근 20개월 일평균 거래량 대비"
            ),
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
        signal = item.get("대표신호", {})
        if isinstance(signal, dict) and signal.get("탐지") is True:
            copied = dict(signal)
            copied["시간봉"] = timeframe
            active.append(copied)
    active.sort(key=lambda item: (int(item.get("발생봉전", 999999)), -int(item.get("신뢰도", 0))))
    return {
        "분석상태": "정상" if any(item.get("분석가능") for item in timeframes.values()) else "자료부족",
        "계산방식": "RSI14(Wilder) + 우측1봉 확정 피벗 + 시간봉별 최근 대표 1신호 + 근접 Relative Volume + 가장 가까운 유효 스윙 종가 확인",
        "엔진버전": "4.0-latest-one-per-timeframe",
        "4시간봉집계": "KRX 09:00 KST anchor · 09:00-13:00 / 13:00-15:30",
        "미래데이터사용": False,
        "확정피벗사용": True,
        "시간봉": timeframes,
        "활성신호": active,
        "활성신호수": len(active),
        "대표신호원칙": "각 시간봉에서 4종 전체 중 가장 최근 확정 1개만 활성",
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
        source = source + " + Yahoo 6개월 1시간봉→KRX 09:00 기준 장중 4시간봉"

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
