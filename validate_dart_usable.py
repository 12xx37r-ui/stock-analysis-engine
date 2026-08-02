"""Validate whether a generated stock result is safe to publish.

Exit codes:
  0  usable (including warning-pass based on the latest formal report)
  10 retryable OpenDART collection failure
  20 non-retryable valuation/contract failure
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
        print(f"DART USABILITY: FAIL - invalid JSON: {type(error).__name__}: {error}")
        return NON_RETRYABLE_FAILURE

    code = str(data.get("KIS종목코드", "")).zfill(6)
    if code != str(args.stock_code).zfill(6):
        print("DART USABILITY: FAIL - stock code mismatch")
        return NON_RETRYABLE_FAILURE

    fundamentals = safe_dict(data.get("기업기초데이터"))
    period_bundle = safe_dict(fundamentals.get("재무기간"))
    periods = safe_list(period_bundle.get("기간목록"))
    valid_periods = [
        item for item in periods
        if isinstance(item, dict)
        and item.get("수집상태") == "정상"
        and safe_dict(item.get("지표")).get("매출") not in (None, 0, 0.0, "")
    ]
    valuation = safe_dict(data.get("가치평가"))
    qualification = safe_dict(valuation.get("데이터자격검사"))
    stop_reasons = [str(item) for item in safe_list(qualification.get("중단사유"))]
    warning_reasons = [str(item) for item in safe_list(qualification.get("주의사유"))]

    retryable = []
    if len(valid_periods) < 4:
        retryable.append(f"정상 재무기간 {len(valid_periods)}개")
    if period_bundle.get("수집상태") != "정상":
        retryable.append("OpenDART 재무기간 수집 실패")

    if retryable:
        print("DART USABILITY: RETRY")
        for item in retryable:
            print("-", item)
        return RETRYABLE_DART_FAILURE

    structural = []
    if valuation.get("최종값사용가능") is not True:
        structural.append("최종 가치평가 사용 불가")
    if valuation.get("산출상태") != "정상":
        structural.append(f"산출상태 {valuation.get('산출상태', '미확인')}")
    if qualification.get("통과") is not True:
        structural.append("데이터 자격검사 미통과")

    if structural:
        print("DART USABILITY: FAIL")
        for item in structural + stop_reasons:
            print("-", item)
        return NON_RETRYABLE_FAILURE

    if warning_reasons:
        print("DART USABILITY: PASS WITH WARNING")
        for item in warning_reasons:
            print("-", item)
    else:
        print("DART USABILITY: PASS")
    print("- valid financial periods:", len(valid_periods))
    print("- formal period key:", qualification.get("정식재무기준분기키"))
    print("- valuation basis:", qualification.get("평가기준", "최신 정식보고서 기준"))
    print("- TTM EPS:", valuation.get("TTMEPS"))
    print("- valuation:", valuation.get("기본적정가"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
