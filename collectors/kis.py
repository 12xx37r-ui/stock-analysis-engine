import requests
import time
from datetime import datetime

from config import (
    KIS_APP_KEY,
    KIS_APP_SECRET,
    KIS_BASE_URL
)


ACCESS_TOKEN = None



def get_access_token(force=False):

    global ACCESS_TOKEN


    if ACCESS_TOKEN and not force:
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



    for retry in range(3):

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

                return ACCESS_TOKEN



            print(
                "TOKEN ERROR:",
                data
            )



        except Exception as e:

            print(
                "TOKEN REQUEST ERROR:",
                e
            )



        time.sleep(2)



    ACCESS_TOKEN = None

    return None





def kis_request(
    tr_id,
    path,
    params
):


    global ACCESS_TOKEN



    token = get_access_token()



    if not token:

        return {

            "rt_cd":
            "TOKEN_ERROR",

            "msg1":
            "토큰 발급 실패"

        }




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




    for retry in range(2):


        try:


            time.sleep(0.5)



            response = requests.get(

                KIS_BASE_URL + path,

                headers=headers,

                params=params,

                timeout=10

            )



            data = response.json()



            # 토큰 만료 또는 오류

            if data.get("rt_cd") != "0":


                msg = str(
                    data.get(
                        "msg1",
                        ""
                    )
                )


                if (
                    "TOKEN" in msg.upper()
                    or
                    "토큰" in msg
                ):

                    get_access_token(
                        force=True
                    )


                    headers["authorization"] = (
                        "Bearer "
                        +
                        ACCESS_TOKEN
                    )

                    continue



            return data



        except Exception as e:


            print(
                "KIS REQUEST ERROR:",
                e
            )


            time.sleep(2)




    return {

        "rt_cd":
        "REQUEST_ERROR",

        "msg1":
        "KIS 요청 실패"

    }







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



    if isinstance(output, list) and len(output) > 0:

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
