import json

from collectors.dart import get_financial_data
from collectors.market import get_market_data

from analyzers.financial import analyze_financial
from analyzers.valuation import calculate_value

from predictors.short_term import predict_short
from predictors.mid_term import predict_mid
from predictors.long_term import predict_long



def run(company, code):


    financial_raw = get_financial_data(
        code
    )


    financial = analyze_financial(
        financial_raw
    )


    market = get_market_data(
        code
    )


    valuation = calculate_value(
        financial,
        market
    )


    short = predict_short(
        financial,
        market
    )


    mid = predict_mid(
        financial,
        market
    )


    long = predict_long(
        financial,
        valuation
    )



    result = {


        "기업명":
        company,


        "기업코드":
        code,


        "재무분석":
        financial,


        "시장정보":
        market,


        "가치평가":
        valuation,


        "주가예측":

        {

            "단기1~5일":
            short,


            "중기1~8주":
            mid,


            "장기6~18개월":
            long

        }

    }


    return result




if __name__ == "__main__":


    result = run(

        "삼성전자",

        "005930"

    )


    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        )
    )
