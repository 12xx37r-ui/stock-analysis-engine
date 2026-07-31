def predict_short(financial, market):

    score = 0

    detail = {
        "기술거래량": 0,
        "외국인기관수급": 0,
        "파생프로그램": 0,
        "환율글로벌": 0,
        "뉴스공시": 0
    }

    reasons = []


    # =====================
    # 1. 기술·거래량 (20점)
    # =====================

    change = float(
        market.get("등락률", 0)
    )

    volume = int(
        market.get("거래량", 0)
    )


    if change > 0:
        detail["기술거래량"] += 10
        reasons.append("상승 흐름")


    if volume > 1000000:
        detail["기술거래량"] += 10
        reasons.append("거래량 확인")


    score += detail["기술거래량"]



    # =====================
    # 2. 외국인·기관 수급 (25점)
    # =====================

    investor = market.get(
        "수급",
        {}
    )


    output = []


    # KIS 실제 구조 대응
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


    foreign = 0
    institution = 0


    if len(output) > 0:

        today = output[0]

        foreign = float(
            today.get(
                "frgn_ntby_qty",
                0
            )
        )

        institution = float(
            today.get(
                "orgn_ntby_qty",
                0
            )
        )


    # 외국인
    if foreign > 0:

        detail["외국인기관수급"] += 15
        reasons.append(
            "외국인 순매수"
        )

    elif foreign < 0:

        detail["외국인기관수급"] -= 10



    # 기관
    if institution > 0:

        detail["외국인기관수급"] += 10
        reasons.append(
            "기관 순매수"
        )

    elif institution < 0:

        detail["외국인기관수급"] -= 5



    score += detail["외국인기관수급"]



    # =====================
    # 3~5 추후 연결
    # =====================

    detail["파생프로그램"] = 0
    detail["환율글로벌"] = 0
    detail["뉴스공시"] = 0



    if score < 0:
        score = 0

    if score > 100:
        score = 100



    return {

        "기간": "1~5일",

        "점수": score,

        "상승확률": score,

        "세부점수": detail,

        "근거": reasons

    }
