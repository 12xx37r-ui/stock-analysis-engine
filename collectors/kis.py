import requests
from config import (
    KIS_APP_KEY,
    KIS_APP_SECRET,
    KIS_BASE_URL
)



def get_access_token():

    url = f"{KIS_BASE_URL}/oauth2/tokenP"

    body = {

        "grant_type": "client_credentials",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET

    }


    response = requests.post(
        url,
        json=body,
        timeout=10
    )


    data=response.json()


    return data.get(
        "access_token"
    )




def get_stock_price(stock_code):


    token=get_access_token()


    if not token:

        return {

            "오류":
            "토큰 발급 실패"

        }



    url = (
        f"{KIS_BASE_URL}"
        "/uapi/domestic-stock/v1/"
        "quotations/inquire-price"
    )


    headers={


        "authorization":
        "Bearer "+token,


        "appkey":
        KIS_APP_KEY,


        "appsecret":
        KIS_APP_SECRET,


        "tr_id":
        "FHKST01010100",


        "custtype":
        "P"

    }



    params={


        "FID_COND_MRKT_DIV_CODE":
        "J",


        "FID_INPUT_ISCD":
        stock_code

    }



    response=requests.get(

        url,

        headers=headers,

        params=params,

        timeout=10

    )


    data=response.json()



    return {


        "KIS응답코드":
        data.get("rt_cd"),


        "KIS메시지":
        data.get("msg1"),


        "종목코드":
        stock_code,


        "원본":
        data.get("output",{})


    }
