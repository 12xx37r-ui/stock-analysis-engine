import requests


def get_market_data(stock_code):

    try:

        headers = {
            "User-Agent": "Mozilla/5.0"
        }


        url = (
            "https://query1.finance.yahoo.com/v8/finance/chart/"
            f"{stock_code}.KS"
            "?range=1d&interval=1m"
        )


        response = requests.get(
            url,
            headers=headers,
            timeout=10
        )


        data = response.json()


        result = data["chart"]["result"][0]


        quote = result["indicators"]["quote"][0]


        prices = quote["close"]


        prices = [
            p for p in prices
            if p is not None
        ]


        if not prices:

            raise Exception(
                "가격 데이터 없음"
            )


        current_price = prices[-1]



        return {

            "현재가":
            round(current_price,2),


            "데이터출처":
            "Yahoo Finance 1분봉"

        }



    except Exception as e:


        return {

            "현재가":0,

            "오류":
            str(e)

        }
