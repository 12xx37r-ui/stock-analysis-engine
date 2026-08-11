"""업종 적응형 가치평가 프로필 정적 검증."""

from analyzers.valuation import FUTURE_GROWTH_CONFIG, VALUATION_PROFILES, calculate_value
from collectors.company import VALUATION_INDUSTRIES, classify_dart_industry, classify_dart_industry_detail


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

    for code, config in FUTURE_GROWTH_CONFIG.items():
        if code not in VALUATION_PROFILES:
            errors.append(f"{code}: 미래성장 설정에 없는 가치프로필")
            continue
        if VALUATION_PROFILES[code].get("growth") is not True:
            errors.append(f"{code}: 성장형이 아닌데 미래성장 설정 존재")
        if not (0.05 <= config.get("weight", 0) <= 0.25):
            errors.append(f"{code}: 미래성장 가중치 범위 오류")
        if not (0 < config.get("fy4_cap", 0) <= config.get("fy3_cap", 0) <= 0.30):
            errors.append(f"{code}: 미래성장 감쇠·상한 오류")
        if not (1.0 <= config.get("eps_cap", 0) <= 2.5):
            errors.append(f"{code}: 미래 EPS 상한 오류")
        if not (1.0 <= config.get("value_cap", 0) <= 2.0):
            errors.append(f"{code}: 미래가치 상한 오류")

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
        "651": "insurance",
        "661": "finance",
        "107": "consumer_staples",
        "471": "retail",
        "582": "media_entertainment",
        "620": "software_platform",
        "612": "telecom",
        "351": "utilities",
        "201": "materials",
        "20421": "materials",
        "20422": "beauty_consumer",
        "20423": "beauty_consumer",
        "20424": "beauty_consumer",
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

    # 투자산업과 KSIC 정보서비스 코드가 어긋나는 복합기업 회귀검증.
    yg = classify_dart_industry_detail("631", "YG PLUS", "037270")
    if yg.get("산업코드") != "media_entertainment" or yg.get("분류신뢰도", 0) < 95:
        errors.append(f"YG PLUS 산업분류 오류: {yg}")

    ambiguous_631 = classify_dart_industry_detail("631", "가상정보서비스", "999998")
    if ambiguous_631.get("산업코드") == "software_platform":
        errors.append(f"KSIC 631을 소프트웨어로 과잉분류: {ambiguous_631}")

    explicit_platform = classify_dart_industry_detail("631", "클라우드플랫폼", "999997")
    if explicit_platform.get("산업코드") != "software_platform":
        errors.append(f"명시적 플랫폼 기업 분류 오류: {explicit_platform}")

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
                "산업프로필버전": "3.0.1",
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
