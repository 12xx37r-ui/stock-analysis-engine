"""
산업 선행지표 수집기 V1

현재 지원 산업
- 반도체

반도체 구성
- 필라델피아 반도체지수: ^SOX
- VanEck Semiconductor ETF: SMH
- Micron: MU
- TSMC: TSM
- ASML: ASML
- Applied Materials: AMAT
- SK하이닉스: 000660.KS

기능
- Yahoo Chart API 1년 일봉 수집
- 5일·20일·60일·120일 변화율
- MA20·MA60·MA120
- 거래량 20일·60일 비교
- 개별 자산 실패 시 전체 중단 방지

기존 collectors.global_market의 요청·파싱 함수를 재사용한다.
main.py와 predictor.py에는 아직 연결하지 않는다.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from collectors.global_market import (
    parse_chart_result,
    request_chart,
)


KST = timezone(timedelta(hours=9))


INDUSTRY_PROFILES = {
    "semiconductor": {
        "산업명": "반도체",
        "구성자산": {
            "필라델피아반도체": {
                "symbol": "^SOX",
                "segment": "산업지수",
                "mid_weight": 20,
                "long_weight": 15,
            },
            "반도체ETF": {
                "symbol": "SMH",
                "segment": "산업ETF",
                "mid_weight": 20,
                "long_weight": 15,
            },
            "Micron": {
                "symbol": "MU",
                "segment": "메모리",
                "mid_weight": 15,
                "long_weight": 15,
            },
            "TSMC": {
                "symbol": "TSM",
                "segment": "파운드리",
                "mid_weight": 15,
                "long_weight": 15,
            },
            "ASML": {
                "symbol": "ASML",
                "segment": "노광장비",
                "mid_weight": 10,
                "long_weight": 15,
            },
            "AppliedMaterials": {
                "symbol": "AMAT",
                "segment": "반도체장비",
                "mid_weight": 10,
                "long_weight": 10,
            },
            "SK하이닉스": {
                "symbol": "000660.KS",
                "segment": "메모리·HBM",
                "mid_weight": 10,
                "long_weight": 15,
            },
        },
    },
}


INDUSTRY_ALIASES = {
    "semiconductor": "semiconductor",
    "반도체": "semiconductor",
    "memory": "semiconductor",
    "메모리": "semiconductor",
}


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


def safe_text(
    value: Any,
    default: str = "",
) -> str:
    if value is None:
        return default

    return str(value).strip()


def moving_average(
    values: List[float],
    period: int,
) -> float:
    if period <= 0 or len(values) < period:
        return 0.0

    return sum(
        values[-period:]
    ) / period


def rate_of_change(
    values: List[float],
    period: int,
) -> float:
    if period <= 0 or len(values) <= period:
        return 0.0

    previous = values[-period - 1]
    current = values[-1]

    if previous == 0:
        return 0.0

    return (
        (current / previous)
        - 1.0
    ) * 100.0


def normalize_industry(
    industry: str,
) -> str:
    key = safe_text(
        industry,
        "semiconductor",
    ).lower()

    return INDUSTRY_ALIASES.get(
        key,
        key,
    )


def extend_history_metrics(
    result: Dict[str, Any],
) -> Dict[str, Any]:
    if result.get("수집상태") != "정상":
        return result

    rows = result.get(
        "일별데이터",
        [],
    )

    if not isinstance(rows, list):
        rows = []

    closes = [
        safe_float(
            row.get("종가")
        )
        for row in rows
        if isinstance(row, dict)
        and safe_float(
            row.get("종가")
        ) > 0
    ]

    volumes = [
        safe_float(
            row.get("거래량")
        )
        for row in rows
        if isinstance(row, dict)
    ]

    latest = (
        closes[-1]
        if closes
        else 0.0
    )

    ma60 = moving_average(
        closes,
        60,
    )
    ma120 = moving_average(
        closes,
        120,
    )

    volume20 = moving_average(
        volumes,
        20,
    )
    volume60 = moving_average(
        volumes,
        60,
    )

    result.update(
        {
            "60일변화율": round(
                rate_of_change(
                    closes,
                    60,
                ),
                6,
            ),
            "120일변화율": round(
                rate_of_change(
                    closes,
                    120,
                ),
                6,
            ),
            "MA60": round(
                ma60,
                6,
            ),
            "MA120": round(
                ma120,
                6,
            ),
            "현재값대비MA60": round(
                (
                    (
                        latest
                        / ma60
                    )
                    - 1.0
                )
                * 100.0,
                6,
            )
            if ma60 > 0
            else 0.0,
            "현재값대비MA120": round(
                (
                    (
                        latest
                        / ma120
                    )
                    - 1.0
                )
                * 100.0,
                6,
            )
            if ma120 > 0
            else 0.0,
            "20일평균거래량": round(
                volume20,
                4,
            ),
            "60일평균거래량": round(
                volume60,
                4,
            ),
            "거래량비율20대60": round(
                (
                    volume20
                    / volume60
                )
                if volume60 > 0
                else 0.0,
                6,
            ),
        }
    )

    return result


def empty_asset(
    name: str,
    config: Dict[str, Any],
    message: str,
) -> Dict[str, Any]:
    return {
        "자산명": name,
        "심볼": safe_text(
            config.get("symbol")
        ),
        "산업구간": safe_text(
            config.get("segment")
        ),
        "중기가중치": safe_float(
            config.get("mid_weight")
        ),
        "장기가중치": safe_float(
            config.get("long_weight")
        ),
        "수집상태": "실패",
        "응답메시지": message,
        "데이터개수": 0,
        "현재값": 0.0,
        "5일변화율": 0.0,
        "20일변화율": 0.0,
        "60일변화율": 0.0,
        "120일변화율": 0.0,
        "MA20": 0.0,
        "MA60": 0.0,
        "MA120": 0.0,
        "현재값대비MA20": 0.0,
        "현재값대비MA60": 0.0,
        "현재값대비MA120": 0.0,
        "거래량비율20대60": 0.0,
        "데이터지연시간": 0.0,
        "일별데이터": [],
    }


def get_industry_asset(
    name: str,
    config: Dict[str, Any],
) -> Dict[str, Any]:
    symbol = safe_text(
        config.get("symbol")
    )

    try:
        data = request_chart(
            symbol=symbol,
            range_value="1y",
            interval="1d",
        )

        result = parse_chart_result(
            name=name,
            symbol=symbol,
            asset_type="industry_proxy",
            unit="index_or_price",
            data=data,
        )

        result["산업구간"] = safe_text(
            config.get("segment")
        )
        result["중기가중치"] = safe_float(
            config.get("mid_weight")
        )
        result["장기가중치"] = safe_float(
            config.get("long_weight")
        )

        return extend_history_metrics(
            result
        )

    except Exception as error:
        return empty_asset(
            name,
            config,
            (
                f"{type(error).__name__}: "
                f"{error}"
            ),
        )


def collection_status(
    assets: Dict[str, Dict[str, Any]],
) -> str:
    statuses = [
        asset.get("수집상태")
        for asset in assets.values()
    ]

    normal_count = sum(
        status == "정상"
        for status in statuses
    )

    if normal_count == len(statuses):
        return "정상"

    if normal_count > 0:
        return "부분성공"

    return "실패"


def get_industry_bundle(
    industry: str = "semiconductor",
) -> Dict[str, Any]:
    normalized = normalize_industry(
        industry
    )

    profile = INDUSTRY_PROFILES.get(
        normalized
    )

    if profile is None:
        return {
            "전체수집상태": "실패",
            "산업코드": normalized,
            "산업명": safe_text(industry),
            "응답메시지": (
                "지원하지 않는 산업입니다."
            ),
            "자산": {},
            "수집오류": [],
        }

    print(
        "REQUEST INDUSTRY:",
        profile["산업명"],
    )

    assets: Dict[
        str,
        Dict[str, Any],
    ] = {}

    for name, asset_config in profile[
        "구성자산"
    ].items():
        result = get_industry_asset(
            name,
            asset_config,
        )

        assets[name] = result

        print(
            "INDUSTRY",
            name,
            result.get("수집상태"),
            result.get("현재값"),
        )

    errors = [
        {
            "자산명": name,
            "심볼": asset.get(
                "심볼",
                "",
            ),
            "응답메시지": asset.get(
                "응답메시지",
                "",
            ),
        }
        for name, asset in assets.items()
        if asset.get(
            "수집상태"
        ) != "정상"
    ]

    return {
        "전체수집상태": collection_status(
            assets
        ),
        "산업코드": normalized,
        "산업명": profile["산업명"],
        "자산": assets,
        "수집오류": errors,
        "수집시각": datetime.now(
            KST
        ).isoformat(),
        "데이터출처": (
            "Yahoo Finance Chart API"
        ),
    }
