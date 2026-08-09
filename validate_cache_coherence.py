"""Regression test for published-cache/index version coherence."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from build_valuation_audit import main as _unused  # import check
from publish_on_demand import rebuild_latest_index, write_json


def current_stock(code: str):
    return {
        "기업명": "CURRENT",
        "KIS종목코드": code,
        "산업코드": "electronic_components",
        "생성시각": "2026-08-02T00:00:00",
        "재무분석": {"버핏평가": {"점수": 50}},
        "주가예측": {
            "엔진버전": "6.8.0-valuation-contract-v4",
            "단기1~5일": {"점수": 50},
            "중기1~8주": {"점수": 50},
            "장기6~18개월": {"점수": 50},
        },
        "가치평가": {
            "가치평가계약버전": "4.0",
            "가치평가엔진버전": "6.8.0-valuation-contract-v4",
            "산업프로필버전": "3.0.0",
            "가치평가모형개정버전": "future-growth-v1.1.0-price-independent",
            "미래성장모형": {"버전": "1.0.0", "사용가능": False, "차단사유": ["미래성장모형 비대상 업종"], "가치": 0.0},
            "최종값사용가능": True,
            "현재가대비": 0,
            "데이터자격검사": {"통과": True, "상태": "통과", "중단사유": []},
        },
        "화면브리지": {"스키마버전": "2.0", "종목코드": code, "연결상태": "정상"},
    }


def stale_stock(code: str):
    stock = current_stock(code)
    stock["기업명"] = "STALE"
    stock["주가예측"]["엔진버전"] = "6.6.1-valuation-contract-v3"
    stock["가치평가"]["가치평가엔진버전"] = "6.6.1-valuation-contract-v3"
    stock["가치평가"]["가치평가계약버전"] = "3.0"
    stock["가치평가"]["산업프로필버전"] = ""
    stock["가치평가"].pop("가치평가모형개정버전", None)
    stock["가치평가"].pop("데이터자격검사")
    return stock


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "data/latest"
        stocks = root / "stocks"
        write_json(stocks / "009150.json", current_stock("009150"))
        write_json(stocks / "000660.json", stale_stock("000660"))
        index = rebuild_latest_index(root, current_stock("009150"), "009150")

        active = [item["종목코드"] for item in index["종목목록"]]
        assert set(active) == {"009150", "000660"}, index
        assert index["제외종목수"] == 0, index
        assert index["상태"] == "PASS", index

    print("PUBLISHED CACHE COHERENCE: PASS")
    print("- every readable company JSON remains published")
    print("- version/valuation compatibility is a display/audit state, not a publication filter")
    print("- current general-company lookup contract is preserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
