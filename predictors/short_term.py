def predict_short(financial, market):


    score = 50

    reasons = []


    # 1. 기술/거래량 20점

    change = market.get(
        "등락률",
        0
    )

    volume = market.get(
        "거래량",
        0
    )


    if change > 0:

        score += 10

        reasons.append(
            "주가 상승 흐름"
        )

    elif change < 0:

        score -= 10

        reasons.append(
            "주가 하락 흐름"
        )


    if volume > 0:

        score += 10

        reasons.append(
            "거래량 확인"
        )



    # 2. 재무 모멘텀 20점

    growth = financial.get(
        "성장지표",
        {}
    )


    profit_growth = growth.get(
        "영업이익3년성장률",
        0
    )


    if profit_growth > 20:

        score += 10

        reasons.append(
            "영업이익 성장"
        )


    elif profit_growth < 0:

        score -= 10

        reasons.append(
            "영업이익 감소"
        )



    # 3. 밸류 부담 20점

    per = market.get(
        "PER",
        0
    )


    if per > 30:

        score -= 10

        reasons.append(
            "높은 PER 부담"
        )


    elif per > 0 and per < 15:

        score += 10

        reasons.append(
            "낮은 PER"
        )



    # 4. 재무 안정성 20점

    roe = financial.get(
        "재무지표",
        {}
    ).get(
        "ROE",
        0
    )


    debt = financial.get(
        "재무지표",
        {}
    ).get(
        "부채비율",
        0
    )


    if roe >= 15:

        score += 10

        reasons.append(
            "높은 ROE"
        )


    if debt < 50:

        score += 10

        reasons.append(
            "낮은 부채"
        )



    # 5. 수급/뉴스 자리 확보 (KIS 연결 예정)

    reasons.append(
        "외국인·기관·프로그램 데이터 연결 예정"
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
        "1~5일",


        "점수":
        score,


        "상승확률":
        score,


        "근거":
        reasons

    }
