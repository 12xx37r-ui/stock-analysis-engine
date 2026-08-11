#!/usr/bin/env python3
"""보험·금융 재무계정, 업종분류, TTM 안전장치 회귀검사."""

from datetime import datetime

from analyzers.financial import analyze_financial
from analyzers.valuation import (
    _cost_of_equity,
    build_effective_ttm,
    build_ttm,
    calculate_value,
)
from collectors.company import classify_dart_industry_detail
from collectors.fundamentals import parse_financial_period


def quarter(year: int, q: int, revenue: float, net_income: float, operating_income: float = 0.0):
    return {
        "사업연도": year,
        "분기": q,
        "기간키": year * 4 + q,
        "단독분기변환": True,
        "지표": {
            "매출": revenue,
            "영업이익": operating_income,
            "순이익": net_income,
            "자산총계": 300_000.0,
            "부채총계": 240_000.0,
            "자본총계": 60_000.0,
        },
    }


def main() -> None:
    by_name = classify_dart_industry_detail("", "삼성생명", "032830")
    assert by_name["산업코드"] == "insurance", by_name

    by_ksic = classify_dart_industry_detail("65110", "테스트", "")
    assert by_ksic["산업코드"] == "insurance", by_ksic

    related_service = classify_dart_industry_detail("66121", "테스트", "")
    assert related_service["산업코드"] == "finance", related_service

    rows = [
        {
            "sj_div": "IS",
            "account_nm": "보험서비스수익(보험수익)",
            "thstrm_add_amount": "1000000",
            "thstrm_amount": "1000000",
            "ord": "1",
        },
        {
            "sj_div": "IS",
            "account_nm": "영업이익",
            "thstrm_add_amount": "120000",
            "thstrm_amount": "120000",
            "ord": "2",
        },
        {
            "sj_div": "IS",
            "account_nm": "지배기업의 소유주에게 귀속되는 분기순이익",
            "thstrm_add_amount": "90000",
            "thstrm_amount": "90000",
            "ord": "3",
        },
        {
            "sj_div": "BS",
            "account_nm": "자산총계",
            "thstrm_amount": "3000000",
            "ord": "4",
        },
        {
            "sj_div": "BS",
            "account_nm": "부채총계",
            "thstrm_amount": "2400000",
            "ord": "5",
        },
        {
            "sj_div": "BS",
            "account_nm": "자본총계",
            "thstrm_amount": "600000",
            "ord": "6",
        },
    ]
    parsed = parse_financial_period(rows, 2026, "11013", "CFS", "000", "정상")
    metrics = parsed["지표"]
    assert metrics["매출"] == 1_000_000.0, metrics
    assert metrics["영업이익"] == 120_000.0, metrics
    assert metrics["순이익"] == 90_000.0, metrics


    annual_raw = {
        "list": [
            {
                "account_nm": "보험서비스수익(보험수익)",
                "thstrm_amount": "1210000",
                "frmtrm_amount": "1100000",
                "bfefrmtrm_amount": "1000000",
                "ord": "1",
            },
            {
                "account_nm": "보험영업이익",
                "thstrm_amount": "145200",
                "frmtrm_amount": "125000",
                "bfefrmtrm_amount": "100000",
                "ord": "2",
            },
            {
                "account_nm": "당기순이익(손실)",
                "thstrm_amount": "85000",
                "frmtrm_amount": "75000",
                "bfefrmtrm_amount": "65000",
                "ord": "3",
            },
            {
                "account_nm": "자본총계",
                "thstrm_amount": "850000",
                "frmtrm_amount": "800000",
                "bfefrmtrm_amount": "760000",
                "ord": "4",
            },
            {
                "account_nm": "부채총계",
                "thstrm_amount": "4200000",
                "frmtrm_amount": "4000000",
                "bfefrmtrm_amount": "3800000",
                "ord": "5",
            },
        ]
    }
    insurance_quality = analyze_financial(annual_raw, industry_code="insurance")
    assert insurance_quality["재무분석모형버전"] == "financial-quality-v2.0.0", insurance_quality
    assert insurance_quality["원본"]["매출"] == 1_210_000.0, insurance_quality
    assert insurance_quality["성장지표"]["보험수익2년CAGR"] == 10.0, insurance_quality
    assert insurance_quality["버핏평가"]["점수"] > 0, insurance_quality
    assert insurance_quality["버핏평가"]["평가기준"] == "금융·보험업 전용 품질평가", insurance_quality
    assert "부채비율" not in insurance_quality["버핏평가"]["점수구성"], insurance_quality

    missing_revenue_quarters = [
        quarter(2026, 2, 0.0, 110.0),
        quarter(2026, 1, 0.0, 100.0),
        quarter(2025, 4, 0.0, 90.0),
        quarter(2025, 3, 0.0, 80.0),
    ]
    insurance_ttm = build_ttm(missing_revenue_quarters, profile_code="insurance")
    assert insurance_ttm["available"] is True, insurance_ttm
    assert insurance_ttm["quality"] == 84, insurance_ttm
    assert insurance_ttm["metrics"]["순이익"] == 380.0, insurance_ttm
    assert insurance_ttm["금융업매출대체허용"] is True, insurance_ttm

    general_ttm = build_ttm(missing_revenue_quarters, profile_code="general")
    assert general_ttm["available"] is False, general_ttm

    complete_quarters = [
        quarter(2026, 2, 1000.0, 110.0, 130.0),
        quarter(2026, 1, 900.0, 100.0, 120.0),
        quarter(2025, 4, 850.0, 90.0, 110.0),
        quarter(2025, 3, 800.0, 80.0, 100.0),
    ]
    complete_ttm = build_ttm(complete_quarters, profile_code="insurance")
    assert complete_ttm["available"] is True, complete_ttm
    assert complete_ttm["quality"] == 95, complete_ttm
    assert complete_ttm["metrics"]["매출"] == 3550.0, complete_ttm


    provisional = {
        "사용가능": True,
        "기간키": 2026 * 4 + 3,
        "사업연도": 2026,
        "분기": 3,
        "지표": {"매출": 0.0, "영업이익": None, "순이익": 130.0},
        "데이터품질": 80,
        "접수번호": "TEST",
    }
    provisional_rows = [
        quarter(2026, 2, 0.0, 110.0),
        quarter(2026, 1, 0.0, 100.0),
        quarter(2025, 4, 0.0, 90.0),
    ]
    effective = build_effective_ttm(
        provisional_rows,
        insurance_ttm,
        provisional,
        profile_code="insurance",
    )
    assert effective["available"] is True, effective
    assert effective["잠정실적반영"] is True, effective
    assert effective["metrics"]["순이익"] == 430.0, effective

    # 보험수익 계정이 표준화되지 않아 0이어도 순이익·자본·주식수가
    # 정상이면 보험 자본가치형 적정가가 산출되어야 한다.
    current_year = datetime.now().year

    def formal_period(year, report_code, net_income, equity):
        return {
            "사업연도": year,
            "보고서코드": report_code,
            "수집상태": "정상",
            "지표": {
                "매출": 0.0,
                "영업이익": 0.0,
                "순이익": net_income,
                "자산총계": equity * 6.0,
                "부채총계": equity * 5.0,
                "자본총계": equity,
                "현금및현금성자산": 0.0,
                "총차입금": 0.0,
                "잉여현금흐름추정": 0.0,
            },
        }

    y = current_year + 1
    full_periods = [
        formal_period(y, "11013", 600_000_000_000.0, 51_000_000_000_000.0),
        formal_period(y - 1, "11011", 2_050_000_000_000.0, 50_000_000_000_000.0),
        formal_period(y - 1, "11014", 1_550_000_000_000.0, 49_000_000_000_000.0),
        formal_period(y - 1, "11012", 1_050_000_000_000.0, 48_000_000_000_000.0),
        formal_period(y - 1, "11013", 500_000_000_000.0, 47_000_000_000_000.0),
        formal_period(y - 2, "11011", 1_800_000_000_000.0, 46_000_000_000_000.0),
        formal_period(y - 3, "11011", 1_650_000_000_000.0, 45_000_000_000_000.0),
    ]
    full_value = calculate_value(
        {
            "재무지표": {"ROE": 4.0, "부채비율": 500.0},
            "성장지표": {},
        },
        {"현재가": 311_500.0},
        fundamentals_bundle={
            "재무기간": {"기간목록": full_periods},
            "주식총수": {"가치평가주식수": 200_000_000},
        },
        company_info={
            "종목코드": "032830",
            "가치평가산업코드": "insurance",
            "산업분류신뢰도": 100,
            "산업프로필버전": "3.0.1",
            "OpenDART업종코드": "65110",
        },
    )
    assert full_value["가치평가산업코드"] == "insurance", full_value
    assert full_value["TTM데이터품질"] == 84, full_value
    assert full_value["TTMEPS"] > 0, full_value
    assert full_value["BPS"] > 0, full_value
    assert full_value["PBR기준적정가"] > 0, full_value
    assert full_value["잔여이익가치"] > 0, full_value
    assert full_value["기본적정가"] > 0, full_value
    assert full_value["최종값사용가능"] is True, full_value

    # 보험계약부채를 일반 제조업 차입금처럼 처리해 할인율을 올리지 않는다.
    insurance_coe = _cost_of_equity(4.409, "insurance")
    general_coe = _cost_of_equity(4.409, "general")
    assert insurance_coe == 0.09, insurance_coe
    assert general_coe == 0.115, general_coe

    print("INSURANCE FINANCIALS: PASS")


if __name__ == "__main__":
    main()
