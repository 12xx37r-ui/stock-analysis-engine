"""Build a complete listed-company catalog without using KIS.

The catalog is deliberately lightweight.  It lets GAS resolve every listed
company immediately while deep engine files remain an optional background
cache.  OpenDART is fetched once and the result is committed under
``data/latest/universe.json``.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List

from collectors.company import get_company_list, normalize_stock_code

KST = timezone(timedelta(hours=9))
CATALOG_VERSION = "1.0.0"


def safe_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def build_catalog(force_refresh: bool = False) -> Dict[str, Any]:
    rows = get_company_list(force_refresh=force_refresh)
    companies: List[Dict[str, str]] = []
    seen = set()

    for row in rows:
        if not isinstance(row, dict):
            continue
        stock_code = normalize_stock_code(row.get("종목코드") or row.get("stock_code"))
        corp_code = safe_text(row.get("DART기업코드") or row.get("corp_code"))
        company_name = safe_text(row.get("기업명") or row.get("corp_name"))
        if not (stock_code.isdigit() and len(stock_code) == 6):
            continue
        if not (corp_code.isdigit() and len(corp_code) == 8):
            continue
        if not company_name or stock_code in seen:
            continue
        seen.add(stock_code)
        companies.append({
            "종목코드": stock_code,
            "DART기업코드": corp_code,
            "기업명": company_name,
        })

    companies.sort(key=lambda item: (item["기업명"], item["종목코드"]))
    return {
        "스키마버전": CATALOG_VERSION,
        "생성시각": datetime.now(KST).isoformat(),
        "데이터출처": "OpenDART corpCode.xml",
        "상장기업수": len(companies),
        "기업": companies,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/latest/universe.json")
    parser.add_argument("--force-refresh", action="store_true")
    args = parser.parse_args()

    payload = build_catalog(force_refresh=args.force_refresh)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if payload["상장기업수"] < 1000:
        raise SystemExit(f"상장기업 목록이 비정상적으로 적습니다: {payload['상장기업수']}")

    print("UNIVERSE CATALOG OK")
    print("- count:", payload["상장기업수"])
    print("- output:", output)


if __name__ == "__main__":
    main()
