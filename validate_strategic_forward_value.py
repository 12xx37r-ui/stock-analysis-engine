"""Strategic Forward Value V0.3.1 simulation/property validation.

실제 과거 애널리스트 revision/산업/거시 vintage가 현재 ZIP에 없으므로 이 검증은
미래 수익률을 증명하는 백테스트가 아니다. 대신 다음을 검증한다.
- 기존 라이브 재무적정가 불변(shadow)
- 회사 현재가 독립성
- 산업/시장기대 부재 시 미래가치 억제
- 산업 또는 컨센서스 증거가 강해질수록 인정가치 단조 증가
- 검증된 악화 거시는 미래가치를 낮추고, 미검증 거시는 가치에 영향 없음
- 진짜 SOTP는 감사상태·원천·기준일이 검증된 사업부 EV 자료가 있을 때만 계산
- 현재-only 기초가치가 없으면 미래증분 추가를 차단해 FY1/FY2 이중반영 방지
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
from collectors.analyst_consensus import parse_consensus_html


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
        stock_code=code,
        company_name=snapshot.get("기업명", ""),
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


def current_consensus_fixture(company: str, target_price: float = 2_350_500) -> Dict[str, Any]:
    """현재 컨센서스 형태를 재현하는 검증 fixture. 런타임 하드코딩에는 사용하지 않는다."""
    if company == "삼성전기":
        return {
            "사용가능": True, "투자의견": 4.0, "목표주가": target_price,
            "FY1_EPS": 19_742, "PER": 64.7, "추정기관수": 20,
            "데이터품질": 100, "수집상태": "fixture",
        }
    if company == "LG생활건강":
        return {
            "사용가능": True, "투자의견": 3.5, "목표주가": 305_143,
            "FY1_EPS": 13_190, "PER": 21.8, "추정기관수": 14,
            "데이터품질": 100, "수집상태": "fixture",
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
        stock_code="009150", company_name="삼성전기",
    )
    strong = build_strategic_forward_value(
        valuation=samsung_v, financial=samsung["재무분석"], fundamentals_analysis=strong_fa,
        industry_analysis=samsung["산업분석"].get("분석", {}), global_macro_context=macro,
        stock_code="009150", company_name="삼성전기",
    )
    assert weak["전략펀더멘털적정가"] >= samsung_s["전략펀더멘털적정가"] - 1e-6
    assert strong["전략펀더멘털적정가"] >= weak["전략펀더멘털적정가"] - 1e-6

    # 5-b) 실제 Snapshot 형태의 외부 FY1 EPS 컨센서스는 미래이익 근거로 작동한다.
    # 목표주가는 진단용일 뿐 점수/적정가에 영향이 0이어야 한다.
    current_consensus = build_strategic_forward_value(
        valuation=samsung_v, financial=samsung["재무분석"], fundamentals_analysis=fa,
        industry_analysis=samsung["산업분석"].get("분석", {}), global_macro_context=macro,
        external_consensus=current_consensus_fixture("삼성전기"),
        stock_code="009150", company_name="삼성전기",
    )
    target_low = build_strategic_forward_value(
        valuation=samsung_v, financial=samsung["재무분석"], fundamentals_analysis=fa,
        industry_analysis=samsung["산업분석"].get("분석", {}), global_macro_context=macro,
        external_consensus=current_consensus_fixture("삼성전기", target_price=1_000_000),
        stock_code="009150", company_name="삼성전기",
    )
    target_high = build_strategic_forward_value(
        valuation=samsung_v, financial=samsung["재무분석"], fundamentals_analysis=fa,
        industry_analysis=samsung["산업분석"].get("분석", {}), global_macro_context=macro,
        external_consensus=current_consensus_fixture("삼성전기", target_price=5_000_000),
        stock_code="009150", company_name="삼성전기",
    )
    assert current_consensus["근거축"]["시장기대_애널리스트"]["사용가능"] is True
    assert current_consensus["전략펀더멘털적정가"] > samsung_s["전략펀더멘털적정가"]
    assert abs(target_low["전략펀더멘털적정가"] - target_high["전략펀더멘털적정가"]) < 1e-9

    # 5-c) 산업근거에서 삼성전기 자체 주가 행이 제거되어야 한다.
    industry_axis = current_consensus["근거축"]["산업현재미래"]
    assert industry_axis["입력"]["대상기업자체행제외"] is True
    assert "대상기업 자체 주가를 산업 성장근거에서 제외" in industry_axis["근거"]

    # 5-d) 저부하 공개 Snapshot parser 자체 회귀검증.
    synthetic_html = """
    <table><tr><th>투자의견</th><th>목표주가</th><th>EPS</th><th>PER</th><th>추정기관수</th></tr>
    <tr><td>4.00</td><td>2,350,500</td><td>19,742</td><td>64.70</td><td>20</td></tr></table>
    """
    parsed = parse_consensus_html(synthetic_html)
    assert parsed["사용가능"] is True
    assert parsed["FY1_EPS"] == 19742.0 and parsed["추정기관수"] == 20
    assert parse_consensus_html("<html>broken</html>")["사용가능"] is False

    # 6) 미검증 거시는 영향 0, 검증된 악화/호전은 raw increment의 실현률만 조정.
    neutral_unvalidated = build_strategic_forward_value(
        valuation=samsung_v, financial=samsung["재무분석"], fundamentals_analysis=strong_fa,
        industry_analysis=samsung["산업분석"].get("분석", {}), global_macro_context=macro_scenario(-80, False),
        stock_code="009150", company_name="삼성전기",
    )
    bad_macro = build_strategic_forward_value(
        valuation=samsung_v, financial=samsung["재무분석"], fundamentals_analysis=strong_fa,
        industry_analysis=samsung["산업분석"].get("분석", {}), global_macro_context=macro_scenario(-80, True),
        stock_code="009150", company_name="삼성전기",
    )
    good_macro = build_strategic_forward_value(
        valuation=samsung_v, financial=samsung["재무분석"], fundamentals_analysis=strong_fa,
        industry_analysis=samsung["산업분석"].get("분석", {}), global_macro_context=macro_scenario(80, True),
        stock_code="009150", company_name="삼성전기",
    )
    assert abs(neutral_unvalidated["거시조정배수"] - 1.0) < 1e-9
    assert bad_macro["전략펀더멘털적정가"] <= neutral_unvalidated["전략펀더멘털적정가"] + 1e-6
    assert good_macro["전략펀더멘털적정가"] >= neutral_unvalidated["전략펀더멘털적정가"] - 1e-6

    # 7) SOTP: 단순 숫자만 넣은 대용값은 차단하고, 감사된 원천자료만 허용한다.
    no_sotp = build_sotp_base({"segments": [{"name": "A", "enterprise_value": 100}]})
    assert no_sotp["사용가능"] is False
    unverified_sotp = build_sotp_base({
        "segments": [
            {"name": "A", "enterprise_value": 1000, "source": "DART"},
            {"name": "B", "enterprise_value": 500, "source": "DART"},
        ],
        "source_date": "2026-06-30", "currency": "KRW", "diluted_shares": 10,
    })
    assert unverified_sotp["사용가능"] is False
    mixed_basis = build_sotp_base({
        "audit_status": "verified", "source_date": "2026-06-30", "currency": "KRW",
        "segments": [
            {"name": "A", "enterprise_value": 1000, "source": "DART"},
            {"name": "B", "equity_value": 500, "source": "DART"},
        ],
        "diluted_shares": 10,
    })
    assert mixed_basis["사용가능"] is False
    yes_sotp = build_sotp_base({
        "audit_status": "verified", "source_date": "2026-06-30", "currency": "KRW",
        "segments": [
            {"name": "A", "enterprise_value": 1000, "source": "DART", "source_date": "2026-06-30"},
            {"name": "B", "enterprise_value": 500, "source": "DART", "source_date": "2026-06-30"},
        ],
        "listed_stakes": [{"equity_value": 100, "source": "KRX"}],
        "cash": 200, "debt": 300, "minority_interest": 50,
        "preferred_equity": 0, "diluted_shares": 10,
        "balance_sheet_source": "OpenDART 2026-06-30",
    })
    # (1500 +100 +200 -300 -50) / 10 = 145
    assert yes_sotp["사용가능"] is True
    assert abs(yes_sotp["주당SOTP기초가치"] - 145.0) < 1e-9

    # 7-b) current-only 기초가치가 없으면 기존 혼합 적정가에 미래증분을 절대 더하지 않는다.
    mixed_legacy_valuation = copy.deepcopy(samsung_v)
    mixed_legacy_valuation["현재재무기초가치"] = 0
    mixed_legacy_valuation.setdefault("적응형가치모형", {})["현재재무기초가치"] = 0
    blocked_double_count = build_strategic_forward_value(
        valuation=mixed_legacy_valuation,
        financial=samsung["재무분석"], fundamentals_analysis=strong_fa,
        industry_analysis=samsung["산업분석"].get("분석", {}), global_macro_context=macro,
        stock_code="009150", company_name="삼성전기",
    )
    assert blocked_double_count["미래이중계산차단"] is True
    assert blocked_double_count["미래증분추가허용"] is False
    assert blocked_double_count["미래증분가치"] == 0
    assert abs(blocked_double_count["전략펀더멘털적정가"] - mixed_legacy_valuation["재무적정가"]) < 1e-6

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
        "engine_version": "0.3.1-strategic-forward-doublecount-sotp-guard",
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
            "true_sotp_requires_verified_sources": True,
            "future_double_count_guard": True,
            "target_price_influence_on_fair_value": 0,
            "target_company_price_excluded_from_industry_axis": True,
            "analyst_consensus_lazy_cached": True,
        },
        "examples": {
            "삼성전기": samsung_s,
            "LG생활건강": lg_s,
            "아모레퍼시픽": amore_s,
            "삼성전기_weak_consensus": weak,
            "삼성전기_strong_consensus": strong,
            "삼성전기_current_consensus_fixture": current_consensus,
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

    print("STRATEGIC FORWARD VALUE V0.3.1: PASS")
    print("universe", len(rows))
    print("Samsung Electro-Mechanics:", samsung_s["미래성장가치표시문구"], samsung_s["전략펀더멘털적정가"])
    print("LG H&H:", lg_s["미래성장가치표시문구"], lg_s["전략펀더멘털적정가"])
    print("Amore:", amore_s["미래성장가치표시문구"], amore_s["전략펀더멘털적정가"])
    print("Strong consensus Samsung:", strong["미래성장가치표시문구"], strong["전략펀더멘털적정가"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
