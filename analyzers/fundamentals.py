"""
OpenDART 실적·현금흐름·주주환원 분석기 V1

출력 신호
- 분기실적신호: 중기 25점 요소용
- 향후이익방향대용신호: 장기 30점 요소의 대용지표
- 현금흐름재무안전성신호: 장기 10점 요소용
- 주주환원신호: 장기 5점 요소용

신호 범위는 -100~100이며,
데이터 품질은 0~100으로 별도 출력한다.
"""

from typing import Any, Dict, Iterable, List, Optional, Tuple


def safe_text(
    value: Any,
    default: str = "",
) -> str:
    if value is None:
        return default

    return str(value).strip()


def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    try:
        if value in (None, ""):
            return default

        text = (
            str(value)
            .replace(",", "")
            .replace(" ", "")
            .strip()
        )

        if text in {
            "-",
            "--",
            "N/A",
            "nan",
            "None",
        }:
            return default

        if text.startswith("(") and text.endswith(")"):
            text = "-" + text[1:-1]

        return float(text)

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


def growth_rate(
    current: float,
    previous: float,
) -> float:
    if previous == 0:
        return 0.0

    return (
        (current / abs(previous))
        - (1.0 if previous > 0 else -1.0)
    ) * 100.0


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


def get_periods(
    bundle: Dict[str, Any],
) -> List[Dict[str, Any]]:
    financials = bundle.get(
        "재무기간",
        {},
    )

    if not isinstance(
        financials,
        dict,
    ):
        return []

    periods = financials.get(
        "기간목록",
        [],
    )

    if not isinstance(
        periods,
        list,
    ):
        return []

    return [
        item
        for item in periods
        if isinstance(item, dict)
        and item.get("수집상태") == "정상"
    ]


def period_metrics(
    period: Dict[str, Any],
) -> Dict[str, Any]:
    metrics = period.get(
        "지표",
        {},
    )

    if isinstance(metrics, dict):
        return metrics

    return {}


def find_same_report_prior_year(
    latest: Dict[str, Any],
    periods: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    target_year = int(
        safe_float(
            latest.get("사업연도")
        )
    ) - 1

    target_code = safe_text(
        latest.get("보고서코드")
    )

    for period in periods:
        if (
            int(
                safe_float(
                    period.get(
                        "사업연도"
                    )
                )
            )
            == target_year
            and safe_text(
                period.get(
                    "보고서코드"
                )
            )
            == target_code
        ):
            return period

    return None


def latest_annual_period(
    periods: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    annuals = [
        period
        for period in periods
        if period.get(
            "보고서코드"
        )
        == "11011"
    ]

    if not annuals:
        return None

    return max(
        annuals,
        key=lambda item: int(
            safe_float(
                item.get(
                    "사업연도"
                )
            )
        ),
    )


def analyze_earnings(
    periods: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not periods:
        return {
            "신호": 0.0,
            "데이터품질": 0,
            "판정": "중립",
            "설명": (
                "비교할 재무기간이 없습니다."
            ),
        }

    latest = periods[0]
    previous = find_same_report_prior_year(
        latest,
        periods,
    )

    latest_metrics = period_metrics(
        latest
    )

    if previous is None:
        revenue = safe_float(
            latest_metrics.get("매출")
        )
        operating_profit = safe_float(
            latest_metrics.get(
                "영업이익"
            )
        )
        net_income = safe_float(
            latest_metrics.get("순이익")
        )

        margin = (
            operating_profit
            / revenue
            * 100.0
            if revenue != 0
            else 0.0
        )

        signal = clamp(
            margin / 20.0 * 50.0,
            -50.0,
            50.0,
        )

        return {
            "신호": round(signal, 2),
            "데이터품질": 35,
            "판정": signal_label(signal),
            "최신기간": {
                "사업연도": latest.get(
                    "사업연도"
                ),
                "보고서명": latest.get(
                    "보고서명"
                ),
            },
            "전년동기비교": False,
            "영업이익률": round(
                margin,
                2,
            ),
            "설명": (
                "전년 동기 자료가 없어 "
                "최신 영업이익률만 대용했습니다."
            ),
        }

    previous_metrics = period_metrics(
        previous
    )

    revenue_growth = growth_rate(
        safe_float(
            latest_metrics.get("매출")
        ),
        safe_float(
            previous_metrics.get("매출")
        ),
    )

    operating_growth = growth_rate(
        safe_float(
            latest_metrics.get(
                "영업이익"
            )
        ),
        safe_float(
            previous_metrics.get(
                "영업이익"
            )
        ),
    )

    net_growth = growth_rate(
        safe_float(
            latest_metrics.get("순이익")
        ),
        safe_float(
            previous_metrics.get("순이익")
        ),
    )

    latest_revenue = safe_float(
        latest_metrics.get("매출")
    )
    latest_operating = safe_float(
        latest_metrics.get(
            "영업이익"
        )
    )

    latest_margin = (
        latest_operating
        / latest_revenue
        * 100.0
        if latest_revenue != 0
        else 0.0
    )

    signal = (
        clamp(
            revenue_growth / 20.0 * 25.0,
            -25.0,
            25.0,
        )
        + clamp(
            operating_growth / 40.0 * 45.0,
            -45.0,
            45.0,
        )
        + clamp(
            net_growth / 40.0 * 20.0,
            -20.0,
            20.0,
        )
        + clamp(
            latest_margin / 20.0 * 10.0,
            -10.0,
            10.0,
        )
    )

    signal = clamp(
        signal,
        -100.0,
        100.0,
    )

    return {
        "신호": round(signal, 2),
        "데이터품질": 90,
        "판정": signal_label(signal),
        "최신기간": {
            "사업연도": latest.get(
                "사업연도"
            ),
            "보고서명": latest.get(
                "보고서명"
            ),
        },
        "비교기간": {
            "사업연도": previous.get(
                "사업연도"
            ),
            "보고서명": previous.get(
                "보고서명"
            ),
        },
        "전년동기비교": True,
        "매출증가율": round(
            revenue_growth,
            2,
        ),
        "영업이익증가율": round(
            operating_growth,
            2,
        ),
        "순이익증가율": round(
            net_growth,
            2,
        ),
        "영업이익률": round(
            latest_margin,
            2,
        ),
        "설명": (
            "같은 보고서 코드의 전년 동기와 "
            "매출·영업이익·순이익을 비교했습니다."
        ),
    }


def analyze_cash_flow(
    periods: List[Dict[str, Any]],
) -> Dict[str, Any]:
    target = latest_annual_period(
        periods
    )

    if target is None and periods:
        target = periods[0]

    if target is None:
        return {
            "신호": 0.0,
            "데이터품질": 0,
            "판정": "중립",
            "설명": (
                "현금흐름 자료가 없습니다."
            ),
        }

    metrics = period_metrics(
        target
    )

    operating_cash = safe_float(
        metrics.get(
            "영업현금흐름"
        )
    )
    free_cash_flow = safe_float(
        metrics.get(
            "잉여현금흐름추정"
        )
    )
    net_income = safe_float(
        metrics.get("순이익")
    )
    liabilities = safe_float(
        metrics.get(
            "부채총계"
        )
    )
    equity = safe_float(
        metrics.get(
            "자본총계"
        )
    )

    signal = 0.0
    available = 0

    if operating_cash != 0:
        signal += 30 if operating_cash > 0 else -45
        available += 1

    if free_cash_flow != 0:
        signal += 30 if free_cash_flow > 0 else -30
        available += 1

    if (
        operating_cash != 0
        and net_income != 0
    ):
        conversion = (
            operating_cash
            / abs(net_income)
        )

        signal += clamp(
            (conversion - 0.8)
            / 1.2
            * 25.0,
            -25.0,
            25.0,
        )
        available += 1
    else:
        conversion = 0.0

    if equity != 0:
        debt_ratio = (
            liabilities
            / equity
            * 100.0
        )

        signal += clamp(
            (100.0 - debt_ratio)
            / 100.0
            * 15.0,
            -15.0,
            15.0,
        )
        available += 1
    else:
        debt_ratio = 0.0

    signal = clamp(
        signal,
        -100.0,
        100.0,
    )

    quality = min(
        100,
        available * 25,
    )

    return {
        "신호": round(signal, 2),
        "데이터품질": quality,
        "판정": signal_label(signal),
        "기준기간": {
            "사업연도": target.get(
                "사업연도"
            ),
            "보고서명": target.get(
                "보고서명"
            ),
        },
        "영업현금흐름": operating_cash,
        "잉여현금흐름추정": free_cash_flow,
        "현금이익전환율": round(
            conversion,
            3,
        ),
        "부채비율추정": round(
            debt_ratio,
            2,
        ),
        "설명": (
            "영업현금흐름, 추정 잉여현금흐름, "
            "순이익 대비 현금전환율과 부채비율을 반영했습니다."
        ),
    }


def annual_report_rows(
    series: Dict[str, Any],
) -> List[Dict[str, Any]]:
    if not isinstance(series, dict):
        return []

    reports = series.get(
        "보고서목록",
        [],
    )

    if not isinstance(reports, list):
        return []

    return [
        report
        for report in reports
        if isinstance(report, dict)
        and report.get("수집상태") == "정상"
    ]


def find_row_value(
    rows: List[Dict[str, Any]],
    include_words: Iterable[str],
    stock_kind_words: Iterable[str] = (),
) -> float:
    include_words = tuple(
        safe_text(word)
        for word in include_words
    )
    stock_kind_words = tuple(
        safe_text(word)
        for word in stock_kind_words
    )

    candidates = []

    for row in rows:
        section = safe_text(
            row.get("se")
        )
        stock_kind = safe_text(
            row.get("stock_knd")
        )

        if not any(
            word in section
            for word in include_words
        ):
            continue

        if (
            stock_kind_words
            and stock_kind
            and not any(
                word in stock_kind
                for word in stock_kind_words
            )
        ):
            continue

        candidates.append(
            safe_float(
                row.get("thstrm")
            )
        )

    for candidate in candidates:
        if candidate != 0:
            return candidate

    return 0.0


def analyze_dividend(
    series: Dict[str, Any],
) -> Dict[str, Any]:
    reports = annual_report_rows(
        series
    )

    if not reports:
        return {
            "신호": 0.0,
            "데이터품질": 0,
            "판정": "중립",
            "설명": (
                "배당 자료가 없습니다."
            ),
        }

    latest = reports[0]
    rows = latest.get(
        "목록",
        [],
    )

    if not isinstance(rows, list):
        rows = []

    dividend_total = find_row_value(
        rows,
        (
            "현금배당금총액",
        ),
    )

    dividend_per_share = find_row_value(
        rows,
        (
            "주당현금배당금",
            "주당 현금배당금",
        ),
        (
            "보통주",
        ),
    )

    dividend_yield = find_row_value(
        rows,
        (
            "현금배당수익률",
        ),
        (
            "보통주",
        ),
    )

    payout_ratio = find_row_value(
        rows,
        (
            "현금배당성향",
        ),
    )

    signal = 0.0
    available = 0

    if dividend_total > 0:
        signal += 25
        available += 1

    if dividend_per_share > 0:
        signal += 20
        available += 1

    if dividend_yield > 0:
        signal += clamp(
            dividend_yield / 4.0 * 30.0,
            0.0,
            30.0,
        )
        available += 1

    if payout_ratio > 0:
        if payout_ratio <= 70:
            signal += clamp(
                payout_ratio / 50.0 * 25.0,
                0.0,
                25.0,
            )
        else:
            signal += max(
                0.0,
                25.0
                - (payout_ratio - 70.0),
            )

        available += 1

    signal = clamp(
        signal,
        -100.0,
        100.0,
    )

    return {
        "신호": round(signal, 2),
        "데이터품질": min(
            80,
            available * 20,
        ),
        "판정": signal_label(signal),
        "사업연도": latest.get(
            "사업연도"
        ),
        "현금배당금총액": dividend_total,
        "보통주주당배당금": (
            dividend_per_share
        ),
        "보통주배당수익률": (
            dividend_yield
        ),
        "현금배당성향": payout_ratio,
        "설명": (
            "OpenDART 배당 항목의 당기 값을 반영했습니다."
        ),
    }


def analyze_treasury(
    series: Dict[str, Any],
) -> Dict[str, Any]:
    reports = annual_report_rows(
        series
    )

    if not reports:
        return {
            "신호": 0.0,
            "데이터품질": 0,
            "판정": "중립",
            "설명": (
                "자기주식 자료가 없습니다."
            ),
        }

    latest = reports[0]
    rows = latest.get(
        "목록",
        [],
    )

    if not isinstance(rows, list):
        rows = []

    total_rows = [
        row
        for row in rows
        if isinstance(row, dict)
        and (
            "총계"
            in safe_text(
                row.get("acqs_mth3")
            )
            or "소계"
            in safe_text(
                row.get("acqs_mth3")
            )
        )
        and (
            not safe_text(
                row.get("stock_knd")
            )
            or "보통"
            in safe_text(
                row.get("stock_knd")
            )
        )
    ]

    source_rows = (
        total_rows
        if total_rows
        else [
            row
            for row in rows
            if isinstance(row, dict)
            and (
                not safe_text(
                    row.get("stock_knd")
                )
                or "보통"
                in safe_text(
                    row.get("stock_knd")
                )
            )
        ]
    )

    acquired = sum(
        safe_float(
            row.get(
                "change_qy_acqs"
            )
        )
        for row in source_rows
    )

    disposed = sum(
        safe_float(
            row.get(
                "change_qy_dsps"
            )
        )
        for row in source_rows
    )

    cancelled = sum(
        safe_float(
            row.get(
                "change_qy_incnr"
            )
        )
        for row in source_rows
    )

    ending_quantity = sum(
        safe_float(
            row.get("trmend_qy")
        )
        for row in source_rows
    )

    signal = 0.0

    if acquired > 0:
        signal += 35

    if cancelled > 0:
        signal += 45

    if disposed > acquired:
        signal -= 30

    signal = clamp(
        signal,
        -100.0,
        100.0,
    )

    quality = (
        70
        if source_rows
        else 0
    )

    return {
        "신호": round(signal, 2),
        "데이터품질": quality,
        "판정": signal_label(signal),
        "사업연도": latest.get(
            "사업연도"
        ),
        "취득수량": acquired,
        "처분수량": disposed,
        "소각수량": cancelled,
        "기말자기주식수": ending_quantity,
        "설명": (
            "자기주식 취득·처분·소각 수량을 반영했습니다."
        ),
    }


def combine_shareholder_return(
    dividend: Dict[str, Any],
    treasury: Dict[str, Any],
) -> Dict[str, Any]:
    dividend_quality = safe_float(
        dividend.get(
            "데이터품질"
        )
    )
    treasury_quality = safe_float(
        treasury.get(
            "데이터품질"
        )
    )

    dividend_signal = safe_float(
        dividend.get("신호")
    )
    treasury_signal = safe_float(
        treasury.get("신호")
    )

    weighted_quality = (
        dividend_quality * 0.65
        + treasury_quality * 0.35
    )

    effective_weight = (
        dividend_quality * 0.65
        + treasury_quality * 0.35
    )

    if effective_weight > 0:
        signal = (
            dividend_signal
            * dividend_quality
            * 0.65
            + treasury_signal
            * treasury_quality
            * 0.35
        ) / effective_weight
    else:
        signal = 0.0

    signal = clamp(
        signal,
        -100.0,
        100.0,
    )

    return {
        "신호": round(signal, 2),
        "데이터품질": round(
            weighted_quality,
            1,
        ),
        "판정": signal_label(signal),
        "배당분석": dividend,
        "자기주식분석": treasury,
    }


def analyze_fundamentals(
    bundle: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(bundle, dict):
        return {
            "분석상태": "실패",
            "분기실적": {},
            "향후이익방향대용": {},
            "현금흐름재무안전성": {},
            "주주환원": {},
        }

    periods = get_periods(
        bundle
    )

    earnings = analyze_earnings(
        periods
    )

    cash_flow = analyze_cash_flow(
        periods
    )

    dividend = analyze_dividend(
        bundle.get(
            "배당",
            {},
        )
    )

    treasury = analyze_treasury(
        bundle.get(
            "자기주식",
            {},
        )
    )

    shareholder_return = (
        combine_shareholder_return(
            dividend,
            treasury,
        )
    )

    # 컨센서스 부재 상태이므로 실제 향후이익이 아니라
    # 최신 전년동기 실적과 현금창출력을 합성한 대용 신호.
    earnings_quality = safe_float(
        earnings.get(
            "데이터품질"
        )
    )
    cash_quality = safe_float(
        cash_flow.get(
            "데이터품질"
        )
    )

    denominator = (
        earnings_quality * 0.75
        + cash_quality * 0.25
    )

    if denominator > 0:
        future_proxy_signal = (
            safe_float(
                earnings.get("신호")
            )
            * earnings_quality
            * 0.75
            + safe_float(
                cash_flow.get("신호")
            )
            * cash_quality
            * 0.25
        ) / denominator
    else:
        future_proxy_signal = 0.0

    future_proxy_signal = clamp(
        future_proxy_signal,
        -100.0,
        100.0,
    )

    future_proxy_quality = min(
        75.0,
        earnings_quality * 0.75
        + cash_quality * 0.25,
    )

    return {
        "분석상태": (
            "정상"
            if periods
            else "실패"
        ),
        "분기실적": earnings,
        "향후이익방향대용": {
            "신호": round(
                future_proxy_signal,
                2,
            ),
            "데이터품질": round(
                future_proxy_quality,
                1,
            ),
            "판정": signal_label(
                future_proxy_signal
            ),
            "설명": (
                "최신 전년동기 실적과 현금창출력을 합성한 "
                "대용지표이며 애널리스트 컨센서스는 아직 미반영입니다."
            ),
        },
        "현금흐름재무안전성": (
            cash_flow
        ),
        "주주환원": (
            shareholder_return
        ),
        "데이터출처": (
            bundle.get(
                "데이터출처",
                "금융감독원 OpenDART",
            )
        ),
    }
