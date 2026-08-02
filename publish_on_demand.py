"""Publish every generated Korean stock result into data/latest.

General-company financial lookup mode.

This module does not judge whether a company is investable and does not block
publication because valuation, EPS, TTM, current price, technical observations,
or financial periods are unavailable.  It publishes every readable stock JSON
so GAS can display the financial data that was actually collected and mark
unavailable fields as unavailable.

Only irrecoverable file-system/JSON corruption prevents publication.
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
    safe_dict,
    stock_code_of,
)

KST = timezone(timedelta(hours=9))
PUBLISH_MODE = "general-company-financial-unrestricted-v1"


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
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return value


def load_json_strict(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise RuntimeError(f"게시할 JSON 파일이 없습니다: {path}")

    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        raise RuntimeError(
            f"게시할 JSON을 읽을 수 없습니다: {type(error).__name__}: {error}"
        ) from error

    if not isinstance(value, dict):
        raise RuntimeError("게시할 JSON 최상위 값이 객체가 아닙니다.")

    return value


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


def normalize_stock_code(value: Any, fallback: str = "") -> str:
    text = "".join(character for character in str(value or "") if character.isdigit())
    if len(text) == 6 and text != "000000":
        return text

    fallback_text = "".join(
        character for character in str(fallback or "") if character.isdigit()
    )
    if len(fallback_text) == 6 and fallback_text != "000000":
        return fallback_text

    return ""


def stock_code_for(stock: Dict[str, Any], fallback: str = "") -> str:
    return normalize_stock_code(
        stock_code_of(stock)
        or stock.get("KIS종목코드")
        or stock.get("종목코드"),
        fallback,
    )


def horizon_score(prediction, key):
    return safe_float(safe_dict(prediction.get(key)).get("점수"), 50.0)


def build_row(
    stock: Dict[str, Any],
    batch: str = "on_demand",
    fallback_code: str = "",
) -> Dict[str, Any]:
    prediction = safe_dict(stock.get("주가예측"))
    financial = safe_dict(stock.get("재무분석"))
    buffett = safe_dict(financial.get("버핏평가"))
    valuation = safe_dict(stock.get("가치평가"))
    bridge = safe_dict(stock.get("화면브리지"))

    short_score = horizon_score(prediction, "단기1~5일")
    medium_score = horizon_score(prediction, "중기1~8주")
    long_score = horizon_score(prediction, "장기6~18개월")
    buffett_score = safe_float(buffett.get("점수"))

    valuation_usable = (
        valuation.get("최종값사용가능") is True
        and str(valuation.get("산출상태") or "") == "정상"
        and safe_float(valuation.get("기본적정가")) > 0
    )

    gap = safe_float(valuation.get("현재가대비")) if valuation_usable else 0.0
    value_score = (
        max(0.0, min(100.0, 50.0 + gap))
        if valuation_usable
        else 50.0
    )

    composite = (
        long_score * 0.35
        + medium_score * 0.25
        + short_score * 0.15
        + buffett_score * 0.15
        + value_score * 0.10
    )

    qualification = safe_dict(valuation.get("데이터자격검사"))

    return {
        "전체순위": 0,
        "종합순위": 0,
        "기업명": str(stock.get("기업명", "")),
        "종목코드": stock_code_for(stock, fallback_code),
        "산업코드": str(stock.get("산업코드", "none")),
        "배치": batch,
        "종합선별점수": round(composite, 2),
        "단기점수": round(short_score, 2),
        "중기점수": round(medium_score, 2),
        "장기점수": round(long_score, 2),
        "버핏점수": round(buffett_score, 2),
        "가치점수": round(value_score, 2),
        "저평가후보": (
            valuation_usable
            and gap > 0
            and "고평가" not in str(valuation.get("판단", ""))
        ),
        "가치평가사용가능": valuation_usable,
        "가치평가자격상태": qualification.get("상태", "자료부족"),
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


def scan_stock_files(
    stock_root: Path,
    recent_code: str = "",
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Include every readable six-digit stock JSON in the active index."""

    active: List[Dict[str, Any]] = []
    excluded: List[Dict[str, Any]] = []

    for path in sorted(
        stock_root.glob("[0-9][0-9][0-9][0-9][0-9][0-9].json")
    ):
        try:
            stock = json.loads(path.read_text(encoding="utf-8"))
        except Exception as error:
            excluded.append({
                "종목코드": path.stem,
                "기업명": "",
                "엔진버전": "",
                "제외사유": [
                    f"JSON 손상: {type(error).__name__}: {error}"
                ],
                "파일": path.name,
            })
            continue

        if not isinstance(stock, dict):
            excluded.append({
                "종목코드": path.stem,
                "기업명": "",
                "엔진버전": "",
                "제외사유": ["JSON 최상위 값이 객체가 아님"],
                "파일": path.name,
            })
            continue

        row = build_row(
            stock,
            "on_demand" if path.stem == recent_code else "published",
            fallback_code=path.stem,
        )
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


def rebuild_latest_index(
    latest_root: Path,
    recent_stock: Dict[str, Any] | None = None,
    recent_code: str = "",
) -> Dict[str, Any]:
    stock_root = latest_root / "stocks"
    stock_root.mkdir(parents=True, exist_ok=True)

    normalized_recent_code = normalize_stock_code(
        recent_code,
        stock_code_for(recent_stock or {}),
    )

    rows, excluded = scan_stock_files(
        stock_root,
        normalized_recent_code,
    )

    generated_at = datetime.now(KST).isoformat()
    index = load_json(latest_root / "index.json", {})
    if not isinstance(index, dict):
        index = {}

    bridge = safe_dict((recent_stock or {}).get("화면브리지"))
    recent_path = (
        stock_root / f"{normalized_recent_code}.json"
        if normalized_recent_code
        else None
    )
    recent_checksum = (
        file_sha256(recent_path)
        if recent_path and recent_path.exists()
        else ""
    )

    index.update({
        "버전": "1.5.0",
        "피드스키마버전": "2.0",
        "게시모드": PUBLISH_MODE,
        "생성시각": generated_at,
        "상태": "WARNING" if excluded else "PASS",
        "상태설명": (
            f"손상된 JSON {len(excluded)}개만 제외했습니다. "
            "재무·적정가·EPS·현재가·차트 자료부족은 제외 조건이 아닙니다."
            if excluded
            else (
                "모든 읽기 가능한 종목 JSON을 활성 피드에 포함했습니다. "
                "재무·적정가·EPS·현재가·차트 자료부족은 게시를 차단하지 않습니다."
            )
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
                "가치평가자격상태": item.get(
                    "가치평가자격상태",
                    "자료부족",
                ),
                "가치평가엔진버전": item.get(
                    "가치평가엔진버전",
                    "",
                ),
                "산업프로필버전": item.get(
                    "산업프로필버전",
                    "",
                ),
                "가치평가모형개정버전": item.get(
                    "가치평가모형개정버전",
                    "",
                ),
                "유효재무기준분기키": item.get(
                    "유효재무기준분기키",
                    0,
                ),
                "파일SHA256": item.get("파일SHA256", ""),
            }
            for item in rows
        ],
    })

    if recent_stock:
        prediction = safe_dict(recent_stock.get("주가예측"))
        valuation = safe_dict(recent_stock.get("가치평가"))

        index["최근갱신종목"] = {
            "종목코드": normalized_recent_code,
            "기업명": recent_stock.get("기업명", ""),
            "엔진버전": prediction.get("엔진버전", ""),
            "화면브리지스키마": bridge.get("스키마버전", ""),
            "화면브리지상태": bridge.get("연결상태", ""),
            "가치평가사용가능": (
                valuation.get("최종값사용가능") is True
                and str(valuation.get("산출상태") or "") == "정상"
                and safe_float(valuation.get("기본적정가")) > 0
            ),
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
    stock = load_json_strict(source_path)

    # The workflow names the output file with the requested six-digit code.
    # Use that filename as the canonical code so missing valuation/contract data
    # can never prevent general-company publication.
    stock_code = normalize_stock_code(
        source_path.stem,
        stock_code_for(stock),
    )

    if not stock_code:
        raise RuntimeError(
            "종목코드를 결정할 수 없습니다. 출력 파일명은 6자리 종목코드여야 합니다."
        )

    stock_root = latest_root / "stocks"
    latest_stock_path = stock_root / f"{stock_code}.json"
    atomic_copy(source_path, latest_stock_path)

    checksum = file_sha256(latest_stock_path)
    index = rebuild_latest_index(
        latest_root,
        recent_stock=stock,
        recent_code=stock_code,
    )

    valuation = safe_dict(stock.get("가치평가"))
    qualification = safe_dict(valuation.get("데이터자격검사"))
    stop_reasons = qualification.get("중단사유")
    if not isinstance(stop_reasons, list):
        stop_reasons = []

    print("ON-DEMAND PUBLISH RESULT")
    print("- 게시모드:", PUBLISH_MODE)
    print("- 종목코드:", stock_code)
    print("- 결과: PASS")
    print("- 일반기업 재무조회: 조건 없이 게시")
    print(
        "- 가치평가:",
        "사용가능"
        if valuation.get("최종값사용가능") is True
        else "산출보류 또는 자료부족",
    )
    if stop_reasons:
        print(
            "- 가치평가 자료부족 사유:",
            "; ".join(str(item) for item in stop_reasons),
        )
    print("- 활성 최신피드 종목:", index.get("종목수", 0))
    print("- 손상 JSON 제외:", index.get("제외종목수", 0))
    print("- 인덱스 상태:", index.get("상태", ""))
    print(
        "- 엔진버전:",
        safe_dict(stock.get("주가예측")).get("엔진버전", ""),
    )
    print(
        "- 화면브리지:",
        safe_dict(stock.get("화면브리지")).get("스키마버전", ""),
    )
    print("- SHA256:", checksum)
    print("LATEST_STOCK_FILE=" + str(latest_stock_path))
    print("LATEST_INDEX_FILE=" + str(latest_root / "index.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
