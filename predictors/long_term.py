from predictors.score_config import LONG_WEIGHT



def predict_long(financial, valuation):


    score = 50

    reasons = []

    detail = {}



    # 1. 이익 방향 30점

    profit_score = 0


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

        profit_score += 15

        reasons.append(
            "영업이익 성장"
        )


    if net_growth > 20:

        profit_score += 15

        reasons.append(
            "순이익 성장"
        )


    if profit_growth < 0:

        profit_score -= 15

        reasons.append(
            "이익 감소"
        )


    detail["이익방향"] = profit_score



    # 2. 산업 사이클 25점 (추후 연결)

    detail["산업사이클"] = 0

    reasons.append(
        "산업 사이클 데이터 연결 예정"
    )



    # 3. 가치평가 20점

    value_score = 0


    gap = valuation.get(
        "현재가대비",
        0
    )


    if gap > 20:

        value_score = 20

        reasons.append(
            "저평가 구간"
        )


    elif gap < -30:

        value_score = -20

        reasons.append(
            "고평가 부담"
        )


    detail["가치평가"] = value_score



    # 4. 경쟁력 10점 (추후 연결)

    detail["경쟁력"] = 0

    reasons.append(
        "시장점유율 데이터 연결 예정"
    )



    # 5. 현금흐름 10점 (추후 연결)

    detail["현금흐름"] = 0

    reasons.append(
        "현금흐름 데이터 연결 예정"
    )



    # 6. 주주환원 5점 (추후 연결)

    detail["주주환원"] = 0

    reasons.append(
        "배당·자사주 데이터 연결 예정"
    )



    total = 0


    for key, value in detail.items():

        weight = LONG_WEIGHT.get(
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
        "6~18개월",


        "점수":
        score,


        "상승확률":
        score,


        "세부점수":
        detail,


        "근거":
        reasons

    }
