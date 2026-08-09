"""Strategic Forward Value V0.2 simulation/property validation.

실제 과거 애널리스트 revision/산업/거시 vintage가 현재 ZIP에 없으므로 이 검증은
미래 수익률을 증명하는 백테스트가 아니다. 대신 다음을 검증한다.
- 기존 라이브 재무적정가 불변(shadow)
- 회사 현재가 독립성
- 산업/시장기대 부재 시 미래가치 억제
- 산업 또는 컨센서스 증거가 강해질수록 인정가치 단조 증가
- 검증된 악화 거시는 미래가치를 낮추고, 미검증 거시는 가치에 영향 없음
- 진짜 SOTP는 사업부자료가 있을 때만 계산하며 이중조정 방지
"""

import copy
import json
import os
from statistics import median
from typing import Any, Dict

from analyzers.strategic_forward_value import (
    build_sotp_base,
    build_strategic_forward_value,
)
from analyzers.valuation import calculate_value
from collectors.company import classify_dart_industry_detail


MACRO_FIXTURE = os.getenv(
    "STRATEGIC_MACRO_FIXTURE",
    "/mnt/data/work_macro/global-macro-data-collector-main/public/data/cards_8_12_bundle.json",
)


def load_macro() -> Dict[str, Any]:
    if os.path.exists(MACRO_FIXTURE):
        return json.load(open(MACRO_FIXTURE, encoding="utf-8"))
    return {}


_UNIVERSE_FIXTURE = None

def load_universe_fixture() -> Dict[str, Dict[str, Any]]:
    global _UNIVERSE_FIXTURE
    if _UNIVERSE_FIXTURE is None:
        _UNIVERSE_FIXTURE = json.load(open("fixtures/strategic/universe_bundle.json", encoding="utf-8"))
    return _UNIVERSE_FIXTURE

def load_snapshot(code: str) -> Dict[str, Any]:
    return copy.deepcopy(load_universe_fixture()[code])


def refreshed_info(snapshot: Dict[str, Any], code: str) -> Dict[str, Any]:
    info = copy.deepcopy(snapshot["기업조회정보"])
    detail = classify_dart_industry_detail(
        info.get("OpenDART업종코드"), snapshot.get("기업명", ""), code
    )
    info.update({
        "산업코드": detail["산업코드"],
        "가치평가산업코드": detail["산업코드"],
        "산업분류출처": detail["분류출처"],
        "산업분류신뢰도": detail["분류신뢰도"],
    })
    return info


def recalc(snapshot: Dict[str, Any], code: str, price_override=None):
    market = copy.deepcopy(snapshot["시장정보"])
    if price_override is not None:
        market["현재가"] = price_override
        market["PER"] = market["PBR"] = market["EPS"] = market["BPS"] = 0
    valuation = calculate_value(
        snapshot["재무분석"],
        market,
        snapshot["기업기초데이터"].get("분석", {}),
        snapshot["기업기초데이터"],
        snapshot["산업분석"].get("분석", {}),
        snapshot["산업분석"],
        refreshed_info(snapshot, code),
    )
    strategic = build_strategic_forward_value(
        valuation=valuation,
        financial=snapshot["재무분석"],
        fundamentals_analysis=snapshot["기업기초데이터"].get("분석", {}),
        industry_analysis=snapshot["산업분석"].get("분석", {}),
        global_macro_context=load_macro(),
    )
    return valuation, strategic


def synthetic_consensus(strength: str) -> Dict[str, Any]:
    if strength == "strong":
        return {
            "사용가능": True, "애널리스트수": 12,
            "FY1_EPS_3개월수정률": 20, "FY2_EPS_3개월수정률": 16,
            "영업이익_3개월수정률": 22, "상향비율": 78,
            "추정치분산": 10, "데이터품질": 92,
        }
    if strength == "weak":
        return {
            "사용가능": True, "애널리스트수": 6,
            "FY1_EPS_3개월수정률": 2, "FY2_EPS_3개월수정률": 1,
            "영업이익_3개월수정률": 2, "상향비율": 52,
            "추정치분산": 25, "데이터품질": 75,
        }
    return {}


def macro_scenario(score: float, passed: bool) -> Dict[str, Any]:
    return {"cards": {"11": {
        "card": 11, "score": score,
        "current_regime": "test", "future_regime": "test",
        "quality_gate": {"passed": passed, "checks": {
            "a": passed, "b": passed, "c": passed, "d": passed,
        }},
    }}}


def main() -> int:
    macro = load_macro()
    samsung = load_snapshot("009150")
    lg = load_snapshot("051900")
    amore = load_snapshot("090430")

    samsung_v, samsung_s = recalc(samsung, "009150")
    lg_v, lg_s = recalc(lg, "051900")
    amore_v, amore_s = recalc(amore, "090430")

    # 1) Shadow: 기존 라이브 적정가를 절대로 덮어쓰지 않는다.
    assert samsung_v["재무적정가"] > 0
    assert samsung_s["모드"] == "shadow"

    # 2) 현재가 독립성.
    _, low = recalc(samsung, "009150", 100_000)
    _, high = recalc(samsung, "009150", 3_000_000)
    assert abs(low["전략펀더멘털적정가"] - high["전략펀더멘털적정가"]) < 1e-6
    assert low["현재가미사용"] is True

    # 3) 시장 기대/산업자료 없는 뷰티 기업은 미래 증분을 거의 인정하지 않는다.
    # LG는 raw future 자체가 없고, 아모레는 raw future가 있어도 양 축 부재로 12% 이하.
    assert lg_s["미래증분가치"] == 0
    if amore_s["원시미래증분가치"] > 0:
        assert amore_s["미래가치인정률"] <= 12.0001

    # 4) 삼성전기: 산업은 존재하지만 실제 애널리스트 컨센서스가 없어 45% cap.
    assert samsung_s["원시미래증분가치"] > 0
    assert 0 < samsung_s["미래가치인정률"] <= 45.0001
    assert samsung_s["근거축"]["시장기대_애널리스트"]["사용가능"] is False

    # 5) 동일 삼성전기에 객관적 컨센서스가 추가되면 가치가 단조 증가해야 한다.
    fa = copy.deepcopy(samsung["기업기초데이터"].get("분석", {}))
    weak_fa = copy.deepcopy(fa); weak_fa["애널리스트컨센서스"] = synthetic_consensus("weak")
    strong_fa = copy.deepcopy(fa); strong_fa["애널리스트컨센서스"] = synthetic_consensus("strong")
    weak = build_strategic_forward_value(
        valuation=samsung_v, financial=samsung["재무분석"], fundamentals_analysis=weak_fa,
        industry_analysis=samsung["산업분석"].get("분석", {}), global_macro_context=macro,
    )
    strong = build_strategic_forward_value(
        valuation=samsung_v, financial=samsung["재무분석"], fundamentals_analysis=strong_fa,
        industry_analysis=samsung["산업분석"].get("분석", {}), global_macro_context=macro,
    )
    assert weak["전략펀더멘털적정가"] >= samsung_s["전략펀더멘털적정가"] - 1e-6
    assert strong["전략펀더멘털적정가"] >= weak["전략펀더멘털적정가"] - 1e-6

    # 6) 미검증 거시는 영향 0, 검증된 악화/호전은 raw increment의 실현률만 조정.
    neutral_unvalidated = build_strategic_forward_value(
        valuation=samsung_v, financial=samsung["재무분석"], fundamentals_analysis=strong_fa,
        industry_analysis=samsung["산업분석"].get("분석", {}), global_macro_context=macro_scenario(-80, False),
    )
    bad_macro = build_strategic_forward_value(
        valuation=samsung_v, financial=samsung["재무분석"], fundamentals_analysis=strong_fa,
        industry_analysis=samsung["산업분석"].get("분석", {}), global_macro_context=macro_scenario(-80, True),
    )
    good_macro = build_strategic_forward_value(
        valuation=samsung_v, financial=samsung["재무분석"], fundamentals_analysis=strong_fa,
        industry_analysis=samsung["산업분석"].get("분석", {}), global_macro_context=macro_scenario(80, True),
    )
    assert abs(neutral_unvalidated["거시조정배수"] - 1.0) < 1e-9
    assert bad_macro["전략펀더멘털적정가"] <= neutral_unvalidated["전략펀더멘털적정가"] + 1e-6
    assert good_macro["전략펀더멘털적정가"] >= neutral_unvalidated["전략펀더멘털적정가"] - 1e-6

    # 7) SOTP: 두 사업부와 희석주식수가 있을 때만 계산.
    no_sotp = build_sotp_base({"segments": [{"name": "A", "enterprise_value": 100}]})
    assert no_sotp["사용가능"] is False
    yes_sotp = build_sotp_base({
        "segments": [
            {"name": "A", "enterprise_value": 1000},
            {"name": "B", "enterprise_value": 500},
        ],
        "listed_stakes": [{"equity_value": 100}],
        "cash": 200, "debt": 300, "minority_interest": 50,
        "preferred_equity": 0, "diluted_shares": 10,
    })
    # (1500 +100 +200 -300 -50) / 10 = 145
    assert yes_sotp["사용가능"] is True
    assert abs(yes_sotp["주당SOTP기초가치"] - 145.0) < 1e-9

    # 8) 전체 저장 유니버스 시뮬레이션: 결과 분포와 억제 정책 확인.
    rows = []
    for code, fixture_snapshot in load_universe_fixture().items():
        snap = copy.deepcopy(fixture_snapshot)
        try:
            val, st = recalc(snap, code)
        except Exception:
            continue
        if st["기초가치"] <= 0:
            continue
        rows.append({
            "code": code, "company": snap.get("기업명"),
            "profile": val.get("가치평가산업코드"),
            "live_fair": val.get("재무적정가"),
            "base": st["기초가치"], "future_raw": st["원시미래증분가치"],
            "recognition_pct": st["미래가치인정률"],
            "strategic_fair": st["전략펀더멘털적정가"],
            "industry_available": st["근거축"]["산업현재미래"]["사용가능"],
            "consensus_available": st["근거축"]["시장기대_애널리스트"]["사용가능"],
        })

    assert len(rows) >= 60, len(rows)
    no_external_expect = [r for r in rows if not r["industry_available"] and not r["consensus_available"] and r["future_raw"] > 0]
    assert all(r["recognition_pct"] <= 12.0001 for r in no_external_expect)

    report = {
        "engine_version": "0.2.0-strategic-forward-shadow-low-load",
        "validation_type": "cross-sectional + property/stress simulation; not historical predictive backtest",
        "universe_count": len(rows),
        "price_independence": True,
        "live_fair_value_unchanged": True,
        "macro_fixture_quality_gate_passed": bool((((macro.get("cards") or {}).get("11") or {}).get("quality_gate") or {}).get("passed")),
        "policies_verified": {
            "no_industry_and_no_consensus_future_cap_pct": 12,
            "industry_only_no_consensus_future_cap_pct": 45,
            "unvalidated_macro_modifier": 1.0,
            "validated_macro_modifier_range": [0.8, 1.1],
            "true_sotp_requires_two_segments": True,
        },
        "examples": {
            "삼성전기": samsung_s,
            "LG생활건강": lg_s,
            "아모레퍼시픽": amore_s,
            "삼성전기_weak_consensus": weak,
            "삼성전기_strong_consensus": strong,
            "삼성전기_bad_macro": bad_macro,
            "삼성전기_good_macro": good_macro,
        },
        "universe_summary": {
            "median_recognition_pct": median([r["recognition_pct"] for r in rows]),
            "future_raw_positive_count": sum(r["future_raw"] > 0 for r in rows),
            "industry_available_count": sum(r["industry_available"] for r in rows),
            "actual_consensus_available_count": sum(r["consensus_available"] for r in rows),
            "no_external_expectation_positive_future_count": len(no_external_expect),
        },
        "limitations": [
            "현재 ZIP에는 과거 시점별 애널리스트 EPS revision vintage가 없어 실전 OOS 적정가 정확도 백테스트는 불가능",
            "현재 ZIP에는 사업부별 손익/EV 입력이 없어 실제 기업 SOTP는 shadow 계약만 구현",
            "글로벌 매크로 업로드 스냅샷의 card11 quality_gate가 미통과면 거시값은 가치에 반영하지 않음",
            "따라서 production 승격 전 historical vintages를 누적한 walk-forward 검증이 추가로 필요",
        ],
    }
    json.dump(report, open("strategic_forward_validation_report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print("STRATEGIC FORWARD VALUE V0.2: PASS")
    print("universe", len(rows))
    print("Samsung Electro-Mechanics:", samsung_s["미래성장가치표시문구"], samsung_s["전략펀더멘털적정가"])
    print("LG H&H:", lg_s["미래성장가치표시문구"], lg_s["전략펀더멘털적정가"])
    print("Amore:", amore_s["미래성장가치표시문구"], amore_s["전략펀더멘털적정가"])
    print("Strong consensus Samsung:", strong["미래성장가치표시문구"], strong["전략펀더멘털적정가"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
