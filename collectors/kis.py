import requests
import time
import os
import json
from datetime import datetime, timedelta


from config import (
    KIS_APP_KEY,
    KIS_APP_SECRET,
    KIS_BASE_URL
)



TOKEN_FILE = "kis_token.json"



def load_token():

    if not os.path.exists(TOKEN_FILE):

        return None


    try:

        with open(
            TOKEN_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)



        expire = datetime.fromisoformat(
            data["expire"]
        )


        if datetime.now() < expire:

            return data["access_token"]



    except Exception:

        pass



    return None





def save_token(token):


    data = {


        "access_token":
        token,


        "expire":
        (
            datetime.now()
            +
            timedelta(hours=23)
        ).isoformat()


    }


    with open(

        TOKEN_FILE,

        "w",

        encoding="utf-8"

    ) as f:


        json.dump(

            data,

            f,

            ensure_ascii=False

        )







def get_access_token(force=False):


    if not force:


        token = load_token()


        if token:

            return token





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


        save_token(

            token

        )


        print(

            "TOKEN CREATED: True"

        )


        return token



    print(

        "TOKEN ERROR",

        data

    )


    return None








def kis_request(

    tr_id,

    path,

    params

):


    token = get_access_token()



    if not token:


        return {


            "rt_cd":

            "TOKEN_ERROR",


            "msg1":

            "토큰 발급 실패",


            "output":[]

        }





    headers = {


        "authorization":

        "Bearer "

        +

        token,


        "appkey":

        KIS_APP_KEY,


        "appsecret":

        KIS_APP_SECRET,


        "tr_id":

        tr_id,


        "custtype":

        "P"


    }



    time.sleep(0.5)



    response = requests.get(

        KIS_BASE_URL + path,

        headers=headers,

        params=params,

        timeout=10

    )



    data = response.json()



    # 토큰 만료

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


            token = get_access_token(

                force=True

            )


            headers["authorization"] = (

                "Bearer "

                +

                token

            )


            response = requests.get(

                KIS_BASE_URL + path,

                headers=headers,

                params=params,

                timeout=10

            )


            data = response.json()



    return data









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
