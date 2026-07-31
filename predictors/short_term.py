from predictors.score_config import SHORT_WEIGHT



def predict_short(financial, market):


    score = 50

    reasons = []


    detail = {}



    # 1. 기술·거래량 20점

    tech_score = 0


    change = market.get(
        "등락률",
        0
    )


    volume = market.get(
        "거래량",
        0
    )


    if change > 0:

        tech_score += 10

        reasons.append(
            "단기 상승 흐름"
        )


    elif change < 0:

        tech_score -= 10

        reasons.append(
            "단기 하락 흐름"
        )


    if volume > 0:

        tech_score += 10

        reasons.append(
            "거래량 확인"
        )


    detail["기술거래량"] = tech_score



    # 2. 파생·프로그램 30점 (KIS 연결 예정)

    detail["파생프로그램"] = 0

    reasons.append(
        "선물·프로그램 데이터 연결 예정"
    )



    # 3. 외국인·기관 수급 25점 (KIS 연결 예정)

    detail["외국인기관수급"] = 0

    reasons.append(
        "외국인·기관 수급 데이터 연결 예정"
    )



    # 4. 환율·글로벌 15점

    detail["환율글로벌"] = 0

    reasons.append(
        "환율·미국시장 데이터 연결 예정"
    )



    # 5. 뉴스공시 10점

    detail["뉴스공시"] = 0

    reasons.append(
        "뉴스·공시 데이터 연결 예정"
    )



    # 가중치 적용

    total = 0


    for key, value in detail.items():

        weight = SHORT_WEIGHT.get(
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
        "1~5일",


        "점수":
        score,


        "상승확률":
        score,


        "세부점수":
        detail,


        "근거":
        reasons

    }
