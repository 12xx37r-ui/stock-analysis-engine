"""
주간 순방향 표본수집 계획 검증기 V1
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict


EXPECTED_VERSION = "1.0.0"

EXPECTED_BATCHES = {
    "semiconductor",
    "automotive",
    "battery",
    "biotechnology",
    "construction",
    "finance",
}

MAX_STOCKS_PER_BATCH = 10


def safe_dict(
    value: Any,
) -> Dict[str, Any]:
    if isinstance(
        value,
        dict,
    ):
        return value

    return {}


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "주간 순방향 표본수집 계획 검증"
        )
    )

    parser.add_argument(
        "--plan",
        default="data/sampling_plan.json",
    )

    args = parser.parse_args()

    path = Path(
        args.plan
    )

    errors = []
    warnings = []

    if not path.exists():
        errors.append(
            f"파일 없음: {path}"
        )
        payload = {}

    else:
        try:
            payload = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

        except Exception as error:
            errors.append(
                "계획 파일 읽기 실패: "
                f"{type(error).__name__}: "
                f"{error}"
            )
            payload = {}

    if payload.get(
        "version"
    ) != EXPECTED_VERSION:
        errors.append(
            "계획 버전 불일치"
        )

    batches = safe_dict(
        payload.get(
            "batches"
        )
    )

    if set(
        batches
    ) != EXPECTED_BATCHES:
        errors.append(
            "배치 목록 불일치"
        )

    seen_codes = {}
    total_stocks = 0

    for batch_name in sorted(
        EXPECTED_BATCHES
    ):
        detail = safe_dict(
            batches.get(
                batch_name
            )
        )

        industry_code = str(
            detail.get(
                "industry_code",
                "",
            )
        ).strip()

        if industry_code != "auto":
            errors.append(
                f"{batch_name}: "
                "industry_code는 auto여야 함"
            )

        stocks = safe_dict(
            detail.get(
                "stocks"
            )
        )

        if not stocks:
            errors.append(
                f"{batch_name}: 종목 없음"
            )

        if len(
            stocks
        ) > MAX_STOCKS_PER_BATCH:
            errors.append(
                f"{batch_name}: "
                f"종목 수 {len(stocks)}개가 "
                f"상한 {MAX_STOCKS_PER_BATCH}개 초과"
            )

        total_stocks += len(
            stocks
        )

        for stock_code, company_name in (
            stocks.items()
        ):
            code = str(
                stock_code
            ).strip()

            if (
                len(
                    code
                )
                != 6
                or not code.isdigit()
            ):
                errors.append(
                    f"{batch_name}: "
                    f"종목코드 오류 {code}"
                )

            if not str(
                company_name
            ).strip():
                errors.append(
                    f"{batch_name}/{code}: "
                    "기업명 없음"
                )

            previous = seen_codes.get(
                code
            )

            if previous:
                errors.append(
                    f"{code}: "
                    f"{previous}, {batch_name} "
                    "중복 배치"
                )

            seen_codes[
                code
            ] = batch_name

    if total_stocks < 20:
        warnings.append(
            f"전체 표본 종목이 {total_stocks}개로 적음"
        )

    print(
        "SAMPLING PLAN VALIDATION"
    )

    print(
        "RESULT:",
        "PASS"
        if not errors
        else "FAIL",
    )

    print()
    print(
        "SUMMARY"
    )

    print(
        "- 배치 수:",
        len(
            batches
        ),
    )

    print(
        "- 전체 종목 수:",
        total_stocks,
    )

    if warnings:
        print()
        print(
            "WARNINGS"
        )

        for warning in warnings:
            print(
                "-",
                warning,
            )

    if errors:
        print()
        print(
            "ERRORS"
        )

        for error in errors:
            print(
                "-",
                error,
            )

    print()
    print(
        "COUNTS:",
        f"errors={len(errors)}",
        f"warnings={len(warnings)}",
    )

    return (
        0
        if not errors
        else 1
    )


if __name__ == "__main__":
    sys.exit(
        main()
    )
