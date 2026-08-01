import requests

from config import DART_API_KEY



def get_company_code(company_name):


    url = (
        "https://opendart.fss.or.kr/api/"
        "corpCode.xml"
    )


    # 기존 프로젝트에서 이미 기업코드를
    # 직접 사용하는 구조라면 그대로 반환

    company_map = {


        "삼성전자":
        "00126380"


    }


    return company_map.get(
        company_name,
        None
    )
