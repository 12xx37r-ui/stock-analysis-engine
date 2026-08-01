"""
다종목 스크리너 출력 검증기 V1

검증:
- 요청 종목과 성공·실패 수 일치
- 종합·버핏 순위 연속성
- 실제 저평가 종목만 저평가순위 포함
- 개별 종목 JSON 검증
- CSV 종목 수·코드 일치
- 이전 실행의 잔여 JSON 차단
"""

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from validate_output import validate_output


EXPECTED_SCREENER_VERSION = (
    "1.1.0-ranking-integrity"
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


def normalize_stock_code(
    value: Any,
) -> str:
    text = str(
        value
        or ""
    ).strip()

    if not text:
        return ""

    if not text.isdigit():
        return text

    return text.zfill(6)


def parse_stock_codes(
    raw_value: str,
) -> List[str]:
    normalized = []

    for value in str(
        raw_value
        or ""
    ).replace(
        ";",
        ",",
    ).split(
        ","
    ):
        value = value.strip()

        if not value:
            continue

        code = normalize_stock_code(
            value
        )

        if code not in normalized:
            normalized.append(
                code
            )

    return normalized


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


def validate_rank_sequence(
    name: str,
    rows: List[Dict[str, Any]],
    rank_key: str,
    result: Result,
) -> None:
    ranks = [
        row.get(
            rank_key
        )
        for row in rows
    ]

    expected = list(
        range(
            1,
            len(rows) + 1,
        )
    )

    if ranks != expected:
        result.error(
            f"{name} 순위 불연속: "
            f"{ranks}, 기대값 {expected}"
        )


def validate_screener(
    output_dir: Path,
    requested_codes: List[str],
) -> Result:
    result = Result()

    screener_path = (
        output_dir
        / "screener.json"
    )

    csv_path = (
        output_dir
        / "screener.csv"
    )

    if not screener_path.exists():
        result.error(
            "output/screener.json 없음"
        )
        return result

    if not csv_path.exists():
        result.error(
            "output/screener.csv 없음"
        )

    try:
        payload = json.loads(
            screener_path.read_text(
                encoding="utf-8"
            )
        )

    except Exception as error:
        result.error(
            "screener.json 읽기 실패: "
            f"{type(error).__name__}: "
            f"{error}"
        )
        return result

    if payload.get(
        "스크리너버전"
    ) != EXPECTED_SCREENER_VERSION:
        result.error(
            "스크리너버전 불일치: "
            f"{payload.get('스크리너버전')}"
        )

    payload_requested = [
        normalize_stock_code(
            value
        )
        for value in safe_list(
            payload.get(
                "요청종목코드"
            )
        )
    ]

    if payload_requested != requested_codes:
        result.error(
            "요청종목코드 불일치: "
            f"JSON {payload_requested}, "
            f"실행 {requested_codes}"
        )

    total_rows = [
        safe_dict(
            row
        )
        for row in safe_list(
            payload.get(
                "종합순위"
            )
        )
    ]

    buffett_rows = [
        safe_dict(
            row
        )
        for row in safe_list(
            payload.get(
                "버핏순위"
            )
        )
    ]

    valuation_rows = [
        safe_dict(
            row
        )
        for row in safe_list(
            payload.get(
                "저평가순위"
            )
        )
    ]

    failures = [
        safe_dict(
            row
        )
        for row in safe_list(
            payload.get(
                "실패"
            )
        )
    ]

    success_count = int(
        payload.get(
            "성공종목수",
            -1,
        )
    )

    failure_count = int(
        payload.get(
            "실패종목수",
            -1,
        )
    )

    if success_count != len(
        total_rows
    ):
        result.error(
            "성공종목수 불일치"
        )

    if failure_count != len(
        failures
    ):
        result.error(
            "실패종목수 불일치"
        )

    if (
        success_count
        + failure_count
        != len(
            requested_codes
        )
    ):
        result.error(
            "성공+실패 종목 수가 "
            "요청 종목 수와 다름"
        )

    total_codes = [
        normalize_stock_code(
            row.get(
                "종목코드"
            )
        )
        for row in total_rows
    ]

    if len(
        total_codes
    ) != len(
        set(
            total_codes
        )
    ):
        result.error(
            "종합순위에 종목코드 중복"
        )

    if set(
        total_codes
    ) - set(
        requested_codes
    ):
        result.error(
            "요청하지 않은 종목이 "
            "종합순위에 포함됨"
        )

    validate_rank_sequence(
        "종합순위",
        total_rows,
        "종합순위",
        result,
    )

    validate_rank_sequence(
        "버핏순위",
        buffett_rows,
        "버핏순위",
        result,
    )

    validate_rank_sequence(
        "저평가순위",
        valuation_rows,
        "저평가순위",
        result,
    )

    for row in valuation_rows:
        if row.get(
            "저평가후보"
        ) is not True:
            result.error(
                "저평가순위에 "
                "비후보 종목 포함"
            )

        if float(
            row.get(
                "현재가대비적정가",
                0,
            )
        ) <= 0:
            result.error(
                "저평가순위에 "
                "상승여력 0 이하 종목 포함"
            )

        if "고평가" in str(
            row.get(
                "가치판단",
                "",
            )
        ):
            result.error(
                "저평가순위에 "
                "고평가 종목 포함"
            )

    for row in total_rows:
        is_candidate = (
            row.get(
                "저평가후보"
            ) is True
        )

        rank = int(
            row.get(
                "저평가순위",
                0,
            )
        )

        if is_candidate and rank <= 0:
            result.error(
                "저평가후보의 순위 누락: "
                f"{row.get('종목코드')}"
            )

        if not is_candidate and rank != 0:
            result.error(
                "비저평가 종목에 순위 부여: "
                f"{row.get('종목코드')}"
            )

    expected_json_names = {
        f"{code}.json"
        for code in total_codes
    }

    expected_json_names.add(
        "screener.json"
    )

    actual_json_names = {
        path.name
        for path in output_dir.glob(
            "*.json"
        )
        if path.is_file()
    }

    unexpected_json = (
        actual_json_names
        - expected_json_names
    )

    if unexpected_json:
        result.error(
            "이전 실행 잔여 JSON 발견: "
            + ",".join(
                sorted(
                    unexpected_json
                )
            )
        )

    missing_json = (
        expected_json_names
        - actual_json_names
    )

    if missing_json:
        result.error(
            "필수 JSON 누락: "
            + ",".join(
                sorted(
                    missing_json
                )
            )
        )

    for stock_code in total_codes:
        stock_path = (
            output_dir
            / f"{stock_code}.json"
        )

        if not stock_path.exists():
            continue

        try:
            stock_data = json.loads(
                stock_path.read_text(
                    encoding="utf-8"
                )
            )

        except Exception as error:
            result.error(
                f"{stock_code}.json 읽기 실패: "
                f"{type(error).__name__}: "
                f"{error}"
            )
            continue

        stock_result = validate_output(
            stock_data,
            expected_stock_code=(
                stock_code
            ),
        )

        for error in stock_result.errors:
            result.error(
                f"{stock_code}: {error}"
            )

        for warning in stock_result.warnings:
            result.warning(
                f"{stock_code}: {warning}"
            )

    if csv_path.exists():
        try:
            with csv_path.open(
                "r",
                encoding="utf-8-sig",
                newline="",
            ) as file:
                csv_rows = list(
                    csv.DictReader(
                        file
                    )
                )

            csv_codes = [
                normalize_stock_code(
                    row.get(
                        "종목코드"
                    )
                )
                for row in csv_rows
            ]

            if csv_codes != total_codes:
                result.error(
                    "screener.csv 종목 순서·코드 "
                    "불일치"
                )

        except Exception as error:
            result.error(
                "screener.csv 읽기 실패: "
                f"{type(error).__name__}: "
                f"{error}"
            )

    result.info(
        "요청 "
        f"{len(requested_codes)}개, "
        f"성공 {success_count}개, "
        f"실패 {failure_count}개"
    )

    result.info(
        "저평가후보 "
        f"{len(valuation_rows)}개"
    )

    result.info(
        "개별 종목 JSON "
        f"{len(total_codes)}개 검증"
    )

    return result


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
            "다종목 스크리너 출력 검증"
        )
    )

    parser.add_argument(
        "--stock-codes",
        required=True,
        help=(
            "쉼표로 구분한 요청 종목코드"
        ),
    )

    parser.add_argument(
        "--output-dir",
        default="output",
        help=(
            "출력 디렉터리"
        ),
    )

    args = parser.parse_args()

    requested_codes = parse_stock_codes(
        args.stock_codes
    )

    result = validate_screener(
        Path(
            args.output_dir
        ),
        requested_codes,
    )

    print(
        "SCREENER OUTPUT VALIDATION"
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
