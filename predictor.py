"""
주가예측 통합 엔진 V3

고정 가중치
- 단기 1~5일:
  파생시장·프로그램 30, 외국인·기관 수급 25, 기술·거래량 20,
  환율·글로벌 15, 뉴스·공시 10
- 중기 1~8주:
  분기 실적 25, 산업 선행지표 25, 누적수급 15,
  환율·금리·거시 15, 가격추세 10, 뉴스·공시 10
- 장기 6~18개월:
  향후 이익 방향 30, 산업 사이클 25, 가치평가·안전마진 20,
  경쟁력·시장점유율 10, 현금흐름·재무안전성 10,
  주주환원·지배구조 5

현재 수집되지 않은 요소는 임의로 추정하지 않고 0점(중립) 처리한다.
데이터 커버리지는 별도 신뢰도에 반영하며, 상승확률은 신뢰도에 따라
50% 방향으로 축소한다.
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
        return float(str(value).replace(",", ""))
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
    """
    점수와 상승확률을 분리한다.

    신뢰도가 낮으면 50% 쪽으로 강하게 축소하며,
    최종 확률은 20~80% 범위로 제한한다.
    """
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

    # 총 가중치 100, 총신호 -100~100을 종합점수 0~100으로 변환
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


def supply_signal(market):
    supply = market.get("수급", {}) or {}

    foreign_net = safe_float(supply.get("외국인순매수"))
    institution_net = safe_float(supply.get("기관순매수"))
    individual_net = safe_float(supply.get("개인순매수"))
    volume = safe_float(market.get("거래량"))

    combined = foreign_net + institution_net

    if volume <= 0:
        ratio = 0.0
    else:
        ratio = combined / volume

    # 거래량 대비 외국인+기관 순매수 10%에서 신호 ±100
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

    data_exists = (
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

    quality = 1.0 if data_exists else 0.0

    return {
        "signal": signal,
        "quality": quality,
        "foreign": foreign_net,
        "institution": institution_net,
        "individual": individual_net,
        "combined": combined,
        "ratio": ratio,
    }


def technical_signal(market):
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

    signal = normalize_signal(signal)

    required = [
        current_price > 0,
        open_price > 0,
        high_price > 0,
        low_price > 0,
        volume > 0,
    ]
    quality = sum(required) / len(required)

    return {
        "signal": signal,
        "quality": quality,
        "change_rate": change_rate,
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
            "revenue_growth": revenue_growth,
            "operating_growth": operating_growth,
            "net_income_growth": net_income_growth,
        }

    revenue_component = clamp(revenue_growth / 30.0 * 35.0, -35.0, 35.0)
    operating_component = clamp(operating_growth / 50.0 * 40.0, -40.0, 40.0)
    net_component = clamp(net_income_growth / 40.0 * 25.0, -25.0, 25.0)

    signal = normalize_signal(
        revenue_component
        + operating_component
        + net_component
    )

    # 현재 데이터는 3년 성장률이므로 분기실적/향후이익의 대용지표에 불과함
    quality = (present / 3.0) * 0.60

    return {
        "signal": signal,
        "quality": quality,
        "revenue_growth": revenue_growth,
        "operating_growth": operating_growth,
        "net_income_growth": net_income_growth,
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
        components.append(clamp((roe - 8.0) / 12.0 * 100.0, -100.0, 100.0))

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

    if not components:
        quality_business = 0.0
        quality_level = 0.0
    else:
        quality_business = sum(components) / len(components)
        quality_level = min(len(components) / 3.0, 1.0) * 0.70

    if debt_ratio == 0:
        safety_signal = 0.0
        safety_quality = 0.0
    else:
        safety_signal = clamp((100.0 - debt_ratio) / 70.0 * 100.0, -100.0, 100.0)
        safety_quality = 0.50

    return {
        "business_signal": normalize_signal(quality_business),
        "business_quality": quality_level,
        "safety_signal": normalize_signal(safety_signal),
        "safety_quality": safety_quality,
        "roe": roe,
        "operating_margin": operating_margin,
        "debt_ratio": debt_ratio,
        "buffett_score": buffett_score,
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


def calculate_short_term(market):
    reasons = []

    supply = supply_signal(market)
    technical = technical_signal(market)

    if supply["signal"] >= 60:
        add_reason(reasons, "외국인·기관 순매수가 거래량 대비 매우 강함")
    elif supply["signal"] >= 20:
        add_reason(reasons, "외국인·기관 수급이 우호적")
    elif supply["signal"] <= -60:
        add_reason(reasons, "외국인·기관 순매도가 거래량 대비 매우 강함")
    elif supply["signal"] <= -20:
        add_reason(reasons, "외국인·기관 수급이 비우호적")

    if supply["combined"] > 0 and supply["individual"] < 0:
        add_reason(reasons, "개인 매도 물량을 외국인·기관이 흡수")

    if technical["signal"] >= 60:
        add_reason(reasons, "단기 가격 모멘텀이 매우 강함")
    elif technical["signal"] >= 20:
        add_reason(reasons, "단기 가격 흐름이 상승")
    elif technical["signal"] <= -60:
        add_reason(reasons, "단기 가격 모멘텀이 매우 약함")
    elif technical["signal"] <= -20:
        add_reason(reasons, "단기 가격 흐름이 하락")

    factors = [
        build_factor(
            "파생시장·프로그램",
            SHORT_WEIGHTS["파생시장·프로그램"],
            source="미수집",
            note="선물·옵션·프로그램매매 데이터 연결 전",
        ),
        build_factor(
            "외국인·기관수급",
            SHORT_WEIGHTS["외국인·기관수급"],
            signal=supply["signal"],
            quality=supply["quality"],
            source="KIS 투자자별 매매",
            note=(
                "외국인+기관 합산 "
                f"{supply['combined']:.0f}주, "
                f"거래량 대비 {supply['ratio'] * 100:.3f}%"
            ),
        ),
        build_factor(
            "기술·거래량",
            SHORT_WEIGHTS["기술·거래량"],
            signal=technical["signal"],
            quality=technical["quality"],
            source="KIS 현재가",
            note=f"당일 등락률 {technical['change_rate']:.2f}%",
        ),
        build_factor(
            "환율·글로벌",
            SHORT_WEIGHTS["환율·글로벌"],
            source="미수집",
            note="환율·미국지수·반도체지수 연결 전",
        ),
        build_factor(
            "뉴스·공시",
            SHORT_WEIGHTS["뉴스·공시"],
            source="미수집",
            note="뉴스·DART 공시 이벤트 분석 연결 전",
        ),
    ]

    return finalize_prediction(
        "1~5일",
        factors,
        reasons,
    )


def calculate_mid_term(market, financial):
    reasons = []

    earnings = earnings_signal(financial)
    supply = supply_signal(market)
    technical = technical_signal(market)

    if earnings["signal"] >= 60:
        add_reason(reasons, "매출·영업이익·순이익 성장 흐름이 강함")
    elif earnings["signal"] >= 20:
        add_reason(reasons, "재무 성장 흐름이 양호")
    elif earnings["signal"] <= -20:
        add_reason(reasons, "재무 성장 흐름이 약함")

    if supply["signal"] >= 20:
        add_reason(reasons, "현재 외국인·기관 수급이 우호적")
    elif supply["signal"] <= -20:
        add_reason(reasons, "현재 외국인·기관 수급이 비우호적")

    factors = [
        build_factor(
            "분기실적",
            MID_WEIGHTS["분기실적"],
            signal=earnings["signal"],
            quality=earnings["quality"],
            source="DART 3년 성장률 대용",
            note="실제 분기 전년동기·전분기 비교 데이터 연결 필요",
        ),
        build_factor(
            "산업선행지표",
            MID_WEIGHTS["산업선행지표"],
            source="미수집",
            note="산업 수주·재고·가격·설비투자 연결 전",
        ),
        build_factor(
            "누적수급",
            MID_WEIGHTS["누적수급"],
            signal=supply["signal"],
            quality=supply["quality"] * 0.35,
            source="KIS 당일 수급 대용",
            note="20일·60일 누적수급 연결 전이므로 품질 감점",
        ),
        build_factor(
            "환율·금리·거시",
            MID_WEIGHTS["환율·금리·거시"],
            source="미수집",
            note="원달러·국채금리·거시엔진 연결 전",
        ),
        build_factor(
            "가격추세",
            MID_WEIGHTS["가격추세"],
            signal=technical["signal"],
            quality=technical["quality"] * 0.30,
            source="KIS 당일 가격 대용",
            note="20일·60일 이동평균과 변동성 연결 전",
        ),
        build_factor(
            "뉴스·공시",
            MID_WEIGHTS["뉴스·공시"],
            source="미수집",
            note="실적발표·수주·증설·규제 이벤트 연결 전",
        ),
    ]

    return finalize_prediction(
        "1~8주",
        factors,
        reasons,
    )


def calculate_long_term(financial, valuation):
    reasons = []

    earnings = earnings_signal(financial)
    quality = quality_signal(financial)
    value = valuation_signal(valuation)

    if earnings["signal"] >= 60:
        add_reason(reasons, "과거 이익 성장 방향이 강함")
    elif earnings["signal"] <= -20:
        add_reason(reasons, "과거 이익 성장 방향이 약함")

    if value["signal"] >= 40:
        add_reason(reasons, "적정가 대비 안전마진이 존재")
    elif value["signal"] <= -40:
        add_reason(reasons, "현재 가격의 고평가 부담이 큼")

    if quality["business_signal"] >= 40:
        add_reason(reasons, "ROE·영업이익률·기업 품질이 양호")
    elif quality["business_signal"] <= -20:
        add_reason(reasons, "기업 경쟁력 지표가 약함")

    if quality["safety_signal"] >= 40:
        add_reason(reasons, "부채비율 기준 재무안전성이 높음")
    elif quality["safety_signal"] <= -20:
        add_reason(reasons, "부채비율 기준 재무위험이 높음")

    factors = [
        build_factor(
            "향후이익방향",
            LONG_WEIGHTS["향후이익방향"],
            signal=earnings["signal"],
            quality=earnings["quality"],
            source="DART 과거 성장률 대용",
            note="향후 컨센서스 없이 과거 성장률만 사용하므로 품질 감점",
        ),
        build_factor(
            "산업사이클",
            LONG_WEIGHTS["산업사이클"],
            source="미수집",
            note="산업 선행예측 엔진 연결 전",
        ),
        build_factor(
            "가치평가·안전마진",
            LONG_WEIGHTS["가치평가·안전마진"],
            signal=value["signal"],
            quality=value["quality"],
            source="내부 가치평가",
            note=(
                f"현재가 대비 {value['gap']:.2f}%, "
                f"판단 {value['judgment']}"
            ),
        ),
        build_factor(
            "경쟁력·시장점유율",
            LONG_WEIGHTS["경쟁력·시장점유율"],
            signal=quality["business_signal"],
            quality=quality["business_quality"],
            source="ROE·영업이익률·버핏점수 대용",
            note="실제 시장점유율과 경쟁사 비교 연결 필요",
        ),
        build_factor(
            "현금흐름·재무안전성",
            LONG_WEIGHTS["현금흐름·재무안전성"],
            signal=quality["safety_signal"],
            quality=quality["safety_quality"],
            source="부채비율 대용",
            note="영업현금흐름·FCF·순현금 연결 필요",
        ),
        build_factor(
            "주주환원·지배구조",
            LONG_WEIGHTS["주주환원·지배구조"],
            source="미수집",
            note="배당·자사주·지배구조 데이터 연결 전",
        ),
    ]

    return finalize_prediction(
        "6~18개월",
        factors,
        reasons,
    )


def predict_stock(market, financial, value):
    short_term = calculate_short_term(market)
    mid_term = calculate_mid_term(market, financial)
    long_term = calculate_long_term(financial, value)

    supply = market.get("수급", {}) or {}

    return {
        "엔진버전": "3.0.0-fixed-weights",
        "단기1~5일": short_term,
        "중기1~8주": mid_term,
        "장기6~18개월": long_term,
        "데이터완전성": {
            "KIS가격": bool(safe_float(market.get("현재가"))),
            "KIS수급": any(
                safe_float(supply.get(key)) != 0
                for key in (
                    "외국인순매수",
                    "기관순매수",
                    "개인순매수",
                )
            ),
            "DART재무": bool(financial.get("재무지표")),
            "DART성장": bool(financial.get("성장지표")),
            "가치평가": bool(value),
            "파생시장": False,
            "산업선행지표": False,
            "거시환경": False,
            "뉴스공시": False,
        },
        "주의": (
            "미수집 요소는 추정하지 않고 중립 처리한다. "
            "상승확률은 데이터 커버리지에 따라 50% 방향으로 축소된 모델 확률이다."
        ),
    }
