"""Validate the GAS-facing latest stock feed and normalized screen bridge."""

import argparse
import json
import sys
from pathlib import Path


def safe_dict(value):
    return value if isinstance(value, dict) else {}


def safe_list(value):
    return value if isinstance(value, list) else []


def fail(message, errors):
    errors.append(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--stock-code", required=True)
    args = parser.parse_args()

    path = Path(args.file)
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = []

    if str(data.get("KIS종목코드", "")).zfill(6) != args.stock_code:
        fail("종목코드 불일치", errors)

    prediction = safe_dict(data.get("주가예측"))
    if prediction.get("엔진버전") != "6.6.4-valuation-contract-v3":
        fail("엔진버전 불일치", errors)

    valuation = safe_dict(data.get("가치평가"))
    if valuation.get("가치평가계약버전") != "3.0":
        fail("가치평가 계약버전 3.0 누락", errors)
    if valuation.get("가치평가엔진버전") != "6.6.4-valuation-contract-v3":
        fail("가치평가 엔진버전 불일치", errors)
    if valuation.get("최종값사용가능") is not True:
        fail("가치평가 최종값 사용불가", errors)
    base = float(valuation.get("기본적정가") or 0)
    low = float(valuation.get("보수적적정가") or 0)
    high = float(valuation.get("성장적정가") or 0)
    if not (0 < low <= base <= high):
        fail("가치평가 범위 순서 오류", errors)
    if args.stock_code == "005930":
        if valuation.get("복합기업대용모형") is not True:
            fail("삼성전자 복합기업 대용 가치합산 미적용", errors)
        current_price = float(safe_dict(data.get("시장정보")).get("현재가") or 0)
        if current_price > 0 and base / current_price < 0.50:
            fail("삼성전자 적정가가 현재가의 50% 미만", errors)

    bridge = safe_dict(data.get("화면브리지"))
    if bridge.get("스키마버전") != "2.0":
        fail("화면브리지 스키마 2.0 누락", errors)
    if str(bridge.get("종목코드", "")).zfill(6) != args.stock_code:
        fail("화면브리지 종목코드 불일치", errors)

    technical = safe_dict(bridge.get("기술분석"))
    for key in ("일봉", "주봉", "월봉"):
        item = safe_dict(technical.get(key))
        if item.get("사용가능") is not True:
            fail(f"화면브리지 {key} 사용불가", errors)
        if int(item.get("관측수") or 0) <= 0:
            fail(f"화면브리지 {key} 관측수 없음", errors)

    forecasts = safe_dict(bridge.get("예측"))
    for key in ("단기", "중기", "장기"):
        horizon = safe_dict(forecasts.get(key))
        if not safe_list(horizon.get("요소별평가")):
            fail(f"화면브리지 {key} 요소별평가 없음", errors)
        if not 0 <= int(horizon.get("상승확률") or -1) <= 100:
            fail(f"화면브리지 {key} 상승확률 오류", errors)

    elements = safe_dict(bridge.get("요소상태"))
    required_elements = (
        "거시환경",
        "산업선행지표",
        "산업사이클",
        "뉴스",
        "기업공시",
        "외국인기관수급",
        "프로그램매매",
    )
    for key in required_elements:
        if key not in elements:
            fail(f"화면브리지 요소 누락: {key}", errors)

    if errors:
        print("PUBLISHED FEED VALIDATION: FAIL")
        for message in errors:
            print("-", message)
        return 1

    print("PUBLISHED FEED VALIDATION: PASS")
    print("- stock:", args.stock_code)
    print("- engine:", prediction.get("엔진버전"))
    print("- bridge:", bridge.get("스키마버전"), bridge.get("연결상태"))
    print("- technical observations:", {
        key: safe_dict(technical.get(key)).get("관측수")
        for key in ("일봉", "주봉", "월봉")
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
