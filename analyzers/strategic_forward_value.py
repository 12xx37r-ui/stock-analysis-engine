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

from analyzers.valuation import build_standalone_quarters


ENGINE_VERSION = "0.7.0-quarterly-acceleration-quality-gate"


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



def _safe_growth_rate(current: float, previous: float, *, base_floor: float = 0.0) -> Optional[float]:
    current = safe_float(current)
    previous = safe_float(previous)
    if previous == 0 or abs(previous) <= max(0.0, base_floor):
        return None
    return (current / previous - 1.0) * 100.0


def earnings_acceleration_quality_axis(
    fundamentals_bundle: Dict[str, Any],
    valuation: Dict[str, Any],
) -> Dict[str, Any]:
    """직전분기/전년동기 급등이 구조적 가속인지 기저효과인지 판별한다."""
    periods_block = fundamentals_bundle.get("재무기간", {}) if isinstance(fundamentals_bundle, dict) else {}
    periods = periods_block.get("기간목록", []) if isinstance(periods_block, dict) else []
    if not isinstance(periods, list) or not periods:
        return {"점수":50.0,"품질":0.0,"사용가능":False,"지속가능성배수":0.90,
                "기저효과위험":False,"이익단독급등":False,"연속성점수":0.0,"비교분기수":0,
                "근거":["단독분기 이력 부족 → 기존 성장증거만 사용"],"입력":{}}
    try:
        quarters=[q for q in build_standalone_quarters(periods) if q.get("단독분기변환") is True]
    except Exception:
        quarters=[]
    if len(quarters)<2:
        return {"점수":50.0,"품질":20.0,"사용가능":False,"지속가능성배수":0.90,
                "기저효과위험":False,"이익단독급등":False,"연속성점수":0.0,"비교분기수":0,
                "근거":["비교 가능한 단독분기 2개 미만"],"입력":{}}

    by_key={int(q.get("기간키",0)):q for q in quarters if int(q.get("기간키",0))>0}
    latest=quarters[0]; latest_key=int(latest.get("기간키",0))
    previous=by_key.get(latest_key-1); year_ago=by_key.get(latest_key-4)
    def metrics(row):
        return row.get("지표",{}) if isinstance(row,dict) and isinstance(row.get("지표"),dict) else {}
    lm,pm,ym=metrics(latest),metrics(previous),metrics(year_ago)
    rev,op,net=(safe_float(lm.get(k)) for k in ("매출","영업이익","순이익"))
    prev_rev,prev_op,prev_net=(safe_float(pm.get(k)) for k in ("매출","영업이익","순이익"))
    yoy_rev0,yoy_op0,yoy_net0=(safe_float(ym.get(k)) for k in ("매출","영업이익","순이익"))

    qoq_rev=_safe_growth_rate(rev,prev_rev) if previous else None
    qoq_op=_safe_growth_rate(op,prev_op,base_floor=abs(prev_rev)*0.003) if previous else None
    qoq_net=_safe_growth_rate(net,prev_net,base_floor=abs(prev_rev)*0.003) if previous else None
    yoy_rev=_safe_growth_rate(rev,yoy_rev0) if year_ago else None
    yoy_op=_safe_growth_rate(op,yoy_op0,base_floor=abs(yoy_rev0)*0.003) if year_ago else None
    yoy_net=_safe_growth_rate(net,yoy_net0,base_floor=abs(yoy_rev0)*0.003) if year_ago else None

    op_margin=(op/rev*100.0) if rev>0 else None
    prev_margin=(prev_op/prev_rev*100.0) if previous and prev_rev>0 else None
    yoy_margin=(yoy_op0/yoy_rev0*100.0) if year_ago and yoy_rev0>0 else None
    margin_qoq=(op_margin-prev_margin) if op_margin is not None and prev_margin is not None else None
    margin_yoy=(op_margin-yoy_margin) if op_margin is not None and yoy_margin is not None else None

    base_effect=bool(year_ago and yoy_rev0>0 and abs(yoy_op0)/yoy_rev0<0.025 and yoy_op is not None and yoy_op>=100.0)
    profit_only=bool(yoy_op is not None and yoy_op>=60.0 and yoy_rev is not None and yoy_rev<5.0 and (margin_yoy is None or margin_yoy>=2.0))

    comparable=[]
    for q in quarters[:4]:
        k=int(q.get("기간키",0)); older=by_key.get(k-4)
        if not older: continue
        a,b=metrics(q),metrics(older)
        ar,ao=safe_float(a.get("매출")),safe_float(a.get("영업이익"))
        br,bo=safe_float(b.get("매출")),safe_float(b.get("영업이익"))
        gr=_safe_growth_rate(ar,br); go=_safe_growth_rate(ao,bo,base_floor=abs(br)*0.003)
        if gr is not None and go is not None: comparable.append((gr,go))
    continuity=(sum(1 for gr,go in comparable if gr>0 and go>0)/len(comparable)*100.0) if comparable else 0.0

    score=50.0
    if yoy_rev is not None: score += clamp(yoy_rev,-20,30)*0.45
    if yoy_op is not None: score += clamp(yoy_op,-50,100)*0.16
    if qoq_rev is not None: score += clamp(qoq_rev,-20,20)*0.20
    if qoq_op is not None: score += clamp(qoq_op,-40,60)*0.10
    if margin_yoy is not None: score += clamp(margin_yoy,-5,8)*2.0
    if margin_qoq is not None: score += clamp(margin_qoq,-4,5)*1.0
    if comparable: score += (continuity-50.0)*0.20
    if base_effect: score -= 18.0
    if profit_only: score -= 12.0
    score=clamp(score,0.0,100.0)

    quality=clamp(35.0+min(len(quarters),6)*7.5+(15.0 if year_ago else 0.0)+(5.0 if previous else 0.0),0.0,100.0)
    sustain=1.0
    if base_effect: sustain*=0.78
    if profit_only: sustain*=0.82
    if comparable and continuity<50.0: sustain*=0.88
    if yoy_rev is not None and yoy_op is not None and yoy_rev>=10 and yoy_op>=25 and (margin_yoy or 0)>=0:
        sustain=min(1.05,sustain*1.05)
    sustain=clamp(sustain,0.55,1.05)

    reasons=[]
    if yoy_rev is not None and yoy_rev>=10: reasons.append("전년동기 매출 성장 동반")
    if yoy_op is not None and yoy_op>=30: reasons.append("전년동기 영업이익 가속")
    if qoq_rev is not None and qoq_rev>0 and qoq_op is not None and qoq_op>0: reasons.append("직전분기 대비 매출·영업이익 동반 개선")
    if margin_yoy is not None and margin_yoy>=1.0: reasons.append("영업이익률 전년동기 대비 개선")
    if comparable and continuity>=66.0: reasons.append("최근 비교분기 성장 지속성 확인")
    if base_effect: reasons.append("낮은 전년 이익기저로 YoY 과대확대 가능성 감쇠")
    if profit_only: reasons.append("매출 동반 없는 이익 급등 감쇠")
    if not reasons: reasons.append("최근 실적가속은 중립 수준")
    return {"점수":round(score,2),"품질":round(quality,2),"사용가능":quality>=55.0,
            "지속가능성배수":round(sustain,4),"기저효과위험":base_effect,"이익단독급등":profit_only,
            "연속성점수":round(continuity,2),"비교분기수":len(comparable),"근거":reasons,
            "입력":{"최신기간키":latest_key,
                    "매출YoY":None if yoy_rev is None else round(yoy_rev,2),"영업이익YoY":None if yoy_op is None else round(yoy_op,2),
                    "순이익YoY":None if yoy_net is None else round(yoy_net,2),"매출QoQ":None if qoq_rev is None else round(qoq_rev,2),
                    "영업이익QoQ":None if qoq_op is None else round(qoq_op,2),"순이익QoQ":None if qoq_net is None else round(qoq_net,2),
                    "영업이익률":None if op_margin is None else round(op_margin,2),
                    "영업이익률YoY변화":None if margin_yoy is None else round(margin_yoy,2),
                    "영업이익률QoQ변화":None if margin_qoq is None else round(margin_qoq,2)}}


def company_growth_axis(
    valuation: Dict[str, Any],
    fundamentals_analysis: Dict[str, Any],
    acceleration_quality: Optional[Dict[str, Any]] = None,
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
    acceleration_quality = acceleration_quality or {}
    if acceleration_quality.get("사용가능") is True:
        acceleration_score = clamp(safe_float(acceleration_quality.get("점수"), 50.0), 0.0, 100.0)
        score = clamp(score * 0.65 + acceleration_score * 0.35, 0.0, 100.0)

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
            "실적가속품질점수": safe_float((acceleration_quality or {}).get("점수"), 0.0),
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




def industry_environment_opportunity_axis(environment: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """산업환경 엔진의 현재/3개월/개선폭을 미래가치 *자격*에 사용한다.

    이 축은 독립적으로 새 가치를 만들지 않는다. 이미 가격독립적으로 계산된
    ``원시미래증분가치``의 인정 자격과 실현 가능성만 제한적으로 조정한다.
    """
    env = environment or {}
    usable = env.get("사용가능") is True or env.get("모형사용가능") is True
    current = safe_float(env.get("현재점수"), -1.0)
    future = safe_float(env.get("3개월점수"), -1.0)
    delta = safe_float(env.get("변화점수"), future - current if current >= 0 and future >= 0 else 0.0)
    quality = _bounded_quality(env.get("품질점수"), 0.0)

    if not usable or current < 0 or future < 0 or quality < 55.0:
        return {
            "점수": 0.0, "품질": round(quality, 2), "사용가능": False,
            "기회배수": 1.0, "국면": "미검증",
            "근거": ["검증 가능한 산업환경 현재·향후값 부족"],
            "입력": {"현재점수": None if current < 0 else current, "3개월점수": None if future < 0 else future, "변화점수": delta},
        }

    # 개선폭은 -20p 이하=0, 0p=50, +20p 이상=100으로 매핑한다.
    improvement = clamp(50.0 + delta * 2.5, 0.0, 100.0)
    score = clamp(current * 0.25 + future * 0.50 + improvement * 0.25, 0.0, 100.0)

    if current >= 70.0 and future >= 70.0 and delta >= 3.0:
        regime = "활황·추가개선"
    elif future >= 65.0 and delta >= 8.0:
        regime = "개선가속"
    elif current >= 70.0 and delta <= -6.0:
        regime = "활황·둔화"
    elif future >= 60.0:
        regime = "우호"
    elif future < 45.0 and delta <= 0.0:
        regime = "약세"
    else:
        regime = "중립"

    # 산업환경은 미래가치를 생성하지 않고 최대 ±15%의 기회배수만 제공한다.
    opportunity_modifier = clamp(0.85 + score / 100.0 * 0.30, 0.85, 1.15)
    if regime == "활황·둔화":
        opportunity_modifier = min(opportunity_modifier, 1.00)
    elif regime == "약세":
        opportunity_modifier = min(opportunity_modifier, 0.90)

    reasons: List[str] = []
    if regime in {"활황·추가개선", "개선가속"}:
        reasons.append("산업환경 현재·향후값이 우호적이고 개선폭도 양호")
    elif regime == "활황·둔화":
        reasons.append("현재 산업은 활황이나 향후 둔화 신호")
    elif regime == "약세":
        reasons.append("산업환경 약세로 미래가치 확대 제한")

    return {
        "점수": round(score, 2),
        "품질": round(quality, 2),
        "사용가능": True,
        "기회배수": round(opportunity_modifier, 4),
        "국면": regime,
        "근거": reasons,
        "입력": {
            "현재점수": round(current, 2),
            "3개월점수": round(future, 2),
            "변화점수": round(delta, 2),
            "개선폭점수": round(improvement, 2),
        },
    }


def unrealized_growth_axis(valuation: Dict[str, Any], expectation: Dict[str, Any]) -> Dict[str, Any]:
    """FY3/FY4 성장 중 FY1·현재 이익에 아직 반영되지 않은 비율을 추정한다.

    미래성장모형의 총 성장 자체를 다시 평가하는 것이 아니라, 이미 현재 재무기초가치와
    FY1에 들어온 성장을 제거해 경제적 이중계산을 줄이는 장치다.
    """
    future_model = valuation.get("미래성장모형", {}) if isinstance(valuation.get("미래성장모형"), dict) else {}
    adaptive = valuation.get("적응형가치모형", {}) if isinstance(valuation.get("적응형가치모형"), dict) else {}
    current_eps = safe_float(adaptive.get("현재EPS앵커"))
    if current_eps <= 0:
        current_eps = safe_float(valuation.get("TTM_EPS"))
    internal_fy1 = safe_float(valuation.get("FY1예상EPS"))
    inp = expectation.get("입력", {}) if isinstance(expectation.get("입력"), dict) else {}
    external_fy1 = safe_float(inp.get("외부FY1EPS")) if expectation.get("사용가능") else 0.0
    # 외부 컨센서스가 있으면 과도한 단일 추정치를 피하기 위해 내부값과 중간값을 사용한다.
    if external_fy1 > 0 and internal_fy1 > 0:
        fy1_eps = (external_fy1 + internal_fy1) / 2.0
    else:
        fy1_eps = external_fy1 if external_fy1 > 0 else internal_fy1
    fy3_eps = safe_float(future_model.get("FY3EPS"))
    fy4_eps = safe_float(future_model.get("FY4EPS"))

    def remaining(target: float) -> Optional[float]:
        if current_eps <= 0 or target <= current_eps:
            return None
        if fy1_eps <= 0:
            return 0.55
        already = clamp((fy1_eps - current_eps) / (target - current_eps), 0.0, 1.0)
        return clamp(1.0 - already, 0.15, 1.0)

    r3 = remaining(fy3_eps)
    r4 = remaining(fy4_eps)
    values = [(r3, 0.60), (r4, 0.40)]
    usable_values = [(v, w) for v, w in values if v is not None]
    if not usable_values:
        factor = 0.50
        usable = False
        reason = "현재/FY1/FY3·FY4 EPS 연결고리 부족 → 미반영성장 50% 보수 가정"
    else:
        denom = sum(w for _, w in usable_values)
        factor = sum(v * w for v, w in usable_values) / denom
        usable = True
        reason = "FY1에 이미 반영된 성장과 FY3·FY4까지 남은 성장을 분리"

    return {
        "미반영성장비율": round(clamp(factor, 0.15, 1.0), 4),
        "사용가능": usable,
        "근거": [reason],
        "입력": {
            "현재EPS앵커": round(current_eps, 4),
            "FY1EPS앵커": round(fy1_eps, 4),
            "FY3EPS": round(fy3_eps, 4),
            "FY4EPS": round(fy4_eps, 4),
        },
    }


def cycle_sustainability_axis(valuation: Dict[str, Any], industry_env_axis: Dict[str, Any], acceleration_quality: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """사이클 고점 이익의 영구화를 막는 연속형 지속가능성 계수."""
    future_model = valuation.get("미래성장모형", {}) if isinstance(valuation.get("미래성장모형"), dict) else {}
    adaptive = valuation.get("적응형가치모형", {}) if isinstance(valuation.get("적응형가치모형"), dict) else {}
    limited_reasons = [str(x) for x in (future_model.get("제한사유") or []) if str(x)]
    run_rate_ratio = safe_float(adaptive.get("분기런레이트대정상화배수"), 1.0)
    factor = 1.0
    reasons: List[str] = []

    if any("사이클 고점 이익 영구화 위험" in x for x in limited_reasons):
        factor *= 0.70
        reasons.append("사이클 고점 이익 영구화 위험 감쇠")
    if run_rate_ratio >= 6.0:
        factor *= 0.60
        reasons.append("분기 런레이트가 정상화 이익의 6배 이상")
    elif run_rate_ratio >= 3.0:
        factor *= 0.72
        reasons.append("분기 런레이트가 정상화 이익의 3배 이상")
    elif run_rate_ratio >= 2.0:
        factor *= 0.85
        reasons.append("분기 런레이트가 정상화 이익을 크게 상회")

    if industry_env_axis.get("사용가능") is True:
        delta = safe_float(_analysis_dict(industry_env_axis, "입력").get("변화점수"))
        current = safe_float(_analysis_dict(industry_env_axis, "입력").get("현재점수"))
        if current >= 70.0 and delta <= -6.0:
            factor *= 0.85
            reasons.append("산업 활황 이후 향후 둔화 예상")

    acceleration_quality = acceleration_quality or {}
    if acceleration_quality.get("사용가능") is True:
        accel_sustain = clamp(safe_float(acceleration_quality.get("지속가능성배수"), 1.0), 0.55, 1.05)
        factor *= accel_sustain
        if accel_sustain < 0.95:
            reasons.append("최근 실적급등의 기저효과·단발성 위험 감쇠")
        elif accel_sustain > 1.0:
            reasons.append("매출·마진 동반 및 연속 성장으로 지속가능성 보강")

    return {
        "지속가능성배수": round(clamp(factor, 0.30, 1.0), 4),
        "근거": reasons or ["특별한 사이클 감쇠 신호 없음"],
        "입력": {"분기런레이트대정상화배수": round(run_rate_ratio, 4),
                 "실적가속지속가능성": round(safe_float(acceleration_quality.get("지속가능성배수"), 1.0),4)},
    }



def company_industry_benefit_axis(
    valuation: Dict[str, Any],
    company: Dict[str, Any],
    industry: Dict[str, Any],
    expectation: Dict[str, Any],
) -> Dict[str, Any]:
    """산업 성장의 직접 수혜 가능성을 보수적으로 점수화한다.

    사업부별 매출노출/점유율 원천이 없으면 '실제 점유율'을 추정하지 않는다.
    대신 미래성장모형 대상업종 여부 + 해당 기업 실적의 동행 + 산업 독립신호를
    검증 대용치로 사용하고 점수를 85점 이하로 제한한다.
    """
    future_model = valuation.get("미래성장모형", {}) if isinstance(valuation.get("미래성장모형"), dict) else {}
    target = future_model.get("대상업종") is True and future_model.get("사용가능") is True
    company_score = safe_float(company.get("점수")) if company.get("사용가능") else 0.0
    industry_score = safe_float(industry.get("점수")) if industry.get("사용가능") else 0.0
    expectation_score = safe_float(expectation.get("점수")) if expectation.get("사용가능") else 0.0
    structural = valuation.get("구조적실적가속") is True
    reasons_src = [str(x) for x in (future_model.get("선정근거") or []) if str(x)]
    industry_link = any("산업" in x or "사이클" in x for x in reasons_src)

    if not target:
        return {"점수": 15.0 if industry_score >= 55 else 5.0, "사용가능": False,
                "검증방식": "대용지표", "근거": ["미래성장모형 대상업종 검증 실패"]}

    score = 42.0
    score += min(18.0, company_score * 0.18)
    score += min(12.0, industry_score * 0.12)
    score += min(8.0, expectation_score * 0.08)
    score += 8.0 if structural else 0.0
    score += 5.0 if industry_link else 0.0
    score = clamp(score, 0.0, 85.0)
    reasons = ["미래성장모형 대상업종과 기업 실적 동행 확인"]
    if structural: reasons.append("구조적 실적가속 확인")
    if industry_link: reasons.append("산업사이클/선행근거가 기업 성장근거에 포함")
    reasons.append("사업부 매출노출·점유율 원천 부재로 수혜도는 보수적 대용점수 사용")
    return {"점수": round(score,2), "사용가능": True, "검증방식": "대용지표", "근거": reasons}


def confirmed_forward_financial_axis(valuation: Dict[str, Any], current_only_base: float) -> Dict[str, Any]:
    """현재-only와 기존 기본적정가 사이의 '확인된 선행재무가치'를 분리한다.

    일반 성장기업은 기존 기본적정가까지의 차이를 보존한다. 다만 이익급회복/사이클
    고점처럼 현재·FY1 이익이 비정상적으로 팽창한 경우에는 그 차이를 전부
    '확인된 가치'로 취급하지 않고 지속가능성에 따라 제한한다.
    """
    legacy_base = safe_float(valuation.get("재무적정가")) or safe_float(valuation.get("기본적정가")) or safe_float(valuation.get("기존V4재무적정가"))
    raw_gap = max(0.0, legacy_base - current_only_base) if current_only_base > 0 else 0.0
    adaptive = valuation.get("적응형가치모형", {}) if isinstance(valuation.get("적응형가치모형"), dict) else {}
    future_model = valuation.get("미래성장모형", {}) if isinstance(valuation.get("미래성장모형"), dict) else {}
    run_rate = safe_float(adaptive.get("분기런레이트대정상화배수"), 1.0)
    dislocation = adaptive.get("이익급회복괴리") is True
    limited = [str(x) for x in (future_model.get("제한사유") or []) if str(x)]
    cycle_peak = any("사이클 고점 이익 영구화 위험" in x for x in limited)
    factor = 1.0
    reasons=[]
    if dislocation or run_rate >= 6.0:
        factor = min(factor, 0.10)
        reasons.append("극단적 이익급회복/런레이트로 선행재무가치 10%만 확정")
    elif run_rate >= 3.0:
        factor = min(factor, 0.25)
        reasons.append("분기 런레이트가 정상화 이익을 크게 상회해 25%만 확정")
    elif run_rate >= 2.0:
        factor = min(factor, 0.50)
        reasons.append("분기 런레이트가 정상화 이익의 2배 이상이라 50%만 확정")
    if cycle_peak:
        factor = min(factor, 0.25)
        reasons.append("사이클 고점 영구화 위험으로 선행재무가치 확정률 제한")
    confirmed = raw_gap * factor
    return {
        "기존기본적정가": round(legacy_base,2), "원시선행재무가치": round(raw_gap,2),
        "선행재무확정률": round(factor,4), "확인된선행재무가치": round(confirmed,2),
        "사용가능": bool(current_only_base > 0 and legacy_base > 0),
        "근거": reasons or ["사이클 급팽창 경고가 없어 기존 기본적정가까지의 선행재무가치 보존"],
    }

def future_value_eligibility_axis(
    *,
    valuation: Dict[str, Any],
    company: Dict[str, Any],
    industry: Dict[str, Any],
    industry_env: Dict[str, Any],
    expectation: Dict[str, Any],
    unrealized: Optional[Dict[str, Any]] = None,
    sustainability: Optional[Dict[str, Any]] = None,
    beneficiary: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """미래가치 기업 필터 V3.

    점수 = 산업 향후 35% + 기업 산업수혜도 25% + 기업 성장증거 20%
         + 미반영성장 15% + 데이터품질 5% - 사이클고점 감점.
    """
    future_model = valuation.get("미래성장모형", {}) if isinstance(valuation.get("미래성장모형"), dict) else {}
    target = future_model.get("대상업종") is True and future_model.get("사용가능") is True
    if not target:
        return {"등급":"비대상","점수":0.0,"최대인정률":0.05,"사용가능":False,
                "근거":["검증된 미래성장모형 대상기업이 아님"]}

    unrealized = unrealized or {}
    sustainability = sustainability or {}
    beneficiary = beneficiary or company_industry_benefit_axis(valuation, company, industry, expectation)
    env_available = industry_env.get("사용가능") is True
    industry_future = safe_float(industry_env.get("점수")) if env_available else (safe_float(industry.get("점수")) if industry.get("사용가능") else 0.0)
    benefit_score = safe_float(beneficiary.get("점수"))
    company_score = safe_float(company.get("점수")) if company.get("사용가능") else 0.0
    unrealized_score = clamp(safe_float(unrealized.get("미반영성장비율"),0.0)*100.0,0.0,100.0)
    qualities=[safe_float(x.get("품질")) for x in (company,industry,industry_env,expectation) if isinstance(x,dict) and x.get("사용가능") is True and safe_float(x.get("품질"))>0]
    quality_score=sum(qualities)/len(qualities) if qualities else _bounded_quality(future_model.get("품질"),0.0)
    sustain=clamp(safe_float(sustainability.get("지속가능성배수"),1.0),0.30,1.0)
    cycle_penalty=(1.0-sustain)*25.0

    score = industry_future*0.35 + benefit_score*0.25 + company_score*0.20 + unrealized_score*0.15 + quality_score*0.05 - cycle_penalty
    score=clamp(score,0.0,100.0)
    # 미반영 성장률 하나만 높아서 약한 산업/약한 기업이 통과하지 못하게 최소자격을 둔다.
    weak_core = (industry_future < 45.0 and company_score < 20.0) or (benefit_score < 40.0 and company_score < 20.0)
    if weak_core:
        grade,cap="비대상",0.10
    elif score>=75 and env_available and benefit_score>=55 and company_score>=50:
        grade,cap="고성장 대상",1.20
    elif score>=58:
        grade,cap="정상 대상",0.80
    elif score>=38:
        grade,cap="제한 대상",0.40
    else:
        grade,cap="비대상",0.10
    if not env_available and grade=="고성장 대상": grade,cap="정상 대상",0.80
    reasons=[f"미래가치 자격 {grade}", f"산업향후 {industry_future:.1f}·수혜도 {benefit_score:.1f}·기업성장 {company_score:.1f}·미반영 {unrealized_score:.1f}"]
    if cycle_penalty>0: reasons.append(f"사이클 지속가능성 감점 -{cycle_penalty:.1f}점")
    if not env_available: reasons.append("산업환경 3개월 품질 미달 → 기존 산업사이클로 대체하고 고성장 승격 금지")
    return {"등급":grade,"점수":round(score,2),"최대인정률":round(cap,4),"사용가능":grade!="비대상",
            "산업환경검증":env_available,"사이클감점":round(cycle_penalty,2),"구성점수":{
                "산업향후":round(industry_future,2),"기업산업수혜도":round(benefit_score,2),"기업성장증거":round(company_score,2),
                "미반영성장":round(unrealized_score,2),"데이터품질":round(quality_score,2)},"근거":reasons}

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



FUTURE_INCREMENT_CAP_POLICY_VERSION = "1.0.0"


def _future_increment_cap_ratio(
    *,
    valuation: Dict[str, Any],
    future_model: Dict[str, Any],
    company: Dict[str, Any],
    industry: Dict[str, Any],
    expectation: Dict[str, Any],
) -> Tuple[float, List[str]]:
    """현재 재무기초가치 대비 최종 미래증분 상한.

    미래가치 후보 계산은 유지하되, 좋은 신호가 여러 개 겹쳐도
    현재가치보다 과도하게 큰 금액이 한 번에 붙는 것을 제한한다.
    현재가·목표주가·시장가격은 사용하지 않는다.
    """
    status = str(future_model.get("상태") or "")
    limited_reasons = [
        str(x) for x in (future_model.get("제한사유") or [])
        if str(x)
    ]

    ratio = 1.00
    reasons: List[str] = ["기본 미래증분 상한 = 현재 재무기초가치의 100%"]

    if status == "제한사용":
        ratio = min(ratio, 0.70)
        reasons.append("미래성장모형 제한사용 → 미래증분 상한 70%")

    if any("사이클 고점 이익 영구화 위험" in r for r in limited_reasons):
        ratio = min(ratio, 0.65)
        reasons.append("사이클 고점 이익 영구화 위험 → 미래증분 상한 65%")

    company_score = safe_float(company.get("점수")) if company.get("사용가능") else 0.0
    industry_score = safe_float(industry.get("점수")) if industry.get("사용가능") else 0.0
    expectation_score = safe_float(expectation.get("점수")) if expectation.get("사용가능") else 0.0
    structural_acceleration = valuation.get("구조적실적가속") is True

    if (
        status != "제한사용"
        and structural_acceleration
        and company_score >= 70.0
        and industry_score >= 60.0
        and expectation_score >= 60.0
    ):
        ratio = 1.20
        reasons = ["구조적 실적가속 + 기업·산업·시장기대 강세 → 미래증분 상한 120%"]

    return clamp(ratio, 0.0, 1.20), reasons

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
    fundamentals_bundle: Optional[Dict[str, Any]] = None,
    industry_analysis: Optional[Dict[str, Any]] = None,
    industry_environment: Optional[Dict[str, Any]] = None,
    global_macro_context: Optional[Dict[str, Any]] = None,
    segment_data: Optional[Dict[str, Any]] = None,
    external_consensus: Optional[Dict[str, Any]] = None,
    stock_code: str = "",
    company_name: str = "",
) -> Dict[str, Any]:
    """전략적 미래가치 Shadow 결과를 생성한다."""
    financial = financial or {}
    fundamentals_analysis = fundamentals_analysis or {}
    fundamentals_bundle = fundamentals_bundle or {}
    industry_analysis = industry_analysis or {}
    industry_environment = industry_environment or {}

    adaptive = valuation.get("적응형가치모형", {}) if isinstance(valuation.get("적응형가치모형"), dict) else {}
    current_only_base, current_only_source, current_only_available, double_count_reasons = _select_current_only_base(valuation)
    legacy_base = safe_float(valuation.get("재무적정가"))
    if legacy_base <= 0:
        legacy_base = safe_float(valuation.get("기존V4재무적정가"))
    strategic_base = current_only_base if current_only_base > 0 else legacy_base
    base_source = current_only_source if current_only_base > 0 else "기존 라이브 재무적정가"
    future_addition_allowed = bool(current_only_available and current_only_base > 0)

    sotp = build_sotp_base(segment_data)
    verified_sotp = sotp.get("사용가능") is True
    if verified_sotp:
        strategic_base = safe_float(sotp.get("주당SOTP기초가치"))
        base_source = "검증된 SOTP기초가치"
        future_addition_allowed = True
        current_only_base = strategic_base
        current_only_available = True
        double_count_reasons = ["검증된 SOTP 현재가치와 미래증분을 분리"]

    acceleration_quality = earnings_acceleration_quality_axis(fundamentals_bundle, valuation)
    company = company_growth_axis(valuation, fundamentals_analysis, acceleration_quality)
    industry = industry_growth_axis(
        industry_analysis, stock_code=stock_code, company_name=company_name
    )
    expectation = analyst_expectation_axis(
        fundamentals_analysis, valuation=valuation, external_consensus=external_consensus
    )
    macro = macro_axis(global_macro_context)
    industry_env = industry_environment_opportunity_axis(industry_environment)

    # 기존 미래성장모형은 가격독립적인 FY3/FY4 총가치 후보로 활용한다.
    future_model = (
        valuation.get("미래성장모형", {})
        if isinstance(valuation.get("미래성장모형"), dict)
        else {}
    )
    unrealized = unrealized_growth_axis(valuation, expectation)
    sustainability = cycle_sustainability_axis(valuation, industry_env, acceleration_quality)
    beneficiary = company_industry_benefit_axis(valuation, company, industry, expectation)
    eligibility = future_value_eligibility_axis(
        valuation=valuation, company=company, industry=industry,
        industry_env=industry_env, expectation=expectation,
        unrealized=unrealized, sustainability=sustainability, beneficiary=beneficiary,
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

    # 3층 구조: 현재-only + 확인된 선행재무 + 미실현 미래성장.
    # SOTP는 별도의 검증 현재가치이므로 선행재무 gap을 추가하지 않는다.
    confirmed_forward = (
        {"기존기본적정가": round(strategic_base,2), "원시선행재무가치":0.0, "선행재무확정률":0.0,
         "확인된선행재무가치":0.0, "사용가능":False, "근거":["검증 SOTP 사용 시 별도 선행재무층 미추가"]}
        if verified_sotp else confirmed_forward_financial_axis(valuation, strategic_base)
    )
    confirmed_forward_value = safe_float(confirmed_forward.get("확인된선행재무가치"))
    pre_future_base = strategic_base + confirmed_forward_value
    if not current_only_available and not verified_sotp:
        confirmed_forward_value = 0.0
        pre_future_base = strategic_base
        future_addition_allowed = False

    raw_increment = (
        max(0.0, future_total - pre_future_base)
        if strategic_base > 0 and future_addition_allowed
        else 0.0
    )
    evidence_factor, cap_reasons = _evidence_recognition_factor(company, industry, expectation)
    eligibility_cap = safe_float(eligibility.get("최대인정률"), 0.10)
    evidence_factor = min(evidence_factor, eligibility_cap)
    industry_opportunity_modifier = safe_float(industry_env.get("기회배수"), 1.0)
    unrealized_factor = safe_float(unrealized.get("미반영성장비율"), 0.50)
    sustainability_factor = safe_float(sustainability.get("지속가능성배수"), 1.0)
    macro_modifier = safe_float(macro.get("조정배수"), 1.0)
    uncapped_recognized_increment = (
        raw_increment
        * evidence_factor
        * industry_opportunity_modifier
        * unrealized_factor
        * sustainability_factor
        * macro_modifier
    )

    # 어떤 보정도 원시 미래증분 자체를 넘어 새 가치를 만들 수 없다.
    uncapped_recognized_increment = min(uncapped_recognized_increment, raw_increment)

    increment_cap_ratio, increment_cap_reasons = _future_increment_cap_ratio(
        valuation=valuation,
        future_model=future_model,
        company=company,
        industry=industry,
        expectation=expectation,
    )
    increment_cap_value = (
        strategic_base * increment_cap_ratio
        if strategic_base > 0 and future_addition_allowed
        else 0.0
    )

    unrealized_future_value = min(
        uncapped_recognized_increment,
        increment_cap_value if increment_cap_value > 0 else uncapped_recognized_increment,
    )
    total_increment = confirmed_forward_value + unrealized_future_value
    strategic_fair = strategic_base + total_increment if strategic_base > 0 else 0.0

    evidence_quality_parts = []
    for axis in (company, industry, expectation):
        if axis.get("사용가능"):
            evidence_quality_parts.append(safe_float(axis.get("품질")))
    evidence_quality = sum(evidence_quality_parts) / len(evidence_quality_parts) if evidence_quality_parts else 0.0
    if not expectation.get("사용가능"):
        evidence_quality = min(evidence_quality, 72.0)
    if not industry.get("사용가능"):
        evidence_quality = min(evidence_quality, 62.0)

    label = future_value_label(pre_future_base, unrealized_future_value)
    reasons = []
    reasons.extend(double_count_reasons)
    reasons.extend(company.get("근거", []))
    reasons.extend(industry.get("근거", []))
    reasons.extend(expectation.get("근거", []))
    reasons.extend(industry_env.get("근거", []))
    reasons.extend(eligibility.get("근거", []))
    reasons.extend(unrealized.get("근거", []))
    reasons.extend(sustainability.get("근거", []))
    reasons.extend(macro.get("근거", []))
    reasons.extend(cap_reasons)
    reasons.extend(increment_cap_reasons)

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
        "현재재무기초가치": round(strategic_base, 2),
        "확인된선행재무": confirmed_forward,
        "확인된선행재무가치": round(confirmed_forward_value, 2),
        "선행재무반영후기초가치": round(pre_future_base, 2),
        "미래가치인정률": round(evidence_factor * 100.0, 2),
        "미래가치자격": eligibility,
        "산업환경기회": industry_env,
        "실적가속품질": acceleration_quality,
        "미반영성장": unrealized,
        "사이클지속가능성": sustainability,
        "산업기회배수": round(industry_opportunity_modifier, 4),
        "미반영성장비율": round(unrealized_factor * 100.0, 2),
        "사이클지속가능성배수": round(sustainability_factor, 4),
        "거시조정배수": round(macro_modifier, 4),
        "상한적용전미래증분가치": round(uncapped_recognized_increment, 2),
        "미래증분상한정책버전": FUTURE_INCREMENT_CAP_POLICY_VERSION,
        "미래증분상한비율": round(increment_cap_ratio * 100.0, 2),
        "미래증분상한금액": round(increment_cap_value, 2),
        "미래증분상한적용": bool(
            increment_cap_value > 0
            and uncapped_recognized_increment > increment_cap_value + 1e-9
        ),
        "미실현미래성장가치": round(unrealized_future_value, 2),
        "미래증분가치": round(total_increment, 2),
        "전략펀더멘털적정가": round(strategic_fair, 2),
        "미래성장가치표시": label,
        "미래성장가치표시문구": f"{label} · +{unrealized_future_value:,.0f}원" if unrealized_future_value > 0 else label,
        "근거신뢰도": round(evidence_quality, 2),
        "근거축": {
            "기업실적가속": company,
            "기존산업사이클": industry,
            "산업환경현재향후": industry_env,
            "미래가치기업분류": eligibility,
            "기업산업수혜도": beneficiary,
            "확인된선행재무": confirmed_forward,
            "미반영성장": unrealized,
            "사이클지속가능성": sustainability,
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
            "미래이중계산": "현재-only + 확인된 선행재무 + 미실현 미래성장의 3층 구조; 사이클 급팽창 구간은 선행재무 gap도 제한",
            "미래가치자격": "산업환경 현재·향후·개선폭과 기업 성장증거로 비대상/제한/정상/고성장 대상을 먼저 분류",
            "미반영성장": "FY1에 이미 반영된 성장은 제외하고 FY3·FY4까지 남은 성장만 증분가치로 인정",
            "사이클지속성": "사이클 고점·과도한 분기 런레이트는 연속형 지속가능성 배수로 감쇠",
            "미래증분상한": "현재가·목표주가와 무관하게 현재 재무기초가치 대비 미래증분 상한을 적용; 제한사용 70%, 사이클 고점 위험 65%, 구조적 가속 강증거 정상사용만 최대 120%",
        },
    }
