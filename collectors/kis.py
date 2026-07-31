import requests

from config import (
    KIS_APP_KEY,
    KIS_APP_SECRET,
    KIS_BASE_URL
)



def get_access_token():


    url = (
        f"{KIS_BASE_URL}/oauth2/tokenP"
    )


    body = {

        "grant_type":
        "client_credentials",

        "appkey":
        KIS_APP_KEY,

        "appsecret":
        KIS_APP_SECRET

    }


    r = requests.post(
        url,
        json=body
    )


    return r.json().get(
        "access_token"
    )




def get_stock_price(stock_code):


    token = get_access_token()


    url = (
        f"{KIS_BASE_URL}/uapi/domestic-stock/v1/"
        "quotations/inquire-price"
    )


    headers = {


        "authorization":
        "Bearer " + token,


        "appkey":
        KIS_APP_KEY,


        "appsecret":
        KIS_APP_SECRET,


        "tr_id":
        "FHKST01010100"

    }


    params = {


        "FID_COND_MRKT_DIV_CODE":
        "J",


        "FID_INPUT_ISCD":
        stock_code

    }



    response = requests.get(

        url,

        headers=headers,

        params=params

    )


    data=response.json()



    output=data.get(
        "output",
        {}
    )


    return {


        "현재가":
        float(
            output.get(
                "stck_prpr",
                0
            )
        ),


        "전일대비":
        float(
            output.get(
                "prdy_vrss",
                0
            )
        ),


        "등락률":
        float(
            output.get(
                "prdy_ctrt",
                0
            )
        ),


        "거래량":
        int(
            output.get(
                "acml_vol",
                0
            )
        ),


        "시가총액":
        0,


        "데이터출처":
        "한국투자증권 KIS"

    }
