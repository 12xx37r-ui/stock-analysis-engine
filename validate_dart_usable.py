"""Validate whether a generated stock result is safe to publish.

General financial analysis mode.

Exit codes:
  0  usable (including incomplete valuation warning)
  10 retryable OpenDART collection failure
  20 invalid contract failure
"""

import argparse
import json
from pathlib import Path


RETRYABLE_DART_FAILURE = 10
NON_RETRYABLE_FAILURE = 20


def safe_dict(value):
    return value if isinstance(value, dict) else {}


def safe_list(value):
    return value if isinstance(value, list) else []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--stock-code", required=True)
    args = parser.parse_args()

    path = Path(args.file)

    if not path.exists():
        print("DART USABILITY: RETRY - output file missing")
        return RETRYABLE_DART_FAILURE

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        print(
            f"DART USABILITY: FAIL - invalid JSON: "
            f"{type(error).__name__}: {error}"
        )
        return NON_RETRYABLE_FAILURE


    code = str(data.get("KIS종목코드", "")).zfill(6)

    if code != str(args.stock_code).zfill(6):
        print("DART USABILITY: FAIL - stock code mismatch")
        return NON_RETRYABLE_FAILURE


    fundamentals = safe_dict(
        data.get("기업기초데이터")
    )

    period_bundle = safe_dict(
        fundamentals.get("재무기간")
    )

    periods = safe_list(
        period_bundle.get("기간목록")
    )


    valid_periods = [
        item
        for item in periods
        if isinstance(item, dict)
        and item.get("수집상태") == "정상"
    ]


    valuation = safe_dict(
        data.get("가치평가")
    )


    # 실제 DART 수집 실패만 재시도
    if len(valid_periods) == 0:

        print(
            "DART USABILITY: RETRY"
        )

        print(
            "- usable financial period 없음"
        )

        return RETRYABLE_DART_FAILURE



    warnings = []


    if valuation.get("최종값사용가능") is not True:
        warnings.append(
            "최종 적정가 일부 모델 산출 불가"
        )


    if valuation.get("TTMEPS") in (
        None,
        "",
        0,
        0.0
    ):
        warnings.append(
            "TTM EPS 미확보"
        )


    qualification = safe_dict(
        valuation.get("데이터자격검사")
    )


    for item in safe_list(
        qualification.get("중단사유")
    ):
        warnings.append(str(item))


    for item in safe_list(
        qualification.get("주의사유")
    ):
        warnings.append(str(item))


    if warnings:

        print(
            "DART USABILITY: PASS WITH WARNING"
        )

        for item in warnings:
            print("-", item)

    else:

        print(
            "DART USABILITY: PASS"
        )


    print(
        "- valid financial periods:",
        len(valid_periods)
    )

    print(
        "- formal period key:",
        qualification.get(
            "정식재무기준분기키"
        )
    )

    print(
        "- valuation basis:",
        qualification.get(
            "평가기준",
            "최신 정식보고서 기준"
        )
    )

    print(
        "- TTM EPS:",
        valuation.get("TTMEPS")
    )

    print(
        "- valuation:",
        valuation.get("기본적정가")
    )


    return 0



if __name__ == "__main__":
    raise SystemExit(main())
