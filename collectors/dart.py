import requests

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



    try:


        response = requests.get(

            url,

            params=params,

            timeout=30

        )


        response.raise_for_status()



        data = response.json()



        return data



    except requests.exceptions.Timeout:


        print(
            "DART TIMEOUT"
        )


        return {

            "status":
            "error",

            "message":
            "DART timeout",

            "list":
            []

        }



    except Exception as e:


        print(

            "DART REQUEST ERROR:",
            e

        )


        return {

            "status":
            "error",

            "message":
            str(e),

            "list":
            []

        }
