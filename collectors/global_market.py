"""
글로벌 시장 데이터 수집기 V1

수집 대상
- 원/달러: KRW=X
- S&P500: ^GSPC
- 나스닥: ^IXIC
- 필라델피아 반도체: ^SOX
- VIX: ^VIX
- 미국 10년물 금리: ^TNX
- 미국 5년물 금리: ^FVX
- 미국 13주 단기금리: ^IRX

특징
- requests 외 추가 패키지 없음
- Yahoo Chart API 사용
- 개별 자산 실패 시 전체 엔진 중단 방지
- 1일·5일·20일 변화율, MA5·MA20, 데이터 지연시간 계산
- main.py와 predictor.py에는 아직 연결하지 않음
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

import requests


KST = timezone(timedelta(hours=9))
UTC = timezone.utc

YAHOO_CHART_URL = (
    "https://query1.finance.yahoo.com/"
    "v8/finance/chart/{symbol}"
)

ASSETS = {
    "원달러": {
        "symbol": "KRW=X",
        "type": "fx",
        "unit": "KRW/USD",
    },
    "S&P500": {
        "symbol": "^GSPC",
        "type": "equity_index",
        "unit": "index",
    },
    "나스닥": {
        "symbol": "^IXIC",
        "type": "equity_index",
        "unit": "index",
    },
    "반도체지수": {
        "symbol": "^SOX",
        "type": "equity_index",
        "unit": "index",
    },
    "VIX": {
        "symbol": "^VIX",
        "type": "volatility",
        "unit": "index",
    },
    "미국10년물": {
        "symbol": "^TNX",
        "type": "yield",
        "unit": "percent",
    },
    "미국5년물": {
        "symbol": "^FVX",
        "type": "yield",
        "unit": "percent",
    },
    "미국13주": {
        "symbol": "^IRX",
        "type": "yield",
        "unit": "percent",
    },
}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default

        return float(
            str(value)
            .replace(",", "")
            .strip()
        )

    except (TypeError, ValueError):
        return default


def safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default

    return str(value).strip()


def moving_average(
    values: List[float],
    period: int,
) -> float:
    if period <= 0 or len(values) < period:
        return 0.0

    return sum(
        values[-period:]
    ) / period


def rate_of_change(
    values: List[float],
    period: int,
) -> float:
    if period <= 0 or len(values) <= period:
        return 0.0

    previous = values[-period - 1]
    current = values[-1]

    if previous == 0:
        return 0.0

    return (
        (current / previous)
        - 1.0
    ) * 100.0


def utc_iso(timestamp: Any) -> str:
    try:
        numeric = int(timestamp)

        return datetime.fromtimestamp(
            numeric,
            tz=UTC,
        ).isoformat()

    except (TypeError, ValueError, OSError):
        return ""


def age_hours(timestamp: Any) -> float:
    try:
        numeric = int(timestamp)

        observed = datetime.fromtimestamp(
            numeric,
            tz=UTC,
        )

        now = datetime.now(UTC)

        return max(
            (
                now - observed
            ).total_seconds()
            / 3600.0,
            0.0,
        )

    except (TypeError, ValueError, OSError):
        return 0.0


def request_chart(
    symbol: str,
    range_value: str = "3mo",
    interval: str = "1d",
) -> Dict[str, Any]:
    url = YAHOO_CHART_URL.format(
        symbol=symbol
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept": "application/json,text/plain,*/*",
    }

    params = {
        "range": range_value,
        "interval": interval,
        "includePrePost": "false",
        "events": "div,splits",
    }

    last_error = ""

    for attempt in range(3):
        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=20,
            )

            if response.status_code == 429:
                last_error = "Yahoo rate limit"
                time.sleep(
                    3 + attempt * 2
                )
                continue

            response.raise_for_status()

            data = response.json()

            if isinstance(data, dict):
                return data

            last_error = (
                "Yahoo 응답 형식이 "
                "딕셔너리가 아닙니다."
            )

        except Exception as error:
            last_error = (
                f"{type(error).__name__}: "
                f"{error}"
            )

            time.sleep(
                2 + attempt
            )

    return {
        "chart": {
            "result": None,
            "error": {
                "code": "REQUEST_FAILED",
                "description": last_error,
            },
        }
    }


def empty_asset_result(
    name: str,
    symbol: str,
    asset_type: str,
    unit: str,
    message: str,
) -> Dict[str, Any]:
    return {
        "자산명": name,
        "심볼": symbol,
        "유형": asset_type,
        "단위": unit,
        "수집상태": "실패",
        "응답메시지": message,
        "현재값": 0.0,
        "전일값": 0.0,
        "1일변화율": 0.0,
        "5일변화율": 0.0,
        "20일변화율": 0.0,
        "MA5": 0.0,
        "MA20": 0.0,
        "현재값대비MA20": 0.0,
        "최종관측시각UTC": "",
        "데이터지연시간": 0.0,
        "데이터개수": 0,
        "일별데이터": [],
    }


def parse_chart_result(
    name: str,
    symbol: str,
    asset_type: str,
    unit: str,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    chart = data.get(
        "chart",
        {},
    )

    if not isinstance(chart, dict):
        return empty_asset_result(
            name,
            symbol,
            asset_type,
            unit,
            "chart 필드가 없습니다.",
        )

    error = chart.get("error")

    if error:
        if isinstance(error, dict):
            message = safe_text(
                error.get("description")
                or error.get("code")
            )
        else:
            message = safe_text(error)

        return empty_asset_result(
            name,
            symbol,
            asset_type,
            unit,
            message or "Yahoo 응답 오류",
        )

    results = chart.get("result")

    if not isinstance(results, list) or not results:
        return empty_asset_result(
            name,
            symbol,
            asset_type,
            unit,
            "Yahoo 결과가 비어 있습니다.",
        )

    result = results[0]

    if not isinstance(result, dict):
        return empty_asset_result(
            name,
            symbol,
            asset_type,
            unit,
            "Yahoo 결과 형식 오류",
        )

    timestamps = result.get(
        "timestamp",
        [],
    )

    indicators = result.get(
        "indicators",
        {},
    )

    quotes = (
        indicators.get("quote", [])
        if isinstance(indicators, dict)
        else []
    )

    if not isinstance(quotes, list) or not quotes:
        return empty_asset_result(
            name,
            symbol,
            asset_type,
            unit,
            "가격 데이터가 없습니다.",
        )

    quote = quotes[0]

    if not isinstance(quote, dict):
        return empty_asset_result(
            name,
            symbol,
            asset_type,
            unit,
            "가격 데이터 형식 오류",
        )

    closes = quote.get(
        "close",
        [],
    )

    opens = quote.get(
        "open",
        [],
    )

    highs = quote.get(
        "high",
        [],
    )

    lows = quote.get(
        "low",
        [],
    )

    volumes = quote.get(
        "volume",
        [],
    )

    rows: List[Dict[str, Any]] = []

    for index, timestamp in enumerate(
        timestamps
        if isinstance(timestamps, list)
        else []
    ):
        close = safe_float(
            closes[index]
            if isinstance(closes, list)
            and index < len(closes)
            else 0.0
        )

        if close <= 0:
            continue

        rows.append(
            {
                "시각UTC": utc_iso(timestamp),
                "timestamp": int(timestamp),
                "종가": close,
                "시가": safe_float(
                    opens[index]
                    if isinstance(opens, list)
                    and index < len(opens)
                    else 0.0
                ),
                "고가": safe_float(
                    highs[index]
                    if isinstance(highs, list)
                    and index < len(highs)
                    else 0.0
                ),
                "저가": safe_float(
                    lows[index]
                    if isinstance(lows, list)
                    and index < len(lows)
                    else 0.0
                ),
                "거래량": safe_float(
                    volumes[index]
                    if isinstance(volumes, list)
                    and index < len(volumes)
                    else 0.0
                ),
            }
        )

    if not rows:
        return empty_asset_result(
            name,
            symbol,
            asset_type,
            unit,
            "유효한 종가 데이터가 없습니다.",
        )

    rows.sort(
        key=lambda item: item["timestamp"]
    )

    close_values = [
        row["종가"]
        for row in rows
    ]

    latest = close_values[-1]
    previous = (
        close_values[-2]
        if len(close_values) >= 2
        else latest
    )

    ma5 = moving_average(
        close_values,
        5,
    )

    ma20 = moving_average(
        close_values,
        20,
    )

    return {
        "자산명": name,
        "심볼": symbol,
        "유형": asset_type,
        "단위": unit,
        "수집상태": "정상",
        "응답메시지": "",
        "현재값": round(
            latest,
            6,
        ),
        "전일값": round(
            previous,
            6,
        ),
        "1일변화율": round(
            rate_of_change(
                close_values,
                1,
            ),
            6,
        ),
        "5일변화율": round(
            rate_of_change(
                close_values,
                5,
            ),
            6,
        ),
        "20일변화율": round(
            rate_of_change(
                close_values,
                20,
            ),
            6,
        ),
        "MA5": round(
            ma5,
            6,
        ),
        "MA20": round(
            ma20,
            6,
        ),
        "현재값대비MA20": round(
            (
                (
                    latest
                    / ma20
                )
                - 1.0
            )
            * 100.0,
            6,
        )
        if ma20 > 0
        else 0.0,
        "최종관측시각UTC": rows[-1][
            "시각UTC"
        ],
        "데이터지연시간": round(
            age_hours(
                rows[-1]["timestamp"]
            ),
            3,
        ),
        "데이터개수": len(rows),
        "일별데이터": rows,
    }


def get_global_asset(
    name: str,
    config: Dict[str, str],
) -> Dict[str, Any]:
    symbol = safe_text(
        config.get("symbol")
    )

    asset_type = safe_text(
        config.get("type")
    )

    unit = safe_text(
        config.get("unit")
    )

    try:
        data = request_chart(
            symbol=symbol,
            range_value="3mo",
            interval="1d",
        )

        return parse_chart_result(
            name=name,
            symbol=symbol,
            asset_type=asset_type,
            unit=unit,
            data=data,
        )

    except Exception as error:
        return empty_asset_result(
            name,
            symbol,
            asset_type,
            unit,
            (
                f"{type(error).__name__}: "
                f"{error}"
            ),
        )


def overall_status(
    results: Dict[str, Dict[str, Any]],
) -> str:
    statuses = [
        safe_text(
            result.get("수집상태")
        )
        for result in results.values()
    ]

    normal_count = sum(
        status == "정상"
        for status in statuses
    )

    if normal_count == len(statuses):
        return "정상"

    if normal_count > 0:
        return "부분성공"

    return "실패"


def get_global_market_bundle() -> Dict[str, Any]:
    print("REQUEST GLOBAL MARKET")

    results: Dict[
        str,
        Dict[str, Any],
    ] = {}

    for name, asset_config in ASSETS.items():
        result = get_global_asset(
            name,
            asset_config,
        )

        results[name] = result

        print(
            "GLOBAL",
            name,
            result.get("수집상태"),
            result.get("현재값"),
        )

    errors = [
        {
            "자산명": name,
            "심볼": result.get("심볼", ""),
            "응답메시지": result.get(
                "응답메시지",
                "",
            ),
        }
        for name, result in results.items()
        if result.get("수집상태") != "정상"
    ]

    return {
        "전체수집상태": overall_status(
            results
        ),
        "자산": results,
        "수집오류": errors,
        "수집시각": datetime.now(
            KST
        ).isoformat(),
        "데이터출처": "Yahoo Finance Chart API",
    }
