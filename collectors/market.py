from collectors.kis import get_stock_price



def get_market_data(stock_code):


    data = get_stock_price(
        stock_code
    )



    return {


        "현재가":

        float(
            data.get(
                "stck_prpr",
                0
            )
        ),



        "전일대비":

        float(
            data.get(
                "prdy_vrss",
                0
            )
        ),



        "등락률":

        float(
            data.get(
                "prdy_ctrt",
                0
            )
        ),



        "거래량":

        int(
            data.get(
                "acml_vol",
                0
            )
        ),



        "시가":

        float(
            data.get(
                "stck_oprc",
                0
            )
        ),



        "고가":

        float(
            data.get(
                "stck_hgpr",
                0
            )
        ),



        "저가":

        float(
            data.get(
                "stck_lwpr",
                0
            )
        ),



        "PER":

        float(
            data.get(
                "per",
                0
            )
        ),



        "PBR":

        float(
            data.get(
                "pbr",
                0
            )
        ),



        "EPS":

        float(
            data.get(
                "eps",
                0
            )
        ),



        "BPS":

        float(
            data.get(
                "bps",
                0
            )
        ),



        "시가총액":

        float(
            data.get(
                "hts_avls",
                0
            )
        ),



        "데이터출처":

        "한국투자증권 KIS"

    }
