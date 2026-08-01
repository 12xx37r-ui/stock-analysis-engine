from typing import Any, Dict, List, Optional


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, "", "-", "--"):
            return default
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def growth_rate(current: float, previous: float) -> float:
    current = safe_float(current)
    previous = safe_float(previous)

    if previous == 0:
        return 0.0

    return ((current / abs(previous)) - (1.0 if previous > 0 else -1.0)) * 100.0


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def weighted_average(rows: List[Dict[str, float]]) -> Optional[float]:
    valid = [row for row in rows if safe_float(row.get("value"), 0.0) > 0 and safe_float(row.get("weight"), 0.0) > 0]
    if not valid:
        return None

    total_weight = sum(safe_float(row.get("weight"), 0.0) for row in valid)
    if total_weight <= 0:
        return None

    return sum(
        safe_float(row.get("value"), 0.0) * safe_float(row.get("weight"), 0.0)
        for row in valid
    ) / total_weight


def get_periods(fundamentals_bundle: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    bundle = safe_dict(fundamentals_bundle)
    periods = safe_list(
        safe_dict(
            bundle.get("재무기간")
        ).get("기간목록")
    )
    return [
        item for item in periods
        if isinstance(item, dict) and item.get("수집상태") == "정상"
    ]


def get_period_metrics(period: Dict[str, Any]) -> Dict[str, Any]:
    return safe_dict(period.get("지표"))


def find_same_report_prior_year(latest: Dict[str, Any], periods: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    latest_year = int(safe_float(latest.get("사업연도"), 0))
    target_year = latest_year - 1
    target_code = str(latest.get("보고서코드", "")).strip()

    for period in periods:
        if int(safe_float(period.get("사업연도"), 0)) == target_year and str(period.get("보고서코드", "")).strip() == target_code:
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
        }

    latest = periods[0]
    latest_metrics = get_period_metrics(latest)
    previous = find_same_report_prior_year(latest, periods)
    previous_metrics = get_period_metrics(previous) if previous else {}

    latest_revenue = safe_float(latest_metrics.get("매출"))
    latest_operating_income = safe_float(latest_metrics.get("영업이익"))
    latest_net_income = safe_float(latest_metrics.get("순이익"))

    revenue_yoy = growth_rate(latest_revenue, safe_float(previous_metrics.get("매출"))) if previous else 0.0
    operating_yoy = growth_rate(latest_operating_income, safe_float(previous_metrics.get("영업이익"))) if previous else 0.0
    net_yoy = growth_rate(latest_net_income, safe_float(previous_metrics.get("순이익"))) if previous else 0.0

    signal = (
        clamp(revenue_yoy / 40.0, -1.0, 1.0) * 20.0 +
        clamp(operating_yoy / 60.0, -1.0, 1.0) * 45.0 +
        clamp(net_yoy / 80.0, -1.0, 1.0) * 35.0
    )

    quality = 75 if previous else 35

    return {
        "latest_revenue": latest_revenue,
        "latest_operating_income": latest_operating_income,
        "latest_net_income": latest_net_income,
        "revenue_yoy": revenue_yoy,
        "operating_yoy": operating_yoy,
        "net_yoy": net_yoy,
        "signal": clamp(signal, -100.0, 100.0),
        "quality": quality,
        "latest_period": f"{latest.get('사업연도', '')} {latest.get('보고서명', '')}".strip(),
    }


def calculate_value(
    financial: Dict[str, Any],
    market: Dict[str, Any],
    fundamentals_analysis: Optional[Dict[str, Any]] = None,
    fundamentals_bundle: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    financial = safe_dict(financial)
    market = safe_dict(market)
    fundamentals_analysis = safe_dict(fundamentals_analysis)
    fundamentals_bundle = safe_dict(fundamentals_bundle)

    metrics = safe_dict(financial.get("재무지표"))
    growth = safe_dict(financial.get("성장지표"))

    price = safe_float(market.get("현재가"))
    eps = safe_float(market.get("EPS"))
    bps = safe_float(market.get("BPS"))
    per = safe_float(market.get("PER"))
    pbr = safe_float(market.get("PBR"))

    roe = safe_float(metrics.get("ROE")) / 100.0
    operating_margin = safe_float(metrics.get("영업이익률")) / 100.0
    net_margin = safe_float(metrics.get("순이익률")) / 100.0
    debt_ratio = safe_float(metrics.get("부채비율")) / 100.0

    revenue_growth_3y = safe_float(growth.get("매출3년성장률")) / 100.0
    operating_growth_3y = safe_float(growth.get("영업이익3년성장률")) / 100.0
    net_growth_3y = safe_float(growth.get("순이익3년성장률")) / 100.0

    periods = get_periods(fundamentals_bundle)
    quarter = quarter_signal(periods)

    earnings_analysis = safe_dict(fundamentals_analysis.get("분기실적"))
    forward_direction = safe_dict(fundamentals_analysis.get("향후이익방향대용"))
    cash_quality = safe_dict(fundamentals_analysis.get("현금흐름재무안전성"))

    earnings_signal = safe_float(earnings_analysis.get("신호"), quarter["signal"])
    forward_signal = safe_float(forward_direction.get("신호"), 0.0)
    cash_signal = safe_float(cash_quality.get("신호"), 0.0)

    transition_strength = weighted_average([
        {"value": abs(quarter["operating_yoy"]), "weight": 0.45},
        {"value": abs(quarter["net_yoy"]), "weight": 0.35},
        {"value": abs(safe_float(operating_growth_3y) * 100.0), "weight": 0.20},
    ]) or 0.0

    positive_transition = (
        quarter["operating_yoy"] >= 25.0 or
        quarter["net_yoy"] >= 35.0 or
        earnings_signal >= 25.0 or
        forward_signal >= 25.0
    )

    negative_transition = (
        quarter["operating_yoy"] <= -20.0 or
        quarter["net_yoy"] <= -25.0 or
        earnings_signal <= -25.0 or
        forward_signal <= -25.0
    )

    transition_direction = (
        "실적 급상승 전환" if positive_transition and not negative_transition
        else "실적 급하락 전환" if negative_transition and not positive_transition
        else "실적 안정/혼합"
    )

    target_per = 10.5
    target_per += clamp((roe - 0.08) * 34.0, -2.5, 8.5)
    target_per += clamp((operating_margin - 0.08) * 18.0, -1.5, 4.5)
    target_per += clamp(revenue_growth_3y * 8.0, -1.0, 2.5)
    target_per += clamp(operating_growth_3y * 3.0, -1.5, 3.0)
    target_per += clamp(net_growth_3y * 2.5, -1.0, 3.0)
    target_per += clamp(earnings_signal / 100.0 * 3.5, -2.0, 3.5)
    target_per += clamp(forward_signal / 100.0 * 2.5, -1.5, 2.5)
    target_per += clamp(cash_signal / 100.0 * 1.2, -0.8, 1.2)

    if debt_ratio > 2.0:
        target_per -= 1.8
    elif debt_ratio > 1.0:
        target_per -= 0.8

    if positive_transition:
        target_per += clamp(transition_strength / 50.0, 0.8, 4.5)
    if negative_transition:
        target_per -= clamp(transition_strength / 45.0, 0.8, 4.0)

    target_per = clamp(target_per, 7.0, 30.0)

    target_pbr = 0.95
    target_pbr += clamp((roe - 0.08) * 6.0, -0.25, 1.9)
    target_pbr += clamp((operating_margin - 0.08) * 3.0, -0.15, 0.40)
    target_pbr += clamp(revenue_growth_3y * 1.4, -0.15, 0.35)
    if positive_transition:
        target_pbr += 0.15
    if debt_ratio > 2.0:
        target_pbr -= 0.20
    target_pbr = clamp(target_pbr, 0.55, 3.20)

    forward_eps = eps if eps > 0 else 0.0
    if forward_eps > 0:
        eps_multiplier = 1.0
        eps_multiplier += clamp(quarter["operating_yoy"] / 100.0 * 0.28, -0.20, 0.40)
        eps_multiplier += clamp(quarter["net_yoy"] / 100.0 * 0.18, -0.15, 0.30)
        eps_multiplier += clamp(forward_signal / 100.0 * 0.20, -0.08, 0.20)
        eps_multiplier += 0.08 if positive_transition and operating_margin >= 0.10 else 0.0
        if negative_transition:
            eps_multiplier -= 0.08
        eps_multiplier = clamp(eps_multiplier, 0.80, 1.65)
        forward_eps *= eps_multiplier

    per_value = forward_eps * target_per if forward_eps > 0 else 0.0
    pbr_value = bps * target_pbr if bps > 0 else 0.0

    residual_value = 0.0
    if bps > 0 and roe > 0:
        cost_of_equity = 0.115 if debt_ratio > 1.5 else 0.105 if debt_ratio > 0.8 else 0.095
        persistence = 0.70 if positive_transition else 0.55 if roe >= 0.12 else 0.35
        excess_return = max(0.0, roe - cost_of_equity)
        residual_value = bps + (bps * excess_return * persistence / max(0.035, cost_of_equity - 0.02))

    transition_value = 0.0
    if eps > 0:
        transition_per = target_per
        if positive_transition:
            transition_per += clamp(transition_strength / 40.0, 1.5, 5.5)
        if negative_transition:
            transition_per -= clamp(transition_strength / 45.0, 1.0, 4.0)
        transition_per = clamp(transition_per, 7.0, 34.0)
        transition_multiplier = 1.10 if positive_transition else 0.94 if negative_transition else 1.0
        transition_value = eps * transition_per * transition_multiplier

    financial_value = weighted_average([
        {"value": per_value, "weight": 0.42},
        {"value": pbr_value, "weight": 0.18},
        {"value": residual_value, "weight": 0.18},
        {"value": transition_value, "weight": 0.22},
    ]) or 0.0

    if positive_transition and financial_value > 0:
        financial_value *= 1.04

    available_values = [value for value in [per_value, pbr_value, residual_value, transition_value, financial_value] if value > 0]
    available_values.sort()

    if available_values:
        if len(available_values) % 2 == 1:
            basic = available_values[len(available_values) // 2]
        else:
            basic = (available_values[len(available_values) // 2 - 1] + available_values[len(available_values) // 2]) / 2.0
        basic = weighted_average([
            {"value": basic, "weight": 0.55},
            {"value": financial_value, "weight": 0.45},
        ]) or basic
    else:
        basic = 0.0

    conservative = min(available_values) * 0.94 if available_values else basic
    growth_value = max(available_values) * (1.05 if positive_transition else 1.0) if available_values else basic

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

    confidence = 45
    if eps > 0:
        confidence += 10
    if bps > 0:
        confidence += 8
    if periods:
        confidence += 12
    if quarter["quality"] >= 70:
        confidence += 8
    if len(available_values) >= 4:
        confidence += 10
    if abs(gap) <= 150:
        confidence += 4
    confidence = int(clamp(confidence, 35, 95))

    confidence_grade = "A" if confidence >= 85 else "B" if confidence >= 70 else "C" if confidence >= 55 else "D"

    notes = []
    if positive_transition:
        notes.append("최근 분기 이익 급증 신호를 반영해 선행 EPS와 목표 PER을 상향 보정했습니다.")
    if negative_transition:
        notes.append("최근 분기 이익 둔화 신호를 반영해 목표 PER과 선행 EPS를 보수적으로 조정했습니다.")
    if periods:
        notes.append(f"OpenDART 최신 분기 {quarter['latest_period']} 자료를 함께 반영했습니다.")
    if debt_ratio > 2.0:
        notes.append("부채비율이 높아 밸류에이션 배수를 일부 낮췄습니다.")

    return {
        "현재가": price,
        "실제PER": per,
        "실제PBR": pbr,
        "EPS": eps,
        "BPS": bps,
        "선행EPS": round(forward_eps, 2) if forward_eps > 0 else 0.0,
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
        "실적전환방향": transition_direction,
        "실적전환강도": round(transition_strength, 2),
        "분기매출성장률": round(quarter["revenue_yoy"], 2),
        "분기영업이익성장률": round(quarter["operating_yoy"], 2),
        "분기순이익성장률": round(quarter["net_yoy"], 2),
        "가치신뢰도": confidence,
        "가치신뢰도등급": confidence_grade,
        "설명": notes,
    }
