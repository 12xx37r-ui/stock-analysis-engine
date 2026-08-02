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
from collectors.news import get_company_news
from collectors.technical import get_stock_technical_bundle
from predictor import predict_stock


DEFAULT_STOCK_CODE = "005930"
DEFAULT_MARKET_CODE = "K"
DEFAULT_INDUSTRY_CODE = "auto"


LIVE_INDUSTRY_CODES = {
    "semiconductor",
    "automotive",
    "battery",
    "biotechnology",
    "construction",
    "finance",
}

VALUATION_INDUSTRY_CODES = {
    "semiconductor",
    "automotive",
    "battery",
    "biotechnology",
    "pharmaceutical",
    "construction",
    "finance",
    "insurance",
    "consumer_staples",
    "consumer_discretionary",
    "retail",
    "media_entertainment",
    "software_platform",
    "telecom",
    "utilities",
    "materials",
    "industrial",
    "transportation",
    "real_estate",
    "healthcare",
    "energy",
    "holding_company",
    "services",
    "general",
    "none",
}


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


def safe_number(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def apply_technical_price_fallback(market, technical_bundle):
    """Use Yahoo 5-year chart as the source-neutral price history fallback.

    KIS remains the only source for investor/program data. When KIS price history
    is unavailable, a valid Yahoo technical bundle must still drive the price
    trend factor and must not be reported as a complete history failure.
    """
    market = market if isinstance(market, dict) else {}
    technical_bundle = technical_bundle if isinstance(technical_bundle, dict) else {}
    history = market.get("과거데이터")
    if not isinstance(history, dict):
        history = {}
        market["과거데이터"] = history

    status = history.get("수집상태")
    if not isinstance(status, dict):
        status = {}
        history["수집상태"] = status

    existing_count = int(safe_number(status.get("가격데이터개수"), 0))
    existing_state = str(status.get("가격데이터상태") or "")
    daily = technical_bundle.get("일봉") if isinstance(technical_bundle.get("일봉"), dict) else {}
    rows = technical_bundle.get("최근일봉") if isinstance(technical_bundle.get("최근일봉"), list) else []

    if existing_state == "정상" and existing_count > 0:
        status["가격데이터출처"] = status.get("가격데이터출처") or "한국투자증권 KIS"
        return market

    if technical_bundle.get("수집상태") not in {"정상", "부분성공"} or daily.get("available") is not True:
        return market

    closes = [safe_number(row.get("종가"), 0.0) for row in rows if isinstance(row, dict)]
    closes = [value for value in closes if value > 0]
    volumes = [safe_number(row.get("거래량"), 0.0) for row in rows if isinstance(row, dict)]

    def roc(period):
        if len(closes) <= period or closes[-period - 1] <= 0:
            return 0.0
        return (closes[-1] / closes[-period - 1] - 1.0) * 100.0

    def mean(values, period):
        usable = [value for value in values[-period:] if value >= 0]
        return sum(usable) / len(usable) if usable else 0.0

    avg5 = mean(volumes, 5)
    avg20 = mean(volumes, 20)
    history["가격추세"] = {
        "종가": safe_number(daily.get("latestClose"), closes[-1] if closes else 0.0),
        "MA5": safe_number(daily.get("maFast")),
        "MA20": safe_number(daily.get("maMedium")),
        "MA60": safe_number(daily.get("maLong")),
        "종가대비MA20": ((safe_number(daily.get("latestClose")) / safe_number(daily.get("maMedium")) - 1.0) * 100.0) if safe_number(daily.get("maMedium")) > 0 else 0.0,
        "종가대비MA60": ((safe_number(daily.get("latestClose")) / safe_number(daily.get("maLong")) - 1.0) * 100.0) if safe_number(daily.get("maLong")) > 0 else 0.0,
        "5일수익률": roc(5),
        "20일수익률": roc(20),
        "60일수익률": roc(60),
        "RSI14": safe_number(daily.get("rsi14")),
        "20일일간변동성": 0.0,
        "5일평균거래량": avg5,
        "20일평균거래량": avg20,
        "거래량비율5대20": avg5 / avg20 if avg20 > 0 else 0.0,
    }

    count = int(safe_number(technical_bundle.get("일봉데이터개수"), len(closes)))
    status.update({
        "가격데이터상태": "정상",
        "가격응답상태": "YAHOO_FALLBACK",
        "가격응답메시지": "KIS 일봉 미확보 · Yahoo 5년 일봉으로 가격추세 정상 보완",
        "가격데이터개수": count,
        "가격최초일": technical_bundle.get("최초일", ""),
        "가격최종일": technical_bundle.get("최종일", ""),
        "가격데이터출처": technical_bundle.get("데이터출처", "Yahoo Finance Chart API 5년 일봉"),
    })

    investor_ok = status.get("누적수급데이터상태") == "정상" and int(safe_number(status.get("누적수급데이터개수"), 0)) > 0
    program_ok = status.get("프로그램데이터상태") == "정상" and int(safe_number(status.get("프로그램데이터개수"), 0)) > 0
    status["전체수집상태"] = "정상" if investor_ok and program_ok else "부분성공"
    history["데이터출처"] = "Yahoo 가격이력 + KIS 수급·프로그램(설정 시)"
    return market


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
            "가격데이터출처": (
                price_history.get(
                    "데이터출처",
                    history_bundle.get(
                        "데이터출처",
                        "한국투자증권 KIS",
                    ),
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
        "주식총수": safe_dict(
            bundle.get(
                "주식총수"
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

    if industry_code not in VALUATION_INDUSTRY_CODES:
        industry_code = "general"

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



def _bridge_number(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def _bridge_technical_item(value):
    value = safe_dict(value)
    available = value.get("available") is True and _bridge_number(value.get("observations")) > 0
    return {
        "사용가능": available,
        "available": available,
        "점수": _bridge_number(value.get("score")),
        "score": _bridge_number(value.get("score")),
        "판정": value.get("trend", "중립"),
        "trend": value.get("trend", "중립"),
        "RSI14": value.get("rsi14"),
        "rsi14": value.get("rsi14"),
        "빠른이동평균": value.get("maFast"),
        "maFast": value.get("maFast"),
        "중간이동평균": value.get("maMedium"),
        "maMedium": value.get("maMedium"),
        "장기이동평균": value.get("maLong"),
        "maLong": value.get("maLong"),
        "단기모멘텀": value.get("momentumFast"),
        "momentumFast": value.get("momentumFast"),
        "중기모멘텀": value.get("momentumMedium"),
        "momentumMedium": value.get("momentumMedium"),
        "관측수": int(_bridge_number(value.get("observations"))),
        "observations": int(_bridge_number(value.get("observations"))),
        "자료신뢰도": _bridge_number(value.get("confidence")),
        "confidence": _bridge_number(value.get("confidence")),
    }


def _bridge_horizon(value):
    value = safe_dict(value)
    factors = []
    for item in safe_list(value.get("요소별평가")):
        item = safe_dict(item)
        quality = _bridge_number(item.get("데이터품질"))
        factors.append({
            "요소": item.get("요소", ""),
            "사용가능": quality > 0,
            "가중치": _bridge_number(item.get("가중치")),
            "신호": _bridge_number(item.get("신호")),
            "판정": item.get("신호판정", "중립"),
            "신호판정": item.get("신호판정", "중립"),
            "데이터상태": "정상" if quality > 0 else "미수집",
            "데이터품질": quality,
            "점수기여": _bridge_number(item.get("점수기여")),
            "출처": item.get("출처", ""),
            "설명": item.get("설명", ""),
        })

    return {
        "기간": value.get("기간", ""),
        "점수": int(round(_bridge_number(value.get("점수"), 50))),
        "상승확률": int(round(_bridge_number(value.get("상승확률"), 50))),
        "판정": value.get("판정", "중립"),
        "자료신뢰도": int(round(_bridge_number(value.get("신뢰도")))),
        "신뢰도": int(round(_bridge_number(value.get("신뢰도")))),
        "자료신뢰도등급": value.get("신뢰도등급", "-"),
        "신뢰도등급": value.get("신뢰도등급", "-"),
        "요소별평가": factors,
        "미수집요소": safe_list(value.get("미수집요소")),
    }


def build_screen_bridge(
    stock_code,
    generated_at,
    technical_bundle,
    prediction,
    global_summary,
    industry_summary,
    news_bundle,
    disclosure_summary,
    market,
):
    technical_bundle = safe_dict(technical_bundle)
    prediction = safe_dict(prediction)
    global_summary = safe_dict(global_summary)
    industry_summary = safe_dict(industry_summary)
    news_bundle = safe_dict(news_bundle)
    disclosure_summary = safe_dict(disclosure_summary)
    market = safe_dict(market)

    technical = {
        "수집상태": technical_bundle.get("수집상태", ""),
        "데이터출처": technical_bundle.get("데이터출처", ""),
        "일봉": _bridge_technical_item(technical_bundle.get("일봉")),
        "주봉": _bridge_technical_item(technical_bundle.get("주봉")),
        "월봉": _bridge_technical_item(technical_bundle.get("월봉")),
    }
    technical["사용가능"] = any(
        technical[key]["사용가능"]
        for key in ("일봉", "주봉", "월봉")
    )

    horizons = {
        "단기": _bridge_horizon(prediction.get("단기1~5일")),
        "중기": _bridge_horizon(prediction.get("중기1~8주")),
        "장기": _bridge_horizon(prediction.get("장기6~18개월")),
    }

    global_analysis = safe_dict(global_summary.get("분석"))
    industry_analysis = safe_dict(industry_summary.get("분석"))
    news_analysis = safe_dict(news_bundle.get("분석"))
    disclosure_analysis = safe_dict(disclosure_summary.get("분석"))
    history = safe_dict(market.get("과거데이터"))
    history_state = safe_dict(history.get("수집상태"))

    elements = {
        "거시환경": {
            "사용가능": global_summary.get("전체수집상태") == "정상" and global_analysis.get("분석상태") == "정상",
            "점수": _bridge_number(global_analysis.get("중기신호", global_analysis.get("단기신호"))),
            "데이터품질": _bridge_number(global_analysis.get("중기데이터품질", global_analysis.get("단기데이터품질"))),
            "판정": global_analysis.get("중기판정", global_analysis.get("단기판정", "중립")),
            "출처": global_summary.get("데이터출처", ""),
        },
        "산업선행지표": {
            "사용가능": _bridge_number(safe_dict(industry_analysis.get("중기산업선행")).get("데이터품질")) > 0,
            "점수": _bridge_number(safe_dict(industry_analysis.get("중기산업선행")).get("신호")),
            "데이터품질": _bridge_number(safe_dict(industry_analysis.get("중기산업선행")).get("데이터품질")),
            "판정": safe_dict(industry_analysis.get("중기산업선행")).get("판정", "중립"),
            "출처": industry_summary.get("데이터출처", ""),
        },
        "산업사이클": {
            "사용가능": _bridge_number(safe_dict(industry_analysis.get("장기산업사이클")).get("데이터품질")) > 0,
            "점수": _bridge_number(safe_dict(industry_analysis.get("장기산업사이클")).get("신호")),
            "데이터품질": _bridge_number(safe_dict(industry_analysis.get("장기산업사이클")).get("데이터품질")),
            "판정": safe_dict(industry_analysis.get("장기산업사이클")).get("판정", "중립"),
            "출처": industry_summary.get("데이터출처", ""),
        },
        "뉴스": {
            "사용가능": news_bundle.get("수집상태") == "정상" and _bridge_number(news_bundle.get("뉴스개수")) > 0,
            "점수": _bridge_number(news_analysis.get("신호")),
            "데이터품질": _bridge_number(news_analysis.get("데이터품질")),
            "판정": news_analysis.get("판정", "중립"),
            "출처": news_bundle.get("데이터출처", ""),
        },
        "기업공시": {
            "사용가능": disclosure_summary.get("수집상태") == "정상",
            "점수": _bridge_number(disclosure_analysis.get("신호")),
            "데이터품질": _bridge_number(disclosure_analysis.get("데이터품질")),
            "판정": disclosure_analysis.get("판정", "중립"),
            "출처": disclosure_summary.get("데이터출처", ""),
        },
        "외국인기관수급": {
            "사용가능": history_state.get("누적수급데이터상태") == "정상" or bool(safe_dict(market.get("수급"))),
            "점수": next((f["점수기여"] for f in horizons["단기"]["요소별평가"] if f["요소"] == "외국인·기관수급"), 0.0),
            "데이터품질": next((f["데이터품질"] for f in horizons["단기"]["요소별평가"] if f["요소"] == "외국인·기관수급"), 0.0),
            "판정": next((f["판정"] for f in horizons["단기"]["요소별평가"] if f["요소"] == "외국인·기관수급"), "중립"),
            "출처": "한국투자증권 KIS",
        },
        "프로그램매매": {
            "사용가능": history_state.get("프로그램데이터상태") == "정상",
            "점수": next((f["점수기여"] for f in horizons["단기"]["요소별평가"] if "프로그램" in f["요소"]), 0.0),
            "데이터품질": next((f["데이터품질"] for f in horizons["단기"]["요소별평가"] if "프로그램" in f["요소"]), 0.0),
            "판정": next((f["판정"] for f in horizons["단기"]["요소별평가"] if "프로그램" in f["요소"]), "중립"),
            "출처": "한국투자증권 KIS 종목별 프로그램매매",
        },
    }

    errors = []
    if not technical["사용가능"]:
        errors.append("일봉·주봉·월봉 기술분석이 모두 미연결")
    for name, item in elements.items():
        if not item.get("사용가능"):
            errors.append(name + " 미연결")

    return {
        "스키마버전": "2.0",
        "엔진버전": prediction.get("엔진버전", ""),
        "종목코드": stock_code,
        "생성시각": generated_at,
        "연결상태": "정상" if not errors else "부분",
        "기술분석": technical,
        "예측": horizons,
        "요소상태": elements,
        "검증오류": errors,
    }

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

    technical_bundle = safe_execute(
        "MULTI TIMEFRAME TECHNICAL",
        lambda: get_stock_technical_bundle(
            stock_code,
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

    market = apply_technical_price_fallback(
        market,
        technical_bundle,
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
            "주식총수": {},
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

    if industry_code not in LIVE_INDUSTRY_CODES:
        print(
            "INDUSTRY SKIPPED:",
            stock_code,
        )

        industry_bundle = {
            "전체수집상태": "미적용",
            "산업코드": industry_code,
            "산업명": industry_code if industry_code != "none" else "미분류",
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

    generated_at = datetime.now().isoformat()
    disclosure_summary = build_disclosure_summary(
        disclosure_bundle,
        disclosure_analysis,
    )
    global_summary = build_global_summary(
        global_bundle,
        global_analysis,
    )
    fundamentals_summary = build_fundamentals_summary(
        fundamentals_bundle,
        fundamentals_analysis,
    )
    industry_summary = build_industry_summary(
        industry_bundle,
        industry_analysis,
    )
    screen_bridge = build_screen_bridge(
        stock_code=stock_code,
        generated_at=generated_at,
        technical_bundle=technical_bundle,
        prediction=prediction,
        global_summary=global_summary,
        industry_summary=industry_summary,
        news_bundle=news_bundle,
        disclosure_summary=disclosure_summary,
        market=market,
    )

    result = {
        "기업명": company,
        "DART기업코드": dart_code,
        "KIS종목코드": stock_code,
        "산업코드": industry_code,
        "기업조회정보": target[
            "기업조회"
        ],
        "생성시각": generated_at,
        "재무분석": financial,
        "시장정보": market,
        "공시정보": disclosure_summary,
        "글로벌시장": global_summary,
        "기업기초데이터": fundamentals_summary,
        "산업분석": industry_summary,
        "기술분석": technical_bundle,
        "뉴스분석": news_bundle,
        "가치평가": valuation,
        "주가예측": prediction,
        "화면브리지": screen_bridge,
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
