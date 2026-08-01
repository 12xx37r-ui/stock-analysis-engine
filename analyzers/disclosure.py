"""
OpenDART 공시 이벤트 신호 분석기 V1

입력
- collectors.disclosure.get_recent_disclosures() 결과

출력
- 뉴스·공시 요소에 사용할 -100~100 신호
- 데이터 품질
- 긍정·부정 이벤트 목록

주의
- 보고서 제목 기반 규칙형 신호다.
- 공시 원문 정량분석 연결 전까지 데이터 품질을 최대 70으로 제한한다.
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Tuple


KST = timezone(timedelta(hours=9))


POSITIVE_RULES: Tuple[Tuple[str, int], ...] = (
    ("단일판매ㆍ공급계약체결", 35),
    ("단일판매·공급계약체결", 35),
    ("공급계약체결", 30),
    ("영업(잠정)실적", 18),
    ("영업실적", 18),
    ("매출액또는손익구조", 15),
    ("시설투자", 18),
    ("신규시설투자", 20),
    ("타법인주식및출자증권취득결정", 10),
    ("자기주식취득결정", 25),
    ("자기주식소각결정", 30),
    ("현금ㆍ현물배당결정", 18),
    ("현금·현물배당결정", 18),
    ("무상증자결정", 12),
    ("특허권취득", 10),
    ("품목허가", 15),
    ("임상시험", 8),
)

NEGATIVE_RULES: Tuple[Tuple[str, int], ...] = (
    ("유상증자결정", -25),
    ("전환사채권발행결정", -18),
    ("신주인수권부사채권발행결정", -18),
    ("교환사채권발행결정", -15),
    ("감자결정", -30),
    ("영업정지", -35),
    ("회생절차", -50),
    ("파산신청", -60),
    ("부도발생", -60),
    ("횡령ㆍ배임", -55),
    ("횡령·배임", -55),
    ("소송등의제기", -18),
    ("상장폐지", -70),
    ("거래정지", -45),
    ("불성실공시", -25),
    ("감사의견", -30),
    ("최대주주변경", -12),
    ("담보제공", -10),
    ("채무보증", -10),
    ("유형자산양도결정", -8),
)

CORRECTION_WORDS = (
    "기재정정",
    "첨부정정",
    "정정신고",
)


def safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def safe_date(value: Any):
    text = safe_text(value)

    try:
        return datetime.strptime(
            text,
            "%Y%m%d",
        ).date()
    except ValueError:
        return None


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def recency_weight(disclosure_date) -> float:
    if disclosure_date is None:
        return 0.50

    today = datetime.now(KST).date()
    age = max((today - disclosure_date).days, 0)

    if age <= 2:
        return 1.00
    if age <= 7:
        return 0.85
    if age <= 14:
        return 0.65
    if age <= 30:
        return 0.45
    if age <= 60:
        return 0.25

    return 0.15


def score_report_title(
    report_name: str,
) -> Tuple[float, List[str]]:
    report_name = safe_text(report_name)
    score = 0.0
    matched: List[str] = []

    for keyword, weight in POSITIVE_RULES:
        if keyword in report_name:
            score += weight
            matched.append(keyword)

    for keyword, weight in NEGATIVE_RULES:
        if keyword in report_name:
            score += weight
            matched.append(keyword)

    if any(
        word in report_name
        for word in CORRECTION_WORDS
    ):
        score *= 0.60
        matched.append("정정공시 감점")

    return (
        clamp(score, -100.0, 100.0),
        matched,
    )


def analyze_disclosures(
    disclosure_bundle: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(disclosure_bundle, dict):
        return {
            "분석상태": "실패",
            "신호": 0.0,
            "데이터품질": 0,
            "판정": "중립",
            "이벤트개수": 0,
            "긍정이벤트": [],
            "부정이벤트": [],
            "중립이벤트": [],
            "설명": "공시 수집 결과 형식이 올바르지 않습니다.",
        }

    collection_status = safe_text(
        disclosure_bundle.get("수집상태")
    )
    disclosures = disclosure_bundle.get(
        "공시목록",
        [],
    )

    if not isinstance(disclosures, list):
        disclosures = []

    analyzed = []

    for item in disclosures:
        if not isinstance(item, dict):
            continue

        report_name = safe_text(
            item.get("보고서명")
        )

        raw_score, matched = score_report_title(
            report_name
        )

        weight = recency_weight(
            safe_date(
                item.get("공시일")
            )
        )

        weighted_score = raw_score * weight

        analyzed.append(
            {
                "공시일": safe_text(
                    item.get("공시일")
                ),
                "보고서명": report_name,
                "접수번호": safe_text(
                    item.get("접수번호")
                ),
                "원점수": round(raw_score, 2),
                "최종점수": round(
                    weighted_score,
                    2,
                ),
                "일자가중치": round(
                    weight,
                    2,
                ),
                "매칭규칙": matched,
            }
        )

    scored_events = [
        item
        for item in analyzed
        if item["원점수"] != 0
    ]

    if scored_events:
        total = sum(
            item["최종점수"]
            for item in scored_events
        )

        signal = clamp(
            total / max(len(scored_events) ** 0.5, 1.0),
            -100.0,
            100.0,
        )
    else:
        signal = 0.0

    if signal >= 20:
        judgment = "긍정"
    elif signal <= -20:
        judgment = "부정"
    else:
        judgment = "중립"

    positive = sorted(
        [
            item
            for item in analyzed
            if item["최종점수"] > 0
        ],
        key=lambda item: item["최종점수"],
        reverse=True,
    )

    negative = sorted(
        [
            item
            for item in analyzed
            if item["최종점수"] < 0
        ],
        key=lambda item: item["최종점수"],
    )

    neutral = [
        item
        for item in analyzed
        if item["최종점수"] == 0
    ]

    if collection_status != "정상":
        quality = 0
    elif len(disclosures) == 0:
        quality = 35
    elif scored_events:
        quality = min(
            70,
            45 + len(scored_events) * 5,
        )
    else:
        quality = 45

    return {
        "분석상태": (
            "정상"
            if collection_status == "정상"
            else "실패"
        ),
        "신호": round(signal, 2),
        "데이터품질": quality,
        "판정": judgment,
        "전체공시개수": len(disclosures),
        "이벤트개수": len(scored_events),
        "긍정이벤트": positive[:10],
        "부정이벤트": negative[:10],
        "중립이벤트": neutral[:10],
        "설명": (
            "최근 공시 제목과 공시일을 기준으로 계산한 규칙형 신호입니다. "
            "공시 원문 정량분석 전 단계이므로 데이터품질 상한은 70입니다."
        ),
    }
