from analyzers.strategic_forward_value import build_strategic_forward_value


def env(current, future, quality=90):
    return {
        '사용가능': True,
        '모형사용가능': True,
        '현재점수': current,
        '3개월점수': future,
        '변화점수': future-current,
        '품질점수': quality,
    }


def valuation(*, base=100, future=200, current_eps=100, fy1=120, fy3=170, fy4=200,
              run_rate=1.3, cyclical=False, structural=True, growth_quality=90):
    reasons = ['사이클 고점 이익 영구화 위험'] if cyclical else []
    return {
        '현재재무기초가치': base,
        '재무적정가': base,
        '기본적정가': base,
        '성장적정가': future,
        'FY1예상EPS': fy1,
        '구조적실적가속': structural,
        '분기매출성장률': 25,
        '분기영업이익성장률': 60,
        '분기순이익성장률': 50,
        'FY1성장률': 20,
        '실적전환강도': 80,
        'TTM데이터품질': 90,
        '데이터신뢰도': 90,
        '미래성장모형': {
            '대상업종': True,
            '사용가능': True,
            '상태': '제한사용' if cyclical else '정상',
            '제한사유': reasons,
            '가치': future,
            'FY3EPS': fy3,
            'FY4EPS': fy4,
            '품질': growth_quality,
        },
        '적응형가치모형': {
            '현재재무기초가치': base,
            '현재EPS앵커': current_eps,
            '분기런레이트대정상화배수': run_rate,
        },
    }


def fundamentals(forward_signal=70):
    return {
        '향후이익방향대용': {'신호': forward_signal, '데이터품질': 90}
    }


def industry(mid=40, long=55, quality=90):
    return {
        '분석상태': '정상',
        '중기산업선행': {'신호': mid, '데이터품질': quality},
        '장기산업사이클': {'신호': long, '데이터품질': quality},
        '시장폭': {'MA20상회비율': 70, 'MA120상회비율': 75},
        '상대강도': {'기준시장대비초과수익률': 6},
    }


def consensus(external_eps=130, n=12, opinion=4.0):
    return {'사용가능': True, 'FY1_EPS': external_eps, '추정기관수': n, '투자의견': opinion, '데이터품질': 90, '목표주가': 0}


def run(name, v, ie, f=None, ia=None, cons=None):
    result = build_strategic_forward_value(
        valuation=v,
        fundamentals_analysis=f or fundamentals(),
        industry_analysis=ia or industry(),
        industry_environment=ie,
        external_consensus=cons or consensus(),
        global_macro_context={},
        stock_code='TEST',
        company_name=name,
    )
    return result


def main():
    # 1) 산업 개선 + 성장 미반영: 미래가치 대상이어야 함.
    emerging = run('산업개선형', valuation(base=100, future=220, current_eps=100, fy1=115, fy3=180, fy4=210, run_rate=1.2), env(58, 78))
    # 2) 이미 FY1에 대부분 반영 + 사이클 고점: 미래가치가 강하게 줄어야 함.
    realized_cycle = run('사이클실현형', valuation(base=100, future=220, current_eps=100, fy1=185, fy3=190, fy4=205, run_rate=7.0, cyclical=True), env(82, 78))
    # 3) 약한 산업 + 약한 회사: 미래가치 비대상/저인정이어야 함.
    weak_v = valuation(base=100, future=180, current_eps=100, fy1=102, fy3=120, fy4=125, run_rate=1.0, structural=False, growth_quality=65)
    weak_v.update({'분기매출성장률': 2, '분기영업이익성장률': 3, '분기순이익성장률': 2, 'FY1성장률': 2, '실적전환강도': 5})
    weak = run('약한산업형', weak_v, env(38, 35), f=fundamentals(5), ia=industry(mid=-10, long=-20), cons={'사용가능': False})
    # 4) 현재 활황이지만 둔화: 같은 수준의 성장기업이라도 개선형보다 낮아야 함.
    slowing = run('활황둔화형', valuation(base=100, future=220, current_eps=100, fy1=115, fy3=180, fy4=210), env(82, 70))
    # 5) 산업환경 엔진 미검증: 고성장 등급 승격 금지.
    no_env = run('산업환경미검증', valuation(base=100, future=220, current_eps=100, fy1=115, fy3=180, fy4=210), {})

    assert emerging['미래가치자격']['등급'] in {'정상 대상', '고성장 대상'}
    assert emerging['미래증분가치'] > realized_cycle['미래증분가치']
    assert realized_cycle['미반영성장비율'] < emerging['미반영성장비율']
    assert realized_cycle['사이클지속가능성배수'] < emerging['사이클지속가능성배수']
    assert weak['미래가치자격']['등급'] == '비대상'
    assert weak['미래증분가치'] <= 8.0
    assert slowing['산업기회배수'] <= emerging['산업기회배수']
    assert no_env['미래가치자격']['등급'] != '고성장 대상'
    assert all(r['전략펀더멘털적정가'] >= r['기초가치'] for r in [emerging, realized_cycle, weak, slowing, no_env])

    print('FUTURE VALUE ELIGIBILITY V2: PASS')
    for r in [emerging, realized_cycle, weak, slowing, no_env]:
        print({
            'name': r['미래가치자격']['등급'],
            'eligibility_score': r['미래가치자격']['점수'],
            'industry': r['산업환경기회']['국면'],
            'industry_modifier': r['산업기회배수'],
            'unrealized_pct': r['미반영성장비율'],
            'sustainability': r['사이클지속가능성배수'],
            'future_increment': r['미래증분가치'],
            'fair_value': r['전략펀더멘털적정가'],
        })


if __name__ == '__main__':
    main()
