"""실행 시점 한국 주식 현재가 라이브 회귀검증.

고정 가격을 사용하지 않는다. 각 종목의 Yahoo 최신 timestamp-aligned quote.close와
독립 5년 일봉의 최신 종가를 다시 수집하고 가격 스키마 V3 검증을 통과하는지 확인한다.
KIS_DISABLED=1에서도 중앙 토큰 발급 API를 호출하지 않고 실행할 수 있다.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from collectors.market import finalize_market_data, get_market_data
from collectors.technical import get_stock_technical_bundle
from collectors.price import PRICE_SCHEMA_VERSION

DEFAULT_CODES = ("328130", "203650", "053300")


def load_existing_fundamentals(code: str) -> Dict[str, Any]:
    path = Path(__file__).resolve().parent / "data" / "latest" / "stocks" / f"{code}.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    value = payload.get("기업기초데이터")
    return value if isinstance(value, dict) else {}


def compact_result(code: str, market: Dict[str, Any]) -> Dict[str, Any]:
    diagnostic = market.get("가격진단") if isinstance(market.get("가격진단"), dict) else {}
    return {
        "종목코드": code,
        "시장구분": diagnostic.get("시장구분", ""),
        "최종가격": market.get("현재가", 0),
        "가격기준일": diagnostic.get("가격기준일", ""),
        "가격기준시각": diagnostic.get("가격기준시각", ""),
        "가격수집시각": diagnostic.get("가격수집시각", ""),
        "가격출처": diagnostic.get("가격출처", ""),
        "거래시장": diagnostic.get("거래시장", ""),
        "가격종류": diagnostic.get("가격종류", ""),
        "조정주가여부": diagnostic.get("조정주가여부"),
        "캐시사용여부": diagnostic.get("캐시사용여부"),
        "캐시버전": diagnostic.get("캐시버전", ""),
        "발행주식수": diagnostic.get("발행주식수", 0),
        "시가총액": diagnostic.get("시가총액", 0),
        "가격곱하기발행주식수": diagnostic.get("가격곱하기발행주식수", 0),
        "시가총액일관성결과": diagnostic.get("시가총액일관성결과", ""),
        "기업행위의심여부": diagnostic.get("기업행위의심여부"),
        "최종채택": diagnostic.get("최종채택"),
        "거부사유": diagnostic.get("거부사유", []),
        "가격스키마버전": diagnostic.get("가격스키마버전", ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("codes", nargs="*", default=list(DEFAULT_CODES))
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    results = []
    failures = []
    for raw_code in args.codes:
        code = str(raw_code).zfill(6)
        raw_market = get_market_data(code, market_code="")
        technical = get_stock_technical_bundle(code, market_code="")
        validated = finalize_market_data(
            raw_market,
            stock_code=code,
            market_code="",
            fundamentals_bundle=load_existing_fundamentals(code),
            technical_bundle=technical,
        )
        row = compact_result(code, validated)
        results.append(row)
        if row["가격스키마버전"] != PRICE_SCHEMA_VERSION or row["최종채택"] is not True:
            failures.append(code)

    payload = {
        "가격스키마버전": PRICE_SCHEMA_VERSION,
        "고정가격사용": False,
        "결과": results,
        "실패종목": failures,
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
