def safe(value):

    try:
        return float(value)
    except:
        return 0



def calculate_value(financial, price):


    current_price = safe(
        price.get("현재가")
    )


    per = safe(
        price.get("PER")
    )


    pbr = safe(
        price.get("PBR")
    )


    eps = safe(
        price.get("EPS")
    )


    bps = safe(
        price.get("BPS")
    )



    per_value = 0

    if eps > 0:

        per_value = eps * 15



    pbr_value = 0

    if bps > 0:

        pbr_value = bps * 1.5



    values=[]


    if per_value > 0:

        values.append(per_value)


    if pbr_value > 0:

        values.append(pbr_value)



    fair_value=0


    if values:

        fair_value=sum(values)/len(values)



    discount=0


    if current_price > 0:

        discount=(
            (fair_value-current_price)
            /
            current_price
        )*100



    return {


        "현재가":

        current_price,


        "PER기준가":

        round(per_value,2),


        "PBR기준가":

        round(pbr_value,2),


        "재무적정가":

        round(fair_value,2),


        "현재가대비":

        round(discount,2),


        "판단":

        "저평가"
        if discount > 10
        else
        "적정"
        if discount > -10
        else
        "고평가"

    }
