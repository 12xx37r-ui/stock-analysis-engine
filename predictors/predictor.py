def safe_float(v):
    try:
        return float(v)
    except:
        return 0


def calculate_prediction(financial, market, value):

    score_short = 50
    score_mid = 50
    score_long = 50


    reasons_short = []
    reasons_mid = []
    reasons_long = []


    price_change = safe_float(
        market.get("등락률", 0)
    )

    volume = safe_float(
        market.get("거래량", 0)
    )


    roe = safe_float(
        financial
        .get("재무지표", {})
        .get("ROE", 0)
    )


    growth = safe_float(
        financial
        .get("성장지표", {})
        .get("영업이익3년성장률", 0)
    )


    value_margin = safe_float(
        value.get("현재가대비", 0)
    )



    # 단기
    if price_change > 0:
        score_short += 15
        reasons_short.append(
            "상승 흐름"
        )

    if volume > 0:
        score_short += 10
        reasons_short.append(
            "거래량 존재"
        )


    score_short = min(
        max(score_short,0),
        100
    )



    # 중기

    if growth > 20:
        score_mid += 20
        reasons_mid.append(
            "영업이익 성장"
        )

    if roe >= 10:
        score_mid += 10
        reasons_mid.append(
            "ROE 양호"
        )

    score_mid = min(
        max(score_mid,0),
        100
    )



    # 장기

    if growth > 30:
        score_long += 20
        reasons_long.append(
            "성장성 우수"
        )


    if value_margin < -20:
        score_long += 10
        reasons_long.append(
            "가치평가 매력"
        )


    if value_margin > 20:
        score_long -= 20
        reasons_long.append(
            "고평가 부담"
        )


    score_long = min(
        max(score_long,0),
        100
    )



    return {

        "단기1~5일": {

            "기간":"1~5일",

            "점수":score_short,

            "상승확률":score_short,

            "근거":reasons_short

        },


        "중기1~8주": {

            "기간":"1~8주",

            "점수":score_mid,

            "상승확률":score_mid,

            "근거":reasons_mid

        },


        "장기6~18개월": {

            "기간":"6~18개월",

            "점수":score_long,

            "상승확률":score_long,

            "근거":reasons_long

        }

    }
