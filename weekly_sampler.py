"""
주간 순방향 표본수집 실행기 V1.2

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

from collectors.kis import (
    get_access_token,
    get_token_failure_message,
)


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


def safe_list(
    value: Any,
) -> List[Any]:
    if isinstance(
        value,
        list,
    ):
        return value

    return []


def load_json_file(
    path: Path,
    default: Any,
) -> Any:
    if not path.exists():
        return default

    try:
        return json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except Exception as error:
        raise RuntimeError(
            f"{path} 읽기 실패: "
            f"{type(error).__name__}: "
            f"{error}"
        ) from error


def write_json_file(
    path: Path,
    payload: Any,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    temporary.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary.replace(
        path
    )


def publish_batch_latest(
    root: Path,
    batch_name: str,
    stock_codes: List[str],
) -> None:
    latest_root = (
        root
        / "data"
        / "latest"
    )

    stocks_root = (
        latest_root
        / "stocks"
    )

    batches_root = (
        latest_root
        / "batches"
    )

    stocks_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    batches_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    screener_path = (
        root
        / "output"
        / "screener.json"
    )

    screener = load_json_file(
        screener_path,
        {},
    )

    if not isinstance(
        screener,
        dict,
    ):
        raise RuntimeError(
            "스크리너 최신 결과가 객체가 아닙니다."
        )

    screener[
        "배치"
    ] = batch_name

    screener[
        "피드갱신시각"
    ] = now_iso()

    write_json_file(
        batches_root
        / f"{batch_name}.json",
        screener,
    )

    for stock_code in stock_codes:
        source = (
            root
            / "output"
            / f"{stock_code}.json"
        )

        if not source.exists():
            raise RuntimeError(
                f"최신 엔진 종목파일 누락: {source}"
            )

        shutil.copy2(
            source,
            stocks_root
            / source.name,
        )


def build_latest_index(
    root: Path,
    summary: Dict[str, Any],
) -> Dict[str, Any]:
    latest_root = (
        root
        / "data"
        / "latest"
    )

    batches_root = (
        latest_root
        / "batches"
    )

    batch_files = sorted(
        batches_root.glob(
            "*.json"
        )
    )

    row_by_code: Dict[
        str,
        Dict[str, Any],
    ] = {}

    batch_summaries = []

    for batch_path in batch_files:
        payload = load_json_file(
            batch_path,
            {},
        )

        if not isinstance(
            payload,
            dict,
        ):
            continue

        rows = [
            safe_dict(
                row
            )
            for row in safe_list(
                payload.get(
                    "종합순위"
                )
            )
        ]

        batch_name = str(
            payload.get(
                "배치",
                batch_path.stem,
            )
        )

        batch_summaries.append(
            {
                "배치": batch_name,
                "종목수": len(
                    rows
                ),
                "피드갱신시각": payload.get(
                    "피드갱신시각",
                    "",
                ),
            }
        )

        for row in rows:
            stock_code = str(
                row.get(
                    "종목코드",
                    "",
                )
            ).zfill(6)

            if not stock_code:
                continue

            normalized = dict(
                row
            )

            normalized[
                "종목코드"
            ] = stock_code

            normalized[
                "배치"
            ] = batch_name

            row_by_code[
                stock_code
            ] = normalized

    ranking = sorted(
        row_by_code.values(),
        key=lambda row: (
            float(
                row.get(
                    "종합선별점수",
                    0,
                )
                or 0
            ),
            float(
                row.get(
                    "장기점수",
                    0,
                )
                or 0
            ),
            float(
                row.get(
                    "버핏점수",
                    0,
                )
                or 0
            ),
        ),
        reverse=True,
    )

    for rank, row in enumerate(
        ranking,
        start=1,
    ):
        row[
            "전체순위"
        ] = rank

    index_payload = {
        "버전": "1.0.0",
        "생성시각": now_iso(),
        "상태": summary.get(
            "상태",
            "PASS",
        ),
        "최근실행배치": summary.get(
            "요청배치",
            "",
        ),
        "배치수": len(
            batch_summaries
        ),
        "종목수": len(
            ranking
        ),
        "배치": batch_summaries,
        "종합순위": ranking,
        "종목목록": [
            {
                "종목코드": row.get(
                    "종목코드",
                    "",
                ),
                "기업명": row.get(
                    "기업명",
                    "",
                ),
                "배치": row.get(
                    "배치",
                    "",
                ),
            }
            for row in ranking
        ],
        "설명": (
            "weekly-forward-sampling이 생성한 "
            "Google Apps Script 연결용 안정 경로"
        ),
    }

    write_json_file(
        latest_root
        / "index.json",
        index_payload,
    )

    for report_name in (
        "forward_test_report.json",
        "calibration_report.json",
    ):
        source = (
            root
            / "output"
            / report_name
        )

        if source.exists():
            shutil.copy2(
                source,
                latest_root
                / report_name,
            )

    return index_payload


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
        print()
        print(
            "KIS PREFLIGHT CHECK"
        )

        token = get_access_token()

        if not token:
            raise RuntimeError(
                "KIS 인증 서버 연결 실패: "
                + get_token_failure_message()
            )

        print(
            "KIS PREFLIGHT OK"
        )

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

            publish_batch_latest(
                root,
                batch_name,
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

        latest_index = build_latest_index(
            root,
            summary,
        )

        summary[
            "최신피드종목수"
        ] = latest_index[
            "종목수"
        ]

        print(
            "LATEST ENGINE FEED:"
        )

        print(
            "- 종목:",
            latest_index[
                "종목수"
            ],
        )

        print(
            "LATEST_INDEX_FILE="
            "data/latest/index.json"
        )

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
