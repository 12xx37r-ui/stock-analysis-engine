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
    warnings = []

    if not index_path.exists():
        errors.append("index.json 없음")
        index = {}
    else:
        index = load(index_path)

    active_codes = []
    indexed_files = set()
    for item in safe_list(index.get("종목목록")):
        row = safe_dict(item)
        code = str(row.get("종목코드", "")).zfill(6)
        active_codes.append(code)
        path = stock_root / f"{code}.json"
        if not path.exists():
            errors.append(f"활성 인덱스 파일 없음: {code}")
            continue
        try:
            stock = load(path)
        except Exception as error:
            errors.append(f"활성 인덱스 JSON 손상: {code}: {type(error).__name__}: {error}")
            continue
        if not isinstance(stock, dict):
            errors.append(f"활성 인덱스 JSON 루트가 객체 아님: {code}")
            continue
        indexed_files.add(code)
        compatible, reasons = inspect_published_stock(stock, code)
        if not compatible:
            warnings.append(
                f"구형 계약·검증스키마 캐시(점진 갱신 대상): {code}: {'; '.join(reasons)}"
            )

    excluded_rows = [safe_dict(item) for item in safe_list(index.get("제외종목"))]
    excluded_codes = [str(item.get("종목코드", "")).zfill(6) for item in excluded_rows]

    # Current publication policy keeps every readable six-digit stock JSON in
    # the index. Contract/schema compatibility controls refresh priority and
    # strict validation of newly generated files; it does not hide readable
    # legacy cache files during gradual migration.
    actual_readable = []
    actual_unreadable = []
    for path in sorted(stock_root.glob("[0-9][0-9][0-9][0-9][0-9][0-9].json")):
        try:
            stock = load(path)
            if not isinstance(stock, dict):
                raise ValueError("JSON root is not object")
            actual_readable.append(path.stem)
        except Exception:
            actual_unreadable.append(path.stem)

    if len(active_codes) != len(set(active_codes)):
        errors.append("활성 인덱스 종목코드 중복")
    if len(excluded_codes) != len(set(excluded_codes)):
        errors.append("제외종목 종목코드 중복")
    if int(index.get("종목수") or 0) != len(active_codes):
        errors.append("index 종목수와 종목목록 개수 불일치")
    if int(index.get("제외종목수") or 0) != len(excluded_codes):
        errors.append("index 제외종목수와 제외종목 개수 불일치")
    if sorted(active_codes) != sorted(actual_readable):
        errors.append(
            f"읽기 가능한 실제 파일과 활성 인덱스 불일치: actual={actual_readable}, index={active_codes}"
        )
    if sorted(excluded_codes) != sorted(actual_unreadable):
        errors.append(
            f"손상/비객체 파일과 제외목록 불일치: actual={actual_unreadable}, index={excluded_codes}"
        )
    if set(active_codes) & set(excluded_codes):
        errors.append("동일 종목이 활성·제외 목록에 동시에 존재")

    audit_summary = {}
    if audit_path.exists():
        audit_summary = safe_dict(load(audit_path).get("요약"))
        fail_count = int(audit_summary.get("FAIL") or 0)
        review_count = int(audit_summary.get("REVIEW") or 0)
        status = str(index.get("상태", ""))
        # Audit is informative for general lookup; only unreadable index files
        # determine publication failure. Do not make valuation REVIEW/FAIL hide
        # a readable company JSON.
        if fail_count > 0 or review_count > 0:
            warnings.append(
                f"가치평가 감사 상태 참고: FAIL {fail_count}, REVIEW {review_count}"
            )

    if errors:
        print("LATEST INDEX VALIDATION: FAIL")
        for error in errors:
            print("-", error)
        return 1

    print("LATEST INDEX VALIDATION: PASS")
    print("- readable stocks:", len(active_codes))
    print("- unreadable excluded files:", len(excluded_codes))
    print("- contract/schema refresh targets:", len(warnings))
    print("- index status:", index.get("상태", ""))
    print("- audit summary:", audit_summary)
    if warnings:
        print("- migration note:", warnings[0])
    return 0


if __name__ == "__main__":
    sys.exit(main())
