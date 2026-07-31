from predictors.score_config import MID_WEIGHT



def predict_mid(financial, market):


    score = 50

    reasons = []

    detail = {}



    # 1. 실적 25점

    result_score = 0


    growth = financial.get(
        "성장지표",
        {}
    )


    sales = growth.get(
        "매출3년성장률",
        0
    )


    profit = growth.get(
        "영업이익3년성장률",
        0
    )


    if sales > 10:

        result_score += 10

        reasons.append(
            "매출 성장"
        )


    if profit > 20:

        result_score += 15

        reasons.append(
            "영업이익 성장"
        )


    elif profit < 0:

        result_score -= 15

        reasons.append(
            "영업이익 감소"
        )


    detail["실적"] = result_score



    # 2. 산업 선행지표 25점 (추후 연결)

    detail["산업선행"] = 0

    reasons.append(
        "산업 선행지표 연결 예정"
    )



    # 3. 누적수급 15점 (추후 KIS 연결)

    detail["누적수급"] = 0

    reasons.append(
        "외국인·기관 누적수급 연결 예정"
    )



    # 4. 금리·환율 15점

    detail["금리환율"] = 0

    reasons.append(
        "금리·환율 데이터 연결 예정"
    )



    # 5. 가격추세 10점

    trend_score = 0


    change = market.get(
        "등락률",
        0
    )


    if change > 0:

        trend_score = 10

        reasons.append(
            "가격 상승 추세"
        )


    elif change < 0:

        trend_score = -10

        reasons.append(
            "가격 약세"
        )


    detail["가격추세"] = trend_score



    # 6. 뉴스공시 10점

    detail["뉴스공시"] = 0

    reasons.append(
        "뉴스·공시 연결 예정"
    )



    total = 0


    for key, value in detail.items():

        weight = MID_WEIGHT.get(
            key,
            0
        )


        if value > 0:

            total += weight


        elif value < 0:

            total -= weight



    score = 50 + total



    score = max(
        0,
        min(
            score,
            100
        )
    )



    return {

        "기간":
        "1~8주",


        "점수":
        score,


        "상승확률":
        score,


        "세부점수":
        detail,


        "근거":
        reasons

    }
