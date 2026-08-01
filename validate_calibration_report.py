"""
확률 보정 보고서 검증기 V1
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List


EXPECTED_VERSION = "1.0.0"

HORIZONS = {
    "short_5d",
    "mid_20d",
    "mid_40d",
    "long_126d",
    "long_252d",
    "long_378d",
}


def safe_dict(
    value: Any,
) -> Dict[str, Any]:
    if isinstance(
        value,
        dict,
    ):
        return value

    return {}


def safe_list(
    value: Any,
) -> List[Any]:
    if isinstance(
        value,
        list,
    ):
        return value

    return []


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        return float(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return default


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "확률 보정 보고서 검증"
        )
    )

    parser.add_argument(
        "--report",
        default=(
            "output/"
            "calibration_report.json"
        ),
    )

    args = parser.parse_args()

    path = Path(
        args.report
    )

    errors = []
    warnings = []
    summary = []

    if not path.exists():
        errors.append(
            f"파일 없음: {path}"
        )
        report = {}

    else:
        try:
            report = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

        except Exception as error:
            errors.append(
                "보고서 읽기 실패: "
                f"{type(error).__name__}: "
                f"{error}"
            )
            report = {}

    if report.get(
        "버전"
    ) != EXPECTED_VERSION:
        errors.append(
            "보고서 버전 불일치"
        )

    if report.get(
        "라이브엔진자동적용"
    ) is not False:
        errors.append(
            "라이브 자동적용은 False여야 함"
        )

    policy = safe_dict(
        report.get(
            "정책"
        )
    )

    if policy.get(
        "자동적용금지"
    ) is not True:
        errors.append(
            "자동적용금지 정책 누락"
        )

    horizons = safe_dict(
        report.get(
            "구간별보정상태"
        )
    )

    if set(
        horizons
    ) != HORIZONS:
        errors.append(
            "보정 구간 키 불일치"
        )

    ready_count = 0

    for horizon_key in HORIZONS:
        detail = safe_dict(
            horizons.get(
                horizon_key
            )
        )

        status = detail.get(
            "상태"
        )

        if status not in (
            "표본부족",
            "검토가능",
        ):
            errors.append(
                f"{horizon_key}: 상태 오류"
            )

        if detail.get(
            "라이브적용"
        ) is not False:
            errors.append(
                f"{horizon_key}: 라이브적용은 False여야 함"
            )

        evaluation_count = int(
            safe_float(
                detail.get(
                    "평가수"
                )
            )
        )

        minimum_count = int(
            safe_float(
                detail.get(
                    "필요최소평가수"
                )
            )
        )

        populated_bins = int(
            safe_float(
                detail.get(
                    "사용가능확률구간수"
                )
            )
        )

        minimum_bins = int(
            safe_float(
                detail.get(
                    "필요최소확률구간수"
                )
            )
        )

        bins = safe_list(
            detail.get(
                "확률구간"
            )
        )

        if len(
            bins
        ) != 6:
            errors.append(
                f"{horizon_key}: 확률구간 6개가 아님"
            )

        for bin_detail in bins:
            bin_detail = safe_dict(
                bin_detail
            )

            actual_rate = safe_float(
                bin_detail.get(
                    "실제상승률"
                )
            )

            smoothed_rate = safe_float(
                bin_detail.get(
                    "스무딩상승률"
                )
            )

            if not (
                0.0
                <= actual_rate
                <= 100.0
            ):
                errors.append(
                    f"{horizon_key}: 실제상승률 범위 오류"
                )

            if not (
                0.0
                <= smoothed_rate
                <= 100.0
            ):
                errors.append(
                    f"{horizon_key}: 스무딩상승률 범위 오류"
                )

        should_be_ready = (
            evaluation_count
            >= minimum_count
            and populated_bins
            >= minimum_bins
        )

        if (
            status
            == "검토가능"
        ) != should_be_ready:
            errors.append(
                f"{horizon_key}: 상태와 표본 조건 불일치"
            )

        mapping = safe_list(
            detail.get(
                "보정후보매핑"
            )
        )

        if status == "표본부족" and mapping:
            errors.append(
                f"{horizon_key}: 표본부족인데 후보매핑 존재"
            )

        if status == "검토가능":
            ready_count += 1

            if not mapping:
                warnings.append(
                    f"{horizon_key}: 검토가능하지만 후보매핑 비어 있음"
                )

    report_ready_count = int(
        safe_float(
            report.get(
                "보정검토가능구간수"
            )
        )
    )

    if report_ready_count != ready_count:
        errors.append(
            "보정검토가능구간수 불일치"
        )

    summary.append(
        f"보정검토 가능 구간 {ready_count}개"
    )

    summary.append(
        f"검증 구간 {len(HORIZONS)}개"
    )

    print(
        "CALIBRATION REPORT VALIDATION"
    )

    print(
        "RESULT:",
        "PASS"
        if not errors
        else "FAIL",
    )

    if summary:
        print()
        print(
            "SUMMARY"
        )

        for item in summary:
            print(
                "-",
                item,
            )

    if warnings:
        print()
        print(
            "WARNINGS"
        )

        for item in warnings:
            print(
                "-",
                item,
            )

    if errors:
        print()
        print(
            "ERRORS"
        )

        for item in errors:
            print(
                "-",
                item,
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
