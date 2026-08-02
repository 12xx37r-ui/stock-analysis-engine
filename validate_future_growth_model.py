"""미래성장가치 모형 v1 회귀검증.

검증 원칙
- 현재가를 산식과 주식수 결정에 사용하지 않는다.
- 구조적 성장 증거가 있는 성장형 업종에만 적용한다.
- FY3·FY4 성장률은 감쇠되고 업종 상한을 넘지 않는다.
- EPS·가치 상한을 넘지 않는다.
- 비성장·급하락·이익저점 국면은 자동 차단한다.
"""
from __future__ import annotations

from analyzers.valuation import (
    FUTURE_GROWTH_CONFIG,
    build_future_growth_model,
    calculate_value,
)
from collectors.fundamentals import parse_stock_total_rows


def period(year, code, revenue, operating, net, equity, liabilities, cash, debt, fcf):
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
            "총차입금": debt,
            "잉여현금흐름추정": fcf,
        },
    }


def bundle():
    shares = 75_547_250
    stock_total = parse_stock_total_rows(
        [{
            "se": "합계",
            "isu_stock_totqy": "77600680",
            "istc_totqy": "77600680",
            "tesstk_co": "2053430",
            "distb_stock_co": str(shares),
            "stlm_dt": "2025-12-31",
        }],
        2025,
        "11011",
        "000",
        "정상",
    )
    provisional = {
        "수집상태": "정상",
        "사용가능": True,
        "접수번호": "20260730800303",
        "공시일": "20260730",
        "사업연도": 2026,
        "분기": 2,
        "기간키": 2026 * 4 + 2,
        "지표": {
            "매출": 3_457_205_000_000,
            "영업이익": 433_269_000_000,
            "순이익": 315_702_000_000,
        },
        "데이터품질": 86,
    }
    return {
        "주식총수": stock_total,
        "잠정실적": provisional,
        "재무기간": {"기간목록": [
            period(2026, "11013", 3_209_113_412_582, 280_572_751_176, 252_687_583_556, 10_091_093_028_695, 5_569_390_662_139, 3_243_304_854_863, 2_646_014_498_441, 520_000_000_000),
            period(2025, "11011", 11_314_459_238_100, 913_331_178_557, 730_989_517_218, 9_797_343_882_863, 4_798_551_372_605, 2_701_205_916_236, 2_191_798_953_235, 650_000_000_000),
            period(2025, "11014", 8_412_313_988_630, 673_835_267_071, 503_689_930_802, 9_425_735_078_673, 4_416_478_078_204, 2_767_369_756_303, 126_198_000_000, 430_000_000_000),
            period(2025, "11012", 5_523_278_231_955, 413_557_994_356, 278_838_146_459, 9_015_420_339_369, 4_185_128_646_957, 2_541_281_740_080, 157_108_991_973, 260_000_000_000),
            period(2025, "11013", 2_738_649_099_826, 200_549_840_807, 141_602_249_084, 9_047_891_195_336, 4_244_639_395_469, 2_542_253_527_843, 206_688_466_029, 120_000_000_000),
            period(2024, "11011", 10_294_102_976_435, 735_005_856_995, 703_215_637_082, 9_015_854_031_770, 3_776_548_889_114, 2_013_326_031_516, 244_127_399_380, 480_000_000_000),
            period(2023, "11011", 8_900_000_000_000, 530_000_000_000, 450_000_000_000, 8_600_000_000_000, 3_500_000_000_000, 1_800_000_000_000, 260_000_000_000, 350_000_000_000),
        ]},
    }


def calculate(price: float):
    financial = {
        "재무지표": {"ROE": 7.46, "부채비율": 48.98, "영업이익률": 8.07, "순이익률": 6.46},
        "성장지표": {"매출3년성장률": 27.24, "영업이익3년성장률": 38.27, "순이익3년성장률": 62.27},
    }
    market = {
        "현재가": price,
        "시가총액": 853_002,
        "EPS": 9_099,
        "BPS": 126_302,
        "PER": 125.51,
        "PBR": 9.04,
    }
    fundamentals_analysis = {
        "분기실적": {"신호": 90.73, "데이터품질": 90},
        "향후이익방향대용": {"신호": 73.06, "데이터품질": 75, "애널리스트컨센서스반영": False},
        "현금흐름재무안전성": {"신호": 20, "데이터품질": 80},
    }
    industry_analysis = {
        "분석상태": "정상",
        "중기산업선행": {"신호": -31.29, "데이터품질": 97},
        "장기산업사이클": {"신호": 34.62, "데이터품질": 97},
        "산업국면": "장기상승 중 단기조정",
    }
    company = {
        "기업명": "삼성전기",
        "종목코드": "009150",
        "산업코드": "electronic_components",
        "가치평가산업코드": "electronic_components",
        "OpenDART업종코드": "2622",
        "산업분류출처": "수동 종목매핑",
        "산업분류신뢰도": 100,
        "산업프로필버전": "3.0.0",
    }
    return calculate_value(
        financial,
        market,
        fundamentals_analysis,
        bundle(),
        industry_analysis,
        {"산업코드": "electronic_components"},
        company,
    )


def direct_model(**overrides):
    args = {
        "profile_code": "electronic_components",
        "profile": {"growth": True, "cyclical": True},
        "ttm_eps": 13_000,
        "normalized_eps": 10_000,
        "fy1_eps": 15_000,
        "fy2_eps": 17_000,
        "fy1_growth": 0.20,
        "fy2_growth": 0.12,
        "quarter": {"revenue_yoy": 20, "operating_yoy": 70, "net_yoy": 65, "잠정실적반영": True},
        "revenue_growth_3y": 0.25,
        "operating_growth_3y": 0.38,
        "net_growth_3y": 0.55,
        "earnings_signal": 80,
        "forward_signal": 70,
        "industry": {"available": True, "long": 35},
        "operating_margin": 0.10,
        "net_margin": 0.07,
        "target_per": 20,
        "per_max": 28,
        "cost_of_equity": 0.095,
        "share_quality": 100,
        "ttm_quality": 86,
        "structural_acceleration": True,
        "negative_transition": False,
        "earnings_trough": False,
        "earnings_value": 280_000,
    }
    args.update(overrides)
    return build_future_growth_model(**args)


def main():
    high_price = calculate(1_142_000)
    low_price = calculate(114_200)

    assert high_price["가치평가모형개정버전"] == "future-growth-v1.0.1-insurance-financials"
    assert high_price["미래성장모형"]["사용가능"] is True, high_price["미래성장모형"]
    assert high_price["미래성장모형"]["현재가미사용"] is True
    assert high_price["발행주식수추정"] == 75_547_250, high_price["발행주식수후보"]
    assert "현재가·시가총액 미사용" in high_price["발행주식수결정원칙"]
    assert high_price["재무적정가"] == low_price["재무적정가"], (high_price["재무적정가"], low_price["재무적정가"])
    assert high_price["미래성장가치"] == low_price["미래성장가치"]
    assert high_price["FY2예상EPS"] < high_price["FY3예상EPS"] < high_price["FY4예상EPS"]
    assert high_price["FY3성장률"] <= FUTURE_GROWTH_CONFIG["electronic_components"]["fy3_cap"] * 100 + 0.01
    assert high_price["FY4성장률"] <= FUTURE_GROWTH_CONFIG["electronic_components"]["fy4_cap"] * 100 + 0.01
    assert high_price["미래성장가치"] <= high_price["미래성장모형"]["가치상한"] + 0.05
    assert high_price["보수적적정가"] <= high_price["기본적정가"] <= high_price["성장적정가"]
    assert high_price["최종값사용가능"] is True, high_price["이상치검사"]

    non_growth = direct_model(profile_code="automotive", profile={"growth": False, "cyclical": True})
    assert non_growth["사용가능"] is False
    assert "미래성장모형 비대상 업종" in non_growth["차단사유"]

    downturn = direct_model(negative_transition=True)
    assert downturn["사용가능"] is False
    assert "실적 급하락 전환" in downturn["차단사유"]

    trough = direct_model(earnings_trough=True)
    assert trough["사용가능"] is False
    assert "이익저점 국면은 회복가치 모형 우선" in trough["차단사유"]

    peak = direct_model(ttm_eps=32_000, normalized_eps=10_000)
    assert peak["사용가능"] is False
    assert "사이클 고점 이익 영구화 위험" in peak["차단사유"]

    print("FUTURE GROWTH MODEL V1: PASS")
    print("- price-independent shares/fair value: PASS")
    print("- FY3/FY4 decay and caps: PASS")
    print("- non-growth/downturn/trough/cycle-peak blocks: PASS")
    print(
        "- Samsung Electro-Mechanics synthetic:",
        f"base={high_price['기본적정가']:,.0f}",
        f"growth={high_price['성장적정가']:,.0f}",
        f"future={high_price['미래성장가치']:,.0f}",
    )


if __name__ == "__main__":
    main()
