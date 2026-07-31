import requests



def get_market_data(stock_code):


    try:


        headers = {

            "User-Agent":
            "Mozilla/5.0"

        }



        # 현재가

        chart_url = (
            f"https://query1.finance.yahoo.com/v8/finance/chart/"
            f"{stock_code}.KS"
        )


        chart = requests.get(
            chart_url,
            headers=headers,
            timeout=10
        ).json()



        meta = chart["chart"]["result"][0]["meta"]


        price = meta.get(
            "regularMarketPrice",
            0
        )



        # quote API

        quote_url = (
            "https://query1.finance.yahoo.com/v7/finance/quote?"
            f"symbols={stock_code}.KS"
        )


        quote = requests.get(
            quote_url,
            headers=headers,
            timeout=10
        ).json()



        result = quote["quoteResponse"]["result"][0]



        market_cap = result.get(
            "marketCap",
            0
        )


        per = result.get(
            "trailingPE",
            0
        )


        eps = result.get(
            "epsTrailingTwelveMonths",
            0
        )


        return {


            "현재가":
            price,


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


            "시가총액":0,


            "PER":0,


            "EPS":0,


            "오류":
            str(e)

        }
