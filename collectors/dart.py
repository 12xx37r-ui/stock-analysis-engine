from collectors.dart_http import get_json as dart_get_json

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



    data = dart_get_json(url, params)

    if str(data.get("status", "")) in {"000", "013"}:
        return data

    print("DART REQUEST ERROR:", data.get("message", "OpenDART failure"))
    return data

