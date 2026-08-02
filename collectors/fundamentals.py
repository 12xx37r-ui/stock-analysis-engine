"""
OpenDART 실적·현금흐름·주주환원·주식수 수집기 V1.2

수집 대상
1. 최근 분기/반기/사업보고서 전체 재무제표
2. 최근 사업보고서 배당에 관한 사항
3. 최근 사업보고서 자기주식 취득 및 처분 현황
4. 최신 정기보고서 주식의 총수 현황

기존 main.py와 predictor.py에는 아직 연결하지 않는다.
모든 요청은 개별 실패를 허용하며, 수집 가능한 데이터만 반환한다.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import config

from collectors.dart_http import get_json as dart_get_json


KST = timezone(timedelta(hours=9))

DART_FINANCIAL_URL = (
    "https://opendart.fss.or.kr/api/"
    "fnlttSinglAcntAll.json"
)
DART_DIVIDEND_URL = (
    "https://opendart.fss.or.kr/api/"
    "alotMatter.json"
)
DART_TREASURY_URL = (
    "https://opendart.fss.or.kr/api/"
    "tesstkAcqsDspsSttus.json"
)
DART_STOCK_TOTAL_URL = (
    "https://opendart.fss.or.kr/api/"
    "stockTotqySttus.json"
)

REPORT_NAMES = {
    "11013": "1분기",
    "11012": "반기",
    "11014": "3분기",
    "11011": "사업보고서",
}


def safe_text(
    value: Any,
    default: str = "",
) -> str:
    if value is None:
        return default

    return str(value).strip()


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        if value in (None, ""):
            return default

        text = (
            str(value)
            .replace(",", "")
            .replace(" ", "")
            .strip()
        )

        if text in {
            "-",
            "--",
            "N/A",
            "nan",
            "None",
        }:
            return default

        if text.startswith("(") and text.endswith(")"):
            text = "-" + text[1:-1]

        return float(text)

    except (TypeError, ValueError):
        return default


def get_dart_api_key() -> str:
    candidates = (
        getattr(
            config,
            "DART_API_KEY",
            "",
        ),
        getattr(
            config,
            "DART_KEY",
            "",
        ),
        os.getenv(
            "DART_API_KEY",
            "",
        ),
        os.getenv(
            "DART_KEY",
            "",
        ),
    )

    for candidate in candidates:
        key = safe_text(candidate)

        if key:
            return key

    return ""


def request_dart(
    url: str,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    return dart_get_json(url, params)


def normalize_list(
    value: Any,
) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []

    return [
        row
        for row in value
        if isinstance(row, dict)
    ]


def candidate_periods() -> List[Tuple[int, str]]:
    """
    최신 공시 가능성이 높은 순서로 조회한다.
    최대 4개 성공 기간을 확보하면 중단한다.
    """
    current_year = datetime.now(KST).year

    return [
        (current_year, "11014"),
        (current_year, "11012"),
        (current_year, "11013"),
        (current_year - 1, "11011"),
        (current_year - 1, "11014"),
        (current_year - 1, "11012"),
        (current_year - 1, "11013"),
        (current_year - 2, "11011"),
    ]


def annual_years(
    count: int = 3,
) -> List[int]:
    current_year = datetime.now(KST).year

    return [
        current_year - offset
        for offset in range(1, count + 2)
    ]


def clean_account_name(
    value: Any,
) -> str:
    return (
        safe_text(value)
        .replace(" ", "")
        .replace("\n", "")
        .replace("\t", "")
    )


ACCOUNT_ALIASES = {
    "매출": (
        "매출액",
        "수익(매출액)",
        "영업수익",
        "매출",
    ),
    "영업이익": (
        "영업이익",
        "영업이익(손실)",
    ),
    "순이익": (
        "당기순이익",
        "당기순이익(손실)",
        "연결당기순이익",
        "분기순이익",
        "반기순이익",
    ),
    "자산총계": (
        "자산총계",
    ),
    "부채총계": (
        "부채총계",
    ),
    "자본총계": (
        "자본총계",
    ),
    "현금및현금성자산": (
        "현금및현금성자산",
        "현금및현금성자산의증가(감소)",
    ),
    "단기차입금": (
        "단기차입금",
        "유동성장기차입금",
        "유동성사채",
    ),
    "장기차입금": (
        "장기차입금",
        "사채",
        "장기성차입금",
    ),
    "영업현금흐름": (
        "영업활동으로인한현금흐름",
        "영업활동현금흐름",
        "영업활동으로부터의현금흐름",
    ),
    "유형자산취득": (
        "유형자산의취득",
        "유형자산취득",
    ),
    "무형자산취득": (
        "무형자산의취득",
        "무형자산취득",
    ),
}


def find_account_value(
    rows: List[Dict[str, Any]],
    aliases: Iterable[str],
    statement_types: Optional[Iterable[str]] = None,
    cumulative: bool = True,
) -> float:
    aliases_clean = {
        clean_account_name(alias)
        for alias in aliases
    }

    allowed_types = (
        set(statement_types)
        if statement_types
        else None
    )

    candidates = []

    for row in rows:
        statement_type = safe_text(
            row.get("sj_div")
        )

        if (
            allowed_types is not None
            and statement_type not in allowed_types
        ):
            continue

        account_name = clean_account_name(
            row.get("account_nm")
        )

        if account_name not in aliases_clean:
            continue

        if cumulative:
            value = safe_float(
                row.get(
                    "thstrm_add_amount"
                )
            )

            if value == 0:
                value = safe_float(
                    row.get(
                        "thstrm_amount"
                    )
                )
        else:
            value = safe_float(
                row.get(
                    "thstrm_amount"
                )
            )

        candidates.append(
            {
                "value": value,
                "order": safe_float(
                    row.get("ord"),
                    999999,
                ),
            }
        )

    if not candidates:
        return 0.0

    candidates.sort(
        key=lambda item: item["order"]
    )

    for candidate in candidates:
        if candidate["value"] != 0:
            return candidate["value"]

    return candidates[0]["value"]


def parse_financial_period(
    rows: List[Dict[str, Any]],
    year: int,
    report_code: str,
    fs_div: str,
    status: str,
    message: str,
) -> Dict[str, Any]:
    metrics: Dict[str, float] = {}

    for key, aliases in ACCOUNT_ALIASES.items():
        if key in {
            "자산총계",
            "부채총계",
            "자본총계",
            "현금및현금성자산",
            "단기차입금",
            "장기차입금",
        }:
            statement_types = (
                "BS",
            )
            cumulative = False

        elif key in {
            "영업현금흐름",
            "유형자산취득",
            "무형자산취득",
        }:
            statement_types = (
                "CF",
            )
            cumulative = True

        else:
            statement_types = (
                "IS",
                "CIS",
            )
            cumulative = True

        metrics[key] = find_account_value(
            rows,
            aliases,
            statement_types=statement_types,
            cumulative=cumulative,
        )

    capex = abs(
        metrics["유형자산취득"]
    ) + abs(
        metrics["무형자산취득"]
    )

    free_cash_flow = (
        metrics["영업현금흐름"]
        - capex
    )

    return {
        "사업연도": year,
        "보고서코드": report_code,
        "보고서명": REPORT_NAMES.get(
            report_code,
            report_code,
        ),
        "연결구분": fs_div,
        "수집상태": (
            "정상"
            if status == "000" and rows
            else "실패"
        ),
        "응답코드": status,
        "응답메시지": message,
        "계정개수": len(rows),
        "지표": {
            "매출": metrics["매출"],
            "영업이익": metrics["영업이익"],
            "순이익": metrics["순이익"],
            "자산총계": metrics["자산총계"],
            "부채총계": metrics["부채총계"],
            "자본총계": metrics["자본총계"],
            "현금및현금성자산": (
                metrics["현금및현금성자산"]
            ),
            "단기차입금": metrics["단기차입금"],
            "장기차입금": metrics["장기차입금"],
            "총차입금": abs(metrics["단기차입금"]) + abs(metrics["장기차입금"]),
            "영업현금흐름": (
                metrics["영업현금흐름"]
            ),
            "유형자산취득": (
                metrics["유형자산취득"]
            ),
            "무형자산취득": (
                metrics["무형자산취득"]
            ),
            "설비투자추정": capex,
            "잉여현금흐름추정": (
                free_cash_flow
            ),
        },
    }


def fetch_financial_period(
    api_key: str,
    corp_code: str,
    year: int,
    report_code: str,
) -> Dict[str, Any]:
    last_result = {
        "사업연도": year,
        "보고서코드": report_code,
        "보고서명": REPORT_NAMES.get(
            report_code,
            report_code,
        ),
        "연결구분": "",
        "수집상태": "실패",
        "응답코드": "",
        "응답메시지": "",
        "계정개수": 0,
        "지표": {},
    }

    for fs_div in (
        "CFS",
        "OFS",
    ):
        data = request_dart(
            DART_FINANCIAL_URL,
            {
                "crtfc_key": api_key,
                "corp_code": corp_code,
                "bsns_year": str(year),
                "reprt_code": report_code,
                "fs_div": fs_div,
            },
        )

        status = safe_text(
            data.get("status")
        )
        message = safe_text(
            data.get("message")
        )
        rows = normalize_list(
            data.get("list")
        )

        parsed = parse_financial_period(
            rows,
            year,
            report_code,
            fs_div,
            status,
            message,
        )

        last_result = parsed

        if parsed["수집상태"] == "정상":
            return parsed

        if status not in {
            "013",
            "",
        }:
            return parsed

    return last_result


def get_financial_periods(
    api_key: str,
    corp_code: str,
    maximum_success: int = 4,
) -> Dict[str, Any]:
    periods = []
    errors = []

    for year, report_code in candidate_periods():
        period = fetch_financial_period(
            api_key,
            corp_code,
            year,
            report_code,
        )

        print(
            "DART FINANCIAL",
            year,
            REPORT_NAMES.get(
                report_code,
                report_code,
            ),
            period.get("수집상태"),
            period.get("계정개수"),
        )

        if period.get("수집상태") == "정상":
            periods.append(period)

            if len(periods) >= maximum_success:
                break
        else:
            errors.append(
                {
                    "사업연도": year,
                    "보고서코드": report_code,
                    "응답코드": period.get(
                        "응답코드",
                        "",
                    ),
                    "응답메시지": period.get(
                        "응답메시지",
                        "",
                    ),
                }
            )

    return {
        "수집상태": (
            "정상"
            if periods
            else "실패"
        ),
        "기간개수": len(periods),
        "기간목록": periods,
        "수집오류": errors,
    }


def get_report_rows(
    api_key: str,
    url: str,
    corp_code: str,
    year: int,
    report_code: str = "11011",
) -> Dict[str, Any]:
    data = request_dart(
        url,
        {
            "crtfc_key": api_key,
            "corp_code": corp_code,
            "bsns_year": str(year),
            "reprt_code": report_code,
        },
    )

    status = safe_text(
        data.get("status")
    )
    message = safe_text(
        data.get("message")
    )
    rows = normalize_list(
        data.get("list")
    )

    return {
        "사업연도": year,
        "보고서코드": report_code,
        "수집상태": (
            "정상"
            if status == "000"
            else (
                "데이터없음"
                if status == "013"
                else "실패"
            )
        ),
        "응답코드": status,
        "응답메시지": message,
        "데이터개수": len(rows),
        "목록": rows,
    }


def _stock_total_number(
    rows: List[Dict[str, Any]],
    field: str,
) -> float:
    """주식총수 API의 합계행을 우선하고, 없으면 증권종류별 합계를 사용한다."""
    total_rows = [
        row
        for row in rows
        if clean_account_name(row.get("se")) in {"합계", "총계", "계"}
    ]
    for row in total_rows:
        value = safe_float(row.get(field))
        if value > 0:
            return value

    values = []
    for row in rows:
        label = clean_account_name(row.get("se"))
        if not label or label in {"합계", "총계", "계", "비고"}:
            continue
        value = safe_float(row.get(field))
        if value > 0:
            values.append(value)
    return sum(values)


def parse_stock_total_rows(
    rows: List[Dict[str, Any]],
    year: int,
    report_code: str,
    status: str,
    message: str,
) -> Dict[str, Any]:
    issued = _stock_total_number(rows, "istc_totqy")
    treasury = _stock_total_number(rows, "tesstk_co")
    distributed = _stock_total_number(rows, "distb_stock_co")
    authorized = _stock_total_number(rows, "isu_stock_totqy")

    if distributed <= 0 and issued > 0:
        distributed = max(0.0, issued - max(0.0, treasury))

    valuation_shares = distributed if distributed > 0 else issued
    usable = status == "000" and valuation_shares >= 100_000

    return {
        "사업연도": year,
        "보고서코드": report_code,
        "보고서명": REPORT_NAMES.get(report_code, report_code),
        "수집상태": "정상" if usable else "실패",
        "응답코드": status,
        "응답메시지": message,
        "행개수": len(rows),
        "발행가능주식수": round(authorized) if authorized > 0 else 0,
        "발행주식수": round(issued) if issued > 0 else 0,
        "자기주식수": round(treasury) if treasury > 0 else 0,
        "유통주식수": round(distributed) if distributed > 0 else 0,
        "가치평가주식수": round(valuation_shares) if valuation_shares > 0 else 0,
        "주식수기준": "유통주식수" if distributed > 0 else "발행주식수" if issued > 0 else "미확보",
        "결산기준일": safe_text(rows[0].get("stlm_dt")) if rows else "",
    }


def get_stock_total_status(
    api_key: str,
    corp_code: str,
) -> Dict[str, Any]:
    errors = []
    for year, report_code in candidate_periods():
        report = get_report_rows(
            api_key,
            DART_STOCK_TOTAL_URL,
            corp_code,
            year,
            report_code,
        )
        parsed = parse_stock_total_rows(
            normalize_list(report.get("목록")),
            year,
            report_code,
            safe_text(report.get("응답코드")),
            safe_text(report.get("응답메시지")),
        )
        print(
            "DART STOCK TOTAL",
            year,
            REPORT_NAMES.get(report_code, report_code),
            parsed.get("수집상태"),
            parsed.get("가치평가주식수"),
        )
        if parsed.get("수집상태") == "정상":
            return parsed
        errors.append({
            "사업연도": year,
            "보고서코드": report_code,
            "응답코드": parsed.get("응답코드", ""),
            "응답메시지": parsed.get("응답메시지", ""),
        })

    return {
        "수집상태": "실패",
        "발행주식수": 0,
        "자기주식수": 0,
        "유통주식수": 0,
        "가치평가주식수": 0,
        "주식수기준": "미확보",
        "수집오류": errors,
    }


def get_annual_series(
    api_key: str,
    url: str,
    corp_code: str,
    maximum_success: int = 3,
) -> Dict[str, Any]:
    reports = []
    errors = []

    for year in annual_years(
        maximum_success
    ):
        report = get_report_rows(
            api_key,
            url,
            corp_code,
            year,
            "11011",
        )

        if report["수집상태"] == "정상":
            reports.append(report)

            if len(reports) >= maximum_success:
                break
        else:
            errors.append(
                {
                    "사업연도": year,
                    "응답코드": report[
                        "응답코드"
                    ],
                    "응답메시지": report[
                        "응답메시지"
                    ],
                }
            )

    return {
        "수집상태": (
            "정상"
            if reports
            else "실패"
        ),
        "보고서개수": len(reports),
        "보고서목록": reports,
        "수집오류": errors,
    }


def get_fundamentals_bundle(
    corp_code: str,
) -> Dict[str, Any]:
    print("REQUEST DART FUNDAMENTALS")

    corp_code = safe_text(corp_code)
    api_key = get_dart_api_key()

    if not corp_code:
        return {
            "전체수집상태": "실패",
            "응답메시지": (
                "기업코드가 비어 있습니다."
            ),
            "재무기간": {},
            "배당": {},
            "자기주식": {},
            "주식총수": {},
        }

    if not api_key:
        return {
            "전체수집상태": "실패",
            "응답메시지": (
                "DART API 키를 찾지 못했습니다."
            ),
            "재무기간": {},
            "배당": {},
            "자기주식": {},
            "주식총수": {},
        }

    financials = get_financial_periods(
        api_key,
        corp_code,
        maximum_success=6,
    )

    dividends = get_annual_series(
        api_key,
        DART_DIVIDEND_URL,
        corp_code,
        maximum_success=3,
    )

    treasury = get_annual_series(
        api_key,
        DART_TREASURY_URL,
        corp_code,
        maximum_success=2,
    )

    stock_total = get_stock_total_status(
        api_key,
        corp_code,
    )

    statuses = [
        financials.get("수집상태"),
        dividends.get("수집상태"),
        treasury.get("수집상태"),
        stock_total.get("수집상태"),
    ]

    normal_count = sum(
        status == "정상"
        for status in statuses
    )

    if normal_count == len(statuses):
        overall = "정상"
    elif normal_count > 0:
        overall = "부분성공"
    else:
        overall = "실패"

    return {
        "전체수집상태": overall,
        "기업코드": corp_code,
        "재무기간": financials,
        "배당": dividends,
        "자기주식": treasury,
        "주식총수": stock_total,
        "수집시각": datetime.now(
            KST
        ).isoformat(),
        "데이터출처": (
            "금융감독원 OpenDART"
        ),
    }
