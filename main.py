import json
import os
from datetime import datetime


from collectors.company import get_company_code
from collectors.dart import get_financial_data
from collectors.market import get_market_data


from analyzers.buffett import analyze_buffett
from analyzers.value import analyze_value


from predictors.stock_predictor import predict_stock



# =========================
# 기본 종목
# =========================

STOCK_NAME = "삼성전자"
STOCK_CODE = "005930"
DART_CODE = "00126380"



# =========================
# JSON 저장
# =========================

def save_output(data):

    os.makedirs(
        "output",
        exist_ok=True
    )


    filename = (
        "output/"
        + STOCK_CODE
        + "_analysis.json"
    )


    with open(
        filename,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )



# =========================
# Main
# =========================

def main():


    print(
        "START ENGINE"
    )


    result = {


        "기업명":
        STOCK_NAME,


        "DART기업코드":
        DART_CODE,


        "KIS종목코드":
        STOCK_CODE

    }



    # -------------------------
    # DART 재무
    # -------------------------

    try:

        finance = get_financial_data(
            DART_CODE
        )


    except Exception as e:

        finance = {

            "error":
            str(e)

        }



    result["재무분석"] = finance



    # -------------------------
    # 버핏 분석
    # -------------------------

    try:

        result["버핏평가"] = analyze_buffett(
            finance
        )


    except Exception as e:

        result["버핏평가"] = {

            "error":
            str(e)

        }




    # -------------------------
    # KIS 시장 데이터
    # -------------------------

    try:

        market = get_market_data(
            STOCK_CODE
        )


    except Exception as e:

        market = {

            "error":
            str(e)

        }



    result["시장정보"] = market




    # -------------------------
    # 가치평가
    # -------------------------

    try:

        result["가치평가"] = analyze_value(
            market,
            finance
        )


    except Exception as e:

        result["가치평가"] = {

            "error":
            str(e)

        }




    # -------------------------
    # 주가 예측
    # -------------------------

    try:

        result["주가예측"] = predict_stock(
            market,
            finance
        )


    except Exception as e:

        result["주가예측"] = {

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
