"""
다종목 스크리너 V1.1

사용:
    python screener.py \
        --stock-codes "005930,000660" \
        --industry-code auto

기능:
- 여러 종목을 한 번의 실행에서 분석
- 글로벌시장 데이터는 실행당 1회만 수집
- 산업 데이터는 산업코드별 1회만 수집
- 종목별 출력 JSON 생성
- 종합순위·버핏순위 생성
- 실제 저평가 종목만 저평가순위에 포함
- 이전 실행 잔여 output 파일 자동 제거
- output/screener.json
- output/screener.csv
- 각 종목 결과를 validate_output.py로 검증
"""

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from analyzers.disclosure import analyze_disclosures
from analyzers.financial import analyze_financial
from analyzers.fundamentals import analyze_fundamentals
from analyzers.global_market import analyze_global_market
from analyzers.industry import analyze_industry
from analyzers.valuation import calculate_value
from collectors.dart import get_financial
from collectors.disclosure import get_recent_disclosures
from collectors.fundamentals import get_fundamentals_bundle
from collectors.global_market import get_global_market_bundle
from collectors.history import get_history_bundle
from collectors.industry import get_industry_bundle
from collectors.market import finalize_market_data, get_market_data
from collectors.news import get_company_news
from collectors.technical import get_stock_technical_bundle
from main import (
    build_disclosure_summary,
    build_fundamentals_summary,
    build_global_summary,
    build_history_summary,
    build_industry_summary,
    LIVE_INDUSTRY_CODES,
    resolve_target,
    safe_execute,
    save_result,
)
from predictor import predict_stock
from validate_output import validate_output


DEFAULT_STOCK_CODES = (
    "005930,000660"
)

DEFAULT_INDUSTRY_CODE = "auto"
DEFAULT_MARKET_CODE = "K"
MAX_STOCKS = 10
SCREENER_VERSION = "1.1.0-ranking-integrity"


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


def clamp(
    value: float,
    minimum: float,
    maximum: float,
) -> float:
    return max(
        minimum,
        min(
            maximum,
            value,
        ),
    )


def prepare_output_directory() -> None:
    """
    현재 실행 결과만 Artifact에 포함되도록
    이전 JSON·CSV 산출물을 제거한다.
    """
    output_dir = Path(
        "output"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    removed = []

    for pattern in (
        "*.json",
        "*.csv",
    ):
        for path in output_dir.glob(
            pattern
        ):
            if not path.is_file():
                continue

            path.unlink()
            removed.append(
                path.name
            )

    if removed:
        print(
            "OUTPUT CLEANED:",
            ",".join(
                sorted(
                    removed
                )
            ),
        )


def parse_stock_codes(
    raw_value: str,
) -> List[str]:
    values = re.split(
        r"[\s,;]+",
        str(
            raw_value
            or ""
        ).strip(),
    )

    normalized: List[str] = []

    for value in values:
        if not value:
            continue

        if not value.isdigit():
            raise ValueError(
                f"종목코드는 숫자만 입력해야 합니다: "
                f"{value}"
            )

        stock_code = value.zfill(6)

        if len(stock_code) != 6:
            raise ValueError(
                f"6자리 종목코드가 아닙니다: "
                f"{value}"
            )

        if stock_code not in normalized:
            normalized.append(
                stock_code
            )

    if not normalized:
        raise ValueError(
            "분석할 종목코드가 없습니다."
        )

    if len(normalized) > MAX_STOCKS:
        raise ValueError(
            f"한 번에 최대 {MAX_STOCKS}개까지 "
            f"실행할 수 있습니다."
        )

    return normalized


def factor_signal(
    prediction: Dict[str, Any],
    horizon_name: str,
    factor_name: str,
) -> float:
    horizon = safe_dict(
        prediction.get(
            horizon_name
        )
    )

    factors = horizon.get(
        "요소별평가",
        [],
    )

    if not isinstance(
        factors,
        list,
    ):
        return 0.0

    for factor in factors:
        factor = safe_dict(
            factor
        )

        if factor.get(
            "요소"
        ) == factor_name:
            return safe_float(
                factor.get(
                    "신호"
                )
            )

    return 0.0


def completeness_score(
    prediction: Dict[str, Any],
) -> Tuple[float, int, int]:
    completeness = safe_dict(
        prediction.get(
            "데이터완전성"
        )
    )

    total = len(
        completeness
    )

    true_count = sum(
        value is True
        for value in completeness.values()
    )

    score = (
        true_count
        / total
        * 100.0
        if total > 0
        else 0.0
    )

    return (
        round(
            score,
            2,
        ),
        true_count,
        total,
    )


def make_ranking_row(
    result: Dict[str, Any],
) -> Dict[str, Any]:
    prediction = safe_dict(
        result.get(
            "주가예측"
        )
    )

    short_term = safe_dict(
        prediction.get(
            "단기1~5일"
        )
    )

    mid_term = safe_dict(
        prediction.get(
            "중기1~8주"
        )
    )

    long_term = safe_dict(
        prediction.get(
            "장기6~18개월"
        )
    )

    buffett = safe_dict(
        safe_dict(
            result.get(
                "재무분석"
            )
        ).get(
            "버핏평가"
        )
    )

    valuation = safe_dict(
        result.get(
            "가치평가"
        )
    )

    completeness, true_count, total_count = (
        completeness_score(
            prediction
        )
    )

    short_score = safe_float(
        short_term.get(
            "점수"
        )
    )

    mid_score = safe_float(
        mid_term.get(
            "점수"
        )
    )

    long_score = safe_float(
        long_term.get(
            "점수"
        )
    )

    buffett_score = safe_float(
        buffett.get(
            "점수"
        )
    )

    valuation_signal = factor_signal(
        prediction,
        "장기6~18개월",
        "가치평가·안전마진",
    )

    valuation_score = clamp(
        (
            valuation_signal
            + 100.0
        )
        / 2.0,
        0.0,
        100.0,
    )

    fair_value_gap = safe_float(
        valuation.get(
            "현재가대비"
        )
    )

    valuation_judgment = str(
        valuation.get(
            "판단",
            "",
        )
    ).strip()

    undervalued_candidate = (
        fair_value_gap > 0.0
        and "고평가"
        not in valuation_judgment
    )

    total_score = (
        long_score * 0.30
        + mid_score * 0.20
        + short_score * 0.10
        + buffett_score * 0.20
        + valuation_score * 0.10
        + completeness * 0.10
    )

    return {
        "종합순위": 0,
        "버핏순위": 0,
        "저평가순위": 0,
        "저평가후보": (
            undervalued_candidate
        ),
        "기업명": result.get(
            "기업명",
            "",
        ),
        "종목코드": result.get(
            "KIS종목코드",
            "",
        ),
        "산업코드": result.get(
            "산업코드",
            "",
        ),
        "현재가": safe_float(
            safe_dict(
                result.get(
                    "시장정보"
                )
            ).get(
                "현재가"
            )
        ),
        "종합선별점수": round(
            total_score,
            2,
        ),
        "단기점수": round(
            short_score,
            2,
        ),
        "단기상승확률": safe_float(
            short_term.get(
                "상승확률"
            )
        ),
        "중기점수": round(
            mid_score,
            2,
        ),
        "중기상승확률": safe_float(
            mid_term.get(
                "상승확률"
            )
        ),
        "장기점수": round(
            long_score,
            2,
        ),
        "장기상승확률": safe_float(
            long_term.get(
                "상승확률"
            )
        ),
        "버핏점수": round(
            buffett_score,
            2,
        ),
        "버핏판정": buffett.get(
            "판정",
            "",
        ),
        "가치평가점수": round(
            valuation_score,
            2,
        ),
        "현재가대비적정가": round(
            fair_value_gap,
            2,
        ),
        "가치판단": valuation_judgment,
        "데이터완전성점수": (
            completeness
        ),
        "데이터완전성": (
            f"{true_count}/{total_count}"
        ),
        "엔진버전": prediction.get(
            "엔진버전",
            "",
        ),
    }



def assign_ranks(
    rows: List[Dict[str, Any]],
) -> None:
    for row in rows:
        row[
            "종합순위"
        ] = 0
        row[
            "버핏순위"
        ] = 0
        row[
            "저평가순위"
        ] = 0

    total_sorted = sorted(
        rows,
        key=lambda row: (
            row[
                "종합선별점수"
            ],
            row[
                "장기점수"
            ],
            row[
                "버핏점수"
            ],
        ),
        reverse=True,
    )

    for rank, row in enumerate(
        total_sorted,
        start=1,
    ):
        row[
            "종합순위"
        ] = rank

    buffett_sorted = sorted(
        rows,
        key=lambda row: (
            row[
                "버핏점수"
            ],
            row[
                "장기점수"
            ],
        ),
        reverse=True,
    )

    for rank, row in enumerate(
        buffett_sorted,
        start=1,
    ):
        row[
            "버핏순위"
        ] = rank

    valuation_candidates = [
        row
        for row in rows
        if row.get(
            "저평가후보"
        ) is True
    ]

    valuation_sorted = sorted(
        valuation_candidates,
        key=lambda row: (
            row[
                "현재가대비적정가"
            ],
            row[
                "가치평가점수"
            ],
            row[
                "버핏점수"
            ],
        ),
        reverse=True,
    )

    for rank, row in enumerate(
        valuation_sorted,
        start=1,
    ):
        row[
            "저평가순위"
        ] = rank



def empty_industry_result(
    industry_code: str,
) -> Tuple[
    Dict[str, Any],
    Dict[str, Any],
]:
    return (
        {
            "전체수집상태": "미적용",
            "산업코드": industry_code,
            "산업명": "미분류",
            "자산": {},
            "수집오류": [],
        },
        {
            "분석상태": "미적용",
            "중기산업선행": {},
            "장기산업사이클": {},
            "산업국면": "미분류",
        },
    )


def analyze_one_stock(
    stock_code: str,
    requested_industry: str,
    market_code: str,
    global_bundle: Dict[str, Any],
    global_analysis: Dict[str, Any],
    industry_cache: Dict[
        str,
        Tuple[
            Dict[str, Any],
            Dict[str, Any],
        ],
    ],
) -> Dict[str, Any]:
    target = resolve_target(
        stock_code,
        requested_industry,
    )

    company = target[
        "기업명"
    ]

    dart_code = target[
        "DART기업코드"
    ]

    resolved_stock_code = target[
        "종목코드"
    ]

    industry_code = target[
        "산업코드"
    ]

    print()
    print(
        "SCREEN TARGET:",
        company,
        resolved_stock_code,
        "INDUSTRY",
        industry_code,
    )

    dart_raw = get_financial(
        dart_code
    )

    financial = analyze_financial(
        dart_raw,
        industry_code=industry_code,
    )

    market = get_market_data(
        resolved_stock_code
    )

    history_bundle = safe_execute(
        "HISTORY",
        lambda: get_history_bundle(
            resolved_stock_code,
            market_code=market_code,
        ),
        {
            "전체수집상태": "실패",
            "가격추세": {},
            "누적수급": {},
            "프로그램매매": {},
            "수집오류": [],
        },
    )

    market[
        "과거데이터"
    ] = build_history_summary(
        history_bundle
    )

    technical_bundle = safe_execute(
        "MULTI TIMEFRAME TECHNICAL",
        lambda: get_stock_technical_bundle(
            resolved_stock_code,
            market_code=market_code,
            history_bundle=history_bundle,
        ),
        {
            "수집상태": "실패",
            "응답메시지": "멀티타임프레임 차트 수집 중 예외",
            "일봉": {},
            "주봉": {},
            "월봉": {},
            "수집오류": [],
        },
    )

    news_bundle = safe_execute(
        "COMPANY NEWS",
        lambda: get_company_news(
            company,
            maximum_items=30,
        ),
        {
            "수집상태": "실패",
            "응답메시지": "기업 뉴스 수집 중 예외",
            "뉴스개수": 0,
            "뉴스목록": [],
            "분석": {
                "분석상태": "실패",
                "신호": 0.0,
                "데이터품질": 0.0,
                "판정": "중립",
            },
        },
    )

    disclosure_bundle = safe_execute(
        "DISCLOSURE",
        lambda: get_recent_disclosures(
            dart_code,
            days=30,
            page_count=100,
        ),
        {
            "수집상태": "실패",
            "응답메시지": (
                "공시 수집 중 예외"
            ),
            "공시개수": 0,
            "공시목록": [],
        },
    )

    disclosure_analysis = safe_execute(
        "DISCLOSURE ANALYSIS",
        lambda: analyze_disclosures(
            disclosure_bundle
        ),
        {
            "분석상태": "실패",
            "신호": 0.0,
            "데이터품질": 0,
            "판정": "중립",
        },
    )

    fundamentals_bundle = safe_execute(
        "DART FUNDAMENTALS",
        lambda: get_fundamentals_bundle(
            dart_code
        ),
        {
            "전체수집상태": "실패",
            "재무기간": {},
            "배당": {},
            "자기주식": {},
        },
    )

    market = finalize_market_data(
        market,
        resolved_stock_code,
        market_code=market_code,
        fundamentals_bundle=fundamentals_bundle,
        technical_bundle=technical_bundle,
    )

    fundamentals_analysis = safe_execute(
        "FUNDAMENTALS ANALYSIS",
        lambda: analyze_fundamentals(
            fundamentals_bundle
        ),
        {
            "분석상태": "실패",
            "분기실적": {},
            "향후이익방향대용": {},
            "현금흐름재무안전성": {},
            "주주환원": {},
        },
    )

    if industry_code not in industry_cache:
        if industry_code not in LIVE_INDUSTRY_CODES:
            industry_cache[
                industry_code
            ] = empty_industry_result(
                industry_code
            )

        else:
            industry_bundle = safe_execute(
                "INDUSTRY",
                lambda: get_industry_bundle(
                    industry_code
                ),
                {
                    "전체수집상태": "실패",
                    "산업코드": industry_code,
                    "산업명": industry_code,
                    "자산": {},
                    "수집오류": [],
                },
            )

            industry_analysis = safe_execute(
                "INDUSTRY ANALYSIS",
                lambda: analyze_industry(
                    industry_bundle,
                    global_bundle,
                ),
                {
                    "분석상태": "실패",
                    "중기산업선행": {},
                    "장기산업사이클": {},
                    "산업국면": "판정불가",
                },
            )

            industry_cache[
                industry_code
            ] = (
                industry_bundle,
                industry_analysis,
            )

    (
        industry_bundle,
        industry_analysis,
    ) = industry_cache[
        industry_code
    ]

    valuation = calculate_value(
        financial,
        market,
        fundamentals_analysis,
        fundamentals_bundle,
        industry_analysis,
        industry_bundle,
        target.get("기업조회", {}),
    )

    prediction = predict_stock(
        market,
        financial,
        valuation,
        disclosure_analysis=(
            disclosure_analysis
        ),
        global_analysis=(
            global_analysis
        ),
        fundamentals_analysis=(
            fundamentals_analysis
        ),
        industry_analysis=(
            industry_analysis
        ),
        news_analysis=(
            news_bundle.get("분석", {})
            if isinstance(news_bundle, dict)
            else {}
        ),
        technical_analysis=(
            technical_bundle
        ),
    )

    result = {
        "기업명": company,
        "DART기업코드": dart_code,
        "KIS종목코드": (
            resolved_stock_code
        ),
        "산업코드": industry_code,
        "기업조회정보": target[
            "기업조회"
        ],
        "생성시각": (
            datetime.now().isoformat()
        ),
        "재무분석": financial,
        "시장정보": market,
        "공시정보": (
            build_disclosure_summary(
                disclosure_bundle,
                disclosure_analysis,
            )
        ),
        "글로벌시장": (
            build_global_summary(
                global_bundle,
                global_analysis,
            )
        ),
        "기업기초데이터": (
            build_fundamentals_summary(
                fundamentals_bundle,
                fundamentals_analysis,
            )
        ),
        "산업분석": (
            build_industry_summary(
                industry_bundle,
                industry_analysis,
            )
        ),
        "기술분석": technical_bundle,
        "뉴스분석": news_bundle,
        "가치평가": valuation,
        "주가예측": prediction,
    }

    validation = validate_output(
        result,
        expected_stock_code=(
            resolved_stock_code
        ),
    )

    if validation.errors:
        raise RuntimeError(
            "출력 검증 실패: "
            + " | ".join(
                validation.errors
            )
        )

    save_result(
        result,
        resolved_stock_code,
    )

    return result


def save_screener_outputs(
    stock_codes: List[str],
    rows: List[Dict[str, Any]],
    failures: List[Dict[str, Any]],
) -> None:
    output_dir = Path(
        "output"
    )

    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    total_ranking = sorted(
        rows,
        key=lambda row: row[
            "종합순위"
        ],
    )

    buffett_ranking = sorted(
        rows,
        key=lambda row: row[
            "버핏순위"
        ],
    )

    valuation_ranking = sorted(
        (
            row
            for row in rows
            if row.get(
                "저평가후보"
            ) is True
        ),
        key=lambda row: row[
            "저평가순위"
        ],
    )

    overvalued_list = sorted(
        (
            row
            for row in rows
            if row.get(
                "저평가후보"
            ) is not True
        ),
        key=lambda row: (
            row[
                "현재가대비적정가"
            ],
            row[
                "가치평가점수"
            ],
        ),
        reverse=True,
    )

    payload = {
        "스크리너버전": (
            SCREENER_VERSION
        ),
        "생성시각": (
            datetime.now().isoformat()
        ),
        "요청종목코드": stock_codes,
        "성공종목수": len(rows),
        "실패종목수": len(failures),
        "종합순위": total_ranking,
        "버핏순위": buffett_ranking,
        "저평가순위": valuation_ranking,
        "저평가후보수": len(
            valuation_ranking
        ),
        "비저평가목록": (
            overvalued_list
        ),
        "실패": failures,
        "산정방식": {
            "종합선별점수": (
                "장기점수 30% + 중기점수 20% + "
                "단기점수 10% + 버핏점수 20% + "
                "가치평가점수 10% + 데이터완전성 10%"
            ),
            "저평가후보": (
                "적정가가 현재가보다 높고 "
                "가치판단이 고평가가 아닌 종목만 포함"
            ),
            "저평가순위": (
                "현재가 대비 적정가 상승여력, "
                "가치평가점수, 버핏점수 순"
            ),
            "주의": (
                "종합순위는 선별 보조지표이며 "
                "매수·매도 지시가 아닙니다."
            ),
        },
    }

    (
        output_dir
        / "screener.json"
    ).write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    fieldnames = [
        "종합순위",
        "버핏순위",
        "저평가순위",
        "저평가후보",
        "기업명",
        "종목코드",
        "산업코드",
        "현재가",
        "종합선별점수",
        "단기점수",
        "단기상승확률",
        "중기점수",
        "중기상승확률",
        "장기점수",
        "장기상승확률",
        "버핏점수",
        "버핏판정",
        "가치평가점수",
        "현재가대비적정가",
        "가치판단",
        "데이터완전성점수",
        "데이터완전성",
        "엔진버전",
    ]

    with (
        output_dir
        / "screener.csv"
    ).open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )

        writer.writeheader()

        for row in total_ranking:
            writer.writerow(
                {
                    key: row.get(
                        key,
                        "",
                    )
                    for key in fieldnames
                }
            )



def print_summary(
    rows: List[Dict[str, Any]],
    failures: List[Dict[str, Any]],
) -> None:
    print()
    print(
        "SCREENER RESULT"
    )

    if rows:
        print(
            "종합순위"
        )

        for row in sorted(
            rows,
            key=lambda item: item[
                "종합순위"
            ],
        ):
            valuation_label = (
                f"저평가 {row['저평가순위']}위"
                if row.get(
                    "저평가후보"
                ) is True
                else "저평가 아님"
            )

            print(
                f"{row['종합순위']}. "
                f"{row['기업명']} "
                f"({row['종목코드']}) "
                f"종합 {row['종합선별점수']:.2f} "
                f"장기 {row['장기점수']:.0f} "
                f"버핏 {row['버핏점수']:.0f} "
                f"가치 {row['가치평가점수']:.2f} "
                f"{valuation_label}"
            )

        valuation_candidates = [
            row
            for row in rows
            if row.get(
                "저평가후보"
            ) is True
        ]

        if valuation_candidates:
            print(
                "저평가순위"
            )

            for row in sorted(
                valuation_candidates,
                key=lambda item: item[
                    "저평가순위"
                ],
            ):
                print(
                    f"{row['저평가순위']}. "
                    f"{row['기업명']} "
                    f"({row['종목코드']}) "
                    f"상승여력 "
                    f"{row['현재가대비적정가']:.2f}%"
                )

        else:
            print(
                "저평가후보 없음"
            )

    if failures:
        print(
            "실패종목"
        )

        for failure in failures:
            print(
                "-",
                failure[
                    "종목코드"
                ],
                failure[
                    "오류"
                ],
            )

    print(
        "OUTPUT_FILE=output/screener.json"
    )
    print(
        "OUTPUT_FILE=output/screener.csv"
    )



def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "여러 국내주식 분석 및 순위 생성"
        )
    )

    parser.add_argument(
        "--stock-codes",
        default=DEFAULT_STOCK_CODES,
        help=(
            "쉼표로 구분한 6자리 종목코드"
        ),
    )

    parser.add_argument(
        "--industry-code",
        default=DEFAULT_INDUSTRY_CODE,
        choices=(
            "auto",
            "semiconductor",
            "automotive",
            "battery",
            "biotechnology",
            "construction",
            "finance",
            "none",
        ),
        help=(
            "산업분석 코드"
        ),
    )

    parser.add_argument(
        "--market-code",
        default=DEFAULT_MARKET_CODE,
        help=(
            "KIS 시장코드 보조값"
        ),
    )

    return parser.parse_args()


def main() -> int:
    args = parse_arguments()

    try:
        stock_codes = parse_stock_codes(
            args.stock_codes
        )

    except ValueError as error:
        print(
            "SCREENER FAILED:",
            error,
        )
        return 1

    print(
        "START SCREENER:",
        ",".join(
            stock_codes
        ),
    )

    prepare_output_directory()

    global_bundle = safe_execute(
        "GLOBAL MARKET",
        get_global_market_bundle,
        {
            "전체수집상태": "실패",
            "자산": {},
            "수집오류": [],
        },
    )

    global_analysis = safe_execute(
        "GLOBAL ANALYSIS",
        lambda: analyze_global_market(
            global_bundle
        ),
        {
            "분석상태": "실패",
            "단기신호": 0.0,
            "단기데이터품질": 0.0,
            "중기신호": 0.0,
            "중기데이터품질": 0.0,
        },
    )

    industry_cache: Dict[
        str,
        Tuple[
            Dict[str, Any],
            Dict[str, Any],
        ],
    ] = {}

    ranking_rows: List[
        Dict[str, Any]
    ] = []

    failures: List[
        Dict[str, Any]
    ] = []

    for stock_code in stock_codes:
        try:
            result = analyze_one_stock(
                stock_code=stock_code,
                requested_industry=(
                    args.industry_code
                ),
                market_code=(
                    args.market_code
                ),
                global_bundle=(
                    global_bundle
                ),
                global_analysis=(
                    global_analysis
                ),
                industry_cache=(
                    industry_cache
                ),
            )

            ranking_rows.append(
                make_ranking_row(
                    result
                )
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
                "SCREEN ERROR:",
                stock_code,
                type(error).__name__,
                error,
            )

    if not ranking_rows:
        print(
            "SCREENER FAILED: "
            "정상 분석된 종목이 없습니다."
        )
        return 1

    assign_ranks(
        ranking_rows
    )

    save_screener_outputs(
        stock_codes,
        ranking_rows,
        failures,
    )

    print_summary(
        ranking_rows,
        failures,
    )

    return 0


if __name__ == "__main__":
    sys.exit(
        main()
    )
