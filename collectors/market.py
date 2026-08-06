"""
국내주식 시장 데이터 수집기 V1.1

우선순위
1. 한국투자증권 KIS 현재가·수급
2. KIS 현재가 또는 거래량이 비정상일 때 Yahoo Chart API로
   현재가·OHLCV를 자동 보완
3. 투자자 수급은 KIS 값만 사용하며 임의로 추정하지 않음

기존 인터페이스 유지
- get_market_data(stock_code)
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import requests

from collectors.kis import (
    get_investor_trade,
    get_stock_price,
)


YAHOO_CHART_URL = (
    "https://query1.finance.yahoo.com/"
    "v8/finance/chart/{symbol}"
)

YAHOO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
}

YAHOO_MAX_PRICE_AGE_DAYS = 10
YAHOO_MAX_META_CLOSE_GAP_RATIO = 0.35


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        if value in (
            None,
            "",
        ):
            return default

        return float(
            str(value)
            .replace(",", "")
            .strip()
        )

    except (
        TypeError,
        ValueError,
    ):
        return default


def safe_int(
    value: Any,
    default: int = 0,
) -> int:
    try:
        if value in (
            None,
            "",
        ):
            return default

        return int(
            float(
                str(value)
                .replace(",", "")
                .strip()
            )
        )

    except (
        TypeError,
        ValueError,
    ):
        return default


def safe_dict(
    value: Any,
) -> Dict[str, Any]:
    if isinstance(
        value,
        dict,
    ):
        return value

    return {}


def safe_list(
    value: Any,
) -> List[Any]:
    if isinstance(
        value,
        list,
    ):
        return value

    return []


def latest_numeric(
    values: Any,
    default: float = 0.0,
) -> float:
    rows = safe_list(
        values
    )

    for value in reversed(
        rows
    ):
        numeric = safe_float(
            value,
            0.0,
        )

        if numeric > 0:
            return numeric

    return default


def latest_integer(
    values: Any,
    default: int = 0,
) -> int:
    rows = safe_list(
        values
    )

    for value in reversed(
        rows
    ):
        numeric = safe_int(
            value,
            0,
        )

        if numeric > 0:
            return numeric

    return default


def normalize_yahoo_market_code(
    market_code: str,
) -> str:
    value = str(
        market_code
        or ""
    ).strip().upper()

    if value in {
        "KQ",
        "Q",
        "KOSDAQ",
        "KOSDAQ GLOBAL",
    }:
        return "KQ"

    if value in {
        "KS",
        "Y",
        "KOSPI",
        "KSE",
    }:
        return "KS"

    return ""


def yahoo_symbols(
    stock_code: str,
    market_code: str = "",
) -> List[str]:
    code = str(
        stock_code
    ).strip().zfill(6)

    normalized_market = (
        normalize_yahoo_market_code(
            market_code
        )
    )

    if normalized_market == "KQ":
        return [
            f"{code}.KQ",
            f"{code}.KS",
        ]

    if normalized_market == "KS":
        return [
            f"{code}.KS",
            f"{code}.KQ",
        ]

    return [
        f"{code}.KS",
        f"{code}.KQ",
    ]


def unix_time(
    value: Any,
) -> int:
    return safe_int(
        value,
        0,
    )


def timestamp_is_fresh(
    timestamp: Any,
    maximum_age_days: int = YAHOO_MAX_PRICE_AGE_DAYS,
) -> bool:
    seconds = unix_time(
        timestamp
    )

    if seconds <= 0:
        return False

    observed = datetime.fromtimestamp(
        seconds,
        tz=timezone.utc,
    )
    now = datetime.now(
        timezone.utc
    )

    if observed > now + timedelta(
        days=1
    ):
        return False

    return (
        now - observed
        <= timedelta(
            days=max(
                1,
                maximum_age_days,
            )
        )
    )


def value_at(
    values: Any,
    index: int,
    default: float = 0.0,
) -> float:
    rows = safe_list(
        values
    )

    if (
        index < 0
        or index >= len(rows)
    ):
        return default

    return safe_float(
        rows[index],
        default,
    )


def integer_at(
    values: Any,
    index: int,
    default: int = 0,
) -> int:
    rows = safe_list(
        values
    )

    if (
        index < 0
        or index >= len(rows)
    ):
        return default

    return safe_int(
        rows[index],
        default,
    )


def quote_rows(
    timestamps: Any,
    opens: Any,
    highs: Any,
    lows: Any,
    closes: Any,
    volumes: Any,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    for index, timestamp in enumerate(
        safe_list(
            timestamps
        )
    ):
        close = value_at(
            closes,
            index,
        )
        seconds = unix_time(
            timestamp
        )

        if (
            seconds <= 0
            or close <= 0
        ):
            continue

        rows.append({
            "timestamp": seconds,
            "open": value_at(
                opens,
                index,
                close,
            ),
            "high": value_at(
                highs,
                index,
                close,
            ),
            "low": value_at(
                lows,
                index,
                close,
            ),
            "close": close,
            "volume": integer_at(
                volumes,
                index,
                0,
            ),
        })

    rows.sort(
        key=lambda item: item[
            "timestamp"
        ]
    )

    return rows


def yahoo_symbol_metadata_valid(
    symbol: str,
    meta: Dict[str, Any],
) -> bool:
    response_symbol = str(
        meta.get(
            "symbol",
            "",
        )
    ).strip().upper()

    if (
        response_symbol
        and response_symbol != symbol.upper()
    ):
        return False

    currency = str(
        meta.get(
            "currency",
            "",
        )
    ).strip().upper()

    if (
        currency
        and currency != "KRW"
    ):
        return False

    exchange = str(
        meta.get(
            "exchangeName",
            "",
        )
    ).strip().upper()

    if symbol.upper().endswith(
        ".KQ"
    ):
        return (
            not exchange
            or exchange in {
                "KOE",
                "KOSDAQ",
            }
        )

    if symbol.upper().endswith(
        ".KS"
    ):
        return (
            not exchange
            or exchange in {
                "KSE",
                "KSC",
                "KOSPI",
            }
        )

    return False

def request_yahoo_chart(
    symbol: str,
) -> Dict[str, Any]:
    url = YAHOO_CHART_URL.format(
        symbol=symbol
    )

    response = requests.get(
        url,
        headers=YAHOO_HEADERS,
        params={
            "range": "5d",
            "interval": "1d",
            "includePrePost": "false",
            "events": "div,splits",
        },
        timeout=20,
    )

    response.raise_for_status()

    data = response.json()

    if not isinstance(
        data,
        dict,
    ):
        raise RuntimeError(
            "Yahoo 응답 형식 오류"
        )

    return data


def parse_yahoo_market(
    symbol: str,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    chart = safe_dict(
        data.get(
            "chart"
        )
    )

    if chart.get(
        "error"
    ):
        return {}

    results = safe_list(
        chart.get(
            "result"
        )
    )

    if not results:
        return {}

    result = safe_dict(
        results[0]
    )
    meta = safe_dict(
        result.get(
            "meta"
        )
    )

    if not yahoo_symbol_metadata_valid(
        symbol,
        meta,
    ):
        return {}

    indicators = safe_dict(
        result.get(
            "indicators"
        )
    )
    quotes = safe_list(
        indicators.get(
            "quote"
        )
    )
    quote = (
        safe_dict(
            quotes[0]
        )
        if quotes
        else {}
    )

    rows = quote_rows(
        result.get(
            "timestamp"
        ),
        quote.get(
            "open"
        ),
        quote.get(
            "high"
        ),
        quote.get(
            "low"
        ),
        quote.get(
            "close"
        ),
        quote.get(
            "volume"
        ),
    )

    if not rows:
        return {}

    latest = rows[-1]

    if not timestamp_is_fresh(
        latest.get(
            "timestamp"
        )
    ):
        return {}

    latest_close = safe_float(
        latest.get(
            "close"
        )
    )
    regular_price = safe_float(
        meta.get(
            "regularMarketPrice"
        )
    )
    regular_time = unix_time(
        meta.get(
            "regularMarketTime"
        )
    )

    use_regular_price = (
        regular_price > 0
        and timestamp_is_fresh(
            regular_time
        )
    )

    if (
        use_regular_price
        and latest_close > 0
    ):
        price_gap_ratio = abs(
            regular_price
            / latest_close
            - 1.0
        )

        if (
            price_gap_ratio
            > YAHOO_MAX_META_CLOSE_GAP_RATIO
        ):
            use_regular_price = False

        if (
            regular_time
            < safe_int(
                latest.get(
                    "timestamp"
                )
            ) - 18 * 60 * 60
        ):
            use_regular_price = False

    current_price = (
        regular_price
        if use_regular_price
        else latest_close
    )

    if current_price <= 0:
        return {}

    volume = (
        safe_int(
            meta.get(
                "regularMarketVolume"
            )
        )
        if use_regular_price
        else 0
    )

    if volume <= 0:
        volume = safe_int(
            latest.get(
                "volume"
            )
        )

    if volume <= 0:
        return {}

    open_price = (
        safe_float(
            meta.get(
                "regularMarketOpen"
            )
        )
        if use_regular_price
        else 0.0
    )
    high_price = (
        safe_float(
            meta.get(
                "regularMarketDayHigh"
            )
        )
        if use_regular_price
        else 0.0
    )
    low_price = (
        safe_float(
            meta.get(
                "regularMarketDayLow"
            )
        )
        if use_regular_price
        else 0.0
    )

    if open_price <= 0:
        open_price = safe_float(
            latest.get(
                "open"
            ),
            current_price,
        )
    if high_price <= 0:
        high_price = safe_float(
            latest.get(
                "high"
            ),
            current_price,
        )
    if low_price <= 0:
        low_price = safe_float(
            latest.get(
                "low"
            ),
            current_price,
        )

    previous_close = (
        safe_float(
            rows[-2].get(
                "close"
            )
        )
        if len(rows) >= 2
        else 0.0
    )

    if (
        previous_close <= 0
        and use_regular_price
    ):
        previous_close = safe_float(
            meta.get(
                "chartPreviousClose"
            )
            or meta.get(
                "previousClose"
            )
        )

    change = (
        current_price
        - previous_close
        if previous_close > 0
        else 0.0
    )
    change_rate = (
        change
        / previous_close
        * 100.0
        if previous_close > 0
        else 0.0
    )

    market_cap = safe_float(
        meta.get(
            "marketCap"
        )
    )

    return {
        "현재가": current_price,
        "전일대비": change,
        "등락률": change_rate,
        "거래량": volume,
        "시가": open_price,
        "고가": high_price,
        "저가": low_price,
        "시가총액": market_cap,
        "Yahoo심볼": symbol,
        "Yahoo통화": str(
            meta.get(
                "currency",
                "",
            )
        ),
        "Yahoo거래소": str(
            meta.get(
                "exchangeName",
                "",
            )
        ),
    }

def get_yahoo_market_fallback(
    stock_code: str,
    market_code: str = "",
) -> Dict[str, Any]:
    errors = []
    candidates: List[Dict[str, Any]] = []
    normalized_market = normalize_yahoo_market_code(
        market_code
    )

    for symbol in yahoo_symbols(
        stock_code,
        market_code=market_code,
    ):
        try:
            data = request_yahoo_chart(
                symbol
            )

            parsed = parse_yahoo_market(
                symbol,
                data,
            )

            if parsed:
                candidates.append(
                    parsed
                )

                if normalized_market:
                    break

                continue

            errors.append(
                f"{symbol}: 유효가격 없음"
            )

        except Exception as error:
            errors.append(
                (
                    f"{symbol}: "
                    f"{type(error).__name__}: "
                    f"{error}"
                )
            )

    if len(candidates) == 1:
        parsed = candidates[0]
        print(
            "MARKET YAHOO FALLBACK OK:",
            parsed.get(
                "Yahoo심볼"
            ),
            parsed.get(
                "현재가"
            ),
            parsed.get(
                "거래량"
            ),
        )
        parsed[
            "응답메시지"
        ] = ""
        return parsed

    if len(candidates) > 1:
        errors.append(
            "시장구분 미확정 상태에서 .KS와 .KQ가 모두 응답하여 오채택 방지를 위해 거부"
        )

    print(
        "MARKET YAHOO FALLBACK FAILED:",
        " / ".join(
            errors
        ),
    )

    return {
        "응답메시지": (
            " / ".join(
                errors
            )
        ),
    }


def get_market_data(
    stock_code: str,
    market_code: str = "",
) -> Dict[str, Any]:
    price = safe_dict(
        get_stock_price(
            stock_code
        )
    )

    investor = safe_dict(
        get_investor_trade(
            stock_code
        )
    )

    market = {
        "현재가": safe_float(
            price.get(
                "stck_prpr"
            )
        ),
        "전일대비": safe_float(
            price.get(
                "prdy_vrss"
            )
        ),
        "등락률": safe_float(
            price.get(
                "prdy_ctrt"
            )
        ),
        "거래량": safe_int(
            price.get(
                "acml_vol"
            )
        ),
        "시가": safe_float(
            price.get(
                "stck_oprc"
            )
        ),
        "고가": safe_float(
            price.get(
                "stck_hgpr"
            )
        ),
        "저가": safe_float(
            price.get(
                "stck_lwpr"
            )
        ),
        "PER": safe_float(
            price.get(
                "per"
            )
        ),
        "PBR": safe_float(
            price.get(
                "pbr"
            )
        ),
        "EPS": safe_float(
            price.get(
                "eps"
            )
        ),
        "BPS": safe_float(
            price.get(
                "bps"
            )
        ),
        "시가총액": safe_float(
            price.get(
                "hts_avls"
            )
        ),
        "수급": {
            "외국인순매수": (
                investor.get(
                    "외국인순매수",
                    0,
                )
            ),
            "기관순매수": (
                investor.get(
                    "기관순매수",
                    0,
                )
            ),
            "개인순매수": (
                investor.get(
                    "개인순매수",
                    0,
                )
            ),
        },
        "현재가수집상태": (
            "정상"
            if (
                safe_float(
                    price.get(
                        "stck_prpr"
                    )
                ) > 0
                and safe_int(
                    price.get(
                        "acml_vol"
                    )
                ) > 0
            )
            else "실패"
        ),
        "현재가응답메시지": "",
        "데이터출처": (
            "한국투자증권 KIS"
        ),
    }

    if (
        market[
            "현재가"
        ] <= 0
        or market[
            "거래량"
        ] <= 0
    ):
        print(
            "MARKET KIS INVALID:",
            stock_code,
            market[
                "현재가"
            ],
            market[
                "거래량"
            ],
        )

        yahoo = (
            get_yahoo_market_fallback(
                stock_code,
                market_code=market_code,
            )
        )

        if (
            safe_float(
                yahoo.get(
                    "현재가"
                )
            ) > 0
            and safe_int(
                yahoo.get(
                    "거래량"
                )
            ) > 0
        ):
            for key in (
                "현재가",
                "전일대비",
                "등락률",
                "거래량",
                "시가",
                "고가",
                "저가",
            ):
                market[
                    key
                ] = yahoo[
                    key
                ]

            if (
                market[
                    "시가총액"
                ] <= 0
                and safe_float(
                    yahoo.get(
                        "시가총액"
                    )
                ) > 0
            ):
                market[
                    "시가총액"
                ] = yahoo[
                    "시가총액"
                ]

            market[
                "Yahoo심볼"
            ] = yahoo.get(
                "Yahoo심볼",
                "",
            )

            market[
                "Yahoo통화"
            ] = yahoo.get(
                "Yahoo통화",
                "",
            )

            market[
                "Yahoo거래소"
            ] = yahoo.get(
                "Yahoo거래소",
                "",
            )

            market[
                "현재가수집상태"
            ] = "보완성공"

            market[
                "현재가응답메시지"
            ] = (
                "KIS 현재가·거래량이 비어 "
                "Yahoo Chart API로 보완"
            )

            market[
                "데이터출처"
            ] = (
                "한국투자증권 KIS "
                "+ Yahoo Finance 보완"
            )

        else:
            market[
                "현재가응답메시지"
            ] = (
                "KIS 현재가·거래량 실패 / "
                "Yahoo 보완도 실패: "
                + str(
                    yahoo.get(
                        "응답메시지",
                        "",
                    )
                )
            )

    print(
        "MARKET RESULT:",
        stock_code,
        market[
            "현재가수집상태"
        ],
        market[
            "현재가"
        ],
        market[
            "거래량"
        ],
        market[
            "데이터출처"
        ],
    )

    return market
