import json
import os
from datetime import datetime


from collectors.dart import get_financial
from collectors.market import get_market_data


from analyzers.financial import analyze_financial
from analyzers.valuation import calculate_value



STOCK_NAME = "삼성전자"
STOCK_CODE = "005930"
DART_CODE = "00126380"




def save_output(data):

    os.makedirs(
        "output",
        exist_ok=True
    )


    with open(
        "output/result.json",
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )




def main():


    print("START ENGINE")



    result = {

        "기업명": STOCK_NAME,

        "DART기업코드": DART_CODE,

        "KIS종목코드": STOCK_CODE

    }



    # =====================
    # DART 재무
    # =====================

    try:

        dart_raw = get_financial(
            DART_CODE
        )


        financial = analyze_financial(
            dart_raw
        )


    except Exception as e:

        financial = {

            "error": str(e)

        }



    result["재무분석"] = financial





    # =====================
    # KIS 시장 데이터
    # =====================

    try:

        market = get_market_data(
            STOCK_CODE
        )


    except Exception as e:

        market = {

            "error": str(e)

        }



    result["시장정보"] = market





    # =====================
    # 가치평가
    # =====================

    try:

        value = calculate_value(

            financial,

            market

        )


    except Exception as e:

        value = {

            "error": str(e)

        }



    result["가치평가"] = value





    result["생성시간"] = (
        datetime.now()
        .isoformat()
    )



    save_output(
        result
    )



    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2
        )
    )





if __name__ == "__main__":

    main()
