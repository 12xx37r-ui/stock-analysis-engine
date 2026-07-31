def get_investor_trade(stock_code):

    data = kis_request(

        "FHPTJ04160001",

        "/uapi/domestic-stock/v1/quotations/inquire-investor",

        {

            "FID_COND_MRKT_DIV_CODE": "J",

            "FID_INPUT_ISCD": stock_code

        }

    )


    output = data.get(
        "output",
        []
    )


    if isinstance(output,list) and len(output)>0:

        row=output[0]

    else:

        row={}


    return {

        "원본응답": data,


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
