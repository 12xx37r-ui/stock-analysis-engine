def predict_stock(market, financial, value):


    price = market.get(
        "현재가",
        0
    )


    volume = market.get(
        "거래량",
        0
    )


    roe = financial.get(
        "재무지표",
        {}
    ).get(
        "ROE",
        0
    )


    op_growth = financial.get(
        "성장지표",
        {}
    ).get(
        "영업이익3년성장률",
        0
    )


    margin = value.get(
        "현재가대비",
        0
    )



    # =================
    # 단기 1~5일
    # =================

    short_score = 50


    if volume > 0:
        short_score += 10


    if market.get(
        "등락률",
        0
    ) > 0:

        short_score += 10



    short_score = min(
        short_score,
        100
    )




    # =================
    # 중기 1~8주
    # =================

    mid_score = 50


    if op_growth > 20:

        mid_score += 20


    if roe > 10:

        mid_score += 10



    mid_score = min(
        mid_score,
        100
    )





    # =================
    # 장기 6~18개월
    # =================

    long_score = 50


    if op_growth > 30:

        long_score += 20


    if margin > 20:

        long_score += 15


    elif margin < -20:

        long_score -= 20



    if long_score < 0:

        long_score = 0


    if long_score > 100:

        long_score = 100





    return {


        "단기1~5일":{

            "기간":
            "1~5일",

            "점수":
            short_score,

            "상승확률":
            short_score,

            "근거":[

                "거래량",

                "가격 흐름"

            ]

        },



        "중기1~8주":{

            "기간":
            "1~8주",

            "점수":
            mid_score,

            "상승확률":
            mid_score,

            "근거":[

                "실적 성장",

                "재무 안정성"

            ]

        },



        "장기6~18개월":{

            "기간":
            "6~18개월",

            "점수":
            long_score,

            "상승확률":
            long_score,

            "근거":[

                "영업이익 성장",

                "가치평가"

            ]

        }


    }
