from collectors.company import find_company_code
from collectors.dart import get_financial


company="삼성전자"


corp_code=find_company_code(company)


financial=get_financial(
    corp_code
)


print(financial)
