from analyzers.financial import analyze_financial
from analyzers.valuation import calculate_value


def run(company):

    result = {}

    result["company"] = company

    financial = analyze_financial(company)

    result["financial"] = financial

    valuation = calculate_value(financial)

    result["valuation"] = valuation

    return result


if __name__ == "__main__":

    data = run("삼성전자")

    print(data)
