"""Validate only that the published file is readable JSON.

General-company financial lookup mode.

No company is rejected because of:
- missing or negative EPS
- missing TTM
- missing current price or volume
- missing valuation range
- valuation hold/unavailable status
- missing daily/weekly/monthly observations
- missing forecast components
- missing bridge elements
- Buffett-style screening conditions

Those are data-availability states and must be displayed by GAS, not treated as
GitHub Actions failures.
"""

import argparse
import json
import sys
from pathlib import Path


VALIDATION_MODE = "general-company-financial-unrestricted-v1"


def safe_dict(value):
    return value if isinstance(value, dict) else {}


def normalize_stock_code(value):
    text = "".join(character for character in str(value or "") if character.isdigit())
    return text if len(text) == 6 else ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--stock-code", required=True)
    args = parser.parse_args()

    path = Path(args.file)

    if not path.exists():
        print("PUBLISHED FEED VALIDATION: FAIL")
        print("- 게시 파일 없음:", path)
        return 1

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        print("PUBLISHED FEED VALIDATION: FAIL")
        print(
            "- JSON 손상:",
            type(error).__name__,
            str(error),
        )
        return 1

    if not isinstance(data, dict):
        print("PUBLISHED FEED VALIDATION: FAIL")
        print("- JSON 최상위 값이 객체가 아님")
        return 1

    expected_code = normalize_stock_code(args.stock_code)
    payload_code = normalize_stock_code(
        data.get("KIS종목코드")
        or data.get("종목코드")
    )

    warnings = []

    if not payload_code:
        warnings.append(
            "JSON 내부 종목코드 미표기 · 파일명/워크플로 종목코드로 게시"
        )
    elif expected_code and payload_code != expected_code:
        warnings.append(
            f"JSON 내부 종목코드 {payload_code}와 요청코드 "
            f"{expected_code}가 다름 · 게시 자체는 차단하지 않음"
        )

    valuation = safe_dict(data.get("가치평가"))
    qualification = safe_dict(valuation.get("데이터자격검사"))

    if valuation.get("최종값사용가능") is not True:
        warnings.append("적정가 산출보류 또는 자료부족")

    stop_reasons = qualification.get("중단사유")
    if isinstance(stop_reasons, list):
        warnings.extend(
            str(item)
            for item in stop_reasons
            if str(item)
        )

    print(
        "PUBLISHED FEED VALIDATION:",
        "PASS WITH WARNING" if warnings else "PASS",
    )
    print("- validation mode:", VALIDATION_MODE)
    print("- stock:", expected_code or args.stock_code)
    print("- rule: 모든 읽기 가능한 일반기업 JSON 게시 허용")

    for warning in dict.fromkeys(warnings):
        print("-", warning)

    return 0


if __name__ == "__main__":
    sys.exit(main())
