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


def yahoo_symbols(
    stock_code: str,
) -> List[str]:
    code = str(
        stock_code
    ).strip().zfill(6)

    return [
        f"{code}.KS",
        f"{code}.KQ",
    ]


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

    closes = safe_list(
        quote.get(
            "close"
        )
    )

    opens = safe_list(
        quote.get(
            "open"
        )
    )

    highs = safe_list(
        quote.get(
            "high"
        )
    )

    lows = safe_list(
        quote.get(
            "low"
        )
    )

    volumes = safe_list(
        quote.get(
            "volume"
        )
    )

    current_price = safe_float(
        meta.get(
            "regularMarketPrice"
        ),
        0.0,
    )

    if current_price <= 0:
        current_price = latest_numeric(
            closes
        )

    volume = safe_int(
        meta.get(
            "regularMarketVolume"
        ),
        0,
    )

    if volume <= 0:
        volume = latest_integer(
            volumes
        )

    open_price = safe_float(
        meta.get(
            "regularMarketOpen"
        ),
        0.0,
    )

    if open_price <= 0:
        open_price = latest_numeric(
            opens
        )

    high_price = safe_float(
        meta.get(
            "regularMarketDayHigh"
        ),
        0.0,
    )

    if high_price <= 0:
        high_price = latest_numeric(
            highs
        )

    low_price = safe_float(
        meta.get(
            "regularMarketDayLow"
        ),
        0.0,
    )

    if low_price <= 0:
        low_price = latest_numeric(
            lows
        )

    previous_close = safe_float(
        meta.get(
            "chartPreviousClose"
        )
        or meta.get(
            "previousClose"
        ),
        0.0,
    )

    if previous_close <= 0:
        valid_closes = [
            safe_float(
                value
            )
            for value in closes
            if safe_float(
                value
            ) > 0
        ]

        if len(
            valid_closes
        ) >= 2:
            previous_close = (
                valid_closes[-2]
            )

    change = (
        current_price
        - previous_close
        if (
            current_price > 0
            and previous_close > 0
        )
        else 0.0
    )

    change_rate = (
        change
        / previous_close
        * 100.0
        if previous_close > 0
        else 0.0
    )

    if (
        current_price <= 0
        or volume <= 0
    ):
        return {}

    market_cap = safe_float(
        meta.get(
            "marketCap"
        ),
        0.0,
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
) -> Dict[str, Any]:
    errors = []

    for symbol in yahoo_symbols(
        stock_code
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
                print(
                    "MARKET YAHOO FALLBACK OK:",
                    symbol,
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
                stock_code
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
