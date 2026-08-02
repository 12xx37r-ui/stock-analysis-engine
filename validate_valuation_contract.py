"""가치평가 계약 v4 회귀검증.

삼성전자형 복합·사이클 기업에서 구형 PBR 값이 최종 적정가로
잘못 채택되는 회귀를 차단한다.
"""

from analyzers.valuation import calculate_value
from collectors.fundamentals import parse_stock_total_rows


def period(year, code, revenue, operating, net, equity, liabilities, cash, fcf):
    return {
        "사업연도": year,
        "보고서코드": code,
        "보고서명": {"11013": "1분기", "11012": "반기", "11014": "3분기", "11011": "사업보고서"}[code],
        "수집상태": "정상",
        "지표": {
            "매출": revenue,
            "영업이익": operating,
            "순이익": net,
            "자본총계": equity,
            "부채총계": liabilities,
            "현금및현금성자산": cash,
            "총차입금": 31_000_000_000_000,
            "잉여현금흐름추정": fcf,
        },
    }


def main():
    financial = {
        "재무지표": {"ROE": 10.36, "부채비율": 29.94, "영업이익률": 13.07, "순이익률": 13.55},
        "성장지표": {"매출3년성장률": 28.84, "영업이익3년성장률": 563.94, "순이익3년성장률": 191.90},
    }
    market = {
        "현재가": 262_500,
        "EPS": 6_564,
        "BPS": 63_997,
        "PER": 39.99,
        "PBR": 4.10,
    }
    stock_total = parse_stock_total_rows(
        [
            {
                "se": "합계",
                "isu_stock_totqy": "25,000,000,000",
                "istc_totqy": "6,792,669,250",
                "tesstk_co": "12,345,678",
                "distb_stock_co": "6,780,323,572",
                "stlm_dt": "2026-03-31",
            }
        ],
        2026,
        "11013",
        "000",
        "정상",
    )
    assert stock_total["수집상태"] == "정상"
    assert stock_total["가치평가주식수"] == 6_780_323_572

    fundamentals_bundle = {
        "주식총수": stock_total,
        "재무기간": {
            "기간목록": [
                period(2026, "11013", 133_873_444_000_000, 57_232_797_000_000, 47_225_272_000_000, 486_635_976_000_000, 146_703_628_000_000, 73_306_751_000_000, 22_097_151_000_000),
                period(2025, "11011", 333_605_938_000_000, 43_601_051_000_000, 45_206_805_000_000, 436_320_337_000_000, 130_621_773_000_000, 57_856_378_000_000, 33_161_999_000_000),
                period(2025, "11014", 239_768_567_000_000, 23_527_391_000_000, 25_565_060_000_000, 413_501_494_000_000, 110_158_092_000_000, 53_399_483_000_000, 17_121_837_000_000),
                period(2025, "11012", 153_706_820_000_000, 11_361_329_000_000, 13_339_313_000_000, 399_561_967_000_000, 105_313_218_000_000, 47_120_025_000_000, 6_738_441_000_000),
                period(2025, "11013", 79_140_503_000_000, 6_685_272_000_000, 8_222_878_000_000, 391_286_000_000_000, 109_762_479_000_000, 45_000_000_000_000, 4_100_000_000_000),
                period(2024, "11011", 300_870_903_000_000, 6_567_000_000_000, 15_487_000_000_000, 390_000_000_000_000, 112_000_000_000_000, 45_000_000_000_000, 12_000_000_000_000),
            ]
        }
    }
    fundamentals_analysis = {
        "분기실적": {"신호": 100, "데이터품질": 90},
        "향후이익방향대용": {"신호": 98.15, "데이터품질": 75, "애널리스트컨센서스반영": False},
        "현금흐름재무안전성": {"신호": 93.16, "데이터품질": 100},
    }
    industry_analysis = {
        "분석상태": "정상",
        "중기산업선행": {"신호": -20, "데이터품질": 100},
        "장기산업사이클": {"신호": 45, "데이터품질": 100},
        "산업국면": "장기상승 중 단기조정",
    }
    company_info = {
        "기업명": "삼성전자",
        "종목코드": "005930",
        "산업코드": "semiconductor",
        "가치평가산업코드": "semiconductor",
        "OpenDART업종코드": "264",
        "산업분류출처": "회귀검증",
        "산업분류신뢰도": 100,
        "산업프로필버전": "3.0.0",
    }

    value = calculate_value(
        financial,
        market,
        fundamentals_analysis,
        fundamentals_bundle,
        industry_analysis,
        {"산업코드": "semiconductor"},
        company_info,
    )

    assert value["가치평가계약버전"] == "4.0"
    assert value["가치평가모형개정버전"] == "future-growth-v1.0.1-insurance-financials", value
    assert value["최종값사용가능"] is True, value["이상치검사"]
    assert value["복합기업대용모형"] is True
    assert value["TTMEPS"] > value["EPS"]
    assert value["기본적정가"] > 150_000, value
    assert value["기본적정가"] > value["PBR기준적정가"] * 1.8, value
    assert value["보수적적정가"] <= value["기본적정가"] <= value["성장적정가"]
    assert 10 <= value["목표PER"] <= 24

    # GitHub KIS_DISABLED=1 경로 회귀검증: Yahoo 현재가만 있어도
    # OpenDART 주식총수 + DART 재무로 EPS/BPS와 적정가를 산출해야 한다.
    no_kis_market = {"현재가": 262_500, "거래량": 10_000_000}
    no_kis_value = calculate_value(
        financial,
        no_kis_market,
        fundamentals_analysis,
        fundamentals_bundle,
        industry_analysis,
        {"산업코드": "semiconductor"},
        company_info,
    )
    assert no_kis_value["최종값사용가능"] is True, no_kis_value["이상치검사"]
    assert no_kis_value["발행주식수추정"] == 6_780_323_572
    assert no_kis_value["TTMEPS"] > 0
    assert no_kis_value["BPS"] > 0
    assert no_kis_value["기본적정가"] > 0

    print("VALUATION CONTRACT V4: PASS")
    print(
        "KIS-disabled regression:",
        f"shares={no_kis_value['발행주식수추정']:,}",
        f"TTM EPS={no_kis_value['TTMEPS']:,.0f}",
        f"fair={no_kis_value['기본적정가']:,.0f}",
    )
    print(
        "Samsung regression:",
        f"TTM EPS={value['TTMEPS']:,.0f}",
        f"FY1 EPS={value['FY1예상EPS']:,.0f}",
        f"fair={value['기본적정가']:,.0f}",
        f"PBR floor={value['PBR기준적정가']:,.0f}",
    )

    from validate_sdi_trough import run_validation as run_sdi_trough_validation
    sdi_value = run_sdi_trough_validation()
    print(
        "Samsung SDI trough regression:",
        f"earnings={sdi_value['PER기준적정가']:,.0f}",
        f"asset={sdi_value['PBR기준적정가']:,.0f}",
        f"graham={sdi_value['그레이엄가치']:,.0f}",
        f"fair={sdi_value['기본적정가']:,.0f}",
    )


if __name__ == "__main__":
    main()
