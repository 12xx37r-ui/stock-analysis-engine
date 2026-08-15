"""Strategic Forward Valuation Engine V0.3.1 (double-count guard + audited SOTP + low-load).

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


ENGINE_VERSION = "0.4.0-strategic-forward-recognition-gate"


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


def _industry_detail_without_target(
    block: Dict[str, Any],
    stock_code: str = "",
    company_name: str = "",
) -> Tuple[float, float, bool, int]:
    """산업 요소별 평가에서 대상기업 자체 주가 행을 제외해 신호를 재집계한다.

    산업 바스켓에 평가대상 종목이 포함되면 그 종목의 주가가 다시 미래가치의
    근거가 되는 순환오염이 생길 수 있다. 요소별평가가 제공되는 경우 해당 행을
    제거한 뒤 원래와 동일하게 가중치×데이터품질로 재집계한다.
    """
    details = block.get("요소별평가") if isinstance(block, dict) else None
    if not isinstance(details, list) or not details:
        return safe_float(block.get("신호")), _bounded_quality(block.get("데이터품질"), 0.0), False, 0

    code = str(stock_code or "").strip()
    name = str(company_name or "").strip()
    kept = []
    removed = 0
    for row in details:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("심볼") or "").strip().upper()
        asset_name = str(row.get("자산명") or "").strip()
        is_self = bool(code and (symbol == code or symbol.startswith(code + "."))) or bool(name and asset_name == name)
        if is_self:
            removed += 1
            continue
        kept.append(row)

    if removed <= 0:
        return safe_float(block.get("신호")), _bounded_quality(block.get("데이터품질"), 0.0), False, 0

    weighted_sum = 0.0
    effective_weight_sum = 0.0
    nominal_weight_sum = 0.0
    quality_sum = 0.0
    for row in kept:
        weight = max(0.0, safe_float(row.get("가중치")))
        quality = clamp(safe_float(row.get("데이터품질"), 0.0) / 100.0, 0.0, 1.0)
        signal = clamp(safe_float(row.get("신호")), -100.0, 100.0)
        effective = weight * quality
        weighted_sum += signal * effective
        effective_weight_sum += effective
        nominal_weight_sum += weight
        quality_sum += weight * quality

    if effective_weight_sum <= 0 or nominal_weight_sum <= 0:
        return 0.0, 0.0, True, removed

    signal = weighted_sum / effective_weight_sum
    quality = quality_sum / nominal_weight_sum * 100.0
    return clamp(signal, -100.0, 100.0), clamp(quality, 0.0, 100.0), True, removed


def industry_growth_axis(
    industry_analysis: Dict[str, Any],
    stock_code: str = "",
    company_name: str = "",
) -> Dict[str, Any]:
    """산업의 현재·장기 확장 신호를 평가한다.

    핵심 원칙
    - 산업 데이터가 없으면 임의 프리미엄을 만들지 않는다.
    - 산업 바스켓에 대상기업 자체가 들어 있으면 해당 주가 행은 제거한다.
    - 자체 행 제거 시 그 행이 섞여 있는 시장폭/상대강도 집계값도 가치평가에는
      사용하지 않고, 독립 peer들의 중기·장기 신호만 사용한다.
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

    mid_signal, mid_quality, mid_self_removed, mid_removed_count = _industry_detail_without_target(
        mid, stock_code=stock_code, company_name=company_name
    )
    long_signal, long_quality, long_self_removed, long_removed_count = _industry_detail_without_target(
        long, stock_code=stock_code, company_name=company_name
    )
    self_removed = mid_self_removed or long_self_removed

    ma20 = safe_float(breadth.get("MA20상회비율"), 50.0)
    ma120 = safe_float(breadth.get("MA120상회비율"), 50.0)
    excess = safe_float(relative.get("기준시장대비초과수익률"), 0.0)

    if self_removed:
        # 시장폭·상대강도도 대상기업 자체 가격을 포함한 집계일 수 있으므로 제외.
        # 독립 peer의 중기/장기 신호만 34:66으로 재정규화한다.
        score = (
            _positive_score(mid_signal, 60.0) * 0.34
            + _positive_score(long_signal, 70.0) * 0.66
        )
        quality = clamp(mid_quality * 0.40 + long_quality * 0.60, 0.0, 100.0)
    else:
        # 미래가치에는 양(+)의 확장 증거만 기여한다. 단기 모멘텀보다 장기 사이클 비중을 높인다.
        score = (
            _positive_score(mid_signal, 60.0) * 0.22
            + _positive_score(long_signal, 70.0) * 0.43
            + clamp((ma20 - 45.0) / 55.0 * 100.0, 0.0, 100.0) * 0.10
            + clamp((ma120 - 45.0) / 55.0 * 100.0, 0.0, 100.0) * 0.15
            + _positive_score(excess, 15.0) * 0.10
        )
        quality = clamp(mid_quality * 0.40 + long_quality * 0.60, 0.0, 100.0)

    reasons: List[str] = []
    if self_removed:
        reasons.append("대상기업 자체 주가를 산업 성장근거에서 제외")
    if long_signal >= 35:
        reasons.append("장기 산업사이클 강세")
    elif long_signal >= 15:
        reasons.append("장기 산업사이클 우호")
    if mid_signal >= 25:
        reasons.append("중기 산업선행 강세")
    if not self_removed and ma120 >= 70:
        reasons.append("산업 구성자산 장기 시장폭 양호")
    if not self_removed and excess >= 5:
        reasons.append("기준시장 대비 산업 상대강도 우위")

    return {
        "점수": round(clamp(score, 0.0, 100.0), 2),
        "품질": round(quality, 2),
        "사용가능": quality >= 55.0,
        "근거": reasons,
        "입력": {
            "중기산업신호": round(mid_signal, 2),
            "장기산업신호": round(long_signal, 2),
            "MA20상회비율": None if self_removed else ma20,
            "MA120상회비율": None if self_removed else ma120,
            "기준시장대비초과수익률": None if self_removed else excess,
            "대상기업자체행제외": self_removed,
            "제외행수": max(mid_removed_count, long_removed_count),
        },
    }


def analyst_expectation_axis(
    fundamentals_analysis: Dict[str, Any],
    valuation: Optional[Dict[str, Any]] = None,
    external_consensus: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """애널리스트 *실적* 기대를 시장가와 분리해 사용한다.

    우선순위
    1) 명시적인 EPS/영업이익 수정률 데이터가 있으면 기존 revision 방식 사용.
    2) revision 이력이 없지만 외부 FY1 EPS 컨센서스가 있으면 내부 FY1 EPS와의
       괴리, 추정기관수, 투자의견을 이용해 '기대 강도'만 산출한다.

    목표주가는 저장/표시용 진단값으로만 보존한다. 적정가에 직접 합산하지 않는다.
    현재주가/시가총액도 사용하지 않는다.
    """
    valuation = valuation or {}
    external_consensus = external_consensus or {}

    consensus = _analysis_dict(fundamentals_analysis, "애널리스트컨센서스")
    if consensus and consensus.get("사용가능") is True:
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
            "방식": "revision",
            "입력": {
                "애널리스트수": n,
                "FY1_EPS_3개월수정률": fy1_rev,
                "FY2_EPS_3개월수정률": fy2_rev,
                "영업이익_3개월수정률": op_rev,
                "상향비율": upward,
                "추정치분산": dispersion,
            },
        }

    if external_consensus.get("사용가능") is True:
        n = int(max(0, safe_float(external_consensus.get("추정기관수"))))
        opinion = safe_float(external_consensus.get("투자의견"), 3.0)
        external_eps = safe_float(external_consensus.get("FY1_EPS"))
        internal_eps = safe_float(valuation.get("FY1예상EPS"))
        target_price = safe_float(external_consensus.get("목표주가"))
        implied_per = target_price / external_eps if target_price > 0 and external_eps > 0 else 0.0
        eps_gap_pct = ((external_eps / internal_eps) - 1.0) * 100.0 if internal_eps > 0 else 0.0

        # 실적 컨센서스가 내부 전망보다 높을수록 강한 미래이익 검증으로 본다.
        # 목표주가와 목표가 암시 PER은 진단용으로만 보존하며 점수/적정가에는 0% 반영한다.
        score = (
            _positive_score(eps_gap_pct, 30.0) * 0.60
            + clamp((opinion - 3.0) / 1.5 * 100.0, 0.0, 100.0) * 0.18
            + clamp(n / 15.0 * 100.0, 0.0, 100.0) * 0.22
        )
        source_quality = _bounded_quality(external_consensus.get("데이터품질"), 70.0)
        coverage_quality = clamp(n / 12.0 * 100.0, 0.0, 100.0)
        quality = clamp(source_quality * 0.72 + coverage_quality * 0.28, 0.0, 100.0)
        reasons: List[str] = []
        if eps_gap_pct >= 10:
            reasons.append("외부 FY1 EPS 컨센서스가 내부 전망보다 상향")
        elif eps_gap_pct <= -10:
            reasons.append("외부 FY1 EPS 컨센서스가 내부 전망보다 하향")
        if n >= 10:
            reasons.append("다수 추정기관의 실적 컨센서스 확보")
        if opinion >= 3.8:
            reasons.append("애널리스트 투자의견 기대 강함")

        return {
            "점수": round(clamp(score, 0.0, 100.0), 2),
            "품질": round(quality, 2),
            "사용가능": quality >= 55.0 and n >= 3 and external_eps > 0,
            "근거": reasons,
            "방식": "current_consensus_anchor",
            "입력": {
                "애널리스트수": n,
                "투자의견": round(opinion, 2),
                "외부FY1EPS": round(external_eps, 4),
                "내부FY1EPS": round(internal_eps, 4),
                "EPS전망격차율": round(eps_gap_pct, 2),
                "목표암시PER_진단전용": round(implied_per, 2),
                "목표주가직접가치미사용": True,
            },
        }

    return {
        "점수": 0.0,
        "품질": 0.0,
        "사용가능": False,
        "근거": ["애널리스트 실적 컨센서스 자료 없음"],
        "주의": "목표주가/현재주가를 임의 대용하지 않음",
        "방식": "none",
    }


def _consensus_adjusted_future_total(
    future_total: float,
    valuation: Dict[str, Any],
    expectation: Dict[str, Any],
) -> Tuple[float, Dict[str, Any]]:
    """외부 FY1 EPS가 있을 때 기존 FY3/FY4 미래가치 후보를 보수적으로 보정한다.

    외부 컨센서스는 FY1 앵커일 뿐이므로 전체 격차를 100% 장기화하지 않는다.
    품질에 따라 최대 80%만 미래 경로에 전달하고, 상향/하향 비율은 0.75~1.35로
    제한한다. 목표주가/현재가는 전혀 사용하지 않는다.
    """
    if future_total <= 0 or expectation.get("사용가능") is not True:
        return future_total, {"적용": False, "배수": 1.0}
    inp = expectation.get("입력", {}) if isinstance(expectation.get("입력"), dict) else {}
    external_eps = safe_float(inp.get("외부FY1EPS"))
    internal_eps = safe_float(inp.get("내부FY1EPS"))
    if external_eps <= 0 or internal_eps <= 0:
        return future_total, {"적용": False, "배수": 1.0}

    raw_ratio = external_eps / internal_eps
    bounded_ratio = clamp(raw_ratio, 0.75, 1.35)
    quality_weight = clamp(safe_float(expectation.get("품질")) / 100.0 * 0.80, 0.0, 0.80)
    applied_ratio = 1.0 + (bounded_ratio - 1.0) * quality_weight
    adjusted = max(0.0, future_total * applied_ratio)
    return adjusted, {
        "적용": True,
        "외부대내부FY1EPS배수": round(raw_ratio, 4),
        "상하한적용배수": round(bounded_ratio, 4),
        "품질전달률": round(quality_weight, 4),
        "최종미래가치보정배수": round(applied_ratio, 4),
        "목표주가미사용": True,
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
    """검증된 사업부 원천자료가 있을 때만 진짜 SOTP 기초가치를 계산한다.

    치명적 오판 방지 원칙
    - ``audit_status``가 verified/audited가 아니면 사용하지 않는다.
    - 최소 2개 독립 사업부, 희석주식수, 기준일, 통화가 모두 필요하다.
    - 각 영업사업부는 EV 기준만 허용한다. EV/Equity 혼합은 순부채 이중조정 위험 때문에 차단한다.
    - 각 사업부에는 출처와 기준일이 있어야 하며 중복 사업부명은 허용하지 않는다.
    - 조건을 하나라도 충족하지 못하면 기존 현재재무기초가치로 fallback한다.
    """
    data = segment_data or {}
    if not isinstance(data, dict):
        data = {}

    blocked: List[str] = []
    audit_status = str(data.get("audit_status", "")).strip().lower()
    if audit_status not in {"verified", "audited"}:
        blocked.append("SOTP 감사상태 미검증")

    source_date = str(data.get("source_date") or data.get("as_of") or "").strip()
    if not source_date:
        blocked.append("SOTP 기준일 없음")

    currency = str(data.get("currency", "")).strip().upper()
    if not currency:
        blocked.append("SOTP 통화 기준 없음")

    diluted_shares = max(0.0, safe_float(data.get("diluted_shares")))
    if diluted_shares <= 0:
        blocked.append("희석주식수 미확보")

    segments = data.get("segments", [])
    if not isinstance(segments, list) or len(segments) < 2:
        blocked.append("유효 사업부 2개 미만")
        return {
            "사용가능": False,
            "검증상태": "차단",
            "주당SOTP기초가치": 0.0,
            "차단사유": list(dict.fromkeys(blocked)),
            "근거": ["감사 가능한 2개 이상 사업부 원천자료가 없어 SOTP 비적용"],
        }

    total_ev = 0.0
    valid_segments = 0
    detail = []
    seen_names = set()
    for idx, row in enumerate(segments):
        if not isinstance(row, dict):
            blocked.append(f"사업부 {idx+1} 형식 오류")
            continue
        name = str(row.get("name") or row.get("segment_id") or "").strip()
        if not name:
            blocked.append(f"사업부 {idx+1} 식별자 없음")
            continue
        key = name.lower()
        if key in seen_names:
            blocked.append(f"사업부 중복: {name}")
            continue
        seen_names.add(key)

        row_source = str(row.get("source") or row.get("data_source") or "").strip()
        row_date = str(row.get("source_date") or row.get("as_of") or source_date).strip()
        row_currency = str(row.get("currency") or currency).strip().upper()
        if not row_source:
            blocked.append(f"사업부 출처 없음: {name}")
            continue
        if not row_date:
            blocked.append(f"사업부 기준일 없음: {name}")
            continue
        if currency and row_currency and row_currency != currency:
            blocked.append(f"사업부 통화 불일치: {name}")
            continue

        # 지분가치 직접 입력은 회사 전체 순부채 조정과 중복될 수 있으므로 차단한다.
        if safe_float(row.get("equity_value")) > 0:
            blocked.append(f"사업부 Equity 직접값 혼합 차단: {name}")
            continue

        ev = safe_float(row.get("enterprise_value"))
        basis = "enterprise_value"
        if ev <= 0:
            metric = safe_float(row.get("metric"))
            multiple = safe_float(row.get("multiple"))
            metric_name = str(row.get("metric_name", "")).strip()
            multiple_source = str(row.get("multiple_source", "")).strip()
            if metric > 0 and multiple > 0 and metric_name and multiple_source:
                ev = metric * multiple
                basis = "metric×multiple"
            else:
                blocked.append(f"검증 가능한 EV 산식 없음: {name}")
                continue

        if ev <= 0:
            blocked.append(f"사업부 EV 비정상: {name}")
            continue
        total_ev += ev
        valid_segments += 1
        detail.append({
            "name": name,
            "value": round(ev, 2),
            "basis": basis,
            "source": row_source,
            "as_of": row_date,
            "currency": row_currency or currency,
        })

    if valid_segments < 2:
        blocked.append("검증 통과 사업부 2개 미만")

    stakes = data.get("listed_stakes", [])
    stake_value = 0.0
    if isinstance(stakes, list):
        for row in stakes:
            if not isinstance(row, dict):
                continue
            value = max(0.0, safe_float(row.get("equity_value")))
            source = str(row.get("source") or row.get("data_source") or "").strip()
            if value > 0 and source:
                stake_value += value
            elif value > 0:
                blocked.append("상장지분가치 출처 없음")

    non_operating_assets = max(0.0, safe_float(data.get("non_operating_assets")))
    cash = max(0.0, safe_float(data.get("cash")))
    debt = max(0.0, safe_float(data.get("debt")))
    minority = max(0.0, safe_float(data.get("minority_interest")))
    preferred = max(0.0, safe_float(data.get("preferred_equity")))

    if any(v > 0 for v in (cash, debt, minority, preferred, non_operating_assets)):
        if not str(data.get("balance_sheet_source", "")).strip():
            blocked.append("순현금·비지배지분 조정 원천 없음")

    if blocked:
        return {
            "사용가능": False,
            "검증상태": "차단",
            "주당SOTP기초가치": 0.0,
            "사업부개수": valid_segments,
            "사업부": detail,
            "차단사유": list(dict.fromkeys(blocked)),
            "근거": ["SOTP 원천·기준일·사업부 EV·순부채 조정의 감사조건 미충족"],
        }

    equity_value = (
        total_ev
        + stake_value
        + non_operating_assets
        + cash
        - debt
        - minority
        - preferred
    )
    per_share = equity_value / diluted_shares if equity_value > 0 else 0.0
    usable = per_share > 0 and valid_segments >= 2
    return {
        "사용가능": usable,
        "검증상태": "verified" if usable else "차단",
        "주당SOTP기초가치": round(per_share, 2) if usable else 0.0,
        "총SOTP지분가치": round(equity_value, 2) if equity_value > 0 else 0.0,
        "사업부개수": valid_segments,
        "사업부": detail,
        "기준일": source_date,
        "통화": currency,
        "차단사유": [],
        "근거": ["검증된 사업부 EV 합산 후 회사단위 순현금·비지배지분·우선주를 1회만 조정"],
    }


def _select_current_only_base(valuation: Dict[str, Any]) -> Tuple[float, str, bool, List[str]]:
    """Strategic 미래가치를 더하기 전 '현재만'의 기초가치를 고른다.

    반환: (base, source, future_addition_allowed, reasons)
    current-only 기초가치가 없고 기존 라이브 적정가만 남아 있으면 그 값에는 FY1/FY2 또는
    미래성장모형이 섞였을 수 있으므로 미래증분을 추가하지 않는다.
    """
    adaptive = valuation.get("적응형가치모형", {}) if isinstance(valuation.get("적응형가치모형"), dict) else {}
    candidates = [
        (safe_float(valuation.get("현재재무기초가치")), "현재재무기초가치"),
        (safe_float(adaptive.get("현재재무기초가치")), "적응형 현재재무기초가치"),
    ]
    for value, source in candidates:
        if value > 0:
            return value, source, True, ["TTM·정상화·자산·FCF 기반 현재가치와 미래증분을 분리"]

    return 0.0, "현재-only 기초가치 없음", False, [
        "현재-only 기초가치가 없어 FY1/FY2·미래성장과의 이중계산 가능성을 차단"
    ]

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
    external_consensus: Optional[Dict[str, Any]] = None,
    stock_code: str = "",
    company_name: str = "",
) -> Dict[str, Any]:
    """전략적 미래가치 Shadow 결과를 생성한다."""
    financial = financial or {}
    fundamentals_analysis = fundamentals_analysis or {}
    industry_analysis = industry_analysis or {}

    adaptive = valuation.get("적응형가치모형", {}) if isinstance(valuation.get("적응형가치모형"), dict) else {}
    current_only_base, current_only_source, current_only_available, double_count_reasons = _select_current_only_base(valuation)
    legacy_base = safe_float(valuation.get("재무적정가"))
    if legacy_base <= 0:
        legacy_base = safe_float(valuation.get("기존V4재무적정가"))
    strategic_base = legacy_base if legacy_base > 0 else current_only_base
    base_source = "기존 라이브 재무적정가" if legacy_base > 0 else current_only_source
    future_addition_allowed = False

    sotp = build_sotp_base(segment_data)
    verified_sotp = sotp.get("사용가능") is True
    if verified_sotp:
        strategic_base = safe_float(sotp.get("주당SOTP기초가치"))
        base_source = "검증된 SOTP기초가치"
        future_addition_allowed = True
        double_count_reasons = ["검증된 SOTP 현재가치와 미래증분을 분리"]

    company = company_growth_axis(valuation, fundamentals_analysis)
    industry = industry_growth_axis(
        industry_analysis, stock_code=stock_code, company_name=company_name
    )
    expectation = analyst_expectation_axis(
        fundamentals_analysis, valuation=valuation, external_consensus=external_consensus
    )
    macro = macro_axis(global_macro_context)

    # 기존 미래성장모형은 가격독립적인 FY3/FY4 총가치 후보로 활용한다.
    future_model = (
        valuation.get("미래성장모형", {})
        if isinstance(valuation.get("미래성장모형"), dict)
        else {}
    )
    future_total = (
        safe_float(future_model.get("가치"))
        if future_model.get("사용가능") is True
        else 0.0
    )
    future_total_source = (
        "FY3/FY4 미래성장모형"
        if future_total > 0
        else ""
    )

    if future_total <= 0:
        adaptive_total = safe_float(adaptive.get("미래총가치"))
        if adaptive_total > 0:
            future_total = adaptive_total
            future_total_source = "적응형 미래총가치"

    # 전략모형 정책:
    # 성장업종에서 FY3/FY4 총가치가 기존 기본가치보다 낮아
    # 미래증분이 0이 되는 경우에만, 이미 가격독립 산식으로
    # 계산된 '성장적정가'를 미래 총가치의 보조 시나리오로 사용할 수 있다.
    # 이 값 자체를 전부 더하지 않고, 기본적정가와 성장적정가의 차이에
    # 아래 evidence recognition factor를 적용한다.
    growth_scenario = safe_float(valuation.get("성장적정가"))
    base_scenario = safe_float(valuation.get("기본적정가"))
    growth_target = future_model.get("대상업종") is True

    use_growth_scenario_gap = bool(
        growth_target
        and growth_scenario > 0
        and base_scenario > 0
        and growth_scenario > base_scenario
        and future_total <= base_scenario
    )

    if use_growth_scenario_gap:
        future_total = max(future_total, growth_scenario)
        future_total_source = "가격독립 성장적정가 시나리오"

    original_future_total = future_total
    future_total, consensus_future_adjustment = _consensus_adjusted_future_total(
        future_total, valuation, expectation
    )

    # 일반 FY3/FY4 총가치는 current-only base와 비교한다.
    # 성장적정가 시나리오 fallback은 동일 valuation family의 base→growth
    # 시나리오 간 격차이므로 기존 기본적정가를 기준으로 부분 인정한다.
    if not verified_sotp and future_total > 0:
        if use_growth_scenario_gap and legacy_base > 0:
            strategic_base = legacy_base
            base_source = "기존 기본적정가"
            future_addition_allowed = True
            double_count_reasons = [
                "기본적정가와 성장적정가의 시나리오 격차만 미래증분 후보로 사용"
            ]
        elif current_only_available and current_only_base > 0:
            strategic_base = current_only_base
            base_source = current_only_source
            future_addition_allowed = True
        else:
            strategic_base = legacy_base if legacy_base > 0 else strategic_base
            base_source = "기존 혼합 재무적정가(미래증분 추가 금지)"
            future_addition_allowed = False

    raw_increment = (
        max(0.0, future_total - strategic_base)
        if strategic_base > 0 and future_addition_allowed
        else 0.0
    )
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
    reasons.extend(double_count_reasons)
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
        "미래이중계산차단": True,
        "미래증분추가허용": bool(future_addition_allowed),
        "SOTP": sotp,
        "기존미래총가치": round(original_future_total, 2),
        "미래총가치출처": future_total_source,
        "원시미래총가치": round(future_total, 2),
        "컨센서스미래가치보정": consensus_future_adjustment,
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
            "시장기대없음": "애널리스트 실적자료가 없으면 임의 목표주가/시장가로 대체하지 않음",
            "시장기대있음": "외부 FY1 EPS/추정기관수/투자의견은 미래가치 근거로 사용하되 목표주가는 적정가에 직접 합산하지 않음",
            "산업자료없음": "산업 선행자료가 없으면 산업 프리미엄 0점",
            "산업시장기대모두부족": "미래가치 후보는 유지하되 미래증분가치 최대 12% 인정",
            "산업만확인": "컨센서스 없으면 미래가치 후보는 유지하되 미래증분가치 최대 45% 인정",
            "거시환경": "품질게이트 통과시에만 0.80~1.10 범위의 실현확률 조정; 새 가치를 만들지 않음",
            "SOTP": "verified/audited 원천·기준일·통화·2개 이상 사업부 EV·희석주식수·순부채 원천이 모두 확인될 때만 진짜 SOTP 사용",
            "미래이중계산": "현재-only 기초가치가 없으면 기존 혼합 재무적정가에 미래증분을 추가하지 않음",
        },
    }
