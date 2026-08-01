def safe_float(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return default


def clamp(value, minimum=0, maximum=100):
    return max(minimum, min(maximum, round(value)))


def score_label(score):
    if score >= 75:
        return "강한 상승 우위"
    if score >= 60:
        return "상승 우위"
    if score >= 45:
        return "중립"
    if score >= 30:
        return "하락 우위"
    return "강한 하락 우위"


def add_reason(reasons, text):
    if text and text not in reasons:
        reasons.append(text)


def calculate_short_term(market):
    score = 50
    reasons = []

    supply = market.get("수급", {}) or {}

    foreign_net = safe_float(
        supply.get("외국인순매수")
    )
    institution_net = safe_float(
        supply.get("기관순매수")
    )
    individual_net = safe_float(
        supply.get("개인순매수")
    )

    combined_smart_money = (
        foreign_net
        + institution_net
    )

    if (
        foreign_net > 0
        and institution_net > 0
    ):
        score += 25
        add_reason(
            reasons,
            "외국인과 기관이 동시에 순매수"
        )

    elif combined_smart_money > 0:
        score += 15
        add_reason(
            reasons,
            "외국인·기관 합산 순매수"
        )

    elif (
        foreign_net < 0
        and institution_net < 0
    ):
        score -= 25
        add_reason(
            reasons,
            "외국인과 기관이 동시에 순매도"
        )

    elif combined_smart_money < 0:
        score -= 15
        add_reason(
            reasons,
            "외국인·기관 합산 순매도"
        )

    if (
        combined_smart_money > 0
        and individual_net < 0
    ):
        score += 5
        add_reason(
            reasons,
            "개인 매도 물량을 외국인·기관이 흡수"
        )

    elif (
        combined_smart_money < 0
        and individual_net > 0
    ):
        score -= 5
        add_reason(
            reasons,
            "외국인·기관 매도 물량을 개인이 흡수"
        )

    change_rate = safe_float(
        market.get("등락률")
    )

    if change_rate >= 5:
        score += 12
        add_reason(
            reasons,
            "강한 단기 가격 모멘텀"
        )

    elif change_rate >= 1:
        score += 7
        add_reason(
            reasons,
            "단기 가격 흐름 상승"
        )

    elif change_rate <= -5:
        score -= 12
        add_reason(
            reasons,
            "강한 단기 하락 모멘텀"
        )

    elif change_rate <= -1:
        score -= 7
        add_reason(
            reasons,
            "단기 가격 흐름 하락"
        )

    current_price = safe_float(
        market.get("현재가")
    )
    open_price = safe_float(
        market.get("시가")
    )
    high_price = safe_float(
        market.get("고가")
    )
    low_price = safe_float(
        market.get("저가")
    )
    volume = safe_float(
        market.get("거래량")
    )

    if (
        current_price > 0
        and open_price > 0
    ):
        if current_price > open_price:
            score += 4
            add_reason(
                reasons,
                "현재가가 시가보다 높음"
            )

        elif current_price < open_price:
            score -= 4
            add_reason(
                reasons,
                "현재가가 시가보다 낮음"
            )

    if (
        current_price > 0
        and high_price > low_price > 0
    ):
        range_position = (
            current_price - low_price
        ) / (
            high_price - low_price
        )

        if range_position >= 0.75:
            score += 4
            add_reason(
                reasons,
                "당일 가격이 고가권에 위치"
            )

        elif range_position <= 0.25:
            score -= 4
            add_reason(
                reasons,
                "당일 가격이 저가권에 위치"
            )

    if volume > 0:
        add_reason(
            reasons,
            "거래량 데이터 정상 반영"
        )

    final_score = clamp(score)

    return {
        "기간": "1~5일",
        "점수": final_score,
        "상승확률": final_score,
        "판정": score_label(
            final_score
        ),
        "수급점검": {
            "외국인순매수": foreign_net,
            "기관순매수": institution_net,
            "개인순매수": individual_net,
            "외국인기관합산": combined_smart_money,
        },
        "근거": reasons,
    }


def calculate_mid_term(
    market,
    financial,
):
    score = 50
    reasons = []

    indicators = (
        financial.get(
            "재무지표",
            {},
        )
        or {}
    )

    growth = (
        financial.get(
            "성장지표",
            {},
        )
        or {}
    )

    revenue_growth = safe_float(
        growth.get(
            "매출3년성장률"
        )
    )
    operating_growth = safe_float(
        growth.get(
            "영업이익3년성장률"
        )
    )
    net_income_growth = safe_float(
        growth.get(
            "순이익3년성장률"
        )
    )

    roe = safe_float(
        indicators.get("ROE")
    )
    operating_margin = safe_float(
        indicators.get(
            "영업이익률"
        )
    )

    if revenue_growth >= 20:
        score += 10
        add_reason(
            reasons,
            "매출 성장세가 강함"
        )

    elif revenue_growth >= 5:
        score += 5
        add_reason(
            reasons,
            "매출 성장세가 양호"
        )

    elif revenue_growth < 0:
        score -= 10
        add_reason(
            reasons,
            "매출이 감소"
        )

    if operating_growth >= 30:
        score += 12
        add_reason(
            reasons,
            "영업이익 증가세가 강함"
        )

    elif operating_growth >= 5:
        score += 6
        add_reason(
            reasons,
            "영업이익이 증가"
        )

    elif operating_growth < 0:
        score -= 12
        add_reason(
            reasons,
            "영업이익이 감소"
        )

    if net_income_growth >= 20:
        score += 8
        add_reason(
            reasons,
            "순이익 성장세가 강함"
        )

    elif net_income_growth < 0:
        score -= 8
        add_reason(
            reasons,
            "순이익이 감소"
        )

    if roe >= 15:
        score += 6
        add_reason(
            reasons,
            "ROE가 우수"
        )

    elif roe >= 8:
        score += 3
        add_reason(
            reasons,
            "ROE가 양호"
        )

    elif roe < 5:
        score -= 5
        add_reason(
            reasons,
            "ROE가 낮음"
        )

    if operating_margin >= 15:
        score += 5
        add_reason(
            reasons,
            "영업이익률이 우수"
        )

    elif operating_margin < 5:
        score -= 5
        add_reason(
            reasons,
            "영업이익률이 낮음"
        )

    supply = market.get(
        "수급",
        {},
    ) or {}

    combined_smart_money = (
        safe_float(
            supply.get(
                "외국인순매수"
            )
        )
        + safe_float(
            supply.get(
                "기관순매수"
            )
        )
    )

    if combined_smart_money > 0:
        score += 5
        add_reason(
            reasons,
            "외국인·기관 수급이 우호적"
        )

    elif combined_smart_money < 0:
        score -= 5
        add_reason(
            reasons,
            "외국인·기관 수급이 비우호적"
        )

    final_score = clamp(score)

    return {
        "기간": "1~8주",
        "점수": final_score,
        "상승확률": final_score,
        "판정": score_label(
            final_score
        ),
        "근거": reasons,
    }


def calculate_long_term(
    financial,
    valuation,
):
    score = 50
    reasons = []

    indicators = (
        financial.get(
            "재무지표",
            {},
        )
        or {}
    )

    growth = (
        financial.get(
            "성장지표",
            {},
        )
        or {}
    )

    buffett = (
        financial.get(
            "버핏평가",
            {},
        )
        or {}
    )

    roe = safe_float(
        indicators.get("ROE")
    )
    debt_ratio = safe_float(
        indicators.get(
            "부채비율"
        )
    )
    operating_margin = safe_float(
        indicators.get(
            "영업이익률"
        )
    )
    revenue_growth = safe_float(
        growth.get(
            "매출3년성장률"
        )
    )
    operating_growth = safe_float(
        growth.get(
            "영업이익3년성장률"
        )
    )
    buffett_score = safe_float(
        buffett.get("점수")
    )

    valuation_gap = safe_float(
        valuation.get(
            "현재가대비"
        )
    )
    valuation_judgment = str(
        valuation.get(
            "판단",
            "",
        )
    )

    if roe >= 15:
        score += 10
        add_reason(
            reasons,
            "장기 자본효율성이 우수"
        )

    elif roe >= 8:
        score += 5
        add_reason(
            reasons,
            "장기 자본효율성이 양호"
        )

    elif roe < 5:
        score -= 8
        add_reason(
            reasons,
            "자본효율성이 낮음"
        )

    if debt_ratio <= 50:
        score += 8
        add_reason(
            reasons,
            "부채비율이 낮아 재무안전성이 높음"
        )

    elif debt_ratio >= 150:
        score -= 12
        add_reason(
            reasons,
            "부채비율이 높음"
        )

    if operating_margin >= 15:
        score += 8
        add_reason(
            reasons,
            "높은 영업수익성"
        )

    elif operating_margin >= 8:
        score += 4
        add_reason(
            reasons,
            "영업수익성이 양호"
        )

    elif operating_margin < 3:
        score -= 8
        add_reason(
            reasons,
            "영업수익성이 낮음"
        )

    if (
        revenue_growth > 0
        and operating_growth > 0
    ):
        score += 10
        add_reason(
            reasons,
            "매출과 영업이익이 함께 성장"
        )

    elif (
        revenue_growth < 0
        and operating_growth < 0
    ):
        score -= 12
        add_reason(
            reasons,
            "매출과 영업이익이 함께 감소"
        )

    if buffett_score >= 80:
        score += 8
        add_reason(
            reasons,
            "버핏형 기업 평가가 우수"
        )

    elif buffett_score < 50:
        score -= 8
        add_reason(
            reasons,
            "기업 품질 평가가 낮음"
        )

    if (
        valuation_gap >= 30
        or "저평가" in valuation_judgment
    ):
        score += 16
        add_reason(
            reasons,
            "적정가 대비 안전마진이 큼"
        )

    elif valuation_gap >= 10:
        score += 8
        add_reason(
            reasons,
            "적정가 대비 상승여력이 존재"
        )

    elif (
        valuation_gap <= -30
        or "고평가" in valuation_judgment
    ):
        score -= 20
        add_reason(
            reasons,
            "현재 가격의 고평가 부담이 큼"
        )

    elif valuation_gap < 0:
        score -= 8
        add_reason(
            reasons,
            "현재 가격에 고평가 부담이 존재"
        )

    final_score = clamp(score)

    return {
        "기간": "6~18개월",
        "점수": final_score,
        "상승확률": final_score,
        "판정": score_label(
            final_score
        ),
        "가치평가반영": {
            "현재가대비": valuation_gap,
            "판단": valuation_judgment,
        },
        "근거": reasons,
    }


def predict_stock(
    market,
    financial,
    value,
):
    short_term = calculate_short_term(
        market
    )

    mid_term = calculate_mid_term(
        market,
        financial,
    )

    long_term = calculate_long_term(
        financial,
        value,
    )

    return {
        "단기1~5일": short_term,
        "중기1~8주": mid_term,
        "장기6~18개월": long_term,
        "데이터완전성": {
            "KIS가격": bool(
                safe_float(
                    market.get(
                        "현재가"
                    )
                )
            ),
            "KIS수급": any(
                safe_float(
                    (
                        market.get(
                            "수급",
                            {},
                        )
                        or {}
                    ).get(key)
                )
                != 0
                for key in (
                    "외국인순매수",
                    "기관순매수",
                    "개인순매수",
                )
            ),
            "DART재무": bool(
                financial.get(
                    "재무지표"
                )
            ),
            "가치평가": bool(value),
        },
    }
