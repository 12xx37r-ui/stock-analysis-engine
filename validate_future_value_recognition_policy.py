from analyzers.valuation import build_future_growth_model, VALUATION_PROFILES
from analyzers.strategic_forward_value import build_strategic_forward_value

profile = VALUATION_PROFILES["battery"]

future = build_future_growth_model(
    profile_code="battery",
    profile=profile,
    ttm_eps=0.0,
    normalized_eps=1745.66,
    fy1_eps=1575.58,
    fy2_eps=1468.12,
    fy1_growth=-0.0974,
    fy2_growth=-0.0682,
    quarter={
        "revenue_yoy": 35.84,
        "operating_yoy": -76.98,
        "net_yoy": -462.72,
        "잠정실적반영": True,
    },
    revenue_growth_3y=-0.2985,
    operating_growth_3y=-0.3777,
    net_growth_3y=-0.9507,
    earnings_signal=-60.0,
    forward_signal=-24.48,
    industry={"available": True, "long": -40.0},
    operating_margin=-0.01,
    net_margin=-0.04,
    target_per=8.02,
    per_max=24.0,
    cost_of_equity=0.10,
    share_quality=100.0,
    ttm_quality=86.0,
    structural_acceleration=False,
    negative_transition=True,
    earnings_trough=True,
    earnings_value=22445.75,
)

assert future["사용가능"] is True, future
assert future["상태"] == "제한사용", future
assert future["가치"] > 0, future
assert 0 < future["모형인정률"] <= 30, future
assert future["차단사유"] == [], future
assert "실적 급하락 전환" in future["제한사유"], future
assert "이익저점 국면 · 회복가치 우선" in future["제한사유"], future

valuation = {
    "재무적정가": 87152.73,
    "기존V4재무적정가": 87152.73,
    "기본적정가": 87152.73,
    "성장적정가": 135086.73,
    "현재재무기초가치": 60874.64,
    "미래성장모형": future,
    "적응형가치모형": {"미래총가치": future["가치"], "현재재무기초가치": 60874.64},
    "분기매출성장률": 35.84,
    "분기영업이익성장률": -76.98,
    "분기순이익성장률": -462.72,
    "FY1성장률": -9.74,
    "구조적실적가속": False,
    "실적전환강도": 204.15,
    "TTM데이터품질": 86,
    "가치평가산업코드": "battery",
}

fundamentals_analysis = {
    "향후이익방향대용": {
        "신호": -24.48,
        "데이터품질": 80,
        "사용가능": True,
    }
}
industry_analysis = {
    "분석": {
        "장기": {
            "점수": 25,
            "데이터품질": 70,
        }
    }
}

strategic = build_strategic_forward_value(
    valuation=valuation,
    fundamentals_analysis=fundamentals_analysis,
    industry_analysis=industry_analysis,
    stock_code="373220",
    company_name="LG에너지솔루션",
)

assert strategic["원시미래총가치"] >= valuation["성장적정가"], strategic
assert strategic["미래총가치출처"] == "가격독립 성장적정가 시나리오", strategic
assert strategic["원시미래증분가치"] > 0, strategic
assert strategic["미래가치인정률"] > 0, strategic
assert strategic["미래증분가치"] > 0, strategic
assert strategic["전략펀더멘털적정가"] > valuation["기본적정가"], strategic
assert strategic["전략펀더멘털적정가"] < valuation["성장적정가"], strategic

print("FUTURE VALUE RECOGNITION POLICY: PASS")
print("future_model_value", round(future["가치"], 2))
print("model_recognition_pct", round(future["모형인정률"], 2))
print("raw_growth_gap", strategic["원시미래증분가치"])
print("strategic_recognition_pct", strategic["미래가치인정률"])
print("recognized_increment", strategic["미래증분가치"])
print("strategic_fair", strategic["전략펀더멘털적정가"])
