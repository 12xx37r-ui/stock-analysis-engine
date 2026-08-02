"""Refresh already-published engine files without KIS token issuance.

This is a background cache warmer, not a prerequisite for GAS searches.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def main():
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
    print("BACKGROUND CACHE STOCKS:", len(codes))

    for code in codes:
        print("REFRESH:", code)
        subprocess.run([
            sys.executable, "main.py", "--stock-code", code,
            "--industry-code", args.industry_code,
        ], check=True)
        subprocess.run([
            sys.executable, "validate_output.py", "--file", f"output/{code}.json",
            "--stock-code", code,
        ], check=True)
        subprocess.run([
            sys.executable, "publish_on_demand.py", "--stock-file", f"output/{code}.json",
            "--latest-root", "data/latest",
        ], check=True)
        subprocess.run([
            sys.executable, "validate_published_feed.py",
            "--file", f"data/latest/stocks/{code}.json",
            "--stock-code", code,
        ], check=True)


if __name__ == "__main__":
    main()
