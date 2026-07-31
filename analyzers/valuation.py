def calculate_value(financial, market):


    current_price = market.get(
        "현재가",
        0
    )


    real_per = market.get(
        "PER",
        0
    )


    real_pbr = market.get(
        "PBR",
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



    # 버핏형 보수 가치평가

    per_target = 15

    pbr_target = 1.5



    per_value = 0

    if eps > 0:

        per_value = eps * per_target



    pbr_value = 0

    if bps > 0:

        pbr_value = bps * pbr_target



    values=[]


    if per_value > 0:

        values.append(
            per_value
        )


    if pbr_value > 0:

        values.append(
            pbr_value
        )



    fair_value = 0


    if values:

        fair_value = sum(values)/len(values)



    gap = 0


    if current_price > 0 and fair_value > 0:

        gap = (
            (fair_value-current_price)
            /
            current_price
        )*100



    if gap >= 20:

        judgment="저평가"


    elif gap <= -20:

        judgment="고평가"


    else:

        judgment="적정"



    return {


        "현재가":

        current_price,


        "실제PER":

        real_per,


        "실제PBR":

        real_pbr,


        "EPS":

        eps,


        "BPS":

        bps,


        "PER기준적정가":

        round(per_value,2),


        "PBR기준적정가":

        round(pbr_value,2),


        "재무적정가":

        round(fair_value,2),


        "현재가대비":

        round(gap,2),


        "판단":

        judgment

    }
