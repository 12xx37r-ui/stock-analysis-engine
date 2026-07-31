import json
import os
from datetime import datetime


from collectors.dart import get_financial
from collectors.market import get_market_data

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




def parse_financial(raw):

    return {

        "원본": raw,

        "재무지표": {

            "ROE":0,
            "부채비율":0,
            "영업이익률":0,
            "순이익률":0

        },

        "성장지표": {

            "매출3년성장률":0,
            "영업이익3년성장률":0,
            "순이익3년성장률":0

        }

    }




def main():


    result = {

        "기업명": STOCK_NAME,

        "DART기업코드": DART_CODE,

        "KIS종목코드": STOCK_CODE

    }



    # =====================
    # DART
    # =====================

    try:

        dart_raw = get_financial(
            DART_CODE
        )


        financial = parse_financial(
            dart_raw
        )


    except Exception as e:

        financial = {
            "error":str(e)
        }



    result["재무분석"] = financial




    # =====================
    # KIS
    # =====================

    try:

        market = get_market_data(
            STOCK_CODE
        )


    except Exception as e:

        market = {
            "error":str(e)
        }



    result["시장정보"] = market




    # =====================
    # 가치평가
    # =====================

    try:

        result["가치평가"] = calculate_value(

            financial,

            market

        )


    except Exception as e:

        result["가치평가"] = {

            "error":
            str(e)

        }



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
