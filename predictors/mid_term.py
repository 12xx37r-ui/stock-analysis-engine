from predictors.score_config import MID_WEIGHT


def predict_mid(financial, market):


    detail={}
    reasons=[]


    growth=financial.get(
        "성장지표",
        {}
    )


    score=50


    result=0


    if growth.get("매출3년성장률",0)>10:
        result+=10


    if growth.get("영업이익3년성장률",0)>20:
        result+=15


    detail["실적"]=result



    investor=market.get(
        "수급",
        {}
    )


    flow=0


    if investor.get("외국인순매수",0)>0:
        flow+=8


    if investor.get("기관순매수",0)>0:
        flow+=7


    detail["누적수급"]=flow



    detail["산업선행"]=0

    detail["금리환율"]=0


    if market.get("등락률",0)>0:

        detail["가격추세"]=10

    else:

        detail["가격추세"]=0



    detail["뉴스공시"]=0



    for key,value in detail.items():

        weight=MID_WEIGHT.get(
            key,
            0
        )


        if value>0:
            score+=weight



    score=max(
        0,
        min(score,100)
    )


    return {

        "기간":"1~8주",

        "점수":score,

        "상승확률":score,

        "세부점수":detail,

        "근거":reasons

    }
