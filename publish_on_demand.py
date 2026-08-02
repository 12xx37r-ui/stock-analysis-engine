"""Publish one on-demand engine result into data/latest with feed metadata."""

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))


def safe_dict(value):
    return value if isinstance(value, dict) else {}


def safe_list(value):
    return value if isinstance(value, list) else []


def safe_float(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def file_sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def horizon_score(prediction, key):
    return safe_float(
        safe_dict(prediction.get(key)).get("점수"),
        50.0,
    )


def build_row(stock):
    prediction = safe_dict(stock.get("주가예측"))
    financial = safe_dict(stock.get("재무분석"))
    buffett = safe_dict(financial.get("버핏평가"))
    valuation = safe_dict(stock.get("가치평가"))
    bridge = safe_dict(stock.get("화면브리지"))

    short_score = horizon_score(prediction, "단기1~5일")
    medium_score = horizon_score(prediction, "중기1~8주")
    long_score = horizon_score(prediction, "장기6~18개월")
    buffett_score = safe_float(buffett.get("점수"))
    valuation_usable = valuation.get("최종값사용가능") is True
    gap = safe_float(valuation.get("현재가대비")) if valuation_usable else 0.0
    value_score = max(0.0, min(100.0, 50.0 + gap)) if valuation_usable else 50.0
    composite = (
        long_score * 0.35
        + medium_score * 0.25
        + short_score * 0.15
        + buffett_score * 0.15
        + value_score * 0.10
    )

    return {
        "전체순위": 0,
        "종합순위": 0,
        "기업명": str(stock.get("기업명", "")),
        "종목코드": str(stock.get("KIS종목코드", "")).zfill(6),
        "산업코드": str(stock.get("산업코드", "none")),
        "배치": "on_demand",
        "종합선별점수": round(composite, 2),
        "단기점수": round(short_score, 2),
        "중기점수": round(medium_score, 2),
        "장기점수": round(long_score, 2),
        "버핏점수": round(buffett_score, 2),
        "가치점수": round(value_score, 2),
        "저평가후보": valuation_usable and gap > 0 and "고평가" not in str(valuation.get("판단", "")),
        "가치평가사용가능": valuation_usable,
        "가치평가자격상태": safe_dict(valuation.get("데이터자격검사")).get("상태", "미확인"),
        "가치평가계약버전": valuation.get("가치평가계약버전", ""),
        "가치평가엔진버전": valuation.get("가치평가엔진버전", ""),
        "산업프로필버전": valuation.get("산업프로필버전", ""),
        "산업분류신뢰도": valuation.get("산업분류신뢰도", 0),
        "정식재무기준분기키": valuation.get("정식재무기준분기키", 0),
        "유효재무기준분기키": valuation.get("유효재무기준분기키", 0),
        "잠정실적반영": valuation.get("TTM잠정실적반영") is True,
        "생성시각": stock.get("생성시각", ""),
        "엔진버전": prediction.get("엔진버전", ""),
        "화면브리지스키마": bridge.get("스키마버전", ""),
        "화면브리지상태": bridge.get("연결상태", ""),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stock-file", required=True)
    parser.add_argument("--latest-root", default="data/latest")
    args = parser.parse_args()

    source_path = Path(args.stock_file)
    latest_root = Path(args.latest_root)
    stock = load_json(source_path, {})
    stock_code = str(stock.get("KIS종목코드", "")).zfill(6)

    if len(stock_code) != 6 or not stock_code.isdigit():
        raise RuntimeError("종목코드 오류")

    bridge = safe_dict(stock.get("화면브리지"))
    if bridge.get("스키마버전") != "2.0":
        raise RuntimeError("화면브리지 스키마 2.0이 없습니다.")

    stock_root = latest_root / "stocks"
    stock_root.mkdir(parents=True, exist_ok=True)
    latest_stock_path = stock_root / f"{stock_code}.json"
    shutil.copy2(source_path, latest_stock_path)

    checksum = file_sha256(latest_stock_path)
    index_path = latest_root / "index.json"
    index = load_json(
        index_path,
        {
            "버전": "1.3.0",
            "배치": [],
            "종합순위": [],
            "종목목록": [],
        },
    )

    rows = [
        safe_dict(item)
        for item in safe_list(index.get("종합순위"))
        if str(safe_dict(item).get("종목코드", "")).zfill(6) != stock_code
    ]
    new_row = build_row(stock)
    new_row["파일SHA256"] = checksum
    rows.append(new_row)
    rows.sort(
        key=lambda item: (
            safe_float(item.get("종합선별점수")),
            safe_float(item.get("장기점수")),
            safe_float(item.get("버핏점수")),
        ),
        reverse=True,
    )

    for rank, item in enumerate(rows, 1):
        item["전체순위"] = rank
        item["종합순위"] = rank

    generated_at = datetime.now(KST).isoformat()
    index.update(
        {
            "버전": "1.3.0",
            "피드스키마버전": "2.0",
            "생성시각": generated_at,
            "상태": "PASS",
            "최근실행배치": "on_demand",
            "종목수": len(rows),
            "종합순위": rows,
            "종목목록": [
                {
                    "종목코드": item.get("종목코드", ""),
                    "기업명": item.get("기업명", ""),
                    "배치": item.get("배치", ""),
                    "엔진버전": item.get("엔진버전", ""),
                    "화면브리지스키마": item.get("화면브리지스키마", ""),
                    "가치평가사용가능": item.get("가치평가사용가능", False),
                    "가치평가자격상태": item.get("가치평가자격상태", "미확인"),
                    "가치평가엔진버전": item.get("가치평가엔진버전", ""),
                    "산업프로필버전": item.get("산업프로필버전", ""),
                    "유효재무기준분기키": item.get("유효재무기준분기키", 0),
                    "파일SHA256": item.get("파일SHA256", ""),
                }
                for item in rows
            ],
            "최근갱신종목": {
                "종목코드": stock_code,
                "기업명": stock.get("기업명", ""),
                "엔진버전": safe_dict(stock.get("주가예측")).get("엔진버전", ""),
                "화면브리지스키마": bridge.get("스키마버전", ""),
                "화면브리지상태": bridge.get("연결상태", ""),
                "생성시각": stock.get("생성시각", ""),
                "파일SHA256": checksum,
            },
        }
    )
    write_json(index_path, index)

    print("ON-DEMAND PUBLISH RESULT")
    print("- 종목코드:", stock_code)
    print("- 전체 최신피드 종목:", len(rows))
    print("- 엔진버전:", safe_dict(stock.get("주가예측")).get("엔진버전", ""))
    print("- 화면브리지:", bridge.get("스키마버전", ""), bridge.get("연결상태", ""))
    print("- SHA256:", checksum)
    print("LATEST_STOCK_FILE=" + str(latest_stock_path))
    print("LATEST_INDEX_FILE=" + str(index_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
