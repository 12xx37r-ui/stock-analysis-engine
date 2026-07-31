from predictors.score_config import SHORT_WEIGHT


def predict_short(financial, market):


    detail={}

    reasons=[]


    change=market.get(
        "등락률",
        0
    )

    volume=market.get(
        "거래량",
        0
    )


    tech=0


    if change>0:
        tech+=10
        reasons.append("상승 흐름")


    if volume>0:
        tech+=10
        reasons.append("거래량")


    detail["기술거래량"]=tech



    investor=market.get(
        "수급",
        {}
    )


    foreign=investor.get(
        "외국인순매수",
        0
    )


    org=investor.get(
        "기관순매수",
        0
    )


    flow=0


    if foreign>0:
        flow+=15


    if org>0:
        flow+=10


    detail["외국인기관수급"]=flow



    detail["파생프로그램"]=0

    detail["환율글로벌"]=0

    detail["뉴스공시"]=0



    score=50


    for key,value in detail.items():

        weight=SHORT_WEIGHT.get(
            key,
            0
        )


        if value>0:
            score+=weight


        elif value<0:
            score-=weight



    score=max(
        0,
        min(score,100)
    )


    return {

        "기간":"1~5일",

        "점수":score,

        "상승확률":score,

        "세부점수":detail,

        "근거":reasons

    }
