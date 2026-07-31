from collectors.company import find_company_code
from collectors.dart import get_financial
from collectors.price import get_price

from analyzers.financial import analyze_financial
from analyzers.valuation import calculate_value

import json
import os



def run(company):


    corp_code = find_company_code(
        company
    )


    if corp_code is None:

        return {
            "error":"기업코드 없음"
        }



    # DART 재무

    dart_data = get_financial(
        corp_code
    )


    if dart_data.get("status") != "000":

        return {
            "error":dart_data
        }



    # 재무 분석

    financial = analyze_financial(
        dart_data
    )



    # 가격 데이터

    price = get_price(
        corp_code
    )



    # 적정가 계산

    valuation = calculate_value(
        financial,
        price
    )



    result={


        "기업명":
        company,


        "기업코드":
        corp_code,


        "재무분석":
        financial,


        "가격정보":
        price,


        "가치평가":
        valuation


    }


    return result




if __name__ == "__main__":


    company="삼성전자"


    result=run(
        company
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
