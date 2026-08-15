from analyzers.strategic_forward_value import build_strategic_forward_value

def make_case(base, current_only, growth, future_model_value, future_state, limited_reasons,
              fy1_growth, quarter_rev, quarter_op, quarter_net, forward_signal, structural=False):
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
            "제한사유": limited_reasons,
            "가치": future_model_value,
        },
        "적응형가치모형": {"미래총가치": future_model_value, "현재재무기초가치": current_only},
        "분기매출성장률": quarter_rev,
        "분기영업이익성장률": quarter_op,
        "분기순이익성장률": quarter_net,
        "FY1성장률": fy1_growth,
        "구조적실적가속": structural,
        "실적전환강도": 100.0,
        "TTM데이터품질": 95,
        "가치평가산업코드": "semiconductor",
    }
    fundamentals = {"향후이익방향대용": {"신호": forward_signal, "데이터품질": 95, "사용가능": True}}
    return build_strategic_forward_value(
        valuation=valuation,
        fundamentals_analysis=fundamentals,
        industry_analysis={},
        external_consensus=None,
        stock_code="TEST",
        company_name="TEST",
    )

samsung = make_case(
    450126.71, 216944.97, 636058.66, 588943.20, "제한사용",
    ["사이클 고점 이익 영구화 위험"], 18.0, 130.0, 1813.84, 1299.89, 98.15, False
)
assert abs(samsung["기초가치"] - 216944.97) < 0.01
assert samsung["미래증분상한비율"] == 65.0
assert samsung["미래증분가치"] <= samsung["미래증분상한금액"] + 0.02

lges = make_case(
    87158.71, 60877.86, 135096.00, 13118.95, "제한사용",
    ["실적 급하락 전환", "이익저점 국면 · 회복가치 우선", "장기 산업사이클 과도한 역풍"],
    -9.74, 35.84, -76.98, -462.72, -24.48, False
)
assert lges["미래증분상한비율"] == 70.0
assert lges["미래증분가치"] <= lges["미래증분상한금액"] + 0.02

print("FUTURE INCREMENT CAP POLICY: PASS")
print("Samsung-like:", samsung["기초가치"], samsung["상한적용전미래증분가치"], samsung["미래증분상한금액"], samsung["미래증분가치"], samsung["전략펀더멘털적정가"])
print("LGES-like:", lges["기초가치"], lges["미래증분상한금액"], lges["미래증분가치"], lges["전략펀더멘털적정가"])
