import requests


def get_market_data(stock_code):


    try:

        url = (
            f"https://query1.finance.yahoo.com/v10/finance/quoteSummary/"
            f"{stock_code}.KS"
            "?modules=price,defaultKeyStatistics,financialData"
        )


        headers = {

            "User-Agent":
            "Mozilla/5.0"

        }


        response=requests.get(
            url,
            headers=headers,
            timeout=10
        )


        data=response.json()


        result=data["quoteSummary"]["result"][0]


        price=result["price"]

        stats=result["defaultKeyStatistics"]


        current_price=price.get(
            "regularMarketPrice",
            {}
        ).get(
            "raw",
            0
        )


        market_cap=price.get(
            "marketCap",
            {}
        ).get(
            "raw",
            0
        )


        per=stats.get(
            "trailingPE",
            {}
        ).get(
            "raw",
            0
        )


        eps=stats.get(
            "trailingEps",
            {}
        ).get(
            "raw",
            0
        )


        return {


            "현재가":
            current_price,


            "시가총액":
            market_cap,


            "PER":
            per,


            "EPS":
            eps,


            "데이터출처":
            "Yahoo Finance"

        }


    except Exception as e:


        return {


            "현재가":0,


            "PER":0,


            "EPS":0,


            "오류":
            str(e)

        }
