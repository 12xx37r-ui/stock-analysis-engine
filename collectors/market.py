from collectors.kis import (
    get_stock_price,
    get_investor_trade
)


def get_market_data(stock_code):


    price = get_stock_price(
        stock_code
    )


    investor_raw = get_investor_trade(
        stock_code
    )


    # KIS 투자자 원본 파싱
    investor = {

        "외국인순매수": 0,

        "기관순매수": 0,

        "개인순매수": 0

    }


    try:

        output2 = investor_raw.get(
            "output2",
            []
        )


        if len(output2) > 0:

            today = output2[0]


            investor["외국인순매수"] = int(
                today.get(
                    "frgn_ntby_qty",
                    0
                )
            )


            investor["기관순매수"] = int(
                today.get(
                    "orgn_ntby_qty",
                    0
                )
            )


            investor["개인순매수"] = int(
                today.get(
                    "prsn_ntby_qty",
                    0
                )
            )


    except Exception as e:

        print(
            "투자자 데이터 파싱 오류:",
            e
        )



    return {


        "현재가":
        float(
            price.get(
                "stck_prpr",
                0
            )
        ),


        "전일대비":
        float(
            price.get(
                "prdy_vrss",
                0
            )
        ),


        "등락률":
        float(
            price.get(
                "prdy_ctrt",
                0
            )
        ),


        "거래량":
        int(
            price.get(
                "acml_vol",
                0
            )
        ),


        "시가":
        float(
            price.get(
                "stck_oprc",
                0
            )
        ),


        "고가":
        float(
            price.get(
                "stck_hgpr",
                0
            )
        ),


        "저가":
        float(
            price.get(
                "stck_lwpr",
                0
            )
        ),


        "PER":
        float(
            price.get(
                "per",
                0
            )
        ),


        "PBR":
        float(
            price.get(
                "pbr",
                0
            )
        ),


        "EPS":
        float(
            price.get(
                "eps",
                0
            )
        ),


        "BPS":
        float(
            price.get(
                "bps",
                0
            )
        ),


        "시가총액":
        float(
            price.get(
                "hts_avls",
                0
            )
        ),


        "수급":
        investor,


        "데이터출처":
        "한국투자증권 KIS"

    }
