"""
산업 프로필 정적 검증기 V1

네트워크 호출 없이 다음을 검증한다.
- 지원 산업 8종 존재
- 산업별 중기·장기 가중치 합계 100
- 구성자산 심볼·산업구간 존재
- 상대강도 기준시장 유효
- 산업 자동분류 매핑의 산업코드 유효
- 동일 종목코드 중복 분류 차단
"""

import json
import sys
from pathlib import Path

from collectors.industry import (
    INDUSTRY_PROFILES,
)
from collectors.company import (
    VALUATION_INDUSTRIES,
)


EXPECTED_INDUSTRIES = {
    "semiconductor",
    "electronic_components",
    "automotive",
    "battery",
    "biotechnology",
    "construction",
    "finance",
    "insurance",
}

ALLOWED_BENCHMARKS = {
    "S&P500",
    "나스닥",
}

MAP_PATH = Path(
    "data/industry_map.json"
)


def main() -> int:
    errors = []
    warnings = []

    actual_industries = set(
        INDUSTRY_PROFILES
    )

    missing = (
        EXPECTED_INDUSTRIES
        - actual_industries
    )

    if missing:
        errors.append(
            "지원 산업 누락: "
            + ",".join(
                sorted(
                    missing
                )
            )
        )

    for industry_code in sorted(
        EXPECTED_INDUSTRIES
    ):
        profile = INDUSTRY_PROFILES.get(
            industry_code,
            {},
        )

        assets = profile.get(
            "구성자산",
            {},
        )

        if not assets:
            errors.append(
                f"{industry_code}: 구성자산 없음"
            )
            continue

        mid_sum = 0.0
        long_sum = 0.0

        for asset_name, asset in (
            assets.items()
        ):
            symbol = str(
                asset.get(
                    "symbol",
                    "",
                )
            ).strip()

            segment = str(
                asset.get(
                    "segment",
                    "",
                )
            ).strip()

            if not symbol:
                errors.append(
                    f"{industry_code}/{asset_name}: "
                    "심볼 없음"
                )

            if not segment:
                errors.append(
                    f"{industry_code}/{asset_name}: "
                    "산업구간 없음"
                )

            try:
                mid_sum += float(
                    asset.get(
                        "mid_weight",
                        0,
                    )
                )

                long_sum += float(
                    asset.get(
                        "long_weight",
                        0,
                    )
                )

            except (
                TypeError,
                ValueError,
            ):
                errors.append(
                    f"{industry_code}/{asset_name}: "
                    "가중치 숫자 오류"
                )

        if abs(
            mid_sum
            - 100.0
        ) > 0.001:
            errors.append(
                f"{industry_code}: "
                f"중기가중치 합계 {mid_sum}"
            )

        if abs(
            long_sum
            - 100.0
        ) > 0.001:
            errors.append(
                f"{industry_code}: "
                f"장기가중치 합계 {long_sum}"
            )

        benchmark = profile.get(
            "상대강도기준"
        )

        if benchmark not in (
            ALLOWED_BENCHMARKS
        ):
            errors.append(
                f"{industry_code}: "
                f"기준시장 오류 {benchmark}"
            )

    if not MAP_PATH.exists():
        errors.append(
            "data/industry_map.json 없음"
        )

    else:
        try:
            payload = json.loads(
                MAP_PATH.read_text(
                    encoding="utf-8"
                )
            )

            industries = payload.get(
                "industries",
                {},
            )

            seen_codes = {}

            for industry_code, detail in (
                industries.items()
            ):
                if industry_code not in VALUATION_INDUSTRIES:
                    errors.append(
                        "가치평가에 미지원 산업코드: "
                        f"{industry_code}"
                    )
                elif industry_code not in EXPECTED_INDUSTRIES:
                    warnings.append(
                        f"{industry_code}: 가치평가 전용 매핑 · 실시간 산업 대표자산 모델은 미지원"
                    )

                stock_codes = detail.get(
                    "stock_codes",
                    {},
                )

                if not stock_codes:
                    warnings.append(
                        f"{industry_code}: "
                        "자동분류 종목 없음"
                    )

                for stock_code in stock_codes:
                    normalized = str(
                        stock_code
                    ).zfill(6)

                    previous = seen_codes.get(
                        normalized
                    )

                    if previous:
                        errors.append(
                            f"{normalized}: "
                            f"{previous}, {industry_code} "
                            "중복 분류"
                        )

                    seen_codes[
                        normalized
                    ] = industry_code

        except Exception as error:
            errors.append(
                "산업 매핑 JSON 오류: "
                f"{type(error).__name__}: "
                f"{error}"
            )

    print(
        "INDUSTRY PROFILE VALIDATION"
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
        "- 지원 산업:",
        ", ".join(
            sorted(
                EXPECTED_INDUSTRIES
            )
        ),
    )

    print(
        "- 산업 수:",
        len(
            EXPECTED_INDUSTRIES
        ),
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
