def safe_float(value):

    try:
        if value is None:
            return 0

        return float(
            str(value)
            .replace(",", "")
            .replace("-", "0")
        )

    except:
        return 0



def get_account(data, name):

    result=[]

    for item in data.get("list", []):

        if item.get("account_nm") == name:

            result.append(item)

    return result



def analyze_financial(data):


    # 손익
    sales = get_account(
        data,
        "매출액"
    )

    operating = get_account(
        data,
        "영업이익"
    )

    net = get_account(
        data,
        "당기순이익(손실)"
    )


    # 재무상태
    assets = get_account(
        data,
        "자산총계"
    )

    debt = get_account(
        data,
        "부채총계"
    )

    equity = get_account(
        data,
        "자본총계"
    )


    # 최신값
    revenue = safe_float(
        sales[0]["thstrm_amount"]
        if sales else 0
    )

    op_profit = safe_float(
        operating[0]["thstrm_amount"]
        if operating else 0
    )


    net_profit = safe_float(
        net[0]["thstrm_amount"]
        if net else 0
    )


    total_asset = safe_float(
        assets[0]["thstrm_amount"]
        if assets else 0
    )


    total_debt = safe_float(
        debt[0]["thstrm_amount"]
        if debt else 0
    )


    total_equity = safe_float(
        equity[0]["thstrm_amount"]
        if equity else 0
    )


    # =====================
    # 핵심 재무 계산
    # =====================


    roe = 0

    if total_equity > 0:

        roe = (
            net_profit /
            total_equity
        ) * 100



    debt_ratio = 0

    if total_equity > 0:

        debt_ratio = (
            total_debt /
            total_equity
        ) * 100



    operating_margin = 0

    if revenue > 0:

        operating_margin = (
            op_profit /
            revenue
        ) * 100



    net_margin = 0

    if revenue > 0:

        net_margin = (
            net_profit /
            revenue
        ) * 100



    # =====================
    # 버핏형 점수
    # =====================


    score = 0


    if roe >= 15:
        score += 20


    if debt_ratio <= 50:
        score += 15


    if operating_margin >= 10:
        score += 15


    if net_margin >= 10:
        score += 10



    # 결과 반환

    return {


        "재무지표":{


            "ROE":round(roe,2),

            "부채비율":
            round(debt_ratio,2),


            "영업이익률":
            round(operating_margin,2),


            "순이익률":
            round(net_margin,2)

        },


        "버핏형점수":
        score,


        "투자해석":{


            "ROE":
            f"ROE {round(roe,2)}%입니다. 자기자본으로 얼마나 효율적으로 돈을 버는지 보는 지표입니다.",


            "부채":
            f"부채비율 {round(debt_ratio,2)}%입니다. 재무 안정성을 판단하는 기준입니다.",


            "수익성":
            f"영업이익률 {round(operating_margin,2)}%입니다. 판매 후 실제 돈을 얼마나 남기는지 보여줍니다."

        },


        "원본":{


            "매출":
            revenue,


            "영업이익":
            op_profit,


            "순이익":
            net_profit

        }

    }
