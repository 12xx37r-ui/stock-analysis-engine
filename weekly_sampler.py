"""
주간 순방향 표본수집 실행기 V1

산업별 배치를 순차 실행해:
1. 스크리너 실행 및 검증
2. 예측 스냅샷만 누적 기록
3. 모든 배치 완료 후 기존 예측을 한 번만 평가
4. 순방향 검증·확률 보정 보고서 생성 및 검증

사용
    python weekly_sampler.py

    python weekly_sampler.py \
        --batch semiconductor
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List


KST = timezone(
    timedelta(hours=9)
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


def now_iso() -> str:
    return datetime.now(
        KST
    ).isoformat()


def load_plan(
    path: Path,
) -> Dict[str, Any]:
    if not path.exists():
        raise RuntimeError(
            f"표본수집 계획 없음: {path}"
        )

    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except Exception as error:
        raise RuntimeError(
            "표본수집 계획 읽기 실패: "
            f"{type(error).__name__}: "
            f"{error}"
        ) from error

    if not isinstance(
        payload,
        dict,
    ):
        raise RuntimeError(
            "표본수집 계획 루트가 객체가 아닙니다."
        )

    return payload


def run_command(
    command: List[str],
    cwd: Path,
) -> None:
    print()
    print(
        "RUN:",
        " ".join(
            command
        ),
    )

    subprocess.run(
        command,
        cwd=cwd,
        check=True,
    )


def copy_batch_outputs(
    root: Path,
    destination: Path,
    stock_codes: List[str],
) -> None:
    destination.mkdir(
        parents=True,
        exist_ok=True,
    )

    required_files = [
        root
        / "output"
        / "screener.json",
        root
        / "output"
        / "screener.csv",
    ]

    required_files.extend(
        root
        / "output"
        / f"{stock_code}.json"
        for stock_code in stock_codes
    )

    for source in required_files:
        if not source.exists():
            raise RuntimeError(
                f"배치 산출물 누락: {source}"
            )

        shutil.copy2(
            source,
            destination
            / source.name,
        )


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "주간 순방향 표본수집"
        )
    )

    parser.add_argument(
        "--plan",
        default="data/sampling_plan.json",
    )

    parser.add_argument(
        "--batch",
        default="all",
        help=(
            "all 또는 sampling_plan의 배치명"
        ),
    )

    parser.add_argument(
        "--root",
        default=".",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_arguments()

    root = Path(
        args.root
    ).resolve()

    plan_path = (
        root
        / args.plan
    )

    plan = load_plan(
        plan_path
    )

    batches = safe_dict(
        plan.get(
            "batches"
        )
    )

    if args.batch == "all":
        selected_names = list(
            batches.keys()
        )

    else:
        if args.batch not in batches:
            raise RuntimeError(
                f"존재하지 않는 배치: {args.batch}"
            )

        selected_names = [
            args.batch
        ]

    if not selected_names:
        raise RuntimeError(
            "실행할 배치가 없습니다."
        )

    output_root = (
        root
        / "output"
        / "weekly_sampling"
    )

    if output_root.exists():
        shutil.rmtree(
            output_root
        )

    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary = {
        "버전": "1.0.0",
        "시작시각": now_iso(),
        "종료시각": "",
        "요청배치": args.batch,
        "배치수": len(
            selected_names
        ),
        "종목수": 0,
        "배치결과": [],
        "상태": "실행중",
    }

    python = sys.executable

    try:
        for batch_name in selected_names:
            detail = safe_dict(
                batches[
                    batch_name
                ]
            )

            stocks = safe_dict(
                detail.get(
                    "stocks"
                )
            )

            stock_codes = list(
                stocks.keys()
            )

            if not stock_codes:
                raise RuntimeError(
                    f"{batch_name}: 종목 없음"
                )

            codes_argument = ",".join(
                stock_codes
            )

            industry_code = str(
                detail.get(
                    "industry_code",
                    "auto",
                )
            )

            print()
            print(
                "WEEKLY SAMPLING BATCH:",
                batch_name,
                codes_argument,
            )

            run_command(
                [
                    python,
                    "screener.py",
                    "--stock-codes",
                    codes_argument,
                    "--industry-code",
                    industry_code,
                ],
                root,
            )

            run_command(
                [
                    python,
                    "validate_screener.py",
                    "--stock-codes",
                    codes_argument,
                ],
                root,
            )

            batch_destination = (
                output_root
                / batch_name
            )

            copy_batch_outputs(
                root,
                batch_destination,
                stock_codes,
            )

            run_command(
                [
                    python,
                    "forward_test.py",
                    "--record-only",
                    "--screener-file",
                    "output/screener.json",
                    "--store",
                    "data/forward_tests.json",
                    "--report",
                    "output/forward_test_report.json",
                ],
                root,
            )

            summary[
                "종목수"
            ] += len(
                stock_codes
            )

            summary[
                "배치결과"
            ].append(
                {
                    "배치": batch_name,
                    "종목수": len(
                        stock_codes
                    ),
                    "종목코드": stock_codes,
                    "상태": "PASS",
                }
            )

        run_command(
            [
                python,
                "forward_test.py",
                "--evaluate-only",
                "--store",
                "data/forward_tests.json",
                "--report",
                "output/forward_test_report.json",
            ],
            root,
        )

        run_command(
            [
                python,
                "validate_forward_test.py",
                "--store",
                "data/forward_tests.json",
                "--report",
                "output/forward_test_report.json",
            ],
            root,
        )

        run_command(
            [
                python,
                "calibration_monitor.py",
                "--store",
                "data/forward_tests.json",
                "--report",
                "output/calibration_report.json",
            ],
            root,
        )

        run_command(
            [
                python,
                "validate_calibration_report.py",
                "--report",
                "output/calibration_report.json",
            ],
            root,
        )

        summary[
            "상태"
        ] = "PASS"

    except Exception as error:
        summary[
            "상태"
        ] = "FAIL"

        summary[
            "오류"
        ] = (
            f"{type(error).__name__}: "
            f"{error}"
        )

        raise

    finally:
        summary[
            "종료시각"
        ] = now_iso()

        summary_path = (
            root
            / "output"
            / "weekly_sampling_summary.json"
        )

        summary_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        summary_path.write_text(
            json.dumps(
                summary,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print()
        print(
            "WEEKLY SAMPLING RESULT"
        )

        print(
            "- 상태:",
            summary[
                "상태"
            ],
        )

        print(
            "- 배치:",
            summary[
                "배치수"
            ],
        )

        print(
            "- 종목:",
            summary[
                "종목수"
            ],
        )

        print(
            "SUMMARY_FILE="
            "output/"
            "weekly_sampling_summary.json"
        )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )
