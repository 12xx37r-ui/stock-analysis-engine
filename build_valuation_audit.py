"""Build a repository-wide valuation audit feed.

This audit never moves fair values toward market prices. It only flags stale,
misclassified, incomplete, or structurally inconsistent valuation inputs.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

KST = timezone(timedelta(hours=9))
EXPECTED_ENGINE = "6.7.0-valuation-contract-v4"
EXPECTED_CONTRACT = "4.0"
EXPECTED_PROFILE = "3.0.0"


def safe_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def safe_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return default


def load(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        return {"_load_error": f"{type(error).__name__}: {error}"}


def audit_stock(path: Path) -> Dict[str, Any]:
    stock = load(path)
    code = str(stock.get("KIS종목코드", path.stem)).zfill(6)
    company = str(stock.get("기업명", ""))
    valuation = safe_dict(stock.get("가치평가"))
    qualification = safe_dict(valuation.get("데이터자격검사"))
    market = safe_dict(stock.get("시장정보"))

    critical: List[str] = []
    warnings: List[str] = []
    if stock.get("_load_error"):
        critical.append(str(stock["_load_error"]))
    if valuation.get("가치평가엔진버전") != EXPECTED_ENGINE:
        critical.append("구형 또는 불일치 가치평가 엔진")
    if valuation.get("가치평가계약버전") != EXPECTED_CONTRACT:
        critical.append("가치평가 계약버전 불일치")
    if valuation.get("산업프로필버전") != EXPECTED_PROFILE:
        critical.append("산업 프로필 버전 불일치")
    if not qualification:
        critical.append("데이터자격검사 누락")
    elif qualification.get("통과") is not True:
        critical.extend(str(item) for item in safe_list(qualification.get("중단사유")))
    warnings.extend(str(item) for item in safe_list(qualification.get("주의사유")))

    price = safe_float(market.get("현재가"), safe_float(valuation.get("현재가")))
    base = safe_float(valuation.get("기본적정가"))
    ratio = base / price if base > 0 and price > 0 else 0.0
    if ratio and (ratio < 0.34 or ratio > 3.0):
        warnings.append("현재가와 기준 적정가 약 3배 이상 괴리")

    dispersion = safe_float(valuation.get("전체모형분산배수"))
    if dispersion >= 5.0:
        warnings.append("전체 가치모형 최대·최소 차이 5배 이상")

    if valuation.get("구조적실적가속") is True and safe_float(valuation.get("FY1성장률")) < 10.0:
        warnings.append("구조적 실적가속인데 FY1 EPS 성장률 10% 미만")

    classification_confidence = int(safe_float(valuation.get("산업분류신뢰도"), 0))
    if classification_confidence < 70:
        warnings.append(f"산업분류 신뢰도 {classification_confidence}점")

    provisional = safe_dict(valuation.get("잠정실적"))
    if provisional.get("접수번호") and provisional.get("사용가능") is not True:
        critical.append("최신 잠정실적 공시 미정량화")

    critical = list(dict.fromkeys(item for item in critical if item))
    warnings = list(dict.fromkeys(item for item in warnings if item))
    status = "FAIL" if critical else "REVIEW" if warnings else "PASS"
    return {
        "종목코드": code,
        "기업명": company,
        "상태": status,
        "최종값사용가능": valuation.get("최종값사용가능") is True,
        "현재가": price,
        "기본적정가": base,
        "현재가대비적정가배수": round(ratio, 4) if ratio else 0.0,
        "산업코드": valuation.get("가치평가산업코드", stock.get("산업코드", "")),
        "산업분류신뢰도": classification_confidence,
        "유효재무기준분기키": valuation.get("유효재무기준분기키", 0),
        "엔진버전": valuation.get("가치평가엔진버전", ""),
        "치명오류": critical,
        "주의": warnings,
        "파일": path.name,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--latest-root", default="data/latest")
    parser.add_argument("--stock-root", default="")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    latest_root = Path(args.latest_root)
    root = Path(args.stock_root) if args.stock_root else latest_root / "stocks"
    rows = [audit_stock(path) for path in sorted(root.glob("[0-9][0-9][0-9][0-9][0-9][0-9].json"))]
    summary = {
        "PASS": sum(row["상태"] == "PASS" for row in rows),
        "REVIEW": sum(row["상태"] == "REVIEW" for row in rows),
        "FAIL": sum(row["상태"] == "FAIL" for row in rows),
    }
    payload = {
        "버전": "1.0.0",
        "생성시각": datetime.now(KST).isoformat(),
        "기대엔진버전": EXPECTED_ENGINE,
        "기대계약버전": EXPECTED_CONTRACT,
        "기대산업프로필버전": EXPECTED_PROFILE,
        "종목수": len(rows),
        "요약": summary,
        "문제종목": [row for row in rows if row["상태"] != "PASS"],
        "전체감사": rows,
    }
    output = Path(args.output) if args.output else latest_root / "valuation_audit.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print("VALUATION AUDIT", summary, "=>", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
