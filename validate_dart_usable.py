"""Fail fast when an engine output cannot safely replace the published stock feed."""
import argparse
import json
from pathlib import Path


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
        print("DART USABILITY: FAIL - output file missing")
        return 1

    data = json.loads(path.read_text(encoding="utf-8"))
    code = str(data.get("KIS종목코드", "")).zfill(6)
    if code != str(args.stock_code).zfill(6):
        print("DART USABILITY: FAIL - stock code mismatch")
        return 1

    fundamentals = safe_dict(data.get("기업기초데이터"))
    periods = safe_list(safe_dict(fundamentals.get("재무기간")).get("기간목록"))
    valid_periods = [
        item for item in periods
        if isinstance(item, dict)
        and item.get("수집상태") == "정상"
        and safe_dict(item.get("지표")).get("매출") not in (None, 0, 0.0, "")
    ]
    valuation = safe_dict(data.get("가치평가"))
    qualification = safe_dict(valuation.get("데이터자격검사"))
    stop_reasons = [str(item) for item in safe_list(qualification.get("중단사유"))]

    errors = []
    if len(valid_periods) < 4:
        errors.append(f"정상 재무기간 {len(valid_periods)}개")
    if safe_dict(fundamentals.get("재무기간")).get("수집상태") != "정상":
        errors.append("OpenDART 재무기간 수집 실패")
    if valuation.get("최종값사용가능") is not True:
        errors.append("최종 가치평가 사용 불가")
    if valuation.get("산출상태") != "정상":
        errors.append(f"산출상태 {valuation.get('산출상태', '미확인')}")
    if qualification.get("통과") is not True:
        errors.append("데이터 자격검사 미통과")

    if errors:
        print("DART USABILITY: FAIL")
        for item in errors + stop_reasons:
            print("-", item)
        return 1

    print("DART USABILITY: PASS")
    print("- valid financial periods:", len(valid_periods))
    print("- TTM EPS:", valuation.get("TTMEPS"))
    print("- valuation:", valuation.get("기본적정가"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
