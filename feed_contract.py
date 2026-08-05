"""GAS-facing published-feed contract and compatibility checks.

The valuation engine and the published cache are separate concerns.  A stock
file is eligible for the active latest index only when it was produced by the
current engine/contract/profile and contains a coherent qualification result.
Older files may remain on disk so the refresh workflow can discover and rebuild
them, but they must not be ranked or advertised as active data.
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

EXPECTED_ENGINE_VERSION = "6.8.0-valuation-contract-v4"
EXPECTED_VALUATION_CONTRACT = "4.0"
EXPECTED_INDUSTRY_PROFILE = "3.0.0"
EXPECTED_BRIDGE_SCHEMA = "2.0"
EXPECTED_VALUATION_MODEL_REVISION = "future-growth-v1.1.0-price-independent"
EXPECTED_PRICE_SCHEMA = "3.0.0"


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def stock_code_of(stock: Dict[str, Any], fallback: str = "") -> str:
    return str(stock.get("KIS종목코드", fallback)).zfill(6)


def inspect_published_stock(stock: Dict[str, Any], expected_code: str = "") -> Tuple[bool, List[str]]:
    """Return whether a stock file is eligible for the active latest index."""
    reasons: List[str] = []
    code = stock_code_of(stock, expected_code)

    if len(code) != 6 or not code.isdigit():
        reasons.append("종목코드 오류")
    if expected_code and code != str(expected_code).zfill(6):
        reasons.append("종목코드 불일치")

    prediction = safe_dict(stock.get("주가예측"))
    valuation = safe_dict(stock.get("가치평가"))
    qualification = safe_dict(valuation.get("데이터자격검사"))
    bridge = safe_dict(stock.get("화면브리지"))
    market = safe_dict(stock.get("시장정보"))
    price_diagnostic = safe_dict(market.get("가격진단"))

    if str(price_diagnostic.get("가격스키마버전", "")) != EXPECTED_PRICE_SCHEMA:
        reasons.append("현재가 검증 스키마 불일치")
    elif price_diagnostic.get("최종채택") is True:
        if float(market.get("현재가") or 0) <= 0:
            reasons.append("현재가 채택 상태인데 가격 없음")
        if price_diagnostic.get("조정주가여부") is not False:
            reasons.append("현재가에 조정주가 사용")
    elif price_diagnostic.get("최종채택") is False:
        if float(market.get("현재가") or 0) > 0:
            reasons.append("현재가 거부 상태인데 가격이 남아 있음")
        if not safe_list(price_diagnostic.get("거부사유")):
            reasons.append("현재가 거부 사유 누락")
    else:
        reasons.append("현재가 최종 검증상태 누락")

    if prediction.get("엔진버전") != EXPECTED_ENGINE_VERSION:
        reasons.append("주가예측 엔진버전 불일치")
    if valuation.get("가치평가엔진버전") != EXPECTED_ENGINE_VERSION:
        reasons.append("가치평가 엔진버전 불일치")
    if str(valuation.get("가치평가계약버전", "")) != EXPECTED_VALUATION_CONTRACT:
        reasons.append("가치평가 계약버전 불일치")
    if str(valuation.get("산업프로필버전", "")) != EXPECTED_INDUSTRY_PROFILE:
        reasons.append("산업 프로필 버전 불일치")
    if str(valuation.get("가치평가모형개정버전", "")) != EXPECTED_VALUATION_MODEL_REVISION:
        reasons.append("가치평가 모형개정버전 불일치")
    future_model = safe_dict(valuation.get("미래성장모형"))
    if not future_model:
        reasons.append("미래성장모형 상태 누락")
    elif future_model.get("사용가능") is True and future_model.get("현재가미사용") is not True:
        reasons.append("미래성장모형 현재가 비사용 보증 누락")
    elif future_model.get("사용가능") is not True and not safe_list(future_model.get("차단사유")):
        reasons.append("미래성장모형 미사용 사유 누락")

    if bridge.get("스키마버전") != EXPECTED_BRIDGE_SCHEMA:
        reasons.append("화면브리지 스키마 불일치")
    if stock_code_of(bridge, bridge.get("종목코드", "")) != code:
        # stock_code_of reads KIS종목코드 first, while bridge normally exposes 종목코드.
        bridge_code = str(bridge.get("종목코드", "")).zfill(6)
        if bridge_code != code:
            reasons.append("화면브리지 종목코드 불일치")

    if not qualification:
        reasons.append("데이터자격검사 누락")
    else:
        usable = valuation.get("최종값사용가능") is True
        passed = qualification.get("통과") is True
        blocked_reasons = [str(item) for item in safe_list(qualification.get("중단사유")) if str(item)]
        if usable and not passed:
            reasons.append("최종값 사용가능인데 데이터자격검사 미통과")
        if not usable and (passed or not blocked_reasons):
            reasons.append("산출보류 자격상태 또는 중단사유 불일치")

    return (not reasons, list(dict.fromkeys(reasons)))
