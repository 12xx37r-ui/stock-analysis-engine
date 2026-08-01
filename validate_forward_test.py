"""
순방향 검증 저장소·보고서 검증기 V1

사용
    python validate_forward_test.py \
        --store data/forward_tests.json \
        --report output/forward_test_report.json
"""

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Dict, List


EXPECTED_STORE_VERSION = "1.0.0"
EXPECTED_REPORT_VERSION = "1.0.0"

HORIZONS = {
    "short_5d": 5,
    "mid_20d": 20,
    "mid_40d": 40,
    "long_126d": 126,
    "long_252d": 252,
    "long_378d": 378,
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
        if value in (
            None,
            "",
        ):
            return default

        return float(
            str(value)
            .replace(",", "")
            .strip()
        )

    except (
        TypeError,
        ValueError,
    ):
        return default


class Result:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.summary = []

    def error(
        self,
        message: str,
    ) -> None:
        self.errors.append(
            message
        )

    def warning(
        self,
        message: str,
    ) -> None:
        self.warnings.append(
            message
        )

    def info(
        self,
        message: str,
    ) -> None:
        self.summary.append(
            message
        )


def load_json(
    path: Path,
    result: Result,
) -> Dict[str, Any]:
    if not path.exists():
        result.error(
            f"파일 없음: {path}"
        )
        return {}

    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except Exception as error:
        result.error(
            f"{path} 읽기 실패: "
            f"{type(error).__name__}: "
            f"{error}"
        )
        return {}

    if not isinstance(
        data,
        dict,
    ):
        result.error(
            f"{path}: 루트가 객체가 아님"
        )
        return {}

    return data


def validate_store(
    store: Dict[str, Any],
    result: Result,
) -> Dict[str, int]:
    if store.get(
        "버전"
    ) != EXPECTED_STORE_VERSION:
        result.error(
            "저장소 버전 불일치: "
            f"{store.get('버전')}"
        )

    records = [
        safe_dict(
            record
        )
        for record in safe_list(
            store.get(
                "기록"
            )
        )
    ]

    ids = []
    completed = 0
    pending = 0

    for index, record in enumerate(
        records
    ):
        prefix = (
            f"기록[{index}]"
        )

        record_id = str(
            record.get(
                "ID",
                "",
            )
        ).strip()

        if not record_id:
            result.error(
                f"{prefix}: ID 없음"
            )

        ids.append(
            record_id
        )

        stock_code = str(
            record.get(
                "종목코드",
                "",
            )
        ).strip()

        if (
            len(
                stock_code
            )
            != 6
            or not stock_code.isdigit()
        ):
            result.error(
                f"{prefix}: 종목코드 오류 "
                f"{stock_code}"
            )

        base_price = safe_float(
            record.get(
                "기준가격"
            )
        )

        if base_price <= 0:
            result.error(
                f"{prefix}: 기준가격 0 이하"
            )

        prediction_date = str(
            record.get(
                "예측일",
                "",
            )
        )

        if len(
            prediction_date
        ) != 10:
            result.error(
                f"{prefix}: 예측일 형식 오류"
            )

        evaluations = safe_dict(
            record.get(
                "평가"
            )
        )

        if set(
            evaluations
        ) != set(
            HORIZONS
        ):
            result.error(
                f"{prefix}: 평가구간 키 불일치"
            )

        for key, trading_days in (
            HORIZONS.items()
        ):
            evaluation = safe_dict(
                evaluations.get(
                    key
                )
            )

            if int(
                safe_float(
                    evaluation.get(
                        "거래일"
                    )
                )
            ) != trading_days:
                result.error(
                    f"{prefix}/{key}: 거래일 오류"
                )

            probability = safe_float(
                evaluation.get(
                    "예측상승확률"
                ),
                float(
                    "nan"
                ),
            )

            if (
                math.isnan(
                    probability
                )
                or not (
                    20.0
                    <= probability
                    <= 80.0
                )
            ):
                result.error(
                    f"{prefix}/{key}: "
                    f"상승확률 오류 {probability}"
                )

            status = evaluation.get(
                "상태"
            )

            if status == "완료":
                completed += 1

                if not evaluation.get(
                    "평가일"
                ):
                    result.error(
                        f"{prefix}/{key}: "
                        "평가일 누락"
                    )

                if safe_float(
                    evaluation.get(
                        "평가가격"
                    )
                ) <= 0:
                    result.error(
                        f"{prefix}/{key}: "
                        "평가가격 0 이하"
                    )

                brier = safe_float(
                    evaluation.get(
                        "Brier점수"
                    ),
                    -1.0,
                )

                if not (
                    0.0
                    <= brier
                    <= 1.0
                ):
                    result.error(
                        f"{prefix}/{key}: "
                        f"Brier점수 오류 {brier}"
                    )

            elif status == "대기":
                pending += 1

            else:
                result.error(
                    f"{prefix}/{key}: "
                    f"상태 오류 {status}"
                )

    if len(
        ids
    ) != len(
        set(
            ids
        )
    ):
        result.error(
            "예측 기록 ID 중복"
        )

    result.info(
        f"예측기록 {len(records)}개"
    )

    result.info(
        f"평가완료 {completed}개"
    )

    result.info(
        f"평가대기 {pending}개"
    )

    return {
        "records": len(
            records
        ),
        "completed": completed,
        "pending": pending,
    }


def validate_report(
    report: Dict[str, Any],
    counts: Dict[str, int],
    result: Result,
) -> None:
    if report.get(
        "버전"
    ) != EXPECTED_REPORT_VERSION:
        result.error(
            "보고서 버전 불일치: "
            f"{report.get('버전')}"
        )

    if int(
        safe_float(
            report.get(
                "예측기록수"
            )
        )
    ) != counts[
        "records"
    ]:
        result.error(
            "보고서 예측기록수 불일치"
        )

    if int(
        safe_float(
            report.get(
                "평가완료수"
            )
        )
    ) != counts[
        "completed"
    ]:
        result.error(
            "보고서 평가완료수 불일치"
        )

    if int(
        safe_float(
            report.get(
                "평가대기수"
            )
        )
    ) != counts[
        "pending"
    ]:
        result.error(
            "보고서 평가대기수 불일치"
        )

    metrics = safe_dict(
        report.get(
            "구간별성과"
        )
    )

    if set(
        metrics
    ) != set(
        HORIZONS
    ):
        result.error(
            "보고서 구간별성과 키 불일치"
        )

    for key in HORIZONS:
        metric = safe_dict(
            metrics.get(
                key
            )
        )

        hit_rate = safe_float(
            metric.get(
                "방향적중률"
            )
        )

        if not (
            0.0
            <= hit_rate
            <= 100.0
        ):
            result.error(
                f"{key}: 방향적중률 오류"
            )

        brier = safe_float(
            metric.get(
                "평균Brier점수"
            )
        )

        if not (
            0.0
            <= brier
            <= 1.0
        ):
            result.error(
                f"{key}: 평균Brier점수 오류"
            )


def print_items(
    title: str,
    items: List[str],
) -> None:
    if not items:
        return

    print()
    print(
        title
    )

    for item in items:
        print(
            "-",
            item,
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "순방향 검증 저장소·보고서 검증"
        )
    )

    parser.add_argument(
        "--store",
        default="data/forward_tests.json",
    )

    parser.add_argument(
        "--report",
        default=(
            "output/"
            "forward_test_report.json"
        ),
    )

    args = parser.parse_args()

    result = Result()

    store = load_json(
        Path(
            args.store
        ),
        result,
    )

    report = load_json(
        Path(
            args.report
        ),
        result,
    )

    counts = validate_store(
        store,
        result,
    )

    validate_report(
        report,
        counts,
        result,
    )

    print(
        "FORWARD TEST VALIDATION"
    )

    print(
        "RESULT:",
        "PASS"
        if not result.errors
        else "FAIL",
    )

    print_items(
        "SUMMARY",
        result.summary,
    )

    print_items(
        "WARNINGS",
        result.warnings,
    )

    print_items(
        "ERRORS",
        result.errors,
    )

    print()
    print(
        "COUNTS:",
        f"errors={len(result.errors)}",
        f"warnings={len(result.warnings)}",
    )

    return (
        0
        if not result.errors
        else 1
    )


if __name__ == "__main__":
    sys.exit(
        main()
    )
