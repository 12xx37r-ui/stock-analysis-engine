import requests


def get_market_data(stock_code):


    try:


        headers = {

            "User-Agent":
            "Mozilla/5.0"

        }


        url = (
            "https://query1.finance.yahoo.com/v8/finance/chart/"
            f"{stock_code}.KS"
            "?range=5d&interval=1d"
        )


        response = requests.get(
            url,
            headers=headers,
            timeout=10
        )


        data=response.json()


        result=data["chart"]["result"][0]


        meta=result["meta"]


        prices=result["indicators"]["quote"][0]["close"]


        price=prices[-1]



        return {


            "현재가":
            price,


            "전일종가":
            prices[-2],


            "데이터출처":
            "Yahoo Finance chart"


        }



    except Exception as e:


        return {


            "현재가":0,


            "오류":
            str(e)

        }
