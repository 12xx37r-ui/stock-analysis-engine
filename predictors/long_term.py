def predict_long(financial, valuation):


    score=50

    reasons=[]


    roe = financial.get(
        "재무지표",
        {}
    ).get(
        "ROE",
        0
    )


    if roe >= 15:

        score += 15

        reasons.append(
            "높은 ROE"
        )


    gap = valuation.get(
        "현재가대비",
        0
    )


    if gap > 20:

        score += 20

        reasons.append(
            "저평가 구간"
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
