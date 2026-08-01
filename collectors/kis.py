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

TOKEN_FILE = "kis_token.json"





def load_token():

    global ACCESS_TOKEN


    if not os.path.exists(TOKEN_FILE):

        return None



    try:

        with open(
            TOKEN_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)



        token = data.get(
            "access_token"
        )


        if token:

            ACCESS_TOKEN = token

            print(
                "TOKEN LOADED"
            )

            return token



    except Exception as e:

        print(
            "TOKEN LOAD ERROR",
            e
        )



    return None





def save_token(token):

    try:

        with open(
            TOKEN_FILE,
            "w",
            encoding="utf-8"
        ) as f:


            json.dump(

                {
                    "access_token": token,
                    "saved_at":
                    datetime.now().isoformat()
                },

                f,

                indent=2

            )


    except Exception as e:

        print(
            "TOKEN SAVE ERROR",
            e
        )







def get_access_token(force=False):


    global ACCESS_TOKEN



    if ACCESS_TOKEN and not force:

        return ACCESS_TOKEN




    if not force:

        token = load_token()

        if token:

            return token





    print(
        "REQUEST TOKEN"
    )



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


            save_token(token)


            print(
                "TOKEN OK"
            )


            return token





        print(

            "TOKEN FAIL",

            data

        )




    except Exception as e:


        print(

            "TOKEN ERROR",

            e

        )




    ACCESS_TOKEN = None


    return None







def kis_request(

    tr_id,

    path,

    params

):



    for retry in range(3):


        token = get_access_token()



        if not token:


            return {

                "rt_cd":

                "TOKEN_ERROR",


                "msg1":

                "토큰 실패",


                "output":[]

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




        try:


            time.sleep(1.2)



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



            if "초당" in msg:


                print(

                    "RATE LIMIT"

                )


                time.sleep(5)


                continue




            if "토큰" in msg:


                get_access_token(

                    True

                )


                continue




            return data




        except Exception as e:


            print(

                "REQUEST ERROR",

                e

            )


            time.sleep(3)





    return {


        "rt_cd":

        "ERROR",


        "msg1":

        "REQUEST FAILED",


        "output":[]

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



    if not output:


        output = data.get(

            "output2",

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
