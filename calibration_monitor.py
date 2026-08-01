"""
순방향 예측 확률 보정 모니터 V1

역할
- data/forward_tests.json의 실제 평가 결과를 분석
- 구간별 표본 수·방향 적중률·Brier 점수·기준모형 대비 성과 계산
- 예측확률 구간별 실제 상승률을 산출
- 충분한 표본이 모였을 때만 보정 후보를 제시
- 라이브 predictor.py는 자동 수정하지 않음

사용
    python calibration_monitor.py \
        --store data/forward_tests.json \
        --report output/calibration_report.json
"""

import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List


REPORT_VERSION = "1.0.0"

KST = timezone(
    timedelta(hours=9)
)

HORIZONS = (
    "short_5d",
    "mid_20d",
    "mid_40d",
    "long_126d",
    "long_252d",
    "long_378d",
)

MIN_TOTAL_EVALUATIONS = 30
MIN_POPULATED_BINS = 3
MIN_BIN_EVALUATIONS = 5

PROBABILITY_BINS = (
    (20.0, 30.0),
    (30.0, 40.0),
    (40.0, 50.0),
    (50.0, 60.0),
    (60.0, 70.0),
    (70.0, 80.000001),
)


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


def now_iso() -> str:
    return datetime.now(
        KST
    ).isoformat()


def load_store(
    path: Path,
) -> Dict[str, Any]:
    if not path.exists():
        raise RuntimeError(
            f"순방향 검증 저장소 없음: {path}"
        )

    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except Exception as error:
        raise RuntimeError(
            f"저장소 읽기 실패: "
            f"{type(error).__name__}: "
            f"{error}"
        ) from error

    if not isinstance(
        data,
        dict,
    ):
        raise RuntimeError(
            "저장소 루트가 객체가 아닙니다."
        )

    return data


def completed_evaluations(
    store: Dict[str, Any],
    horizon_key: str,
) -> List[Dict[str, Any]]:
    completed = []

    for record in safe_list(
        store.get(
            "기록"
        )
    ):
        record = safe_dict(
            record
        )

        evaluation = safe_dict(
            safe_dict(
                record.get(
                    "평가"
                )
            ).get(
                horizon_key
            )
        )

        if evaluation.get(
            "상태"
        ) != "완료":
            continue

        probability = safe_float(
            evaluation.get(
                "예측상승확률"
            ),
            float(
                "nan"
            ),
        )

        if math.isnan(
            probability
        ):
            continue

        actual_up = evaluation.get(
            "실제상승"
        )

        if actual_up not in (
            True,
            False,
        ):
            continue

        completed.append(
            {
                "예측상승확률": probability,
                "실제상승": bool(
                    actual_up
                ),
                "방향적중": evaluation.get(
                    "방향적중"
                ),
                "수익률": safe_float(
                    evaluation.get(
                        "수익률"
                    )
                ),
                "Brier점수": safe_float(
                    evaluation.get(
                        "Brier점수"
                    )
                ),
            }
        )

    return completed


def mean(
    values: List[float],
) -> float:
    if not values:
        return 0.0

    return sum(
        values
    ) / len(
        values
    )


def build_bins(
    evaluations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    bins = []

    for lower, upper in PROBABILITY_BINS:
        members = [
            item
            for item in evaluations
            if (
                lower
                <= item[
                    "예측상승확률"
                ]
                < upper
            )
        ]

        count = len(
            members
        )

        actual_up_count = sum(
            item[
                "실제상승"
            ]
            is True
            for item in members
        )

        actual_rate = (
            actual_up_count
            / count
            * 100.0
            if count > 0
            else 0.0
        )

        # Beta(2,2) 사전분포를 사용한 완만한 스무딩.
        smoothed_rate = (
            (
                actual_up_count
                + 2.0
            )
            / (
                count
                + 4.0
            )
            * 100.0
            if count > 0
            else 50.0
        )

        bins.append(
            {
                "구간하단": int(
                    lower
                ),
                "구간상단": (
                    80
                    if upper > 80.0
                    else int(
                        upper
                    )
                ),
                "구간중심": round(
                    (
                        lower
                        + min(
                            upper,
                            80.0,
                        )
                    )
                    / 2.0,
                    2,
                ),
                "평가수": count,
                "평균예측확률": round(
                    mean(
                        [
                            item[
                                "예측상승확률"
                            ]
                            for item in members
                        ]
                    ),
                    2,
                ),
                "실제상승수": actual_up_count,
                "실제상승률": round(
                    actual_rate,
                    2,
                ),
                "스무딩상승률": round(
                    smoothed_rate,
                    2,
                ),
                "후보사용가능": (
                    count
                    >= MIN_BIN_EVALUATIONS
                ),
            }
        )

    return bins


def candidate_mapping(
    bins: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    points = []

    for item in bins:
        if item.get(
            "후보사용가능"
        ) is not True:
            continue

        points.append(
            {
                "원확률": item[
                    "평균예측확률"
                ],
                "보정후보확률": round(
                    max(
                        20.0,
                        min(
                            80.0,
                            safe_float(
                                item.get(
                                    "스무딩상승률"
                                )
                            ),
                        ),
                    ),
                    2,
                ),
                "표본수": item[
                    "평가수"
                ],
            }
        )

    return sorted(
        points,
        key=lambda item: item[
            "원확률"
        ],
    )


def horizon_report(
    evaluations: List[Dict[str, Any]],
) -> Dict[str, Any]:
    sample_count = len(
        evaluations
    )

    bins = build_bins(
        evaluations
    )

    populated_bins = sum(
        item[
            "평가수"
        ]
        >= MIN_BIN_EVALUATIONS
        for item in bins
    )

    actual_values = [
        1.0
        if item[
            "실제상승"
        ]
        else 0.0
        for item in evaluations
    ]

    probabilities = [
        item[
            "예측상승확률"
        ]
        / 100.0
        for item in evaluations
    ]

    base_rate = mean(
        actual_values
    )

    raw_brier = mean(
        [
            (
                probability
                - actual
            ) ** 2
            for probability, actual in zip(
                probabilities,
                actual_values,
            )
        ]
    )

    baseline_brier = (
        base_rate
        * (
            1.0
            - base_rate
        )
        if sample_count > 0
        else 0.0
    )

    brier_skill = (
        1.0
        - (
            raw_brier
            / baseline_brier
        )
        if baseline_brier > 0
        else 0.0
    )

    direction_values = [
        item[
            "방향적중"
        ]
        for item in evaluations
        if item.get(
            "방향적중"
        ) is not None
    ]

    ready = (
        sample_count
        >= MIN_TOTAL_EVALUATIONS
        and populated_bins
        >= MIN_POPULATED_BINS
    )

    status = (
        "검토가능"
        if ready
        else "표본부족"
    )

    return {
        "상태": status,
        "라이브적용": False,
        "평가수": sample_count,
        "필요최소평가수": (
            MIN_TOTAL_EVALUATIONS
        ),
        "사용가능확률구간수": (
            populated_bins
        ),
        "필요최소확률구간수": (
            MIN_POPULATED_BINS
        ),
        "평균예측상승확률": round(
            mean(
                probabilities
            )
            * 100.0,
            2,
        ),
        "실제상승률": round(
            base_rate
            * 100.0,
            2,
        ),
        "방향평가가능수": len(
            direction_values
        ),
        "방향적중률": round(
            (
                sum(
                    value is True
                    for value in (
                        direction_values
                    )
                )
                / len(
                    direction_values
                )
                * 100.0
            )
            if direction_values
            else 0.0,
            2,
        ),
        "평균수익률": round(
            mean(
                [
                    item[
                        "수익률"
                    ]
                    for item in evaluations
                ]
            ),
            4,
        ),
        "원확률Brier점수": round(
            raw_brier,
            6,
        ),
        "기준모형Brier점수": round(
            baseline_brier,
            6,
        ),
        "BrierSkillScore": round(
            brier_skill,
            6,
        ),
        "확률구간": bins,
        "보정후보매핑": (
            candidate_mapping(
                bins
            )
            if ready
            else []
        ),
        "판단": (
            "표본과 확률구간이 충분합니다. "
            "후보 매핑을 검토할 수 있지만 "
            "라이브 엔진에는 자동 적용하지 않습니다."
            if ready
            else (
                "표본이 충분하지 않아 확률 보정을 "
                "적용하지 않습니다."
            )
        ),
    }


def build_report(
    store: Dict[str, Any],
) -> Dict[str, Any]:
    horizons = {}

    for horizon_key in HORIZONS:
        evaluations = (
            completed_evaluations(
                store,
                horizon_key,
            )
        )

        horizons[
            horizon_key
        ] = horizon_report(
            evaluations
        )

    ready_count = sum(
        detail[
            "상태"
        ]
        == "검토가능"
        for detail in horizons.values()
    )

    return {
        "버전": REPORT_VERSION,
        "생성시각": now_iso(),
        "라이브엔진자동적용": False,
        "보정검토가능구간수": ready_count,
        "정책": {
            "최소전체평가수": (
                MIN_TOTAL_EVALUATIONS
            ),
            "최소확률구간수": (
                MIN_POPULATED_BINS
            ),
            "확률구간별최소평가수": (
                MIN_BIN_EVALUATIONS
            ),
            "자동적용금지": True,
            "설명": (
                "표본이 충분해도 보정 후보만 생성하며 "
                "predictor.py는 자동 수정하지 않습니다."
            ),
        },
        "구간별보정상태": horizons,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "순방향 예측 확률 보정 모니터"
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
            "calibration_report.json"
        ),
    )

    args = parser.parse_args()

    store = load_store(
        Path(
            args.store
        )
    )

    report = build_report(
        store
    )

    report_path = Path(
        args.report
    )

    report_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    report_path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(
        "CALIBRATION MONITOR RESULT"
    )

    print(
        "- 보정검토 가능 구간:",
        report[
            "보정검토가능구간수"
        ],
    )

    for horizon_key, detail in (
        report[
            "구간별보정상태"
        ].items()
    ):
        print(
            "-",
            horizon_key,
            detail[
                "상태"
            ],
            f"평가 {detail['평가수']}개",
            f"확률구간 {detail['사용가능확률구간수']}개",
        )

    print(
        "REPORT_FILE=",
        report_path,
        sep="",
    )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )
