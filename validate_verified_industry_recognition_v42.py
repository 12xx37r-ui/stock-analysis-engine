from analyzers.strategic_forward_value import _evidence_recognition_factor

company = {"점수": 81.13, "품질": 85.55, "사용가능": True}
verified_industry_env = {"점수": 47.49, "품질": 57.0, "사용가능": True}
expectation = {"점수": 94.0, "품질": 100.0, "사용가능": True}
legacy_missing = {"점수": 0.0, "품질": 0.0, "사용가능": False}

verified_factor, verified_reasons = _evidence_recognition_factor(
    company, verified_industry_env, expectation
)
legacy_factor, legacy_reasons = _evidence_recognition_factor(
    company, legacy_missing, expectation
)

assert verified_factor > 0.40, (verified_factor, verified_reasons)
assert not any("산업근거 부족" in x for x in verified_reasons), verified_reasons
assert abs(legacy_factor - 0.40) < 1e-9, (legacy_factor, legacy_reasons)
assert any("산업근거 부족" in x for x in legacy_reasons), legacy_reasons

print("VERIFIED INDUSTRY RECOGNITION V4.2: PASS")
print("verified_industry_factor_pct", round(verified_factor * 100, 2))
print("legacy_missing_factor_pct", round(legacy_factor * 100, 2))
