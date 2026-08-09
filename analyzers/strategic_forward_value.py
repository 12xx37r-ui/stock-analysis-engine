"""Strategic Forward Valuation Engine V0.2 (shadow-first, low-load).

목적
- 기존 재무가치 엔진을 변경하지 않고, 현재 재무기초가치 위에 실제로 근거가
  확인되는 미래 증분가치만 제한적으로 인정한다.
- 산업/시장 기대 자료가 없으면 미래가치를 거의 인정하지 않는다.
- 글로벌 거시환경은 가치를 새로 만들지 않고 미래가치의 실현확률/할인만 조정한다.
- 진짜 SOTP는 감사 가능한 사업부 자료가 있을 때만 사용한다.
- 회사 현재주가/시가총액/시장 PER·PBR은 산식에 사용하지 않는다.

주의
- 이 모듈은 기본적으로 shadow 결과를 반환한다. 기존 ``재무적정가``를 덮어쓰지 않는다.
- 애널리스트 컨센서스가 없으면 이를 임의 추정하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple


ENGINE_VERSION = "0.2.0-strategic-forward-shadow-low-load"


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def safe_bool(value: Any) -> bool:
    return bool(value is True or str(value).lower() in {"true", "1", "yes", "y"})


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _positive_score(value: float, full_at: float) -> float:
    """0 이하=0, full_at 이상=100인 단조 점수."""
    if full_at <= 0:
        return 0.0
    return clamp(value / full_at * 100.0, 0.0, 100.0)


def _bounded_quality(value: Any, default: float = 0.0) -> float:
    return clamp(safe_float(value, default), 0.0, 100.0)


def _analysis_dict(container: Dict[str, Any], key: str) -> Dict[str, Any]:
    value = container.get(key, {}) if isinstance(container, dict) else {}
    return value if isinstance(value, dict) else {}


def company_growth_axis(
    valuation: Dict[str, Any],
    fundamentals_analysis: Dict[str, Any],
) -> Dict[str, Any]:
    """실제 실적/재무자료에서 확인되는 성장 가속도.

    가격/시가총액은 사용하지 않는다. 최근 한 분기만으로 만점을 받을 수 없도록
    구조적 가속, 매출, 영업이익, FY1 방향, TTM 품질을 함께 본다.
    """
    revenue_yoy = safe_float(valuation.get("분기매출성장률"))
    operating_yoy = safe_float(valuation.get("분기영업이익성장률"))
    net_yoy = safe_float(valuation.get("분기순이익성장률"))
    fy1_growth = safe_float(valuation.get("FY1성장률"))
    structural = safe_bool(valuation.get("구조적실적가속"))
    transition = safe_float(valuation.get("실적전환강도"))

    forward = _analysis_dict(fundamentals_analysis, "향후이익방향대용")
    forward_signal = safe_float(forward.get("신호"))
    forward_quality = _bounded_quality(forward.get("데이터품질"), 0.0)

    score = 0.0
    score += 20.0 if structural else 0.0
    score += _positive_score(revenue_yoy, 30.0) * 0.18
    score += _positive_score(operating_yoy, 100.0) * 0.22
    score += _positive_score(net_yoy, 100.0) * 0.12
    score += _positive_score(fy1_growth, 25.0) * 0.16
    score += _positive_score(transition, 120.0) * 0.07
    score += _positive_score(forward_signal, 80.0) * 0.05
    score = clamp(score, 0.0, 100.0)

    ttm_quality = _bounded_quality(valuation.get("TTM데이터품질"), 0.0)
    data_confidence = _bounded_quality(valuation.get("데이터신뢰도"), 0.0)
    quality = clamp(ttm_quality * 0.45 + data_confidence * 0.40 + forward_quality * 0.15, 0.0, 100.0)

    reasons: List[str] = []
    if structural:
        reasons.append("매출·영업이익·순이익의 구조적 가속 감지")
    if operating_yoy >= 35:
        reasons.append("최근 분기 영업이익 고성장")
    if revenue_yoy >= 10:
        reasons.append("최근 분기 매출 성장 동반")
    if fy1_growth >= 10:
        reasons.append("FY1 이익 성장방향 강함")
    if forward_signal >= 35:
        reasons.append("DART 기반 향후이익 대용지표 긍정")

    return {
        "점수": round(score, 2),
        "품질": round(quality, 2),
        "사용가능": quality >= 50.0,
        "근거": reasons,
        "입력": {
            "분기매출YoY": revenue_yoy,
            "분기영업이익YoY": operating_yoy,
            "분기순이익YoY": net_yoy,
            "FY1성장률": fy1_growth,
            "구조적실적가속": structural,
            "실적전환강도": transition,
            "향후이익대용신호": forward_signal,
        },
    }


def industry_growth_axis(industry_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """산업 가격/시장폭으로 확인되는 현재·장기 산업 확장 신호.

    산업 데이터가 없으면 0점/미사용이며 임의 업종 프리미엄을 만들지 않는다.
    """
    if not isinstance(industry_analysis, dict) or industry_analysis.get("분석상태") != "정상":
        return {
            "점수": 0.0,
            "품질": 0.0,
            "사용가능": False,
            "근거": ["검증 가능한 산업 선행/사이클 자료 없음"],
        }

    mid = _analysis_dict(industry_analysis, "중기산업선행")
    long = _analysis_dict(industry_analysis, "장기산업사이클")
    breadth = _analysis_dict(industry_analysis, "시장폭")
    relative = _analysis_dict(industry_analysis, "상대강도")

    mid_signal = safe_float(mid.get("신호"))
    long_signal = safe_float(long.get("신호"))
    ma20 = safe_float(breadth.get("MA20상회비율"), 50.0)
    ma120 = safe_float(breadth.get("MA120상회비율"), 50.0)
    excess = safe_float(relative.get("기준시장대비초과수익률"), 0.0)

    # 미래가치에는 양(+)의 확장 증거만 기여한다. 단기 모멘텀보다 장기 사이클 비중을 높인다.
    score = (
        _positive_score(mid_signal, 60.0) * 0.22
        + _positive_score(long_signal, 70.0) * 0.43
        + clamp((ma20 - 45.0) / 55.0 * 100.0, 0.0, 100.0) * 0.10
        + clamp((ma120 - 45.0) / 55.0 * 100.0, 0.0, 100.0) * 0.15
        + _positive_score(excess, 15.0) * 0.10
    )
    mid_quality = _bounded_quality(mid.get("데이터품질"), 0.0)
    long_quality = _bounded_quality(long.get("데이터품질"), 0.0)
    quality = clamp(mid_quality * 0.40 + long_quality * 0.60, 0.0, 100.0)

    reasons: List[str] = []
    if long_signal >= 35:
        reasons.append("장기 산업사이클 강세")
    elif long_signal >= 15:
        reasons.append("장기 산업사이클 우호")
    if mid_signal >= 25:
        reasons.append("중기 산업선행 강세")
    if ma120 >= 70:
        reasons.append("산업 구성자산 장기 시장폭 양호")
    if excess >= 5:
        reasons.append("기준시장 대비 산업 상대강도 우위")

    return {
        "점수": round(clamp(score, 0.0, 100.0), 2),
        "품질": round(quality, 2),
        "사용가능": quality >= 55.0,
        "근거": reasons,
        "입력": {
            "중기산업신호": mid_signal,
            "장기산업신호": long_signal,
            "MA20상회비율": ma20,
            "MA120상회비율": ma120,
            "기준시장대비초과수익률": excess,
        },
    }


def analyst_expectation_axis(fundamentals_analysis: Dict[str, Any]) -> Dict[str, Any]:
    """애널리스트 실적 컨센서스의 '수정 방향'만 사용한다.

    목표주가 수준은 가치 산식에 넣지 않는다. 현재 stock engine에는 보통 이 자료가
    없으므로, 없을 때는 명시적으로 0점/미사용 처리한다.

    지원 입력 예시::
      fundamentals_analysis['애널리스트컨센서스'] = {
        '사용가능': True, '애널리스트수': 12,
        'FY1_EPS_3개월수정률': 15.0, 'FY2_EPS_3개월수정률': 12.0,
        '영업이익_3개월수정률': 18.0, '상향비율': 75.0,
        '추정치분산': 12.0, '데이터품질': 90.0
      }
    """
    consensus = _analysis_dict(fundamentals_analysis, "애널리스트컨센서스")
    if not consensus or consensus.get("사용가능") is not True:
        return {
            "점수": 0.0,
            "품질": 0.0,
            "사용가능": False,
            "근거": ["애널리스트 실적 컨센서스 수정자료 없음"],
            "주의": "목표주가를 임의 대용하지 않음",
        }

    n = int(max(0, safe_float(consensus.get("애널리스트수"))))
    fy1_rev = safe_float(consensus.get("FY1_EPS_3개월수정률"))
    fy2_rev = safe_float(consensus.get("FY2_EPS_3개월수정률"))
    op_rev = safe_float(consensus.get("영업이익_3개월수정률"))
    upward = safe_float(consensus.get("상향비율"), 50.0)
    dispersion = safe_float(consensus.get("추정치분산"), 50.0)

    score = (
        _positive_score(fy1_rev, 25.0) * 0.35
        + _positive_score(fy2_rev, 25.0) * 0.25
        + _positive_score(op_rev, 30.0) * 0.20
        + clamp((upward - 50.0) / 40.0 * 100.0, 0.0, 100.0) * 0.15
        + clamp((30.0 - dispersion) / 25.0 * 100.0, 0.0, 100.0) * 0.05
    )
    source_quality = _bounded_quality(consensus.get("데이터품질"), 70.0)
    coverage_quality = clamp(n / 10.0 * 100.0, 20.0 if n > 0 else 0.0, 100.0)
    quality = clamp(source_quality * 0.70 + coverage_quality * 0.30, 0.0, 100.0)

    reasons = []
    if fy1_rev >= 8:
        reasons.append("FY1 EPS 컨센서스 상향")
    if fy2_rev >= 8:
        reasons.append("FY2 EPS 컨센서스 상향")
    if op_rev >= 10:
        reasons.append("영업이익 컨센서스 상향")
    if upward >= 65:
        reasons.append("상향 애널리스트 비율 우세")

    return {
        "점수": round(clamp(score, 0.0, 100.0), 2),
        "품질": round(quality, 2),
        "사용가능": quality >= 55.0 and n >= 3,
        "근거": reasons,
        "입력": {
            "애널리스트수": n,
            "FY1_EPS_3개월수정률": fy1_rev,
            "FY2_EPS_3개월수정률": fy2_rev,
            "영업이익_3개월수정률": op_rev,
            "상향비율": upward,
            "추정치분산": dispersion,
        },
    }


def macro_axis(global_macro_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """별도 글로벌 거시 엔진의 카드11 통합판정을 읽는다.

    검증 게이트가 통과하지 않으면 거시환경은 미래가치를 조정하지 않는다.
    통과한 경우에도 '새 가치'를 만들지 않고 이미 계산된 미래 증분가치의
    실현확률만 0.80~1.10 범위에서 조정한다.
    """
    context = global_macro_context or {}
    cards = context.get("cards", {}) if isinstance(context, dict) else {}
    card11 = cards.get("11", {}) if isinstance(cards, dict) else {}
    if not card11 and isinstance(context, dict) and context.get("card") == 11:
        card11 = context
    if not isinstance(card11, dict) or not card11:
        return {
            "점수": 0.0,
            "품질": 0.0,
            "사용가능": False,
            "조정배수": 1.0,
            "근거": ["글로벌 거시 엔진 통합판정 없음"],
        }

    quality_gate = card11.get("quality_gate", {}) if isinstance(card11.get("quality_gate"), dict) else {}
    passed = quality_gate.get("passed") is True
    score = clamp(safe_float(card11.get("score")), -100.0, 100.0)
    checks = quality_gate.get("checks", {}) if isinstance(quality_gate.get("checks"), dict) else {}
    check_values = [bool(v) for v in checks.values()]
    quality = (sum(check_values) / len(check_values) * 100.0) if check_values else 0.0

    if not passed:
        return {
            "점수": round(score, 2),
            "품질": round(quality, 2),
            "사용가능": False,
            "조정배수": 1.0,
            "근거": ["거시 통합판정 품질게이트 미통과 → 가치조정 미적용"],
            "국면": card11.get("current_regime", ""),
            "미래국면": card11.get("future_regime", ""),
        }

    if score >= 0:
        modifier = 1.0 + min(score, 100.0) / 100.0 * 0.10
    else:
        modifier = 1.0 + max(score, -100.0) / 100.0 * 0.20
    modifier = clamp(modifier, 0.80, 1.10)

    reasons = [f"검증 통과 글로벌 경기점수 {score:.1f}"]
    return {
        "점수": round(score, 2),
        "품질": round(quality, 2),
        "사용가능": True,
        "조정배수": round(modifier, 4),
        "근거": reasons,
        "국면": card11.get("current_regime", ""),
        "미래국면": card11.get("future_regime", ""),
    }


def build_sotp_base(segment_data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """감사 가능한 사업부 입력이 있을 때만 진짜 SOTP 기초가치를 계산한다.

    ``segments`` 각 행은 이미 산출된 사업부 기업가치(EV) 또는 지분가치(equity_value)를
    제공할 수 있다. EV를 제공하면 전체 회사 수준의 cash/debt/minority_interest를
    한 번만 조정한다. listed_stakes/non_operating_assets는 지분가치로 더한다.
    주당가치는 diluted_shares로 나눈다.

    데이터가 없으면 0을 반환해 기존 재무기초가치로 fallback하게 한다.
    """
    data = segment_data or {}
    segments = data.get("segments", []) if isinstance(data, dict) else []
    if not isinstance(segments, list) or not segments:
        return {
            "사용가능": False,
            "주당SOTP기초가치": 0.0,
            "근거": ["감사 가능한 사업부별 가치자료 없음"],
        }

    total_ev = 0.0
    direct_equity = 0.0
    valid_segments = 0
    detail = []
    for row in segments:
        if not isinstance(row, dict):
            continue
        ev = safe_float(row.get("enterprise_value"))
        eq = safe_float(row.get("equity_value"))
        value = 0.0
        basis = ""
        if ev > 0:
            total_ev += ev
            value = ev
            basis = "EV"
        elif eq > 0:
            direct_equity += eq
            value = eq
            basis = "Equity"
        else:
            metric = safe_float(row.get("metric"))
            multiple = safe_float(row.get("multiple"))
            if metric > 0 and multiple > 0:
                total_ev += metric * multiple
                value = metric * multiple
                basis = "metric×multiple"
        if value > 0:
            valid_segments += 1
            detail.append({"name": row.get("name", "segment"), "value": value, "basis": basis})

    if valid_segments < 2:
        return {
            "사용가능": False,
            "주당SOTP기초가치": 0.0,
            "근거": ["유효 사업부가 2개 미만이라 SOTP 비적용"],
        }

    stakes = data.get("listed_stakes", [])
    stake_value = sum(
        max(0.0, safe_float(row.get("equity_value")))
        for row in stakes if isinstance(row, dict)
    ) if isinstance(stakes, list) else 0.0
    non_operating_assets = max(0.0, safe_float(data.get("non_operating_assets")))
    cash = max(0.0, safe_float(data.get("cash")))
    debt = max(0.0, safe_float(data.get("debt")))
    minority = max(0.0, safe_float(data.get("minority_interest")))
    preferred = max(0.0, safe_float(data.get("preferred_equity")))
    diluted_shares = max(0.0, safe_float(data.get("diluted_shares")))

    equity_value = (
        total_ev
        + direct_equity
        + stake_value
        + non_operating_assets
        + cash
        - debt
        - minority
        - preferred
    )
    per_share = equity_value / diluted_shares if equity_value > 0 and diluted_shares > 0 else 0.0
    usable = per_share > 0 and valid_segments >= 2
    return {
        "사용가능": usable,
        "주당SOTP기초가치": round(per_share, 2) if usable else 0.0,
        "총SOTP지분가치": round(equity_value, 2) if equity_value > 0 else 0.0,
        "사업부개수": valid_segments,
        "사업부": detail,
        "근거": ["사업부별 가치합산 후 순현금·비지배지분·우선주를 단일 조정"] if usable else ["희석주식수 또는 양(+)의 지분가치 미확보"],
    }


def _evidence_recognition_factor(
    company: Dict[str, Any],
    industry: Dict[str, Any],
    expectation: Dict[str, Any],
) -> Tuple[float, List[str]]:
    """미래 증분가치 인정률.

    핵심 정책:
    - 회사 성장증거가 약하면 최대 10%만 인정.
    - 산업+시장기대가 모두 없으면 최대 12%.
    - 산업만 강하고 실적컨센서스가 없으면 최대 45%.
    - 객관적 컨센서스와 산업이 함께 강할 때만 80~100% 접근 가능.
    """
    cs = safe_float(company.get("점수")) / 100.0 if company.get("사용가능") else 0.0
    is_ = safe_float(industry.get("점수")) / 100.0 if industry.get("사용가능") else 0.0
    es = safe_float(expectation.get("점수")) / 100.0 if expectation.get("사용가능") else 0.0
    cq = safe_float(company.get("품질")) / 100.0 if company.get("사용가능") else 0.0
    iq = safe_float(industry.get("품질")) / 100.0 if industry.get("사용가능") else 0.0
    eq = safe_float(expectation.get("품질")) / 100.0 if expectation.get("사용가능") else 0.0

    company_component = cs * cq
    industry_component = is_ * iq
    expectation_component = es * eq

    factor = (
        company_component * 0.55
        + industry_component * 0.25
        + expectation_component * 0.20
    )

    caps = []
    reasons = []
    if company_component < 0.25:
        caps.append(0.10)
        reasons.append("기업 자체 성장증거 약함 → 미래가치 최대 10% 인정")
    if industry_component < 0.20 and expectation_component < 0.20:
        caps.append(0.12)
        reasons.append("산업·시장기대 근거 동시 부족 → 미래가치 최대 12% 인정")
    elif industry_component >= 0.20 and expectation_component < 0.20:
        caps.append(0.45)
        reasons.append("산업근거는 있으나 실적 컨센서스 없음 → 미래가치 최대 45% 인정")
    elif industry_component < 0.20 and expectation_component >= 0.20:
        caps.append(0.40)
        reasons.append("컨센서스는 있으나 산업근거 부족 → 미래가치 최대 40% 인정")

    if caps:
        factor = min(factor, min(caps))
    factor = clamp(factor, 0.0, 1.0)
    return factor, reasons


def future_value_label(base_value: float, future_increment: float) -> str:
    if base_value <= 0 or future_increment <= 0:
        return "미래성장가치 반영 낮음"
    share = future_increment / (base_value + future_increment)
    if share >= 0.50:
        return "미래성장가치 반영 매우 높음"
    if share >= 0.30:
        return "미래성장가치 반영 높음"
    if share >= 0.12:
        return "미래성장가치 반영 보통"
    return "미래성장가치 반영 낮음"


def build_strategic_forward_value(
    *,
    valuation: Dict[str, Any],
    financial: Optional[Dict[str, Any]] = None,
    fundamentals_analysis: Optional[Dict[str, Any]] = None,
    industry_analysis: Optional[Dict[str, Any]] = None,
    global_macro_context: Optional[Dict[str, Any]] = None,
    segment_data: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """전략적 미래가치 Shadow 결과를 생성한다."""
    financial = financial or {}
    fundamentals_analysis = fundamentals_analysis or {}
    industry_analysis = industry_analysis or {}

    adaptive = valuation.get("적응형가치모형", {}) if isinstance(valuation.get("적응형가치모형"), dict) else {}
    adaptive_applied = valuation.get("적응형가치적용") is True
    if adaptive_applied:
        current_base = safe_float(valuation.get("현재재무기초가치"))
        if current_base <= 0:
            current_base = safe_float(adaptive.get("현재재무기초가치"))
        base_source = "적응형 현재재무기초가치"
    else:
        # 기존 엔진이 정상 동작하는 종목은 기존 라이브 기준가를 기초가치로 유지한다.
        # 계산은 되어 있으나 승격되지 않은 adaptive current_base를 새 엔진이 임의 승격하지 않는다.
        current_base = safe_float(valuation.get("재무적정가"))
        base_source = "기존 라이브 재무적정가"
    if current_base <= 0:
        current_base = safe_float(valuation.get("기존V4재무적정가"))
        base_source = "기존 V4 재무적정가"

    sotp = build_sotp_base(segment_data)
    strategic_base = current_base
    if sotp.get("사용가능") is True:
        strategic_base = safe_float(sotp.get("주당SOTP기초가치"))
        base_source = "SOTP기초가치"

    company = company_growth_axis(valuation, fundamentals_analysis)
    industry = industry_growth_axis(industry_analysis)
    expectation = analyst_expectation_axis(fundamentals_analysis)
    macro = macro_axis(global_macro_context)

    # 기존 미래성장모형은 가격독립적인 FY3/FY4 총가치 후보로만 활용한다.
    future_model = valuation.get("미래성장모형", {}) if isinstance(valuation.get("미래성장모형"), dict) else {}
    future_total = safe_float(future_model.get("가치")) if future_model.get("사용가능") is True else 0.0
    if future_total <= 0:
        future_total = safe_float(adaptive.get("미래총가치"))

    raw_increment = max(0.0, future_total - strategic_base) if strategic_base > 0 else 0.0
    evidence_factor, cap_reasons = _evidence_recognition_factor(company, industry, expectation)
    macro_modifier = safe_float(macro.get("조정배수"), 1.0)
    recognized_increment = raw_increment * evidence_factor * macro_modifier

    # 거시가 우호적이어도 raw increment 이상으로 증폭시키지 않는다.
    recognized_increment = min(recognized_increment, raw_increment)
    strategic_fair = strategic_base + recognized_increment if strategic_base > 0 else 0.0

    evidence_quality_parts = []
    for axis in (company, industry, expectation):
        if axis.get("사용가능"):
            evidence_quality_parts.append(safe_float(axis.get("품질")))
    evidence_quality = sum(evidence_quality_parts) / len(evidence_quality_parts) if evidence_quality_parts else 0.0
    if not expectation.get("사용가능"):
        evidence_quality = min(evidence_quality, 72.0)
    if not industry.get("사용가능"):
        evidence_quality = min(evidence_quality, 62.0)

    label = future_value_label(strategic_base, recognized_increment)
    reasons = []
    reasons.extend(company.get("근거", []))
    reasons.extend(industry.get("근거", []))
    reasons.extend(expectation.get("근거", []))
    reasons.extend(macro.get("근거", []))
    reasons.extend(cap_reasons)

    return {
        "엔진버전": ENGINE_VERSION,
        "모드": "shadow",
        "현재가미사용": True,
        "시가총액미사용": True,
        "시장PER_PBR미사용": True,
        "기초가치": round(strategic_base, 2),
        "기초가치출처": base_source,
        "SOTP": sotp,
        "원시미래총가치": round(future_total, 2),
        "원시미래증분가치": round(raw_increment, 2),
        "미래가치인정률": round(evidence_factor * 100.0, 2),
        "거시조정배수": round(macro_modifier, 4),
        "미래증분가치": round(recognized_increment, 2),
        "전략펀더멘털적정가": round(strategic_fair, 2),
        "미래성장가치표시": label,
        "미래성장가치표시문구": f"{label} · +{recognized_increment:,.0f}원" if recognized_increment > 0 else label,
        "근거신뢰도": round(evidence_quality, 2),
        "근거축": {
            "기업실적가속": company,
            "산업현재미래": industry,
            "시장기대_애널리스트": expectation,
            "글로벌거시": macro,
        },
        "근거": list(dict.fromkeys(str(x) for x in reasons if x)),
        "정책": {
            "시장기대없음": "애널리스트 실적수정 자료가 없으면 임의 목표주가/시장가로 대체하지 않음",
            "산업자료없음": "산업 선행자료가 없으면 산업 프리미엄 0점",
            "산업시장기대모두부족": "미래증분가치 최대 12% 인정",
            "산업만확인": "컨센서스 없으면 미래증분가치 최대 45% 인정",
            "거시환경": "품질게이트 통과시에만 0.80~1.10 범위의 실현확률 조정; 새 가치를 만들지 않음",
            "SOTP": "감사 가능한 2개 이상 사업부와 희석주식수 있을 때만 진짜 SOTP 사용",
        },
    }
