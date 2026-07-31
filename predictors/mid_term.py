def predict_mid(financial, market):

    score = 0

    detail = {
        "실적": 0,
        "산업선행": 0,
        "누적수급": 0,
        "금리환율": 0,
        "가격추세": 0,
        "뉴스공시": 0
    }

    reasons = []


    # =====================
    # 1. 실적 (25점)
    # =====================

    growth = financial.get(
        "성장지표",
        {}
    )


    sales_growth = growth.get(
        "매출3년성장률",
        0
    )


    profit_growth = growth.get(
        "영업이익3년성장률",
        0
    )


    if sales_growth > 10:

        detail["실적"] += 10


    if profit_growth > 30:

        detail["실적"] += 15

        reasons.append(
            "영업이익 성장"
        )


    score += detail["실적"]



    # =====================
    # 2. 산업선행 (25점)
    # =====================

    # 추후 산업 데이터 연결

    detail["산업선행"] = 0



    # =====================
    # 3. 누적수급 (15점)
    # =====================

    investor = market.get(
        "수급",
        {}
    )


    foreign = float(
        investor.get(
            "외국인순매수",
            0
        )
    )


    institution = float(
        investor.get(
            "기관순매수",
            0
        )
    )


    if foreign > 0:

        detail["누적수급"] += 8


    elif foreign < 0:

        detail["누적수급"] -= 5



    if institution > 0:

        detail["누적수급"] += 7


    elif institution < 0:

        detail["누적수급"] -= 5



    if detail["누적수급"] > 0:

        reasons.append(
            "외국인·기관 수급"
        )



    score += detail["누적수급"]



    # =====================
    # 4. 금리·환율 (15점)
    # =====================

    # 추후 거시환경 엔진 연결

    detail["금리환율"] = 0



    # =====================
    # 5. 가격추세 (10점)
    # =====================

    change = float(
        market.get(
            "등락률",
            0
        )
    )


    if change > 0:

        detail["가격추세"] = 10

        reasons.append(
            "가격 상승 추세"
        )



    score += detail["가격추세"]



    # =====================
    # 6. 뉴스·공시 (10점)
    # =====================

    # 추후 뉴스 NLP 연결

    detail["뉴스공시"] = 0



    if score < 0:

        score = 0


    if score > 100:

        score = 100



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
