import requests


def get_market_data(stock_code):

    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        f"{stock_code}.KS"
    )


    try:

        response = requests.get(
            url,
            timeout=10
        )


        data=response.json()


        result=data["chart"]["result"][0]


        price=result["meta"].get(
            "regularMarketPrice",
            0
        )


        return {

            "현재가":price,

            "데이터출처":
            "Yahoo Finance"

        }


    except Exception as e:


        return {

            "현재가":0,

            "오류":
            str(e)

        }
