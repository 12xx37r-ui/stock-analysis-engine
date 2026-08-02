"""Publish one on-demand engine result into data/latest with coherent metadata.

Only files that satisfy the current feed contract are included in the active
index.  Older stock JSON files remain on disk for the batch refresh workflow,
but they are excluded from rankings and surfaced as stale/incompatible files.
"""

import argparse
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from feed_contract import (
    EXPECTED_BRIDGE_SCHEMA,
    EXPECTED_ENGINE_VERSION,
    EXPECTED_INDUSTRY_PROFILE,
    EXPECTED_VALUATION_CONTRACT,
    EXPECTED_VALUATION_MODEL_REVISION,
    inspect_published_stock,
    safe_dict,
    safe_list,
    stock_code_of,
)

KST = timezone(timedelta(hours=9))


def safe_float(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)


def atomic_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_bytes(source.read_bytes())
    temporary.replace(target)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def horizon_score(prediction, key):
    return safe_float(safe_dict(prediction.get(key)).get("점수"), 50.0)


def build_row(stock: Dict[str, Any], batch: str = "on_demand") -> Dict[str, Any]:
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
        "종목코드": stock_code_of(stock),
        "산업코드": str(stock.get("산업코드", "none")),
        "배치": batch,
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
        "가치평가모형개정버전": valuation.get("가치평가모형개정버전", ""),
        "산업분류신뢰도": valuation.get("산업분류신뢰도", 0),
        "정식재무기준분기키": valuation.get("정식재무기준분기키", 0),
        "유효재무기준분기키": valuation.get("유효재무기준분기키", 0),
        "잠정실적반영": valuation.get("TTM잠정실적반영") is True,
        "생성시각": stock.get("생성시각", ""),
        "엔진버전": prediction.get("엔진버전", ""),
        "화면브리지스키마": bridge.get("스키마버전", ""),
        "화면브리지상태": bridge.get("연결상태", ""),
    }


def scan_stock_files(stock_root: Path, recent_code: str = "") -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    active: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []
    for path in sorted(stock_root.glob("[0-9][0-9][0-9][0-9][0-9][0-9].json")):
        stock = load_json(path, {})
        compatible, reasons = inspect_published_stock(stock, path.stem)
        if not compatible:
            valuation = safe_dict(stock.get("가치평가"))
            prediction = safe_dict(stock.get("주가예측"))
            excluded.append({
                "종목코드": path.stem,
                "기업명": str(stock.get("기업명", "")),
                "엔진버전": valuation.get("가치평가엔진버전", prediction.get("엔진버전", "")),
                "제외사유": reasons,
                "파일": path.name,
            })
            continue

        row = build_row(stock, "on_demand" if path.stem == recent_code else "published")
        row["파일SHA256"] = file_sha256(path)
        active.append(row)

    active.sort(
        key=lambda item: (
            safe_float(item.get("종합선별점수")),
            safe_float(item.get("장기점수")),
            safe_float(item.get("버핏점수")),
        ),
        reverse=True,
    )
    for rank, item in enumerate(active, 1):
        item["전체순위"] = rank
        item["종합순위"] = rank
    return active, excluded


def rebuild_latest_index(latest_root: Path, recent_stock: Dict[str, Any] | None = None) -> Dict[str, Any]:
    stock_root = latest_root / "stocks"
    stock_root.mkdir(parents=True, exist_ok=True)
    recent_code = stock_code_of(recent_stock or {}) if recent_stock else ""
    rows, excluded = scan_stock_files(stock_root, recent_code)
    generated_at = datetime.now(KST).isoformat()

    index = load_json(latest_root / "index.json", {})
    bridge = safe_dict((recent_stock or {}).get("화면브리지"))
    recent_path = stock_root / f"{recent_code}.json" if recent_code else None
    recent_checksum = file_sha256(recent_path) if recent_path and recent_path.exists() else ""

    index.update({
        "버전": "1.4.0",
        "피드스키마버전": "2.0",
        "생성시각": generated_at,
        "상태": "WARNING" if excluded else "PASS",
        "상태설명": (
            f"구형·불일치 종목파일 {len(excluded)}개를 활성 인덱스에서 제외했습니다."
            if excluded else "모든 활성 종목파일이 현재 게시 계약과 일치합니다."
        ),
        "최근실행배치": "on_demand" if recent_stock else "rebuild",
        "전체파일수": len(rows) + len(excluded),
        "종목수": len(rows),
        "제외종목수": len(excluded),
        "제외종목": excluded,
        "기대엔진버전": EXPECTED_ENGINE_VERSION,
        "기대가치평가계약버전": EXPECTED_VALUATION_CONTRACT,
        "기대산업프로필버전": EXPECTED_INDUSTRY_PROFILE,
        "기대가치평가모형개정버전": EXPECTED_VALUATION_MODEL_REVISION,
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
                "가치평가모형개정버전": item.get("가치평가모형개정버전", ""),
                "유효재무기준분기키": item.get("유효재무기준분기키", 0),
                "파일SHA256": item.get("파일SHA256", ""),
            }
            for item in rows
        ],
    })

    if recent_stock:
        index["최근갱신종목"] = {
            "종목코드": recent_code,
            "기업명": recent_stock.get("기업명", ""),
            "엔진버전": safe_dict(recent_stock.get("주가예측")).get("엔진버전", ""),
            "화면브리지스키마": bridge.get("스키마버전", ""),
            "화면브리지상태": bridge.get("연결상태", ""),
            "생성시각": recent_stock.get("생성시각", ""),
            "파일SHA256": recent_checksum,
        }

    write_json(latest_root / "index.json", index)
    return index


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stock-file", required=True)
    parser.add_argument("--latest-root", default="data/latest")
    args = parser.parse_args()

    source_path = Path(args.stock_file)
    latest_root = Path(args.latest_root)
    stock = load_json(source_path, {})
    stock_code = stock_code_of(stock)

    compatible, reasons = inspect_published_stock(stock, stock_code)
    if not compatible:
        raise RuntimeError("게시 계약 검증 실패: " + "; ".join(reasons))

    valuation = safe_dict(stock.get("가치평가"))
    qualification = safe_dict(valuation.get("데이터자격검사"))
    if valuation.get("최종값사용가능") is not True or valuation.get("산출상태") != "정상":
        stop_reasons = safe_list(qualification.get("중단사유"))
        detail = "; ".join(str(item) for item in stop_reasons) or "가치평가 데이터 자격 미통과"
        raise RuntimeError(
            "게시 차단: OpenDART/재무자료가 불완전한 결과로 기존 정상 피드를 덮어쓰지 않습니다. "
            + detail
        )

    stock_root = latest_root / "stocks"
    latest_stock_path = stock_root / f"{stock_code}.json"
    atomic_copy(source_path, latest_stock_path)
    checksum = file_sha256(latest_stock_path)
    index = rebuild_latest_index(latest_root, stock)

    print("ON-DEMAND PUBLISH RESULT")
    print("- 종목코드:", stock_code)
    print("- 활성 최신피드 종목:", index.get("종목수", 0))
    print("- 제외된 구형파일:", index.get("제외종목수", 0))
    print("- 인덱스 상태:", index.get("상태", ""))
    print("- 엔진버전:", safe_dict(stock.get("주가예측")).get("엔진버전", ""))
    print("- 화면브리지:", safe_dict(stock.get("화면브리지")).get("스키마버전", ""))
    print("- SHA256:", checksum)
    print("LATEST_STOCK_FILE=" + str(latest_stock_path))
    print("LATEST_INDEX_FILE=" + str(latest_root / "index.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
