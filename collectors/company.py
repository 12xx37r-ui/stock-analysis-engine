import json


def find_company_code(name):


    with open(
        "data/corp_codes.json",
        encoding="utf-8"
    ) as f:

        companies=json.load(f)



    for company in companies:


        if name in company["corp_name"]:


            return company["corp_code"]



    return None
