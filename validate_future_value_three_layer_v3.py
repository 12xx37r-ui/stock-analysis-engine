from analyzers.strategic_forward_value import (
    confirmed_forward_financial_axis,
    future_value_eligibility_axis,
    company_industry_benefit_axis,
)

# 1) 일반 성장기업: 기본 적정가까지 선행재무층을 보존
normal = {
    '재무적정가': 140.0,
    '미래성장모형': {'대상업종': True, '사용가능': True, '품질': 85, '선정근거':['장기 산업사이클 우호']},
    '적응형가치모형': {'분기런레이트대정상화배수': 1.4, '이익급회복괴리': False},
    '구조적실적가속': True,
}
a = confirmed_forward_financial_axis(normal, 100.0)
assert abs(a['확인된선행재무가치'] - 40.0) < 1e-9

# 2) 사이클 극단 구간: 기본 적정가 gap을 전액 확정하지 않음
peak = {
    '재무적정가': 240.0,
    '미래성장모형': {'대상업종': True, '사용가능': True, '품질': 80, '제한사유':['사이클 고점 이익 영구화 위험']},
    '적응형가치모형': {'분기런레이트대정상화배수': 8.0, '이익급회복괴리': True},
}
b = confirmed_forward_financial_axis(peak, 100.0)
assert abs(b['확인된선행재무가치'] - 14.0) < 1e-9
assert b['선행재무확정률'] == 0.10

# 3) 미래가치 필터: 좋은 산업 + 직접수혜 + 성장 미반영 -> 정상 이상
company={'점수':75,'품질':90,'사용가능':True}
industry={'점수':70,'품질':85,'사용가능':True}
env={'점수':78,'품질':80,'사용가능':True}
expect={'점수':65,'품질':85,'사용가능':True}
benefit=company_industry_benefit_axis(normal,company,industry,expect)
elig=future_value_eligibility_axis(valuation=normal,company=company,industry=industry,industry_env=env,expectation=expect,
    unrealized={'미반영성장비율':0.60},sustainability={'지속가능성배수':0.95},beneficiary=benefit)
assert elig['등급'] in {'정상 대상','고성장 대상'}, elig

# 4) 같은 성장증거라도 사이클고점 + 이미 반영된 성장 -> 제한 이하
benefit2=company_industry_benefit_axis(peak,company,industry,expect)
elig2=future_value_eligibility_axis(valuation=peak,company=company,industry=industry,industry_env={'점수':55,'품질':80,'사용가능':True},expectation=expect,
    unrealized={'미반영성장비율':0.18},sustainability={'지속가능성배수':0.40},beneficiary=benefit2)
assert elig2['등급'] in {'비대상','제한 대상'}, elig2

print('THREE LAYER FUTURE VALUE V3: PASS')
print('normal confirmed=',a['확인된선행재무가치'],'eligibility=',elig['등급'],elig['점수'])
print('cycle peak confirmed=',b['확인된선행재무가치'],'eligibility=',elig2['등급'],elig2['점수'])
