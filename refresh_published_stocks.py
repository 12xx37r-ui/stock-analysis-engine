"""Refresh already-published stock files with current engine/contract versions.

Incompatible files are refreshed first.  They remain on disk when a rebuild
fails so the next run can retry, but publish_on_demand excludes them from the
active index until they pass the current publication contract.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Tuple

from feed_contract import inspect_published_stock


def run_step(command: List[str]) -> int:
    print("RUN:", " ".join(command), flush=True)
    completed = subprocess.run(command, check=False)
    return int(completed.returncode)


def load_stock(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def compatibility_key(path: Path) -> Tuple[int, float, str]:
    stock = load_stock(path)
    compatible, _ = inspect_published_stock(stock, path.stem)
    # Incompatible files first, then oldest files first.
    return (1 if compatible else 0, path.stat().st_mtime, path.name)


def restore_file(target: Path, backup: Path | None) -> None:
    if backup and backup.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, target)
    elif target.exists():
        target.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20, help="0 이하면 기존 게시 종목 전체")
    parser.add_argument("--industry-code", default="auto")
    args = parser.parse_args()

    stock_root = Path("data/latest/stocks")
    paths = sorted(
        stock_root.glob("[0-9][0-9][0-9][0-9][0-9][0-9].json"),
        key=compatibility_key,
    )
    selected = paths if args.limit <= 0 else paths[: args.limit]
    codes = [path.stem for path in selected]
    stale_count = sum(not inspect_published_stock(load_stock(path), path.stem)[0] for path in paths)
    print("BACKGROUND CACHE STOCKS:", len(codes), flush=True)
    print("INCOMPATIBLE FILES FOUND:", stale_count, flush=True)

    backup_root = Path(".refresh_backup")
    if backup_root.exists():
        shutil.rmtree(backup_root)
    backup_root.mkdir(parents=True, exist_ok=True)

    refreshed: List[str] = []
    skipped: List[str] = []
    failed: List[str] = []

    for code in codes:
        print("\nREFRESH:", code, flush=True)
        output_file = Path("output") / f"{code}.json"
        published_file = stock_root / f"{code}.json"
        index_file = Path("data/latest/index.json")
        backup_file = backup_root / f"{code}.json"
        backup_index = backup_root / f"index-{code}.json"
        stock_backup = None
        index_backup = None

        if published_file.exists():
            shutil.copy2(published_file, backup_file)
            stock_backup = backup_file
        if index_file.exists():
            shutil.copy2(index_file, backup_index)
            index_backup = backup_index

        output_file.unlink(missing_ok=True)

        if run_step([
            sys.executable,
            "main.py",
            "--stock-code",
            code,
            "--industry-code",
            args.industry_code,
        ]) != 0:
            print("REFRESH ENGINE FAILED:", code, flush=True)
            failed.append(code)
            continue

        if run_step([
            sys.executable,
            "validate_output.py",
            "--file",
            str(output_file),
            "--stock-code",
            code,
        ]) != 0:
            print("REFRESH SKIPPED: invalid new output; stale file remains excluded:", code, flush=True)
            skipped.append(code)
            continue

        if run_step([
            sys.executable,
            "publish_on_demand.py",
            "--stock-file",
            str(output_file),
            "--latest-root",
            "data/latest",
        ]) != 0:
            restore_file(published_file, stock_backup)
            restore_file(index_file, index_backup)
            print("REFRESH PUBLISH FAILED; previous files restored:", code, flush=True)
            failed.append(code)
            continue

        if run_step([
            sys.executable,
            "validate_published_feed.py",
            "--file",
            str(published_file),
            "--stock-code",
            code,
        ]) != 0:
            restore_file(published_file, stock_backup)
            restore_file(index_file, index_backup)
            print("REFRESH FEED INVALID; previous files restored:", code, flush=True)
            failed.append(code)
            continue

        refreshed.append(code)
        print("REFRESH OK:", code, flush=True)

    shutil.rmtree(backup_root, ignore_errors=True)

    audit_rc = run_step([
        sys.executable,
        "build_valuation_audit.py",
        "--latest-root",
        "data/latest",
    ])
    if audit_rc != 0:
        print("VALUATION AUDIT BUILD FAILED", flush=True)

    index_rc = run_step([
        sys.executable,
        "validate_latest_index.py",
        "--latest-root",
        "data/latest",
    ])
    if index_rc != 0:
        print("LATEST INDEX VALIDATION FAILED", flush=True)

    print("\nBACKGROUND REFRESH SUMMARY", flush=True)
    print("- requested:", len(codes), flush=True)
    print("- refreshed:", len(refreshed), refreshed, flush=True)
    print("- skipped-invalid:", len(skipped), skipped, flush=True)
    print("- failed-runtime:", len(failed), failed, flush=True)
    print("- remaining incompatible files will stay excluded from active index", flush=True)

    # Best-effort batch. Invalid/stale files are not active in the index.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
