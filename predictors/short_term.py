def predict_short(financial, market):

    score = 50

    reasons=[]


    change = market.get(
        "등락률",
        0
    )


    volume = market.get(
        "거래량",
        0
    )


    if change > 0:

        score += 5
        reasons.append(
            "당일 상승 흐름"
        )

    elif change < 0:

        score -= 5
        reasons.append(
            "당일 하락 흐름"
        )


    if volume > 0:

        score += 5
        reasons.append(
            "거래량 존재"
        )


    return {

        "기간":
        "1~5일",

        "점수":
        score,

        "상승확률":
        score,

        "근거":
        reasons

    }
