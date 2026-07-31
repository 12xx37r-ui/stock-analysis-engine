def calculate_value(financial, market):

    price = market.get(
        "현재가",
        0
    )


    eps = market.get(
        "EPS",
        0
    )


    bps = market.get(
        "BPS",
        0
    )


    per = market.get(
        "PER",
        0
    )


    pbr = market.get(
        "PBR",
        0
    )


    # PER 적정
    per_value = eps * 15


    # PBR 적정
    pbr_value = bps * 1.5


    # 재무 기반
    roe = financial.get(
        "재무지표",
        {}
    ).get(
        "ROE",
        0
    )


    if roe > 15:

        financial_value = price * 1.2

    elif roe > 10:

        financial_value = price

    else:

        financial_value = price * 0.8



    basic = (
        per_value +
        pbr_value +
        financial_value
    ) / 3



    margin = (
        (basic-price)
        /
        price
        *
        100
        if price > 0
        else 0
    )



    if margin > 20:

        judgment = "저평가"

    elif margin < -20:

        judgment = "고평가"

    else:

        judgment = "적정"



    return {

        "현재가": price,

        "실제PER": per,

        "실제PBR": pbr,

        "EPS": eps,

        "BPS": bps,

        "PER기준적정가": per_value,

        "PBR기준적정가": pbr_value,

        "재무적정가": financial_value,

        "기본적정가": basic,

        "현재가대비": margin,

        "판단": judgment

    }
