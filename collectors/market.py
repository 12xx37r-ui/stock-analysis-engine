import requests


def get_market_data(stock_code):


    try:


        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/"
            f"{stock_code}.KS"
        )


        headers={

            "User-Agent":
            "Mozilla/5.0"

        }



        response=requests.get(

            url,

            headers=headers,

            timeout=10

        )



        if response.status_code != 200:

            return {

                "현재가":0,

                "오류":
                f"HTTP {response.status_code}"

            }



        data=response.json()



        result=data["chart"]["result"][0]



        meta=result["meta"]



        price=meta.get(

            "regularMarketPrice",

            0

        )



        return {


            "현재가":

            price,


            "데이터출처":

            "Yahoo Finance"


        }



    except Exception as e:


        return {


            "현재가":

            0,


            "오류":

            str(e)

        }
