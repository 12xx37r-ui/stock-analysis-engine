def predict_mid(financial, market):


    score=50

    reasons=[]


    growth = financial.get(
        "성장지표",
        {}
    )


    sales = growth.get(
        "매출3년성장률",
        0
    )


    if sales > 10:

        score += 10

        reasons.append(
            "매출 성장"
        )


    profit = growth.get(
        "영업이익3년성장률",
        0
    )


    if profit > 10:

        score += 10

        reasons.append(
            "영업이익 성장"
        )


    return {

        "기간":
        "1~8주",

        "점수":
        score,

        "상승확률":
        score,

        "근거":
        reasons

    }
