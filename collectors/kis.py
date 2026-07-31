import requests
import time
import json
import os
from datetime import datetime

from config import (
    KIS_APP_KEY,
    KIS_APP_SECRET,
    KIS_BASE_URL
)


ACCESS_TOKEN = None


# =========================
# Token
# =========================

def get_access_token():

    global ACCESS_TOKEN


    if ACCESS_TOKEN:

        return ACCESS_TOKEN



    url = (
        KIS_BASE_URL
        +
        "/oauth2/tokenP"
    )


    body = {

        "grant_type":
        "client_credentials",

        "appkey":
        KIS_APP_KEY,

        "appsecret":
        KIS_APP_SECRET

    }


    try:

        response = requests.post(

            url,

            json=body,

            timeout=10

        )


        data = response.json()



        token = data.get(
            "access_token"
        )


        if token:

            ACCESS_TOKEN = token

            print(
                "TOKEN CREATED: True"
            )

            return token



        print(
            "TOKEN ERROR:",
            data
        )


    except Exception as e:

        print(
            "TOKEN REQUEST ERROR:",
            e
        )


    return None





def clear_token():

    global ACCESS_TOKEN

    ACCESS_TOKEN = None





# =========================
# Request
# =========================

def kis_request(
    tr_id,
    path,
    params
):


    for retry in range(3):


        token = get_access_token()


        if not token:

            clear_token()

            time.sleep(2)

            continue



        headers = {


            "authorization":
            "Bearer " + token,


            "appkey":
            KIS_APP_KEY,


            "appsecret":
            KIS_APP_SECRET,


            "tr_id":
            tr_id,


            "custtype":
            "P"

        }



        try:


            time.sleep(1)



            response = requests.get(

                KIS_BASE_URL + path,

                headers=headers,

                params=params,

                timeout=10

            )



            data = response.json()



            msg = str(
                data.get(
                    "msg1",
                    ""
                )
            )



            # 호출 제한

            if (

                "EGW00201" in msg

                or

                "초당 거래건수" in msg

            ):


                print(
                    "KIS RATE LIMIT WAIT"
                )


                time.sleep(5)

                continue





            # 토큰 만료

            if (

                "TOKEN" in msg.upper()

                or

                "토큰" in msg

            ):


                print(
                    "TOKEN REISSUE"
                )


                clear_token()

                continue





            return data





        except Exception as e:


            print(
                "KIS ERROR:",
                e
            )


            time.sleep(3)





    return {

        "rt_cd":
        "ERROR",

        "msg1":
        "KIS REQUEST FAILED",

        "output":[]

    }







# =========================
# Price
# =========================

def get_stock_price(stock_code):


    data = kis_request(

        "FHKST01010100",

        "/uapi/domestic-stock/v1/quotations/inquire-price",

        {

            "FID_COND_MRKT_DIV_CODE":
            "J",

            "FID_INPUT_ISCD":
            stock_code

        }

    )


    return data.get(

        "output",

        {}

    )







# =========================
# Investor
# =========================

def get_investor_trade(stock_code):


    today = datetime.now().strftime(
        "%Y%m%d"
    )



    data = kis_request(

        "FHPTJ04160001",

        "/uapi/domestic-stock/v1/quotations/inquire-investor",

        {

            "FID_COND_MRKT_DIV_CODE":
            "J",

            "FID_INPUT_ISCD":
            stock_code,

            "FID_INPUT_DATE_1":
            today,

            "FID_ORG_ADJ_PRC":
            "0",

            "FID_ETC_CLS_CODE":
            "00"

        }

    )



    output = data.get(

        "output",

        []

    )



    row = {}



    if isinstance(output,list) and len(output)>0:

        row = output[0]



    return {


        "원본응답":
        data,


        "외국인순매수":
        float(
            row.get(
                "frgn_ntby_qty",
                0
            )
        ),


        "기관순매수":
        float(
            row.get(
                "orgn_ntby_qty",
                0
            )
        ),


        "개인순매수":
        float(
            row.get(
                "prsn_ntby_qty",
                0
            )
        )

    }
