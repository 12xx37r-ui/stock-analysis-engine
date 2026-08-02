"""Validate whether a generated stock result is safe to publish.

General financial analysis mode.

This validator checks data integrity only.
It does NOT judge whether a company is investable.

Exit codes:
  0  usable (including incomplete data warning)
  10 retryable system/data collection failure
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


    # output 파일 자체 없음
    if not path.exists():
        print("DART USABILITY: RETRY - output file missing")
        return RETRYABLE_DART_FAILURE


    # JSON 손상
    try:
        data = json.loads(
            path.read_text(encoding="utf-8")
        )
    except Exception as error:
        print(
            "DART USABILITY: FAIL - invalid JSON:",
            type(error).__name__,
            error
        )
        return NON_RETRYABLE_FAILURE



    # 종목코드 검증
    code = str(
        data.get("KIS종목코드", "")
    ).zfill(6)

    if code != str(args.stock_code).zfill(6):
        print(
            "DART USABILITY: FAIL - stock code mismatch"
        )
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



    warnings = []



    # 재무기간 부족
    if len(valid_periods) == 0:
        warnings.append(
            "정식 재무기간 확보 실패"
        )


    # 현재가 없음
    current_price = data.get("현재가")

    if current_price in (
        None,
        0,
        0.0,
        ""
    ):
        warnings.append(
            "현재가 데이터 없음"
        )


    # 적정가 없음
    if valuation.get(
        "최종값사용가능"
    ) is not True:
        warnings.append(
            "최종 적정가 일부 또는 전체 산출 불가"
        )


    # EPS 없음
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
        valuation.get(
            "데이터자격검사"
        )
    )


    for item in safe_list(
        qualification.get("중단사유")
    ):
        warnings.append(
            str(item)
        )


    for item in safe_list(
        qualification.get("주의사유")
    ):
        warnings.append(
            str(item)
        )



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
        valuation.get(
            "TTMEPS"
        )
    )

    print(
        "- valuation:",
        valuation.get(
            "기본적정가"
        )
    )


    return 0



if __name__ == "__main__":
    raise SystemExit(main())
