import requests
from datetime import datetime, timedelta


def get_market_data(stock_code):

    try:

        today = datetime.now()

        start = (
            today - timedelta(days=10)
        ).strftime("%Y-%m-%d")

        end = today.strftime("%Y-%m-%d")


        url = "https://query1.finance.yahoo.com/v8/finance/chart/"


        ticker = stock_code + ".KS"


        response = requests.get(
            url + ticker,
            params={
                "period1": start,
                "period2": end,
                "interval": "1d"
            },
            headers={
                "User-Agent":
                "Mozilla/5.0"
            },
            timeout=10
        )


        data=response.json()


        result=data["chart"]["result"][0]


        closes=result["indicators"]["quote"][0]["close"]


        closes=[
            x for x in closes
            if x is not None
        ]


        if len(closes)==0:

            raise Exception(
                "가격 데이터 없음"
            )


        price=closes[-1]


        return {


            "현재가":
            round(price,2),


            "데이터출처":
            "Yahoo Finance chart"

        }



    except Exception as e:


        return {


            "현재가":0,


            "오류":
            str(e)

        }
