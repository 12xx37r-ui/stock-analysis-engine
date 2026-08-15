"""Robust fair-value v4.1 regression tests."""
from analyzers.valuation import _normalized_eps, VALUATION_PROFILES

# LGES-like annual EPS: one depressed year must not become the whole cycle-normalized EPS.
annual = [
    {"year": 2025, "eps": 345.31},
    {"year": 2024, "eps": 1447.02},
    {"year": 2023, "eps": 6999.94},
]
normalized = _normalized_eps(annual)
assert normalized > 1200, normalized
assert normalized < 3000, normalized

# One-year only stays backward-compatible and does not invent history.
single = _normalized_eps([{"year": 2025, "eps": 345.31}])
assert abs(single - 345.31) < 0.01, single

# Profiles remain unchanged; no tuning to market price.
assert VALUATION_PROFILES["battery"]["base_per"] == 16.0
assert VALUATION_PROFILES["electronic_components"]["base_per"] == 15.0

print("ROBUST FAIR VALUE V4.1: PASS")
print("normalized_lges_like_eps", round(normalized, 2))
