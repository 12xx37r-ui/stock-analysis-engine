def num(value):

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



def find_account(data, name):

    for item in data.get("list", []):

        if item.get("account_nm") == name:

            return item

    return None



def growth(current, previous):

    if previous <= 0:
        return 0

    return ((current - previous) / previous) * 100



def analyze_financial(data):


    # -----------------
    # 계정 가져오기
    # -----------------

    revenue=find_account(
        data,
        "매출액"
    )

    operating=find_account(
        data,
        "영업이익"
    )

    net=find_account(
        data,
        "당기순이익(손실)"
    )

    equity=find_account(
        data,
        "자본총계"
    )

    debt=find_account(
        data,
        "부채총계"
    )



    # -----------------
    # 금액
    # -----------------

    sales_now=num(
        revenue.get("thstrm_amount")
        if revenue else 0
    )

    sales_prev=num(
        revenue.get("frmtrm_amount")
        if revenue else 0
    )


    sales_old=num(
        revenue.get("bfefrmtrm_amount")
        if revenue else 0
    )



    op_now=num(
        operating.get("thstrm_amount")
        if operating else 0
    )

    op_prev=num(
        operating.get("frmtrm_amount")
        if operating else 0
    )

    op_old=num(
        operating.get("bfefrmtrm_amount")
        if operating else 0
    )



    net_now=num(
        net.get("thstrm_amount")
        if net else 0
    )

    net_prev=num(
        net.get("frmtrm_amount")
        if net else 0
    )

    net_old=num(
        net.get("bfefrmtrm_amount")
        if net else 0
    )



    equity_now=num(
        equity.get("thstrm_amount")
        if equity else 0
    )

    debt_now=num(
        debt.get("thstrm_amount")
        if debt else 0
    )



    # -----------------
    # 지표 계산
    # -----------------

    roe=0

    if equity_now:

        roe=(net_now/equity_now)*100



    debt_ratio=0

    if equity_now:

        debt_ratio=(debt_now/equity_now)*100



    op_margin=0

    if sales_now:

        op_margin=(op_now/sales_now)*100



    net_margin=0

    if sales_now:

        net_margin=(net_now/sales_now)*100



    # 성장률

    sales_growth=growth(
        sales_now,
        sales_old
    )


    op_growth=growth(
        op_now,
        op_old
    )


    net_growth=growth(
        net_now,
        net_old
    )



    # -----------------
    # 버핏 평가
    # -----------------

    score=0

    good=[]

    bad=[]



    # 수익성

    if roe>=15:

        score+=20

        good.append(
            "ROE가 높아 자기자본 활용 능력이 우수합니다."
        )

    elif roe>=10:

        score+=10

        good.append(
            "ROE는 양호하지만 최고 수준은 아닙니다."
        )

    else:

        bad.append(
            f"ROE {roe:.2f}%로 수익성 개선이 필요합니다."
        )



    # 재무안정성

    if debt_ratio<=50:

        score+=20

        good.append(
            "부채비율이 낮아 재무 안전성이 좋습니다."
        )

    else:

        bad.append(
            "부채 부담이 높은 편입니다."
        )



    # 성장

    if sales_growth>10:

        score+=15

        good.append(
            "최근 매출 성장 흐름이 좋습니다."
        )

    else:

        bad.append(
            "매출 성장성이 강한지 확인이 필요합니다."
        )



    if op_growth>10:

        score+=20

        good.append(
            "영업이익 성장성이 우수합니다."
        )

    else:

        bad.append(
            "영업이익 성장성이 약합니다."
        )



    # 마진

    if op_margin>=10:

        score+=15

        good.append(
            "영업이익률이 좋아 높은 수익성을 보여줍니다."
        )



    # 등급

    if score>=75:

        grade="버핏형 우수기업"

    elif score>=55:

        grade="투자검토 가능"

    else:

        grade="조건 미달"



    return {


        "재무지표":{

            "ROE":round(roe,2),

            "부채비율":round(debt_ratio,2),

            "영업이익률":round(op_margin,2),

            "순이익률":round(net_margin,2)

        },


        "성장지표":{

            "매출3년성장률":round(sales_growth,2),

            "영업이익3년성장률":round(op_growth,2),

            "순이익3년성장률":round(net_growth,2)

        },


        "버핏평가":{

            "점수":score,

            "판정":grade,

            "좋은점":good,

            "주의점":bad

        },


        "투자자해설":{

            "ROE":
            "ROE는 회사가 주주의 돈을 이용해 얼마나 많은 이익을 만드는지 나타냅니다. 높을수록 자본 활용 능력이 좋습니다.",


            "부채비율":
            "부채비율은 회사가 가진 자기 돈 대비 빚의 규모입니다. 낮을수록 경기 침체에도 버틸 힘이 있습니다.",


            "영업이익률":
            "영업이익률은 물건을 팔고 비용을 제외한 뒤 얼마가 남는지를 보여주는 기업 경쟁력 지표입니다."

        },


        "원본":{

            "매출":sales_now,

            "영업이익":op_now,

            "순이익":net_now

        }

    }
