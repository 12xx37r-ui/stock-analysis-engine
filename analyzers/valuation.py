def calculate_value(financial, market):

    price = market.get("현재가", 0)

    eps = market.get("EPS", 0)

    bps = market.get("BPS", 0)

    per = market.get("PER", 0)

    pbr = market.get("PBR", 0)


    # 보수 가치
    conservative = 0

    if eps > 0:
        conservative += eps * 12

    if bps > 0:
        conservative += bps * 1.0


    if conservative > 0:
        conservative /= 2



    # 기본 가치
    normal = 0

    if eps > 0:
        normal += eps * 15

    if bps > 0:
        normal += bps * 1.5


    if normal > 0:
        normal /= 2



    # 성장 가치
    roe = financial.get(
        "재무지표",
        {}
    ).get(
        "ROE",
        0
    )


    growth = normal


    if roe >= 15:

        growth *= 1.3

    elif roe >= 10:

        growth *= 1.15



    gap = 0

    if price > 0 and growth > 0:

        gap = (
            (growth-price)
            /
            price
        ) * 100



    if gap >= 30:

        result="강한 저평가"

    elif gap >= 10:

        result="저평가"

    elif gap <= -30:

        result="고평가"

    else:

        result="적정"



    return {

        "현재가": price,

        "실제PER": per,

        "실제PBR": pbr,

        "EPS": eps,

        "BPS": bps,

        "보수적적정가":
        round(conservative,2),

        "기본적정가":
        round(normal,2),

        "성장반영적정가":
        round(growth,2),

        "현재가대비":
        round(gap,2),

        "판단":
        result

    }
