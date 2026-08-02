"""Validate coherence between data/latest/index.json, stock files, and audit."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from feed_contract import inspect_published_stock, safe_dict, safe_list


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--latest-root", default="data/latest")
    args = parser.parse_args()

    root = Path(args.latest_root)
    stock_root = root / "stocks"
    index_path = root / "index.json"
    audit_path = root / "valuation_audit.json"
    errors = []

    if not index_path.exists():
        errors.append("index.json 없음")
        index = {}
    else:
        index = load(index_path)

    active_codes = []
    for item in safe_list(index.get("종목목록")):
        row = safe_dict(item)
        code = str(row.get("종목코드", "")).zfill(6)
        active_codes.append(code)
        path = stock_root / f"{code}.json"
        if not path.exists():
            errors.append(f"활성 인덱스 파일 없음: {code}")
            continue
        compatible, reasons = inspect_published_stock(load(path), code)
        if not compatible:
            errors.append(f"활성 인덱스에 구형·불일치 파일 포함: {code}: {'; '.join(reasons)}")

    excluded_rows = [safe_dict(item) for item in safe_list(index.get("제외종목"))]
    excluded_codes = [str(item.get("종목코드", "")).zfill(6) for item in excluded_rows]

    actual_active = []
    actual_excluded = []
    for path in sorted(stock_root.glob("[0-9][0-9][0-9][0-9][0-9][0-9].json")):
        compatible, _ = inspect_published_stock(load(path), path.stem)
        (actual_active if compatible else actual_excluded).append(path.stem)

    if len(active_codes) != len(set(active_codes)):
        errors.append("활성 인덱스 종목코드 중복")
    if len(excluded_codes) != len(set(excluded_codes)):
        errors.append("제외종목 종목코드 중복")
    if int(index.get("종목수") or 0) != len(active_codes):
        errors.append("index 종목수와 종목목록 개수 불일치")
    if int(index.get("제외종목수") or 0) != len(excluded_codes):
        errors.append("index 제외종목수와 제외종목 개수 불일치")
    if sorted(active_codes) != sorted(actual_active):
        errors.append(f"실제 적격파일과 활성 인덱스 불일치: actual={actual_active}, index={active_codes}")
    if sorted(excluded_codes) != sorted(actual_excluded):
        errors.append(f"실제 비적격파일과 제외목록 불일치: actual={actual_excluded}, index={excluded_codes}")
    if set(active_codes) & set(excluded_codes):
        errors.append("동일 종목이 활성·제외 목록에 동시에 존재")

    audit_summary = {}
    if audit_path.exists():
        audit_summary = safe_dict(load(audit_path).get("요약"))
        fail_count = int(audit_summary.get("FAIL") or 0)
        review_count = int(audit_summary.get("REVIEW") or 0)
        status = str(index.get("상태", ""))
        if fail_count > 0 and status == "PASS":
            errors.append("감사 FAIL이 있는데 index 상태가 PASS")
        if fail_count == 0 and review_count > 0 and status == "PASS":
            errors.append("감사 REVIEW가 있는데 index 상태가 PASS")

    if errors:
        print("LATEST INDEX VALIDATION: FAIL")
        for error in errors:
            print("-", error)
        return 1

    print("LATEST INDEX VALIDATION: PASS")
    print("- active stocks:", len(active_codes))
    print("- excluded stale files:", len(excluded_codes))
    print("- index status:", index.get("상태", ""))
    print("- audit summary:", audit_summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
