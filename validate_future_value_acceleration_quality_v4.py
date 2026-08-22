from analyzers.strategic_forward_value import earnings_acceleration_quality_axis


def period(year, code, rev, op, net):
    return {"사업연도": year, "보고서코드": code, "지표": {"매출": rev, "영업이익": op, "순이익": net}}

# OpenDART 누적값 형태: Q1, H1, Q3 cumulative, FY cumulative
# Case A: 매출/영업이익/마진이 2개 이상 비교분기에서 동반 개선
structural = {"재무기간": {"기간목록": [
    period(2026,"11012",230,35,28),  # 2026 Q2 standalone = 130/22/18
    period(2026,"11013",100,13,10),
    period(2025,"11011",400,38,30),
    period(2025,"11014",290,25,20),  # Q3 standalone=100/8/6
    period(2025,"11012",190,17,13),  # Q2 standalone=100/9/7
    period(2025,"11013",90,8,6),
]}}
a = earnings_acceleration_quality_axis(structural,{})
assert a["사용가능"] is True, a
assert a["점수"] >= 65, a
assert a["지속가능성배수"] >= 1.0, a
assert a["기저효과위험"] is False, a

# Case B: 매출은 거의 정체, 전년 영업이익률 1%의 낮은 기저에서 이익만 폭증
base_spike = {"재무기간": {"기간목록": [
    period(2026,"11012",201,25,18),   # Q2 standalone=101/20/14
    period(2026,"11013",100,5,4),
    period(2025,"11011",400,20,14),
    period(2025,"11014",300,17,12),
    period(2025,"11012",200,11,8),   # Q2 standalone=100/1/1
    period(2025,"11013",100,10,7),
]}}
b = earnings_acceleration_quality_axis(base_spike,{})
assert b["사용가능"] is True, b
assert b["기저효과위험"] is True, b
assert b["이익단독급등"] is True, b
assert b["지속가능성배수"] < 0.8, b
assert b["점수"] < a["점수"], (a,b)

# Case C: 히스토리 없음 -> 강제 추정하지 않고 fallback
c = earnings_acceleration_quality_axis({}, {})
assert c["사용가능"] is False, c
assert c["점수"] == 50.0, c

print("PASS: future value acceleration quality v4")
print("structural", a)
print("base_spike", b)
