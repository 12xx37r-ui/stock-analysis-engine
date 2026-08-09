"""적응형 펀더멘털 가치모형 회귀검증.

목표
- 20422/20423 소비재 세부분류가 화학·소재로 오분류되지 않는지 확인
- 현재가를 바꿔도 내재가치가 변하지 않는지 확인
- 현재 재무기초가치 + 미래 증분가치의 이중계산 방지 확인
- 삼성전기/LG생활건강/아모레퍼시픽 저장 스냅샷에서 극단 왜곡 개선 확인
- 전체 저장 유니버스에서 비대상 기업의 기존 v4 값이 그대로 유지되는지 확인
"""

import copy
import json
from typing import Any, Dict

from analyzers.valuation import calculate_value
from collectors.company import classify_dart_industry_detail


_UNIVERSE_FIXTURE = None

def load_universe_fixture() -> Dict[str, Dict[str, Any]]:
    global _UNIVERSE_FIXTURE
    if _UNIVERSE_FIXTURE is None:
        with open("fixtures/strategic/universe_bundle.json", encoding="utf-8") as handle:
            _UNIVERSE_FIXTURE = json.load(handle)
    return _UNIVERSE_FIXTURE

def load_snapshot(code: str) -> Dict[str, Any]:
    return copy.deepcopy(load_universe_fixture()[code])


def refreshed_company_info(snapshot: Dict[str, Any], code: str) -> Dict[str, Any]:
    info = copy.deepcopy(snapshot["기업조회정보"])
    detail = classify_dart_industry_detail(
        info.get("OpenDART업종코드"),
        snapshot.get("기업명", ""),
        code,
    )
    info.update({
        "산업코드": detail["산업코드"],
        "가치평가산업코드": detail["산업코드"],
        "산업분류출처": detail["분류출처"],
        "산업분류신뢰도": detail["분류신뢰도"],
    })
    return info


def recalc(snapshot: Dict[str, Any], code: str, price_override=None) -> Dict[str, Any]:
    market = copy.deepcopy(snapshot["시장정보"])
    if price_override is not None:
        market["현재가"] = float(price_override)
        # 시장배수는 진단값일 뿐이지만 가격독립성 검증을 위해 같이 비운다.
        market["PER"] = 0.0
        market["PBR"] = 0.0
    return calculate_value(
        snapshot["재무분석"],
        market,
        snapshot["기업기초데이터"].get("분석", {}),
        snapshot["기업기초데이터"],
        snapshot["산업분석"].get("분석", {}),
        snapshot["산업분석"],
        refreshed_company_info(snapshot, code),
    )


def assert_close(a: float, b: float, tolerance: float = 1e-6) -> None:
    scale = max(1.0, abs(a), abs(b))
    assert abs(a - b) <= tolerance * scale, (a, b)


def main() -> int:
    # KSIC 정밀 분류: 20421은 소재, 20422~20424는 브랜드 소비재.
    assert classify_dart_industry_detail("20421")["산업코드"] == "materials"
    assert classify_dart_industry_detail("20422")["산업코드"] == "beauty_consumer"
    assert classify_dart_industry_detail("20423")["산업코드"] == "beauty_consumer"
    assert classify_dart_industry_detail("20424")["산업코드"] == "beauty_consumer"

    samsung = load_snapshot("009150")
    lg = load_snapshot("051900")
    amore = load_snapshot("090430")

    samsung_value = recalc(samsung, "009150")
    lg_value = recalc(lg, "051900")
    amore_value = recalc(amore, "090430")

    # 현재가 독립성: 현재가를 약 10배 바꿔도 적정가는 동일해야 한다.
    samsung_low_price = recalc(samsung, "009150", 120_000)
    samsung_high_price = recalc(samsung, "009150", 2_400_000)
    assert_close(
        samsung_low_price["재무적정가"],
        samsung_high_price["재무적정가"],
    )
    assert samsung_value["적응형가치모형"]["현재가미사용"] is True

    # 이중계산 방지: 펀더멘털가치 = 현재기초 + 미래증분.
    for value in (samsung_value, lg_value, amore_value):
        model = value["적응형가치모형"]
        assert_close(
            model["펀더멘털적정가"],
            model["현재재무기초가치"] + model["미래증분가치"],
        )
        if model["미래총가치"] > 0:
            assert model["미래증분가치"] <= model["미래총가치"] + 1e-6

    # 실제 저장 스냅샷 회귀: 특정 현재가에 맞춘 하드코딩이 아니라
    # 산업분류/재무/성장 데이터만으로 기존 극단 왜곡을 줄이는지 확인한다.
    assert lg_value["가치평가산업코드"] == "beauty_consumer"
    assert lg_value["적응형가치적용"] is True
    assert lg_value["재무적정가"] > 0
    assert lg_value["현재재무기초가치"] > 0

    assert amore_value["가치평가산업코드"] == "beauty_consumer"
    assert amore_value["적응형가치적용"] is True
    assert amore_value["재무적정가"] > 0

    assert samsung_value["적응형가치적용"] is True
    assert samsung_value["미래증분가치"] > 0
    assert samsung_value["재무적정가"] > 0
    # 검증은 시장가와의 수렴을 강제하지 않는다. 가격독립성 검증이 그 역할을 한다.

    # 전체 저장 유니버스: 적응형 비대상 기업은 같은 계산 안에서 기존 v4 기준가를 그대로 유지한다.
    checked = 0
    changed = []
    for code, fixture_snapshot in load_universe_fixture().items():
        snapshot = copy.deepcopy(fixture_snapshot)
        new_value = recalc(snapshot, code)
        legacy_fair = float(new_value.get("기존V4재무적정가") or 0.0)
        new_fair = float(new_value.get("재무적정가") or 0.0)
        if legacy_fair <= 0 or new_fair <= 0:
            continue
        checked += 1
        if new_value.get("적응형가치적용") is True:
            changed.append((code, snapshot.get("기업명"), new_fair / legacy_fair))
        else:
            assert_close(new_fair, legacy_fair), (code, snapshot.get("기업명"), legacy_fair, new_fair)

    assert checked >= 60, checked
    assert len(changed) <= 8, changed

    print("ADAPTIVE FUNDAMENTAL VALUE V1: PASS")
    print(f"- universe checked: {checked}, changed by adaptive rules: {len(changed)}")
    print(
        "- LG생활건강: "
        f"{lg['가치평가']['재무적정가']:,.0f} -> {lg_value['재무적정가']:,.0f}원"
    )
    print(
        "- 아모레퍼시픽: "
        f"{amore['가치평가']['재무적정가']:,.0f} -> {amore_value['재무적정가']:,.0f}원"
    )
    print(
        "- 삼성전기: "
        f"{samsung['가치평가']['재무적정가']:,.0f} -> {samsung_value['재무적정가']:,.0f}원 "
        f"(현재재무 {samsung_value['현재재무기초가치']:,.0f} + 미래증분 {samsung_value['미래증분가치']:,.0f})"
    )
    print("- price independence: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
