"""Validate one GAS-facing stock JSON against the current publication contract."""

import argparse
import json
import sys
from pathlib import Path

from feed_contract import (
    EXPECTED_ENGINE_VERSION,
    inspect_published_stock,
    safe_dict,
    safe_list,
)


def fail(message, errors):
    errors.append(message)


def warn(message, warnings):
    warnings.append(message)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--stock-code", required=True)
    args = parser.parse_args()

    path = Path(args.file)
    data = json.loads(path.read_text(encoding="utf-8"))
    compatible, errors = inspect_published_stock(data, args.stock_code)
    errors = list(errors)
    warnings = []

    valuation = safe_dict(data.get("가치평가"))
    base = float(valuation.get("기본적정가") or 0)
    low = float(valuation.get("보수적적정가") or 0)
    high = float(valuation.get("성장적정가") or 0)
    valuation_usable = (
        valuation.get("최종값사용가능") is True
        and valuation.get("산출상태") == "정상"
    )
    if valuation_usable:
        if not (0 < low <= base <= high):
            fail("사용가능 가치평가의 범위 순서 오류", errors)
    else:
        stop_reasons = [
            str(item)
            for item in safe_list(
                safe_dict(valuation.get("데이터자격검사")).get("중단사유")
            )
            if str(item)
        ]
        warn(
            "가치평가 산출보류: "
            + ("; ".join(stop_reasons) or "적정가 자료 미확보"),
            warnings,
        )

    if args.stock_code == "005930" and valuation_usable:
        if valuation.get("복합기업대용모형") is not True:
            fail("삼성전자 복합기업 대용 가치합산 미적용", errors)
        current_price = float(safe_dict(data.get("시장정보")).get("현재가") or 0)
        if current_price > 0 and base / current_price < 0.50:
            fail("삼성전자 적정가가 현재가의 50% 미만", errors)

    bridge = safe_dict(data.get("화면브리지"))
    technical = safe_dict(bridge.get("기술분석"))
    for key in ("일봉", "주봉", "월봉"):
        if key not in technical:
            fail(f"화면브리지 {key} 구조 누락", errors)
            continue
        item = safe_dict(technical.get(key))
        if item.get("사용가능") is not True:
            warn(f"화면브리지 {key} 자료 미확보", warnings)
        if int(item.get("관측수") or 0) <= 0:
            warn(f"화면브리지 {key} 관측수 없음", warnings)

    forecasts = safe_dict(bridge.get("예측"))
    for key in ("단기", "중기", "장기"):
        horizon = safe_dict(forecasts.get(key))
        if not safe_list(horizon.get("요소별평가")):
            warn(f"화면브리지 {key} 요소별평가 자료 미확보", warnings)
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

    errors = list(dict.fromkeys(errors))
    warnings = list(dict.fromkeys(warnings))
    if errors or not compatible:
        print("PUBLISHED FEED VALIDATION: FAIL")
        for message in errors:
            print("-", message)
        if warnings:
            print("WARNINGS")
            for message in warnings:
                print("-", message)
        return 1

    print(
        "PUBLISHED FEED VALIDATION:",
        "PASS WITH WARNING" if warnings else "PASS",
    )
    for message in warnings:
        print("-", message)
    print("- stock:", args.stock_code)
    print("- engine:", EXPECTED_ENGINE_VERSION)
    print("- bridge:", bridge.get("스키마버전"), bridge.get("연결상태"))
    print("- technical observations:", {
        key: safe_dict(technical.get(key)).get("관측수")
        for key in ("일봉", "주봉", "월봉")
    })
    return 0


if __name__ == "__main__":
    sys.exit(main())
