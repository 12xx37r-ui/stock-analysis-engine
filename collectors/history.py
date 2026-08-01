"""
KIS 과거 시세·누적 수급·프로그램매매 수집기

외부 패키지 추가 없음.
기존 collectors.kis.kis_request()를 그대로 사용한다.

수집:
1) 종목 일봉 최대 100개
2) 종목별 투자자 매매동향 일별
3) 시장 프로그램매매 종합현황 일별

주의:
- 이 파일을 생성하는 단계에서는 main.py와 predictor.py에 연결하지 않는다.
- 다음 통합 단계에서 한 번에 연결한 뒤 GitHub Actions를 1회만 실행한다.
"""

from datetime import datetime, timedelta, timezone

from collectors.kis import kis_request


KST = timezone(timedelta(hours=9))


def safe_float(value, default=0.0):
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


def first_value(row, keys, default=0.0):
    for key in keys:
        if key not in row:
            continue

        value = row.get(key)

        if value not in (None, ""):
            return value

    return default


def normalize_rows(value):
    if isinstance(value, list):
        return [
            row
            for row in value
            if isinstance(row, dict)
        ]

    if isinstance(value, dict):
        return [value]

    return []


def collect_response_rows(data):
    rows = []

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


def moving_average(values, period):
    if len(values) < period:
        return 0.0

    window = values[-period:]

    return sum(window) / period


def rate_of_change(values, period):
    if len(values) <= period:
        return 0.0

    previous = values[-period - 1]
    current = values[-1]

    if previous == 0:
        return 0.0

    return (
        (current / previous) - 1.0
    ) * 100.0


def standard_deviation(values):
    if len(values) < 2:
        return 0.0

    average = sum(values) / len(values)

    variance = sum(
        (value - average) ** 2
        for value in values
    ) / len(values)

    return variance ** 0.5


def calculate_rsi(closes, period=14):
    if len(closes) <= period:
        return 0.0

    gains = []
    losses = []

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
        sum(gains) / period
    )
    average_loss = (
        sum(losses) / period
    )

    if average_loss == 0:
        return 100.0

    relative_strength = (
        average_gain / average_loss
    )

    return 100.0 - (
        100.0
        / (1.0 + relative_strength)
    )


def get_daily_price_history(
    stock_code,
    calendar_days=180,
):
    end_date = datetime.now(
        KST
    ).date()

    start_date = (
        end_date
        - timedelta(
            days=calendar_days
        )
    )

    data = kis_request(
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

    rows_by_date = {}

    for row in raw_rows:
        date = str(
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

        normalized = {
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

        rows_by_date[date] = normalized

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
        if row["거래량"] > 0
    ]

    daily_returns = []

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

    average_volume_5 = (
        moving_average(
            volumes,
            5,
        )
        if volumes
        else 0.0
    )

    average_volume_20 = (
        moving_average(
            volumes,
            20,
        )
        if volumes
        else 0.0
    )

    volume_ratio = 0.0

    if average_volume_20 > 0:
        volume_ratio = (
            average_volume_5
            / average_volume_20
        )

    return {
        "응답상태": data.get(
            "rt_cd",
            "",
        ),
        "응답메시지": data.get(
            "msg1",
            "",
        ),
        "데이터개수": len(rows),
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
            "MA5": round(
                ma5,
                4,
            ),
            "MA20": round(
                ma20,
                4,
            ),
            "MA60": round(
                ma60,
                4,
            ),
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
    stock_code,
):
    query_date = datetime.now(
        KST
    ).strftime(
        "%Y%m%d"
    )

    data = kis_request(
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

    rows_by_date = {}

    for row in raw_rows:
        date = str(
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
        key,
        period,
    ):
        return sum(
            row[key]
            for row in rows[-period:]
        )

    return {
        "응답상태": data.get(
            "rt_cd",
            "",
        ),
        "응답메시지": data.get(
            "msg1",
            "",
        ),
        "데이터개수": len(rows),
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
            "외국인5일": cumulative(
                "외국인순매수",
                5,
            ),
            "외국인20일": cumulative(
                "외국인순매수",
                20,
            ),
            "기관5일": cumulative(
                "기관순매수",
                5,
            ),
            "기관20일": cumulative(
                "기관순매수",
                20,
            ),
            "개인5일": cumulative(
                "개인순매수",
                5,
            ),
            "개인20일": cumulative(
                "개인순매수",
                20,
            ),
            "외국인기관합산5일": (
                cumulative(
                    "외국인순매수",
                    5,
                )
                + cumulative(
                    "기관순매수",
                    5,
                )
            ),
            "외국인기관합산20일": (
                cumulative(
                    "외국인순매수",
                    20,
                )
                + cumulative(
                    "기관순매수",
                    20,
                )
            ),
        },
        "일별수급": rows,
    }


def detect_program_net_values(row):
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

            numeric = safe_float(
                value
            )

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
    market_code="K",
    calendar_days=40,
):
    end_date = datetime.now(
        KST
    ).date()

    start_date = (
        end_date
        - timedelta(
            days=calendar_days
        )
    )

    data = kis_request(
        "FHPPG04600001",
        (
            "/uapi/domestic-stock/v1/"
            "quotations/"
            "comp-program-trade-daily"
        ),
        {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_MRKT_CLS_CODE": (
                market_code
            ),
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

    rows_by_date = {}

    for row in raw_rows:
        date = str(
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

    return {
        "시장": (
            "KOSPI"
            if market_code == "K"
            else "KOSDAQ"
        ),
        "응답상태": data.get(
            "rt_cd",
            "",
        ),
        "응답메시지": data.get(
            "msg1",
            "",
        ),
        "데이터개수": len(rows),
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


def get_history_bundle(
    stock_code,
    market_code="K",
):
    print(
        "REQUEST PRICE HISTORY"
    )

    price_history = (
        get_daily_price_history(
            stock_code
        )
    )

    print(
        "REQUEST INVESTOR HISTORY"
    )

    investor_history = (
        get_investor_daily_history(
            stock_code
        )
    )

    print(
        "REQUEST PROGRAM HISTORY"
    )

    program_history = (
        get_program_trade_history(
            market_code=market_code
        )
    )

    return {
        "가격추세": price_history,
        "누적수급": investor_history,
        "프로그램매매": program_history,
        "데이터출처": (
            "한국투자증권 KIS"
        ),
    }
