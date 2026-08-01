"""
주가예측 순방향 검증기 V1

역할
- screen-stocks 실행 결과의 예측 스냅샷을 누적 저장
- 이후 실행 시 만기가 지난 예측을 실제 종가로 평가
- 방향 적중률, 평균수익률, Brier 점수 산출
- 과거 시점 재무자료를 현재 자료로 대체하는 허위 백테스트를 하지 않음

평가 시점
- short_5d: 5거래일, 단기1~5일 확률
- mid_20d: 20거래일, 중기1~8주 확률
- mid_40d: 40거래일, 중기1~8주 확률
- long_126d: 126거래일, 장기6~18개월 확률
- long_252d: 252거래일, 장기6~18개월 확률
- long_378d: 378거래일, 장기6~18개월 확률

사용
    python forward_test.py \
        --screener-file output/screener.json \
        --store data/forward_tests.json \
        --report output/forward_test_report.json

    python forward_test.py \
        --evaluate-only \
        --store data/forward_tests.json \
        --report output/forward_test_report.json
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import requests


STORE_VERSION = "1.0.0"
REPORT_VERSION = "1.0.0"

KST = timezone(
    timedelta(hours=9)
)

YAHOO_CHART_URL = (
    "https://query1.finance.yahoo.com/v8/"
    "finance/chart/{symbol}"
)

HORIZONS = {
    "short_5d": {
        "거래일": 5,
        "예측구간": "단기1~5일",
    },
    "mid_20d": {
        "거래일": 20,
        "예측구간": "중기1~8주",
    },
    "mid_40d": {
        "거래일": 40,
        "예측구간": "중기1~8주",
    },
    "long_126d": {
        "거래일": 126,
        "예측구간": "장기6~18개월",
    },
    "long_252d": {
        "거래일": 252,
        "예측구간": "장기6~18개월",
    },
    "long_378d": {
        "거래일": 378,
        "예측구간": "장기6~18개월",
    },
}


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


def now_iso() -> str:
    return datetime.now(
        KST
    ).isoformat()


def load_json(
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


def save_json(
    path: Path,
    data: Any,
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
            data,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    temporary.replace(
        path
    )


def empty_store() -> Dict[str, Any]:
    return {
        "버전": STORE_VERSION,
        "최종갱신시각": "",
        "기록": [],
    }


def load_store(
    path: Path,
) -> Dict[str, Any]:
    store = load_json(
        path,
        empty_store(),
    )

    if not isinstance(
        store,
        dict,
    ):
        raise RuntimeError(
            "순방향 검증 저장소 루트가 객체가 아닙니다."
        )

    if "기록" not in store:
        store[
            "기록"
        ] = []

    if not isinstance(
        store[
            "기록"
        ],
        list,
    ):
        raise RuntimeError(
            "순방향 검증 저장소의 기록이 목록이 아닙니다."
        )

    store[
        "버전"
    ] = STORE_VERSION

    return store


def prediction_id(
    stock_code: str,
    prediction_date: str,
    engine_version: str,
) -> str:
    raw = (
        f"{stock_code}|"
        f"{prediction_date}|"
        f"{engine_version}"
    )

    digest = hashlib.sha256(
        raw.encode(
            "utf-8"
        )
    ).hexdigest()[:16]

    return (
        f"{stock_code}-"
        f"{prediction_date}-"
        f"{digest}"
    )


def completeness_summary(
    prediction: Dict[str, Any],
) -> Dict[str, Any]:
    completeness = safe_dict(
        prediction.get(
            "데이터완전성"
        )
    )

    true_count = sum(
        value is True
        for value in completeness.values()
    )

    return {
        "정상개수": true_count,
        "전체개수": len(
            completeness
        ),
        "비율": round(
            (
                true_count
                / len(
                    completeness
                )
                * 100.0
            )
            if completeness
            else 0.0,
            2,
        ),
    }


def horizon_snapshot(
    prediction: Dict[str, Any],
    horizon_name: str,
) -> Dict[str, Any]:
    horizon = safe_dict(
        prediction.get(
            horizon_name
        )
    )

    return {
        "점수": safe_float(
            horizon.get(
                "점수"
            )
        ),
        "상승확률": safe_float(
            horizon.get(
                "상승확률"
            )
        ),
        "신뢰도": safe_float(
            horizon.get(
                "신뢰도"
            )
        ),
        "판정": str(
            horizon.get(
                "판정",
                "",
            )
        ),
    }


def build_record(
    stock_data: Dict[str, Any],
) -> Dict[str, Any]:
    stock_code = normalize_stock_code(
        stock_data.get(
            "KIS종목코드"
        )
    )

    company_name = str(
        stock_data.get(
            "기업명",
            "",
        )
    ).strip()

    created_at = str(
        stock_data.get(
            "생성시각",
            "",
        )
    ).strip()

    prediction_date = (
        created_at[:10]
        if len(
            created_at
        ) >= 10
        else datetime.now(
            KST
        ).date().isoformat()
    )

    market = safe_dict(
        stock_data.get(
            "시장정보"
        )
    )

    prediction = safe_dict(
        stock_data.get(
            "주가예측"
        )
    )

    engine_version = str(
        prediction.get(
            "엔진버전",
            "",
        )
    ).strip()

    base_price = safe_float(
        market.get(
            "현재가"
        )
    )

    if not stock_code:
        raise RuntimeError(
            "종목코드가 없습니다."
        )

    if not company_name:
        raise RuntimeError(
            f"{stock_code}: 기업명이 없습니다."
        )

    if base_price <= 0:
        raise RuntimeError(
            f"{stock_code}: 기준가격이 0 이하입니다."
        )

    if not engine_version:
        raise RuntimeError(
            f"{stock_code}: 엔진버전이 없습니다."
        )

    evaluations = {}

    for key, definition in (
        HORIZONS.items()
    ):
        horizon_name = definition[
            "예측구간"
        ]

        probability = safe_float(
            safe_dict(
                prediction.get(
                    horizon_name
                )
            ).get(
                "상승확률"
            )
        )

        evaluations[
            key
        ] = {
            "거래일": definition[
                "거래일"
            ],
            "예측구간": horizon_name,
            "예측상승확률": probability,
            "상태": "대기",
            "평가일": "",
            "평가가격": 0.0,
            "수익률": 0.0,
            "실제상승": None,
            "방향적중": None,
            "Brier점수": None,
        }

    return {
        "ID": prediction_id(
            stock_code,
            prediction_date,
            engine_version,
        ),
        "종목코드": stock_code,
        "기업명": company_name,
        "산업코드": str(
            stock_data.get(
                "산업코드",
                "",
            )
        ),
        "예측일": prediction_date,
        "예측시각": created_at,
        "기준가격": base_price,
        "엔진버전": engine_version,
        "단기1~5일": horizon_snapshot(
            prediction,
            "단기1~5일",
        ),
        "중기1~8주": horizon_snapshot(
            prediction,
            "중기1~8주",
        ),
        "장기6~18개월": horizon_snapshot(
            prediction,
            "장기6~18개월",
        ),
        "데이터완전성": (
            completeness_summary(
                prediction
            )
        ),
        "평가": evaluations,
        "기록시각": now_iso(),
        "최종평가시각": "",
    }


def load_screener_stock_files(
    screener_path: Path,
) -> List[Dict[str, Any]]:
    payload = load_json(
        screener_path,
        {},
    )

    if not isinstance(
        payload,
        dict,
    ):
        raise RuntimeError(
            "screener.json 루트가 객체가 아닙니다."
        )

    rows = safe_list(
        payload.get(
            "종합순위"
        )
    )

    if not rows:
        raise RuntimeError(
            "screener.json에 성공 종목이 없습니다."
        )

    output_dir = screener_path.parent
    stock_data_list = []

    for row in rows:
        row = safe_dict(
            row
        )

        stock_code = normalize_stock_code(
            row.get(
                "종목코드"
            )
        )

        if not stock_code:
            raise RuntimeError(
                "스크리너 행의 종목코드가 비어 있습니다."
            )

        stock_path = (
            output_dir
            / f"{stock_code}.json"
        )

        stock_data = load_json(
            stock_path,
            {},
        )

        if not isinstance(
            stock_data,
            dict,
        ):
            raise RuntimeError(
                f"{stock_path}: 루트가 객체가 아닙니다."
            )

        stock_data_list.append(
            stock_data
        )

    return stock_data_list


def add_records(
    store: Dict[str, Any],
    stock_data_list: List[
        Dict[str, Any]
    ],
) -> Tuple[int, int]:
    records = store[
        "기록"
    ]

    existing_ids = {
        str(
            record.get(
                "ID",
                "",
            )
        )
        for record in records
        if isinstance(
            record,
            dict,
        )
    }

    added = 0
    duplicated = 0

    for stock_data in stock_data_list:
        record = build_record(
            stock_data
        )

        if record[
            "ID"
        ] in existing_ids:
            duplicated += 1
            continue

        records.append(
            record
        )

        existing_ids.add(
            record[
                "ID"
            ]
        )

        added += 1

    records.sort(
        key=lambda record: (
            str(
                record.get(
                    "예측일",
                    "",
                )
            ),
            str(
                record.get(
                    "종목코드",
                    "",
                )
            ),
        )
    )

    return added, duplicated


def request_yahoo_chart(
    symbol: str,
) -> Dict[str, Any]:
    url = YAHOO_CHART_URL.format(
        symbol=quote(
            symbol,
            safe="",
        )
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept": (
            "application/json,text/plain,*/*"
        ),
    }

    params = {
        "range": "5y",
        "interval": "1d",
        "includePrePost": "false",
        "events": "div,splits",
    }

    last_error = ""

    for attempt in range(3):
        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=25,
            )

            if response.status_code == 429:
                last_error = (
                    "Yahoo rate limit"
                )
                time.sleep(
                    3 + attempt * 2
                )
                continue

            response.raise_for_status()

            data = response.json()

            if isinstance(
                data,
                dict,
            ):
                return data

            last_error = (
                "Yahoo 응답이 객체가 아닙니다."
            )

        except Exception as error:
            last_error = (
                f"{type(error).__name__}: "
                f"{error}"
            )

            time.sleep(
                2 + attempt
            )

    raise RuntimeError(
        f"{symbol}: {last_error}"
    )


def parse_price_series(
    data: Dict[str, Any],
) -> List[Dict[str, Any]]:
    chart = safe_dict(
        data.get(
            "chart"
        )
    )

    error = chart.get(
        "error"
    )

    if error:
        raise RuntimeError(
            str(
                error
            )
        )

    results = safe_list(
        chart.get(
            "result"
        )
    )

    if not results:
        return []

    result = safe_dict(
        results[0]
    )

    timestamps = safe_list(
        result.get(
            "timestamp"
        )
    )

    indicators = safe_dict(
        result.get(
            "indicators"
        )
    )

    adjclose_list = safe_list(
        indicators.get(
            "adjclose"
        )
    )

    quote_list = safe_list(
        indicators.get(
            "quote"
        )
    )

    adjusted = []

    if adjclose_list:
        adjusted = safe_list(
            safe_dict(
                adjclose_list[0]
            ).get(
                "adjclose"
            )
        )

    closes = []

    if quote_list:
        closes = safe_list(
            safe_dict(
                quote_list[0]
            ).get(
                "close"
            )
        )

    values = (
        adjusted
        if adjusted
        else closes
    )

    rows_by_date = {}

    for index, timestamp in enumerate(
        timestamps
    ):
        if index >= len(
            values
        ):
            break

        price = safe_float(
            values[
                index
            ]
        )

        if price <= 0:
            continue

        try:
            date = datetime.fromtimestamp(
                int(
                    timestamp
                ),
                tz=timezone.utc,
            ).astimezone(
                KST
            ).date().isoformat()

        except Exception:
            continue

        rows_by_date[
            date
        ] = {
            "날짜": date,
            "종가": price,
        }

    return sorted(
        rows_by_date.values(),
        key=lambda row: row[
            "날짜"
        ],
    )


def fetch_price_series(
    stock_code: str,
) -> Tuple[
    str,
    List[Dict[str, Any]],
]:
    errors = []

    for suffix in (
        ".KS",
        ".KQ",
    ):
        symbol = (
            stock_code
            + suffix
        )

        try:
            data = request_yahoo_chart(
                symbol
            )

            rows = parse_price_series(
                data
            )

            if len(
                rows
            ) >= 20:
                return symbol, rows

            errors.append(
                f"{symbol}: 데이터 {len(rows)}건"
            )

        except Exception as error:
            errors.append(
                f"{symbol}: "
                f"{type(error).__name__}: "
                f"{error}"
            )

    raise RuntimeError(
        " | ".join(
            errors
        )
    )


def target_row(
    price_rows: List[Dict[str, Any]],
    prediction_date: str,
    trading_days: int,
) -> Optional[
    Dict[str, Any]
]:
    future_rows = [
        row
        for row in price_rows
        if str(
            row.get(
                "날짜",
                "",
            )
        ) > prediction_date
    ]

    target_index = (
        trading_days
        - 1
    )

    if target_index < 0:
        return None

    if len(
        future_rows
    ) <= target_index:
        return None

    return future_rows[
        target_index
    ]


def evaluate_record(
    record: Dict[str, Any],
    price_rows: List[Dict[str, Any]],
) -> int:
    prediction_date = str(
        record.get(
            "예측일",
            "",
        )
    )

    base_price = safe_float(
        record.get(
            "기준가격"
        )
    )

    evaluations = safe_dict(
        record.get(
            "평가"
        )
    )

    evaluated_count = 0

    for key, definition in (
        HORIZONS.items()
    ):
        evaluation = safe_dict(
            evaluations.get(
                key
            )
        )

        if evaluation.get(
            "상태"
        ) == "완료":
            continue

        target = target_row(
            price_rows,
            prediction_date,
            definition[
                "거래일"
            ],
        )

        if not target:
            continue

        target_price = safe_float(
            target.get(
                "종가"
            )
        )

        if (
            target_price <= 0
            or base_price <= 0
        ):
            continue

        return_rate = (
            (
                target_price
                / base_price
            )
            - 1.0
        ) * 100.0

        probability = safe_float(
            evaluation.get(
                "예측상승확률"
            )
        )

        actual_up = (
            return_rate > 0.0
        )

        if probability > 50.0:
            direction_hit = (
                actual_up is True
            )

        elif probability < 50.0:
            direction_hit = (
                actual_up is False
            )

        else:
            direction_hit = None

        probability_decimal = (
            probability
            / 100.0
        )

        actual_value = (
            1.0
            if actual_up
            else 0.0
        )

        brier = (
            probability_decimal
            - actual_value
        ) ** 2

        evaluation.update(
            {
                "상태": "완료",
                "평가일": target[
                    "날짜"
                ],
                "평가가격": round(
                    target_price,
                    6,
                ),
                "수익률": round(
                    return_rate,
                    6,
                ),
                "실제상승": actual_up,
                "방향적중": direction_hit,
                "Brier점수": round(
                    brier,
                    8,
                ),
            }
        )

        evaluations[
            key
        ] = evaluation

        evaluated_count += 1

    record[
        "평가"
    ] = evaluations

    if evaluated_count > 0:
        record[
            "최종평가시각"
        ] = now_iso()

    return evaluated_count


def evaluate_store(
    store: Dict[str, Any],
) -> Tuple[
    int,
    List[Dict[str, str]],
]:
    records = [
        record
        for record in store[
            "기록"
        ]
        if isinstance(
            record,
            dict,
        )
    ]

    pending_codes = sorted(
        {
            normalize_stock_code(
                record.get(
                    "종목코드"
                )
            )
            for record in records
            if any(
                safe_dict(
                    evaluation
                ).get(
                    "상태"
                ) != "완료"
                for evaluation in (
                    safe_dict(
                        record.get(
                            "평가"
                        )
                    ).values()
                )
            )
        }
    )

    series_cache = {}
    failures = []

    for stock_code in pending_codes:
        if not stock_code:
            continue

        try:
            symbol, rows = (
                fetch_price_series(
                    stock_code
                )
            )

            series_cache[
                stock_code
            ] = rows

            print(
                "FORWARD PRICE OK:",
                stock_code,
                symbol,
                len(
                    rows
                ),
            )

        except Exception as error:
            failures.append(
                {
                    "종목코드": stock_code,
                    "오류": (
                        f"{type(error).__name__}: "
                        f"{error}"
                    ),
                }
            )

            print(
                "FORWARD PRICE FAIL:",
                stock_code,
                type(error).__name__,
                error,
            )

    evaluated_count = 0

    for record in records:
        stock_code = normalize_stock_code(
            record.get(
                "종목코드"
            )
        )

        rows = series_cache.get(
            stock_code
        )

        if not rows:
            continue

        evaluated_count += evaluate_record(
            record,
            rows,
        )

    return evaluated_count, failures


def metric_for_horizon(
    records: List[Dict[str, Any]],
    horizon_key: str,
) -> Dict[str, Any]:
    completed = []

    for record in records:
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
        ) == "완료":
            completed.append(
                evaluation
            )

    direction_values = [
        evaluation[
            "방향적중"
        ]
        for evaluation in completed
        if evaluation.get(
            "방향적중"
        ) is not None
    ]

    returns = [
        safe_float(
            evaluation.get(
                "수익률"
            )
        )
        for evaluation in completed
    ]

    brier_values = [
        safe_float(
            evaluation.get(
                "Brier점수"
            )
        )
        for evaluation in completed
        if evaluation.get(
            "Brier점수"
        ) is not None
    ]

    probabilities = [
        safe_float(
            evaluation.get(
                "예측상승확률"
            )
        )
        for evaluation in completed
    ]

    actual_up_values = [
        1.0
        if evaluation.get(
            "실제상승"
        ) is True
        else 0.0
        for evaluation in completed
    ]

    return {
        "평가완료": len(
            completed
        ),
        "방향평가가능": len(
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
            (
                sum(
                    returns
                )
                / len(
                    returns
                )
            )
            if returns
            else 0.0,
            4,
        ),
        "평균Brier점수": round(
            (
                sum(
                    brier_values
                )
                / len(
                    brier_values
                )
            )
            if brier_values
            else 0.0,
            6,
        ),
        "평균예측상승확률": round(
            (
                sum(
                    probabilities
                )
                / len(
                    probabilities
                )
            )
            if probabilities
            else 0.0,
            2,
        ),
        "실제상승비율": round(
            (
                sum(
                    actual_up_values
                )
                / len(
                    actual_up_values
                )
                * 100.0
            )
            if actual_up_values
            else 0.0,
            2,
        ),
    }


def build_report(
    store: Dict[str, Any],
    price_failures: List[
        Dict[str, str]
    ],
) -> Dict[str, Any]:
    records = [
        record
        for record in store[
            "기록"
        ]
        if isinstance(
            record,
            dict,
        )
    ]

    metrics = {
        key: metric_for_horizon(
            records,
            key,
        )
        for key in HORIZONS
    }

    pending_count = 0
    completed_count = 0

    for record in records:
        for evaluation in safe_dict(
            record.get(
                "평가"
            )
        ).values():
            if safe_dict(
                evaluation
            ).get(
                "상태"
            ) == "완료":
                completed_count += 1
            else:
                pending_count += 1

    return {
        "버전": REPORT_VERSION,
        "생성시각": now_iso(),
        "예측기록수": len(
            records
        ),
        "평가완료수": completed_count,
        "평가대기수": pending_count,
        "구간별성과": metrics,
        "가격수집실패": price_failures,
        "설명": {
            "방향적중률": (
                "예측상승확률이 50%보다 크면 상승, "
                "작으면 하락으로 판정합니다. "
                "정확히 50%는 방향평가에서 제외합니다."
            ),
            "Brier점수": (
                "0에 가까울수록 확률예측이 정확합니다."
            ),
            "주의": (
                "이 결과는 실제 예측 시점 이후의 가격으로 "
                "평가하는 순방향 검증입니다."
            ),
        },
    }


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "주가예측 순방향 기록·평가"
        )
    )

    parser.add_argument(
        "--screener-file",
        default="output/screener.json",
        help=(
            "스크리너 결과 JSON"
        ),
    )

    parser.add_argument(
        "--store",
        default="data/forward_tests.json",
        help=(
            "누적 저장소 JSON"
        ),
    )

    parser.add_argument(
        "--report",
        default=(
            "output/"
            "forward_test_report.json"
        ),
        help=(
            "성과 보고서 JSON"
        ),
    )

    parser.add_argument(
        "--evaluate-only",
        action="store_true",
        help=(
            "새 예측 기록 없이 기존 기록만 평가"
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_arguments()

    store_path = Path(
        args.store
    )

    report_path = Path(
        args.report
    )

    store = load_store(
        store_path
    )

    added = 0
    duplicated = 0

    if not args.evaluate_only:
        screener_path = Path(
            args.screener_file
        )

        stock_data_list = (
            load_screener_stock_files(
                screener_path
            )
        )

        added, duplicated = add_records(
            store,
            stock_data_list,
        )

    evaluated_count, failures = (
        evaluate_store(
            store
        )
    )

    store[
        "최종갱신시각"
    ] = now_iso()

    save_json(
        store_path,
        store,
    )

    report = build_report(
        store,
        failures,
    )

    save_json(
        report_path,
        report,
    )

    print(
        "FORWARD TEST RESULT"
    )

    print(
        "- 신규 예측:",
        added,
    )

    print(
        "- 중복 제외:",
        duplicated,
    )

    print(
        "- 이번 평가 완료:",
        evaluated_count,
    )

    print(
        "- 누적 예측:",
        report[
            "예측기록수"
        ],
    )

    print(
        "- 누적 평가 완료:",
        report[
            "평가완료수"
        ],
    )

    print(
        "- 평가 대기:",
        report[
            "평가대기수"
        ],
    )

    print(
        "- 가격수집 실패:",
        len(
            failures
        ),
    )

    print(
        "STORE_FILE=",
        store_path,
        sep="",
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
