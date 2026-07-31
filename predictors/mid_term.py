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


    # 실적 (25)
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



    # 산업선행 (25)
    # 향후 산업 데이터 연결 자리

    detail["산업선행"] = 0



    # 누적수급 (15)

    investor = market.get(
        "수급",
        {}
    )

    output = []

    if isinstance(investor, dict):

        raw = investor.get(
            "원본응답",
            {}
        )

        if isinstance(raw, dict):

            output = raw.get(
                "output2",
                []
            )


    if output:

        latest = output[0]

        foreign = float(
            latest.get(
                "frgn_ntby_qty",
                0
            )
        )

        institution = float(
            latest.get(
                "orgn_ntby_qty",
                0
            )
        )


        if foreign > 0:
            detail["누적수급"] += 8

        if institution > 0:
            detail["누적수급"] += 7


        if detail["누적수급"] > 0:
            reasons.append(
                "외국인·기관 수급"
            )


    score += detail["누적수급"]



    # 금리환율
    detail["금리환율"] = 0



    # 가격추세 (10)

    change = market.get(
        "등락률",
        0
    )

    if change > 0:
        detail["가격추세"] = 10
        reasons.append(
            "가격 상승 추세"
        )


    score += detail["가격추세"]



    # 뉴스공시
    detail["뉴스공시"] = 0



    if score > 100:
        score = 100


    return {

        "기간": "1~8주",

        "점수": score,

        "상승확률": score,

        "세부점수": detail,

        "근거": reasons

    }
