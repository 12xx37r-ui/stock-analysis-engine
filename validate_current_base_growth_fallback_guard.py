
from analyzers.strategic_forward_value import build_strategic_forward_value

def run_case(*, base, current_only, growth, future_model_value, future_state,
             fy1_growth, quarter_rev, quarter_op, quarter_net,
             forward_signal, industry_long):
    valuation = {
        "재무적정가": base,
        "기존V4재무적정가": base,
        "기본적정가": base,
        "성장적정가": growth,
        "현재재무기초가치": current_only,
        "미래성장모형": {
            "대상업종": True,
            "사용가능": True,
            "상태": future_state,
            "가치": future_model_value,
        },
        "적응형가치모형": {
            "미래총가치": future_model_value,
            "현재재무기초가치": current_only,
        },
        "분기매출성장률": quarter_rev,
        "분기영업이익성장률": quarter_op,
        "분기순이익성장률": quarter_net,
        "FY1성장률": fy1_growth,
        "구조적실적가속": False,
        "실적전환강도": 100.0,
        "TTM데이터품질": 90,
        "가치평가산업코드": "semiconductor",
    }
    fundamentals = {
        "향후이익방향대용": {
            "신호": forward_signal,
            "데이터품질": 90,
            "사용가능": True,
        }
    }
    industry = {"분석": {"장기": {"점수": industry_long, "데이터품질": 90}}}
    return build_strategic_forward_value(
        valuation=valuation,
        fundamentals_analysis=fundamentals,
        industry_analysis=industry,
        stock_code="TEST",
        company_name="TEST",
    )

samsung = run_case(
    base=450126.71,
    current_only=216973.47,
    growth=636058.66,
    future_model_value=588943.20,
    future_state="제한사용",
    fy1_growth=18.0,
    quarter_rev=130.0,
    quarter_op=1813.84,
    quarter_net=1299.89,
    forward_signal=98.15,
    industry_long=67.72,
)
assert abs(samsung["기초가치"] - 216973.47) < 0.01, samsung
assert samsung["기초가치출처"] == "현재재무기초가치", samsung
assert samsung["미래총가치출처"] == "FY3/FY4 미래성장모형", samsung

lges = run_case(
    base=87158.71,
    current_only=60877.86,
    growth=135096.00,
    future_model_value=13118.95,
    future_state="제한사용",
    fy1_growth=-9.74,
    quarter_rev=35.84,
    quarter_op=-76.98,
    quarter_net=-462.72,
    forward_signal=-24.48,
    industry_long=-40.0,
)
assert abs(lges["기초가치"] - 87158.71) < 0.01, lges
assert lges["기초가치출처"] == "기존 기본적정가", lges
assert lges["미래총가치출처"] == "가격독립 성장적정가 시나리오", lges

print("CURRENT BASE / GROWTH FALLBACK GUARD: PASS")
print("Samsung-like:", samsung["기초가치"], samsung["기초가치출처"], samsung["미래총가치출처"])
print("LGES-like:", lges["기초가치"], lges["기초가치출처"], lges["미래총가치출처"])
