"""
주가예측 통합 엔진 V6
- KIS 과거 일봉
- 5일·20일 누적 수급
- 시장 프로그램매매
연결 버전

고정 가중치
단기 1~5일
- 파생시장·프로그램 30
- 외국인·기관 수급 25
- 기술·거래량 20
- 환율·글로벌 15
- 뉴스·공시 10

중기 1~8주
- 분기 실적 25
- 산업 선행지표 25
- 누적수급 15
- 환율·금리·거시 15
- 가격추세 10
- 뉴스·공시 10

장기 6~18개월
- 향후 이익 방향 30
- 산업 사이클 25
- 가치평가·안전마진 20
- 경쟁력·시장점유율 10
- 현금흐름·재무안전성 10
- 주주환원·지배구조 5

미수집 항목은 임의 추정하지 않고 중립 처리한다.
상승확률은 데이터 신뢰도에 따라 50% 방향으로 축소한다.
"""


SHORT_WEIGHTS = {
    "파생시장·프로그램": 30,
    "외국인·기관수급": 25,
    "기술·거래량": 20,
    "환율·글로벌": 15,
    "뉴스·공시": 10,
}

MID_WEIGHTS = {
    "분기실적": 25,
    "산업선행지표": 25,
    "누적수급": 15,
    "환율·금리·거시": 15,
    "가격추세": 10,
    "뉴스·공시": 10,
}

LONG_WEIGHTS = {
    "향후이익방향": 30,
    "산업사이클": 25,
    "가치평가·안전마진": 20,
    "경쟁력·시장점유율": 10,
    "현금흐름·재무안전성": 10,
    "주주환원·지배구조": 5,
}


def safe_float(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def round_int(value):
    return int(round(value))


def add_reason(reasons, text):
    if text and text not in reasons:
        reasons.append(text)


def score_label(score):
    if score >= 70:
        return "강한 상승 우위"
    if score >= 58:
        return "상승 우위"
    if score >= 43:
        return "중립"
    if score >= 30:
        return "하락 우위"
    return "강한 하락 우위"


def confidence_label(confidence):
    if confidence >= 80:
        return "높음"
    if confidence >= 60:
        return "보통"
    if confidence >= 40:
        return "낮음"
    return "매우 낮음"


def signal_label(signal):
    if signal >= 60:
        return "매우 긍정"
    if signal >= 20:
        return "긍정"
    if signal > -20:
        return "중립"
    if signal > -60:
        return "부정"
    return "매우 부정"


def probability_from_score(score, confidence):
    confidence_ratio = clamp(confidence / 100.0, 0.0, 1.0)
    probability = 50.0 + (score - 50.0) * confidence_ratio * 0.80
    return round_int(clamp(probability, 20.0, 80.0))


def normalize_signal(value):
    return clamp(value, -100.0, 100.0)


def build_factor(
    name,
    weight,
    signal=0.0,
    quality=0.0,
    source="미수집",
    note="",
):
    signal = normalize_signal(signal)
    quality = clamp(quality, 0.0, 1.0)
    contribution = weight * (signal / 100.0)

    return {
        "요소": name,
        "가중치": weight,
        "신호": round(signal, 2),
        "신호판정": signal_label(signal),
        "데이터품질": round(quality * 100, 1),
        "점수기여": round(contribution, 2),
        "출처": source,
        "설명": note,
    }


def finalize_prediction(period, factors, reasons):
    total_signal = sum(item["점수기여"] for item in factors)

    score = 50.0 + (total_signal / 2.0)
    score = round_int(clamp(score, 15.0, 85.0))

    confidence = sum(
        item["가중치"] * (item["데이터품질"] / 100.0)
        for item in factors
    )
    confidence = round_int(clamp(confidence, 0.0, 100.0))

    probability = probability_from_score(score, confidence)

    missing = [
        item["요소"]
        for item in factors
        if item["데이터품질"] <= 0
    ]

    weak_proxy = [
        item["요소"]
        for item in factors
        if 0 < item["데이터품질"] < 70
    ]

    return {
        "기간": period,
        "점수": score,
        "상승확률": probability,
        "판정": score_label(score),
        "신뢰도": confidence,
        "신뢰도등급": confidence_label(confidence),
        "요소별평가": factors,
        "미수집요소": missing,
        "약한대용지표": weak_proxy,
        "근거": reasons,
    }


def get_history(market):
    history = market.get("과거데이터", {}) or {}

    return {
        "price": history.get("가격추세", {}) or {},
        "investor": history.get("누적수급", {}) or {},
        "program": history.get("프로그램매매", {}) or {},
        "status": history.get("수집상태", {}) or {},
    }


def current_supply_signal(market):
    supply = market.get("수급", {}) or {}

    foreign_net = safe_float(supply.get("외국인순매수"))
    institution_net = safe_float(supply.get("기관순매수"))
    individual_net = safe_float(supply.get("개인순매수"))
    volume = safe_float(market.get("거래량"))

    combined = foreign_net + institution_net
    ratio = combined / volume if volume > 0 else 0.0

    signal = clamp((ratio / 0.10) * 100.0, -100.0, 100.0)

    if foreign_net > 0 and institution_net > 0:
        signal += 10
    elif foreign_net < 0 and institution_net < 0:
        signal -= 10

    if combined > 0 and individual_net < 0:
        signal += 5
    elif combined < 0 and individual_net > 0:
        signal -= 5

    signal = normalize_signal(signal)

    exists = (
        volume > 0
        and any(
            value != 0
            for value in (
                foreign_net,
                institution_net,
                individual_net,
            )
        )
    )

    return {
        "signal": signal,
        "quality": 1.0 if exists else 0.0,
        "foreign": foreign_net,
        "institution": institution_net,
        "individual": individual_net,
        "combined": combined,
        "ratio": ratio,
    }


def accumulated_supply_signal(market):
    history = get_history(market)
    investor = history["investor"]
    price = history["price"]

    combined_5 = safe_float(investor.get("외국인기관합산5일"))
    combined_20 = safe_float(investor.get("외국인기관합산20일"))

    average_volume_20 = safe_float(price.get("20일평균거래량"))
    denominator_5 = average_volume_20 * 5.0
    denominator_20 = average_volume_20 * 20.0

    ratio_5 = combined_5 / denominator_5 if denominator_5 > 0 else 0.0
    ratio_20 = combined_20 / denominator_20 if denominator_20 > 0 else 0.0

    signal_5 = clamp((ratio_5 / 0.03) * 45.0, -45.0, 45.0)
    signal_20 = clamp((ratio_20 / 0.03) * 55.0, -55.0, 55.0)

    signal = normalize_signal(signal_5 + signal_20)

    investor_count = int(
        safe_float(
            history["status"].get("누적수급데이터개수")
        )
    )

    if investor_count >= 20:
        quality = 1.0
    elif investor_count >= 5:
        quality = 0.65
    elif investor_count > 0:
        quality = 0.35
    else:
        quality = 0.0

    return {
        "signal": signal,
        "quality": quality,
        "combined_5": combined_5,
        "combined_20": combined_20,
        "ratio_5": ratio_5,
        "ratio_20": ratio_20,
        "count": investor_count,
    }


def program_signal(market):
    history = get_history(market)
    program = history["program"]
    price = history["price"]

    quantity_5 = safe_float(program.get("프로그램순매수수량5일"))
    quantity_20 = safe_float(program.get("프로그램순매수수량20일"))
    amount_5 = safe_float(program.get("프로그램순매수금액5일"))
    amount_20 = safe_float(program.get("프로그램순매수금액20일"))
    average_volume_20 = safe_float(price.get("20일평균거래량"))

    denominator_5 = average_volume_20 * 5.0
    denominator_20 = average_volume_20 * 20.0
    ratio_5 = quantity_5 / denominator_5 if denominator_5 > 0 else 0.0
    ratio_20 = quantity_20 / denominator_20 if denominator_20 > 0 else 0.0

    if average_volume_20 > 0:
        signal_5 = clamp(ratio_5 / 0.02 * 45.0, -45.0, 45.0)
        signal_20 = clamp(ratio_20 / 0.02 * 55.0, -55.0, 55.0)
        signal = normalize_signal(signal_5 + signal_20)
    else:
        signal = 0.0
        if quantity_5 > 0:
            signal += 25.0
        elif quantity_5 < 0:
            signal -= 25.0
        if quantity_20 > 0:
            signal += 35.0
        elif quantity_20 < 0:
            signal -= 35.0
        signal = normalize_signal(signal)

    count = int(safe_float(history["status"].get("프로그램데이터개수")))

    if count >= 20:
        quality = 0.70
    elif count >= 5:
        quality = 0.50
    elif count > 0:
        quality = 0.30
    else:
        quality = 0.0

    if quality > 0 and average_volume_20 <= 0:
        quality = min(quality, 0.35)

    return {
        "signal": signal,
        "quality": quality,
        "quantity_5": quantity_5,
        "quantity_20": quantity_20,
        "amount_5": amount_5,
        "amount_20": amount_20,
        "ratio_5": ratio_5,
        "ratio_20": ratio_20,
        "average_volume_20": average_volume_20,
        "count": count,
    }



def historical_technical_signal(market):
    history = get_history(market)
    price = history["price"]

    close = safe_float(price.get("종가"))
    ma5 = safe_float(price.get("MA5"))
    ma20 = safe_float(price.get("MA20"))
    ma60 = safe_float(price.get("MA60"))

    return_5 = safe_float(price.get("5일수익률"))
    return_20 = safe_float(price.get("20일수익률"))
    return_60 = safe_float(price.get("60일수익률"))
    rsi14 = safe_float(price.get("RSI14"))
    volume_ratio = safe_float(price.get("거래량비율5대20"))

    signal = 0.0
    components = 0

    if close > 0 and ma20 > 0:
        signal += 20 if close > ma20 else -20
        components += 1

    if ma5 > 0 and ma20 > 0:
        signal += 15 if ma5 > ma20 else -15
        components += 1

    if ma20 > 0 and ma60 > 0:
        signal += 20 if ma20 > ma60 else -20
        components += 1

    if return_5 != 0:
        signal += clamp(return_5 / 10.0 * 20.0, -20.0, 20.0)
        components += 1

    if return_20 != 0:
        signal += clamp(return_20 / 20.0 * 20.0, -20.0, 20.0)
        components += 1

    if rsi14 > 0:
        if 50 <= rsi14 <= 70:
            signal += 10
        elif rsi14 > 80:
            signal -= 5
        elif 30 <= rsi14 < 50:
            signal -= 5
        elif rsi14 < 30:
            signal += 5
        components += 1

    if volume_ratio >= 1.5 and return_5 > 0:
        signal += 10
    elif volume_ratio >= 1.5 and return_5 < 0:
        signal -= 10

    signal = normalize_signal(signal)

    count = int(
        safe_float(
            history["status"].get("가격데이터개수")
        )
    )

    if count >= 60:
        quality = 1.0
    elif count >= 20:
        quality = 0.75
    elif count >= 5:
        quality = 0.40
    else:
        quality = 0.0

    return {
        "signal": signal,
        "quality": quality,
        "close": close,
        "ma5": ma5,
        "ma20": ma20,
        "ma60": ma60,
        "return_5": return_5,
        "return_20": return_20,
        "return_60": return_60,
        "rsi14": rsi14,
        "volume_ratio": volume_ratio,
        "count": count,
    }


def intraday_technical_signal(market):
    current_price = safe_float(market.get("현재가"))
    open_price = safe_float(market.get("시가"))
    high_price = safe_float(market.get("고가"))
    low_price = safe_float(market.get("저가"))
    change_rate = safe_float(market.get("등락률"))
    volume = safe_float(market.get("거래량"))

    signal = 0.0
    components = 0

    if change_rate != 0:
        signal += clamp(change_rate / 10.0 * 60.0, -60.0, 60.0)
        components += 1

    if current_price > 0 and open_price > 0:
        intraday_rate = (current_price - open_price) / open_price * 100.0
        signal += clamp(intraday_rate / 5.0 * 20.0, -20.0, 20.0)
        components += 1

    if current_price > 0 and high_price > low_price > 0:
        position = (current_price - low_price) / (high_price - low_price)
        signal += (position - 0.5) * 40.0
        components += 1

    if components > 0:
        signal = signal / components * 1.5

    required = [
        current_price > 0,
        open_price > 0,
        high_price > 0,
        low_price > 0,
        volume > 0,
    ]

    return {
        "signal": normalize_signal(signal),
        "quality": sum(required) / len(required),
        "change_rate": change_rate,
    }


def combined_short_technical_signal(market):
    historical = historical_technical_signal(market)
    intraday = intraday_technical_signal(market)

    if historical["quality"] > 0:
        signal = (
            historical["signal"] * 0.75
            + intraday["signal"] * 0.25
        )
        quality = (
            historical["quality"] * 0.80
            + intraday["quality"] * 0.20
        )
        source = "KIS 일봉+현재가"
    else:
        signal = intraday["signal"]
        quality = intraday["quality"] * 0.45
        source = "KIS 현재가 대용"

    return {
        "signal": normalize_signal(signal),
        "quality": clamp(quality, 0.0, 1.0),
        "source": source,
        "historical": historical,
        "intraday": intraday,
    }


def earnings_signal(financial):
    growth = financial.get("성장지표", {}) or {}

    revenue_growth = safe_float(growth.get("매출3년성장률"))
    operating_growth = safe_float(growth.get("영업이익3년성장률"))
    net_income_growth = safe_float(growth.get("순이익3년성장률"))

    values = [
        revenue_growth,
        operating_growth,
        net_income_growth,
    ]

    present = sum(value != 0 for value in values)

    if present == 0:
        return {
            "signal": 0.0,
            "quality": 0.0,
        }

    revenue_component = clamp(
        revenue_growth / 30.0 * 35.0,
        -35.0,
        35.0,
    )
    operating_component = clamp(
        operating_growth / 50.0 * 40.0,
        -40.0,
        40.0,
    )
    net_component = clamp(
        net_income_growth / 40.0 * 25.0,
        -25.0,
        25.0,
    )

    signal = normalize_signal(
        revenue_component
        + operating_component
        + net_component
    )

    quality = (present / 3.0) * 0.60

    return {
        "signal": signal,
        "quality": quality,
    }


def quality_signal(financial):
    indicators = financial.get("재무지표", {}) or {}
    buffett = financial.get("버핏평가", {}) or {}

    roe = safe_float(indicators.get("ROE"))
    operating_margin = safe_float(indicators.get("영업이익률"))
    debt_ratio = safe_float(indicators.get("부채비율"))
    buffett_score = safe_float(buffett.get("점수"))

    components = []

    if roe != 0:
        components.append(
            clamp(
                (roe - 8.0) / 12.0 * 100.0,
                -100.0,
                100.0,
            )
        )

    if operating_margin != 0:
        components.append(
            clamp(
                (operating_margin - 8.0) / 12.0 * 100.0,
                -100.0,
                100.0,
            )
        )

    if buffett_score != 0:
        components.append(
            clamp(
                (buffett_score - 50.0) / 30.0 * 100.0,
                -100.0,
                100.0,
            )
        )

    if components:
        business_signal = sum(components) / len(components)
        business_quality = min(len(components) / 3.0, 1.0) * 0.70
    else:
        business_signal = 0.0
        business_quality = 0.0

    if debt_ratio != 0:
        safety_signal = clamp(
            (100.0 - debt_ratio) / 70.0 * 100.0,
            -100.0,
            100.0,
        )
        safety_quality = 0.50
    else:
        safety_signal = 0.0
        safety_quality = 0.0

    return {
        "business_signal": normalize_signal(business_signal),
        "business_quality": business_quality,
        "safety_signal": normalize_signal(safety_signal),
        "safety_quality": safety_quality,
    }


def valuation_signal(valuation):
    gap = safe_float(valuation.get("현재가대비"))
    judgment = str(valuation.get("판단", ""))

    if gap != 0:
        signal = clamp(gap / 40.0 * 100.0, -100.0, 100.0)
        quality = 1.0
    elif "저평가" in judgment:
        signal = 40.0
        quality = 0.50
    elif "고평가" in judgment:
        signal = -40.0
        quality = 0.50
    else:
        signal = 0.0
        quality = 0.0

    return {
        "signal": normalize_signal(signal),
        "quality": quality,
        "gap": gap,
        "judgment": judgment,
    }


def external_signal(
    analysis,
    signal_key,
    quality_key,
):
    if not isinstance(analysis, dict):
        return {
            "signal": 0.0,
            "quality": 0.0,
            "status": "미수집",
        }

    signal = normalize_signal(
        safe_float(
            analysis.get(signal_key)
        )
    )

    quality = clamp(
        safe_float(
            analysis.get(quality_key)
        )
        / 100.0,
        0.0,
        1.0,
    )

    return {
        "signal": signal,
        "quality": quality,
        "status": str(
            analysis.get(
                "분석상태",
                "미수집",
            )
        ),
    }


def disclosure_signal(
    disclosure_analysis,
):
    return external_signal(
        disclosure_analysis,
        "신호",
        "데이터품질",
    )


def combined_event_signal(
    disclosure_analysis,
    news_analysis,
):
    disclosure = external_signal(
        disclosure_analysis,
        "신호",
        "데이터품질",
    )
    news = external_signal(
        news_analysis,
        "신호",
        "데이터품질",
    )

    components = []

    if disclosure["quality"] > 0:
        components.append(
            {
                "signal": disclosure["signal"],
                "weight": disclosure["quality"] * 0.55,
                "source": "OpenDART 최근 공시",
            }
        )

    if news["quality"] > 0:
        components.append(
            {
                "signal": news["signal"],
                "weight": news["quality"] * 0.45,
                "source": "Google News RSS",
            }
        )

    total_weight = sum(
        item["weight"]
        for item in components
    )

    if total_weight <= 0:
        return {
            "signal": 0.0,
            "quality": 0.0,
            "status": "미수집",
            "source": "뉴스·공시 미수집",
            "disclosure": disclosure,
            "news": news,
        }

    signal = sum(
        item["signal"] * item["weight"]
        for item in components
    ) / total_weight

    quality = clamp(
        total_weight / 1.0,
        0.0,
        1.0,
    )

    return {
        "signal": normalize_signal(signal),
        "quality": quality,
        "status": "정상",
        "source": " + ".join(
            item["source"]
            for item in components
        ),
        "disclosure": disclosure,
        "news": news,
    }



def nested_analysis_signal(
    analysis,
    section_name,
):
    if not isinstance(analysis, dict):
        return {
            "signal": 0.0,
            "quality": 0.0,
            "status": "미수집",
            "section": {},
        }

    section = analysis.get(
        section_name,
        {},
    )

    if not isinstance(section, dict):
        section = {}

    return {
        "signal": normalize_signal(
            safe_float(
                section.get("신호")
            )
        ),
        "quality": clamp(
            safe_float(
                section.get("데이터품질")
            )
            / 100.0,
            0.0,
            1.0,
        ),
        "status": str(
            analysis.get(
                "분석상태",
                "미수집",
            )
        ),
        "section": section,
    }


def choose_signal(
    primary,
    fallback,
    primary_source,
    fallback_source,
):
    if primary["quality"] > 0:
        return {
            "signal": primary["signal"],
            "quality": primary["quality"],
            "source": primary_source,
            "used_fallback": False,
            "section": primary.get(
                "section",
                {},
            ),
        }

    return {
        "signal": fallback["signal"],
        "quality": fallback["quality"],
        "source": fallback_source,
        "used_fallback": True,
        "section": fallback.get(
            "section",
            {},
        ),
    }

def calculate_short_term(
    market,
    disclosure_analysis=None,
    global_analysis=None,
    news_analysis=None,
):
    reasons = []

    program = program_signal(market)
    current_supply = current_supply_signal(market)
    technical = combined_short_technical_signal(market)
    global_market = external_signal(
        global_analysis,
        "단기신호",
        "단기데이터품질",
    )
    disclosure = combined_event_signal(
        disclosure_analysis,
        news_analysis,
    )

    if program["signal"] >= 20:
        add_reason(reasons, "시장 프로그램매매가 순매수 우위")
    elif program["signal"] <= -20:
        add_reason(reasons, "시장 프로그램매매가 순매도 우위")

    if current_supply["signal"] >= 60:
        add_reason(reasons, "외국인·기관 순매수가 거래량 대비 매우 강함")
    elif current_supply["signal"] >= 20:
        add_reason(reasons, "외국인·기관 당일 수급이 우호적")
    elif current_supply["signal"] <= -60:
        add_reason(reasons, "외국인·기관 순매도가 거래량 대비 매우 강함")
    elif current_supply["signal"] <= -20:
        add_reason(reasons, "외국인·기관 당일 수급이 비우호적")

    if (
        current_supply["combined"] > 0
        and current_supply["individual"] < 0
    ):
        add_reason(reasons, "개인 매도 물량을 외국인·기관이 흡수")

    if technical["signal"] >= 60:
        add_reason(reasons, "일봉·당일 가격 모멘텀이 매우 강함")
    elif technical["signal"] >= 20:
        add_reason(reasons, "일봉·당일 가격 흐름이 상승")
    elif technical["signal"] <= -60:
        add_reason(reasons, "일봉·당일 가격 모멘텀이 매우 약함")
    elif technical["signal"] <= -20:
        add_reason(reasons, "일봉·당일 가격 흐름이 하락")

    if global_market["signal"] >= 20:
        add_reason(reasons, "환율·미국시장·반도체·VIX 환경이 우호적")
    elif global_market["signal"] <= -20:
        add_reason(reasons, "환율·미국시장·반도체·VIX 환경이 비우호적")

    if disclosure["signal"] >= 20:
        add_reason(reasons, "최근 공시 이벤트가 긍정적")
    elif disclosure["signal"] <= -20:
        add_reason(reasons, "최근 공시 이벤트가 부정적")

    factors = [
        build_factor(
            "파생시장·프로그램",
            SHORT_WEIGHTS["파생시장·프로그램"],
            signal=program["signal"],
            quality=program["quality"],
            source="KIS 종목별 프로그램매매",
            note=(
                f"5일 수량 {program['quantity_5']:.0f}, "
                f"20일 수량 {program['quantity_20']:.0f}, "
                f"5일 거래량대비 {program['ratio_5'] * 100:.3f}%, "
                f"20일 거래량대비 {program['ratio_20'] * 100:.3f}%"
            ),
        ),
        build_factor(
            "외국인·기관수급",
            SHORT_WEIGHTS["외국인·기관수급"],
            signal=current_supply["signal"],
            quality=current_supply["quality"],
            source="KIS 투자자별 당일 매매",
            note=(
                "외국인+기관 합산 "
                f"{current_supply['combined']:.0f}주, "
                f"거래량 대비 {current_supply['ratio'] * 100:.3f}%"
            ),
        ),
        build_factor(
            "기술·거래량",
            SHORT_WEIGHTS["기술·거래량"],
            signal=technical["signal"],
            quality=technical["quality"],
            source=technical["source"],
            note=(
                f"5일수익률 "
                f"{technical['historical']['return_5']:.2f}%, "
                f"RSI14 {technical['historical']['rsi14']:.2f}"
            ),
        ),
        build_factor(
            "환율·글로벌",
            SHORT_WEIGHTS["환율·글로벌"],
            signal=global_market["signal"],
            quality=global_market["quality"],
            source="Yahoo 글로벌시장 분석",
            note=(
                f"분석상태 {global_market['status']}, "
                f"신호 {global_market['signal']:.2f}"
            ),
        ),
        build_factor(
            "뉴스·공시",
            SHORT_WEIGHTS["뉴스·공시"],
            signal=disclosure["signal"],
            quality=disclosure["quality"],
            source=disclosure["source"],
            note=(
                f"분석상태 {disclosure['status']}, "
                f"신호 {disclosure['signal']:.2f}"
            ),
        ),
    ]

    return finalize_prediction(
        "1~5일",
        factors,
        reasons,
    )


def calculate_mid_term(
    market,
    financial,
    disclosure_analysis=None,
    global_analysis=None,
    fundamentals_analysis=None,
    industry_analysis=None,
    news_analysis=None,
):
    reasons = []

    legacy_earnings = earnings_signal(
        financial
    )

    fundamental_earnings = (
        nested_analysis_signal(
            fundamentals_analysis,
            "분기실적",
        )
    )

    earnings = choose_signal(
        fundamental_earnings,
        legacy_earnings,
        "OpenDART 최신 분기 전년동기 실적",
        "DART 3년 성장률 대용",
    )

    industry = nested_analysis_signal(
        industry_analysis,
        "중기산업선행",
    )

    accumulated = accumulated_supply_signal(
        market
    )

    historical = historical_technical_signal(
        market
    )

    global_macro = external_signal(
        global_analysis,
        "중기신호",
        "중기데이터품질",
    )

    disclosure = combined_event_signal(
        disclosure_analysis,
        news_analysis,
    )

    if earnings["signal"] >= 60:
        add_reason(
            reasons,
            "최신 실적 성장 신호가 매우 강함",
        )
    elif earnings["signal"] >= 20:
        add_reason(
            reasons,
            "최신 실적 성장 신호가 양호",
        )
    elif earnings["signal"] <= -20:
        add_reason(
            reasons,
            "최신 실적 성장 신호가 약함",
        )

    if industry["signal"] >= 60:
        add_reason(
            reasons,
            "반도체 산업 선행 흐름이 매우 강함",
        )
    elif industry["signal"] >= 20:
        add_reason(
            reasons,
            "반도체 산업 선행 흐름이 우호적",
        )
    elif industry["signal"] <= -20:
        add_reason(
            reasons,
            "반도체 산업 선행 흐름이 비우호적",
        )

    if accumulated["signal"] >= 20:
        add_reason(
            reasons,
            "외국인·기관 5일·20일 누적수급이 우호적",
        )
    elif accumulated["signal"] <= -20:
        add_reason(
            reasons,
            "외국인·기관 5일·20일 누적수급이 비우호적",
        )

    if historical["signal"] >= 20:
        add_reason(
            reasons,
            "20일·60일 가격추세가 우호적",
        )
    elif historical["signal"] <= -20:
        add_reason(
            reasons,
            "20일·60일 가격추세가 비우호적",
        )

    if global_macro["signal"] >= 20:
        add_reason(
            reasons,
            "원달러·미국금리·글로벌 추세가 우호적",
        )
    elif global_macro["signal"] <= -20:
        add_reason(
            reasons,
            "원달러·미국금리·글로벌 추세가 비우호적",
        )

    if disclosure["signal"] >= 20:
        add_reason(
            reasons,
            "최근 공시 이벤트가 중기 방향에 긍정적",
        )
    elif disclosure["signal"] <= -20:
        add_reason(
            reasons,
            "최근 공시 이벤트가 중기 방향에 부정적",
        )

    factors = [
        build_factor(
            "분기실적",
            MID_WEIGHTS["분기실적"],
            signal=earnings["signal"],
            quality=earnings["quality"],
            source=earnings["source"],
            note=(
                "최신 분기 전년동기 비교 사용"
                if not earnings["used_fallback"]
                else "분기 비교 실패로 3년 성장률 대용"
            ),
        ),
        build_factor(
            "산업선행지표",
            MID_WEIGHTS["산업선행지표"],
            signal=industry["signal"],
            quality=industry["quality"],
            source="반도체 산업 대표자산 합성",
            note=(
                f"산업국면 "
                f"{industry_analysis.get('산업국면', '')}"
                if isinstance(
                    industry_analysis,
                    dict,
                )
                else "산업 데이터 미수집"
            ),
        ),
        build_factor(
            "누적수급",
            MID_WEIGHTS["누적수급"],
            signal=accumulated["signal"],
            quality=accumulated["quality"],
            source="KIS 투자자별 일별 매매",
            note=(
                f"5일 합산 "
                f"{accumulated['combined_5']:.0f}주, "
                f"20일 합산 "
                f"{accumulated['combined_20']:.0f}주"
            ),
        ),
        build_factor(
            "환율·금리·거시",
            MID_WEIGHTS["환율·금리·거시"],
            signal=global_macro["signal"],
            quality=global_macro["quality"],
            source="Yahoo 환율·미국금리·글로벌시장",
            note=(
                f"분석상태 "
                f"{global_macro['status']}, "
                f"신호 "
                f"{global_macro['signal']:.2f}"
            ),
        ),
        build_factor(
            "가격추세",
            MID_WEIGHTS["가격추세"],
            signal=historical["signal"],
            quality=historical["quality"],
            source="KIS 일봉",
            note=(
                f"20일수익률 "
                f"{historical['return_20']:.2f}%, "
                f"60일수익률 "
                f"{historical['return_60']:.2f}%"
            ),
        ),
        build_factor(
            "뉴스·공시",
            MID_WEIGHTS["뉴스·공시"],
            signal=disclosure["signal"],
            quality=disclosure["quality"],
            source=disclosure["source"],
            note=(
                f"분석상태 "
                f"{disclosure['status']}, "
                f"신호 "
                f"{disclosure['signal']:.2f}"
            ),
        ),
    ]

    return finalize_prediction(
        "1~8주",
        factors,
        reasons,
    )



def calculate_long_term(
    financial,
    valuation,
    fundamentals_analysis=None,
    industry_analysis=None,
):
    reasons = []

    legacy_earnings = earnings_signal(
        financial
    )

    fundamental_future = (
        nested_analysis_signal(
            fundamentals_analysis,
            "향후이익방향대용",
        )
    )

    future = choose_signal(
        fundamental_future,
        legacy_earnings,
        "OpenDART 최신실적·현금창출력 대용",
        "DART 3년 성장률 대용",
    )

    industry_cycle = (
        nested_analysis_signal(
            industry_analysis,
            "장기산업사이클",
        )
    )

    quality = quality_signal(
        financial
    )

    value = valuation_signal(
        valuation
    )

    cash_flow = (
        nested_analysis_signal(
            fundamentals_analysis,
            "현금흐름재무안전성",
        )
    )

    if cash_flow["quality"] <= 0:
        cash_flow = {
            "signal": quality[
                "safety_signal"
            ],
            "quality": quality[
                "safety_quality"
            ],
            "status": "부채비율 대용",
            "section": {},
        }
        cash_source = "부채비율 대용"
    else:
        cash_source = (
            "OpenDART 현금흐름·FCF·부채비율"
        )

    shareholder = (
        nested_analysis_signal(
            fundamentals_analysis,
            "주주환원",
        )
    )

    # 지배구조 데이터가 아직 없으므로
    # 주주환원 데이터 품질을 그대로 100% 인정하지 않는다.
    shareholder_quality = (
        shareholder["quality"]
        * 0.80
    )

    if future["signal"] >= 60:
        add_reason(
            reasons,
            "최신 실적과 현금창출력 기반 이익 방향이 강함",
        )
    elif future["signal"] <= -20:
        add_reason(
            reasons,
            "최신 실적과 현금창출력 기반 이익 방향이 약함",
        )

    if industry_cycle["signal"] >= 60:
        add_reason(
            reasons,
            "반도체 산업 장기 사이클이 매우 우호적",
        )
    elif industry_cycle["signal"] >= 20:
        add_reason(
            reasons,
            "반도체 산업 장기 사이클이 우호적",
        )
    elif industry_cycle["signal"] <= -20:
        add_reason(
            reasons,
            "반도체 산업 장기 사이클이 비우호적",
        )

    if value["signal"] >= 40:
        add_reason(
            reasons,
            "적정가 대비 안전마진이 존재",
        )
    elif value["signal"] <= -40:
        add_reason(
            reasons,
            "현재 가격의 고평가 부담이 큼",
        )

    if quality["business_signal"] >= 40:
        add_reason(
            reasons,
            "ROE·영업이익률·기업 품질이 양호",
        )
    elif quality["business_signal"] <= -20:
        add_reason(
            reasons,
            "기업 경쟁력 대용지표가 약함",
        )

    if cash_flow["signal"] >= 40:
        add_reason(
            reasons,
            "현금흐름과 재무안전성이 우수",
        )
    elif cash_flow["signal"] <= -20:
        add_reason(
            reasons,
            "현금흐름 또는 재무안전성이 취약",
        )

    if shareholder["signal"] >= 20:
        add_reason(
            reasons,
            "배당·자기주식 기준 주주환원이 우호적",
        )
    elif shareholder["signal"] <= -20:
        add_reason(
            reasons,
            "배당·자기주식 기준 주주환원이 비우호적",
        )

    factors = [
        build_factor(
            "향후이익방향",
            LONG_WEIGHTS["향후이익방향"],
            signal=future["signal"],
            quality=future["quality"],
            source=future["source"],
            note=(
                "애널리스트 컨센서스 미반영 대용지표"
                if not future["used_fallback"]
                else "최신 분기자료 실패로 3년 성장률 대용"
            ),
        ),
        build_factor(
            "산업사이클",
            LONG_WEIGHTS["산업사이클"],
            signal=industry_cycle["signal"],
            quality=industry_cycle["quality"],
            source="반도체 산업 대표자산 1년 추세",
            note=(
                f"산업국면 "
                f"{industry_analysis.get('산업국면', '')}"
                if isinstance(
                    industry_analysis,
                    dict,
                )
                else "산업 데이터 미수집"
            ),
        ),
        build_factor(
            "가치평가·안전마진",
            LONG_WEIGHTS["가치평가·안전마진"],
            signal=value["signal"],
            quality=value["quality"],
            source="내부 가치평가",
            note=(
                f"현재가 대비 "
                f"{value['gap']:.2f}%, "
                f"판단 "
                f"{value['judgment']}"
            ),
        ),
        build_factor(
            "경쟁력·시장점유율",
            LONG_WEIGHTS["경쟁력·시장점유율"],
            signal=quality[
                "business_signal"
            ],
            quality=quality[
                "business_quality"
            ],
            source="ROE·영업이익률·버핏점수 대용",
            note=(
                "실제 시장점유율과 경쟁사 비교는 아직 미연결"
            ),
        ),
        build_factor(
            "현금흐름·재무안전성",
            LONG_WEIGHTS["현금흐름·재무안전성"],
            signal=cash_flow["signal"],
            quality=cash_flow["quality"],
            source=cash_source,
            note=(
                f"분석상태 "
                f"{cash_flow['status']}"
            ),
        ),
        build_factor(
            "주주환원·지배구조",
            LONG_WEIGHTS["주주환원·지배구조"],
            signal=shareholder["signal"],
            quality=shareholder_quality,
            source="OpenDART 배당·자기주식",
            note=(
                "배당·자사주는 반영, "
                "지배구조 정량평가는 아직 미연결"
            ),
        ),
    ]

    return finalize_prediction(
        "6~18개월",
        factors,
        reasons,
    )



def predict_stock(
    market,
    financial,
    value,
    disclosure_analysis=None,
    global_analysis=None,
    fundamentals_analysis=None,
    industry_analysis=None,
    news_analysis=None,
    technical_analysis=None,
):
    short_term = calculate_short_term(
        market,
        disclosure_analysis=(
            disclosure_analysis
        ),
        global_analysis=(
            global_analysis
        ),
        news_analysis=(
            news_analysis
        ),
    )

    mid_term = calculate_mid_term(
        market,
        financial,
        disclosure_analysis=(
            disclosure_analysis
        ),
        global_analysis=(
            global_analysis
        ),
        fundamentals_analysis=(
            fundamentals_analysis
        ),
        industry_analysis=(
            industry_analysis
        ),
        news_analysis=(
            news_analysis
        ),
    )

    long_term = calculate_long_term(
        financial,
        value,
        fundamentals_analysis=(
            fundamentals_analysis
        ),
        industry_analysis=(
            industry_analysis
        ),
    )

    supply = market.get(
        "수급",
        {},
    ) or {}

    history = get_history(
        market
    )

    disclosure_ok = (
        isinstance(
            disclosure_analysis,
            dict,
        )
        and disclosure_analysis.get(
            "분석상태"
        )
        == "정상"
    )

    news_ok = (
        isinstance(
            news_analysis,
            dict,
        )
        and news_analysis.get(
            "분석상태"
        )
        == "정상"
    )

    global_ok = (
        isinstance(
            global_analysis,
            dict,
        )
        and global_analysis.get(
            "분석상태"
        )
        == "정상"
    )

    fundamentals_ok = (
        isinstance(
            fundamentals_analysis,
            dict,
        )
        and fundamentals_analysis.get(
            "분석상태"
        )
        == "정상"
    )

    industry_ok = (
        isinstance(
            industry_analysis,
            dict,
        )
        and industry_analysis.get(
            "분석상태"
        )
        == "정상"
    )

    technical_ok = (
        isinstance(technical_analysis, dict)
        and technical_analysis.get("수집상태")
        in {"정상", "부분성공"}
        and any(
            isinstance(technical_analysis.get(key), dict)
            and technical_analysis.get(key, {}).get("available") is True
            for key in ("일봉", "주봉", "월봉")
        )
    )

    history_status = history["status"] if isinstance(history.get("status"), dict) else {}
    price_history_ok = (
        history_status.get("가격데이터상태") == "정상"
        and int(safe_float(history_status.get("가격데이터개수"))) > 0
    )
    investor_history_ok = (
        history_status.get("누적수급데이터상태") == "정상"
        and int(safe_float(history_status.get("누적수급데이터개수"))) > 0
    )
    program_history_ok = (
        history_status.get("프로그램데이터상태") == "정상"
        and int(safe_float(history_status.get("프로그램데이터개수"))) > 0
    )
    market_source = str(market.get("데이터출처", "") or "")
    price_history_source = str(history_status.get("가격데이터출처", "") or "")
    kis_current_price_ok = bool(safe_float(market.get("현재가"))) and "KIS" in market_source
    kis_price_history_ok = price_history_ok and "KIS" in price_history_source

    return {
        "엔진버전": (
            "6.7.2-valuation-contract-v4"
        ),
        "단기1~5일": short_term,
        "중기1~8주": mid_term,
        "장기6~18개월": long_term,
        "데이터완전성": {
            "KIS현재가": kis_current_price_ok,
            "KIS당일수급": any(
                safe_float(
                    supply.get(key)
                )
                != 0
                for key in (
                    "외국인순매수",
                    "기관순매수",
                    "개인순매수",
                )
            ),
            "KIS일봉": kis_price_history_ok,
            "멀티타임프레임차트": technical_ok,
            "KIS누적수급": investor_history_ok,
            "KIS프로그램매매": program_history_ok,
            "현재가": bool(safe_float(market.get("현재가"))),
            "가격이력": price_history_ok,
            "누적수급": investor_history_ok,
            "프로그램매매": program_history_ok,
            "DART기본재무": bool(
                financial.get(
                    "재무지표"
                )
            ),
            "DART분기실적": (
                fundamentals_ok
                and nested_analysis_signal(
                    fundamentals_analysis,
                    "분기실적",
                )["quality"]
                > 0
            ),
            "DART현금흐름": (
                fundamentals_ok
                and nested_analysis_signal(
                    fundamentals_analysis,
                    "현금흐름재무안전성",
                )["quality"]
                > 0
            ),
            "DART주주환원": (
                fundamentals_ok
                and nested_analysis_signal(
                    fundamentals_analysis,
                    "주주환원",
                )["quality"]
                > 0
            ),
            "DART최근공시": (
                disclosure_ok
            ),
            "기업뉴스": news_ok,
            "글로벌시장": global_ok,
            "산업선행지표": (
                industry_ok
                and nested_analysis_signal(
                    industry_analysis,
                    "중기산업선행",
                )["quality"]
                > 0
            ),
            "산업사이클": (
                industry_ok
                and nested_analysis_signal(
                    industry_analysis,
                    "장기산업사이클",
                )["quality"]
                > 0
            ),
            "가치평가": bool(value),
            "애널리스트컨센서스": False,
            "실제시장점유율": False,
            "지배구조정량평가": False,
        },
        "주의": (
            "미수집 요소는 추정하지 않고 중립 처리한다. "
            "파생시장·프로그램 요소에는 현재 종목별 프로그램매매만 반영하며 "
            "파생시장 데이터는 아직 미반영이다. "
            "뉴스와 공시 신호는 제목 기반 규칙형 분석이다. "
            "향후이익 방향은 최신 실적과 현금창출력 기반 대용지표이며 "
            "애널리스트 컨센서스는 아직 반영되지 않았다. "
            "상승확률은 데이터 커버리지에 따라 "
            "50% 방향으로 축소된 모델 확률이다."
        ),
    }
