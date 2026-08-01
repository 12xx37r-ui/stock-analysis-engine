"""
산업 선행지표·산업 사이클 분석기 V1

입력
- collectors.industry.get_industry_bundle()
- 선택적으로 global_market_bundle

출력
- 중기산업선행: 중기 25점 요소용
- 장기산업사이클: 장기 25점 요소용
- 산업국면
- 상승 종목 비율과 상대강도

신호 범위
-100: 매우 비우호적
0: 중립
+100: 매우 우호적
"""

from typing import Any, Dict, List


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
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


def signal_label(
    signal: float,
) -> str:
    if signal >= 60:
        return "매우 긍정"
    if signal >= 20:
        return "긍정"
    if signal > -20:
        return "중립"
    if signal > -60:
        return "부정"
    return "매우 부정"


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

    if count >= 200:
        count_quality = 1.0
    elif count >= 120:
        count_quality = 0.90
    elif count >= 60:
        count_quality = 0.70
    elif count >= 20:
        count_quality = 0.45
    else:
        count_quality = 0.20

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


def mid_asset_signal(
    asset: Dict[str, Any],
) -> float:
    change5 = safe_float(
        asset.get("5일변화율")
    )
    change20 = safe_float(
        asset.get("20일변화율")
    )
    ma20_gap = safe_float(
        asset.get(
            "현재값대비MA20"
        )
    )
    ma20 = safe_float(
        asset.get("MA20")
    )
    ma60 = safe_float(
        asset.get("MA60")
    )
    volume_ratio = safe_float(
        asset.get(
            "거래량비율20대60"
        )
    )

    signal = (
        clamp(
            change5 / 8.0 * 15.0,
            -15.0,
            15.0,
        )
        + clamp(
            change20 / 20.0 * 35.0,
            -35.0,
            35.0,
        )
        + clamp(
            ma20_gap / 12.0 * 25.0,
            -25.0,
            25.0,
        )
    )

    if ma20 > 0 and ma60 > 0:
        signal += (
            15.0
            if ma20 > ma60
            else -15.0
        )

    if volume_ratio >= 1.20:
        if change20 > 0:
            signal += 10.0
        elif change20 < 0:
            signal -= 10.0

    return clamp(
        signal,
        -100.0,
        100.0,
    )


def long_asset_signal(
    asset: Dict[str, Any],
) -> float:
    change60 = safe_float(
        asset.get("60일변화율")
    )
    change120 = safe_float(
        asset.get("120일변화율")
    )
    ma120_gap = safe_float(
        asset.get(
            "현재값대비MA120"
        )
    )
    ma60 = safe_float(
        asset.get("MA60")
    )
    ma120 = safe_float(
        asset.get("MA120")
    )

    signal = (
        clamp(
            change60 / 30.0 * 25.0,
            -25.0,
            25.0,
        )
        + clamp(
            change120 / 50.0 * 35.0,
            -35.0,
            35.0,
        )
        + clamp(
            ma120_gap / 25.0 * 20.0,
            -20.0,
            20.0,
        )
    )

    if ma60 > 0 and ma120 > 0:
        signal += (
            20.0
            if ma60 > ma120
            else -20.0
        )

    return clamp(
        signal,
        -100.0,
        100.0,
    )


def weighted_result(
    assets: Dict[str, Dict[str, Any]],
    signal_function,
    weight_key: str,
) -> Dict[str, Any]:
    weighted_sum = 0.0
    effective_weight_sum = 0.0
    nominal_weight_sum = 0.0
    quality_sum = 0.0
    details: List[Dict[str, Any]] = []

    for name, asset in assets.items():
        if not isinstance(asset, dict):
            continue

        signal = signal_function(
            asset
        )
        quality = asset_quality(
            asset
        )
        weight = max(
            safe_float(
                asset.get(weight_key)
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
        effective_weight_sum += (
            effective_weight
        )
        nominal_weight_sum += weight
        quality_sum += (
            weight
            * quality
        )

        details.append(
            {
                "자산명": name,
                "심볼": asset.get(
                    "심볼",
                    "",
                ),
                "산업구간": asset.get(
                    "산업구간",
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
                "20일변화율": safe_float(
                    asset.get(
                        "20일변화율"
                    )
                ),
                "120일변화율": safe_float(
                    asset.get(
                        "120일변화율"
                    )
                ),
            }
        )

    final_signal = (
        weighted_sum
        / effective_weight_sum
        if effective_weight_sum > 0
        else 0.0
    )

    final_quality = (
        quality_sum
        / nominal_weight_sum
        if nominal_weight_sum > 0
        else 0.0
    )

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


def get_nasdaq_change20(
    global_bundle: Dict[str, Any],
) -> float:
    if not isinstance(
        global_bundle,
        dict,
    ):
        return 0.0

    assets = global_bundle.get(
        "자산",
        {},
    )

    if not isinstance(assets, dict):
        return 0.0

    nasdaq = assets.get(
        "나스닥",
        {},
    )

    if not isinstance(nasdaq, dict):
        return 0.0

    return safe_float(
        nasdaq.get("20일변화율")
    )


def industry_phase(
    mid_signal: float,
    long_signal: float,
) -> str:
    if (
        mid_signal >= 30
        and long_signal >= 30
    ):
        return "확장"

    if (
        mid_signal <= -30
        and long_signal <= -30
    ):
        return "수축"

    if (
        mid_signal < -20
        and long_signal >= 20
    ):
        return "장기상승 중 단기조정"

    if (
        mid_signal >= 20
        and long_signal < -20
    ):
        return "하락사이클 내 반등"

    if (
        mid_signal >= 10
        and long_signal >= -10
    ):
        return "회복 초기"

    if (
        mid_signal <= -10
        and long_signal <= 10
    ):
        return "둔화"

    return "중립·전환"


def analyze_industry(
    bundle: Dict[str, Any],
    global_bundle: Dict[str, Any] = None,
) -> Dict[str, Any]:
    if not isinstance(bundle, dict):
        return {
            "분석상태": "실패",
            "중기산업선행": {},
            "장기산업사이클": {},
            "산업국면": "판정불가",
        }

    assets = bundle.get(
        "자산",
        {},
    )

    if not isinstance(assets, dict):
        assets = {}

    mid = weighted_result(
        assets,
        mid_asset_signal,
        "중기가중치",
    )

    long_term = weighted_result(
        assets,
        long_asset_signal,
        "장기가중치",
    )

    valid_mid_returns = [
        safe_float(
            asset.get("20일변화율")
        )
        for asset in assets.values()
        if isinstance(asset, dict)
        and asset.get("수집상태") == "정상"
    ]

    above_ma20_count = sum(
        safe_float(
            asset.get(
                "현재값대비MA20"
            )
        ) > 0
        for asset in assets.values()
        if isinstance(asset, dict)
        and asset.get("수집상태") == "정상"
    )

    above_ma120_count = sum(
        safe_float(
            asset.get(
                "현재값대비MA120"
            )
        ) > 0
        for asset in assets.values()
        if isinstance(asset, dict)
        and asset.get("수집상태") == "정상"
    )

    valid_count = sum(
        isinstance(asset, dict)
        and asset.get("수집상태") == "정상"
        for asset in assets.values()
    )

    average_industry_return20 = (
        sum(valid_mid_returns)
        / len(valid_mid_returns)
        if valid_mid_returns
        else 0.0
    )

    nasdaq_return20 = (
        get_nasdaq_change20(
            global_bundle
        )
    )

    relative_strength = (
        average_industry_return20
        - nasdaq_return20
        if global_bundle
        else 0.0
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
            and valid_count > 0
            else "실패"
        ),
        "산업코드": bundle.get(
            "산업코드",
            "",
        ),
        "산업명": bundle.get(
            "산업명",
            "",
        ),
        "중기산업선행": {
            "신호": mid["신호"],
            "데이터품질": mid[
                "데이터품질"
            ],
            "판정": signal_label(
                mid["신호"]
            ),
            "요소별평가": mid[
                "요소별평가"
            ],
        },
        "장기산업사이클": {
            "신호": long_term[
                "신호"
            ],
            "데이터품질": long_term[
                "데이터품질"
            ],
            "판정": signal_label(
                long_term["신호"]
            ),
            "요소별평가": long_term[
                "요소별평가"
            ],
        },
        "산업국면": industry_phase(
            mid["신호"],
            long_term["신호"],
        ),
        "시장폭": {
            "정상자산개수": valid_count,
            "MA20상회비율": round(
                (
                    above_ma20_count
                    / valid_count
                    * 100.0
                )
                if valid_count > 0
                else 0.0,
                1,
            ),
            "MA120상회비율": round(
                (
                    above_ma120_count
                    / valid_count
                    * 100.0
                )
                if valid_count > 0
                else 0.0,
                1,
            ),
        },
        "상대강도": {
            "산업평균20일수익률": round(
                average_industry_return20,
                2,
            ),
            "나스닥20일수익률": round(
                nasdaq_return20,
                2,
            ),
            "나스닥대비초과수익률": round(
                relative_strength,
                2,
            ),
            "비교사용": bool(
                global_bundle
            ),
        },
        "설명": (
            "반도체 지수·ETF·메모리·파운드리·장비 대표자산의 "
            "가격추세와 시장폭을 합성한 산업 대용지표입니다."
        ),
    }
