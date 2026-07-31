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



def get_year_values(data, account):

    values={}

    items=get_account(
        data,
        account
    )


    for item in items:

        year=item.get(
            "bsns_year"
        )

        amount=safe_float(
            item.get(
                "thstrm_amount"
            )
        )

        if year:

            values[year]=amount


    return values



def growth_rate(old,new):

    if old <=0:

        return 0

    return (
        (new-old)
        /
        old
    )*100



def analyze_financial(data):


    # ======================
    # 계정 추출
    # ======================


    revenue=get_year_values(
        data,
        "매출액"
    )


    operating=get_year_values(
        data,
        "영업이익"
    )


    net_income=get_year_values(
        data,
        "당기순이익(손실)"
    )


    assets=get_account(
        data,
        "자산총계"
    )


    debt=get_account(
        data,
        "부채총계"
    )


    equity=get_account(
        data,
        "자본총계"
    )



    latest_revenue=max(
        revenue.values()
        if revenue
        else [0]
    )


    latest_operating=max(
        operating.values()
        if operating
        else [0]
    )


    latest_net=max(
        net_income.values()
        if net_income
        else [0]
    )



    total_debt=safe_float(
        debt[0]["thstrm_amount"]
        if debt else 0
    )


    total_equity=safe_float(
        equity[0]["thstrm_amount"]
        if equity else 0
    )



    # ======================
    # 재무 계산
    # ======================


    roe=0

    if total_equity:

        roe=(
            latest_net /
            total_equity
        )*100



    debt_ratio=0

    if total_equity:

        debt_ratio=(
            total_debt /
            total_equity
        )*100



    operating_margin=0

    if latest_revenue:

        operating_margin=(
            latest_operating /
            latest_revenue
        )*100



    net_margin=0

    if latest_revenue:

        net_margin=(
            latest_net /
            latest_revenue
        )*100



    years=sorted(
        revenue.keys()
    )


    revenue_growth=0
    operating_growth=0
    net_growth=0


    if len(years)>=2:

        old=years[0]
        new=years[-1]


        revenue_growth=growth_rate(
            revenue[old],
            revenue[new]
        )


        if old in operating and new in operating:

            operating_growth=growth_rate(
                operating[old],
                operating[new]
            )


        if old in net_income and new in net_income:

            net_growth=growth_rate(
                net_income[old],
                net_income[new]
            )



    # ======================
    # 버핏형 점수
    # ======================


    score=0


    good=[]

    warning=[]



    # ROE

    if roe>=15:

        score+=20

        good.append(
            "ROE가 15% 이상으로 자기자본 활용 능력이 우수합니다."
        )

    else:

        warning.append(
            f"ROE {roe:.2f}%로 버핏 기준 15%에는 부족합니다."
        )



    # 부채

    if debt_ratio<=50:

        score+=15

        good.append(
            "부채비율이 낮아 재무 안정성이 좋습니다."
        )

    else:

        warning.append(
            f"부채비율 {debt_ratio:.2f}%로 관리가 필요합니다."
        )



    # 성장

    if revenue_growth>10:

        score+=15

        good.append(
            "최근 매출 성장 흐름이 좋습니다."
        )

    else:

        warning.append(
            "매출 성장성이 강하지 않습니다."
        )



    if operating_growth>10:

        score+=15

        good.append(
            "영업이익 성장성이 좋습니다."
        )

    else:

        warning.append(
            "영업이익 성장 확인이 필요합니다."
        )



    if operating_margin>=10:

        score+=10

        good.append(
            "영업이익률이 우수해 돈을 남기는 힘이 있습니다."
        )

    else:

        warning.append(
            "영업이익률 개선이 필요합니다."
        )



    # 최종판정

    if score>=75:

        grade="버핏형 우수기업"

    elif score>=55:

        grade="관찰 가치 기업"

    else:

        grade="조건 부족"



    return {


        "재무지표":{

            "ROE":
            round(roe,2),

            "부채비율":
            round(debt_ratio,2),

            "영업이익률":
            round(operating_margin,2),

            "순이익률":
            round(net_margin,2)

        },


        "성장지표":{

            "매출성장률":
            round(revenue_growth,2),

            "영업이익성장률":
            round(operating_growth,2),

            "순이익성장률":
            round(net_growth,2)

        },


        "버핏평가":{

            "점수":
            score,

            "판정":
            grade,


            "좋은점":
            good,


            "주의점":
            warning

        },


        "투자자해설":{

            "ROE":
            "ROE는 회사가 주주의 돈을 이용해 얼마나 효율적으로 이익을 만드는지 보여주는 지표입니다.",


            "부채비율":
            "부채비율은 회사가 빚에 얼마나 의존하는지 보여줍니다. 낮을수록 재무 안전성이 높습니다.",


            "영업이익률":
            "영업이익률은 물건을 팔고 실제 얼마의 이익이 남는지 보여주는 기업 경쟁력 지표입니다."

        },


        "원본":{

            "매출":
            latest_revenue,

            "영업이익":
            latest_operating,

            "순이익":
            latest_net

        }

    }
