"""Refresh already-published engine files with one reusable KIS token per batch.

When GitHub repository secrets KIS_APP_KEY and KIS_APP_SECRET are present,
all stocks in the batch share the same 23-hour token cache file. If the secrets
are absent, Yahoo price history remains available and KIS-only investor/program
data is reported as unavailable without aborting the batch.

This is a background cache warmer, not a prerequisite for GAS searches.
A single stock with insufficient valuation data must not abort the entire batch.
Only outputs that pass both engine-output and published-feed validation replace
an existing published cache file.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List


def run_step(command: List[str]) -> int:
    print("RUN:", " ".join(command), flush=True)
    completed = subprocess.run(command, check=False)
    return int(completed.returncode)


def restore_backup(target: Path, backup: Path | None) -> None:
    if backup and backup.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup, target)
    elif target.exists():
        target.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--industry-code", default="auto")
    args = parser.parse_args()

    stock_root = Path("data/latest/stocks")
    paths = sorted(
        stock_root.glob("[0-9][0-9][0-9][0-9][0-9][0-9].json"),
        key=lambda path: (path.stat().st_mtime, path.name),
    )
    codes = [path.stem for path in paths[: max(0, args.limit)]]
    print("BACKGROUND CACHE STOCKS:", len(codes), flush=True)

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
        backup_file = backup_root / f"{code}.json"
        backup = None

        if published_file.exists():
            shutil.copy2(published_file, backup_file)
            backup = backup_file

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
            print(
                "REFRESH SKIPPED: invalid new output; existing published cache preserved:",
                code,
                flush=True,
            )
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
            restore_backup(published_file, backup)
            print("REFRESH PUBLISH FAILED; previous cache restored:", code, flush=True)
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
            restore_backup(published_file, backup)
            print("REFRESH FEED INVALID; previous cache restored:", code, flush=True)
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

    print("\nBACKGROUND REFRESH SUMMARY", flush=True)
    print("- requested:", len(codes), flush=True)
    print("- refreshed:", len(refreshed), refreshed, flush=True)
    print("- skipped-invalid:", len(skipped), skipped, flush=True)
    print("- failed-runtime:", len(failed), failed, flush=True)

    # Background cache refresh is best-effort. Invalid new files are never published,
    # so partial data availability must not make the scheduled workflow fail.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
