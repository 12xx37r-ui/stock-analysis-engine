import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="data/latest/universe.json")
    args = parser.parse_args()
    payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
    rows = payload.get("기업", [])
    if payload.get("스키마버전") != "1.0.0":
        raise SystemExit("universe schema mismatch")
    if not isinstance(rows, list) or len(rows) < 1000:
        raise SystemExit("universe rows insufficient")
    codes = [str(row.get("종목코드", "")) for row in rows if isinstance(row, dict)]
    if any(len(code) != 6 or not code.isdigit() for code in codes):
        raise SystemExit("invalid stock code in universe")
    if len(set(codes)) != len(codes):
        raise SystemExit("duplicate stock code in universe")
    print("UNIVERSE CATALOG VALID")
    print("- count:", len(rows))


if __name__ == "__main__":
    main()
