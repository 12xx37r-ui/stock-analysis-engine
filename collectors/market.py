"""Validated Korean stock market data collector V3.

Price-source order remains KIS then existing Yahoo fallback.  This collector
never issues or stores KIS tokens; it only calls the existing central KIS
collector.  Current-price candidates are retained until fundamentals and the
technical bundle are available, then ``finalize_market_data`` performs the
freshness/market/corporate-action checks.
"""
from __future__ import annotations

from datetime import datetime, time
from typing import Any, Dict, List, Optional

import requests

from collectors.kis import get_investor_trade, get_stock_price
from collectors.price import (
    KST,
    PRICE_SCHEMA_VERSION,
    apply_price_to_market,
    candidate,
    choose_candidate,
    latest_allowed_trade_date,
    market_status,
    normalize_yahoo_market,
    now_kst,
    parse_date,
    parse_datetime,
    read_price_cache,
    safe_dict,
    safe_float,
    safe_int,
    safe_list,
    suffix_market,
    write_price_cache,
)

YAHOO_CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
YAHOO_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
}


def latest_numeric(values: Any, default: float = 0.0) -> float:
    """Compatibility helper for non-price OHLC fields only."""
    for value in reversed(safe_list(values)):
        numeric = safe_float(value)
        if numeric > 0:
            return numeric
    return default


def latest_integer(values: Any, default: int = 0) -> int:
    for value in reversed(safe_list(values)):
        numeric = safe_int(value)
        if numeric > 0:
            return numeric
    return default


def yahoo_symbols(stock_code: str, market_code: str = "") -> List[str]:
    code = str(stock_code).strip().zfill(6)
    market = str(market_code or "").strip().upper()
    if market in {"Q", "KQ", "KOSDAQ", "KOE"}:
        return [f"{code}.KQ", f"{code}.KS"]
    if market in {"K", "P", "KS", "KOSPI", "KSC", "KSE"}:
        return [f"{code}.KS", f"{code}.KQ"]
    # Both are requested, but the exchange/suffix match is validated later.
    return [f"{code}.KS", f"{code}.KQ"]


def request_yahoo_chart(symbol: str) -> Dict[str, Any]:
    response = requests.get(
        YAHOO_CHART_URL.format(symbol=symbol),
        headers=YAHOO_HEADERS,
        params={
            "range": "10d",
            "interval": "1d",
            "includePrePost": "false",
            "events": "div,splits",
        },
        timeout=20,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise RuntimeError("Yahoo 응답 형식 오류")
    return data


def _row_value(values: List[Any], index: int) -> float:
    return safe_float(values[index]) if 0 <= index < len(values) else 0.0


def _row_int(values: List[Any], index: int) -> int:
    return safe_int(values[index]) if 0 <= index < len(values) else 0


def parse_yahoo_market(
    symbol: str,
    data: Dict[str, Any],
    stock_code: str = "",
) -> Dict[str, Any]:
    """Build a non-adjusted Yahoo quote candidate aligned to its timestamp.

    ``regularMarketPrice`` and ``chartPreviousClose`` are never selected as the
    current price.  The quote ``close`` array is non-adjusted, and the chosen
    row must have its own timestamp and volume.
    """
    chart = safe_dict(data.get("chart"))
    if chart.get("error"):
        return {}
    results = safe_list(chart.get("result"))
    if not results:
        return {}
    result = safe_dict(results[0])
    meta = safe_dict(result.get("meta"))
    indicators = safe_dict(result.get("indicators"))
    quotes = safe_list(indicators.get("quote"))
    quote = safe_dict(quotes[0]) if quotes else {}
    timestamps = safe_list(result.get("timestamp"))
    closes = safe_list(quote.get("close"))
    volumes = safe_list(quote.get("volume"))
    opens = safe_list(quote.get("open"))
    highs = safe_list(quote.get("high"))
    lows = safe_list(quote.get("low"))

    # Use only the latest timestamped row. Do not walk back through months of
    # positive values and promote an old row to current price.
    latest_index = min(len(timestamps), len(closes), len(volumes)) - 1
    if latest_index < 0:
        return {}
    row_timestamp = safe_int(timestamps[latest_index])
    close = _row_value(closes, latest_index)
    volume = _row_int(volumes, latest_index)
    if row_timestamp <= 0 or close <= 0 or volume <= 0:
        return {}

    row_datetime = parse_datetime(row_timestamp)
    if row_datetime is None:
        return {}
    exchange_name = str(meta.get("exchangeName", ""))
    actual_market = normalize_yahoo_market(exchange_name) or suffix_market(symbol)

    regular_time = parse_datetime(meta.get("regularMarketTime"))
    regular_price = safe_float(meta.get("regularMarketPrice"))
    regular_time_matches = bool(regular_time and regular_time.date() == row_datetime.date())
    regular_price_matches = bool(
        regular_price > 0 and abs(regular_price / close - 1.0) <= 0.005
    )
    if regular_time_matches and regular_price_matches:
        basis_time = regular_time.strftime("%H:%M:%S")
        price_type = "장중 체결가" if market_status(regular_time) == "장중" else "KRX 종가"
    else:
        basis_time = "15:30:00"
        price_type = "KRX 종가"

    previous_close = safe_float(meta.get("chartPreviousClose") or meta.get("previousClose"))
    if previous_close <= 0 and latest_index > 0:
        previous_close = _row_value(closes, latest_index - 1)

    market_cap = safe_float(meta.get("marketCap"))
    source_shares = safe_int(meta.get("sharesOutstanding"))
    return candidate(
        stock_code or str(symbol).split(".")[0],
        market=actual_market,
        trading_market="KRX",
        price=close,
        price_date=row_datetime.date(),
        price_time=basis_time,
        collected_at=now_kst(),
        source="Yahoo Finance Chart API",
        price_type=price_type,
        adjusted=False,
        volume=volume,
        market_cap=market_cap,
        source_share_count=source_shares,
        symbol=symbol,
        exchange=exchange_name,
        status=market_status(),
        open_price=_row_value(opens, latest_index),
        high_price=_row_value(highs, latest_index),
        low_price=_row_value(lows, latest_index),
        previous_close=previous_close,
    )


def get_yahoo_market_candidates(stock_code: str, market_code: str = "") -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    errors: List[str] = []
    for symbol in yahoo_symbols(stock_code, market_code):
        try:
            parsed = parse_yahoo_market(symbol, request_yahoo_chart(symbol), stock_code)
            if parsed:
                candidates.append(parsed)
                print(
                    "MARKET YAHOO CANDIDATE:",
                    symbol,
                    parsed.get("가격"),
                    parsed.get("가격기준일"),
                    parsed.get("거래소"),
                )
            else:
                errors.append(f"{symbol}: 최신 timestamp/Close/거래량 후보 없음")
        except Exception as error:
            errors.append(f"{symbol}: {type(error).__name__}: {error}")
    if errors:
        print("MARKET YAHOO DIAGNOSTIC:", " / ".join(errors))
    return candidates


def get_yahoo_market_fallback(stock_code: str, market_code: str = "") -> Dict[str, Any]:
    """Backward-compatible wrapper. Returns the first raw candidate only."""
    rows = get_yahoo_market_candidates(stock_code, market_code)
    return rows[0] if rows else {"응답메시지": "Yahoo 최신 비조정 가격 후보 없음"}


def _kis_candidate(stock_code: str, market_code: str, output: Dict[str, Any]) -> Dict[str, Any]:
    price = safe_float(output.get("stck_prpr"))
    volume = safe_int(output.get("acml_vol"))
    if price <= 0 or volume <= 0:
        return {}
    collected = now_kst()
    status = market_status(collected)
    raw_date = str(output.get("stck_bsop_date") or output.get("bsop_date") or "").strip()
    trade_date = parse_date(raw_date) or latest_allowed_trade_date(collected)
    raw_time = str(
        output.get("stck_cntg_hour")
        or output.get("aspr_acpt_hour")
        or output.get("bsop_hour")
        or ""
    ).strip().replace(":", "")
    response_time = (
        f"{raw_time[0:2]}:{raw_time[2:4]}:{raw_time[4:6]}"
        if len(raw_time) >= 6 and raw_time[:6].isdigit()
        else ""
    )
    price_type = "장중 체결가" if status == "장중" else "KRX 종가"
    basis_time = response_time or (
        collected.strftime("%H:%M:%S") if status == "장중" else "15:30:00"
    )
    market_name = str(
        output.get("rprs_mrkt_kor_name")
        or output.get("mrkt_kor_name")
        or ""
    )
    inferred_market = (
        "KOSDAQ"
        if "코스닥" in market_name
        else "KOSPI"
        if ("코스피" in market_name or "유가" in market_name)
        else market_code
    )
    return candidate(
        stock_code,
        market=inferred_market,
        trading_market="KRX",
        price=price,
        price_date=trade_date,
        price_time=basis_time,
        collected_at=collected,
        source="한국투자증권 KIS",
        price_type=price_type,
        adjusted=False,
        volume=volume,
        market_cap=safe_float(output.get("hts_avls")),
        source_share_count=safe_int(output.get("lstn_stcn")),
        status=status,
        open_price=safe_float(output.get("stck_oprc")),
        high_price=safe_float(output.get("stck_hgpr")),
        low_price=safe_float(output.get("stck_lwpr")),
        previous_close=(
            price - safe_float(output.get("prdy_vrss"))
            if safe_float(output.get("prdy_vrss"))
            else 0.0
        ),
    )


def get_market_data(stock_code: str, market_code: str = "") -> Dict[str, Any]:
    # Existing central manager only. No token issuance/storage logic exists here.
    price_output = safe_dict(get_stock_price(stock_code))
    investor = safe_dict(get_investor_trade(stock_code))
    collected_candidates: List[Dict[str, Any]] = []
    kis_candidate = _kis_candidate(stock_code, market_code, price_output)
    if kis_candidate:
        collected_candidates.append(kis_candidate)
    else:
        print(
            "MARKET KIS INVALID:",
            stock_code,
            safe_float(price_output.get("stck_prpr")),
            safe_int(price_output.get("acml_vol")),
        )

    # Collect both suffixes. A wrong .KS/.KQ response cannot win because final
    # validation checks symbol suffix, exchangeName, and expected market.
    collected_candidates.extend(get_yahoo_market_candidates(stock_code, market_code))

    return {
        "종목코드": str(stock_code).zfill(6),
        "현재가": safe_float(price_output.get("stck_prpr")),
        "전일대비": safe_float(price_output.get("prdy_vrss")),
        "등락률": safe_float(price_output.get("prdy_ctrt")),
        "거래량": safe_int(price_output.get("acml_vol")),
        "시가": safe_float(price_output.get("stck_oprc")),
        "고가": safe_float(price_output.get("stck_hgpr")),
        "저가": safe_float(price_output.get("stck_lwpr")),
        "PER": safe_float(price_output.get("per")),
        "PBR": safe_float(price_output.get("pbr")),
        "EPS": safe_float(price_output.get("eps")),
        "BPS": safe_float(price_output.get("bps")),
        "시가총액": safe_float(price_output.get("hts_avls")),
        "수급": {
            "외국인순매수": investor.get("외국인순매수", 0),
            "기관순매수": investor.get("기관순매수", 0),
            "개인순매수": investor.get("개인순매수", 0),
        },
        "현재가수집상태": "검증대기",
        "현재가응답메시지": "가격 후보 수집 완료 · 재무/기술 교차검증 대기",
        "데이터출처": "가격 후보 검증 전",
        "가격스키마버전": PRICE_SCHEMA_VERSION,
        "_가격후보": collected_candidates,
    }


def _share_count(fundamentals_bundle: Dict[str, Any]) -> int:
    shares = safe_dict(safe_dict(fundamentals_bundle).get("주식총수"))
    return safe_int(
        shares.get("가치평가주식수")
        or shares.get("유통주식수")
        or shares.get("발행주식수")
    )


def _infer_expected_market(candidates: List[Dict[str, Any]], fallback: str) -> str:
    verified_markets: List[str] = []
    for row in candidates:
        symbol = str(row.get("심볼", ""))
        suffix = suffix_market(symbol)
        exchange_market = normalize_yahoo_market(row.get("거래소"))
        if suffix and exchange_market and suffix == exchange_market:
            verified_markets.append(exchange_market)
    unique = list(dict.fromkeys(verified_markets))
    if len(unique) == 1:
        return unique[0]
    direct = [
        str(row.get("시장구분", ""))
        for row in candidates
        if not row.get("심볼") and str(row.get("시장구분", ""))
    ]
    if direct:
        return direct[0]
    return fallback


def finalize_market_data(
    market: Dict[str, Any],
    stock_code: str,
    market_code: str,
    fundamentals_bundle: Optional[Dict[str, Any]],
    technical_bundle: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    target = dict(market or {})
    candidates = [row for row in safe_list(target.pop("_가격후보", [])) if isinstance(row, dict)]
    shares = _share_count(fundamentals_bundle or {})
    expected_market = _infer_expected_market(candidates, market_code)

    # A KIS current-price row may not expose its market name. Once Yahoo's
    # symbol/exchange pair resolves the listing market, use that classification
    # for validation without changing the KIS price itself.
    for row in candidates:
        if not row.get("심볼") and not str(row.get("시장구분", "")):
            row["시장구분"] = expected_market

    cached = read_price_cache(
        stock_code,
        expected_market,
        trading_market="KRX",
        share_count=shares,
    )
    if cached:
        candidates.append(cached)

    selected, checked = choose_candidate(
        candidates,
        stock_code=stock_code,
        expected_market=expected_market,
        share_count=shares,
        technical_bundle=technical_bundle or {},
    )
    result = apply_price_to_market(target, selected, checked)
    result["가격스키마버전"] = PRICE_SCHEMA_VERSION
    if selected:
        write_price_cache(selected, shares)
    print(
        "MARKET RESULT:",
        stock_code,
        result.get("현재가수집상태"),
        result.get("현재가"),
        result.get("가격기준일", ""),
        result.get("데이터출처"),
    )
    return result
