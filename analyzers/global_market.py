"""
글로벌 시장 신호 분석기 V1

입력
- collectors.global_market.get_global_market_bundle()

출력
- 단기용 글로벌 신호
- 중기용 환율·금리·거시 신호
- 데이터 품질
- 구성요소별 설명

신호 범위
-100: 매우 비우호적
0: 중립
+100: 매우 우호적
"""

from typing import Any, Dict, List


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default

        return float(
            str(value)
            .replace(",", "")
            .strip()
        )

    except (TypeError, ValueError):
        return default


def safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default

    return str(value).strip()


def clamp(
    value: float,
    minimum: float,
    maximum: float,
) -> float:
    return max(
        minimum,
        min(
            maximum,
            value,
        ),
    )


def signal_label(signal: float) -> str:
    if signal >= 60:
        return "매우 긍정"
    if signal >= 20:
        return "긍정"
    if signal > -20:
        return "중립"
    if signal > -60:
        return "부정"
    return "매우 부정"


def get_asset(
    bundle: Dict[str, Any],
    name: str,
) -> Dict[str, Any]:
    assets = bundle.get(
        "자산",
        {},
    )

    if not isinstance(assets, dict):
        return {}

    asset = assets.get(
        name,
        {},
    )

    if isinstance(asset, dict):
        return asset

    return {}


def asset_quality(
    asset: Dict[str, Any],
) -> float:
    if asset.get("수집상태") != "정상":
        return 0.0

    count = int(
        safe_float(
            asset.get("데이터개수")
        )
    )

    delay = safe_float(
        asset.get("데이터지연시간")
    )

    if count >= 40:
        count_quality = 1.0
    elif count >= 20:
        count_quality = 0.80
    elif count >= 5:
        count_quality = 0.50
    else:
        count_quality = 0.25

    if delay <= 48:
        delay_quality = 1.0
    elif delay <= 96:
        delay_quality = 0.85
    elif delay <= 168:
        delay_quality = 0.65
    else:
        delay_quality = 0.40

    return clamp(
        count_quality
        * delay_quality,
        0.0,
        1.0,
    )


def trend_signal(
    asset: Dict[str, Any],
    direction: float = 1.0,
) -> float:
    change_1 = safe_float(
        asset.get("1일변화율")
    )

    change_5 = safe_float(
        asset.get("5일변화율")
    )

    change_20 = safe_float(
        asset.get("20일변화율")
    )

    ma20_gap = safe_float(
        asset.get("현재값대비MA20")
    )

    raw = (
        clamp(
            change_1 / 3.0 * 15.0,
            -15.0,
            15.0,
        )
        + clamp(
            change_5 / 6.0 * 30.0,
            -30.0,
            30.0,
        )
        + clamp(
            change_20 / 12.0 * 35.0,
            -35.0,
            35.0,
        )
        + clamp(
            ma20_gap / 8.0 * 20.0,
            -20.0,
            20.0,
        )
    )

    return clamp(
        raw * direction,
        -100.0,
        100.0,
    )


def vix_signal(
    asset: Dict[str, Any],
) -> float:
    current = safe_float(
        asset.get("현재값")
    )

    change_5 = safe_float(
        asset.get("5일변화율")
    )

    if current <= 0:
        return 0.0

    if current < 14:
        level = 45.0
    elif current < 18:
        level = 25.0
    elif current < 22:
        level = 5.0
    elif current < 28:
        level = -25.0
    elif current < 35:
        level = -55.0
    else:
        level = -85.0

    trend = clamp(
        -change_5 / 20.0 * 30.0,
        -30.0,
        30.0,
    )

    return clamp(
        level + trend,
        -100.0,
        100.0,
    )


def usdkrw_signal(
    asset: Dict[str, Any],
) -> float:
    """
    원달러 상승은 국내 위험자산에 일반적으로 비우호적이므로 역방향.
    """
    return trend_signal(
        asset,
        direction=-1.0,
    )


def yield_signal(
    asset: Dict[str, Any],
) -> float:
    """
    미국 금리 상승은 성장주·위험자산에 비우호적이므로 역방향.
    """
    return trend_signal(
        asset,
        direction=-1.0,
    )


def weighted_signal(
    items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    weighted_sum = 0.0
    total_weight = 0.0
    quality_weighted = 0.0
    details = []

    for item in items:
        signal = safe_float(
            item.get("signal")
        )

        quality = clamp(
            safe_float(
                item.get("quality")
            ),
            0.0,
            1.0,
        )

        weight = max(
            safe_float(
                item.get("weight")
            ),
            0.0,
        )

        effective_weight = (
            weight
            * quality
        )

        weighted_sum += (
            signal
            * effective_weight
        )

        total_weight += effective_weight

        quality_weighted += (
            weight
            * quality
        )

        details.append(
            {
                "요소": item.get(
                    "name",
                    "",
                ),
                "신호": round(
                    signal,
                    2,
                ),
                "판정": signal_label(
                    signal
                ),
                "데이터품질": round(
                    quality * 100.0,
                    1,
                ),
                "가중치": weight,
                "설명": item.get(
                    "note",
                    "",
                ),
            }
        )

    if total_weight > 0:
        final_signal = (
            weighted_sum
            / total_weight
        )
    else:
        final_signal = 0.0

    nominal_weight = sum(
        max(
            safe_float(
                item.get("weight")
            ),
            0.0,
        )
        for item in items
    )

    if nominal_weight > 0:
        final_quality = (
            quality_weighted
            / nominal_weight
        )
    else:
        final_quality = 0.0

    return {
        "신호": round(
            clamp(
                final_signal,
                -100.0,
                100.0,
            ),
            2,
        ),
        "데이터품질": round(
            clamp(
                final_quality,
                0.0,
                1.0,
            )
            * 100.0,
            1,
        ),
        "요소별평가": details,
    }


def analyze_global_market(
    bundle: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(bundle, dict):
        return {
            "분석상태": "실패",
            "단기신호": 0.0,
            "단기데이터품질": 0.0,
            "중기신호": 0.0,
            "중기데이터품질": 0.0,
            "설명": (
                "글로벌 시장 수집 결과 형식이 "
                "올바르지 않습니다."
            ),
        }

    usdkrw = get_asset(
        bundle,
        "원달러",
    )
    sp500 = get_asset(
        bundle,
        "S&P500",
    )
    nasdaq = get_asset(
        bundle,
        "나스닥",
    )
    semiconductor = get_asset(
        bundle,
        "반도체지수",
    )
    vix = get_asset(
        bundle,
        "VIX",
    )
    us10y = get_asset(
        bundle,
        "미국10년물",
    )
    us5y = get_asset(
        bundle,
        "미국5년물",
    )
    us13w = get_asset(
        bundle,
        "미국13주",
    )

    short_items = [
        {
            "name": "원달러",
            "signal": usdkrw_signal(
                usdkrw
            ),
            "quality": asset_quality(
                usdkrw
            ),
            "weight": 20,
            "note": (
                f"5일 변화 "
                f"{safe_float(usdkrw.get('5일변화율')):.2f}%"
            ),
        },
        {
            "name": "S&P500",
            "signal": trend_signal(
                sp500
            ),
            "quality": asset_quality(
                sp500
            ),
            "weight": 15,
            "note": (
                f"5일 변화 "
                f"{safe_float(sp500.get('5일변화율')):.2f}%"
            ),
        },
        {
            "name": "나스닥",
            "signal": trend_signal(
                nasdaq
            ),
            "quality": asset_quality(
                nasdaq
            ),
            "weight": 20,
            "note": (
                f"5일 변화 "
                f"{safe_float(nasdaq.get('5일변화율')):.2f}%"
            ),
        },
        {
            "name": "반도체지수",
            "signal": trend_signal(
                semiconductor
            ),
            "quality": asset_quality(
                semiconductor
            ),
            "weight": 25,
            "note": (
                f"5일 변화 "
                f"{safe_float(semiconductor.get('5일변화율')):.2f}%"
            ),
        },
        {
            "name": "VIX",
            "signal": vix_signal(
                vix
            ),
            "quality": asset_quality(
                vix
            ),
            "weight": 20,
            "note": (
                f"현재 "
                f"{safe_float(vix.get('현재값')):.2f}"
            ),
        },
    ]

    mid_items = [
        {
            "name": "원달러",
            "signal": usdkrw_signal(
                usdkrw
            ),
            "quality": asset_quality(
                usdkrw
            ),
            "weight": 25,
            "note": (
                f"20일 변화 "
                f"{safe_float(usdkrw.get('20일변화율')):.2f}%"
            ),
        },
        {
            "name": "미국10년물",
            "signal": yield_signal(
                us10y
            ),
            "quality": asset_quality(
                us10y
            ),
            "weight": 25,
            "note": (
                f"20일 변화 "
                f"{safe_float(us10y.get('20일변화율')):.2f}%"
            ),
        },
        {
            "name": "미국5년물",
            "signal": yield_signal(
                us5y
            ),
            "quality": asset_quality(
                us5y
            ),
            "weight": 15,
            "note": (
                f"20일 변화 "
                f"{safe_float(us5y.get('20일변화율')):.2f}%"
            ),
        },
        {
            "name": "미국13주",
            "signal": yield_signal(
                us13w
            ),
            "quality": asset_quality(
                us13w
            ),
            "weight": 10,
            "note": (
                f"20일 변화 "
                f"{safe_float(us13w.get('20일변화율')):.2f}%"
            ),
        },
        {
            "name": "나스닥",
            "signal": trend_signal(
                nasdaq
            ),
            "quality": asset_quality(
                nasdaq
            ),
            "weight": 10,
            "note": (
                f"20일 변화 "
                f"{safe_float(nasdaq.get('20일변화율')):.2f}%"
            ),
        },
        {
            "name": "반도체지수",
            "signal": trend_signal(
                semiconductor
            ),
            "quality": asset_quality(
                semiconductor
            ),
            "weight": 15,
            "note": (
                f"20일 변화 "
                f"{safe_float(semiconductor.get('20일변화율')):.2f}%"
            ),
        },
    ]

    short_result = weighted_signal(
        short_items
    )

    mid_result = weighted_signal(
        mid_items
    )

    return {
        "분석상태": (
            "정상"
            if bundle.get(
                "전체수집상태"
            ) in {
                "정상",
                "부분성공",
            }
            else "실패"
        ),
        "단기신호": short_result[
            "신호"
        ],
        "단기판정": signal_label(
            short_result["신호"]
        ),
        "단기데이터품질": short_result[
            "데이터품질"
        ],
        "단기요소별평가": short_result[
            "요소별평가"
        ],
        "중기신호": mid_result[
            "신호"
        ],
        "중기판정": signal_label(
            mid_result["신호"]
        ),
        "중기데이터품질": mid_result[
            "데이터품질"
        ],
        "중기요소별평가": mid_result[
            "요소별평가"
        ],
        "설명": (
            "국내주식 기준으로 원달러·미국 주가지수·"
            "반도체지수·VIX·미국 금리의 방향을 "
            "-100~100 신호로 합성했습니다."
        ),
    }
