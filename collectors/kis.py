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
                    "TOKEN LOADED FROM FILE"
                )

                return token


    except Exception as e:

        print(
            "TOKEN LOAD ERROR:",
            e
        )


    return None




def save_token(token):

    with open(
        TOKEN_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            {
                "access_token": token,
                "saved_at": datetime.now().isoformat()
            },
            f,
            ensure_ascii=False,
            indent=2
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
        "REQUEST NEW TOKEN"
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
            "TOKEN CREATED: True"
        )

        return token



    print(
        "TOKEN ERROR:",
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



    time.sleep(0.5)


    response = requests.get(

        KIS_BASE_URL + path,

        headers=headers,

        params=params,

        timeout=10

    )


    return response.json()





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



    # ★ 수정 부분
    # KIS는 output2 사용

    output = data.get(
        "output2",
        []
    )


    row = {}


    if isinstance(output,list) and len(output)>0:

        row = output[0]



    foreign = float(
        row.get(
            "frgn_ntby_qty",
            0
        )
    )


    institution = float(
        row.get(
            "orgn_ntby_qty",
            0
        )
    )


    personal = float(
        row.get(
            "prsn_ntby_qty",
            0
        )
    )



    return {


        "원본응답":
        data,


        "외국인순매수":
        foreign,


        "기관순매수":
        institution,


        "개인순매수":
        personal


    }
