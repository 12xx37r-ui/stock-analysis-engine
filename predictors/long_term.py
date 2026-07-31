def predict_long(financial, valuation):


    score = 50

    reasons = []


    # 1. 향후 이익 방향 30점

    growth = financial.get(
        "성장지표",
        {}
    )


    profit_growth = growth.get(
        "영업이익3년성장률",
        0
    )


    net_growth = growth.get(
        "순이익3년성장률",
        0
    )


    if profit_growth > 20:

        score += 15

        reasons.append(
            "영업이익 성장성 우수"
        )


    if net_growth > 20:

        score += 15

        reasons.append(
            "순이익 성장성 우수"
        )


    if profit_growth < 0:

        score -= 15

        reasons.append(
            "이익 감소"
        )



    # 2. 산업 사이클 / 경쟁력 자리

    reasons.append(
        "산업 사이클 데이터 연결 예정"
    )


    reasons.append(
        "시장점유율 데이터 연결 예정"
    )



    # 3. 가치평가 20점

    gap = valuation.get(
        "현재가대비",
        0
    )


    if gap > 20:

        score += 20

        reasons.append(
            "적정가 대비 저평가"
        )


    elif gap < -30:

        score -= 20

        reasons.append(
            "적정가 대비 고평가"
        )



    # 4. 재무 안정성 15점

    roe = financial.get(
        "재무지표",
        {}
    ).get(
        "ROE",
        0
    )


    debt = financial.get(
        "재무지표",
        {}
    ).get(
        "부채비율",
        0
    )


    if roe >= 15:

        score += 10

        reasons.append(
            "높은 ROE"
        )


    if debt < 50:

        score += 5

        reasons.append(
            "재무 안정성"
        )



    score=max(
        0,
        min(
            score,
            100
        )
    )


    return {


        "기간":
        "6~18개월",


        "점수":
        score,


        "상승확률":
        score,


        "근거":
        reasons

    }
