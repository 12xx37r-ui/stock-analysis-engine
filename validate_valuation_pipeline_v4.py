"""가치평가 계약 v4 데이터 자격·전자부품·잠정실적 회귀검증."""
from __future__ import annotations

from analyzers.valuation import calculate_value
from collectors.company import classify_dart_industry_detail
from collectors.fundamentals import parse_stock_total_rows
from collectors.provisional import parse_provisional_document


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


def build_bundle(provisional):
    shares = 77_600_000
    stock_total = parse_stock_total_rows(
        [{
            "se": "합계",
            "isu_stock_totqy": str(shares),
            "istc_totqy": str(shares),
            "tesstk_co": "0",
            "distb_stock_co": str(shares),
            "stlm_dt": "2026-03-31",
        }],
        2026,
        "11013",
        "000",
        "정상",
    )
    return {
        "주식총수": stock_total,
        "잠정실적": provisional,
        "재무기간": {"기간목록": [
            period(2026, "11013", 3_100_000_000_000, 310_000_000_000, 230_000_000_000, 12_000_000_000_000, 8_000_000_000_000, 2_100_000_000_000, 2_500_000_000_000, 160_000_000_000),
            period(2025, "11011", 11_500_000_000_000, 1_000_000_000_000, 760_000_000_000, 11_500_000_000_000, 7_700_000_000_000, 2_000_000_000_000, 2_400_000_000_000, 520_000_000_000),
            period(2025, "11014", 8_300_000_000_000, 650_000_000_000, 480_000_000_000, 11_250_000_000_000, 7_500_000_000_000, 1_900_000_000_000, 2_350_000_000_000, 350_000_000_000),
            period(2025, "11012", 5_200_000_000_000, 350_000_000_000, 250_000_000_000, 11_000_000_000_000, 7_300_000_000_000, 1_800_000_000_000, 2_300_000_000_000, 190_000_000_000),
            period(2025, "11013", 2_500_000_000_000, 140_000_000_000, 95_000_000_000, 10_800_000_000_000, 7_100_000_000_000, 1_750_000_000_000, 2_250_000_000_000, 75_000_000_000),
            period(2024, "11011", 10_000_000_000_000, 650_000_000_000, 480_000_000_000, 10_400_000_000_000, 6_900_000_000_000, 1_650_000_000_000, 2_200_000_000_000, 320_000_000_000),
            period(2023, "11011", 8_800_000_000_000, 520_000_000_000, 390_000_000_000, 10_000_000_000_000, 6_700_000_000_000, 1_550_000_000_000, 2_100_000_000_000, 260_000_000_000),
        ]},
    }


def calculate(bundle, price=1_142_000):
    company = {
        "기업명": "삼성전기",
        "종목코드": "009150",
        "산업코드": "electronic_components",
        "가치평가산업코드": "electronic_components",
        "OpenDART업종코드": "26299",
        "산업분류출처": "수동 종목매핑",
        "산업분류신뢰도": 100,
        "산업프로필버전": "3.0.0",
    }
    financial = {
        "재무지표": {"ROE": 10.0, "부채비율": 66.0, "영업이익률": 9.0, "순이익률": 6.5},
        "성장지표": {"매출3년성장률": 14.0, "영업이익3년성장률": 32.0, "순이익3년성장률": 28.0},
    }
    market = {"현재가": price, "EPS": 12_000, "BPS": 155_000, "PER": 30.0, "PBR": 4.0}
    fundamentals_analysis = {
        "분기실적": {"신호": 65, "데이터품질": 90},
        "향후이익방향대용": {"신호": 55, "데이터품질": 75, "애널리스트컨센서스반영": False},
        "현금흐름재무안전성": {"신호": 70, "데이터품질": 90},
    }
    industry_analysis = {
        "분석상태": "정상",
        "중기산업선행": {"신호": 35, "데이터품질": 85},
        "장기산업사이클": {"신호": 50, "데이터품질": 85},
        "산업국면": "구조적 성장",
    }
    return calculate_value(
        financial,
        market,
        fundamentals_analysis,
        bundle,
        industry_analysis,
        {"산업코드": "electronic_components"},
        company,
    )


def main():
    classification = classify_dart_industry_detail("26299", "삼성전기", "009150")
    assert classification["산업코드"] == "electronic_components", classification
    assert classification["분류신뢰도"] >= 90, classification

    html = """
    <html><body><div>(단위 : 백만원)</div>
    <div>2026년 04월 01일부터 2026년 06월 30일까지</div>
    <table>
      <tr><td>매출액</td><td>당해실적</td><td>3,457,200</td></tr>
      <tr><td>영업이익</td><td>당해실적</td><td>440,400</td></tr>
      <tr><td>지배기업 소유주지분 순이익</td><td>당해실적</td><td>315,000</td></tr>
    </table></body></html>
    """.encode("utf-8")
    disclosure = {"접수번호": "20260730000001", "공시일": "20260730", "보고서명": "영업(잠정)실적(공정공시)"}
    provisional = parse_provisional_document(html, disclosure)
    assert provisional["사용가능"] is True, provisional
    assert provisional["기간키"] == 2026 * 4 + 2, provisional
    assert provisional["지표"]["매출"] == 3_457_200_000_000, provisional

    value = calculate(build_bundle(provisional))
    assert value["가치평가엔진버전"] == "6.7.2-valuation-contract-v4", value
    assert value["가치평가산업코드"] == "electronic_components", value
    assert value["TTM잠정실적반영"] is True, value
    assert value["유효재무기준분기키"] == 2026 * 4 + 2, value
    assert value["데이터자격검사"]["통과"] is True, value["데이터자격검사"]
    assert value["최종값사용가능"] is True, value["이상치검사"]
    assert value["미래성장모형"]["사용가능"] is True, value["미래성장모형"]
    assert value["미래성장가치"] > value["PER기준적정가"], value
    assert value["FY3예상EPS"] > value["FY2예상EPS"], value
    assert value["FY4예상EPS"] > value["FY3예상EPS"], value

    blocked_provisional = {
        "수집상태": "검토필요",
        "사용가능": False,
        "접수번호": "20260730000002",
        "공시일": "20260730",
        "보고서명": "영업(잠정)실적(공정공시)",
        "사업연도": 2026,
        "분기": 2,
        "기간키": 2026 * 4 + 2,
        "검증사유": ["순이익 미확보"],
    }
    fallback = calculate(build_bundle(blocked_provisional), price=1_142_000)
    assert fallback["데이터자격검사"]["통과"] is True, fallback["데이터자격검사"]
    assert fallback["데이터자격검사"]["상태"] == "주의통과", fallback["데이터자격검사"]
    assert fallback["데이터자격검사"]["정식보고서대체평가"] is True, fallback["데이터자격검사"]
    assert fallback["최종값사용가능"] is True, fallback
    assert fallback["산출상태"] == "정상", fallback
    assert fallback["TTM잠정실적반영"] is False, fallback
    assert fallback["가치신뢰도"] <= 72, fallback

    stale_bundle = build_bundle(blocked_provisional)
    stale_bundle["재무기간"]["기간목록"] = [
        row for row in stale_bundle["재무기간"]["기간목록"]
        if not (row["사업연도"] == 2026 and row["보고서코드"] == "11013")
    ]
    stale = calculate(stale_bundle, price=1_142_000)
    assert stale["데이터자격검사"]["통과"] is False, stale["데이터자격검사"]
    assert stale["최종값사용가능"] is False, stale

    print("VALUATION PIPELINE V4: PASS")
    print("- classification:", classification)
    print("- provisional period:", provisional["사업연도"], provisional["분기"])
    print("- usable fair:", round(value["기본적정가"]), value["데이터자격검사"]["상태"])
    print("- formal fallback:", round(fallback["기본적정가"]), fallback["데이터자격검사"]["주의사유"])
    print("- stale block:", stale["데이터자격검사"]["중단사유"])


if __name__ == "__main__":
    main()
