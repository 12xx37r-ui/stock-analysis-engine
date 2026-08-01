"""
KIS 과거 데이터 수집기 V2.1

기능
1. 종목 일봉 및 기술지표
2. 투자자별 일별 수급과 5일·20일 누적수급
3. 시장 프로그램매매와 5일·20일 누적값
4. 개별 API 실패 시 전체 엔진 중단 방지
5. 수집 결과를 정상·부분성공·실패로 판정

기존 인터페이스 유지
- get_history_bundle(stock_code, market_code="K")
- main.py와 predictor.py 수정 없이 교체 가능
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Tuple

from collectors.kis import kis_request


KST = timezone(timedelta(hours=9))

SUCCESS_CODE = "0"
DEFAULT_PRICE_DAYS = 180
DEFAULT_PROGRAM_DAYS = 40


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


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default

        return int(
            float(
                str(value)
                .replace(",", "")
                .strip()
            )
        )

    except (TypeError, ValueError):
        return default


def safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default

    return str(value).strip()


def first_value(
    row: Dict[str, Any],
    keys: Iterable[str],
    default: Any = 0.0,
) -> Any:
    for key in keys:
        if key not in row:
            continue

        value = row.get(key)

        if value not in (None, ""):
            return value

    return default


def normalize_rows(value: Any) -> List[Dict[str, Any]]:
    if isinstance(value, list):
        return [
            row
            for row in value
            if isinstance(row, dict)
        ]

    if isinstance(value, dict):
        return [value]

    return []


def collect_response_rows(
    data: Dict[str, Any],
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    for key in (
        "output",
        "output1",
        "output2",
    ):
        rows.extend(
            normalize_rows(
                data.get(key)
            )
        )

    return rows


def safe_kis_request(
    tr_id: str,
    path: str,
    params: Dict[str, Any],
) -> Dict[str, Any]:
    try:
        data = kis_request(
            tr_id,
            path,
            params,
        )

        if isinstance(data, dict):
            return data

        return {
            "rt_cd": "INVALID_RESPONSE",
            "msg1": "KIS 응답이 딕셔너리가 아닙니다.",
            "output": [],
        }

    except Exception as error:
        return {
            "rt_cd": "EXCEPTION",
            "msg1": (
                f"{type(error).__name__}: "
                f"{error}"
            ),
            "output": [],
        }


def moving_average(
    values: List[float],
    period: int,
) -> float:
    if period <= 0:
        return 0.0

    if len(values) < period:
        return 0.0

    return sum(
        values[-period:]
    ) / period


def rate_of_change(
    values: List[float],
    period: int,
) -> float:
    if period <= 0:
        return 0.0

    if len(values) <= period:
        return 0.0

    previous = values[-period - 1]
    current = values[-1]

    if previous == 0:
        return 0.0

    return (
        (current / previous)
        - 1.0
    ) * 100.0


def standard_deviation(
    values: List[float],
) -> float:
    if len(values) < 2:
        return 0.0

    average = (
        sum(values)
        / len(values)
    )

    variance = sum(
        (value - average) ** 2
        for value in values
    ) / len(values)

    return variance ** 0.5


def calculate_rsi(
    closes: List[float],
    period: int = 14,
) -> float:
    if period <= 0:
        return 0.0

    if len(closes) <= period:
        return 0.0

    gains: List[float] = []
    losses: List[float] = []

    recent = closes[
        -(period + 1):
    ]

    for previous, current in zip(
        recent,
        recent[1:],
    ):
        change = current - previous

        if change > 0:
            gains.append(change)
            losses.append(0.0)
        else:
            gains.append(0.0)
            losses.append(abs(change))

    average_gain = (
        sum(gains)
        / period
    )
    average_loss = (
        sum(losses)
        / period
    )

    if average_loss == 0:
        return 100.0

    relative_strength = (
        average_gain
        / average_loss
    )

    return 100.0 - (
        100.0
        / (
            1.0
            + relative_strength
        )
    )


def response_status(
    data: Dict[str, Any],
    count: int,
) -> str:
    response_code = safe_text(
        data.get("rt_cd")
    )

    if response_code == SUCCESS_CODE:
        if count > 0:
            return "정상"

        return "데이터없음"

    if count > 0:
        return "부분성공"

    return "실패"


def empty_price_result(
    code: str = "NOT_COLLECTED",
    message: str = "",
) -> Dict[str, Any]:
    return {
        "응답상태": code,
        "응답메시지": message,
        "데이터상태": "실패",
        "데이터개수": 0,
        "최초일": "",
        "최종일": "",
        "지표": {
            "종가": 0.0,
            "MA5": 0.0,
            "MA20": 0.0,
            "MA60": 0.0,
            "종가대비MA20": 0.0,
            "종가대비MA60": 0.0,
            "5일수익률": 0.0,
            "20일수익률": 0.0,
            "60일수익률": 0.0,
            "RSI14": 0.0,
            "20일일간변동성": 0.0,
            "5일평균거래량": 0.0,
            "20일평균거래량": 0.0,
            "거래량비율5대20": 0.0,
        },
        "일봉": [],
    }


def empty_investor_result(
    code: str = "NOT_COLLECTED",
    message: str = "",
) -> Dict[str, Any]:
    return {
        "응답상태": code,
        "응답메시지": message,
        "데이터상태": "실패",
        "데이터개수": 0,
        "최초일": "",
        "최종일": "",
        "누적": {
            "외국인5일": 0.0,
            "외국인20일": 0.0,
            "기관5일": 0.0,
            "기관20일": 0.0,
            "개인5일": 0.0,
            "개인20일": 0.0,
            "외국인기관합산5일": 0.0,
            "외국인기관합산20일": 0.0,
        },
        "일별수급": [],
    }


def empty_program_result(
    market_code: str = "K",
    code: str = "NOT_COLLECTED",
    message: str = "",
) -> Dict[str, Any]:
    return {
        "시장": (
            "KOSDAQ"
            if market_code == "Q"
            else "KOSPI"
        ),
        "응답상태": code,
        "응답메시지": message,
        "데이터상태": "실패",
        "데이터개수": 0,
        "누적": {
            "프로그램순매수수량5일": 0.0,
            "프로그램순매수수량20일": 0.0,
            "프로그램순매수금액5일": 0.0,
            "프로그램순매수금액20일": 0.0,
        },
        "일별프로그램": [],
    }


def get_daily_price_history(
    stock_code: str,
    calendar_days: int = DEFAULT_PRICE_DAYS,
) -> Dict[str, Any]:
    if not safe_text(stock_code):
        return empty_price_result(
            code="INVALID_STOCK_CODE",
            message="종목코드가 비어 있습니다.",
        )

    calendar_days = max(
        safe_int(calendar_days, DEFAULT_PRICE_DAYS),
        30,
    )

    end_date = datetime.now(
        KST
    ).date()

    start_date = (
        end_date
        - timedelta(
            days=calendar_days
        )
    )

    data = safe_kis_request(
        "FHKST03010100",
        (
            "/uapi/domestic-stock/v1/"
            "quotations/"
            "inquire-daily-itemchartprice"
        ),
        {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
            "FID_INPUT_DATE_1": (
                start_date.strftime(
                    "%Y%m%d"
                )
            ),
            "FID_INPUT_DATE_2": (
                end_date.strftime(
                    "%Y%m%d"
                )
            ),
            "FID_PERIOD_DIV_CODE": "D",
            "FID_ORG_ADJ_PRC": "0",
        },
    )

    raw_rows = normalize_rows(
        data.get(
            "output2",
            [],
        )
    )

    rows_by_date: Dict[
        str,
        Dict[str, Any],
    ] = {}

    for row in raw_rows:
        date = safe_text(
            first_value(
                row,
                (
                    "stck_bsop_date",
                    "bsop_date",
                    "date",
                ),
                "",
            )
        )

        close = safe_float(
            first_value(
                row,
                (
                    "stck_clpr",
                    "stck_prpr",
                    "close",
                ),
            )
        )

        if not date or close <= 0:
            continue

        rows_by_date[date] = {
            "날짜": date,
            "종가": close,
            "시가": safe_float(
                first_value(
                    row,
                    (
                        "stck_oprc",
                        "open",
                    ),
                )
            ),
            "고가": safe_float(
                first_value(
                    row,
                    (
                        "stck_hgpr",
                        "high",
                    ),
                )
            ),
            "저가": safe_float(
                first_value(
                    row,
                    (
                        "stck_lwpr",
                        "low",
                    ),
                )
            ),
            "거래량": safe_float(
                first_value(
                    row,
                    (
                        "acml_vol",
                        "volume",
                    ),
                )
            ),
            "거래대금": safe_float(
                first_value(
                    row,
                    (
                        "acml_tr_pbmn",
                        "trade_amount",
                    ),
                )
            ),
            "등락률": safe_float(
                first_value(
                    row,
                    (
                        "prdy_ctrt",
                        "change_rate",
                    ),
                )
            ),
        }

    rows = sorted(
        rows_by_date.values(),
        key=lambda item: item["날짜"],
    )

    closes = [
        row["종가"]
        for row in rows
    ]

    volumes = [
        row["거래량"]
        for row in rows
    ]

    daily_returns: List[float] = []

    for previous, current in zip(
        closes,
        closes[1:],
    ):
        if previous <= 0:
            continue

        daily_returns.append(
            (
                (current / previous)
                - 1.0
            )
            * 100.0
        )

    ma5 = moving_average(
        closes,
        5,
    )
    ma20 = moving_average(
        closes,
        20,
    )
    ma60 = moving_average(
        closes,
        60,
    )

    latest_close = (
        closes[-1]
        if closes
        else 0.0
    )

    average_volume_5 = moving_average(
        volumes,
        5,
    )
    average_volume_20 = moving_average(
        volumes,
        20,
    )

    volume_ratio = (
        average_volume_5
        / average_volume_20
        if average_volume_20 > 0
        else 0.0
    )

    count = len(rows)

    return {
        "응답상태": safe_text(
            data.get("rt_cd")
        ),
        "응답메시지": safe_text(
            data.get("msg1")
        ),
        "데이터상태": response_status(
            data,
            count,
        ),
        "데이터개수": count,
        "최초일": (
            rows[0]["날짜"]
            if rows
            else ""
        ),
        "최종일": (
            rows[-1]["날짜"]
            if rows
            else ""
        ),
        "지표": {
            "종가": latest_close,
            "MA5": round(ma5, 4),
            "MA20": round(ma20, 4),
            "MA60": round(ma60, 4),
            "종가대비MA20": round(
                (
                    (
                        latest_close
                        / ma20
                    )
                    - 1.0
                )
                * 100.0,
                4,
            )
            if ma20 > 0
            else 0.0,
            "종가대비MA60": round(
                (
                    (
                        latest_close
                        / ma60
                    )
                    - 1.0
                )
                * 100.0,
                4,
            )
            if ma60 > 0
            else 0.0,
            "5일수익률": round(
                rate_of_change(
                    closes,
                    5,
                ),
                4,
            ),
            "20일수익률": round(
                rate_of_change(
                    closes,
                    20,
                ),
                4,
            ),
            "60일수익률": round(
                rate_of_change(
                    closes,
                    60,
                ),
                4,
            ),
            "RSI14": round(
                calculate_rsi(
                    closes,
                    14,
                ),
                4,
            ),
            "20일일간변동성": round(
                standard_deviation(
                    daily_returns[-20:]
                ),
                4,
            ),
            "5일평균거래량": round(
                average_volume_5,
                4,
            ),
            "20일평균거래량": round(
                average_volume_20,
                4,
            ),
            "거래량비율5대20": round(
                volume_ratio,
                4,
            ),
        },
        "일봉": rows,
    }


def get_investor_daily_history(
    stock_code: str,
) -> Dict[str, Any]:
    if not safe_text(stock_code):
        return empty_investor_result(
            code="INVALID_STOCK_CODE",
            message="종목코드가 비어 있습니다.",
        )

    query_date = datetime.now(
        KST
    ).strftime(
        "%Y%m%d"
    )

    data = safe_kis_request(
        "FHPTJ04160001",
        (
            "/uapi/domestic-stock/v1/"
            "quotations/"
            "investor-trade-by-stock-daily"
        ),
        {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
            "FID_INPUT_DATE_1": query_date,
            "FID_ORG_ADJ_PRC": "",
            "FID_ETC_CLS_CODE": "",
        },
    )

    raw_rows = collect_response_rows(
        data
    )

    rows_by_date: Dict[
        str,
        Dict[str, Any],
    ] = {}

    for row in raw_rows:
        date = safe_text(
            first_value(
                row,
                (
                    "stck_bsop_date",
                    "bsop_date",
                    "date",
                ),
                "",
            )
        )

        if not date:
            continue

        normalized = {
            "날짜": date,
            "외국인순매수": safe_float(
                first_value(
                    row,
                    (
                        "frgn_ntby_qty",
                        "frgn_ntby_vol",
                    ),
                )
            ),
            "기관순매수": safe_float(
                first_value(
                    row,
                    (
                        "orgn_ntby_qty",
                        "inst_ntby_qty",
                    ),
                )
            ),
            "개인순매수": safe_float(
                first_value(
                    row,
                    (
                        "prsn_ntby_qty",
                        "individual_ntby_qty",
                    ),
                )
            ),
        }

        if not any(
            normalized[key] != 0
            for key in (
                "외국인순매수",
                "기관순매수",
                "개인순매수",
            )
        ):
            continue

        rows_by_date[date] = normalized

    rows = sorted(
        rows_by_date.values(),
        key=lambda item: item["날짜"],
    )

    def cumulative(
        key: str,
        period: int,
    ) -> float:
        return sum(
            safe_float(
                row.get(key)
            )
            for row in rows[-period:]
        )

    count = len(rows)

    foreign_5 = cumulative(
        "외국인순매수",
        5,
    )
    foreign_20 = cumulative(
        "외국인순매수",
        20,
    )
    institution_5 = cumulative(
        "기관순매수",
        5,
    )
    institution_20 = cumulative(
        "기관순매수",
        20,
    )

    return {
        "응답상태": safe_text(
            data.get("rt_cd")
        ),
        "응답메시지": safe_text(
            data.get("msg1")
        ),
        "데이터상태": response_status(
            data,
            count,
        ),
        "데이터개수": count,
        "최초일": (
            rows[0]["날짜"]
            if rows
            else ""
        ),
        "최종일": (
            rows[-1]["날짜"]
            if rows
            else ""
        ),
        "누적": {
            "외국인5일": foreign_5,
            "외국인20일": foreign_20,
            "기관5일": institution_5,
            "기관20일": institution_20,
            "개인5일": cumulative(
                "개인순매수",
                5,
            ),
            "개인20일": cumulative(
                "개인순매수",
                20,
            ),
            "외국인기관합산5일": (
                foreign_5
                + institution_5
            ),
            "외국인기관합산20일": (
                foreign_20
                + institution_20
            ),
        },
        "일별수급": rows,
    }


def detect_program_net_values(
    row: Dict[str, Any],
) -> Tuple[float, float]:
    quantity_keys = (
        "whol_ntby_qty",
        "pgtr_ntby_qty",
        "total_ntby_qty",
        "ntby_qty",
    )

    amount_keys = (
        "whol_ntby_tr_pbmn",
        "pgtr_ntby_tr_pbmn",
        "total_ntby_tr_pbmn",
        "ntby_tr_pbmn",
    )

    net_quantity = safe_float(
        first_value(
            row,
            quantity_keys,
        )
    )

    net_amount = safe_float(
        first_value(
            row,
            amount_keys,
        )
    )

    if (
        net_quantity == 0
        and net_amount == 0
    ):
        for key, value in row.items():
            lowered = key.lower()

            if "ntby" not in lowered:
                continue

            numeric = safe_float(value)

            if numeric == 0:
                continue

            if (
                "qty" in lowered
                or "vol" in lowered
            ):
                net_quantity = numeric

            if (
                "pbmn" in lowered
                or "amt" in lowered
            ):
                net_amount = numeric

    return (
        net_quantity,
        net_amount,
    )


def get_program_trade_history(
    market_code: str = "K",
    calendar_days: int = DEFAULT_PROGRAM_DAYS,
) -> Dict[str, Any]:
    market_code = safe_text(
        market_code,
        "K",
    ).upper()

    if market_code not in {
        "K",
        "Q",
    }:
        market_code = "K"

    calendar_days = max(
        safe_int(
            calendar_days,
            DEFAULT_PROGRAM_DAYS,
        ),
        20,
    )

    end_date = datetime.now(
        KST
    ).date()

    start_date = (
        end_date
        - timedelta(
            days=calendar_days
        )
    )

    data = safe_kis_request(
        "FHPPG04600001",
        (
            "/uapi/domestic-stock/v1/"
            "quotations/"
            "comp-program-trade-daily"
        ),
        {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_MRKT_CLS_CODE": market_code,
            "FID_INPUT_DATE_1": (
                start_date.strftime(
                    "%Y%m%d"
                )
            ),
            "FID_INPUT_DATE_2": (
                end_date.strftime(
                    "%Y%m%d"
                )
            ),
        },
    )

    raw_rows = collect_response_rows(
        data
    )

    rows_by_date: Dict[
        str,
        Dict[str, Any],
    ] = {}

    for row in raw_rows:
        date = safe_text(
            first_value(
                row,
                (
                    "stck_bsop_date",
                    "bsop_date",
                    "date",
                ),
                "",
            )
        )

        if not date:
            continue

        (
            net_quantity,
            net_amount,
        ) = detect_program_net_values(
            row
        )

        rows_by_date[date] = {
            "날짜": date,
            "프로그램순매수수량": (
                net_quantity
            ),
            "프로그램순매수금액": (
                net_amount
            ),
        }

    rows = sorted(
        rows_by_date.values(),
        key=lambda item: item["날짜"],
    )

    count = len(rows)

    return {
        "시장": (
            "KOSDAQ"
            if market_code == "Q"
            else "KOSPI"
        ),
        "응답상태": safe_text(
            data.get("rt_cd")
        ),
        "응답메시지": safe_text(
            data.get("msg1")
        ),
        "데이터상태": response_status(
            data,
            count,
        ),
        "데이터개수": count,
        "누적": {
            "프로그램순매수수량5일": sum(
                row[
                    "프로그램순매수수량"
                ]
                for row in rows[-5:]
            ),
            "프로그램순매수수량20일": sum(
                row[
                    "프로그램순매수수량"
                ]
                for row in rows[-20:]
            ),
            "프로그램순매수금액5일": sum(
                row[
                    "프로그램순매수금액"
                ]
                for row in rows[-5:]
            ),
            "프로그램순매수금액20일": sum(
                row[
                    "프로그램순매수금액"
                ]
                for row in rows[-20:]
            ),
        },
        "일별프로그램": rows,
    }


def safe_collect(
    name: str,
    collector: Callable[[], Dict[str, Any]],
    fallback: Callable[[str, str], Dict[str, Any]],
) -> Dict[str, Any]:
    try:
        result = collector()

        if not isinstance(result, dict):
            message = (
                f"{name} 결과 형식이 "
                "딕셔너리가 아닙니다."
            )

            print(
                f"HISTORY {name} FAILED:",
                message,
            )

            return fallback(
                "INVALID_RESULT",
                message,
            )

        print(
            f"HISTORY {name}:",
            result.get(
                "데이터상태",
                "알수없음",
            ),
            result.get(
                "데이터개수",
                0,
            ),
        )

        return result

    except Exception as error:
        message = (
            f"{type(error).__name__}: "
            f"{error}"
        )

        print(
            f"HISTORY {name} EXCEPTION:",
            message,
        )

        return fallback(
            "EXCEPTION",
            message,
        )


def overall_collection_status(
    results: List[Dict[str, Any]],
) -> str:
    statuses = [
        safe_text(
            item.get(
                "데이터상태"
            )
        )
        for item in results
    ]

    normal_count = sum(
        status == "정상"
        for status in statuses
    )

    usable_count = sum(
        status in {
            "정상",
            "부분성공",
        }
        for status in statuses
    )

    if normal_count == len(results):
        return "정상"

    if usable_count > 0:
        return "부분성공"

    return "실패"


def get_history_bundle(
    stock_code: str,
    market_code: str = "K",
) -> Dict[str, Any]:
    print("REQUEST PRICE HISTORY")

    price_history = safe_collect(
        "PRICE",
        lambda: get_daily_price_history(
            stock_code
        ),
        empty_price_result,
    )

    print("REQUEST INVESTOR HISTORY")

    investor_history = safe_collect(
        "INVESTOR",
        lambda: get_investor_daily_history(
            stock_code
        ),
        empty_investor_result,
    )

    print("REQUEST PROGRAM HISTORY")

    program_history = safe_collect(
        "PROGRAM",
        lambda: get_program_trade_history(
            market_code=market_code
        ),
        lambda code, message: (
            empty_program_result(
                market_code=market_code,
                code=code,
                message=message,
            )
        ),
    )

    results = [
        price_history,
        investor_history,
        program_history,
    ]

    overall_status = (
        overall_collection_status(
            results
        )
    )

    errors = []

    for name, result in (
        ("가격추세", price_history),
        ("누적수급", investor_history),
        ("프로그램매매", program_history),
    ):
        if result.get(
            "데이터상태"
        ) in {
            "실패",
            "데이터없음",
        }:
            errors.append(
                {
                    "항목": name,
                    "응답상태": result.get(
                        "응답상태",
                        "",
                    ),
                    "응답메시지": result.get(
                        "응답메시지",
                        "",
                    ),
                }
            )

    print(
        "HISTORY BUNDLE:",
        overall_status,
    )

    return {
        "가격추세": price_history,
        "누적수급": investor_history,
        "프로그램매매": program_history,
        "전체수집상태": overall_status,
        "수집오류": errors,
        "수집시각": datetime.now(
            KST
        ).isoformat(),
        "데이터출처": (
            "한국투자증권 KIS"
        ),
    }
