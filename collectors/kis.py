import requests

from config import (
    KIS_APP_KEY,
    KIS_APP_SECRET,
    KIS_BASE_URL
)


TOKEN = None



def get_access_token():

    global TOKEN

    if TOKEN:
        return TOKEN


    body = {

        "grant_type":
        "client_credentials",

        "appkey":
        KIS_APP_KEY,

        "appsecret":
        KIS_APP_SECRET

    }


    response = requests.post(

        KIS_BASE_URL + "/oauth2/tokenP",

        json=body,

        timeout=10

    )


    data = response.json()


    TOKEN = data.get(
        "access_token"
    )


    return TOKEN





def kis_request(tr_id, path, params):


    token = get_access_token()


    if not token:

        return {

            "rt_cd":"TOKEN_ERROR",

            "msg1":"토큰 발급 실패"

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



    response = requests.get(

        KIS_BASE_URL + path,

        headers=headers,

        params=params,

        timeout=10

    )


    return response.json()





# 현재가
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





# 투자자 수급
def get_investor_trade(stock_code):


    data = kis_request(

        "FHPTJ04160001",

        "/uapi/domestic-stock/v1/quotations/inquire-investor",

        {

            "FID_COND_MRKT_DIV_CODE":
            "J",

            "FID_INPUT_ISCD":
            stock_code

        }

    )


    output = data.get(

        "output",

        []

    )


    if isinstance(output,list) and len(output)>0:

        row = output[0]

    else:

        row = {}



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
