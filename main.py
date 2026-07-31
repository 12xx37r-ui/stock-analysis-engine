from collectors.company import find_company_code
from collectors.dart import get_financial
from analyzers.financial import analyze_financial

import json
import os



def run(company):

    print(
        f"{company} 분석 시작"
    )


    # 1. 기업코드 조회

    corp_code = find_company_code(
        company
    )


    if corp_code is None:

        return {

            "error":
            "기업코드를 찾을 수 없습니다."

        }



    print(
        "기업코드:",
        corp_code
    )


    # 2. DART 재무 데이터 수집

    dart_data = get_financial(
        corp_code
    )


    if dart_data.get("status") != "000":

        return {

            "error":
            dart_data

        }



    # 3. 재무 분석

    analysis = analyze_financial(
        dart_data
    )


    result={

        "기업명":
        company,


        "기업코드":
        corp_code,


        "분석결과":
        analysis

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


    # 결과 저장

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
