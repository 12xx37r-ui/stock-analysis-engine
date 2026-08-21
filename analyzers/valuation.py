"""재무적정가 엔진 V6.7.0 · 가치평가 계약 v4 · 미래성장모형 v1.

핵심 원칙
- 현재가는 적정가 산식에 넣지 않고 계산 후 괴리 검증에만 사용한다.
- DART 누적 분기자료를 단독 분기로 변환해 TTM·정상화·FY1·FY2 EPS를 분리한다.
- KIS EPS는 미래이익 자체가 아니라 주식 수 교차검증과 보조자료로만 사용한다.
- 업종·기업 국면에 맞지 않는 PBR/잔여이익 하단모형이 성장가치를 끌어내리지 못하게 한다.
- 구형·불완전·비정상 결과는 최종값 사용을 차단한다.
- 단일 정답이 아니라 보수·기준·성장 시나리오와 자료/모형 신뢰도를 함께 반환한다.
"""

from typing import Any, Dict, List, Optional


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, "", "-", "--"):
            return default
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def growth_rate(current: float, previous: float) -> float:
    current = safe_float(current)
    previous = safe_float(previous)
    if previous == 0:
        return 0.0
    return ((current / abs(previous)) - (1.0 if previous > 0 else -1.0)) * 100.0


def weighted_average(rows: List[Dict[str, float]]) -> Optional[float]:
    valid = [
        row
        for row in rows
        if safe_float(row.get("value"), 0.0) > 0
        and safe_float(row.get("weight"), 0.0) > 0
    ]
    if not valid:
        return None
    total_weight = sum(safe_float(row.get("weight"), 0.0) for row in valid)
    if total_weight <= 0:
        return None
    return sum(
        safe_float(row.get("value"), 0.0)
        * safe_float(row.get("weight"), 0.0)
        for row in valid
    ) / total_weight


def weighted_average_signed(rows: List[Dict[str, float]]) -> Optional[float]:
    """손실연도도 정상화 이익에 반영하는 부호 허용 가중평균."""
    valid = [
        row
        for row in rows
        if safe_float(row.get("weight"), 0.0) > 0
        and row.get("value") not in (None, "", "-", "--")
    ]
    if not valid:
        return None
    total_weight = sum(safe_float(row.get("weight"), 0.0) for row in valid)
    if total_weight <= 0:
        return None
    return sum(
        safe_float(row.get("value"), 0.0)
        * safe_float(row.get("weight"), 0.0)
        for row in valid
    ) / total_weight


def percentile(values: List[float], ratio: float) -> Optional[float]:
    rows = sorted(value for value in values if value > 0)
    if not rows:
        return None
    if len(rows) == 1:
        return rows[0]
    position = clamp(ratio, 0.0, 1.0) * (len(rows) - 1)
    lower = int(position)
    upper = min(lower + 1, len(rows) - 1)
    fraction = position - lower
    return rows[lower] * (1.0 - fraction) + rows[upper] * fraction


def median(values: List[float]) -> Optional[float]:
    return percentile(values, 0.5)


# 동일한 재무지표라도 업종마다 정상 배수와 신뢰해야 할 모형이 다르다.
# 배수는 정답이 아니라 출발점이며 ROE·마진·성장·산업신호로 동적 조정된다.
VALUATION_PROFILES: Dict[str, Dict[str, Any]] = {
    "general": {
        "label": "일반기업 적응형",
        "base_per": 10.5, "per_min": 7.0, "per_max": 26.0,
        "base_pbr": 0.95, "pbr_min": 0.55, "pbr_max": 3.20,
        "weights": {"per": 0.38, "pbr": 0.20, "residual": 0.20, "transition": 0.22},
        "eps_floor": 0.78, "eps_cap": 1.65,
        "downside": 0.72, "upside": 1.32,
        "model_floor": 0.38, "model_ceiling": 2.70,
        "cyclical": False, "growth": False,
    },
    "semiconductor": {
        "label": "반도체·메모리 사이클",
        "base_per": 12.0, "per_min": 8.0, "per_max": 30.0,
        "base_pbr": 1.05, "pbr_min": 0.65, "pbr_max": 3.40,
        "weights": {"per": 0.45, "pbr": 0.12, "residual": 0.13, "transition": 0.30},
        "eps_floor": 0.72, "eps_cap": 1.80,
        "downside": 0.65, "upside": 1.45,
        "model_floor": 0.30, "model_ceiling": 3.20,
        "cyclical": True, "growth": True,
    },
    "electronic_components": {
        "label": "전자부품·MLCC·패키지기판 성장형",
        "base_per": 15.0, "per_min": 9.0, "per_max": 28.0,
        "base_pbr": 1.45, "pbr_min": 0.75, "pbr_max": 4.20,
        "weights": {"per": 0.42, "pbr": 0.16, "residual": 0.14, "transition": 0.28},
        "eps_floor": 0.72, "eps_cap": 1.85,
        "downside": 0.64, "upside": 1.52,
        "model_floor": 0.30, "model_ceiling": 3.30,
        "cyclical": True, "growth": True,
    },
    "automotive": {
        "label": "자동차·부품",
        "base_per": 8.5, "per_min": 5.5, "per_max": 17.0,
        "base_pbr": 0.80, "pbr_min": 0.45, "pbr_max": 2.20,
        "weights": {"per": 0.36, "pbr": 0.25, "residual": 0.24, "transition": 0.15},
        "eps_floor": 0.78, "eps_cap": 1.45,
        "downside": 0.72, "upside": 1.28,
        "model_floor": 0.42, "model_ceiling": 2.40,
        "cyclical": True, "growth": False,
    },
    "battery": {
        "label": "2차전지 성장·사이클",
        "base_per": 16.0, "per_min": 8.0, "per_max": 34.0,
        "base_pbr": 1.45, "pbr_min": 0.75, "pbr_max": 4.80,
        "weights": {"per": 0.32, "pbr": 0.30, "residual": 0.12, "transition": 0.26},
        "eps_floor": 0.68, "eps_cap": 1.85,
        "downside": 0.60, "upside": 1.55,
        "model_floor": 0.28, "model_ceiling": 3.40,
        "cyclical": True, "growth": True,
    },
    "biotechnology": {
        "label": "바이오 성장형",
        "base_per": 20.0, "per_min": 10.0, "per_max": 42.0,
        "base_pbr": 1.80, "pbr_min": 0.85, "pbr_max": 6.00,
        "weights": {"per": 0.30, "pbr": 0.31, "residual": 0.10, "transition": 0.29},
        "eps_floor": 0.60, "eps_cap": 1.90,
        "downside": 0.55, "upside": 1.65,
        "model_floor": 0.25, "model_ceiling": 3.80,
        "cyclical": False, "growth": True,
    },
    "pharmaceutical": {
        "label": "제약·의약품",
        "base_per": 16.0, "per_min": 9.0, "per_max": 34.0,
        "base_pbr": 1.45, "pbr_min": 0.75, "pbr_max": 4.50,
        "weights": {"per": 0.38, "pbr": 0.24, "residual": 0.16, "transition": 0.22},
        "eps_floor": 0.70, "eps_cap": 1.75,
        "downside": 0.64, "upside": 1.48,
        "model_floor": 0.30, "model_ceiling": 3.20,
        "cyclical": False, "growth": True,
    },
    "shipbuilding": {
        # 산업재와 동일한 보수적 배수/가중치를 사용하되 산업 식별만 분리한다.
        # 별도 OOS 검증 전까지 조선업에 임의 프리미엄을 주지 않는다.
        "label": "조선·해양·선박 수주사이클",
        "base_per": 11.0, "per_min": 6.5, "per_max": 24.0,
        "base_pbr": 1.05, "pbr_min": 0.50, "pbr_max": 3.20,
        "weights": {"per": 0.37, "pbr": 0.23, "residual": 0.22, "transition": 0.18},
        "eps_floor": 0.74, "eps_cap": 1.55,
        "downside": 0.68, "upside": 1.35,
        "model_floor": 0.38, "model_ceiling": 2.60,
        "cyclical": True, "growth": False,
    },
    "construction": {
        "label": "건설·플랜트 수주형",
        "base_per": 7.5, "per_min": 4.5, "per_max": 15.0,
        "base_pbr": 0.72, "pbr_min": 0.35, "pbr_max": 1.80,
        "weights": {"per": 0.30, "pbr": 0.31, "residual": 0.25, "transition": 0.14},
        "eps_floor": 0.72, "eps_cap": 1.40,
        "downside": 0.67, "upside": 1.27,
        "model_floor": 0.42, "model_ceiling": 2.30,
        "cyclical": True, "growth": False,
    },
    "finance": {
        "label": "은행·금융지주 잔여이익형",
        "base_per": 7.5, "per_min": 4.5, "per_max": 14.0,
        "base_pbr": 0.72, "pbr_min": 0.35, "pbr_max": 1.75,
        "weights": {"per": 0.20, "pbr": 0.41, "residual": 0.30, "transition": 0.09},
        "eps_floor": 0.82, "eps_cap": 1.35,
        "downside": 0.78, "upside": 1.20,
        "model_floor": 0.52, "model_ceiling": 1.95,
        "cyclical": False, "growth": False,
    },
    "insurance": {
        "label": "보험 자본가치형",
        "base_per": 8.0, "per_min": 5.0, "per_max": 15.0,
        "base_pbr": 0.68, "pbr_min": 0.35, "pbr_max": 1.65,
        "weights": {"per": 0.20, "pbr": 0.43, "residual": 0.29, "transition": 0.08},
        "eps_floor": 0.80, "eps_cap": 1.35,
        "downside": 0.76, "upside": 1.22,
        "model_floor": 0.50, "model_ceiling": 2.00,
        "cyclical": False, "growth": False,
    },
    "consumer_staples": {
        "label": "필수소비재 안정형",
        "base_per": 14.0, "per_min": 9.0, "per_max": 27.0,
        "base_pbr": 1.35, "pbr_min": 0.75, "pbr_max": 4.00,
        "weights": {"per": 0.40, "pbr": 0.19, "residual": 0.24, "transition": 0.17},
        "eps_floor": 0.84, "eps_cap": 1.45,
        "downside": 0.80, "upside": 1.23,
        "model_floor": 0.48, "model_ceiling": 2.15,
        "cyclical": False, "growth": False,
    },
    "beauty_consumer": {
        "label": "화장품·생활용품 브랜드 소비재",
        "base_per": 17.0, "per_min": 10.0, "per_max": 34.0,
        "base_pbr": 1.65, "pbr_min": 0.80, "pbr_max": 5.00,
        "weights": {"per": 0.34, "pbr": 0.26, "residual": 0.18, "transition": 0.22},
        "eps_floor": 0.72, "eps_cap": 1.75,
        "downside": 0.68, "upside": 1.48,
        "model_floor": 0.34, "model_ceiling": 2.90,
        "cyclical": False, "growth": True,
    },
    "consumer_discretionary": {
        "label": "경기소비재",
        "base_per": 12.0, "per_min": 7.0, "per_max": 28.0,
        "base_pbr": 1.15, "pbr_min": 0.55, "pbr_max": 4.00,
        "weights": {"per": 0.39, "pbr": 0.21, "residual": 0.18, "transition": 0.22},
        "eps_floor": 0.70, "eps_cap": 1.65,
        "downside": 0.66, "upside": 1.42,
        "model_floor": 0.34, "model_ceiling": 2.90,
        "cyclical": True, "growth": False,
    },
    "retail": {
        "label": "유통·소매",
        "base_per": 11.0, "per_min": 6.0, "per_max": 23.0,
        "base_pbr": 0.95, "pbr_min": 0.45, "pbr_max": 3.00,
        "weights": {"per": 0.38, "pbr": 0.24, "residual": 0.22, "transition": 0.16},
        "eps_floor": 0.74, "eps_cap": 1.50,
        "downside": 0.70, "upside": 1.32,
        "model_floor": 0.40, "model_ceiling": 2.55,
        "cyclical": True, "growth": False,
    },
    "media_entertainment": {
        "label": "미디어·엔터테인먼트·콘텐츠 성장형",
        "base_per": 18.0, "per_min": 9.0, "per_max": 38.0,
        "base_pbr": 1.45, "pbr_min": 0.65, "pbr_max": 5.00,
        "weights": {"per": 0.40, "pbr": 0.20, "residual": 0.12, "transition": 0.28},
        "eps_floor": 0.62, "eps_cap": 1.85,
        "downside": 0.58, "upside": 1.58,
        "model_floor": 0.27, "model_ceiling": 3.50,
        "cyclical": False, "growth": True,
    },
    "software_platform": {
        "label": "소프트웨어·플랫폼 성장형",
        "base_per": 21.0, "per_min": 11.0, "per_max": 42.0,
        "base_pbr": 1.70, "pbr_min": 0.80, "pbr_max": 6.00,
        "weights": {"per": 0.42, "pbr": 0.18, "residual": 0.11, "transition": 0.29},
        "eps_floor": 0.65, "eps_cap": 1.90,
        "downside": 0.58, "upside": 1.62,
        "model_floor": 0.25, "model_ceiling": 3.70,
        "cyclical": False, "growth": True,
    },
    "telecom": {
        "label": "통신 현금흐름 안정형",
        "base_per": 9.0, "per_min": 6.0, "per_max": 17.0,
        "base_pbr": 0.82, "pbr_min": 0.45, "pbr_max": 2.00,
        "weights": {"per": 0.34, "pbr": 0.25, "residual": 0.30, "transition": 0.11},
        "eps_floor": 0.84, "eps_cap": 1.35,
        "downside": 0.80, "upside": 1.20,
        "model_floor": 0.52, "model_ceiling": 1.95,
        "cyclical": False, "growth": False,
    },
    "utilities": {
        "label": "전력·가스·환경 유틸리티",
        "base_per": 8.5, "per_min": 5.0, "per_max": 16.0,
        "base_pbr": 0.72, "pbr_min": 0.35, "pbr_max": 1.80,
        "weights": {"per": 0.29, "pbr": 0.30, "residual": 0.31, "transition": 0.10},
        "eps_floor": 0.80, "eps_cap": 1.35,
        "downside": 0.76, "upside": 1.22,
        "model_floor": 0.50, "model_ceiling": 2.00,
        "cyclical": False, "growth": False,
    },
    "materials": {
        "label": "화학·철강·소재 사이클",
        "base_per": 8.5, "per_min": 5.0, "per_max": 18.0,
        "base_pbr": 0.80, "pbr_min": 0.40, "pbr_max": 2.40,
        "weights": {"per": 0.34, "pbr": 0.27, "residual": 0.22, "transition": 0.17},
        "eps_floor": 0.68, "eps_cap": 1.50,
        "downside": 0.62, "upside": 1.36,
        "model_floor": 0.36, "model_ceiling": 2.65,
        "cyclical": True, "growth": False,
    },
    "industrial": {
        "label": "산업재·기계·전기장비",
        "base_per": 11.0, "per_min": 6.5, "per_max": 24.0,
        "base_pbr": 1.05, "pbr_min": 0.50, "pbr_max": 3.20,
        "weights": {"per": 0.37, "pbr": 0.23, "residual": 0.22, "transition": 0.18},
        "eps_floor": 0.74, "eps_cap": 1.55,
        "downside": 0.68, "upside": 1.35,
        "model_floor": 0.38, "model_ceiling": 2.60,
        "cyclical": True, "growth": False,
    },
    "transportation": {
        "label": "운송·물류 사이클",
        "base_per": 9.0, "per_min": 5.0, "per_max": 20.0,
        "base_pbr": 0.85, "pbr_min": 0.40, "pbr_max": 2.50,
        "weights": {"per": 0.35, "pbr": 0.25, "residual": 0.24, "transition": 0.16},
        "eps_floor": 0.65, "eps_cap": 1.50,
        "downside": 0.60, "upside": 1.38,
        "model_floor": 0.34, "model_ceiling": 2.75,
        "cyclical": True, "growth": False,
    },
    "real_estate": {
        "label": "부동산·임대 자산가치형",
        "base_per": 9.0, "per_min": 5.0, "per_max": 18.0,
        "base_pbr": 0.72, "pbr_min": 0.30, "pbr_max": 1.65,
        "weights": {"per": 0.16, "pbr": 0.46, "residual": 0.29, "transition": 0.09},
        "eps_floor": 0.76, "eps_cap": 1.35,
        "downside": 0.72, "upside": 1.25,
        "model_floor": 0.48, "model_ceiling": 2.05,
        "cyclical": True, "growth": False,
    },
    "medical_devices": {
        # 의료기기/헬스테크는 성장성은 반영하되 바이오 임상가치 프리미엄을 직접 적용하지 않는다.
        "label": "의료기기·헬스테크 성장형",
        "base_per": 15.0, "per_min": 9.0, "per_max": 30.0,
        "base_pbr": 1.35, "pbr_min": 0.70, "pbr_max": 4.00,
        "weights": {"per": 0.38, "pbr": 0.22, "residual": 0.22, "transition": 0.18},
        "eps_floor": 0.78, "eps_cap": 1.60,
        "downside": 0.72, "upside": 1.38,
        "model_floor": 0.38, "model_ceiling": 2.70,
        "cyclical": False, "growth": True,
    },
    "healthcare": {
        "label": "의료서비스",
        "base_per": 15.0, "per_min": 9.0, "per_max": 30.0,
        "base_pbr": 1.35, "pbr_min": 0.70, "pbr_max": 4.00,
        "weights": {"per": 0.38, "pbr": 0.22, "residual": 0.22, "transition": 0.18},
        "eps_floor": 0.78, "eps_cap": 1.60,
        "downside": 0.72, "upside": 1.38,
        "model_floor": 0.38, "model_ceiling": 2.70,
        "cyclical": False, "growth": True,
    },
    "energy": {
        "label": "에너지·자원 사이클",
        "base_per": 8.5, "per_min": 4.5, "per_max": 18.0,
        "base_pbr": 0.80, "pbr_min": 0.35, "pbr_max": 2.30,
        "weights": {"per": 0.34, "pbr": 0.27, "residual": 0.23, "transition": 0.16},
        "eps_floor": 0.60, "eps_cap": 1.50,
        "downside": 0.56, "upside": 1.42,
        "model_floor": 0.32, "model_ceiling": 2.90,
        "cyclical": True, "growth": False,
    },
    "holding_company": {
        "label": "지주회사 자산가치형",
        "base_per": 7.5, "per_min": 4.5, "per_max": 16.0,
        "base_pbr": 0.60, "pbr_min": 0.25, "pbr_max": 1.40,
        "weights": {"per": 0.15, "pbr": 0.49, "residual": 0.28, "transition": 0.08},
        "eps_floor": 0.75, "eps_cap": 1.30,
        "downside": 0.72, "upside": 1.20,
        "model_floor": 0.50, "model_ceiling": 1.95,
        "cyclical": False, "growth": False,
    },
    "services": {
        "label": "서비스업 적응형",
        "base_per": 13.0, "per_min": 7.0, "per_max": 30.0,
        "base_pbr": 1.15, "pbr_min": 0.55, "pbr_max": 4.00,
        "weights": {"per": 0.39, "pbr": 0.21, "residual": 0.18, "transition": 0.22},
        "eps_floor": 0.70, "eps_cap": 1.70,
        "downside": 0.66, "upside": 1.44,
        "model_floor": 0.34, "model_ceiling": 2.95,
        "cyclical": False, "growth": True,
    },
}



PROFILE_ALIASES = {
    "none": "general",
    "auto": "general",
    "": "general",
}

VALUATION_CONTRACT_VERSION = "4.0"
VALUATION_ENGINE_VERSION = "6.8.0-valuation-contract-v4"
INDUSTRY_PROFILE_VERSION = "3.1.0"
DATA_QUALIFICATION_VERSION = "1.1.0"
VALUATION_MODEL_REVISION = "future-growth-v1.1.0-price-independent"
FUTURE_GROWTH_MODEL_VERSION = "1.1.0"
ASSET_CYCLE_ANCHOR_VERSION = "1.0.0"

# 장부가치·잔여이익이 의미 있는 자산집약 업종에서 일시적인 이익 훼손이
# PER 계열 가치만 과도하게 낮출 때 사용하는 가격독립 보정 대상.
# 종목명이나 현재가를 기준으로 예외처리하지 않는다.
ASSET_CYCLE_PROFILES = {
    "construction",
    "shipbuilding",
    "automotive",
    "materials",
    "industrial",
    "transportation",
    "energy",
    "utilities",
    "real_estate",
    "holding_company",
}

# 현재가를 사용하지 않는 FY3~FY4 미래이익 현재가치 모형.
# 업종별 상한과 감쇠율을 두어 한 분기 급증을 장기간 직선 외삽하지 않는다.
FUTURE_GROWTH_CONFIG: Dict[str, Dict[str, float]] = {
    "semiconductor": {"weight": 0.18, "fy3_cap": 0.20, "fy4_cap": 0.13, "exit_premium": 1.5, "eps_cap": 1.85, "value_cap": 1.55, "min_growth": 0.04},
    "electronic_components": {"weight": 0.22, "fy3_cap": 0.24, "fy4_cap": 0.16, "exit_premium": 2.0, "eps_cap": 2.00, "value_cap": 1.65, "min_growth": 0.05},
    "battery": {"weight": 0.20, "fy3_cap": 0.24, "fy4_cap": 0.16, "exit_premium": 2.0, "eps_cap": 2.10, "value_cap": 1.70, "min_growth": 0.04},
    "biotechnology": {"weight": 0.18, "fy3_cap": 0.26, "fy4_cap": 0.18, "exit_premium": 2.5, "eps_cap": 2.30, "value_cap": 1.85, "min_growth": 0.05},
    "medical_devices": {"weight": 0.16, "fy3_cap": 0.22, "fy4_cap": 0.14, "exit_premium": 1.8, "eps_cap": 1.95, "value_cap": 1.60, "min_growth": 0.04},
    "pharmaceutical": {"weight": 0.16, "fy3_cap": 0.20, "fy4_cap": 0.14, "exit_premium": 1.8, "eps_cap": 1.90, "value_cap": 1.60, "min_growth": 0.04},
    "media_entertainment": {"weight": 0.18, "fy3_cap": 0.24, "fy4_cap": 0.16, "exit_premium": 2.2, "eps_cap": 2.10, "value_cap": 1.75, "min_growth": 0.05},
    "software_platform": {"weight": 0.20, "fy3_cap": 0.28, "fy4_cap": 0.18, "exit_premium": 2.8, "eps_cap": 2.40, "value_cap": 1.95, "min_growth": 0.06},
    "beauty_consumer": {"weight": 0.18, "fy3_cap": 0.18, "fy4_cap": 0.12, "exit_premium": 2.5, "eps_cap": 1.85, "value_cap": 1.70, "min_growth": 0.03},
    "services": {"weight": 0.14, "fy3_cap": 0.18, "fy4_cap": 0.12, "exit_premium": 1.5, "eps_cap": 1.80, "value_cap": 1.50, "min_growth": 0.04},
}

# 복합기업은 사업부 세부 공시가 자동 수집되지 않으면 진짜 SOTP를 만들 수 없다.
# 아래 설정의 대용가치는 진짜 SOTP가 아니므로 진단용으로만 계산한다. 최종 기준가에는 직접 반영하지 않는다.
COMPLEX_COMPANY_CONFIG: Dict[str, Dict[str, Any]] = {
    "005930": {
        "label": "삼성전자 복합기술기업 대용 가치합산",
        "profile": "semiconductor",
        "base_multiple": 17.5,
        "min_multiple": 13.0,
        "max_multiple": 22.0,
        "earnings_weight": 0.58,
        "complex_weight": 0.24,
        "asset_weight": 0.06,
        "residual_weight": 0.06,
        "fcf_weight": 0.06,
    },
}

REPORT_QUARTER = {
    "11013": 1,
    "11012": 2,
    "11014": 3,
    "11011": 4,
}

FLOW_METRICS = (
    "매출",
    "영업이익",
    "순이익",
    "영업현금흐름",
    "유형자산취득",
    "무형자산취득",
    "설비투자추정",
    "잉여현금흐름추정",
)

BALANCE_METRICS = (
    "자산총계",
    "부채총계",
    "자본총계",
    "현금및현금성자산",
    "총차입금",
)


def get_periods(fundamentals_bundle: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    bundle = safe_dict(fundamentals_bundle)
    periods = safe_list(safe_dict(bundle.get("재무기간")).get("기간목록"))
    valid = [
        item
        for item in periods
        if isinstance(item, dict) and item.get("수집상태") == "정상"
    ]
    valid.sort(
        key=lambda item: (
            int(safe_float(item.get("사업연도"), 0)),
            REPORT_QUARTER.get(str(item.get("보고서코드", "")), 0),
        ),
        reverse=True,
    )
    return valid


def get_period_metrics(period: Dict[str, Any]) -> Dict[str, Any]:
    return safe_dict(period.get("지표"))


def find_same_report_prior_year(
    latest: Dict[str, Any],
    periods: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    target_year = int(safe_float(latest.get("사업연도"), 0)) - 1
    target_code = str(latest.get("보고서코드", "")).strip()
    for period in periods:
        if (
            int(safe_float(period.get("사업연도"), 0)) == target_year
            and str(period.get("보고서코드", "")).strip() == target_code
        ):
            return period
    return None


def _subtract_metric(current: Dict[str, Any], previous: Dict[str, Any], key: str) -> Optional[float]:
    current_value = safe_float(current.get(key), float("nan"))
    previous_value = safe_float(previous.get(key), float("nan"))
    if current_value != current_value or previous_value != previous_value:
        return None
    return current_value - previous_value


def build_standalone_quarters(periods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """OpenDART 누적 손익/현금흐름을 실제 단독 분기로 변환한다."""
    by_year: Dict[int, Dict[int, Dict[str, Any]]] = {}
    for period in periods:
        year = int(safe_float(period.get("사업연도"), 0))
        quarter = REPORT_QUARTER.get(str(period.get("보고서코드", "")), 0)
        if not year or not quarter:
            continue
        by_year.setdefault(year, {})[quarter] = get_period_metrics(period)

    rows: List[Dict[str, Any]] = []
    for year, cumulative in by_year.items():
        for quarter in range(1, 5):
            current = cumulative.get(quarter)
            if not current:
                continue
            previous = cumulative.get(quarter - 1) if quarter > 1 else None
            metrics: Dict[str, Any] = {}
            for key in FLOW_METRICS:
                if quarter == 1:
                    metrics[key] = safe_float(current.get(key), 0.0)
                elif previous:
                    value = _subtract_metric(current, previous, key)
                    metrics[key] = value if value is not None else 0.0
                else:
                    metrics[key] = 0.0
            for key in BALANCE_METRICS:
                metrics[key] = safe_float(current.get(key), 0.0)
            rows.append({
                "사업연도": year,
                "분기": quarter,
                "기간키": year * 4 + quarter,
                "지표": metrics,
                "단독분기변환": quarter == 1 or previous is not None,
            })
    rows.sort(key=lambda row: row["기간키"], reverse=True)
    return rows


def build_ttm(
    quarters: List[Dict[str, Any]],
    profile_code: str = "general",
) -> Dict[str, Any]:
    if len(quarters) < 4:
        return {"available": False, "quality": 0, "metrics": {}, "period": ""}
    selected = quarters[:4]
    keys = [int(row.get("기간키", 0)) for row in selected]
    contiguous = all(keys[index] - keys[index + 1] == 1 for index in range(3))
    converted = all(bool(row.get("단독분기변환")) for row in selected)
    financial_profile = profile_code in {"finance", "insurance"}
    positive_revenue = all(
        safe_float(safe_dict(row.get("지표")).get("매출")) > 0
        for row in selected
    )
    net_income_present = any(
        abs(safe_float(safe_dict(row.get("지표")).get("순이익"))) > 0
        for row in selected
    )
    revenue_usable = positive_revenue or (financial_profile and net_income_present)
    if not contiguous or not converted or not revenue_usable:
        return {
            "available": False,
            "quality": 20 if contiguous else 10,
            "metrics": {},
            "period": "",
            "reason": (
                "단독분기 변환 불완전" if not converted
                else "분기 핵심 손익자료 불완전" if not revenue_usable
                else "연속 4개 분기 불연속"
            ),
        }
    metrics: Dict[str, float] = {}
    for key in FLOW_METRICS:
        metrics[key] = sum(safe_float(safe_dict(row.get("지표")).get(key)) for row in selected)
    latest_metrics = safe_dict(selected[0].get("지표"))
    for key in BALANCE_METRICS:
        metrics[key] = safe_float(latest_metrics.get(key))
    first = selected[-1]
    last = selected[0]
    period = f"{first.get('사업연도')}Q{first.get('분기')}~{last.get('사업연도')}Q{last.get('분기')}"
    quality = 95 if positive_revenue else 84
    return {
        "available": True,
        "quality": quality,
        "metrics": metrics,
        "period": period,
        "금융업매출대체허용": bool(financial_profile and not positive_revenue),
    }


def annual_periods(periods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = [
        period for period in periods
        if str(period.get("보고서코드", "")) == "11011"
    ]
    rows.sort(key=lambda row: int(safe_float(row.get("사업연도"), 0)), reverse=True)
    return rows


def _recursive_positive(source: Any, keys: set, depth: int = 3) -> Optional[float]:
    if depth < 0 or not isinstance(source, dict):
        return None
    for key, value in source.items():
        if str(key) in keys:
            parsed = safe_float(value, 0.0)
            if parsed > 0:
                return parsed
    for value in source.values():
        if isinstance(value, dict):
            parsed = _recursive_positive(value, keys, depth - 1)
            if parsed and parsed > 0:
                return parsed
    return None


def infer_share_count(
    market: Dict[str, Any],
    periods: List[Dict[str, Any]],
    company_info: Dict[str, Any],
    fundamentals_bundle: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    candidates: List[Dict[str, Any]] = []
    fundamentals_bundle = safe_dict(fundamentals_bundle)

    # OpenDART 주식의 총수 현황을 최우선으로 사용한다. 유통주식수는
    # 자기주식을 제외하므로 EPS·BPS의 주당가치 계산에 가장 적합하다.
    stock_total = safe_dict(fundamentals_bundle.get("주식총수"))
    dart_shares = (
        safe_float(stock_total.get("가치평가주식수"))
        or safe_float(stock_total.get("유통주식수"))
        or safe_float(stock_total.get("발행주식수"))
    )
    if dart_shares >= 100_000:
        candidates.append({
            "value": dart_shares,
            "source": "OpenDART 주식의 총수 현황",
            "quality": 100,
        })

    explicit = _recursive_positive(
        company_info,
        {"가치평가주식수", "발행주식수", "발행주식총수", "상장주식수", "유통주식수", "보통주식수", "shares"},
    ) or _recursive_positive(
        market,
        {"가치평가주식수", "발행주식수", "발행주식총수", "상장주식수", "유통주식수", "보통주식수", "shares"},
    )
    if explicit and explicit > 100000:
        candidates.append({"value": explicit, "source": "직접 발행주식수", "quality": 96})

    # KIS EPS·BPS는 제공처에 따라 현재가/PER, 현재가/PBR로
    # 역산될 수 있다. 이 값으로 주식수를 추정하면 현재가가
    # 주당 재무가치에 간접 유입될 수 있으므로 후보에서 제외한다.
    # 현재가·시가총액·시장 주당지표는 적정가 산식과 주식수 결정에
    # 사용하지 않는다.
    # OpenDART 유통주식수가 있으면 이를 단일 기준값으로 채택하고 다른 후보는
    # 교차검증에만 사용한다. 이 원칙으로 시장가격 변화가 EPS와 적정가를
    # 역으로 움직이는 숨은 가격의존성을 제거한다.
    if not candidates:
        return {"value": 0.0, "source": "미확보", "quality": 0, "candidates": []}

    dart_candidate = next(
        (row for row in candidates if row["source"] == "OpenDART 주식의 총수 현황"),
        None,
    )
    if dart_candidate:
        cross_checks = [
            row for row in candidates
            if row is not dart_candidate and 0.70 <= row["value"] / dart_candidate["value"] <= 1.30
        ]
        quality = 100 if len(cross_checks) >= 1 else 94
        return {
            "value": dart_candidate["value"],
            "source": "OpenDART 주식의 총수 현황",
            "quality": quality,
            "candidates": [{"출처": row["source"], "주식수": round(row["value"])} for row in candidates],
            "결정원칙": "현재가·시가총액 미사용, OpenDART 유통주식수 우선",
        }

    values = sorted(row["value"] for row in candidates)
    center = median(values) or values[0]
    consistent = [row for row in candidates if 0.70 <= row["value"] / center <= 1.30]
    selected = consistent or sorted(candidates, key=lambda row: row["quality"], reverse=True)[:1]
    total_quality = sum(row["quality"] for row in selected)
    value = sum(row["value"] * row["quality"] for row in selected) / max(total_quality, 1)
    quality = min(92, int(sum(row["quality"] for row in selected) / len(selected)))
    return {
        "value": value,
        "source": "+".join(row["source"] for row in selected),
        "quality": quality,
        "candidates": [{"출처": row["source"], "주식수": round(row["value"])} for row in candidates],
        "결정원칙": "현재가·시가총액 미사용, 재무 주당지표 교차추정",
    }


def quarter_signal(periods: List[Dict[str, Any]]) -> Dict[str, Any]:
    quarters = [
        row for row in build_standalone_quarters(periods)
        if bool(row.get("단독분기변환"))
        and safe_float(safe_dict(row.get("지표")).get("매출")) > 0
    ]
    if not quarters:
        return {
            "latest_revenue": 0.0,
            "latest_operating_income": 0.0,
            "latest_net_income": 0.0,
            "revenue_yoy": 0.0,
            "operating_yoy": 0.0,
            "net_yoy": 0.0,
            "signal": 0.0,
            "quality": 0,
            "latest_period": "",
        }
    latest = quarters[0]
    previous = next(
        (
            row for row in quarters
            if row.get("사업연도") == latest.get("사업연도") - 1
            and row.get("분기") == latest.get("분기")
        ),
        None,
    )
    latest_metrics = safe_dict(latest.get("지표"))
    previous_metrics = safe_dict(previous.get("지표")) if previous else {}
    latest_revenue = safe_float(latest_metrics.get("매출"))
    latest_operating_income = safe_float(latest_metrics.get("영업이익"))
    latest_net_income = safe_float(latest_metrics.get("순이익"))
    revenue_yoy = growth_rate(latest_revenue, safe_float(previous_metrics.get("매출"))) if previous else 0.0
    operating_yoy = growth_rate(latest_operating_income, safe_float(previous_metrics.get("영업이익"))) if previous else 0.0
    net_yoy = growth_rate(latest_net_income, safe_float(previous_metrics.get("순이익"))) if previous else 0.0
    signal = (
        clamp(revenue_yoy / 40.0, -1.0, 1.0) * 20.0
        + clamp(operating_yoy / 60.0, -1.0, 1.0) * 45.0
        + clamp(net_yoy / 80.0, -1.0, 1.0) * 35.0
    )
    return {
        "latest_revenue": latest_revenue,
        "latest_operating_income": latest_operating_income,
        "latest_net_income": latest_net_income,
        "revenue_yoy": revenue_yoy,
        "operating_yoy": operating_yoy,
        "net_yoy": net_yoy,
        "signal": clamp(signal, -100.0, 100.0),
        "quality": 90 if previous else 45,
        "latest_period": f"{latest.get('사업연도')}Q{latest.get('분기')}",
    }


def resolve_profile_code(company_info: Dict[str, Any], industry_bundle: Dict[str, Any]) -> str:
    stock_code = str(company_info.get("종목코드") or company_info.get("KIS종목코드") or "").zfill(6)
    complex_config = COMPLEX_COMPANY_CONFIG.get(stock_code)
    if complex_config:
        return str(complex_config.get("profile", "semiconductor"))
    candidates = [
        company_info.get("가치평가산업코드"),
        company_info.get("산업코드"),
        industry_bundle.get("산업코드"),
    ]
    for candidate in candidates:
        code = str(candidate or "").strip().lower()
        if not code:
            continue
        code = PROFILE_ALIASES.get(code, code)
        if code in VALUATION_PROFILES:
            return code
    return "general"


def industry_signal(industry_analysis: Dict[str, Any]) -> Dict[str, Any]:
    analysis = safe_dict(industry_analysis)
    mid = safe_dict(analysis.get("중기산업선행"))
    long_term = safe_dict(analysis.get("장기산업사이클"))
    mid_signal = safe_float(mid.get("신호"), 0.0)
    long_signal = safe_float(long_term.get("신호"), 0.0)
    mid_quality = safe_float(mid.get("데이터품질"), 0.0)
    long_quality = safe_float(long_term.get("데이터품질"), 0.0)
    available = analysis.get("분석상태") == "정상" and (mid_quality > 0 or long_quality > 0)
    combined = (mid_signal * 0.35 + long_signal * 0.65) if available else 0.0
    quality = (mid_quality * 0.35 + long_quality * 0.65) if available else 0.0
    return {
        "available": available,
        "signal": clamp(combined, -100.0, 100.0),
        "quality": clamp(quality, 0.0, 100.0),
        "mid": mid_signal,
        "long": long_signal,
        "phase": str(analysis.get("산업국면", "")).strip(),
    }


def _weighted_positive(values: List[Dict[str, float]]) -> float:
    return weighted_average([row for row in values if safe_float(row.get("value")) > 0]) or 0.0


def _annual_eps_series(periods: List[Dict[str, Any]], shares: float) -> List[Dict[str, Any]]:
    if shares <= 0:
        return []
    rows = []
    for period in annual_periods(periods)[:4]:
        metrics = get_period_metrics(period)
        if metrics.get("순이익") in (None, "", "-", "--"):
            continue
        net_income = safe_float(metrics.get("순이익"))
        rows.append({
            "year": int(safe_float(period.get("사업연도"), 0)),
            "eps": net_income / shares,
            "net_income": net_income,
        })
    return rows


def _signed_median(values: List[float]) -> float:
    rows = sorted(
        safe_float(value)
        for value in values
        if value not in (None, "", "-", "--")
    )
    if not rows:
        return 0.0
    n = len(rows)
    if n % 2 == 1:
        return rows[n // 2]
    return (rows[n // 2 - 1] + rows[n // 2]) / 2.0


def _normalized_eps(annual_eps: List[Dict[str, Any]], market_eps: float = 0.0) -> float:
    weights = (0.52, 0.30, 0.18, 0.10)
    selected = annual_eps[:4]
    rows = [
        {"value": row.get("eps", 0.0), "weight": weights[index]}
        for index, row in enumerate(selected)
    ]
    weighted = weighted_average_signed(rows) or 0.0

    # 최근 한 해만 확보된 경우는 그 값을 그대로 사용한다.
    # 2~4개 연간자료가 있으면 경기저점/고점 한 해에 과도하게 끌려가지 않도록
    # 부호를 보존한 중앙값을 30% 섞는다. 현재가/시장 PER은 사용하지 않는다.
    if len(selected) >= 2:
        med = _signed_median([row.get("eps", 0.0) for row in selected])
        normalized = weighted * 0.70 + med * 0.30
    else:
        normalized = weighted

    return normalized


def _cost_of_equity(debt_ratio: float, profile_code: str) -> float:
    base = 0.095
    if profile_code in {"finance", "insurance", "utilities", "telecom"}:
        base -= 0.005
    if profile_code not in {"finance", "insurance"}:
        if debt_ratio > 2.0:
            base += 0.020
        elif debt_ratio > 1.0:
            base += 0.010
    return clamp(base, 0.085, 0.125)


def _annualize_two_year_growth(total_growth: float) -> float:
    """최근 3개 연간값의 2년 누적성장률을 연율로 환산한다."""
    total_growth = clamp(safe_float(total_growth), -0.95, 4.0)
    return (1.0 + total_growth) ** 0.5 - 1.0


def build_future_growth_model(
    *,
    profile_code: str,
    profile: Dict[str, Any],
    ttm_eps: float,
    normalized_eps: float,
    fy1_eps: float,
    fy2_eps: float,
    fy1_growth: float,
    fy2_growth: float,
    quarter: Dict[str, Any],
    revenue_growth_3y: float,
    operating_growth_3y: float,
    net_growth_3y: float,
    earnings_signal: float,
    forward_signal: float,
    industry: Dict[str, Any],
    operating_margin: float,
    net_margin: float,
    target_per: float,
    per_max: float,
    cost_of_equity: float,
    share_quality: float,
    ttm_quality: float,
    structural_acceleration: bool,
    negative_transition: bool,
    earnings_trough: bool,
    earnings_value: float,
) -> Dict[str, Any]:
    """가격독립 FY3~FY4 미래가치 후보.

    v1.1 정책:
    - 데이터 자체가 부족한 경우만 hard block.
    - 성장업종인데 현재 실적/산업국면이 나쁜 경우에는 미래가치를 0으로 삭제하지 않는다.
    - 대신 제한사유를 남기고 모형 가중치(인정률)를 낮춘다.
    - 이후 Strategic 모듈에서 기업/산업/컨센서스 근거에 따라 미래증분 인정률을 한 번 더 적용한다.
    """
    config = safe_dict(FUTURE_GROWTH_CONFIG.get(profile_code))
    hard_blocked: List[str] = []
    limited: List[str] = []
    evidence: List[str] = []

    if not config or not profile.get("growth"):
        hard_blocked.append("미래성장모형 비대상 업종")

    # FY3/FY4 투영의 최소 입력. TTM 자체가 적자/0이어도 정상화·FY1·FY2가
    # 양수면 회복 시나리오는 계산할 수 있다.
    if max(ttm_eps, normalized_eps) <= 0 or fy1_eps <= 0 or fy2_eps <= 0:
        hard_blocked.append("양(+)의 정상화·FY1·FY2 EPS 최소입력 미확보")

    if safe_float(ttm_quality) < 70:
        hard_blocked.append("TTM 데이터품질 70점 미만")
    if safe_float(share_quality) < 75:
        hard_blocked.append("주식수 품질 75점 미만")

    # 아래 항목은 미래가치를 '0'으로 만들지 않고 인정률을 낮추는 조건이다.
    if ttm_eps <= 0:
        limited.append("TTM EPS 비양수 · 정상화/FY1/FY2 기준 제한투영")
    if negative_transition:
        limited.append("실적 급하락 전환")
    if earnings_trough:
        limited.append("이익저점 국면 · 회복가치 우선")
    if operating_margin <= 0.03 or net_margin <= 0.015:
        limited.append("영업·순이익률 성장모형 최소기준 미달")
    if safe_float(industry.get("long")) < -35.0:
        limited.append("장기 산업사이클 과도한 역풍")
    if (
        ttm_eps > 0
        and normalized_eps > 0
        and ttm_eps / normalized_eps > 2.8
        and profile.get("cyclical")
    ):
        limited.append("사이클 고점 이익 영구화 위험")

    strong_evidence = bool(
        structural_acceleration
        or (
            safe_float(quarter.get("revenue_yoy")) >= 8.0
            and safe_float(quarter.get("operating_yoy")) >= 25.0
            and safe_float(quarter.get("net_yoy")) >= 18.0
        )
        or (earnings_signal >= 35.0 and forward_signal >= 35.0)
    )
    if not strong_evidence:
        limited.append("구조적 성장 증거 부족")

    if structural_acceleration:
        evidence.append("매출·영업이익·순이익 동반 구조적 가속")
    if safe_float(quarter.get("revenue_yoy")) >= 8.0:
        evidence.append("최근 분기 매출 성장")
    if safe_float(quarter.get("operating_yoy")) >= 25.0:
        evidence.append("최근 분기 영업이익 고성장")
    if forward_signal >= 35.0:
        evidence.append("향후이익 방향 대용지표 강세")
    if safe_float(industry.get("long")) >= 20.0:
        evidence.append("장기 산업사이클 우호")

    if hard_blocked:
        return {
            "버전": FUTURE_GROWTH_MODEL_VERSION,
            "대상업종": bool(config and profile.get("growth")),
            "사용가능": False,
            "상태": "차단",
            "차단사유": list(dict.fromkeys(hard_blocked)),
            "제한사유": list(dict.fromkeys(limited)),
            "선정근거": list(dict.fromkeys(evidence)),
            "가치": 0.0,
            "가중치": 0.0,
            "모형인정률": 0.0,
            "품질": 0,
            "현재가미사용": True,
        }

    revenue_q = clamp(safe_float(quarter.get("revenue_yoy")) / 100.0, -0.15, 0.25)
    operating_q = clamp(safe_float(quarter.get("operating_yoy")) / 100.0, -0.20, 0.35)
    net_q = clamp(safe_float(quarter.get("net_yoy")) / 100.0, -0.20, 0.35)
    operating_ann = clamp(_annualize_two_year_growth(operating_growth_3y), -0.15, 0.25)
    net_ann = clamp(_annualize_two_year_growth(net_growth_3y), -0.15, 0.25)
    signal_growth = clamp(forward_signal / 100.0 * 0.15, -0.08, 0.15)
    industry_growth = clamp(safe_float(industry.get("long")) / 100.0 * 0.10, -0.06, 0.10)

    raw_fy3_growth = (
        fy2_growth * 0.24
        + fy1_growth * 0.12
        + revenue_q * 0.10
        + operating_q * 0.18
        + net_q * 0.12
        + operating_ann * 0.10
        + net_ann * 0.06
        + signal_growth * 0.05
        + industry_growth * 0.03
    )

    # 제한상태에서는 무조건 양(+) 성장률을 강제하지 않는다.
    soft_mode = bool(limited)
    fy3_floor = -0.03 if soft_mode else safe_float(config.get("min_growth"), 0.04)
    fy4_floor = -0.02 if soft_mode else safe_float(config.get("min_growth"), 0.04) * 0.70

    fy3_growth = clamp(
        raw_fy3_growth,
        fy3_floor,
        safe_float(config.get("fy3_cap"), 0.20),
    )
    long_anchor = clamp(
        operating_ann * 0.55 + net_ann * 0.45,
        -0.04 if soft_mode else 0.0,
        safe_float(config.get("fy4_cap"), 0.14),
    )
    fy4_growth = clamp(
        fy3_growth * 0.62
        + long_anchor * 0.18
        + industry_growth * 0.20,
        fy4_floor,
        safe_float(config.get("fy4_cap"), 0.14),
    )

    eps_anchor = max(ttm_eps, normalized_eps, fy1_eps, fy2_eps)
    fy3_eps = fy2_eps * (1.0 + fy3_growth)
    fy4_eps_raw = fy3_eps * (1.0 + fy4_growth)
    fy4_eps_cap = eps_anchor * safe_float(config.get("eps_cap"), 2.0)
    fy4_eps = min(fy4_eps_raw, fy4_eps_cap)

    exit_premium = clamp(
        (fy4_growth - 0.08) * 16.0,
        -0.5,
        safe_float(config.get("exit_premium"), 2.0),
    )
    if structural_acceleration:
        exit_premium += 0.50

    # 이익저점/급하락 상태의 현재 target PER에는 저점 ROE·마진 감점이 이미 반영돼 있다.
    # FY4 회복가치에 같은 저점 감점을 중복 적용하지 않도록 업종 정상 PER을 하한 앵커로 둔다.
    base_per = safe_float(profile.get("base_per"), target_per)
    future_per_anchor = target_per
    if earnings_trough or negative_transition:
        future_per_anchor = max(target_per, base_per * 0.85)

    exit_per = clamp(
        future_per_anchor + exit_premium,
        max(6.0, future_per_anchor * 0.82),
        per_max,
    )
    discount_rate = clamp(
        cost_of_equity + (0.012 if profile.get("cyclical") else 0.008),
        0.09,
        0.14,
    )
    discount_years = 3.0
    raw_value = fy4_eps * exit_per / ((1.0 + discount_rate) ** discount_years)
    value_cap = (
        earnings_value * safe_float(config.get("value_cap"), 1.65)
        if earnings_value > 0
        else raw_value
    )
    future_value = min(raw_value, value_cap) if value_cap > 0 else raw_value

    # 제한사유는 계산을 죽이지 않고 모형 가중치만 낮춘다.
    recognition = 1.0
    penalty_rules = [
        (ttm_eps <= 0, 0.12),
        (negative_transition, 0.18),
        (earnings_trough, 0.15),
        (operating_margin <= 0.03 or net_margin <= 0.015, 0.12),
        (safe_float(industry.get("long")) < -35.0, 0.12),
        (
            ttm_eps > 0
            and normalized_eps > 0
            and ttm_eps / normalized_eps > 2.8
            and profile.get("cyclical"),
            0.15,
        ),
        (not strong_evidence, 0.15),
    ]
    for condition, penalty in penalty_rules:
        if condition:
            recognition -= penalty
    recognition = clamp(recognition, 0.20, 1.0)

    quality = 35.0
    quality += clamp(ttm_quality, 0.0, 100.0) * 0.20
    quality += clamp(share_quality, 0.0, 100.0) * 0.15
    quality += 15.0 if structural_acceleration else 8.0
    quality += 5.0 if bool(quarter.get("잠정실적반영")) else 0.0
    quality += 5.0 if industry.get("available") else 0.0
    if limited:
        quality -= min(18.0, len(set(limited)) * 3.0)
    quality = int(clamp(quality, 45.0, 92.0))

    effective_weight = (
        safe_float(config.get("weight"), 0.16)
        * quality / 100.0
        * recognition
    )

    return {
        "버전": FUTURE_GROWTH_MODEL_VERSION,
        "대상업종": True,
        "사용가능": future_value > 0,
        "상태": "제한사용" if limited else "정상",
        "차단사유": [],
        "제한사유": list(dict.fromkeys(limited)),
        "선정근거": list(dict.fromkeys(evidence)),
        "FY3성장률": fy3_growth * 100.0,
        "FY4성장률": fy4_growth * 100.0,
        "FY3EPS": fy3_eps,
        "FY4EPS": fy4_eps,
        "출구PER": exit_per,
        "할인율": discount_rate * 100.0,
        "할인기간연수": discount_years,
        "원시가치": raw_value,
        "가치상한": value_cap,
        "상한적용": raw_value > future_value + 1e-9,
        "가치": future_value,
        "가중치": effective_weight,
        "모형인정률": recognition * 100.0,
        "품질": quality,
        "현재가미사용": True,
    }


def _model_row(name: str, value: float, weight: float, role: str = "기준") -> Dict[str, Any]:
    return {"name": name, "value": value, "weight": weight, "role": role}


def build_fundamental_value_decomposition(
    *,
    profile_code: str,
    profile: Dict[str, Any],
    ttm_eps: float,
    normalized_eps: float,
    run_rate_eps: float,
    bps: float,
    roe: float,
    operating_margin: float,
    revenue_growth_3y: float,
    debt_ratio: float,
    pbr_value: float,
    residual_value: float,
    normalized_fcf_ps: float,
    net_cash_per_share: float,
    quarter: Dict[str, Any],
    positive_transition: bool,
    negative_transition: bool,
    structural_acceleration: bool,
    industry: Dict[str, Any],
    future_growth_model: Dict[str, Any],
    cost_of_equity: float,
) -> Dict[str, Any]:
    """현재 재무가치와 객관적 미래 증분가치를 분리한다.

    현재가는 어떤 단계에서도 입력하지 않는다.
    현재 재무기초가치는 확정 TTM/정상화 이익, 순자산, 잔여이익, FCF처럼
    이미 관측된 재무정보만 사용한다. 미래 증분가치는 별도 성장모형의
    미래 총가치가 현재 재무기초가치를 초과하는 부분만 반영해 이중계산을 막는다.
    """
    current_eps = _weighted_positive([
        {"value": ttm_eps, "weight": 0.68 if not profile.get("cyclical") else 0.58},
        {"value": normalized_eps, "weight": 0.32 if not profile.get("cyclical") else 0.42},
    ])
    if current_eps <= 0 and normalized_eps > 0:
        current_eps = normalized_eps

    base_per = safe_float(profile.get("base_per"), 10.5)
    per_min = safe_float(profile.get("per_min"), 6.0)
    per_max = safe_float(profile.get("per_max"), 26.0)
    base_per += clamp((roe - 0.08) * 18.0, -1.8, 4.0)
    if profile_code not in {"finance", "insurance"}:
        base_per += clamp((operating_margin - 0.08) * 8.0, -1.0, 2.2)
    base_per += clamp(revenue_growth_3y * 2.5, -0.8, 1.5)
    if debt_ratio > 2.0 and profile_code not in {"finance", "insurance"}:
        base_per -= 1.2
    base_per = clamp(base_per, per_min, per_max)

    current_earnings_value = current_eps * base_per if current_eps > 0 else 0.0
    current_graham_value = (
        (22.5 * current_eps * bps) ** 0.5
        if current_eps > 0 and bps > 0
        else 0.0
    )
    current_fcf_value = 0.0
    if normalized_fcf_ps > 0:
        fcf_multiple = clamp(base_per * 0.78, 7.0, 18.0)
        current_fcf_value = (
            normalized_fcf_ps * fcf_multiple
            + max(0.0, net_cash_per_share) * 0.65
        )

    run_rate_ratio = (
        run_rate_eps / normalized_eps
        if run_rate_eps > 0 and normalized_eps > 0
        else 0.0
    )
    earnings_dislocation = bool(
        positive_transition
        and not negative_transition
        and run_rate_ratio >= 2.0
        and safe_float(quarter.get("operating_yoy")) >= 35.0
        and safe_float(quarter.get("net_yoy")) >= 25.0
    )

    if profile_code == "beauty_consumer" and earnings_dislocation:
        weights = {
            "earnings": 0.12,
            "pbr": 0.32,
            "residual": 0.08,
            "fcf": 0.30,
            "graham": 0.18,
        }
    elif profile_code == "beauty_consumer":
        weights = {
            "earnings": 0.30,
            "pbr": 0.24,
            "residual": 0.10,
            "fcf": 0.20,
            "graham": 0.16,
        }
    elif profile.get("growth"):
        weights = {
            "earnings": 0.44,
            "pbr": 0.18,
            "residual": 0.14,
            "fcf": 0.09,
            "graham": 0.15,
        }
    else:
        weights = {
            "earnings": 0.40,
            "pbr": 0.22,
            "residual": 0.16,
            "fcf": 0.12,
            "graham": 0.10,
        }

    current_models = [
        {"name": "현재·정상화 이익가치", "value": current_earnings_value, "weight": weights["earnings"]},
        {"name": "순자산 기반가치", "value": pbr_value, "weight": weights["pbr"]},
        {"name": "잔여이익 현재가치", "value": residual_value, "weight": weights["residual"]},
        {"name": "정상화 FCF 가치", "value": current_fcf_value, "weight": weights["fcf"]},
        {"name": "현재 그레이엄 결합가치", "value": current_graham_value, "weight": weights["graham"]},
    ]
    current_models = [
        row for row in current_models
        if safe_float(row.get("value")) > 0 and safe_float(row.get("weight")) > 0
    ]
    current_base = weighted_average(current_models) or 0.0

    future_total = (
        safe_float(future_growth_model.get("가치"))
        if future_growth_model.get("사용가능") is True
        else 0.0
    )
    future_increment = max(0.0, future_total - current_base) if current_base > 0 else 0.0
    fundamental_value = current_base + future_increment if current_base > 0 else 0.0

    values = [safe_float(row.get("value")) for row in current_models if safe_float(row.get("value")) > 0]
    current_dispersion = (
        max(values) / min(values)
        if len(values) >= 2 and min(values) > 0
        else 0.0
    )

    # 자산집약·사이클 업종은 한 시점의 낮은 이익가치가 순자산·잔여이익·
    # 그레이엄 가치와 크게 어긋날 수 있다. 이때 현재가에 맞추지 않고, 이미
    # 수집된 DART 기반 독립 가치앵커가 충분히 합의할 때만 현재재무기초가치를
    # 승격한다. 손실기업처럼 자산가치 하나만 남은 경우와 모형분산이 지나치게
    # 큰 경우는 자동 차단한다.
    asset_anchor_values = [
        value
        for value in (pbr_value, residual_value, current_graham_value, current_fcf_value)
        if safe_float(value) > 0
    ]
    asset_anchor = median(asset_anchor_values) or 0.0
    asset_to_earnings = (
        asset_anchor / current_earnings_value
        if asset_anchor > 0 and current_earnings_value > 0
        else 0.0
    )
    asset_cycle_candidate = bool(
        profile_code in ASSET_CYCLE_PROFILES
        and ttm_eps > 0
        and bps > 0
        and len(current_models) >= 3
        and len(asset_anchor_values) >= 2
        and current_earnings_value > 0
    )
    asset_cycle_dislocation = bool(
        asset_cycle_candidate
        and asset_to_earnings >= 2.40
        and 0.0 < current_dispersion <= 6.0
    )

    adaptive_eligible = bool(
        current_base > 0
        and (
            profile_code == "beauty_consumer"
            or asset_cycle_dislocation
            or (
                profile_code in {"electronic_components"}
                and profile.get("growth") is True
                and future_growth_model.get("사용가능") is True
                and safe_float(future_growth_model.get("품질")) >= 80
                and (structural_acceleration or earnings_dislocation)
            )
        )
    )

    evidence = []
    if asset_cycle_dislocation:
        evidence.append("자산집약 업종에서 순자산·잔여이익 등 독립 가치앵커가 현재 이익가치보다 유의하게 높음")
    if earnings_dislocation:
        evidence.append("최근 분기 이익 급회복과 과거 정상화이익의 큰 괴리를 감지")
    if structural_acceleration:
        evidence.append("매출·영업이익·순이익 동반 가속")
    if future_growth_model.get("사용가능") is True:
        evidence.extend(safe_list(future_growth_model.get("선정근거")))
    if safe_float(industry.get("long")) >= 20.0:
        evidence.append("장기 산업사이클 우호")

    quality = 55.0
    quality += 10.0 if ttm_eps > 0 else 3.0 if normalized_eps > 0 else 0.0
    quality += 8.0 if bps > 0 else 0.0
    quality += 8.0 if current_fcf_value > 0 else 0.0
    quality += 7.0 if len(current_models) >= 4 else 3.0 if len(current_models) >= 3 else 0.0
    quality += 7.0 if future_growth_model.get("사용가능") is True else 0.0
    if current_dispersion >= 8.0:
        quality -= 12.0
    elif current_dispersion >= 4.0:
        quality -= 7.0
    quality = int(clamp(quality, 45.0, 90.0))

    return {
        "버전": "adaptive-fundamental-v1.0.0",
        "현재가미사용": True,
        "적용가능": adaptive_eligible,
        "현재재무기초가치": current_base,
        "미래총가치": future_total,
        "미래증분가치": future_increment,
        "펀더멘털적정가": fundamental_value,
        "현재기준PER": base_per,
        "현재EPS앵커": current_eps,
        "이익급회복괴리": earnings_dislocation,
        "분기런레이트대정상화배수": run_rate_ratio,
        "현재모형분산배수": current_dispersion,
        "자산사이클보정버전": ASSET_CYCLE_ANCHOR_VERSION,
        "자산사이클보정후보": asset_cycle_candidate,
        "자산사이클보정적용조건충족": asset_cycle_dislocation,
        "자산앵커": round(asset_anchor, 2) if asset_anchor > 0 else 0.0,
        "자산앵커개수": len(asset_anchor_values),
        "자산앵커대현재이익가치배수": round(asset_to_earnings, 3) if asset_to_earnings > 0 else 0.0,
        "품질": quality,
        "근거": list(dict.fromkeys(evidence)),
        "현재가치모형": [
            {
                "모형": row["name"],
                "값": round(safe_float(row["value"]), 2),
                "가중치": round(safe_float(row["weight"]), 4),
            }
            for row in current_models
        ],
    }


def provisional_record(fundamentals_bundle: Dict[str, Any]) -> Dict[str, Any]:
    provisional = safe_dict(safe_dict(fundamentals_bundle).get("잠정실적"))
    if not provisional:
        return {}
    return provisional


def latest_period_key(periods: List[Dict[str, Any]]) -> int:
    if not periods:
        return 0
    latest = periods[0]
    year = int(safe_float(latest.get("사업연도"), 0))
    quarter = REPORT_QUARTER.get(str(latest.get("보고서코드", "")), 0)
    return year * 4 + quarter if year and quarter else 0


def expected_formal_period_key(now: Optional[Any] = None) -> int:
    """법정 제출시한에 7일의 안전여유를 둔 최신 정기보고서 기대분기."""
    from datetime import datetime

    current = now if isinstance(now, datetime) else datetime.now()
    year = current.year
    month_day = current.month * 100 + current.day
    if month_day < 407:
        return (year - 1) * 4 + 3
    if month_day < 522:
        return (year - 1) * 4 + 4
    if month_day < 821:
        return year * 4 + 1
    if month_day < 1121:
        return year * 4 + 2
    return year * 4 + 3


def build_effective_ttm(
    formal_quarters: List[Dict[str, Any]],
    formal_ttm: Dict[str, Any],
    provisional: Dict[str, Any],
    profile_code: str = "general",
) -> Dict[str, Any]:
    """최신 잠정실적이 정식보고서보다 한 분기 앞설 때 이익 TTM만 교체한다.

    현금흐름·재무상태는 감사 전 잠정자료에서 임의 추정하지 않고 가장 최근
    정식 TTM/재무상태 값을 유지한다.
    """
    if provisional.get("사용가능") is not True:
        return dict(formal_ttm)

    provisional_key = int(safe_float(provisional.get("기간키"), 0))
    if provisional_key <= 0:
        return dict(formal_ttm)

    rows = [
        row for row in formal_quarters
        if int(safe_float(row.get("기간키"), 0)) < provisional_key
    ][:3]
    keys = [provisional_key] + [int(safe_float(row.get("기간키"), 0)) for row in rows]
    if len(rows) != 3 or any(keys[index] - keys[index + 1] != 1 for index in range(3)):
        result = dict(formal_ttm)
        result["잠정실적반영실패사유"] = "잠정실적과 직전 3개 단독분기가 연속되지 않음"
        return result

    provisional_metrics = safe_dict(provisional.get("지표"))
    financial_profile = profile_code in {"finance", "insurance"}
    net_income_missing = provisional_metrics.get("순이익") in (None, "")
    revenue_missing = safe_float(provisional_metrics.get("매출")) <= 0
    operating_missing = provisional_metrics.get("영업이익") in (None, "")
    if net_income_missing or (
        not financial_profile and (revenue_missing or operating_missing)
    ):
        result = dict(formal_ttm)
        result["잠정실적반영실패사유"] = "잠정실적 핵심 계정 미확보"
        return result

    metrics = dict(safe_dict(formal_ttm.get("metrics")))
    keys_to_replace = ["순이익"]
    if not revenue_missing:
        keys_to_replace.append("매출")
    if not operating_missing:
        keys_to_replace.append("영업이익")
    for key in keys_to_replace:
        metrics[key] = safe_float(provisional_metrics.get(key)) + sum(
            safe_float(safe_dict(row.get("지표")).get(key)) for row in rows
        )

    first = rows[-1]
    result = dict(formal_ttm)
    result.update({
        "available": True,
        "quality": min(88, int(safe_float(provisional.get("데이터품질"), 78))),
        "metrics": metrics,
        "period": f"{first.get('사업연도')}Q{first.get('분기')}~{provisional.get('사업연도')}Q{provisional.get('분기')}",
        "잠정실적반영": True,
        "잠정실적접수번호": provisional.get("접수번호", ""),
        "잠정실적공시일": provisional.get("공시일", ""),
        "현금흐름기준": "최근 정식보고서 TTM 유지",
    })
    return result


def effective_quarter_signal(
    periods: List[Dict[str, Any]],
    formal_quarters: List[Dict[str, Any]],
    provisional: Dict[str, Any],
) -> Dict[str, Any]:
    base = quarter_signal(periods)
    if provisional.get("사용가능") is not True:
        return base
    provisional_key = int(safe_float(provisional.get("기간키"), 0))
    if provisional_key <= latest_period_key(periods):
        return base
    metrics = safe_dict(provisional.get("지표"))
    prior = next(
        (
            row for row in formal_quarters
            if int(safe_float(row.get("사업연도"), 0)) == int(safe_float(provisional.get("사업연도"), 0)) - 1
            and int(safe_float(row.get("분기"), 0)) == int(safe_float(provisional.get("분기"), 0))
        ),
        None,
    )
    prior_metrics = safe_dict(prior.get("지표")) if prior else {}
    revenue = safe_float(metrics.get("매출"))
    operating = safe_float(metrics.get("영업이익"))
    net = safe_float(metrics.get("순이익"))
    revenue_yoy = growth_rate(revenue, safe_float(prior_metrics.get("매출"))) if prior else 0.0
    operating_yoy = growth_rate(operating, safe_float(prior_metrics.get("영업이익"))) if prior else 0.0
    net_yoy = growth_rate(net, safe_float(prior_metrics.get("순이익"))) if prior else 0.0
    signal = (
        clamp(revenue_yoy / 40.0, -1.0, 1.0) * 20.0
        + clamp(operating_yoy / 60.0, -1.0, 1.0) * 45.0
        + clamp(net_yoy / 80.0, -1.0, 1.0) * 35.0
    )
    return {
        "latest_revenue": revenue,
        "latest_operating_income": operating,
        "latest_net_income": net,
        "revenue_yoy": revenue_yoy,
        "operating_yoy": operating_yoy,
        "net_yoy": net_yoy,
        "signal": clamp(signal, -100.0, 100.0),
        "quality": int(safe_float(provisional.get("데이터품질"), 78)),
        "latest_period": f"{provisional.get('사업연도')}Q{provisional.get('분기')}",
        "잠정실적반영": True,
    }


def build_data_qualification(
    periods: List[Dict[str, Any]],
    ttm: Dict[str, Any],
    provisional: Dict[str, Any],
    shares: float,
    valuation_eps: float,
    profile_code: str,
    company_info: Dict[str, Any],
    model_count: int,
    price: float,
    basic: float,
    as_of: Optional[Any] = None,
) -> Dict[str, Any]:
    formal_key = latest_period_key(periods)
    expected_key = expected_formal_period_key(as_of)
    provisional_key = int(safe_float(provisional.get("기간키"), 0))
    provisional_detected = bool(provisional.get("접수번호"))
    provisional_usable = provisional.get("사용가능") is True
    provisional_newer = provisional_detected and provisional_key > formal_key
    provisional_unquantified = provisional_newer and not provisional_usable
    formal_current = formal_key >= expected_key
    formal_fallback_eligible = bool(
        provisional_unquantified
        and formal_current
        and ttm.get("available") is True
        and shares > 0
        and valuation_eps > 0
    )
    effective_key = max(formal_key, provisional_key if provisional_usable else 0)
    industry_confidence = int(safe_float(company_info.get("산업분류신뢰도"), 45))

    critical: List[str] = []
    warnings: List[str] = []
    checks = {
        "정식재무최신성": formal_current,
        "연속TTM": ttm.get("available") is True,
        "주식수": shares > 0,
        "평가EPS": valuation_eps > 0,
        "산업프로필": profile_code != "general",
        "가치모형수": model_count >= 3,
        "최신잠정실적정량화": (not provisional_detected) or provisional_usable or provisional_key <= formal_key,
        "정식보고서대체평가가능": (not provisional_unquantified) or formal_fallback_eligible,
    }
    if not checks["정식재무최신성"]:
        critical.append("정식 재무보고서가 법정 제출시한 기준 최신분기보다 오래됨")
    if not checks["연속TTM"]:
        critical.append("연속 4개 단독분기 TTM 미확보")
    if not checks["주식수"]:
        critical.append("가치평가 주식수 미확보")
    if not checks["평가EPS"]:
        critical.append("양(+)의 평가 EPS 미확보")
    if provisional_unquantified:
        if formal_fallback_eligible:
            warnings.append("최신 잠정실적 미정량화: 최신 정식보고서 기준 평가")
        else:
            critical.append("정식보고서보다 새로운 잠정실적 공시를 정량화하지 못함")
    if not checks["산업프로필"]:
        warnings.append("산업 프로필이 일반기업 또는 저신뢰 분류")
    if not checks["가치모형수"]:
        warnings.append("독립 가치모형 3개 미만")
    if industry_confidence < 70:
        warnings.append(f"산업분류 신뢰도 {industry_confidence}점")

    extreme_gap = bool(price > 0 and basic > 0 and (basic / price < 0.34 or basic / price > 3.0))
    if extreme_gap:
        warnings.append("현재가와 기준 적정가가 약 3배 이상 괴리")
        if provisional_unquantified and formal_fallback_eligible:
            warnings.append("극단적 괴리와 최신 잠정실적 미반영이 동시에 발생하여 보수적 해석 필요")
        if industry_confidence < 70:
            critical.append("극단적 괴리와 저신뢰 산업분류가 동시에 발생")

    passed = not critical
    status = "통과" if passed and not warnings else "주의통과" if passed else "보류"
    return {
        "버전": DATA_QUALIFICATION_VERSION,
        "통과": passed,
        "상태": status,
        "핵심검사": checks,
        "중단사유": list(dict.fromkeys(critical)),
        "주의사유": list(dict.fromkeys(warnings)),
        "정식재무기준분기키": formal_key,
        "기대정식재무분기키": expected_key,
        "잠정실적분기키": provisional_key,
        "유효재무분기키": effective_key,
        "잠정실적감지": provisional_detected,
        "잠정실적반영": bool(ttm.get("잠정실적반영")),
        "잠정실적미정량화": provisional_unquantified,
        "정식보고서대체평가": formal_fallback_eligible,
        "평가기준": (
            "최신 정식보고서 기준·잠정실적 미반영"
            if formal_fallback_eligible
            else "잠정실적 반영"
            if provisional_usable and provisional_key > formal_key
            else "최신 정식보고서 기준"
        ),
        "산업분류신뢰도": industry_confidence,
        "산업프로필버전": company_info.get("산업프로필버전", INDUSTRY_PROFILE_VERSION),
        "극단적괴리": extreme_gap,
    }


def calculate_value(
    financial: Dict[str, Any],
    market: Dict[str, Any],
    fundamentals_analysis: Optional[Dict[str, Any]] = None,
    fundamentals_bundle: Optional[Dict[str, Any]] = None,
    industry_analysis: Optional[Dict[str, Any]] = None,
    industry_bundle: Optional[Dict[str, Any]] = None,
    company_info: Optional[Dict[str, Any]] = None,
    *,
    valuation_as_of: Optional[Any] = None,
) -> Dict[str, Any]:
    financial = safe_dict(financial)
    market = safe_dict(market)
    fundamentals_analysis = safe_dict(fundamentals_analysis)
    fundamentals_bundle = safe_dict(fundamentals_bundle)
    industry_analysis = safe_dict(industry_analysis)
    industry_bundle = safe_dict(industry_bundle)
    company_info = safe_dict(company_info)

    metrics = safe_dict(financial.get("재무지표"))
    growth = safe_dict(financial.get("성장지표"))
    price = safe_float(market.get("현재가"))
    market_eps = safe_float(market.get("EPS"))
    bps = safe_float(market.get("BPS"))
    actual_per = safe_float(market.get("PER"))
    actual_pbr = safe_float(market.get("PBR"))

    roe = safe_float(metrics.get("ROE")) / 100.0
    operating_margin = safe_float(metrics.get("영업이익률")) / 100.0
    net_margin = safe_float(metrics.get("순이익률")) / 100.0
    debt_ratio = safe_float(metrics.get("부채비율")) / 100.0
    revenue_growth_3y = safe_float(growth.get("매출3년성장률")) / 100.0
    operating_growth_3y = safe_float(growth.get("영업이익3년성장률")) / 100.0
    net_growth_3y = safe_float(growth.get("순이익3년성장률")) / 100.0

    profile_code = resolve_profile_code(company_info, industry_bundle)
    periods = get_periods(fundamentals_bundle)
    quarters = build_standalone_quarters(periods)
    formal_ttm = build_ttm(quarters, profile_code=profile_code)
    provisional = provisional_record(fundamentals_bundle)
    ttm = build_effective_ttm(
        quarters,
        formal_ttm,
        provisional,
        profile_code=profile_code,
    )
    quarter = effective_quarter_signal(periods, quarters, provisional)
    share_info = infer_share_count(market, periods, company_info, fundamentals_bundle)
    shares = safe_float(share_info.get("value"))
    annual_eps = _annual_eps_series(periods, shares)
    normalized_eps = _normalized_eps(annual_eps)
    ttm_eps = safe_float(safe_dict(ttm.get("metrics")).get("순이익")) / shares if ttm.get("available") and shares > 0 else 0.0
    latest_quarter_eps = quarter["latest_net_income"] / shares if shares > 0 else 0.0
    run_rate_eps = latest_quarter_eps * 4.0 if latest_quarter_eps > 0 else 0.0

    # GitHub에서는 KIS를 비활성화하므로 Yahoo 현재가만 확보되고 EPS·BPS가
    # 비어 있을 수 있다. 이때 DART TTM/자본총계와 주식수로 주당지표를 복원한다.
    if market_eps <= 0:
        market_eps = ttm_eps if ttm_eps > 0 else normalized_eps
    latest_equity = 0.0
    latest_liabilities = 0.0
    for period in periods:
        period_metrics = get_period_metrics(period)
        latest_equity = safe_float(period_metrics.get("자본총계"))
        latest_liabilities = safe_float(period_metrics.get("부채총계"))
        if latest_equity > 0:
            break

    # 가치평가 품질·배수 보정은 구형 연간 요약보다 유효 TTM과 최신 재무상태를 우선한다.
    ttm_metrics = safe_dict(ttm.get("metrics"))
    ttm_revenue = safe_float(ttm_metrics.get("매출"))
    ttm_operating = safe_float(ttm_metrics.get("영업이익"))
    ttm_net = safe_float(ttm_metrics.get("순이익"))
    if ttm_revenue > 0:
        operating_margin = ttm_operating / ttm_revenue
        net_margin = ttm_net / ttm_revenue
    if latest_equity > 0:
        roe = ttm_net / latest_equity if ttm_net != 0 else roe
        debt_ratio = latest_liabilities / latest_equity if latest_liabilities > 0 else debt_ratio

    annual_rows = annual_periods(periods)
    if len(annual_rows) >= 3:
        newest = get_period_metrics(annual_rows[0])
        oldest = get_period_metrics(annual_rows[2])
        revenue_growth_3y = growth_rate(safe_float(newest.get("매출")), safe_float(oldest.get("매출"))) / 100.0
        operating_growth_3y = growth_rate(safe_float(newest.get("영업이익")), safe_float(oldest.get("영업이익"))) / 100.0
        net_growth_3y = growth_rate(safe_float(newest.get("순이익")), safe_float(oldest.get("순이익"))) / 100.0

    # BPS도 시장 제공값 대신 최신 DART 자본÷독립 확보 주식수로
    # 재산출한다. 이로써 시장 PER/PBR 변화가 적정가에 역유입되지 않는다.
    if shares > 0 and latest_equity > 0:
        bps = latest_equity / shares
    if actual_per <= 0 and price > 0 and market_eps > 0:
        actual_per = price / market_eps
    if actual_pbr <= 0 and price > 0 and bps > 0:
        actual_pbr = price / bps

    profile = dict(VALUATION_PROFILES[profile_code])
    stock_code = str(company_info.get("종목코드") or company_info.get("KIS종목코드") or "").zfill(6)
    complex_config = COMPLEX_COMPANY_CONFIG.get(stock_code)
    profile_recognized = profile_code != "general" or bool(company_info.get("OpenDART업종코드"))

    earnings_analysis = safe_dict(fundamentals_analysis.get("분기실적"))
    forward_direction = safe_dict(fundamentals_analysis.get("향후이익방향대용"))
    cash_quality = safe_dict(fundamentals_analysis.get("현금흐름재무안전성"))
    earnings_signal = (
        safe_float(quarter.get("signal"), 0.0)
        if quarter.get("잠정실적반영")
        else safe_float(earnings_analysis.get("신호"), quarter["signal"])
    )
    forward_signal = safe_float(forward_direction.get("신호"), 0.0)
    if quarter.get("잠정실적반영"):
        forward_signal = clamp(
            forward_signal * 0.55 + safe_float(quarter.get("signal")) * 0.45,
            -100.0,
            100.0,
        )
    cash_signal = safe_float(cash_quality.get("신호"), 0.0)
    industry = industry_signal(industry_analysis)

    transition_strength = _weighted_positive([
        {"value": abs(quarter["operating_yoy"]), "weight": 0.45},
        {"value": abs(quarter["net_yoy"]), "weight": 0.35},
        {"value": abs(operating_growth_3y * 100.0), "weight": 0.20},
    ])
    positive_transition = (
        quarter["operating_yoy"] >= 25.0
        or quarter["net_yoy"] >= 35.0
        or earnings_signal >= 25.0
        or forward_signal >= 25.0
    )
    negative_transition = (
        quarter["operating_yoy"] <= -20.0
        or quarter["net_yoy"] <= -25.0
        or earnings_signal <= -25.0
        or forward_signal <= -25.0
    )
    transition_direction = (
        "실적 급상승 전환" if positive_transition and not negative_transition
        else "실적 급하락 전환" if negative_transition and not positive_transition
        else "실적 안정/혼합"
    )

    # TTM을 중심으로 정상화·분기런레이트를 결합한다. 사이클 기업은 한 분기 연환산 비중을 낮춘다.
    if profile.get("cyclical"):
        base_forward_eps = _weighted_positive([
            {"value": ttm_eps, "weight": 0.65},
            {"value": normalized_eps, "weight": 0.25},
            {"value": run_rate_eps, "weight": 0.10},
        ])
    elif profile.get("growth"):
        base_forward_eps = _weighted_positive([
            {"value": ttm_eps, "weight": 0.58},
            {"value": normalized_eps, "weight": 0.20},
            {"value": run_rate_eps, "weight": 0.22},
        ])
    else:
        base_forward_eps = _weighted_positive([
            {"value": ttm_eps, "weight": 0.62},
            {"value": normalized_eps, "weight": 0.30},
            {"value": run_rate_eps, "weight": 0.08},
        ])
    # 양(+) 이익 자료가 없으면 시장 EPS로 적정가를 역산하지 않고
    # 산출불가로 남겨 거짓 정밀도를 피한다.

    growth_cap = 0.18 if profile.get("cyclical") else 0.24 if profile.get("growth") else 0.14
    structural_acceleration = bool(
        quarter.get("잠정실적반영")
        and quarter["revenue_yoy"] >= 15.0
        and quarter["operating_yoy"] >= 45.0
        and quarter["net_yoy"] >= 25.0
    )
    if structural_acceleration:
        growth_cap = min(0.34, growth_cap + 0.10)
    growth_floor = -0.18 if profile.get("cyclical") else -0.12
    fy1_growth = 0.0
    fy1_growth += clamp(quarter["revenue_yoy"] / 100.0 * 0.10, -0.05, 0.08)
    fy1_growth += clamp(quarter["operating_yoy"] / 100.0 * 0.08, -0.07, 0.10)
    fy1_growth += clamp(quarter["net_yoy"] / 100.0 * 0.05, -0.05, 0.07)
    fy1_growth += clamp(forward_signal / 100.0 * 0.06, -0.04, 0.06)
    fy1_growth += clamp(industry["signal"] / 100.0 * 0.04, -0.03, 0.04)
    if ttm_eps > 0 and normalized_eps > 0 and ttm_eps / normalized_eps > 2.2 and profile.get("cyclical"):
        fy1_growth -= 0.05
    fy1_growth = clamp(fy1_growth, growth_floor, growth_cap)
    fy2_growth = clamp(fy1_growth * (0.55 if fy1_growth >= 0 else 0.70), -0.12, 0.12)
    fy1_eps = base_forward_eps * (1.0 + fy1_growth) if base_forward_eps > 0 else 0.0
    fy2_eps = fy1_eps * (1.0 + fy2_growth) if fy1_eps > 0 else 0.0

    cost_of_equity = _cost_of_equity(debt_ratio, profile_code)
    valuation_eps = _weighted_positive([
        {"value": ttm_eps, "weight": 0.20},
        {"value": normalized_eps, "weight": 0.15},
        {"value": fy1_eps, "weight": 0.45},
        {"value": fy2_eps / (1.0 + cost_of_equity), "weight": 0.20},
    ])
    if valuation_eps <= 0:
        valuation_eps = base_forward_eps

    # 업종·기업 질·실적전환을 반영하되, 사이클 고점 이익 영구화는 감점한다.
    target_per = safe_float(profile.get("base_per"), 10.5)
    per_min = safe_float(profile.get("per_min"), 6.0)
    per_max = safe_float(profile.get("per_max"), 26.0)
    if profile_code == "semiconductor":
        target_per = max(target_per, 14.0)
        per_max = min(per_max, 22.0)
    if complex_config:
        target_per = safe_float(complex_config.get("base_multiple"), target_per)
        per_min = safe_float(complex_config.get("min_multiple"), per_min)
        per_max = safe_float(complex_config.get("max_multiple"), per_max)

    target_per += clamp((roe - 0.08) * 22.0, -2.0, 5.0)
    if profile_code not in {"finance", "insurance"}:
        target_per += clamp((operating_margin - 0.08) * 10.0, -1.2, 2.8)
    target_per += clamp(revenue_growth_3y * 3.5, -1.0, 2.0)
    target_per += clamp(earnings_signal / 100.0 * 1.8, -1.5, 1.8)
    target_per += clamp(forward_signal / 100.0 * 1.3, -1.0, 1.3)
    target_per += clamp(industry["signal"] / 100.0 * 1.0, -0.8, 1.0)
    if positive_transition:
        target_per += clamp(transition_strength / 80.0, 0.5, 2.4)
    if negative_transition:
        target_per -= clamp(transition_strength / 55.0, 0.8, 3.0)
    if debt_ratio > 2.0 and profile_code not in {"finance", "insurance"}:
        target_per -= 1.5
    if profile.get("cyclical") and ttm_eps > 0 and normalized_eps > 0:
        cycle_ratio = ttm_eps / normalized_eps
        if cycle_ratio > 2.5:
            target_per -= 2.5
        elif cycle_ratio > 1.8:
            target_per -= 1.2
    target_per = clamp(target_per, per_min, per_max)

    target_pbr = safe_float(profile.get("base_pbr"), 1.0)
    target_pbr += clamp((roe - 0.08) * 4.5, -0.30, 1.65)
    target_pbr += clamp(industry["signal"] / 100.0 * 0.12, -0.10, 0.12)
    target_pbr = clamp(target_pbr, safe_float(profile.get("pbr_min"), 0.4), safe_float(profile.get("pbr_max"), 3.2))

    earnings_value = valuation_eps * target_per if valuation_eps > 0 else 0.0
    pbr_value = bps * target_pbr if bps > 0 else 0.0

    # 그레이엄 결합가치는 이익과 순자산을 함께 보는 독립 보조모형이다.
    # 현재 이익이 급감한 사이클 저점에서는 TTM 한 시점보다 정상화 EPS를
    # 함께 사용해 일시적 이익 훼손이 전체 기업가치를 0에 가깝게 끌어내리지 않게 한다.
    graham_eps = _weighted_positive([
        {"value": valuation_eps, "weight": 0.55},
        {"value": normalized_eps, "weight": 0.45},
    ])
    graham_value = (
        (22.5 * graham_eps * bps) ** 0.5
        if graham_eps > 0 and bps > 0
        else 0.0
    )

    # 이익저점 국면 판정. 자산·그레이엄 가치가 이익가치보다 3배 이상 높고
    # 성장·사이클 업종이면 현재 이익 한 시점이 기업가치를 과도하게 누르는 것으로 본다.
    asset_to_earnings = pbr_value / earnings_value if pbr_value > 0 and earnings_value > 0 else 0.0
    graham_to_earnings = graham_value / earnings_value if graham_value > 0 and earnings_value > 0 else 0.0
    normalized_to_ttm = normalized_eps / ttm_eps if normalized_eps > 0 and ttm_eps > 0 else 0.0
    earnings_trough = bool(
        profile.get("cyclical")
        and profile.get("growth")
        and bps > 0
        and (
            (asset_to_earnings >= 3.0 and graham_to_earnings >= 2.0)
            or normalized_to_ttm >= 1.80
            or (ttm_eps <= 0 and normalized_eps > 0)
        )
    )

    # 중간 업황 회복 시 정상화 이익이 창출할 수 있는 가치.
    # 이익저점에서는 현재 저점의 ROE·마진·실적급락으로 이미 낮아진 target_per를
    # 다시 정상화 EPS에 곱하면 저점 영향을 이중으로 반영하게 된다.
    # 따라서 저점 회복가치는 업종 기본 PER을 중심으로 장기 산업신호만 제한적으로 반영한다.
    if earnings_trough:
        cycle_normal_per = safe_float(profile.get("base_per"), target_per)
        cycle_normal_per += clamp(industry["signal"] / 100.0 * 1.2, -1.2, 1.2)
        if debt_ratio > 2.0 and profile_code not in {"finance", "insurance"}:
            cycle_normal_per -= 1.0
        recovery_multiple = clamp(cycle_normal_per, per_min, per_max)
    else:
        recovery_multiple = clamp(target_per * 0.90, per_min, per_max)

    normalized_recovery_value = (
        normalized_eps * recovery_multiple
        if normalized_eps > 0
        else 0.0
    )

    residual_value = 0.0
    if bps > 0 and roe > 0:
        persistence = 0.70 if roe >= 0.15 else 0.50 if roe >= 0.10 else 0.28
        if profile.get("cyclical"):
            persistence -= 0.08
        if profile_code in {"finance", "insurance", "real_estate", "holding_company"}:
            persistence += 0.10
        excess_return = max(0.0, roe - cost_of_equity)
        residual_value = bps + bps * excess_return * clamp(persistence, 0.18, 0.85) / max(0.035, cost_of_equity - 0.02)

    latest_metrics = get_period_metrics(periods[0]) if periods else {}
    cash = safe_float(latest_metrics.get("현금및현금성자산"))
    borrowings = safe_float(latest_metrics.get("총차입금"))
    net_cash = cash - borrowings if cash > 0 and borrowings >= 0 else 0.0
    net_cash_per_share = net_cash / shares if shares > 0 else 0.0

    annual_fcf_eps = []
    if shares > 0:
        for period in annual_periods(periods)[:3]:
            fcf = safe_float(get_period_metrics(period).get("잉여현금흐름추정"))
            if fcf > 0:
                annual_fcf_eps.append(fcf / shares)
    normalized_fcf_ps = weighted_average([
        {"value": value, "weight": (0.55, 0.30, 0.15)[index]}
        for index, value in enumerate(annual_fcf_eps[:3])
    ]) or 0.0
    fcf_value = 0.0
    if normalized_fcf_ps > 0:
        fcf_multiple = clamp(target_per * 0.78, 7.0, 18.0)
        fcf_value = normalized_fcf_ps * fcf_multiple + max(0.0, net_cash_per_share) * 0.65

    transition_eps = _weighted_positive([
        {"value": ttm_eps, "weight": 0.30},
        {"value": fy1_eps, "weight": 0.55},
        {"value": normalized_eps, "weight": 0.15},
    ])
    transition_multiple = target_per
    if positive_transition:
        transition_multiple += 1.2
    if negative_transition:
        transition_multiple -= 1.5
    transition_multiple = clamp(transition_multiple, per_min, per_max + 2.0)
    transition_value = transition_eps * transition_multiple if transition_eps > 0 else 0.0

    complex_proxy_value = 0.0
    if complex_config and fy1_eps > 0:
        complex_multiple = clamp(
            safe_float(complex_config.get("base_multiple"), target_per)
            + clamp(forward_signal / 100.0 * 1.0, -0.8, 1.0),
            safe_float(complex_config.get("min_multiple"), per_min),
            safe_float(complex_config.get("max_multiple"), per_max),
        )
        complex_proxy_value = fy1_eps * complex_multiple + max(0.0, net_cash_per_share) * 0.75

    future_growth_model = build_future_growth_model(
        profile_code=profile_code,
        profile=profile,
        ttm_eps=ttm_eps,
        normalized_eps=normalized_eps,
        fy1_eps=fy1_eps,
        fy2_eps=fy2_eps,
        fy1_growth=fy1_growth,
        fy2_growth=fy2_growth,
        quarter=quarter,
        revenue_growth_3y=revenue_growth_3y,
        operating_growth_3y=operating_growth_3y,
        net_growth_3y=net_growth_3y,
        earnings_signal=earnings_signal,
        forward_signal=forward_signal,
        industry=industry,
        operating_margin=operating_margin,
        net_margin=net_margin,
        target_per=target_per,
        per_max=per_max,
        cost_of_equity=cost_of_equity,
        share_quality=safe_float(share_info.get("quality")),
        ttm_quality=safe_float(ttm.get("quality")),
        structural_acceleration=structural_acceleration,
        negative_transition=negative_transition,
        earnings_trough=earnings_trough,
        earnings_value=earnings_value,
    )
    future_growth_value = safe_float(future_growth_model.get("가치"))

    # 기업 유형별 모형 자격과 가중치.
    # 이익저점 국면에서는 현재 이익가치가 자산·그레이엄·정상화 회복가치를
    # 제거하지 못하게 별도 가중치를 적용한다.
    models: List[Dict[str, Any]] = []
    if profile_code == "battery" and earnings_trough:
        models.extend([
            _model_row("현재 이익가치", earnings_value, 0.10, "보조"),
            _model_row("실적전환 가치", transition_value, 0.12, "보조"),
            _model_row("정상화 회복가치", normalized_recovery_value, 0.20, "기준"),
            _model_row("PBR 자산가치", pbr_value, 0.28, "기준"),
            _model_row("그레이엄 결합가치", graham_value, 0.18, "기준"),
            _model_row("잔여이익가치", residual_value, 0.08, "기준"),
            _model_row("FCF 가치", fcf_value, 0.04, "보조"),
        ])
    elif complex_config:
        # 실제 사업부별 SOTP 원천자료가 없는 복합기업 대용값은 진단값으로만 남긴다.
        # 최종 기준가는 감사 가능한 일반 재무모형(이익·전환·FCF·자산·잔여이익)만 사용한다.
        models.extend([
            _model_row("선행·정상화 이익가치", earnings_value, safe_float(complex_config.get("earnings_weight"), 0.58)),
            _model_row("실적전환 가치", transition_value, 0.18),
            _model_row("FCF 가치", fcf_value, max(0.10, safe_float(complex_config.get("fcf_weight"), 0.06))),
            _model_row("PBR 하단가치", pbr_value, max(0.08, safe_float(complex_config.get("asset_weight"), 0.06)), "하단"),
            _model_row("잔여이익 하단가치", residual_value, max(0.08, safe_float(complex_config.get("residual_weight"), 0.06)), "하단"),
            _model_row("그레이엄 결합가치", graham_value, 0.06, "보조"),
        ])
    elif profile_code == "semiconductor":
        models.extend([
            _model_row("선행·정상화 이익가치", earnings_value, 0.48),
            _model_row("실적전환 가치", transition_value, 0.28),
            _model_row("FCF 가치", fcf_value, 0.08),
            _model_row("PBR 하단가치", pbr_value, 0.08, "하단"),
            _model_row("잔여이익 하단가치", residual_value, 0.08, "하단"),
            _model_row("그레이엄 결합가치", graham_value, 0.06, "보조"),
        ])
    else:
        weights = safe_dict(profile.get("weights"))
        models.extend([
            _model_row("선행·정상화 이익가치", earnings_value, safe_float(weights.get("per"), 0.38)),
            _model_row("PBR 자산가치", pbr_value, safe_float(weights.get("pbr"), 0.20)),
            _model_row("잔여이익가치", residual_value, safe_float(weights.get("residual"), 0.20)),
            _model_row("실적전환 가치", transition_value, safe_float(weights.get("transition"), 0.22)),
            _model_row("FCF 가치", fcf_value, 0.10),
            _model_row("그레이엄 결합가치", graham_value, 0.08, "보조"),
            _model_row("정상화 회복가치", normalized_recovery_value, 0.08, "보조"),
        ])

    if future_growth_model.get("사용가능") is True:
        models.append(_model_row(
            "미래 성장가치",
            future_growth_value,
            safe_float(future_growth_model.get("가중치")),
            "성장",
        ))

    valid_models = [row for row in models if row["value"] > 0 and row["weight"] > 0]
    basis_models = []
    excluded_models = []

    if earnings_trough:
        # 이익저점에서는 현재 이익을 앵커로 쓰지 않는다. 자산·그레이엄·정상화 회복·잔여이익의
        # 중앙값을 독립 앵커로 사용하여 자본집약 성장기업의 가치가 한 분기 이익으로 붕괴하는 것을 막는다.
        trough_anchor = median([
            value for value in (
                pbr_value,
                graham_value,
                normalized_recovery_value,
                residual_value,
            ) if value > 0
        ]) or median([row["value"] for row in valid_models]) or 0.0
        floor_ratio = max(0.38, safe_float(profile.get("model_floor"), 0.28))
        ceiling_ratio = safe_float(profile.get("model_ceiling"), 3.40)
        for row in valid_models:
            if trough_anchor > 0 and not (
                trough_anchor * floor_ratio <= row["value"] <= trough_anchor * ceiling_ratio
            ):
                excluded_models.append(row["name"])
                continue
            basis_models.append(row)
    else:
        for row in valid_models:
            # 성장기업의 낮은 FCF·자산 하단모형은 보수 시나리오에는 남기되
            # 구조적 성장 기준가와 모형분산을 왜곡하지 못하게 기준가에서 제외한다.
            if earnings_value > 0 and profile.get("growth"):
                if row["role"] == "하단" and row["value"] < earnings_value * 0.42:
                    excluded_models.append(row["name"])
                    continue
                if row["name"] == "FCF 가치" and row["value"] < earnings_value * 0.38:
                    excluded_models.append(row["name"])
                    continue
            if earnings_value > 0 and not (earnings_value * 0.28 <= row["value"] <= earnings_value * 3.2):
                excluded_models.append(row["name"])
                continue
            basis_models.append(row)

    if len(basis_models) < 2:
        if earnings_trough:
            # 저점 필터가 1개 이하만 남겼다고 현재 이익가치/실적전환가를 전부 다시 넣으면
            # 저점보정이 사실상 무효화된다. 독립 앵커(자산·그레이엄·정상화·잔여이익·FCF)
            # 중 중앙값에 가까운 최대 4개를 사용해 반드시 하나의 기준가를 만든다.
            trough_names = {
                "정상화 회복가치",
                "PBR 자산가치",
                "그레이엄 결합가치",
                "잔여이익가치",
                "FCF 가치",
            }
            trough_candidates = [
                row for row in valid_models
                if row["name"] in trough_names and row["value"] > 0
            ]
            if trough_candidates:
                trough_median = median([row["value"] for row in trough_candidates]) or 0.0
                trough_candidates.sort(
                    key=lambda row: abs(
                        (row["value"] / trough_median) - 1.0
                    ) if trough_median > 0 else 0.0
                )
                basis_models = trough_candidates[:4]
            else:
                basis_models = valid_models[:]
        else:
            basis_models = [row for row in valid_models if row["role"] != "하단"] or valid_models

        excluded_models = [row["name"] for row in valid_models if row not in basis_models]

    weighted_value = weighted_average(basis_models) or 0.0
    basis_values = [row["value"] for row in basis_models]
    basis_median = median(basis_values) or weighted_value
    basic = _weighted_positive([
        {"value": weighted_value, "weight": 0.90},
        {"value": basis_median, "weight": 0.10},
    ])

    all_values = [row["value"] for row in valid_models]
    q25 = percentile(all_values, 0.25) or basic
    q75 = percentile(all_values, 0.75) or basic
    normalized_floor = normalized_eps * max(per_min, target_per * 0.65) if normalized_eps > 0 else 0.0
    earnings_floor = earnings_value * (0.64 if profile.get("cyclical") else 0.72) if earnings_value > 0 else 0.0
    if earnings_trough:
        trough_low_candidates = [
            value for value in (
                pbr_value * 0.65 if pbr_value > 0 else 0.0,
                graham_value * 0.72 if graham_value > 0 else 0.0,
                normalized_recovery_value * 0.70 if normalized_recovery_value > 0 else 0.0,
                q25,
            ) if value > 0
        ]
        conservative = median(trough_low_candidates) or q25 or basic
        conservative = min(conservative, basic) if basic > 0 else conservative
        high_anchor = max(
            pbr_value,
            graham_value,
            normalized_recovery_value,
            residual_value,
            transition_value,
            future_growth_value,
            q75,
        )
        growth_value = min(
            high_anchor * 1.10,
            basic * safe_float(profile.get("upside"), 1.55),
        ) if basic > 0 else high_anchor
        growth_value = max(growth_value, basic)
    else:
        conservative = max(q25, normalized_floor, earnings_floor)
        conservative = min(conservative, basic) if basic > 0 else conservative
        high_anchor = max(earnings_value, transition_value, future_growth_value, q75)
        growth_value = min(high_anchor * 1.08, basic * safe_float(profile.get("upside"), 1.35)) if basic > 0 else high_anchor
        growth_value = max(growth_value, basic)

    # 현재 재무가치와 미래 증분가치를 분리한 적응형 펀더멘털 모형.
    # 기존 v4 기준가는 회귀감사를 위해 보존하고, 객관적 적용조건을 충족한 경우에만
    # 적응형 펀더멘털 적정가를 최종 기준가로 승격한다.
    legacy_basic = basic
    legacy_conservative = conservative
    legacy_growth_value = growth_value
    adaptive_value = build_fundamental_value_decomposition(
        profile_code=profile_code,
        profile=profile,
        ttm_eps=ttm_eps,
        normalized_eps=normalized_eps,
        run_rate_eps=run_rate_eps,
        bps=bps,
        roe=roe,
        operating_margin=operating_margin,
        revenue_growth_3y=revenue_growth_3y,
        debt_ratio=debt_ratio,
        pbr_value=pbr_value,
        residual_value=residual_value,
        normalized_fcf_ps=normalized_fcf_ps,
        net_cash_per_share=net_cash_per_share,
        quarter=quarter,
        positive_transition=positive_transition,
        negative_transition=negative_transition,
        structural_acceleration=structural_acceleration,
        industry=industry,
        future_growth_model=future_growth_model,
        cost_of_equity=cost_of_equity,
    )
    asset_cycle_gate = bool(
        adaptive_value.get("자산사이클보정적용조건충족") is True
    )
    adaptive_applied = bool(
        adaptive_value.get("적용가능") is True
        and safe_float(adaptive_value.get("펀더멘털적정가")) > 0
        and safe_float(adaptive_value.get("품질")) >= 60
        and (
            not asset_cycle_gate
            or safe_float(adaptive_value.get("현재재무기초가치"))
            >= legacy_basic * 1.15
        )
    )
    if adaptive_applied:
        basic = safe_float(adaptive_value.get("펀더멘털적정가"))
        current_base = safe_float(adaptive_value.get("현재재무기초가치"))
        future_total = safe_float(adaptive_value.get("미래총가치"))
        conservative = min(
            basic,
            max(
                legacy_conservative,
                current_base * 0.75 if current_base > 0 else 0.0,
            ),
        )
        growth_value = max(
            basic,
            legacy_growth_value,
            future_total * 1.08 if future_total > 0 else 0.0,
        )
        growth_value = min(
            growth_value,
            basic * max(1.15, safe_float(profile.get("upside"), 1.35)),
        )

    basis_dispersion = max(basis_values) / min(basis_values) if len(basis_values) >= 2 and min(basis_values) > 0 else 0.0
    all_model_dispersion = max(all_values) / min(all_values) if len(all_values) >= 2 and min(all_values) > 0 else 0.0
    model_dispersion = basis_dispersion
    implied_per = basic / valuation_eps if basic > 0 and valuation_eps > 0 else 0.0
    implied_pbr = basic / bps if basic > 0 and bps > 0 else 0.0
    gap = ((basic - price) / price * 100.0) if price > 0 and basic > 0 else 0.0

    data_qualification = build_data_qualification(
        periods=periods,
        ttm=ttm,
        provisional=provisional,
        shares=shares,
        valuation_eps=valuation_eps,
        profile_code=profile_code,
        company_info=company_info,
        model_count=len(valid_models),
        price=price,
        basic=basic,
        as_of=valuation_as_of,
    )

    abnormal_reasons: List[str] = []
    abnormal_reasons.extend(safe_list(data_qualification.get("중단사유")))
    if not ttm.get("available"):
        abnormal_reasons.append("연속 4개 단독분기 TTM 미확보")
    if shares <= 0:
        abnormal_reasons.append("주식수 미확보")
    if valuation_eps <= 0:
        abnormal_reasons.append("양(+)의 평가 EPS 미확보")
    adaptive_earnings_dislocation = bool(adaptive_value.get("이익급회복괴리")) if adaptive_applied else False
    if adaptive_applied and profile_code == "beauty_consumer" and adaptive_earnings_dislocation:
        if implied_pbr > 0 and not (0.45 <= implied_pbr <= safe_float(profile.get("pbr_max"), 5.0) * 1.20):
            abnormal_reasons.append("브랜드소비재 급회복 기준가의 암시 PBR이 업종 허용범위를 벗어남")
    elif not earnings_trough and implied_per > 0 and not (per_min * 0.75 <= implied_per <= per_max * 1.30):
        abnormal_reasons.append("최종가 암시 PER이 업종 허용범위를 벗어남")
    if earnings_trough and implied_pbr > 0 and not (0.35 <= implied_pbr <= safe_float(profile.get("pbr_max"), 4.0) * 1.20):
        abnormal_reasons.append("이익저점 기준가의 암시 PBR이 업종 허용범위를 벗어남")
    dispersion_limit = 5.5 if earnings_trough else 4.0
    if model_dispersion >= dispersion_limit:
        abnormal_reasons.append(
            "이익저점 모형 간 가치 차이가 5.5배 이상"
            if earnings_trough
            else "모형 간 가치 차이가 4배 이상"
        )
    if basic > 0 and price > 0 and (basic / price < 0.35 or basic / price > 3.0) and len(abnormal_reasons) >= 2:
        abnormal_reasons.append("시장가격과 3배 이상 괴리하면서 데이터·모형 경고 동시 발생")

    fatal = shares <= 0 or valuation_eps <= 0 or basic <= 0 or data_qualification.get("통과") is not True
    review = (not fatal) and any(
        reason in abnormal_reasons
        for reason in (
            "연속 4개 단독분기 TTM 미확보",
            "최종가 암시 PER이 업종 허용범위를 벗어남",
            "브랜드소비재 급회복 기준가의 암시 PBR이 업종 허용범위를 벗어남",
            "이익저점 기준가의 암시 PBR이 업종 허용범위를 벗어남",
            "모형 간 가치 차이가 4배 이상",
            "이익저점 모형 간 가치 차이가 5.5배 이상",
            "시장가격과 3배 이상 괴리하면서 데이터·모형 경고 동시 발생",
        )
    )
    calculation_status = (
        "산출보류"
        if data_qualification.get("통과") is not True and basic > 0
        else "산출불가"
        if fatal
        else "검토필요"
        if review
        else "정상"
    )
    # 검토필요는 숫자를 숨기는 상태가 아니라 신뢰도 경고다.
    # 데이터자격 미통과/주식수·EPS·기준가 부재 같은 fatal일 때만 최종값을 차단한다.
    final_available = not fatal and data_qualification.get("통과") is True

    if gap > 25:
        judgment = "강한 저평가"
    elif gap > 10:
        judgment = "저평가"
    elif gap < -25:
        judgment = "강한 고평가"
    elif gap < -10:
        judgment = "고평가"
    else:
        judgment = "적정"
    if not final_available:
        judgment = "산출불가"

    data_confidence = 30
    data_confidence += 18 if ttm.get("available") else 5 if periods else 0
    data_confidence += min(15, len(periods) * 2)
    data_confidence += 12 if share_info.get("quality", 0) >= 85 else 6 if shares > 0 else 0
    data_confidence += 8 if bps > 0 else 0
    data_confidence += 8 if industry["available"] else 0
    data_confidence += 5 if safe_float(cash_quality.get("데이터품질")) >= 70 else 0
    data_confidence += 6 if ttm.get("잠정실적반영") else 0
    data_confidence = int(clamp(data_confidence, 25, 95))
    if data_qualification.get("정식보고서대체평가") is True:
        data_confidence = min(data_confidence, 72)
    if data_qualification.get("통과") is not True:
        data_confidence = min(data_confidence, 45)

    model_confidence = 72
    if model_dispersion > 0:
        if model_dispersion <= 1.5:
            model_confidence += 10
        elif model_dispersion <= 2.2:
            model_confidence += 3
        elif model_dispersion <= 3.0:
            model_confidence -= 8
        else:
            model_confidence -= 20
    if future_growth_model.get("사용가능") is True:
        model_confidence += 3 if safe_float(future_growth_model.get("품질")) >= 85 else 0
    if adaptive_applied:
        adaptive_quality = safe_float(adaptive_value.get("품질"), 60.0)
        model_confidence = int(round(model_confidence * 0.72 + adaptive_quality * 0.28))
    if complex_config:
        model_confidence = min(model_confidence, 78)  # 세부 사업부 자료 없는 대용 SOTP
    if not ttm.get("available"):
        model_confidence -= 12
    if review:
        model_confidence = min(model_confidence, 54)
    model_confidence = int(clamp(model_confidence, 25, 90))
    confidence = int(round(data_confidence * 0.58 + model_confidence * 0.42))
    if not forward_direction.get("애널리스트컨센서스반영"):
        confidence = min(confidence, 84)
    if complex_config:
        confidence = min(confidence, 78)
    if data_qualification.get("정식보고서대체평가") is True:
        confidence = min(confidence, 72)
    if review:
        confidence = min(confidence, 54)
    confidence_grade = "A" if confidence >= 85 else "B" if confidence >= 70 else "C" if confidence >= 55 else "D"

    model_detail = []
    included_names = {row["name"] for row in basis_models}
    for row in valid_models:
        model_detail.append({
            "모형": row["name"],
            "값": round(row["value"], 2),
            "기본가중치": round(row["weight"], 4),
            "역할": row["role"],
            "기준가반영": row["name"] in included_names,
        })

    notes = [
        "DART 누적 분기자료를 단독 분기로 변환한 뒤 최근 4개 분기 TTM을 산출했습니다.",
        "KIS EPS·BPS·PER·PBR은 적정가 산식과 주식수 추정에서 제외하고 시장 진단에만 사용했습니다.",
        "현재가는 적정가 산식에 넣지 않고 계산 완료 후 괴리 검증에만 사용했습니다.",
        f"{profile.get('label', profile_code)} 업종 프로필을 적용했습니다.",
    ]
    if complex_config:
        notes.append("사업부 세부 원천자료가 없어 복합기업 대용가치는 진단용으로만 계산하고 최종 기준가에는 반영하지 않았습니다. 진짜 SOTP는 검증된 사업부 데이터가 있을 때 Strategic 모듈에서만 사용합니다.")
    if earnings_trough:
        notes.append("이익저점 국면을 감지해 현재 이익가치보다 자산·그레이엄·정상화 회복가치의 비중을 높였습니다.")
    if excluded_models:
        notes.append("기업 유형에 부적합하거나 독립 가치앵커에서 과도하게 벗어난 모형은 기준가에서 제외했습니다.")
    if future_growth_model.get("사용가능") is True:
        notes.append("구조적 성장 증거가 확인된 경우에만 FY3·FY4 성장률을 감쇠 적용하고 업종별 EPS·가치 상한 및 할인율을 거친 미래 성장가치를 일부 반영했습니다.")
    if adaptive_applied:
        notes.append("현재 재무기초가치와 미래 총가치를 분리한 뒤 미래 총가치가 현재 재무기초가치를 초과하는 부분만 미래 증분가치로 더해 이중계산을 방지했습니다.")
    if adaptive_applied and adaptive_value.get("자산사이클보정적용조건충족") is True:
        notes.append("자산집약·사이클 업종의 일시적 이익 훼손으로 PER 계열 가치가 독립 자산가치보다 과도하게 낮아지는 경우, 현재가를 사용하지 않고 순자산·잔여이익·그레이엄·FCF 가치의 합의도를 이용해 현재재무기초가치를 승격했습니다.")
    if ttm.get("잠정실적반영"):
        notes.append("정식 보고서보다 최신인 OpenDART 잠정실적을 매출·영업이익·순이익 TTM에 반영했으며 현금흐름은 최근 정식보고서를 유지했습니다.")
    if data_qualification.get("정식보고서대체평가") is True:
        notes.append("최신 잠정실적 공시는 감지했지만 핵심 계정을 신뢰성 있게 정량화하지 못해, 최신 법정 정식보고서의 연속 TTM만으로 적정가를 산출하고 신뢰도 상한을 낮췄습니다.")
    if data_qualification.get("통과") is not True:
        notes.append("데이터 자격검사를 통과하지 못해 계산값은 진단용으로만 남기고 최종 적정가 사용을 차단했습니다.")

    return {
        "가치평가계약버전": VALUATION_CONTRACT_VERSION,
        "가치평가엔진버전": VALUATION_ENGINE_VERSION,
        "가치평가모형개정버전": VALUATION_MODEL_REVISION,
        "가격독립성검사": {
            "통과": True,
            "현재가산식사용": False,
            "시가총액산식사용": False,
            "시장EPS산식사용": False,
            "시장BPS산식사용": False,
            "주식수원칙": share_info.get("결정원칙", "현재가·시가총액 미사용"),
        },
        "미래성장모형버전": FUTURE_GROWTH_MODEL_VERSION,
        "자산사이클보정버전": ASSET_CYCLE_ANCHOR_VERSION,
        "자산사이클보정적용": bool(adaptive_applied and adaptive_value.get("자산사이클보정적용조건충족") is True),
        "산출상태": calculation_status,
        "최종값사용가능": final_available,
        "최종값출처": "Python 가치평가 계약 v4",
        "데이터자격검사": data_qualification,
        "산업프로필버전": company_info.get("산업프로필버전", INDUSTRY_PROFILE_VERSION),
        "산업분류신뢰도": int(safe_float(company_info.get("산업분류신뢰도"), 45)),
        "정식재무기준분기키": latest_period_key(periods),
        "유효재무기준분기키": int(safe_float(data_qualification.get("유효재무분기키"), latest_period_key(periods))),
        "잠정실적": provisional,
        "현재가": price,
        "실제PER": actual_per,
        "실제PBR": actual_pbr,
        "EPS": market_eps,
        "BPS": bps,
        "발행주식수추정": round(shares) if shares > 0 else 0,
        "발행주식수출처": share_info.get("source", ""),
        "발행주식수품질": share_info.get("quality", 0),
        "발행주식수결정원칙": share_info.get("결정원칙", "현재가·시가총액 미사용"),
        "발행주식수후보": share_info.get("candidates", []),
        "TTMEPS": round(ttm_eps, 2) if ttm_eps > 0 else 0.0,
        "정상화EPS": round(normalized_eps, 2) if normalized_eps > 0 else 0.0,
        "정상화EPS연간자료개수": len(annual_eps),
        "분기런레이트EPS": round(run_rate_eps, 2) if run_rate_eps > 0 else 0.0,
        "FY1예상EPS": round(fy1_eps, 2) if fy1_eps > 0 else 0.0,
        "FY2예상EPS": round(fy2_eps, 2) if fy2_eps > 0 else 0.0,
        "FY3예상EPS": round(safe_float(future_growth_model.get("FY3EPS")), 2),
        "FY4예상EPS": round(safe_float(future_growth_model.get("FY4EPS")), 2),
        "평가EPS": round(valuation_eps, 2) if valuation_eps > 0 else 0.0,
        "선행EPS": round(fy1_eps, 2) if fy1_eps > 0 else 0.0,
        "FY1성장률": round(fy1_growth * 100.0, 2),
        "FY2성장률": round(fy2_growth * 100.0, 2),
        "FY3성장률": round(safe_float(future_growth_model.get("FY3성장률")), 2),
        "FY4성장률": round(safe_float(future_growth_model.get("FY4성장률")), 2),
        "TTM기준기간": ttm.get("period", ""),
        "TTM데이터품질": ttm.get("quality", 0),
        "TTM잠정실적반영": bool(ttm.get("잠정실적반영")),
        "TTM현금흐름기준": ttm.get("현금흐름기준", "정식보고서 TTM"),
        "목표PER": round(target_per, 2),
        "목표PBR": round(target_pbr, 2),
        "암시PER": round(implied_per, 2) if implied_per > 0 else 0.0,
        "암시PBR": round(implied_pbr, 2) if implied_pbr > 0 else 0.0,
        "PER기준적정가": round(earnings_value, 2),
        "PBR기준적정가": round(pbr_value, 2),
        "그레이엄가치": round(graham_value, 2),
        "정상화회복가치": round(normalized_recovery_value, 2),
        "정상화회복PER": round(recovery_multiple, 2),
        "잔여이익가치": round(residual_value, 2),
        "FCF가치": round(fcf_value, 2),
        "실적전환보정가": round(transition_value, 2),
        "미래성장가치": round(future_growth_value, 2),
        "미래성장모형": future_growth_model,
        "복합기업대용가치합산": round(complex_proxy_value, 2),
        "순현금주당가치": round(net_cash_per_share, 2),
        "기존V4재무적정가": round(legacy_basic, 2),
        "현재재무기초가치": round(safe_float(adaptive_value.get("현재재무기초가치")), 2),
        "미래증분가치": round(safe_float(adaptive_value.get("미래증분가치")), 2),
        "펀더멘털적정가": round(safe_float(adaptive_value.get("펀더멘털적정가")), 2),
        "적응형가치적용": adaptive_applied,
        "적응형가치모형": adaptive_value,
        "재무적정가": round(basic, 2),
        "기본적정가": round(basic, 2),
        "보수적적정가": round(conservative, 2),
        "성장적정가": round(growth_value, 2),
        "현재가대비": round(gap, 2),
        "판단": judgment,
        "가치평가산업코드": profile_code,
        "가치평가산업프로필": complex_config.get("label") if complex_config else profile.get("label"),
        "복합기업대용모형": bool(complex_config),
        "복합기업대용모형최종반영": False if complex_config else None,
        "진짜SOTP자료확보": False if complex_config else None,
        "산업분류출처": company_info.get("산업분류출처", "내부 일반분류"),
        "OpenDART업종코드": company_info.get("OpenDART업종코드", ""),
        "산업신호반영": industry["available"],
        "산업종합신호": round(industry["signal"], 2),
        "산업국면": industry["phase"],
        "실적전환방향": transition_direction,
        "실적전환강도": round(transition_strength, 2),
        "구조적실적가속": structural_acceleration,
        "가치평가국면": (
            "자산·사이클 현재가치 적응형" if adaptive_applied and adaptive_value.get("자산사이클보정적용조건충족") is True
            else "현재재무+미래증분 적응형" if adaptive_applied
            else "이익저점·회복가치 혼합" if earnings_trough
            else "구조적 성장·미래이익 혼합" if future_growth_model.get("사용가능") is True
            else "일반 가치평가"
        ),
        "이익저점보정": earnings_trough,
        "자산대비이익가치배수": round(asset_to_earnings, 3),
        "그레이엄대비이익가치배수": round(graham_to_earnings, 3),
        "분기매출성장률": round(quarter["revenue_yoy"], 2),
        "분기영업이익성장률": round(quarter["operating_yoy"], 2),
        "분기순이익성장률": round(quarter["net_yoy"], 2),
        "데이터신뢰도": data_confidence,
        "모형신뢰도": model_confidence,
        "가치신뢰도": confidence,
        "가치신뢰도등급": confidence_grade,
        "가치신뢰도정의": "자료완전성과 모형합의도이며 실제 적중률이 아님",
        "모형분산배수": round(model_dispersion, 3),
        "전체모형분산배수": round(all_model_dispersion, 3),
        "모형상세": model_detail,
        "제외모형": excluded_models,
        "이상치검사": {
            "통과": final_available,
            "상태": calculation_status,
            "사유": abnormal_reasons,
        },
        "컨센서스반영": bool(forward_direction.get("애널리스트컨센서스반영")),
        "설명": notes,
    }
