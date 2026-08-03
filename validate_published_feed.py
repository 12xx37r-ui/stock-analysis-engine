"""Minimal integrity validation for a published general-company JSON.

This validator deliberately applies no investment, valuation, EPS, TTM,
financial-period, current-price, technical-chart, bridge-element, or Buffett
condition.  A readable JSON object passes.  Missing data is printed as warning
only and the process exits with status 0.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

VALIDATION_MODE = "general-company-lookup-unrestricted-v1.0.0"


def normalize_stock_code(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits if len(digits) == 6 else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--stock-code", required=True)
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        print("PUBLISHED FEED VALIDATION: FAIL")
        print("- 파일 없음:", path)
        return 1

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        print("PUBLISHED FEED VALIDATION: FAIL")
        print("- JSON 손상:", type(error).__name__, str(error))
        return 1

    if not isinstance(data, dict):
        print("PUBLISHED FEED VALIDATION: FAIL")
        print("- JSON 최상위 값이 객체가 아님")
        return 1

    warnings = []
    expected_code = normalize_stock_code(args.stock_code)
    payload_code = normalize_stock_code(
        data.get("KIS종목코드") or data.get("종목코드")
    )
    if not payload_code:
        warnings.append("JSON 내부 종목코드 미표기 · 요청 파일명 기준으로 게시")
    elif expected_code and payload_code != expected_code:
        warnings.append(
            f"내부 종목코드 {payload_code}와 요청코드 {expected_code} 불일치"
        )

    valuation = data.get("가치평가")
    if not isinstance(valuation, dict):
        warnings.append("가치평가 섹션 미확보")
    elif valuation.get("최종값사용가능") is not True:
        warnings.append("적정가 산출보류 또는 자료부족")

    print(
        "PUBLISHED FEED VALIDATION:",
        "PASS WITH WARNING" if warnings else "PASS",
    )
    print("- validation mode:", VALIDATION_MODE)
    print("- rule: 읽기 가능한 일반기업 JSON은 조건 없이 허용")
    for warning in dict.fromkeys(warnings):
        print("-", warning)
    return 0


if __name__ == "__main__":
    sys.exit(main())
