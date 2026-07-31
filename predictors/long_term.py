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


    # =====================
    # 1. 이익 방향 (30점)
    # =====================

    growth = financial.get(
        "성장지표",
        {}
    )


    profit_growth = growth.get(
        "영업이익3년성장률",
        0
    )


    if profit_growth > 50:

        detail["이익방향"] = 30

        reasons.append(
            "영업이익 성장성"
        )


    elif profit_growth > 10:

        detail["이익방향"] = 15

        reasons.append(
            "영업이익 개선 흐름"
        )


    score += detail["이익방향"]



    # =====================
    # 2. 산업 사이클 (25점)
    # =====================

    # 추후 산업 데이터 엔진 연결

    detail["산업사이클"] = 0



    # =====================
    # 3. 가치평가 (20점)
    # =====================

    judgment = valuation.get(
        "판단",
        ""
    )


    if judgment == "저평가":

        detail["가치평가"] = 20


    elif judgment == "적정":

        detail["가치평가"] = 10


    elif judgment == "고평가":

        detail["가치평가"] = -20

        reasons.append(
            "가치평가 부담"
        )


    score += detail["가치평가"]



    # =====================
    # 4. 경쟁력 (10점)
    # =====================

    # 향후 시장점유율·해자 데이터 연결

    detail["경쟁력"] = 0



    # =====================
    # 5. 현금흐름 (10점)
    # =====================

    # 향후 현금흐름표 연결

    detail["현금흐름"] = 0



    # =====================
    # 6. 주주환원 (5점)
    # =====================

    # 향후 배당·자사주 데이터 연결

    detail["주주환원"] = 0



    if score < 0:

        score = 0


    if score > 100:

        score = 100



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
