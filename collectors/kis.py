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



    if not KIS_APP_KEY or not KIS_APP_SECRET:

        print("KIS KEY 없음")

        return None



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


    print("TOKEN RESPONSE")

    print(response.text)



    data=response.json()



    TOKEN=data.get(

        "access_token"

    )



    return TOKEN





def kis_request(tr_id,path,params):


    token=get_access_token()



    if not token:

        return {}



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



    response=requests.get(

        KIS_BASE_URL+path,

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





def get_investor_trade(stock_code):


    data=kis_request(

        "FHPTJ04040000",

        "/uapi/domestic-stock/v1/quotations/inquire-investor",

        {

        "FID_COND_MRKT_DIV_CODE":"J",

        "FID_INPUT_ISCD":stock_code

        }

    )


    return {


        "원본응답":data,


        "외국인순매수":0,

        "기관순매수":0,

        "개인순매수":0

    }
