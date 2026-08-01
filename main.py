import argparse
import json
import os
from datetime import datetime

from analyzers.disclosure import analyze_disclosures
from analyzers.financial import analyze_financial
from analyzers.fundamentals import analyze_fundamentals
from analyzers.global_market import analyze_global_market
from analyzers.industry import analyze_industry
from analyzers.valuation import calculate_value
from collectors.company import (
    infer_industry_code,
    normalize_stock_code,
    resolve_company,
)
from collectors.dart import get_financial
from collectors.disclosure import get_recent_disclosures
from collectors.fundamentals import get_fundamentals_bundle
from collectors.global_market import get_global_market_bundle
from collectors.history import get_history_bundle
from collectors.industry import get_industry_bundle
from collectors.market import get_market_data
from predictor import predict_stock


DEFAULT_STOCK_CODE = "005930"
DEFAULT_MARKET_CODE = "K"
DEFAULT_INDUSTRY_CODE = "auto"


def safe_dict(value):
    if isinstance(value, dict):
        return value
    return {}


def safe_list(value):
    if isinstance(value, list):
        return value
    return []


def safe_execute(
    name,
    function,
    fallback,
):
    try:
        return function()

    except Exception as error:
        print(
            name,
            "ERROR:",
            type(error).__name__,
            error,
        )

        return fallback


def build_history_summary(
    history_bundle,
):
    history_bundle = safe_dict(
        history_bundle
    )

    price_history = safe_dict(
        history_bundle.get(
            "가격추세"
        )
    )

    investor_history = safe_dict(
        history_bundle.get(
            "누적수급"
        )
    )

    program_history = safe_dict(
        history_bundle.get(
            "프로그램매매"
        )
    )

    return {
        "가격추세": safe_dict(
            price_history.get(
                "지표"
            )
        ),
        "누적수급": safe_dict(
            investor_history.get(
                "누적"
            )
        ),
        "프로그램매매": safe_dict(
            program_history.get(
                "누적"
            )
        ),
        "수집상태": {
            "전체수집상태": (
                history_bundle.get(
                    "전체수집상태",
                    "",
                )
            ),
            "가격데이터상태": (
                price_history.get(
                    "데이터상태",
                    "",
                )
            ),
            "가격응답상태": (
                price_history.get(
                    "응답상태",
                    "",
                )
            ),
            "가격응답메시지": (
                price_history.get(
                    "응답메시지",
                    "",
                )
            ),
            "가격데이터개수": (
                price_history.get(
                    "데이터개수",
                    0,
                )
            ),
            "가격최초일": (
                price_history.get(
                    "최초일",
                    "",
                )
            ),
            "가격최종일": (
                price_history.get(
                    "최종일",
                    "",
                )
            ),
            "누적수급데이터상태": (
                investor_history.get(
                    "데이터상태",
                    "",
                )
            ),
            "누적수급응답상태": (
                investor_history.get(
                    "응답상태",
                    "",
                )
            ),
            "누적수급응답메시지": (
                investor_history.get(
                    "응답메시지",
                    "",
                )
            ),
            "누적수급데이터개수": (
                investor_history.get(
                    "데이터개수",
                    0,
                )
            ),
            "누적수급조회기준일": (
                investor_history.get(
                    "조회기준일",
                    "",
                )
            ),
            "누적수급최초일": (
                investor_history.get(
                    "최초일",
                    "",
                )
            ),
            "누적수급최종일": (
                investor_history.get(
                    "최종일",
                    "",
                )
            ),
            "프로그램데이터상태": (
                program_history.get(
                    "데이터상태",
                    "",
                )
            ),
            "프로그램응답상태": (
                program_history.get(
                    "응답상태",
                    "",
                )
            ),
            "프로그램응답메시지": (
                program_history.get(
                    "응답메시지",
                    "",
                )
            ),
            "프로그램데이터개수": (
                program_history.get(
                    "데이터개수",
                    0,
                )
            ),
        },
        "수집오류": history_bundle.get(
            "수집오류",
            [],
        ),
        "데이터출처": history_bundle.get(
            "데이터출처",
            "한국투자증권 KIS",
        ),
    }


def build_global_summary(
    global_bundle,
    global_analysis,
):
    global_bundle = safe_dict(
        global_bundle
    )

    assets = safe_dict(
        global_bundle.get(
            "자산"
        )
    )

    summarized_assets = {}

    for name, asset in assets.items():
        asset = safe_dict(asset)

        summarized_assets[name] = {
            key: value
            for key, value in asset.items()
            if key != "일별데이터"
        }

    return {
        "전체수집상태": (
            global_bundle.get(
                "전체수집상태",
                "",
            )
        ),
        "자산": summarized_assets,
        "분석": safe_dict(
            global_analysis
        ),
        "수집오류": global_bundle.get(
            "수집오류",
            [],
        ),
        "수집시각": global_bundle.get(
            "수집시각",
            "",
        ),
        "데이터출처": global_bundle.get(
            "데이터출처",
            "Yahoo Finance Chart API",
        ),
    }


def build_disclosure_summary(
    disclosure_bundle,
    disclosure_analysis,
):
    disclosure_bundle = safe_dict(
        disclosure_bundle
    )

    disclosures = safe_list(
        disclosure_bundle.get(
            "공시목록"
        )
    )

    return {
        "수집상태": (
            disclosure_bundle.get(
                "수집상태",
                "",
            )
        ),
        "응답코드": (
            disclosure_bundle.get(
                "응답코드",
                "",
            )
        ),
        "응답메시지": (
            disclosure_bundle.get(
                "응답메시지",
                "",
            )
        ),
        "조회시작일": (
            disclosure_bundle.get(
                "조회시작일",
                "",
            )
        ),
        "조회종료일": (
            disclosure_bundle.get(
                "조회종료일",
                "",
            )
        ),
        "공시개수": (
            disclosure_bundle.get(
                "공시개수",
                len(disclosures),
            )
        ),
        "최근공시": disclosures[:30],
        "분석": safe_dict(
            disclosure_analysis
        ),
        "데이터출처": (
            disclosure_bundle.get(
                "데이터출처",
                "금융감독원 OpenDART",
            )
        ),
    }


def compact_report_series(series):
    series = safe_dict(series)

    reports = []

    for report in safe_list(
        series.get(
            "보고서목록"
        )
    ):
        report = safe_dict(report)

        reports.append(
            {
                "사업연도": report.get(
                    "사업연도"
                ),
                "보고서코드": report.get(
                    "보고서코드",
                    "",
                ),
                "수집상태": report.get(
                    "수집상태",
                    "",
                ),
                "응답코드": report.get(
                    "응답코드",
                    "",
                ),
                "응답메시지": report.get(
                    "응답메시지",
                    "",
                ),
                "데이터개수": report.get(
                    "데이터개수",
                    0,
                ),
            }
        )

    return {
        "수집상태": series.get(
            "수집상태",
            "",
        ),
        "보고서개수": series.get(
            "보고서개수",
            len(reports),
        ),
        "보고서목록": reports,
        "수집오류": series.get(
            "수집오류",
            [],
        ),
    }


def build_fundamentals_summary(
    bundle,
    analysis,
):
    bundle = safe_dict(bundle)

    financial_series = safe_dict(
        bundle.get(
            "재무기간"
        )
    )

    periods = []

    for period in safe_list(
        financial_series.get(
            "기간목록"
        )
    ):
        period = safe_dict(period)

        periods.append(
            {
                "사업연도": period.get(
                    "사업연도"
                ),
                "보고서코드": period.get(
                    "보고서코드",
                    "",
                ),
                "보고서명": period.get(
                    "보고서명",
                    "",
                ),
                "연결구분": period.get(
                    "연결구분",
                    "",
                ),
                "수집상태": period.get(
                    "수집상태",
                    "",
                ),
                "응답코드": period.get(
                    "응답코드",
                    "",
                ),
                "응답메시지": period.get(
                    "응답메시지",
                    "",
                ),
                "계정개수": period.get(
                    "계정개수",
                    0,
                ),
                "지표": safe_dict(
                    period.get(
                        "지표"
                    )
                ),
            }
        )

    return {
        "전체수집상태": bundle.get(
            "전체수집상태",
            "",
        ),
        "재무기간": {
            "수집상태": (
                financial_series.get(
                    "수집상태",
                    "",
                )
            ),
            "기간개수": (
                financial_series.get(
                    "기간개수",
                    len(periods),
                )
            ),
            "기간목록": periods,
            "수집오류": (
                financial_series.get(
                    "수집오류",
                    [],
                )
            ),
        },
        "배당": compact_report_series(
            bundle.get(
                "배당"
            )
        ),
        "자기주식": compact_report_series(
            bundle.get(
                "자기주식"
            )
        ),
        "분석": safe_dict(
            analysis
        ),
        "수집시각": bundle.get(
            "수집시각",
            "",
        ),
        "데이터출처": bundle.get(
            "데이터출처",
            "금융감독원 OpenDART",
        ),
    }


def build_industry_summary(
    bundle,
    analysis,
):
    bundle = safe_dict(bundle)

    assets = safe_dict(
        bundle.get(
            "자산"
        )
    )

    summarized_assets = {}

    for name, asset in assets.items():
        asset = safe_dict(asset)

        summarized_assets[name] = {
            key: value
            for key, value in asset.items()
            if key != "일별데이터"
        }

    return {
        "전체수집상태": bundle.get(
            "전체수집상태",
            "",
        ),
        "산업코드": bundle.get(
            "산업코드",
            "",
        ),
        "산업명": bundle.get(
            "산업명",
            "",
        ),
        "자산": summarized_assets,
        "분석": safe_dict(
            analysis
        ),
        "수집오류": bundle.get(
            "수집오류",
            [],
        ),
        "수집시각": bundle.get(
            "수집시각",
            "",
        ),
        "데이터출처": bundle.get(
            "데이터출처",
            "Yahoo Finance Chart API",
        ),
    }


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "국내주식 재무·시장·예측 엔진"
        )
    )

    parser.add_argument(
        "--stock-code",
        default=os.getenv(
            "STOCK_CODE",
            DEFAULT_STOCK_CODE,
        ),
        help=(
            "6자리 국내 종목코드 "
            "(기본값: 005930)"
        ),
    )

    parser.add_argument(
        "--industry-code",
        default=os.getenv(
            "INDUSTRY_CODE",
            DEFAULT_INDUSTRY_CODE,
        ),
        help=(
            "auto, semiconductor, automotive, battery, "
            "biotechnology, construction, finance, none"
        ),
    )

    parser.add_argument(
        "--market-code",
        default=os.getenv(
            "MARKET_CODE",
            DEFAULT_MARKET_CODE,
        ),
        help=(
            "KIS 시장코드 보조값 "
            "(기본값: K)"
        ),
    )

    return parser.parse_args()


def resolve_target(
    stock_code,
    requested_industry,
):
    normalized_stock_code = (
        normalize_stock_code(
            stock_code
        )
    )

    company_info = resolve_company(
        normalized_stock_code
    )

    if company_info.get(
        "수집상태"
    ) not in {
        "정상",
        "부분성공",
    }:
        raise RuntimeError(
            company_info.get(
                "응답메시지",
                "기업 조회 실패",
            )
        )

    company_name = company_info.get(
        "기업명",
        "",
    )
    dart_code = company_info.get(
        "DART기업코드",
        "",
    )

    if not (
        company_name
        and dart_code
        and normalized_stock_code
    ):
        raise RuntimeError(
            "기업명·DART코드·종목코드 중 "
            "필수 값이 누락됐습니다."
        )

    requested = str(
        requested_industry
        or "auto"
    ).strip().lower()

    if requested in {
        "",
        "auto",
    }:
        industry_code = (
            company_info.get(
                "산업코드"
            )
            or infer_industry_code(
                normalized_stock_code
            )
        )
    else:
        industry_code = requested

    if industry_code not in {
        "semiconductor",
        "automotive",
        "battery",
        "biotechnology",
        "construction",
        "finance",
        "none",
    }:
        raise RuntimeError(
            "지원 산업코드: auto, semiconductor, automotive, "
            "battery, biotechnology, construction, finance, none"
        )

    return {
        "기업명": company_name,
        "DART기업코드": dart_code,
        "종목코드": normalized_stock_code,
        "산업코드": industry_code,
        "기업조회": company_info,
    }


def save_result(
    result,
    stock_code,
):
    os.makedirs(
        "output",
        exist_ok=True,
    )

    output_path = os.path.join(
        "output",
        f"{stock_code}.json",
    )

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2,
        )

    return output_path


def main():
    args = parse_arguments()

    target = resolve_target(
        args.stock_code,
        args.industry_code,
    )

    company = target[
        "기업명"
    ]
    dart_code = target[
        "DART기업코드"
    ]
    stock_code = target[
        "종목코드"
    ]
    industry_code = target[
        "산업코드"
    ]
    market_code = str(
        args.market_code
        or DEFAULT_MARKET_CODE
    ).strip().upper()

    print("START ENGINE")
    print(
        "TARGET:",
        company,
        stock_code,
        "DART",
        dart_code,
        "INDUSTRY",
        industry_code,
    )

    dart_raw = get_financial(
        dart_code
    )

    financial = analyze_financial(
        dart_raw
    )

    market = get_market_data(
        stock_code
    )

    history_bundle = safe_execute(
        "HISTORY",
        lambda: get_history_bundle(
            stock_code,
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

    market["과거데이터"] = (
        build_history_summary(
            history_bundle
        )
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

    if industry_code == "none":
        print(
            "INDUSTRY SKIPPED:",
            stock_code,
        )

        industry_bundle = {
            "전체수집상태": "미적용",
            "산업코드": "none",
            "산업명": "미분류",
            "자산": {},
            "수집오류": [],
        }

        industry_analysis = {
            "분석상태": "미적용",
            "중기산업선행": {},
            "장기산업사이클": {},
            "산업국면": "미분류",
        }

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

    valuation = calculate_value(
        financial,
        market,
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
    )

    result = {
        "기업명": company,
        "DART기업코드": dart_code,
        "KIS종목코드": stock_code,
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
        "가치평가": valuation,
        "주가예측": prediction,
    }

    output_path = save_result(
        result,
        stock_code,
    )

    compact_summary = {
        "기업명": company,
        "종목코드": stock_code,
        "산업코드": industry_code,
        "현재가": market.get(
            "현재가"
        ),
        "엔진버전": prediction.get(
            "엔진버전"
        ),
        "단기1~5일": {
            key: prediction.get(
                "단기1~5일",
                {},
            ).get(key)
            for key in (
                "점수",
                "상승확률",
                "판정",
                "신뢰도",
            )
        },
        "중기1~8주": {
            key: prediction.get(
                "중기1~8주",
                {},
            ).get(key)
            for key in (
                "점수",
                "상승확률",
                "판정",
                "신뢰도",
            )
        },
        "장기6~18개월": {
            key: prediction.get(
                "장기6~18개월",
                {},
            ).get(key)
            for key in (
                "점수",
                "상승확률",
                "판정",
                "신뢰도",
            )
        },
        "데이터완전성": prediction.get(
            "데이터완전성",
            {},
        ),
    }

    print(
        "RESULT SUMMARY"
    )
    print(
        json.dumps(
            compact_summary,
            ensure_ascii=False,
            indent=2,
        )
    )

    print(
        "OUTPUT SAVED:",
        output_path,
    )
    print(
        "OUTPUT_FILE=",
        output_path,
        sep="",
    )


if __name__ == "__main__":
    main()
