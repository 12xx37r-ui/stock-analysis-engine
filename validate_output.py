"""
엔진 출력 검증기 V1

사용:
    python validate_output.py
    python validate_output.py --file output/samsung.json

검증:
- 필수 JSON 구조
- 엔진 버전
- 단기·중기·장기 고정 가중치
- 요소 신호·데이터품질·점수기여
- 종합점수·상승확률 재계산
- 주요 데이터 수집상태
"""

import argparse
import json
import math
import sys
from pathlib import Path


EXPECTED_ENGINE_VERSION = "6.7.2-valuation-contract-v4"
EXPECTED_VALUATION_MODEL_REVISION = "future-growth-v1.0.1-insurance-financials"

EXPECTED_WEIGHTS = {
    "단기1~5일": {
        "파생시장·프로그램": 30,
        "외국인·기관수급": 25,
        "기술·거래량": 20,
        "환율·글로벌": 15,
        "뉴스·공시": 10,
    },
    "중기1~8주": {
        "분기실적": 25,
        "산업선행지표": 25,
        "누적수급": 15,
        "환율·금리·거시": 15,
        "가격추세": 10,
        "뉴스·공시": 10,
    },
    "장기6~18개월": {
        "향후이익방향": 30,
        "산업사이클": 25,
        "가치평가·안전마진": 20,
        "경쟁력·시장점유율": 10,
        "현금흐름·재무안전성": 10,
        "주주환원·지배구조": 5,
    },
}

REQUIRED_ROOT_KEYS = (
    "기업명",
    "DART기업코드",
    "KIS종목코드",
    "재무분석",
    "시장정보",
    "기술분석",
    "뉴스분석",
    "가치평가",
    "주가예측",
    "화면브리지",
)

CRITICAL_COMPLETENESS_KEYS = (
    "현재가",
    "가격이력",
    "멀티타임프레임차트",
    "누적수급",
    "프로그램매매",
    "DART기본재무",
    "DART분기실적",
    "DART현금흐름",
    "DART주주환원",
    "DART최근공시",
    "기업뉴스",
    "글로벌시장",
    "산업선행지표",
    "산업사이클",
    "가치평가",
)


def safe_float(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def safe_dict(value):
    return value if isinstance(value, dict) else {}


def safe_list(value):
    return value if isinstance(value, list) else []


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def nearly_equal(left, right, tolerance=0.02):
    return abs(left - right) <= tolerance


def expected_score(factors):
    contribution = sum(
        safe_float(item.get("점수기여"))
        for item in factors
    )
    return int(round(clamp(50.0 + contribution / 2.0, 15.0, 85.0)))


def expected_probability(score, confidence):
    probability = (
        50.0
        + (score - 50.0)
        * (confidence / 100.0)
        * 0.80
    )
    return int(round(clamp(probability, 20.0, 80.0)))


class Result:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.summary = []

    def error(self, message):
        self.errors.append(message)

    def warning(self, message):
        self.warnings.append(message)

    def info(self, message):
        self.summary.append(message)


def validate_range(
    value,
    minimum,
    maximum,
    name,
    result,
):
    numeric = safe_float(value, float("nan"))

    if math.isnan(numeric):
        result.error(f"{name}: 숫자가 아님")
        return 0.0

    if not minimum <= numeric <= maximum:
        result.error(
            f"{name}: {numeric} "
            f"(허용범위 {minimum}~{maximum})"
        )

    return numeric


def validate_horizon(
    name,
    prediction,
    result,
):
    expected_weights = EXPECTED_WEIGHTS[name]
    factors = [
        safe_dict(item)
        for item in safe_list(
            prediction.get("요소별평가")
        )
    ]

    if not factors:
        result.error(f"{name}: 요소별평가 없음")
        return

    factor_map = {
        str(item.get("요소", "")): item
        for item in factors
    }

    for factor_name, expected_weight in expected_weights.items():
        factor = factor_map.get(factor_name)

        if factor is None:
            result.error(
                f"{name}: 요소 누락 - {factor_name}"
            )
            continue

        weight = safe_float(factor.get("가중치"))

        if not nearly_equal(weight, expected_weight):
            result.error(
                f"{name}/{factor_name}: "
                f"가중치 {weight}, 기대값 {expected_weight}"
            )

        signal = validate_range(
            factor.get("신호"),
            -100.0,
            100.0,
            f"{name}/{factor_name}/신호",
            result,
        )

        quality = validate_range(
            factor.get("데이터품질"),
            0.0,
            100.0,
            f"{name}/{factor_name}/데이터품질",
            result,
        )

        contribution = safe_float(
            factor.get("점수기여")
        )
        recalculated = expected_weight * signal / 100.0

        if not nearly_equal(
            contribution,
            recalculated,
        ):
            result.error(
                f"{name}/{factor_name}: "
                f"점수기여 {contribution}, "
                f"재계산 {recalculated:.2f}"
            )

        if quality == 0:
            result.warning(
                f"{name}/{factor_name}: 데이터 미수집"
            )

        if factor_name == "파생시장·프로그램":
            source = str(factor.get("출처", ""))
            if "종목별 프로그램매매" not in source:
                result.error(
                    f"{name}/{factor_name}: "
                    f"종목별 프로그램매매 출처가 아님 - {source}"
                )

    weight_sum = sum(
        safe_float(item.get("가중치"))
        for item in factors
    )

    if not nearly_equal(weight_sum, 100.0):
        result.error(
            f"{name}: 가중치 합계 {weight_sum}"
        )

    score = validate_range(
        prediction.get("점수"),
        0.0,
        100.0,
        f"{name}/점수",
        result,
    )

    confidence = validate_range(
        prediction.get("신뢰도"),
        0.0,
        100.0,
        f"{name}/신뢰도",
        result,
    )

    probability = validate_range(
        prediction.get("상승확률"),
        20.0,
        80.0,
        f"{name}/상승확률",
        result,
    )

    recalculated_score = expected_score(factors)

    if not nearly_equal(
        score,
        recalculated_score,
        tolerance=0.01,
    ):
        result.error(
            f"{name}: 점수 {score}, "
            f"재계산 {recalculated_score}"
        )

    recalculated_probability = expected_probability(
        score,
        confidence,
    )

    if not nearly_equal(
        probability,
        recalculated_probability,
        tolerance=0.01,
    ):
        result.error(
            f"{name}: 상승확률 {probability}, "
            f"재계산 {recalculated_probability}"
        )

    result.info(
        f"{name}: 점수 {int(score)}, "
        f"상승확률 {int(probability)}%, "
        f"신뢰도 {int(confidence)}%, "
        f"판정 {prediction.get('판정', '')}"
    )



def validate_valuation_contract(data, result):
    valuation = safe_dict(data.get("가치평가"))
    if not valuation:
        result.error("가치평가 누락")
        return

    if str(valuation.get("가치평가계약버전", "")) != "4.0":
        result.error("가치평가 계약버전 4.0 누락")

    if str(valuation.get("가치평가엔진버전", "")) != EXPECTED_ENGINE_VERSION:
        result.error("가치평가 엔진버전 불일치")
    if str(valuation.get("가치평가모형개정버전", "")) != EXPECTED_VALUATION_MODEL_REVISION:
        result.error("가치평가 모형개정버전 불일치")

    qualification = safe_dict(valuation.get("데이터자격검사"))
    if not qualification:
        result.error("데이터자격검사 누락")
    elif valuation.get("최종값사용가능") is True and qualification.get("통과") is not True:
        result.error("최종값 사용가능인데 데이터자격검사는 미통과")
    elif valuation.get("최종값사용가능") is not True:
        if qualification.get("통과") is False and safe_list(qualification.get("중단사유")):
            result.warning(
                "가치평가 최종값 사용보류: "
                + str(qualification.get("중단사유"))
            )
        else:
            result.error("최종값 사용불가인데 명시적 데이터자격 중단사유 없음")

    base = safe_float(valuation.get("기본적정가"))
    conservative = safe_float(valuation.get("보수적적정가"))
    growth = safe_float(valuation.get("성장적정가"))
    evaluation_eps = safe_float(valuation.get("평가EPS"))
    target_per = safe_float(valuation.get("목표PER"))
    implied_per = safe_float(valuation.get("암시PER"))

    if not (base > 0 and conservative > 0 and growth > 0):
        result.error("가치평가 시나리오 값이 0 이하")
    elif not conservative <= base <= growth:
        result.error(
            f"가치평가 범위 순서 오류: {conservative} <= {base} <= {growth}"
        )

    if evaluation_eps <= 0:
        result.error("평가EPS가 0 이하")
    if target_per <= 0:
        result.error("목표PER이 0 이하")
    if base > 0 and evaluation_eps > 0:
        recalculated = base / evaluation_eps
        if not nearly_equal(implied_per, recalculated, tolerance=0.05):
            result.error(
                f"암시PER 불일치: 저장 {implied_per}, 재계산 {recalculated:.2f}"
            )

    current_price = safe_float(safe_dict(data.get("시장정보")).get("현재가"))
    stock_code = str(data.get("KIS종목코드", "")).zfill(6)
    if stock_code == "005930":
        if valuation.get("복합기업대용모형") is not True:
            result.error("삼성전자 복합기업 대용 가치합산 미적용")
        pbr_value = safe_float(valuation.get("PBR기준적정가"))
        if base > 0 and pbr_value > 0 and abs(base - pbr_value) / base < 0.08:
            result.error("삼성전자 최종가가 PBR 하단가치와 사실상 동일")
        if current_price > 0 and base / current_price < 0.50:
            result.error("삼성전자 적정가가 현재가의 50% 미만: 최신 TTM 연결 의심")

    future_model = safe_dict(valuation.get("미래성장모형"))
    if not future_model:
        result.error("미래성장모형 상태 누락")
    else:
        if future_model.get("사용가능") is True:
            if future_model.get("현재가미사용") is not True:
                result.error("미래성장모형 현재가 비사용 보증 누락")
            if safe_float(valuation.get("미래성장가치")) <= 0:
                result.error("미래성장모형 사용가능인데 가치가 0 이하")
            if safe_float(valuation.get("FY3예상EPS")) <= 0 or safe_float(valuation.get("FY4예상EPS")) <= 0:
                result.error("미래성장모형 사용가능인데 FY3·FY4 EPS 누락")
            if safe_float(future_model.get("가치")) > safe_float(future_model.get("가치상한"), float("inf")) + 0.05:
                result.error("미래성장가치가 자체 상한 초과")
        elif not safe_list(future_model.get("차단사유")):
            result.error("미래성장모형 미사용인데 차단사유 없음")

    result.info(
        "가치평가 계약: "
        f"상태 {valuation.get('산출상태', '')}, "
        f"기본 {base:,.0f}, 보수 {conservative:,.0f}, 성장 {growth:,.0f}, "
        f"평가EPS {evaluation_eps:,.2f}, 목표PER {target_per:.2f}"
    )

def validate_output(
    data,
    expected_stock_code="",
):
    result = Result()

    for key in REQUIRED_ROOT_KEYS:
        if key not in data:
            result.error(f"루트 필수 키 누락 - {key}")


    actual_stock_code = str(
        data.get(
            "KIS종목코드",
            "",
        )
    ).strip().zfill(6)

    normalized_expected = str(
        expected_stock_code
        or ""
    ).strip()

    if normalized_expected:
        normalized_expected = (
            normalized_expected.zfill(6)
        )

        if (
            actual_stock_code
            != normalized_expected
        ):
            result.error(
                "종목코드 불일치: "
                f"JSON {actual_stock_code}, "
                f"요청 {normalized_expected}"
            )

    result.info(
        f"분석종목: "
        f"{data.get('기업명', '')} "
        f"({actual_stock_code})"
    )

    market = safe_dict(data.get("시장정보"))
    current_price = safe_float(market.get("현재가"))
    volume = safe_float(market.get("거래량"))

    if current_price <= 0:
        result.error("시장정보/현재가가 0 이하")

    if volume <= 0:
        result.error("시장정보/거래량이 0 이하")

    history = safe_dict(
        market.get("과거데이터")
    )
    history_status = str(
        safe_dict(
            history.get("수집상태")
        ).get("전체수집상태", "")
    )

    if history_status != "정상":
        result.warning(
            f"시장 과거데이터 상태: {history_status or '누락'}"
        )

    result.info(
        f"시장: 현재가 {current_price:,.0f}, "
        f"거래량 {volume:,.0f}, "
        f"과거데이터 {history_status or '미확인'}"
    )

    validate_valuation_contract(data, result)

    program = safe_dict(history.get("프로그램매매"))
    detail_status = safe_dict(history.get("수집상태"))
    program_count = int(safe_float(detail_status.get("프로그램데이터개수")))
    quantity_5 = safe_float(program.get("프로그램순매수수량5일"))
    quantity_20 = safe_float(program.get("프로그램순매수수량20일"))

    if program_count > 0:
        for field_name, value in (
            ("프로그램순매수수량5일", quantity_5),
            ("프로그램순매수수량20일", quantity_20),
        ):
            if not nearly_equal(value, round(value), tolerance=0.01):
                result.error(
                    f"시장정보/과거데이터/{field_name}: "
                    f"수량이 정수가 아님 - {value}"
                )

    result.info(
        "종목별 프로그램매매: "
        f"5일 {quantity_5:,.0f}주, "
        f"20일 {quantity_20:,.0f}주, "
        f"데이터 {program_count}건"
    )

    section_statuses = {
        "글로벌시장": safe_dict(
            data.get("글로벌시장")
        ).get("전체수집상태", ""),
        "기업기초데이터": safe_dict(
            data.get("기업기초데이터")
        ).get("전체수집상태", ""),
        "산업분석": safe_dict(
            data.get("산업분석")
        ).get("전체수집상태", ""),
        "공시정보": safe_dict(
            data.get("공시정보")
        ).get("수집상태", ""),
    }

    for section, status in section_statuses.items():
        allowed = {"정상"}

        if section == "기업기초데이터":
            allowed.add("부분성공")

        if status not in allowed:
            result.warning(
                f"{section} 상태: {status or '누락'}"
            )

    result.info(
        "외부데이터: "
        + ", ".join(
            f"{name} {status or '미확인'}"
            for name, status in section_statuses.items()
        )
    )

    prediction_root = safe_dict(
        data.get("주가예측")
    )

    version = str(
        prediction_root.get("엔진버전", "")
    )

    if version != EXPECTED_ENGINE_VERSION:
        result.error(
            f"엔진버전 {version or '누락'}, "
            f"기대값 {EXPECTED_ENGINE_VERSION}"
        )
    else:
        result.info(f"엔진버전: {version}")

    for horizon_name in EXPECTED_WEIGHTS:
        horizon = safe_dict(
            prediction_root.get(horizon_name)
        )

        if not horizon:
            result.error(
                f"주가예측/{horizon_name} 누락"
            )
            continue

        validate_horizon(
            horizon_name,
            horizon,
            result,
        )

    completeness = safe_dict(
        prediction_root.get("데이터완전성")
    )

    if not completeness:
        result.error("데이터완전성 누락")
    else:
        for key in CRITICAL_COMPLETENESS_KEYS:
            if key not in completeness:
                result.warning(
                    f"데이터완전성 키 누락 - {key}"
                )
            elif completeness[key] is not True:
                result.warning(
                    f"데이터완전성 False - {key}"
                )

        true_count = sum(
            value is True
            for value in completeness.values()
        )

        result.info(
            f"데이터완전성: "
            f"{true_count}/{len(completeness)}개 True"
        )

    return result


def print_items(title, items):
    if not items:
        return

    print()
    print(title)

    for item in items:
        print("-", item)


def main():
    parser = argparse.ArgumentParser(
        description="엔진 출력 JSON 검증"
    )

    parser.add_argument(
        "--file",
        default="",
        help=(
            "검증할 JSON 파일. "
            "생략하면 output/<stock-code>.json"
        ),
    )

    parser.add_argument(
        "--stock-code",
        default="005930",
        help=(
            "요청한 6자리 종목코드"
        ),
    )

    args = parser.parse_args()

    stock_code = str(
        args.stock_code
        or "005930"
    ).strip().zfill(6)

    file_name = (
        args.file
        or f"output/{stock_code}.json"
    )

    path = Path(
        file_name
    )

    if not path.exists():
        print("ENGINE OUTPUT VALIDATION")
        print("RESULT: FAIL")
        print("- 파일 없음:", path)
        return 1

    try:
        data = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except Exception as error:
        print("ENGINE OUTPUT VALIDATION")
        print("RESULT: FAIL")
        print(
            "- JSON 읽기 실패:",
            type(error).__name__,
            error,
        )
        return 1

    if not isinstance(data, dict):
        print("ENGINE OUTPUT VALIDATION")
        print("RESULT: FAIL")
        print("- JSON 루트가 객체가 아님")
        return 1

    result = validate_output(
        data,
        expected_stock_code=stock_code,
    )

    print("ENGINE OUTPUT VALIDATION")
    print(
        "RESULT:",
        "PASS"
        if not result.errors
        else "FAIL",
    )

    print_items(
        "SUMMARY",
        result.summary,
    )
    print_items(
        "WARNINGS",
        result.warnings,
    )
    print_items(
        "ERRORS",
        result.errors,
    )

    print()
    print(
        "COUNTS:",
        f"errors={len(result.errors)}",
        f"warnings={len(result.warnings)}",
    )

    return (
        0
        if not result.errors
        else 1
    )


if __name__ == "__main__":
    sys.exit(
        main()
    )
