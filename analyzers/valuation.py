def safe(value):

    try:
        return float(value)
    except:
        return 0



def calculate_value(financial, market):


    current_price = safe(
        market.get("현재가")
    )


    net_income = safe(
        financial["원본"].get("순이익")
    )


    revenue = safe(
        financial["원본"].get("매출")
    )


    equity = 0


    debt_ratio = safe(
        financial["재무지표"].get("부채비율")
    )


    # 삼성전자 기준 발행주식수
    # 이후 DART 주식수 API 연결 예정

    shares = 5969782550



    # EPS 계산

    eps = 0

    if shares > 0:

        eps = net_income / shares



    # PER 계산

    per = 0

    if eps > 0 and current_price > 0:

        per = current_price / eps



    # PER 적정가

    per_value = 0

    if eps > 0:

        per_value = eps * 15



    # 성장 반영 가치

    growth = financial["성장지표"].get(
        "영업이익3년성장률",
        0
    )


    growth_value = 0


    if eps > 0:

        if growth > 100:

            growth_value = eps * 20

        else:

            growth_value = eps * 15



    values=[]


    if per_value > 0:

        values.append(per_value)


    if growth_value > 0:

        values.append(growth_value)



    fair_value = 0


    if values:

        fair_value=sum(values)/len(values)



    discount=0


    if current_price > 0 and fair_value > 0:

        discount = (
            (fair_value-current_price)
            /
            current_price
        )*100



    return {


        "현재가":
        round(current_price,2),


        "EPS":
        round(eps,2),


        "PER":
        round(per,2),


        "PER기준적정가":
        round(per_value,2),


        "성장반영적정가":
        round(growth_value,2),


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
