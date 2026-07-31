import requests


def get_market_data(stock_code):


    try:

        headers = {

            "User-Agent":
            "Mozilla/5.0"

        }


        url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/"
            f"{stock_code}.KS"
        )


        response = requests.get(
            url,
            headers=headers,
            timeout=10
        )


        data = response.json()


        result = data["chart"]["result"][0]

        meta = result["meta"]


        price = meta.get(
            "regularMarketPrice",
            0
        )


        previous = meta.get(
            "previousClose",
            0
        )


        currency = meta.get(
            "currency",
            "KRW"
        )


        return {


            "현재가":
            price,


            "전일종가":
            previous,


            "통화":
            currency,


            "데이터출처":
            "Yahoo Finance chart"


        }



    except Exception as e:


        return {


            "현재가":0,


            "전일종가":0,


            "오류":
            str(e)

        }
