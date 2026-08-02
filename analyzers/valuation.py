"""업종 적응형 재무적정가 엔진 V6.3.

핵심 원칙
- 현재가를 적정가 산식에 앵커로 넣지 않는다.
- OpenDART 업종코드 또는 수동 종목매핑으로 업종별 배수·모형가중치를 선택한다.
- 최근 분기 급증/급락, 3년 성장, 현금흐름, 산업 선행·사이클 신호를 선행 EPS에 반영한다.
- PER·PBR·잔여이익·실적전환 모형의 합의도로 기준가와 시나리오 범위를 만든다.
- 단일 정답이 아니라 보수·기준·성장 시나리오와 신뢰도를 함께 반환한다.
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
        "label": "미디어·콘텐츠 성장형",
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


def get_periods(fundamentals_bundle: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    bundle = safe_dict(fundamentals_bundle)
    periods = safe_list(safe_dict(bundle.get("재무기간")).get("기간목록"))
    return [
        item
        for item in periods
        if isinstance(item, dict) and item.get("수집상태") == "정상"
    ]


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


def quarter_signal(periods: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not periods:
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

    latest = periods[0]
    latest_metrics = get_period_metrics(latest)
    previous = find_same_report_prior_year(latest, periods)
    previous_metrics = get_period_metrics(previous) if previous else {}

    latest_revenue = safe_float(latest_metrics.get("매출"))
    latest_operating_income = safe_float(latest_metrics.get("영업이익"))
    latest_net_income = safe_float(latest_metrics.get("순이익"))

    revenue_yoy = (
        growth_rate(latest_revenue, safe_float(previous_metrics.get("매출")))
        if previous else 0.0
    )
    operating_yoy = (
        growth_rate(latest_operating_income, safe_float(previous_metrics.get("영업이익")))
        if previous else 0.0
    )
    net_yoy = (
        growth_rate(latest_net_income, safe_float(previous_metrics.get("순이익")))
        if previous else 0.0
    )

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
        "quality": 75 if previous else 35,
        "latest_period": f"{latest.get('사업연도', '')} {latest.get('보고서명', '')}".strip(),
    }


def resolve_profile_code(
    company_info: Dict[str, Any],
    industry_bundle: Dict[str, Any],
) -> str:
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
    available = (
        analysis.get("분석상태") == "정상"
        and (mid_quality > 0 or long_quality > 0)
    )
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


def calculate_value(
    financial: Dict[str, Any],
    market: Dict[str, Any],
    fundamentals_analysis: Optional[Dict[str, Any]] = None,
    fundamentals_bundle: Optional[Dict[str, Any]] = None,
    industry_analysis: Optional[Dict[str, Any]] = None,
    industry_bundle: Optional[Dict[str, Any]] = None,
    company_info: Optional[Dict[str, Any]] = None,
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
    eps = safe_float(market.get("EPS"))
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
    profile = VALUATION_PROFILES[profile_code]
    profile_recognized = profile_code != "general" or bool(
        company_info.get("OpenDART업종코드")
    )

    periods = get_periods(fundamentals_bundle)
    quarter = quarter_signal(periods)

    earnings_analysis = safe_dict(fundamentals_analysis.get("분기실적"))
    forward_direction = safe_dict(fundamentals_analysis.get("향후이익방향대용"))
    cash_quality = safe_dict(fundamentals_analysis.get("현금흐름재무안전성"))

    earnings_signal = safe_float(earnings_analysis.get("신호"), quarter["signal"])
    forward_signal = safe_float(forward_direction.get("신호"), 0.0)
    cash_signal = safe_float(cash_quality.get("신호"), 0.0)
    industry = industry_signal(industry_analysis)

    transition_strength = weighted_average([
        {"value": abs(quarter["operating_yoy"]), "weight": 0.45},
        {"value": abs(quarter["net_yoy"]), "weight": 0.35},
        {"value": abs(operating_growth_3y * 100.0), "weight": 0.20},
    ]) or 0.0

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
        "실적 급상승 전환"
        if positive_transition and not negative_transition
        else "실적 급하락 전환"
        if negative_transition and not positive_transition
        else "실적 안정/혼합"
    )

    # 업종별 기준배수에 기업의 질과 선행신호를 더한다.
    target_per = safe_float(profile["base_per"])
    target_per += clamp((roe - 0.08) * 34.0, -2.5, 8.5)
    target_per += clamp((operating_margin - 0.08) * 18.0, -1.5, 4.5)
    target_per += clamp(revenue_growth_3y * (10.0 if profile["growth"] else 7.0), -1.5, 4.0)
    target_per += clamp(operating_growth_3y * 2.8, -1.5, 3.2)
    target_per += clamp(net_growth_3y * 2.2, -1.2, 3.0)
    target_per += clamp(earnings_signal / 100.0 * 3.2, -2.0, 3.2)
    target_per += clamp(forward_signal / 100.0 * 2.4, -1.5, 2.4)
    target_per += clamp(cash_signal / 100.0 * 1.0, -0.7, 1.0)
    target_per += clamp(industry["signal"] / 100.0 * 2.2, -1.5, 2.2)

    if debt_ratio > 2.0 and profile_code not in {"finance", "insurance"}:
        target_per -= 1.8
    elif debt_ratio > 1.0 and profile_code not in {"finance", "insurance"}:
        target_per -= 0.8

    if positive_transition:
        transition_bonus = 5.5 if profile["growth"] else 4.2
        target_per += clamp(transition_strength / 50.0, 0.7, transition_bonus)
    if negative_transition:
        target_per -= clamp(transition_strength / 45.0, 0.8, 4.0)

    target_per = clamp(
        target_per,
        safe_float(profile["per_min"]),
        safe_float(profile["per_max"]),
    )

    target_pbr = safe_float(profile["base_pbr"])
    target_pbr += clamp((roe - 0.08) * 6.0, -0.30, 2.0)
    target_pbr += clamp((operating_margin - 0.08) * 2.8, -0.18, 0.45)
    target_pbr += clamp(revenue_growth_3y * 1.2, -0.15, 0.35)
    target_pbr += clamp(industry["signal"] / 100.0 * 0.18, -0.12, 0.18)
    if positive_transition:
        target_pbr += 0.12 if profile["growth"] else 0.08
    if debt_ratio > 2.0 and profile_code not in {"finance", "insurance"}:
        target_pbr -= 0.20
    target_pbr = clamp(
        target_pbr,
        safe_float(profile["pbr_min"]),
        safe_float(profile["pbr_max"]),
    )

    # 시장 EPS를 그대로 쓰지 않고 최신 실적·산업 국면으로 선행 EPS를 보정한다.
    forward_eps = eps if eps > 0 else 0.0
    eps_multiplier = 0.0
    if forward_eps > 0:
        eps_multiplier = 1.0
        eps_multiplier += clamp(quarter["operating_yoy"] / 100.0 * 0.28, -0.22, 0.42)
        eps_multiplier += clamp(quarter["net_yoy"] / 100.0 * 0.18, -0.16, 0.32)
        eps_multiplier += clamp(forward_signal / 100.0 * 0.20, -0.10, 0.20)
        eps_multiplier += clamp(industry["signal"] / 100.0 * 0.10, -0.08, 0.10)
        eps_multiplier += 0.08 if positive_transition and operating_margin >= 0.10 else 0.0
        if profile["cyclical"] and positive_transition:
            # 사이클 고점 이익을 영구화하지 않되 최근 구조적 전환은 충분히 반영한다.
            eps_multiplier -= 0.03
        if negative_transition:
            eps_multiplier -= 0.08
        eps_multiplier = clamp(
            eps_multiplier,
            safe_float(profile["eps_floor"]),
            safe_float(profile["eps_cap"]),
        )
        forward_eps *= eps_multiplier

    per_value = forward_eps * target_per if forward_eps > 0 else 0.0
    pbr_value = bps * target_pbr if bps > 0 else 0.0

    residual_value = 0.0
    if bps > 0 and roe > 0:
        cost_of_equity = 0.115 if debt_ratio > 1.5 else 0.105 if debt_ratio > 0.8 else 0.095
        persistence = 0.72 if positive_transition else 0.58 if roe >= 0.12 else 0.36
        if profile_code in {"finance", "insurance", "real_estate", "holding_company"}:
            persistence += 0.08
        if profile["cyclical"]:
            persistence -= 0.05
        excess_return = max(0.0, roe - cost_of_equity)
        residual_value = bps + (
            bps
            * excess_return
            * clamp(persistence, 0.20, 0.85)
            / max(0.035, cost_of_equity - 0.02)
        )

    transition_value = 0.0
    if eps > 0:
        transition_per = target_per
        if positive_transition:
            transition_per += clamp(
                transition_strength / 40.0,
                1.2,
                6.5 if profile["growth"] else 5.2,
            )
        if negative_transition:
            transition_per -= clamp(transition_strength / 45.0, 1.0, 4.0)
        transition_per = clamp(
            transition_per,
            safe_float(profile["per_min"]),
            safe_float(profile["per_max"]) + (5.0 if profile["growth"] else 3.0),
        )
        transition_multiplier = (
            1.10 if positive_transition else 0.94 if negative_transition else 1.0
        )
        transition_value = eps * transition_per * transition_multiplier

    model_values = {
        "PER 선행이익가치": per_value,
        "PBR 자산가치": pbr_value,
        "잔여이익가치": residual_value,
        "실적전환보정가": transition_value,
    }
    model_weights = safe_dict(profile["weights"])
    weight_by_name = {
        "PER 선행이익가치": safe_float(model_weights.get("per")),
        "PBR 자산가치": safe_float(model_weights.get("pbr")),
        "잔여이익가치": safe_float(model_weights.get("residual")),
        "실적전환보정가": safe_float(model_weights.get("transition")),
    }

    positive_values = [value for value in model_values.values() if value > 0]
    model_median = median(positive_values)
    filtered_models = []
    excluded_models = []
    for name, value in model_values.items():
        if value <= 0:
            continue
        if model_median and not (
            model_median * safe_float(profile["model_floor"])
            <= value
            <= model_median * safe_float(profile["model_ceiling"])
        ):
            excluded_models.append(name)
            continue
        filtered_models.append({
            "name": name,
            "value": value,
            "weight": weight_by_name[name],
        })

    # 필터 때문에 모형이 2개 미만이면 원래 유효 모형을 복구한다.
    if len(filtered_models) < 2:
        filtered_models = [
            {"name": name, "value": value, "weight": weight_by_name[name]}
            for name, value in model_values.items()
            if value > 0
        ]
        excluded_models = []

    weighted_value = weighted_average(filtered_models) or 0.0
    filtered_values = [safe_float(row.get("value")) for row in filtered_models]
    filtered_median = median(filtered_values) or weighted_value
    basic = weighted_average([
        {"value": weighted_value, "weight": 0.88},
        {"value": filtered_median, "weight": 0.12},
    ]) or weighted_value

    # 극단적인 min/max가 화면 범위를 망치지 않도록 사분위수와 업종별 시나리오 계수를 함께 사용한다.
    q25 = percentile(filtered_values, 0.25) or basic
    q75 = percentile(filtered_values, 0.75) or basic
    conservative = max(
        q25 * 0.96,
        basic * safe_float(profile["downside"]),
    )
    growth_value = min(
        q75 * (1.08 if positive_transition else 1.03),
        basic * safe_float(profile["upside"]),
    )
    conservative = min(conservative, basic)
    growth_value = max(growth_value, basic)

    financial_value = basic
    gap = ((basic - price) / price * 100.0) if price > 0 and basic > 0 else 0.0

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

    model_dispersion = 0.0
    if len(filtered_values) >= 2 and min(filtered_values) > 0:
        model_dispersion = max(filtered_values) / min(filtered_values)

    earnings_quality = safe_float(earnings_analysis.get("데이터품질"), quarter["quality"])
    cash_quality_score = safe_float(cash_quality.get("데이터품질"), 0.0)
    consensus_available = bool(
        forward_direction.get("애널리스트컨센서스반영")
        or safe_float(forward_direction.get("컨센서스데이터품질"), 0.0) > 0
    )

    confidence = 34
    if price > 0 and eps > 0 and bps > 0:
        confidence += 10
    elif price > 0 and (eps > 0 or bps > 0):
        confidence += 5
    if roe != 0 or operating_margin != 0 or net_margin != 0:
        confidence += 7
    if len(periods) >= 6:
        confidence += 12
    elif len(periods) >= 4:
        confidence += 9
    elif periods:
        confidence += 5
    if quarter["quality"] >= 70:
        confidence += 8
    elif quarter["quality"] >= 35:
        confidence += 4
    if earnings_quality >= 80:
        confidence += 6
    elif earnings_quality >= 50:
        confidence += 3
    if cash_quality_score >= 80:
        confidence += 5
    elif cash_quality_score >= 50:
        confidence += 3
    if profile_recognized:
        confidence += 6
    if industry["available"]:
        confidence += 6
    if consensus_available:
        confidence += 5
    if len(filtered_models) >= 4:
        confidence += 4
    if model_dispersion > 0:
        if model_dispersion <= 1.35:
            confidence += 7
        elif model_dispersion <= 1.70:
            confidence += 4
        elif model_dispersion <= 2.20:
            confidence += 1
        elif model_dispersion >= 3.00:
            confidence -= 8
        else:
            confidence -= 3
    if transition_direction == "실적 안정/혼합" and transition_strength < 25:
        confidence += 4
    elif transition_direction == "실적 급상승 전환":
        confidence -= 3
    elif transition_direction == "실적 급하락 전환":
        confidence -= 5

    confidence = int(clamp(confidence, 30, 95))
    confidence_cap = 95
    confidence_cap_reasons = []
    if not profile_recognized:
        confidence_cap = min(confidence_cap, 79)
        confidence_cap_reasons.append("OpenDART 업종분류 미확보")
    if not industry["available"]:
        confidence_cap = min(confidence_cap, 84)
        confidence_cap_reasons.append("산업 선행·사이클 미반영")
    if not consensus_available:
        confidence_cap = min(confidence_cap, 84)
        confidence_cap_reasons.append("애널리스트 컨센서스 미반영")
    if transition_direction != "실적 안정/혼합":
        confidence_cap = min(confidence_cap, 82)
    confidence = min(confidence, confidence_cap)
    confidence_grade = (
        "A" if confidence >= 85 else
        "B" if confidence >= 70 else
        "C" if confidence >= 55 else
        "D"
    )

    # 세 시나리오 확률은 가격 예측이 아니라 어떤 가치 시나리오에 무게를 둘지 표시한다.
    growth_probability = 34.0
    growth_probability += clamp(earnings_signal * 0.16, -14.0, 16.0)
    growth_probability += clamp(forward_signal * 0.12, -10.0, 12.0)
    growth_probability += clamp(industry["signal"] * 0.10, -8.0, 10.0)
    growth_probability += 5.0 if positive_transition else -5.0 if negative_transition else 0.0
    growth_probability = clamp(growth_probability, 12.0, 68.0)
    conservative_probability = 33.0
    conservative_probability -= clamp(earnings_signal * 0.10, -10.0, 10.0)
    conservative_probability -= clamp(industry["signal"] * 0.06, -6.0, 6.0)
    conservative_probability += 5.0 if negative_transition else -3.0 if positive_transition else 0.0
    conservative_probability = clamp(conservative_probability, 12.0, 62.0)
    base_probability = max(10.0, 100.0 - growth_probability - conservative_probability)
    total_probability = growth_probability + conservative_probability + base_probability
    conservative_probability = conservative_probability / total_probability * 100.0
    base_probability = base_probability / total_probability * 100.0
    growth_probability = growth_probability / total_probability * 100.0

    notes = [
        f"{profile['label']} 업종 프로필의 기준배수와 모형가중치를 적용했습니다.",
        "현재가는 적정가 계산에 앵커로 사용하지 않고 계산 후 차이 비교에만 사용했습니다.",
    ]
    if positive_transition:
        notes.append("최근 분기 이익 급증을 선행 EPS와 실적전환 모형에 반영했습니다.")
    if negative_transition:
        notes.append("최근 분기 이익 둔화를 선행 EPS와 목표배수에 보수적으로 반영했습니다.")
    if periods:
        notes.append(f"OpenDART 최신 분기 {quarter['latest_period']} 자료를 반영했습니다.")
    if industry["available"]:
        notes.append(
            f"산업 중기 {industry['mid']:.2f}, 장기 {industry['long']:.2f} 신호를 배수와 선행 EPS에 반영했습니다."
        )
    if excluded_models:
        notes.append("모형 중앙값에서 과도하게 벗어난 값은 기준가 가중평균에서 제외했습니다.")

    model_detail = []
    included_names = {row["name"] for row in filtered_models}
    for name, value in model_values.items():
        model_detail.append({
            "모형": name,
            "값": round(value, 2) if value > 0 else 0.0,
            "기본가중치": round(weight_by_name[name], 4),
            "기준가반영": name in included_names,
        })

    return {
        "가치평가엔진버전": "6.4.0-all-industry-signal-bridge",
        "현재가": price,
        "실제PER": actual_per,
        "실제PBR": actual_pbr,
        "EPS": eps,
        "BPS": bps,
        "선행EPS": round(forward_eps, 2) if forward_eps > 0 else 0.0,
        "선행EPS보정배수": round(eps_multiplier, 4) if eps_multiplier > 0 else 0.0,
        "목표PER": round(target_per, 2),
        "목표PBR": round(target_pbr, 2),
        "PER기준적정가": round(per_value, 2),
        "PBR기준적정가": round(pbr_value, 2),
        "잔여이익가치": round(residual_value, 2),
        "실적전환보정가": round(transition_value, 2),
        "재무적정가": round(financial_value, 2),
        "기본적정가": round(basic, 2),
        "보수적적정가": round(conservative, 2),
        "성장적정가": round(growth_value, 2),
        "현재가대비": round(gap, 2),
        "판단": judgment,
        "가치평가산업코드": profile_code,
        "가치평가산업프로필": profile["label"],
        "산업분류출처": company_info.get("산업분류출처", "내부 일반분류"),
        "OpenDART업종코드": company_info.get("OpenDART업종코드", ""),
        "산업신호반영": industry["available"],
        "산업종합신호": round(industry["signal"], 2),
        "산업국면": industry["phase"],
        "실적전환방향": transition_direction,
        "실적전환강도": round(transition_strength, 2),
        "분기매출성장률": round(quarter["revenue_yoy"], 2),
        "분기영업이익성장률": round(quarter["operating_yoy"], 2),
        "분기순이익성장률": round(quarter["net_yoy"], 2),
        "가치신뢰도": confidence,
        "가치신뢰도등급": confidence_grade,
        "가치신뢰도상한": confidence_cap,
        "가치신뢰도상한사유": confidence_cap_reasons,
        "컨센서스반영": consensus_available,
        "모형분산배수": round(model_dispersion, 3),
        "모형상세": model_detail,
        "제외모형": excluded_models,
        "시나리오확률": {
            "보수적": round(conservative_probability, 1),
            "기준": round(base_probability, 1),
            "성장": round(growth_probability, 1),
        },
        "설명": notes,
    }
