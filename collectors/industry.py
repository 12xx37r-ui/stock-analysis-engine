"""
산업 선행지표 수집기 V2

현재 지원 산업
- 반도체
- 전자부품·MLCC·패키지기판
- 자동차
- 2차전지
- 바이오
- 건설·인프라
- 금융

기능
- Yahoo Chart API 1년 일봉 수집
- 5일·20일·60일·120일 변화율
- MA20·MA60·MA120
- 거래량 20일·60일 비교
- 산업별 구성자산·가중치·비교시장 분리
- 개별 자산 실패 시 전체 중단 방지

collectors.global_market의 요청·파싱 함수를 재사용한다.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from collectors.global_market import (
    parse_chart_result,
    request_chart,
)


KST = timezone(timedelta(hours=9))


INDUSTRY_PROFILES = {'semiconductor': {'산업명': '반도체', '상대강도기준': '나스닥', '설명': '반도체 지수·ETF·메모리·파운드리·장비 대표자산의 가격추세와 시장폭을 합성합니다.', '구성자산': {'필라델피아반도체': {'symbol': '^SOX', 'segment': '산업지수', 'mid_weight': 20, 'long_weight': 15}, '반도체ETF': {'symbol': 'SMH', 'segment': '산업ETF', 'mid_weight': 20, 'long_weight': 15}, 'Micron': {'symbol': 'MU', 'segment': '메모리', 'mid_weight': 15, 'long_weight': 15}, 'TSMC': {'symbol': 'TSM', 'segment': '파운드리', 'mid_weight': 15, 'long_weight': 15}, 'ASML': {'symbol': 'ASML', 'segment': '노광장비', 'mid_weight': 10, 'long_weight': 15}, 'AppliedMaterials': {'symbol': 'AMAT', 'segment': '반도체장비', 'mid_weight': 10, 'long_weight': 10}, 'SK하이닉스': {'symbol': '000660.KS', 'segment': '메모리·HBM', 'mid_weight': 10, 'long_weight': 15}}}, 'electronic_components': {'산업명': '전자부품·MLCC·패키지기판', '상대강도기준': '나스닥', '설명': '글로벌 전자부품·커넥터·광학소재와 한국 대표 전자부품 기업의 가격추세를 합성합니다.', '구성자산': {'기술하드웨어ETF': {'symbol': 'IYW', 'segment': '기술하드웨어', 'mid_weight': 18, 'long_weight': 18}, 'Amphenol': {'symbol': 'APH', 'segment': '커넥터·전자부품', 'mid_weight': 18, 'long_weight': 18}, 'TEConnectivity': {'symbol': 'TEL', 'segment': '전장·커넥터', 'mid_weight': 16, 'long_weight': 16}, 'Corning': {'symbol': 'GLW', 'segment': '광학·세라믹소재', 'mid_weight': 14, 'long_weight': 14}, 'Jabil': {'symbol': 'JBL', 'segment': '전자부품·EMS', 'mid_weight': 14, 'long_weight': 14}, '삼성전기': {'symbol': '009150.KS', 'segment': 'MLCC·기판·카메라모듈', 'mid_weight': 20, 'long_weight': 20}}}, 'automotive': {'산업명': '자동차', '상대강도기준': 'S&P500', '설명': '글로벌 자동차 ETF와 주요 완성차 기업, 한국 대표 완성차의 추세를 합성합니다.', '구성자산': {'글로벌자동차ETF': {'symbol': 'CARZ', 'segment': '완성차ETF', 'mid_weight': 20, 'long_weight': 20}, '전기차자율주행ETF': {'symbol': 'DRIV', 'segment': '전기차·자율주행', 'mid_weight': 15, 'long_weight': 15}, 'Toyota': {'symbol': 'TM', 'segment': '글로벌완성차', 'mid_weight': 15, 'long_weight': 15}, 'Honda': {'symbol': 'HMC', 'segment': '글로벌완성차', 'mid_weight': 10, 'long_weight': 10}, 'GeneralMotors': {'symbol': 'GM', 'segment': '미국완성차', 'mid_weight': 10, 'long_weight': 10}, '현대차': {'symbol': '005380.KS', 'segment': '한국완성차', 'mid_weight': 15, 'long_weight': 15}, '기아': {'symbol': '000270.KS', 'segment': '한국완성차', 'mid_weight': 15, 'long_weight': 15}}}, 'battery': {'산업명': '2차전지', '상대강도기준': '나스닥', '설명': '리튬·배터리 ETF와 소재·셀·전기차 대표기업의 가격추세를 합성합니다.', '구성자산': {'리튬배터리ETF': {'symbol': 'LIT', 'segment': '리튬·배터리ETF', 'mid_weight': 20, 'long_weight': 20}, '배터리소재ETF': {'symbol': 'BATT', 'segment': '배터리소재ETF', 'mid_weight': 15, 'long_weight': 15}, 'Albemarle': {'symbol': 'ALB', 'segment': '리튬소재', 'mid_weight': 15, 'long_weight': 15}, 'Tesla': {'symbol': 'TSLA', 'segment': '전기차수요', 'mid_weight': 10, 'long_weight': 10}, 'LG에너지솔루션': {'symbol': '373220.KS', 'segment': '배터리셀', 'mid_weight': 15, 'long_weight': 15}, '삼성SDI': {'symbol': '006400.KS', 'segment': '배터리셀', 'mid_weight': 15, 'long_weight': 15}, '에코프로비엠': {'symbol': '247540.KQ', 'segment': '양극재', 'mid_weight': 10, 'long_weight': 10}}}, 'biotechnology': {'산업명': '바이오', '상대강도기준': '나스닥', '설명': '바이오 ETF·바이오 지수·글로벌 제약바이오와 한국 대표 바이오 기업의 추세를 합성합니다.', '구성자산': {'바이오ETF': {'symbol': 'XBI', 'segment': '바이오ETF', 'mid_weight': 20, 'long_weight': 20}, '나스닥바이오ETF': {'symbol': 'IBB', 'segment': '대형바이오ETF', 'mid_weight': 20, 'long_weight': 20}, '나스닥바이오지수': {'symbol': '^NBI', 'segment': '산업지수', 'mid_weight': 15, 'long_weight': 15}, 'EliLilly': {'symbol': 'LLY', 'segment': '글로벌제약', 'mid_weight': 10, 'long_weight': 10}, 'Regeneron': {'symbol': 'REGN', 'segment': '글로벌바이오', 'mid_weight': 10, 'long_weight': 10}, '삼성바이오로직스': {'symbol': '207940.KS', 'segment': 'CDMO', 'mid_weight': 15, 'long_weight': 15}, '셀트리온': {'symbol': '068270.KS', 'segment': '바이오시밀러', 'mid_weight': 10, 'long_weight': 10}}}, 'construction': {'산업명': '건설·인프라', '상대강도기준': 'S&P500', '설명': '인프라 ETF·산업재·중장비·건설장비와 한국 대표 건설·플랜트 기업의 추세를 합성합니다.', '구성자산': {'인프라개발ETF': {'symbol': 'PAVE', 'segment': '인프라ETF', 'mid_weight': 20, 'long_weight': 20}, '미국인프라ETF': {'symbol': 'IFRA', 'segment': '인프라ETF', 'mid_weight': 15, 'long_weight': 15}, '산업재ETF': {'symbol': 'XLI', 'segment': '산업재', 'mid_weight': 15, 'long_weight': 15}, 'Caterpillar': {'symbol': 'CAT', 'segment': '건설장비', 'mid_weight': 15, 'long_weight': 15}, 'UnitedRentals': {'symbol': 'URI', 'segment': '장비임대', 'mid_weight': 10, 'long_weight': 10}, '현대건설': {'symbol': '000720.KS', 'segment': '종합건설', 'mid_weight': 15, 'long_weight': 15}, '삼성E&A': {'symbol': '028050.KS', 'segment': '플랜트·EPC', 'mid_weight': 10, 'long_weight': 10}}}, 'finance': {'산업명': '금융', '상대강도기준': 'S&P500', '설명': '금융·은행 ETF와 글로벌 대형은행, 한국 대표 금융지주의 추세를 합성합니다.', '구성자산': {'미국금융ETF': {'symbol': 'XLF', 'segment': '금융ETF', 'mid_weight': 20, 'long_weight': 20}, '미국은행ETF': {'symbol': 'KBE', 'segment': '은행ETF', 'mid_weight': 15, 'long_weight': 15}, '미국지역은행ETF': {'symbol': 'KRE', 'segment': '지역은행ETF', 'mid_weight': 15, 'long_weight': 15}, 'JPMorgan': {'symbol': 'JPM', 'segment': '글로벌은행', 'mid_weight': 15, 'long_weight': 15}, 'BankOfAmerica': {'symbol': 'BAC', 'segment': '글로벌은행', 'mid_weight': 10, 'long_weight': 10}, 'KB금융': {'symbol': '105560.KS', 'segment': '한국금융지주', 'mid_weight': 15, 'long_weight': 15}, '신한지주': {'symbol': '055550.KS', 'segment': '한국금융지주', 'mid_weight': 10, 'long_weight': 10}}}}


INDUSTRY_ALIASES = {'semiconductor': 'semiconductor', '반도체': 'semiconductor', 'memory': 'semiconductor', '메모리': 'semiconductor', 'electronic_components': 'electronic_components', '전자부품': 'electronic_components', 'mlcc': 'electronic_components', '패키지기판': 'electronic_components', 'automotive': 'automotive', '자동차': 'automotive', 'auto': 'automotive', 'vehicle': 'automotive', 'battery': 'battery', '2차전지': 'battery', 'secondary_battery': 'battery', 'lithium': 'battery', 'biotechnology': 'biotechnology', 'biotech': 'biotechnology', '바이오': 'biotechnology', '제약바이오': 'biotechnology', 'construction': 'construction', '건설': 'construction', '인프라': 'construction', 'finance': 'finance', 'financial': 'finance', '금융': 'finance', '은행': 'finance'}


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
        "상대강도기준": profile.get(
            "상대강도기준",
            "S&P500",
        ),
        "설명": profile.get(
            "설명",
            "",
        ),
        "자산": assets,
        "수집오류": errors,
        "수집시각": datetime.now(
            KST
        ).isoformat(),
        "데이터출처": (
            "Yahoo Finance Chart API"
        ),
    }
