import json
import os

from collectors.dart import get_financial
from collectors.market import get_market_data

from analyzers.financial import analyze_financial
from analyzers.valuation import calculate_value

from predictors.short_term import predict_short
from predictors.mid_term import predict_mid
from predictors.long_term import predict_long



def run(company, dart_code, kis_code):


    financial_raw = get_financial(
        dart_code
    )


    financial = analyze_financial(
        financial_raw
    )


    market = get_market_data(
        kis_code
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


    return {


        "기업명":
        company,


        "DART기업코드":
        dart_code,


        "KIS종목코드":
        kis_code,


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



if __name__ == "__main__":


    result = run(

        "삼성전자",

        "00126380",

        "005930"

    )


    os.makedirs(
        "output",
        exist_ok=True
    )


    with open(

        "output/samsung.json",

        "w",

        encoding="utf-8"

    ) as f:


        json.dump(

            result,

            f,

            ensure_ascii=False,

            indent=2

        )


    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        )
    )
