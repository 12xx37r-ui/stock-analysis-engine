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


    params={

        "crtfc_key":DART_API_KEY,

        "corp_code":corp_code,

        "bsns_year":year,

        "reprt_code":"11011",

        "fs_div":"CFS"

    }


    response=requests.get(
        url,
        params=params
    )


    data=response.json()


    return data
