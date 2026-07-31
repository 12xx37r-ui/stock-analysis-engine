def predict_long(financial, valuation):

    score = 0

    detail = {

        "이익방향": 0,
        "산업사이클": 0,
        "가치평가": 0,
        "경쟁력": 0,
        "현금흐름": 0,
        "주주환원": 0

    }


    reasons = []


    growth = financial.get(
        "성장지표",
        {}
    )


    profit_growth = growth.get(
        "영업이익3년성장률",
        0
    )


    # 이익 방향 30

    if profit_growth > 50:

        detail["이익방향"] = 30

        reasons.append(
            "영업이익 성장성"
        )


    score += detail["이익방향"]



    # 산업 사이클
    # 향후 산업 데이터 연결

    detail["산업사이클"] = 0



    # 가치평가 20

    judgment = valuation.get(
        "판단",
        ""
    )


    if judgment == "저평가":

        detail["가치평가"] = 20

    elif judgment == "적정":

        detail["가치평가"] = 10

    else:

        detail["가치평가"] = -20

        reasons.append(
            "가치평가 부담"
        )


    score += detail["가치평가"]



    # 경쟁력

    detail["경쟁력"] = 0



    # 현금흐름

    detail["현금흐름"] = 0



    # 주주환원

    detail["주주환원"] = 0



    if score < 0:
        score = 0

    if score > 100:
        score = 100


    return {

        "기간": "6~18개월",

        "점수": score,

        "상승확률": score,

        "세부점수": detail,

        "근거": reasons

    }
