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
from collectors.price import (
    apply_price_to_market,
    candidate as build_price_candidate,
    choose_candidate,
    latest_allowed_trade_date,
    market_status as price_market_status,
    normalize_yahoo_market,
    normalized_market_code,
    now_kst,
    read_price_cache,
    suffix_market,
    write_price_cache,
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


def _format_trade_date(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    if len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-":
        return text[:10]
    return fallback


def _format_trade_time(value: Any, fallback: str = "") -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if len(digits) >= 6:
        return f"{digits[:2]}:{digits[2:4]}:{digits[4:6]}"
    if len(digits) == 4:
        return f"{digits[:2]}:{digits[2:4]}:00"
    return fallback


def _market_from_kis(output: Dict[str, Any], market_code: str) -> str:
    label = str(
        output.get("rprs_mrkt_kor_name")
        or output.get("mrkt_kor_name")
        or output.get("bstp_kor_isnm")
        or ""
    ).strip().upper()
    if "KOSDAQ" in label or "코스닥" in label:
        return "KOSDAQ"
    if "KOSPI" in label or "코스피" in label or "유가증권" in label:
        return "KOSPI"
    return normalized_market_code(market_code)


def _kis_candidate(
    stock_code: str,
    market_code: str,
    output: Dict[str, Any],
) -> Dict[str, Any]:
    """Convert a KIS quote response to the common price-candidate schema.

    The function performs no network I/O.  It only normalizes the already
    collected KIS response so the shared price validator can compare it with
    DART shares and the independently collected technical close.
    """
    output = safe_dict(output)
    price = safe_float(output.get("stck_prpr"))
    volume = safe_int(output.get("acml_vol"))
    if price <= 0 or volume <= 0:
        return {}

    collected_at = now_kst()
    current_status = price_market_status(collected_at)
    fallback_date = latest_allowed_trade_date(collected_at).isoformat()
    trade_date = _format_trade_date(
        output.get("stck_bsop_date")
        or output.get("bsop_date"),
        fallback_date,
    )
    trade_time = _format_trade_time(
        output.get("stck_cntg_hour")
        or output.get("cntg_hour"),
        collected_at.strftime("%H:%M:%S") if current_status == "장중" else "15:30:00",
    )

    previous_close = safe_float(
        output.get("stck_prdy_clpr")
        or output.get("prdy_clpr")
    )
    if previous_close <= 0:
        previous_close = price - safe_float(output.get("prdy_vrss"))

    source_shares = safe_int(
        output.get("lstn_stcn")
        or output.get("stck_lstn_stcn")
        or output.get("listing_shares")
    )

    market_name = _market_from_kis(output, market_code)
    price_type = "KRX 실시간가" if current_status == "장중" and trade_date == collected_at.date().isoformat() else "KRX 종가"

    return build_price_candidate(
        stock_code,
        market=market_name or market_code,
        trading_market="KRX",
        price=price,
        price_date=trade_date,
        price_time=trade_time,
        collected_at=collected_at,
        source="한국투자증권 KIS",
        price_type=price_type,
        adjusted=False,
        volume=volume,
        market_cap=safe_float(output.get("hts_avls")),
        source_share_count=source_shares,
        exchange=market_name,
        status=current_status,
        open_price=safe_float(output.get("stck_oprc")),
        high_price=safe_float(output.get("stck_hgpr")),
        low_price=safe_float(output.get("stck_lwpr")),
        previous_close=previous_close,
    )


def parse_yahoo_market(
    symbol: str,
    data: Dict[str, Any],
    stock_code: str = "",
) -> Dict[str, Any]:
    """Parse Yahoo quote.close into the common unadjusted-price candidate.

    regularMarketPrice is used only when it is fresh and coherent with the
    timestamp-aligned quote.close.  This prevents stale/meta split artefacts
    from being published as the current price.
    """
    chart = safe_dict(data.get("chart"))
    if chart.get("error"):
        return {}

    results = safe_list(chart.get("result"))
    if not results:
        return {}

    result = safe_dict(results[0])
    meta = safe_dict(result.get("meta"))
    # Symbol/exchange mismatches are intentionally not discarded here.
    # They must reach the shared validator so diagnostics can record exactly
    # why a .KS/.KQ candidate was rejected.  Currency is still constrained.
    currency = str(meta.get("currency", "")).strip().upper()
    if currency and currency != "KRW":
        return {}

    indicators = safe_dict(result.get("indicators"))
    quotes = safe_list(indicators.get("quote"))
    quote = safe_dict(quotes[0]) if quotes else {}
    rows = quote_rows(
        result.get("timestamp"),
        quote.get("open"),
        quote.get("high"),
        quote.get("low"),
        quote.get("close"),
        quote.get("volume"),
    )
    if not rows:
        return {}

    latest = rows[-1]
    latest_ts = safe_int(latest.get("timestamp"))
    if not timestamp_is_fresh(latest_ts):
        return {}

    latest_close = safe_float(latest.get("close"))
    # The timestamp-aligned quote.close is the canonical Yahoo price.
    # regularMarketPrice is metadata and has produced stale pre-split/pre-event
    # values even when its timestamp looks recent, so it is diagnostic-only.
    regular_price = safe_float(meta.get("regularMarketPrice"))
    regular_time = unix_time(meta.get("regularMarketTime"))
    selected_ts = latest_ts
    current_price = latest_close
    if current_price <= 0 or selected_ts <= 0:
        return {}

    observed = datetime.fromtimestamp(selected_ts, tz=timezone.utc).astimezone(now_kst().tzinfo)
    volume = safe_int(latest.get("volume"))
    if volume <= 0:
        return {}

    open_price = safe_float(latest.get("open"))
    high_price = safe_float(latest.get("high"))
    low_price = safe_float(latest.get("low"))
    if open_price <= 0:
        open_price = safe_float(latest.get("open"), current_price)
    if high_price <= 0:
        high_price = safe_float(latest.get("high"), current_price)
    if low_price <= 0:
        low_price = safe_float(latest.get("low"), current_price)

    previous_close = safe_float(rows[-2].get("close")) if len(rows) >= 2 else 0.0
    if previous_close <= 0:
        previous_close = safe_float(meta.get("chartPreviousClose") or meta.get("previousClose"))

    code = str(stock_code or symbol.split(".", 1)[0]).strip().zfill(6)
    exchange = str(meta.get("exchangeName", ""))
    market_name = normalize_yahoo_market(exchange) or suffix_market(symbol)
    collected_at = now_kst()
    price_type = "KRX 종가"

    return build_price_candidate(
        code,
        market=market_name,
        trading_market="KRX",
        price=current_price,
        price_date=observed.date().isoformat(),
        price_time=observed.strftime("%H:%M:%S"),
        collected_at=collected_at,
        source="Yahoo Finance Chart API",
        price_type=price_type,
        adjusted=False,
        volume=volume,
        market_cap=safe_float(meta.get("marketCap")),
        source_share_count=safe_int(meta.get("sharesOutstanding")),
        symbol=symbol,
        exchange=exchange,
        status=price_market_status(collected_at),
        open_price=open_price,
        high_price=high_price,
        low_price=low_price,
        previous_close=previous_close,
    )


def get_yahoo_market_candidates(
    stock_code: str,
    market_code: str = "",
) -> List[Dict[str, Any]]:
    """Collect the minimum Yahoo candidates needed for a market fallback.

    When KOSPI/KOSDAQ is known, the preferred suffix is tried first and a
    coherent result stops the loop.  The alternate suffix is only queried when
    the preferred response is unusable, preventing the old unconditional
    duplicate Yahoo calls.
    """
    candidates: List[Dict[str, Any]] = []
    expected = normalized_market_code(market_code)

    for symbol in yahoo_symbols(stock_code, market_code=market_code):
        try:
            parsed = parse_yahoo_market(
                symbol,
                request_yahoo_chart(symbol),
                stock_code,
            )
        except Exception as error:
            print(
                "MARKET YAHOO CANDIDATE ERROR:",
                symbol,
                type(error).__name__,
                error,
            )
            continue

        if not parsed:
            continue

        candidates.append(parsed)
        actual = normalized_market_code(parsed.get("시장구분"))
        if expected and actual == expected:
            break

    return candidates


def get_yahoo_market_fallback(
    stock_code: str,
    market_code: str = "",
) -> Dict[str, Any]:
    """Backward-compatible view of the first collected Yahoo candidate."""
    candidates = get_yahoo_market_candidates(stock_code, market_code)
    if not candidates:
        return {"응답메시지": "Yahoo 검증 후보 없음"}

    row = candidates[0]
    price = safe_float(row.get("가격"))
    previous = safe_float(row.get("전일종가"))
    return {
        "현재가": price,
        "전일대비": price - previous if previous > 0 else 0.0,
        "등락률": ((price / previous - 1.0) * 100.0) if previous > 0 else 0.0,
        "거래량": safe_int(row.get("거래량")),
        "시가": safe_float(row.get("시가")),
        "고가": safe_float(row.get("고가")),
        "저가": safe_float(row.get("저가")),
        "시가총액": safe_float(row.get("시가총액")),
        "Yahoo심볼": str(row.get("심볼", "")),
        "Yahoo통화": "KRW",
        "Yahoo거래소": str(row.get("거래소", "")),
        "응답메시지": "",
    }


def _fundamental_share_count(fundamentals_bundle: Dict[str, Any]) -> int:
    bundle = safe_dict(fundamentals_bundle)
    share_blocks = [
        safe_dict(bundle.get("주식총수")),
        safe_dict(bundle.get("주식수")),
        safe_dict(bundle.get("shares")),
        bundle,
    ]
    keys = (
        "가치평가주식수",
        "발행주식수",
        "유통주식수",
        "sharesOutstanding",
        "상장주식수",
    )
    for block in share_blocks:
        for key in keys:
            value = safe_int(block.get(key))
            if value > 0:
                return value
    return 0


def finalize_market_data(
    market: Dict[str, Any],
    stock_code: str,
    market_code: str = "",
    fundamentals_bundle: Dict[str, Any] | None = None,
    technical_bundle: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Validate already-collected price candidates without new network calls."""
    target = dict(market or {})
    share_count = _fundamental_share_count(fundamentals_bundle or {})
    candidates = [
        dict(item)
        for item in safe_list(target.get("_가격후보"))
        if isinstance(item, dict) and item
    ]

    expected_market = normalized_market_code(market_code)
    if not expected_market and candidates:
        expected_market = normalized_market_code(candidates[0].get("시장구분"))

    selected, checked = choose_candidate(
        candidates,
        stock_code=stock_code,
        expected_market=expected_market,
        share_count=share_count,
        technical_bundle=technical_bundle or {},
    )

    if selected is None and target.get("_Yahoo재시도허용") is True:
        # KIS 후보가 재무주식수/기술종가 교차검증에서만 탈락한 경우에 한해
        # Yahoo를 한 번 보조 조회한다. 정상 KIS 또는 이미 Yahoo를 사용한 경로에서는
        # 이 호출이 발생하지 않아 평상시 외부 호출량을 늘리지 않는다.
        yahoo_candidates = get_yahoo_market_candidates(stock_code, market_code)
        if yahoo_candidates:
            retry_selected, retry_checked = choose_candidate(
                yahoo_candidates,
                stock_code=stock_code,
                expected_market=expected_market,
                share_count=share_count,
                technical_bundle=technical_bundle or {},
            )
            checked.extend(retry_checked)
            if retry_selected is not None:
                selected = retry_selected

    if selected is None:
        cache_markets = [expected_market] if expected_market else ["KOSPI", "KOSDAQ"]
        for cache_market in cache_markets:
            cached = read_price_cache(
                stock_code,
                cache_market,
                trading_market="KRX",
                share_count=share_count,
            )
            if not cached:
                continue
            cached_selected, cached_checked = choose_candidate(
                [cached],
                stock_code=stock_code,
                expected_market=cache_market,
                share_count=share_count,
                technical_bundle=technical_bundle or {},
            )
            checked.extend(cached_checked)
            if cached_selected is not None:
                selected = cached_selected
                break

    target = apply_price_to_market(target, selected, checked)
    target.pop("_가격후보", None)
    target.pop("_Yahoo재시도허용", None)

    if selected is not None:
        write_price_cache(selected, share_count)

    return target


def get_market_data(
    stock_code: str,
    market_code: str = "",
) -> Dict[str, Any]:
    """Collect current quote candidates once; validation is finalized later.

    KIS is tried first. Yahoo is contacted only when the KIS quote does not
    provide a usable positive price+volume candidate. Investor flow stays KIS
    only and is never estimated.
    """
    price = safe_dict(get_stock_price(stock_code))
    investor = safe_dict(get_investor_trade(stock_code))

    candidates: List[Dict[str, Any]] = []
    kis_candidate = _kis_candidate(stock_code, market_code, price)
    if kis_candidate:
        candidates.append(kis_candidate)
    else:
        candidates.extend(get_yahoo_market_candidates(stock_code, market_code))

    provisional = candidates[0] if candidates else {}
    provisional_price = safe_float(provisional.get("가격"))
    previous_close = safe_float(provisional.get("전일종가"))

    market = {
        "종목코드": str(stock_code).zfill(6),
        "현재가": provisional_price,
        "전일대비": provisional_price - previous_close if previous_close > 0 else safe_float(price.get("prdy_vrss")),
        "등락률": ((provisional_price / previous_close - 1.0) * 100.0) if previous_close > 0 else safe_float(price.get("prdy_ctrt")),
        "거래량": safe_int(provisional.get("거래량")),
        "시가": safe_float(provisional.get("시가")),
        "고가": safe_float(provisional.get("고가")),
        "저가": safe_float(provisional.get("저가")),
        "PER": safe_float(price.get("per")),
        "PBR": safe_float(price.get("pbr")),
        "EPS": safe_float(price.get("eps")),
        "BPS": safe_float(price.get("bps")),
        "시가총액": safe_float(provisional.get("시가총액")) or safe_float(price.get("hts_avls")),
        "수급": {
            "외국인순매수": investor.get("외국인순매수", 0),
            "기관순매수": investor.get("기관순매수", 0),
            "개인순매수": investor.get("개인순매수", 0),
        },
        "현재가수집상태": "검증대기",
        "현재가응답메시지": (
            "가격 후보 수집 완료 · 재무/기술 교차검증 대기"
            if candidates
            else "검증 가능한 최신 가격 후보 미수집"
        ),
        "데이터출처": (
            str(provisional.get("가격출처", "")) + " · 검증대기"
            if candidates
            else "현재가 후보 없음"
        ),
        "_가격후보": candidates,
        "_Yahoo재시도허용": bool(kis_candidate),
    }

    if provisional.get("심볼"):
        market["Yahoo심볼"] = str(provisional.get("심볼"))
        market["Yahoo통화"] = "KRW"
        market["Yahoo거래소"] = str(provisional.get("거래소", ""))

    print(
        "MARKET CANDIDATES:",
        stock_code,
        len(candidates),
        market["데이터출처"],
    )
    return market
