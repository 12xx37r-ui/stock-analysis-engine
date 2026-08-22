from analyzers.financial import analyze_financial
from collectors.fundamentals import parse_financial_period


def row(account_nm, value, sj_div="BS", account_id=""):
    return {
        "account_nm": account_nm,
        "account_id": account_id,
        "sj_div": sj_div,
        "thstrm_amount": str(value),
        "thstrm_add_amount": str(value),
        "frmtrm_amount": str(value),
        "bfefrmtrm_amount": str(value),
        "ord": "1",
    }


rows = [
    row("매출액", 1000, "IS"),
    row("영업이익", 100, "IS"),
    row("당기순이익", 80, "IS"),
    row("자산총계", 2000, "BS"),
    row("유동자산", 600, "BS", "ifrs-full_CurrentAssets"),
    row("유동부채", 300, "BS", "ifrs-full_CurrentLiabilities"),
    row("부채총계", 800, "BS"),
    row("자본총계", 1200, "BS"),
]

period = parse_financial_period(rows, 2025, "11011", "CFS", "000", "OK")
metrics = period["지표"]

assert metrics["유동자산"] == 600.0, metrics
assert metrics["유동부채"] == 300.0, metrics

analysis = analyze_financial({"list": rows}, industry_code="electronic_components")
assert analysis["재무지표"]["유동비율"] == 200.0, analysis["재무지표"]
assert analysis["원본"]["유동자산"] == 600.0
assert analysis["원본"]["유동부채"] == 300.0

finance_analysis = analyze_financial({"list": rows}, industry_code="finance")
assert finance_analysis["재무지표"]["유동비율"] is None

print("CURRENT RATIO PIPELINE: PASS")
print("일반기업 유동비율:", analysis["재무지표"]["유동비율"])
print("금융업 유동비율:", finance_analysis["재무지표"]["유동비율"])
