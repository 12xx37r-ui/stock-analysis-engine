"""Build a repository-wide valuation audit feed and synchronize index status.

This audit never moves fair values toward market prices. It only flags stale,
misclassified, incomplete, or structurally inconsistent valuation inputs.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from feed_contract import (
    EXPECTED_ENGINE_VERSION,
    EXPECTED_INDUSTRY_PROFILE,
    EXPECTED_VALUATION_CONTRACT,
    EXPECTED_VALUATION_MODEL_REVISION,
    inspect_published_stock,
    safe_dict,
    safe_list,
)

KST = timezone(timedelta(hours=9))


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


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def audit_stock(path: Path) -> Dict[str, Any]:
    stock = load(path)
    code = str(stock.get("KIS종목코드", path.stem)).zfill(6)
    company = str(stock.get("기업명", ""))
    valuation = safe_dict(stock.get("가치평가"))
    qualification = safe_dict(valuation.get("데이터자격검사"))
    market = safe_dict(stock.get("시장정보"))

    compatible, contract_reasons = inspect_published_stock(stock, path.stem)
    critical: List[str] = list(contract_reasons)
    warnings: List[str] = []
    if stock.get("_load_error"):
        critical.append(str(stock["_load_error"]))
    if qualification and qualification.get("통과") is not True:
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

    future_model = safe_dict(valuation.get("미래성장모형"))
    if valuation.get("구조적실적가속") is True and safe_float(valuation.get("FY1성장률")) < 10.0:
        warnings.append("구조적 실적가속인데 FY1 EPS 성장률 10% 미만")
    if valuation.get("구조적실적가속") is True and future_model.get("사용가능") is not True:
        warnings.append("구조적 실적가속이지만 미래성장모형 미적용: " + ", ".join(str(x) for x in safe_list(future_model.get("차단사유"))))
    if future_model.get("사용가능") is True:
        if future_model.get("현재가미사용") is not True:
            critical.append("미래성장모형 현재가 비사용 보증 누락")
        if safe_float(valuation.get("미래성장가치")) <= 0:
            critical.append("미래성장모형 사용가능인데 미래성장가치 미확보")

    classification_confidence = int(safe_float(valuation.get("산업분류신뢰도"), 0))
    if compatible and classification_confidence < 70:
        warnings.append(f"산업분류 신뢰도 {classification_confidence}점")

    provisional = safe_dict(valuation.get("잠정실적"))
    if provisional.get("접수번호") and provisional.get("사용가능") is not True:
        if qualification.get("정식보고서대체평가") is True:
            warnings.append("최신 잠정실적 미정량화: 최신 정식보고서 기준 평가")
        else:
            critical.append("최신 잠정실적 공시 미정량화")

    critical = list(dict.fromkeys(item for item in critical if item))
    warnings = list(dict.fromkeys(item for item in warnings if item))
    status = "FAIL" if critical else "REVIEW" if warnings else "PASS"
    return {
        "종목코드": code,
        "기업명": company,
        "상태": status,
        "활성인덱스적격": compatible,
        "최종값사용가능": valuation.get("최종값사용가능") is True,
        "현재가": price,
        "기본적정가": base,
        "현재가대비적정가배수": round(ratio, 4) if ratio else 0.0,
        "산업코드": valuation.get("가치평가산업코드", stock.get("산업코드", "")),
        "산업분류신뢰도": classification_confidence,
        "유효재무기준분기키": valuation.get("유효재무기준분기키", 0),
        "엔진버전": valuation.get("가치평가엔진버전", ""),
        "모형개정버전": valuation.get("가치평가모형개정버전", ""),
        "치명오류": critical,
        "주의": warnings,
        "파일": path.name,
    }


def sync_index_status(index_path: Path, summary: Dict[str, int]) -> None:
    if not index_path.exists():
        return
    index = load(index_path)
    if index.get("_load_error"):
        return

    if summary["FAIL"] > 0:
        status = "WARNING"
        description = (
            f"감사 FAIL {summary['FAIL']}개는 활성 인덱스에서 제외되어 있으며 재분석이 필요합니다."
        )
    elif summary["REVIEW"] > 0:
        status = "REVIEW"
        description = f"활성 종목 중 검토 경고 {summary['REVIEW']}개가 있습니다."
    else:
        status = "PASS"
        description = "게시 종목 전체가 현재 계약과 감사 기준을 통과했습니다."

    index["상태"] = status
    index["상태설명"] = description
    index["가치평가감사요약"] = summary
    index["가치평가감사시각"] = datetime.now(KST).isoformat()
    write_json(index_path, index)


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
        "버전": "1.1.0",
        "생성시각": datetime.now(KST).isoformat(),
        "기대엔진버전": EXPECTED_ENGINE_VERSION,
        "기대계약버전": EXPECTED_VALUATION_CONTRACT,
        "기대산업프로필버전": EXPECTED_INDUSTRY_PROFILE,
        "기대모형개정버전": EXPECTED_VALUATION_MODEL_REVISION,
        "종목수": len(rows),
        "활성인덱스적격종목수": sum(row["활성인덱스적격"] for row in rows),
        "요약": summary,
        "문제종목": [row for row in rows if row["상태"] != "PASS"],
        "전체감사": rows,
    }
    output = Path(args.output) if args.output else latest_root / "valuation_audit.json"
    write_json(output, payload)
    sync_index_status(latest_root / "index.json", summary)
    print("VALUATION AUDIT", summary, "=>", output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
