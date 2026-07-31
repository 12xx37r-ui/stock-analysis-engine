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


    print("KIS TOKEN RESPONSE")
    print(data)


    return data.get(
        "access_token"
    )



def kis_request(tr_id, path, params):


    token=get_access_token()


    if not token:

        return {

            "error":
            "TOKEN_FAIL"

        }



    headers={


        "authorization":
        "Bearer "+token,


        "appkey":
        KIS_APP_KEY,


        "appsecret":
        KIS_APP_SECRET,


        "tr_id":
        tr_id,


        "custtype":
        "P"

    }



    url=KIS_BASE_URL + path



    response=requests.get(

        url,

        headers=headers,

        params=params,

        timeout=10

    )


    return response.json()



def get_stock_price(stock_code):


    data=kis_request(

        "FHKST01010100",

        "/uapi/domestic-stock/v1/quotations/inquire-price",

        {

            "FID_COND_MRKT_DIV_CODE":"J",

            "FID_INPUT_ISCD":stock_code

        }

    )


    return data.get(
        "output",
        {}
    )



def get_stock_finance(stock_code):


    data=kis_request(

        "FHKST01010400",

        "/uapi/domestic-stock/v1/quotations/search-info",

        {

            "PRDT_TYPE_CD":"300",

            "PDNO":stock_code

        }

    )


    return data.get(
        "output",
        {}
    )
