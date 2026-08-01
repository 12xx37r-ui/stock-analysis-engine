import json
from datetime import datetime


from collectors.company import (
    get_company_code
)

from collectors.dart import (
    get_financial
)

from collectors.kis import (
    get_stock_price,
    get_investor_trade
)


from analyzers.financial import (
    analyze_financial
)


from analyzers.value import (
    calculate_value
)


from predictors.predictor import (
    calculate_prediction
)



COMPANY = "삼성전자"

DART_CODE = "00126380"

STOCK_CODE = "005930"




def get_market_data(stock_code):


    price = get_stock_price(
        stock_code
    )


    investor = get_investor_trade(
        stock_code
    )


    return {

        "현재가":
        float(
            price.get(
                "stck_prpr",
                0
            )
        ),


        "전일대비":
        float(
            price.get(
                "prdy_vrss",
                0
            )
        ),


        "등락률":
        float(
            price.get(
                "prdy_ctrt",
                0
            )
        ),


        "거래량":
        int(
            price.get(
                "acml_vol",
                0
            )
        ),


        "시가":
        float(
            price.get(
                "stck_oprc",
                0
            )
        ),


        "고가":
        float(
            price.get(
                "stck_hgpr",
                0
            )
        ),


        "저가":
        float(
            price.get(
                "stck_lwpr",
                0
            )
        ),


        "PER":
        float(
            price.get(
                "per",
                0
            )
        ),


        "PBR":
        float(
            price.get(
                "pbr",
                0
            )
        ),


        "EPS":
        float(
            price.get(
                "eps",
                0
            )
        ),


        "BPS":
        float(
            price.get(
                "bps",
                0
            )
        ),


        "시가총액":
        float(
            price.get(
                "hts_avls",
                0
            )
        ),


        "수급":{

            "외국인순매수":
            investor.get(
                "외국인순매수",
                0
            ),

            "기관순매수":
            investor.get(
                "기관순매수",
                0
            ),

            "개인순매수":
            investor.get(
                "개인순매수",
                0
            )

        },


        "데이터출처":
        "한국투자증권 KIS"

    }




def main():


    print(
        "START ENGINE"
    )


    # DART

    dart_raw = get_financial(
        DART_CODE
    )


    financial = analyze_financial(
        dart_raw
    )



    # KIS

    market = get_market_data(
        STOCK_CODE
    )



    # 가치평가

    value = calculate_value(
        financial,
        market
    )



    # 예측

    prediction = calculate_prediction(
        financial,
        market,
        value
    )



    result = {


        "기업명":
        COMPANY,


        "DART기업코드":
        DART_CODE,


        "KIS종목코드":
        STOCK_CODE,


        "재무분석":
        financial,


        "시장정보":
        market,


        "가치평가":
        value,


        "주가예측":
        prediction,


        "생성시간":
        datetime.now().isoformat()

    }



    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        )
    )



    with open(
        "output.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2
        )



if __name__ == "__main__":

    main()
