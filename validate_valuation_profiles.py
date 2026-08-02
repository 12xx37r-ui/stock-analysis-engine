"""업종 적응형 가치평가 프로필 정적 검증."""

from analyzers.valuation import VALUATION_PROFILES, calculate_value
from collectors.company import VALUATION_INDUSTRIES, classify_dart_industry


REQUIRED_PROFILE_FIELDS = {
    "label",
    "base_per",
    "per_min",
    "per_max",
    "base_pbr",
    "pbr_min",
    "pbr_max",
    "weights",
    "eps_floor",
    "eps_cap",
    "downside",
    "upside",
    "model_floor",
    "model_ceiling",
    "cyclical",
    "growth",
}


def validate_profiles():
    errors = []

    for code, profile in VALUATION_PROFILES.items():
        missing = REQUIRED_PROFILE_FIELDS - set(profile)
        if missing:
            errors.append(f"{code}: 필수필드 누락 {sorted(missing)}")
            continue

        if not (profile["per_min"] <= profile["base_per"] <= profile["per_max"]):
            errors.append(f"{code}: PER 범위 오류")
        if not (profile["pbr_min"] <= profile["base_pbr"] <= profile["pbr_max"]):
            errors.append(f"{code}: PBR 범위 오류")
        if not (0 < profile["eps_floor"] <= 1.0 <= profile["eps_cap"]):
            errors.append(f"{code}: EPS 보정범위 오류")
        if not (0 < profile["downside"] <= 1.0 <= profile["upside"]):
            errors.append(f"{code}: 시나리오 범위 오류")

        weights = profile["weights"]
        if set(weights) != {"per", "pbr", "residual", "transition"}:
            errors.append(f"{code}: 모형가중치 키 오류")
        elif abs(sum(weights.values()) - 1.0) > 1e-9:
            errors.append(f"{code}: 모형가중치 합이 1이 아님")

    supported = set(VALUATION_PROFILES) | {"none"}
    unknown = set(VALUATION_INDUSTRIES) - supported
    if unknown:
        errors.append(f"company.py 산업코드와 가치프로필 불일치: {sorted(unknown)}")

    mapping_examples = {
        "261": "semiconductor",
        "264": "electronic_components",
        "301": "automotive",
        "212": "pharmaceutical",
        "411": "construction",
        "641": "finance",
        "651": "finance",
        "661": "insurance",
        "107": "consumer_staples",
        "471": "retail",
        "582": "media_entertainment",
        "620": "software_platform",
        "612": "telecom",
        "351": "utilities",
        "201": "materials",
        "291": "industrial",
        "501": "transportation",
        "681": "real_estate",
        "861": "healthcare",
        "051": "energy",
    }
    for dart_code, expected in mapping_examples.items():
        actual = classify_dart_industry(dart_code)
        if actual != expected:
            errors.append(f"DART {dart_code}: {actual} != {expected}")

    synthetic_financial = {
        "재무지표": {
            "ROE": 14.0,
            "부채비율": 70.0,
            "영업이익률": 12.0,
            "순이익률": 9.0,
        },
        "성장지표": {
            "매출3년성장률": 12.0,
            "영업이익3년성장률": 18.0,
            "순이익3년성장률": 15.0,
        },
    }
    synthetic_market = {
        "현재가": 10000.0,
        "EPS": 800.0,
        "BPS": 6000.0,
        "PER": 12.5,
        "PBR": 1.67,
    }

    for code in VALUATION_PROFILES:
        result = calculate_value(
            synthetic_financial,
            synthetic_market,
            company_info={
                "가치평가산업코드": code,
                "산업분류신뢰도": 95,
                "산업프로필버전": "3.0.0",
            },
        )
        low = result["보수적적정가"]
        mid = result["기본적정가"]
        high = result["성장적정가"]
        if not (0 < low <= mid <= high):
            errors.append(f"{code}: 가치범위 순서 오류 {low}, {mid}, {high}")
        if result["가치평가산업코드"] != code:
            errors.append(f"{code}: 프로필 선택 실패")

    if errors:
        print("VALUATION PROFILE VALIDATION FAILED")
        for error in errors:
            print("-", error)
        raise SystemExit(1)

    print(
        "VALUATION PROFILE VALIDATION OK:",
        len(VALUATION_PROFILES),
        "profiles",
    )


if __name__ == "__main__":
    validate_profiles()
