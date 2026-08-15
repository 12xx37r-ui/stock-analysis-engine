"""OpenDART 매출 계정명/XBRL ID 회귀검증."""
from collectors.fundamentals import parse_financial_period

def row(account_nm, amount, account_id="", sj_div="IS", ord_=1, add_amount=None):
    return {
        "sj_div": sj_div,
        "account_nm": account_nm,
        "account_id": account_id,
        "thstrm_amount": str(amount),
        "thstrm_add_amount": str(add_amount if add_amount is not None else amount),
        "ord": str(ord_),
    }

rows = [
    row("수익", 6_800_000_000_000, "ifrs-full_Revenue", ord_=1),
    row("영업이익(손실)", -94_453_000_000, "dart_OperatingIncomeLoss", ord_=2),
    row("당기순이익(손실)", -1_272_678_000_000, "ifrs-full_ProfitLoss", ord_=3),
    row("자산총계", 77_877_681_000_000, sj_div="BS", ord_=1),
    row("부채총계", 47_591_037_000_000, sj_div="BS", ord_=2),
    row("자본총계", 30_286_644_000_000, sj_div="BS", ord_=3),
]
parsed = parse_financial_period(rows, 2026, "11012", "CFS", "000", "정상")
assert parsed["수집상태"] == "정상", parsed
assert parsed["지표"]["매출"] == 6_800_000_000_000, parsed
assert parsed["핵심계정매칭"]["매출"]["계정ID"] == "ifrs-full_Revenue", parsed

rows_by_id = [
    row("제품및서비스수익", 7_100_000_000_000, "ifrs-full_Revenue", ord_=1),
    row("영업이익", 300_000_000_000, ord_=2),
    row("당기순이익", 200_000_000_000, ord_=3),
]
parsed_by_id = parse_financial_period(rows_by_id, 2026, "11013", "CFS", "000", "정상")
assert parsed_by_id["지표"]["매출"] == 7_100_000_000_000, parsed_by_id

missing_revenue = [
    row("영업성과", 123, "custom_OperatingPerformance", ord_=1),
    row("영업이익", -10_000_000_000, "dart_OperatingIncomeLoss", ord_=2),
    row("당기순이익", -20_000_000_000, "ifrs-full_ProfitLoss", ord_=3),
]
blocked = parse_financial_period(missing_revenue, 2026, "11012", "CFS", "000", "정상")
assert blocked["수집상태"] == "부분성공", blocked
assert blocked["지표"]["매출"] == 0.0, blocked
assert blocked["지표검증오류"], blocked

real_zero = [
    row("수익", 0, "ifrs-full_Revenue", ord_=1),
    row("영업이익", -1_000_000_000, "dart_OperatingIncomeLoss", ord_=2),
]
zero = parse_financial_period(real_zero, 2026, "11013", "CFS", "000", "정상")
assert zero["수집상태"] == "정상", zero
assert zero["지표"]["매출"] == 0.0, zero

print("DART REVENUE MATCHING: PASS")
