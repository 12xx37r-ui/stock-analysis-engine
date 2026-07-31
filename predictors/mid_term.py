def predict_mid(financial, market):


    score = 50

    reasons = []


    # 1. 실적 모멘텀 25점

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

        score += 10

        reasons.append(
            "매출 성장 흐름"
        )


    if profit > 20:

        score += 15

        reasons.append(
            "영업이익 성장"
        )


    if profit < 0:

        score -= 15

        reasons.append(
            "영업이익 감소"
        )



    # 2. 가치평가 20점

    per = market.get(
        "PER",
        0
    )


    pbr = market.get(
        "PBR",
        0
    )


    if 0 < per < 15:

        score += 10

        reasons.append(
            "밸류 저평가"
        )


    elif per > 40:

        score -= 10

        reasons.append(
            "높은 밸류 부담"
        )


    if 0 < pbr < 1.5:

        score += 10

        reasons.append(
            "낮은 PBR"
        )



    # 3. 가격추세 10점

    change = market.get(
        "등락률",
        0
    )


    if change > 0:

        score += 10

        reasons.append(
            "가격 상승 모멘텀"
        )

    elif change < 0:

        score -= 10

        reasons.append(
            "가격 약세"
        )



    # 4. 수급/산업 데이터 자리 확보

    reasons.append(
        "외국인·기관 누적수급 연결 예정"
    )

    reasons.append(
        "산업 선행지표 연결 예정"
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
        "1~8주",


        "점수":
        score,


        "상승확률":
        score,


        "근거":
        reasons

    }
