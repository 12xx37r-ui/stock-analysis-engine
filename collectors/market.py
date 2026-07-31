from collectors.kis import get_stock_price



def get_market_data(stock_code):


    data = get_stock_price(
        stock_code
    )


    output = data.get(
        "원본",
        {}
    )


    return {


        "현재가":

        float(
            output.get(
                "stck_prpr",
                0
            )
        ),


        "전일대비":

        float(
            output.get(
                "prdy_vrss",
                0
            )
        ),


        "등락률":

        float(
            output.get(
                "prdy_ctrt",
                0
            )
        ),


        "거래량":

        int(
            output.get(
                "acml_vol",
                0
            )
        ),


        "시가":

        float(
            output.get(
                "stck_oprc",
                0
            )
        ),


        "고가":

        float(
            output.get(
                "stck_hgpr",
                0
            )
        ),


        "저가":

        float(
            output.get(
                "stck_lwpr",
                0
            )
        ),


        "데이터출처":

        "한국투자증권 KIS"

    }
