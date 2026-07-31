import json


def find_company_code(name):

    with open(
        "data/corp_codes.json",
        encoding="utf-8"
    ) as f:

        companies=json.load(f)


    for company in companies:

        if company["corp_name"] == name:

            return company["corp_code"]


    return None
