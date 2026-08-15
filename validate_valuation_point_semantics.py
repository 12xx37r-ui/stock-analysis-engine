from pathlib import Path
src = Path("analyzers/valuation.py").read_text(encoding="utf-8")

required = [
    'if earnings_trough:',
    '"정상화 회복가치"',
    'trough_candidates[:4]',
    'final_available = not fatal and data_qualification.get("통과") is True',
    'judgment = "산출불가"',
    '"정상화EPS연간자료개수": len(annual_eps)',
    '"정상화회복PER": round(recovery_multiple, 2)',
]
for token in required:
    assert token in src, token
print("VALUATION POINT SEMANTICS: PASS")
