from collectors.company import find_company_code
from collectors.dart import get_financial
from collectors.market import get_market_data

from analyzers.financial import analyze_financial
from analyzers.valuation import calculate_value

import json
import os



def run(company, stock_code):


    # 기업코드 검색

    corp_code = find_company_code(
        company
    )


    if corp_code is None:

        return {

            "error":
            "기업코드를 찾을 수 없습니다."

        }



    # DART 재무 데이터

    dart_data = get_financial(
        corp_code
    )


    if dart_data.get("status") != "000":

        return {

            "error":
            dart_data

        }



    # 재무 분석

    financial = analyze_financial(
        dart_data
    )



    # 시장 데이터

    market = get_market_data(
        stock_code
    )



    # 가치평가

    valuation = calculate_value(
        financial,
        market
    )



    result = {


        "기업명":

        company,


        "기업코드":

        corp_code,


        "재무분석":

        financial,


        "시장정보":

        market,


        "가치평가":

        valuation

    }



    return result




if __name__ == "__main__":



    # 테스트 기업

    company = "삼성전자"


    # 종목코드

    stock_code = "005930"



    result = run(

        company,

        stock_code

    )



    print(

        json.dumps(

            result,

            ensure_ascii=False,

            indent=2

        )

    )



    os.makedirs(

        "output",

        exist_ok=True

    )



    with open(

        "output/samsung.json",

        "w",

        encoding="utf-8"

    ) as f:


        json.dump(

            result,

            f,

            ensure_ascii=False,

            indent=2

        )
