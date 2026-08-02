"""멀티타임프레임·뉴스·GAS 신호 브리지 정적 검증."""

from datetime import datetime, timedelta, timezone

from collectors.news import judgment, title_score
from collectors.technical import aggregate_rows, timeframe_summary
from predictor import combined_event_signal


def build_rows(count=900):
    start = datetime(2023, 1, 2, tzinfo=timezone.utc)
    rows = []
    price = 100000.0

    for index in range(count):
        date_value = start + timedelta(days=index)
        if date_value.weekday() >= 5:
            continue

        drift = 1.0008 if index < count * 0.75 else 1.0014
        price *= drift
        rows.append(
            {
                "timestamp": int(date_value.timestamp()),
                "시각UTC": date_value.isoformat(),
                "시가": price * 0.995,
                "고가": price * 1.01,
                "저가": price * 0.99,
                "종가": price,
                "거래량": 1000000 + index * 100,
            }
        )

    return rows


def main():
    errors = []
    rows = build_rows()
    weekly = aggregate_rows(rows, "weekly")
    monthly = aggregate_rows(rows, "monthly")

    daily_summary = timeframe_summary(
        rows,
        5,
        20,
        60,
        5,
        20,
        60,
    )
    weekly_summary = timeframe_summary(
        weekly,
        4,
        13,
        26,
        4,
        13,
        26,
    )
    monthly_summary = timeframe_summary(
        monthly,
        3,
        12,
        24,
        3,
        12,
        24,
    )

    for label, summary in (
        ("일봉", daily_summary),
        ("주봉", weekly_summary),
        ("월봉", monthly_summary),
    ):
        if summary.get("available") is not True:
            errors.append(f"{label} available false")
        if not isinstance(summary.get("score"), (int, float)):
            errors.append(f"{label} score invalid")
        if summary.get("observations", 0) <= 0:
            errors.append(f"{label} observations missing")
        if summary.get("confidence", 0) <= 0:
            errors.append(f"{label} confidence missing")

    positive = title_score("사상 최대 실적과 신규 공급계약 발표")
    negative = title_score("실적 부진과 유상증자 우려")

    if positive["score"] <= 0:
        errors.append("positive news rule failed")
    if negative["score"] >= 0:
        errors.append("negative news rule failed")
    if judgment(50) != "매우 긍정":
        errors.append("news judgment failed")

    event = combined_event_signal(
        {
            "분석상태": "정상",
            "신호": 20,
            "데이터품질": 70,
        },
        {
            "분석상태": "정상",
            "신호": 40,
            "데이터품질": 80,
        },
    )

    if event.get("status") != "정상":
        errors.append("combined event status failed")
    if event.get("quality", 0) <= 0:
        errors.append("combined event quality failed")
    if not (20 <= event.get("signal", 0) <= 40):
        errors.append("combined event signal out of range")

    if errors:
        print("SIGNAL BRIDGE VALIDATION: FAIL")
        for error in errors:
            print("-", error)
        raise SystemExit(1)

    print("SIGNAL BRIDGE VALIDATION: PASS")
    print(
        "- observations:",
        len(rows),
        len(weekly),
        len(monthly),
    )
    print(
        "- scores:",
        daily_summary["score"],
        weekly_summary["score"],
        monthly_summary["score"],
    )


if __name__ == "__main__":
    main()
