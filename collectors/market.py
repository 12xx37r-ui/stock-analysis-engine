from pykrx import stock


def get_market_data(stock_code):

    try:

        today = stock.get_nearest_business_day_in_a_week()


        df = stock.get_market_ohlcv(
            today,
            today,
            stock_code
        )


        price = int(
            df["종가"].iloc[0]
        )


        return {


            "현재가":
            price,


            "데이터출처":
            "KRX pykrx"


        }



    except Exception as e:


        return {


            "현재가":0,


            "오류":
            str(e)

        }
