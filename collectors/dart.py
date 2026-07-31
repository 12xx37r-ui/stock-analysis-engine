import requests
import time

from config import DART_API_KEY



def get_financial(
    corp_code,
    year="2025"
):


    url = (
        "https://opendart.fss.or.kr/api/"
        "fnlttSinglAcnt.json"
    )



    params = {


        "crtfc_key":
        DART_API_KEY,


        "corp_code":
        corp_code,


        "bsns_year":
        year,


        "reprt_code":
        "11011",


        "fs_div":
        "CFS"

    }



    for retry in range(3):

        try:


            response = requests.get(

                url,

                params=params,

                timeout=30

            )


            data = response.json()



            # DART 정상 응답

            if data.get("status") == "000":


                return data



            print(
                "DART 응답 오류:",
                data
            )


        except Exception as e:


            print(
                "DART 요청 실패:",
                retry + 1,
                e
            )



        time.sleep(3)



    return {

        "status":
        "999",

        "message":
        "DART API 요청 실패",

        "list":
        []

    }
