"""Low-load analyst consensus snapshot collector.

Purpose
- Fetch one compact public consensus snapshot only when Strategic Forward actually
  has a positive future-value candidate.
- Cache per stock for 24 hours and reuse stale last-known-good data on failures.
- Never use current market price in valuation logic.
- Target price is preserved only as a market-expectation diagnostic; it is not
  used directly as fair value.

The parser intentionally uses only Python stdlib HTMLParser so no heavy dependency
is added. If the public page layout changes, the collector fails closed and the
valuation falls back to the existing no-consensus policy.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


CACHE_TTL_SECONDS = int(os.getenv("ANALYST_CONSENSUS_CACHE_TTL_SECONDS", "86400"))
STALE_IF_ERROR_SECONDS = int(os.getenv("ANALYST_CONSENSUS_STALE_IF_ERROR_SECONDS", "604800"))
CACHE_ROOT = Path(os.getenv("ANALYST_CONSENSUS_CACHE_ROOT", ".cache/analyst_consensus"))
BASE_URL = os.getenv(
    "ANALYST_CONSENSUS_BASE_URL",
    "https://kwcomp.fnguide.com/CompanyInfo/Snapshot?cmp_cd={stock_code}",
)

_MEMORY: Dict[str, Dict[str, Any]] = {}


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: List[List[List[str]]] = []
        self._table_depth = 0
        self._rows: List[List[str]] = []
        self._row: Optional[List[str]] = None
        self._cell_parts: Optional[List[str]] = None

    def handle_starttag(self, tag: str, attrs: List[Any]) -> None:
        t = tag.lower()
        if t == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._rows = []
        elif self._table_depth == 1 and t == "tr":
            self._row = []
        elif self._table_depth == 1 and t in {"td", "th"}:
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self._table_depth == 1 and self._cell_parts is not None:
            text = re.sub(r"\s+", " ", data or " ").strip()
            if text:
                self._cell_parts.append(text)

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if self._table_depth == 1 and t in {"td", "th"} and self._cell_parts is not None:
            value = " ".join(self._cell_parts).strip()
            if self._row is not None:
                self._row.append(value)
            self._cell_parts = None
        elif self._table_depth == 1 and t == "tr":
            if self._row is not None and any(cell.strip() for cell in self._row):
                self._rows.append(self._row)
            self._row = None
        elif t == "table" and self._table_depth > 0:
            if self._table_depth == 1:
                if self._rows:
                    self.tables.append(self._rows)
                self._rows = []
            self._table_depth -= 1


def _number(value: Any) -> Optional[float]:
    text = str(value or "").strip().replace(",", "").replace("%", "")
    if not text or text in {"-", "--", "N/A", "nan"}:
        return None
    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _atomic_write(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass


def _cache_path(stock_code: str) -> Path:
    return CACHE_ROOT / f"{stock_code}.json"


def _read_cache(stock_code: str) -> Dict[str, Any]:
    try:
        value = json.loads(_cache_path(stock_code).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _cache_age(record: Dict[str, Any], now: float) -> float:
    try:
        return max(0.0, now - float(record.get("fetched_at") or 0.0))
    except Exception:
        return float("inf")


def parse_consensus_html(html: str) -> Dict[str, Any]:
    parser = _TableParser()
    parser.feed(html or "")

    target_headers = {"투자의견", "목표주가", "EPS", "PER", "추정기관수"}
    for table in parser.tables:
        header_index = -1
        header: List[str] = []
        for idx, row in enumerate(table):
            joined = "|".join(row)
            if all(token in joined for token in target_headers):
                header_index = idx
                header = row
                break
        if header_index < 0:
            continue

        # Normalize duplicated/compound headers by positional matching. Snapshot's
        # consensus table is five columns in this exact business meaning even if
        # an extra first row is present.
        for row in table[header_index + 1 :]:
            nums = [_number(cell) for cell in row]
            usable = [value for value in nums if value is not None]
            if len(usable) < 5:
                continue

            # Prefer a 5-column row. If markup introduces extra cells, take the
            # last five numeric values because labels tend to be prepended.
            opinion, target_price, eps, per_value, analyst_count = usable[-5:]
            if not (1.0 <= opinion <= 5.0):
                continue
            if not (target_price and target_price > 0 and eps and eps > 0):
                continue
            if not (0 < analyst_count <= 100):
                continue
            if per_value is not None and not (0 <= per_value <= 1000):
                continue

            count = int(round(analyst_count))
            quality = min(100.0, 62.0 + min(28.0, count * 2.0) + (10.0 if per_value is not None else 0.0))
            return {
                "사용가능": count >= 3,
                "투자의견": round(opinion, 2),
                "목표주가": round(target_price, 2),
                "FY1_EPS": round(eps, 4),
                "PER": round(per_value or 0.0, 4),
                "추정기관수": count,
                "데이터품질": round(quality, 2),
                "파싱상태": "정상",
            }

    return {
        "사용가능": False,
        "파싱상태": "실패",
        "사유": "투자의견·목표주가·EPS·PER·추정기관수 표를 찾지 못함",
    }


def get_analyst_consensus(stock_code: str) -> Dict[str, Any]:
    code = str(stock_code or "").strip()
    if not re.fullmatch(r"\d{6}", code):
        return {"사용가능": False, "수집상태": "실패", "사유": "6자리 종목코드 아님"}

    now = time.time()
    memory = _MEMORY.get(code)
    if isinstance(memory, dict) and now - float(memory.get("_at") or 0.0) <= CACHE_TTL_SECONDS:
        payload = dict(memory.get("payload") or {})
        payload.update({"수집상태": "정상", "캐시": "memory"})
        return payload

    cached = _read_cache(code)
    cached_payload = cached.get("payload") if isinstance(cached.get("payload"), dict) else {}
    age = _cache_age(cached, now)
    if cached_payload and age <= CACHE_TTL_SECONDS:
        _MEMORY[code] = {"_at": now, "payload": cached_payload}
        out = dict(cached_payload)
        out.update({"수집상태": "정상", "캐시": "disk", "캐시나이초": round(age, 1)})
        return out

    url = BASE_URL.format(stock_code=code)
    try:
        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; StrategicForward/0.3; +https://github.com/)",
                "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.5",
            },
            timeout=8,
        )
        response.raise_for_status()
        parsed = parse_consensus_html(response.text)
        parsed.update({
            "수집상태": "정상" if parsed.get("사용가능") else "부분성공",
            "출처": "FnGuide 공개 Snapshot",
            "종목코드": code,
            "현재가미사용": True,
            "목표주가직접가치미사용": True,
        })
        if parsed.get("사용가능"):
            record = {"fetched_at": now, "url": url, "payload": parsed}
            try:
                _atomic_write(_cache_path(code), record)
            except Exception:
                pass
            _MEMORY[code] = {"_at": now, "payload": parsed}
        return parsed
    except Exception as exc:
        if cached_payload and age <= STALE_IF_ERROR_SECONDS:
            out = dict(cached_payload)
            out.update({
                "수집상태": "캐시사용",
                "캐시": "stale_if_error",
                "캐시나이초": round(age, 1),
                "오류": str(exc),
            })
            _MEMORY[code] = {"_at": now, "payload": cached_payload}
            return out
        return {
            "사용가능": False,
            "수집상태": "실패",
            "출처": "FnGuide 공개 Snapshot",
            "종목코드": code,
            "현재가미사용": True,
            "목표주가직접가치미사용": True,
            "사유": str(exc),
        }
