"""재무적정가 엔진 V6.6.2 · 가치평가 계약 v3.

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

VALUATION_CONTRACT_VERSION = "3.0"
VALUATION_ENGINE_VERSION = "6.6.2-valuation-contract-v3"

# 복합기업은 사업부 세부 공시가 자동 수집되지 않으면 진짜 SOTP를 만들 수 없다.
# 아래 설정은 '사업부 대용 가치합산'을 위한 보수적 복합배수이며, 출력에 대용모형임을 명시한다.
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


def build_ttm(quarters: List[Dict[str, Any]]) -> Dict[str, Any]:
    if len(quarters) < 4:
        return {"available": False, "quality": 0, "metrics": {}, "period": ""}
    selected = quarters[:4]
    keys = [int(row.get("기간키", 0)) for row in selected]
    contiguous = all(keys[index] - keys[index + 1] == 1 for index in range(3))
    converted = all(bool(row.get("단독분기변환")) for row in selected)
    positive_revenue = all(
        safe_float(safe_dict(row.get("지표")).get("매출")) > 0
        for row in selected
    )
    if not contiguous or not converted or not positive_revenue:
        return {
            "available": False,
            "quality": 20 if contiguous else 10,
            "metrics": {},
            "period": "",
            "reason": (
                "단독분기 변환 불완전" if not converted
                else "분기 매출자료 불완전" if not positive_revenue
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
    return {"available": True, "quality": 95, "metrics": metrics, "period": period}


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

    annual = annual_periods(periods)
    market_eps = safe_float(market.get("EPS"))
    if annual and market_eps > 0:
        annual_net = safe_float(get_period_metrics(annual[0]).get("순이익"))
        if annual_net > 0:
            implied = annual_net / market_eps
            if implied > 100000:
                candidates.append({"value": implied, "source": "연간순이익÷KIS EPS", "quality": 88})

    bps = safe_float(market.get("BPS"))
    latest_equity = 0.0
    for period in periods:
        latest_equity = safe_float(get_period_metrics(period).get("자본총계"))
        if latest_equity > 0:
            break
    if bps > 0 and latest_equity > 0:
        implied = latest_equity / bps
        if implied > 100000:
            candidates.append({"value": implied, "source": "자본총계÷KIS BPS", "quality": 86})

    market_cap = safe_float(market.get("시가총액"))
    market_price = safe_float(market.get("현재가"))
    if market_cap > 0 and market_price > 0:
        # KIS hts_avls는 억원, Yahoo marketCap은 원 단위일 수 있어 두 단위를 모두
        # 후보화한 뒤 현실적 주식 수 범위와 다른 후보의 일치도로 선택한다.
        for multiplier, label in (
            (1.0, "시가총액÷현재가(원단위)"),
            (100_000_000.0, "시가총액÷현재가(KIS억원)"),
        ):
            implied = market_cap * multiplier / market_price
            if 100_000 <= implied <= 100_000_000_000:
                candidates.append({
                    "value": implied,
                    "source": label,
                    "quality": 82,
                })

    if not candidates:
        return {"value": 0.0, "source": "미확보", "quality": 0, "candidates": []}

    values = sorted(row["value"] for row in candidates)
    center = median(values) or values[0]
    consistent = [row for row in candidates if 0.70 <= row["value"] / center <= 1.30]
    selected = consistent or candidates
    total_quality = sum(row["quality"] for row in selected)
    value = sum(row["value"] * row["quality"] for row in selected) / max(total_quality, 1)
    quality = min(98, int(sum(row["quality"] for row in selected) / len(selected)))
    return {
        "value": value,
        "source": "+".join(row["source"] for row in selected),
        "quality": quality,
        "candidates": [{"출처": row["source"], "주식수": round(row["value"])} for row in candidates],
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


def _normalized_eps(annual_eps: List[Dict[str, Any]], market_eps: float) -> float:
    weights = (0.52, 0.30, 0.18, 0.10)
    rows = [
        {"value": row.get("eps", 0.0), "weight": weights[index]}
        for index, row in enumerate(annual_eps[:4])
    ]
    normalized = weighted_average_signed(rows) or 0.0
    # 손실연도를 삭제해 정상화 EPS가 과대평가되는 문제를 막는다. 다만 최신 KIS EPS가
    # 양수이고 과거 가중평균이 음수일 때는 완전한 0 대신 절반만 잠정 반영한다.
    if normalized <= 0 and market_eps > 0:
        normalized = market_eps * 0.50
    elif normalized > 0 and market_eps > 0:
        normalized = normalized * 0.85 + market_eps * 0.15
    return normalized


def _cost_of_equity(debt_ratio: float, profile_code: str) -> float:
    base = 0.095
    if profile_code in {"finance", "insurance", "utilities", "telecom"}:
        base -= 0.005
    if debt_ratio > 2.0:
        base += 0.020
    elif debt_ratio > 1.0:
        base += 0.010
    return clamp(base, 0.085, 0.125)


def _model_row(name: str, value: float, weight: float, role: str = "기준") -> Dict[str, Any]:
    return {"name": name, "value": value, "weight": weight, "role": role}


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

    periods = get_periods(fundamentals_bundle)
    quarters = build_standalone_quarters(periods)
    ttm = build_ttm(quarters)
    quarter = quarter_signal(periods)
    share_info = infer_share_count(market, periods, company_info, fundamentals_bundle)
    shares = safe_float(share_info.get("value"))
    annual_eps = _annual_eps_series(periods, shares)
    normalized_eps = _normalized_eps(annual_eps, market_eps)
    ttm_eps = safe_float(safe_dict(ttm.get("metrics")).get("순이익")) / shares if ttm.get("available") and shares > 0 else 0.0
    latest_quarter_eps = quarter["latest_net_income"] / shares if shares > 0 else 0.0
    run_rate_eps = latest_quarter_eps * 4.0 if latest_quarter_eps > 0 else 0.0

    # GitHub에서는 KIS를 비활성화하므로 Yahoo 현재가만 확보되고 EPS·BPS가
    # 비어 있을 수 있다. 이때 DART TTM/자본총계와 주식수로 주당지표를 복원한다.
    if market_eps <= 0:
        market_eps = ttm_eps if ttm_eps > 0 else normalized_eps
    latest_equity = 0.0
    for period in periods:
        latest_equity = safe_float(get_period_metrics(period).get("자본총계"))
        if latest_equity > 0:
            break
    if bps <= 0 and shares > 0 and latest_equity > 0:
        bps = latest_equity / shares
    if actual_per <= 0 and price > 0 and market_eps > 0:
        actual_per = price / market_eps
    if actual_pbr <= 0 and price > 0 and bps > 0:
        actual_pbr = price / bps

    profile_code = resolve_profile_code(company_info, industry_bundle)
    profile = dict(VALUATION_PROFILES[profile_code])
    stock_code = str(company_info.get("종목코드") or company_info.get("KIS종목코드") or "").zfill(6)
    complex_config = COMPLEX_COMPANY_CONFIG.get(stock_code)
    profile_recognized = profile_code != "general" or bool(company_info.get("OpenDART업종코드"))

    earnings_analysis = safe_dict(fundamentals_analysis.get("분기실적"))
    forward_direction = safe_dict(fundamentals_analysis.get("향후이익방향대용"))
    cash_quality = safe_dict(fundamentals_analysis.get("현금흐름재무안전성"))
    earnings_signal = safe_float(earnings_analysis.get("신호"), quarter["signal"])
    forward_signal = safe_float(forward_direction.get("신호"), 0.0)
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
    if base_forward_eps <= 0:
        base_forward_eps = market_eps

    growth_cap = 0.18 if profile.get("cyclical") else 0.24 if profile.get("growth") else 0.14
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

    # 중간 업황 회복 시 정상화 이익이 창출할 수 있는 가치. 현재가를 사용하지 않는다.
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
        models.extend([
            _model_row("선행·정상화 이익가치", earnings_value, safe_float(complex_config.get("earnings_weight"), 0.58)),
            _model_row("복합기업 대용 가치합산", complex_proxy_value, safe_float(complex_config.get("complex_weight"), 0.24)),
            _model_row("실적전환 가치", transition_value, 0.12),
            _model_row("FCF 가치", fcf_value, safe_float(complex_config.get("fcf_weight"), 0.06)),
            _model_row("PBR 하단가치", pbr_value, safe_float(complex_config.get("asset_weight"), 0.06), "하단"),
            _model_row("잔여이익 하단가치", residual_value, safe_float(complex_config.get("residual_weight"), 0.06), "하단"),
            _model_row("그레이엄 결합가치", graham_value, 0.04, "보조"),
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
            # 성장·사이클 기업의 하단모형은 보수 시나리오에는 남기되 기준가 가중치에서 과도한 영향 배제.
            if earnings_value > 0 and profile_code in {"semiconductor", "battery", "software_platform", "media_entertainment", "biotechnology"}:
                if row["role"] == "하단" and row["value"] < earnings_value * 0.42:
                    excluded_models.append(row["name"])
                    continue
            if earnings_value > 0 and not (earnings_value * 0.28 <= row["value"] <= earnings_value * 3.2):
                excluded_models.append(row["name"])
                continue
            basis_models.append(row)

    if len(basis_models) < 2:
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
        high_anchor = max(earnings_value, transition_value, complex_proxy_value, q75)
        growth_value = min(high_anchor * 1.08, basic * safe_float(profile.get("upside"), 1.35)) if basic > 0 else high_anchor
        growth_value = max(growth_value, basic)

    basis_dispersion = max(basis_values) / min(basis_values) if len(basis_values) >= 2 and min(basis_values) > 0 else 0.0
    all_model_dispersion = max(all_values) / min(all_values) if len(all_values) >= 2 and min(all_values) > 0 else 0.0
    model_dispersion = basis_dispersion
    implied_per = basic / valuation_eps if basic > 0 and valuation_eps > 0 else 0.0
    implied_pbr = basic / bps if basic > 0 and bps > 0 else 0.0
    gap = ((basic - price) / price * 100.0) if price > 0 and basic > 0 else 0.0

    abnormal_reasons: List[str] = []
    if not ttm.get("available"):
        abnormal_reasons.append("연속 4개 단독분기 TTM 미확보")
    if shares <= 0:
        abnormal_reasons.append("주식수 미확보")
    if valuation_eps <= 0:
        abnormal_reasons.append("양(+)의 평가 EPS 미확보")
    if not earnings_trough and implied_per > 0 and not (per_min * 0.75 <= implied_per <= per_max * 1.30):
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

    fatal = shares <= 0 or valuation_eps <= 0 or basic <= 0
    review = (not fatal) and any(
        reason in abnormal_reasons
        for reason in (
            "연속 4개 단독분기 TTM 미확보",
            "최종가 암시 PER이 업종 허용범위를 벗어남",
            "이익저점 기준가의 암시 PBR이 업종 허용범위를 벗어남",
            "모형 간 가치 차이가 4배 이상",
            "이익저점 모형 간 가치 차이가 5.5배 이상",
            "시장가격과 3배 이상 괴리하면서 데이터·모형 경고 동시 발생",
        )
    )
    calculation_status = "산출불가" if fatal else "검토필요" if review else "정상"
    final_available = not fatal and not review

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
        judgment = "판정 보류"

    data_confidence = 30
    data_confidence += 18 if ttm.get("available") else 5 if periods else 0
    data_confidence += min(15, len(periods) * 2)
    data_confidence += 12 if share_info.get("quality", 0) >= 85 else 6 if shares > 0 else 0
    data_confidence += 8 if bps > 0 else 0
    data_confidence += 8 if industry["available"] else 0
    data_confidence += 5 if safe_float(cash_quality.get("데이터품질")) >= 70 else 0
    data_confidence = int(clamp(data_confidence, 25, 95))

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
        "KIS EPS는 미래이익 자체가 아니라 발행주식수 교차추정과 보조자료로만 사용했습니다.",
        "현재가는 적정가 산식에 넣지 않고 계산 완료 후 괴리 검증에만 사용했습니다.",
        f"{profile.get('label', profile_code)} 업종 프로필을 적용했습니다.",
    ]
    if complex_config:
        notes.append("사업부 세부 손익 자동수집이 없어 진짜 SOTP가 아닌 복합기업 대용 가치합산을 적용했습니다.")
    if earnings_trough:
        notes.append("이익저점 국면을 감지해 현재 이익가치보다 자산·그레이엄·정상화 회복가치의 비중을 높였습니다.")
    if excluded_models:
        notes.append("기업 유형에 부적합하거나 독립 가치앵커에서 과도하게 벗어난 모형은 기준가에서 제외했습니다.")

    return {
        "가치평가계약버전": VALUATION_CONTRACT_VERSION,
        "가치평가엔진버전": VALUATION_ENGINE_VERSION,
        "산출상태": calculation_status,
        "최종값사용가능": final_available,
        "최종값출처": "Python 가치평가 계약 v3",
        "현재가": price,
        "실제PER": actual_per,
        "실제PBR": actual_pbr,
        "EPS": market_eps,
        "BPS": bps,
        "발행주식수추정": round(shares) if shares > 0 else 0,
        "발행주식수출처": share_info.get("source", ""),
        "발행주식수품질": share_info.get("quality", 0),
        "발행주식수후보": share_info.get("candidates", []),
        "TTMEPS": round(ttm_eps, 2) if ttm_eps > 0 else 0.0,
        "정상화EPS": round(normalized_eps, 2) if normalized_eps > 0 else 0.0,
        "분기런레이트EPS": round(run_rate_eps, 2) if run_rate_eps > 0 else 0.0,
        "FY1예상EPS": round(fy1_eps, 2) if fy1_eps > 0 else 0.0,
        "FY2예상EPS": round(fy2_eps, 2) if fy2_eps > 0 else 0.0,
        "평가EPS": round(valuation_eps, 2) if valuation_eps > 0 else 0.0,
        "선행EPS": round(fy1_eps, 2) if fy1_eps > 0 else 0.0,
        "FY1성장률": round(fy1_growth * 100.0, 2),
        "FY2성장률": round(fy2_growth * 100.0, 2),
        "TTM기준기간": ttm.get("period", ""),
        "TTM데이터품질": ttm.get("quality", 0),
        "목표PER": round(target_per, 2),
        "목표PBR": round(target_pbr, 2),
        "암시PER": round(implied_per, 2) if implied_per > 0 else 0.0,
        "암시PBR": round(implied_pbr, 2) if implied_pbr > 0 else 0.0,
        "PER기준적정가": round(earnings_value, 2),
        "PBR기준적정가": round(pbr_value, 2),
        "그레이엄가치": round(graham_value, 2),
        "정상화회복가치": round(normalized_recovery_value, 2),
        "잔여이익가치": round(residual_value, 2),
        "FCF가치": round(fcf_value, 2),
        "실적전환보정가": round(transition_value, 2),
        "복합기업대용가치합산": round(complex_proxy_value, 2),
        "순현금주당가치": round(net_cash_per_share, 2),
        "재무적정가": round(basic, 2),
        "기본적정가": round(basic, 2),
        "보수적적정가": round(conservative, 2),
        "성장적정가": round(growth_value, 2),
        "현재가대비": round(gap, 2),
        "판단": judgment,
        "가치평가산업코드": profile_code,
        "가치평가산업프로필": complex_config.get("label") if complex_config else profile.get("label"),
        "복합기업대용모형": bool(complex_config),
        "진짜SOTP자료확보": False if complex_config else None,
        "산업분류출처": company_info.get("산업분류출처", "내부 일반분류"),
        "OpenDART업종코드": company_info.get("OpenDART업종코드", ""),
        "산업신호반영": industry["available"],
        "산업종합신호": round(industry["signal"], 2),
        "산업국면": industry["phase"],
        "실적전환방향": transition_direction,
        "실적전환강도": round(transition_strength, 2),
        "가치평가국면": "이익저점·회복가치 혼합" if earnings_trough else "일반 가치평가",
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
