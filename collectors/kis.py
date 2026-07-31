def get_investor_trade(stock_code):


    data = kis_request(

        "FHPTJ04040000",

        "/uapi/domestic-stock/v1/quotations/inquire-investor",

        {

            "FID_COND_MRKT_DIV_CODE": "J",

            "FID_INPUT_ISCD": stock_code

        }

    )


    print("KIS 투자자 원본:")
    print(data)



    output = data.get(
        "output",
        []
    )


    if not output:
        return {

            "외국인순매수":0,

            "기관순매수":0,

            "개인순매수":0

        }


    row = output[0]


    return {

        "외국인순매수":
        float(
            row.get(
                "frgn_ntby_qty",
                0
            )
        ),


        "기관순매수":
        float(
            row.get(
                "orgn_ntby_qty",
                0
            )
        ),


        "개인순매수":
        float(
            row.get(
                "prsn_ntby_qty",
                0
            )
        )

    }
