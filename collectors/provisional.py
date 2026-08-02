"""OpenDART 잠정실적 정량 수집기 V1.

안전 원칙
- 공시검색에서 실제 '영업(잠정)실적' 공시만 고른다.
- 공시서류 원문 ZIP을 내려받아 표의 당해실적 값을 파싱한다.
- 매출·영업이익·순이익을 임의 추정하지 않는다.
- 단위와 기간이 검증되지 않으면 가치평가 입력으로 사용하지 않는다.
"""
from __future__ import annotations

import io
import os
import re
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from bs4 import BeautifulSoup

import config

from collectors.dart_http import get_bytes as dart_get_bytes

KST = timezone(timedelta(hours=9))
DART_DOCUMENT_URL = "https://opendart.fss.or.kr/api/document.xml"

PROVISIONAL_PATTERNS = (
    "영업(잠정)실적",
    "영업잠정실적",
    "잠정실적",
    "결산실적",
)
EXCLUDE_PATTERNS = (
    "예고",
    "전망",
    "가이던스",
)

METRIC_ALIASES = {
    "매출": (
        "매출액",
        "영업수익",
        "수익(매출액)",
    ),
    "영업이익": (
        "영업이익",
        "영업이익(손실)",
    ),
    "순이익": (
        "지배기업소유주지분순이익",
        "지배기업소유주지분에귀속되는당기순이익",
        "당기순이익",
        "분기순이익",
        "연결당기순이익",
    ),
}


def safe_text(value: Any, default: str = "") -> str:
    return default if value is None else str(value).strip()


def get_dart_api_key() -> str:
    for candidate in (
        getattr(config, "DART_API_KEY", ""),
        getattr(config, "DART_KEY", ""),
        os.getenv("DART_API_KEY", ""),
        os.getenv("DART_KEY", ""),
    ):
        value = safe_text(candidate)
        if value:
            return value
    return ""


def normalize_label(value: Any) -> str:
    return re.sub(r"[\s\u00a0·ㆍ:：()\[\]{}]", "", safe_text(value)).lower()


def parse_number(value: Any) -> Optional[float]:
    text = safe_text(value)
    if not text or text in {"-", "--", "해당없음", "n/a", "N/A"}:
        return None
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    if text.startswith(("△", "▲")):
        negative = True
        text = text[1:]
    text = text.replace(",", "").replace("원", "").replace("%", "").strip()
    match = re.fullmatch(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    number = float(text)
    return -abs(number) if negative else number


def detect_unit_multiplier(text: str) -> Tuple[float, str]:
    compact = normalize_label(text)
    unit_map = (
        ("단위백만원", 1_000_000.0, "백만원"),
        ("단위억원", 100_000_000.0, "억원"),
        ("단위천원", 1_000.0, "천원"),
        ("단위원", 1.0, "원"),
        ("단위백만달러", 1_000_000.0, "백만달러"),
        ("단위천달러", 1_000.0, "천달러"),
    )
    for token, multiplier, label in unit_map:
        if token in compact:
            return multiplier, label
    return 0.0, "미확인"


def infer_period(disclosure_date: str, document_text: str) -> Dict[str, Any]:
    date_pairs = re.findall(
        r"(20\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})[^0-9]{0,8}"
        r"(?:~|∼|～|부터)[^0-9]{0,8}"
        r"(20\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})",
        document_text,
    )
    if date_pairs:
        parsed = []
        for row in date_pairs:
            try:
                end = datetime(int(row[3]), int(row[4]), int(row[5]), tzinfo=KST)
                parsed.append((end, row))
            except ValueError:
                continue
        if parsed:
            end, row = max(parsed, key=lambda item: item[0])
            quarter = min(4, max(1, (end.month - 1) // 3 + 1))
            return {
                "사업연도": end.year,
                "분기": quarter,
                "기간키": end.year * 4 + quarter,
                "기간시작일": f"{row[0]}-{int(row[1]):02d}-{int(row[2]):02d}",
                "기간종료일": f"{row[3]}-{int(row[4]):02d}-{int(row[5]):02d}",
                "기간판정출처": "공시원문 날짜범위",
            }

    try:
        filed = datetime.strptime(disclosure_date, "%Y%m%d").replace(tzinfo=KST)
    except ValueError:
        filed = datetime.now(KST)

    if filed.month <= 3:
        year, quarter = filed.year - 1, 4
    elif filed.month <= 6:
        year, quarter = filed.year, 1
    elif filed.month <= 9:
        year, quarter = filed.year, 2
    else:
        year, quarter = filed.year, 3
    return {
        "사업연도": year,
        "분기": quarter,
        "기간키": year * 4 + quarter,
        "기간시작일": "",
        "기간종료일": "",
        "기간판정출처": "공시일 기반 보수적 추정",
    }


def is_provisional_report(report_name: Any) -> bool:
    normalized = normalize_label(report_name)
    if any(normalize_label(word) in normalized for word in EXCLUDE_PATTERNS):
        return False
    return any(normalize_label(word) in normalized for word in PROVISIONAL_PATTERNS)


def select_latest_disclosure(disclosure_bundle: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    rows = disclosure_bundle.get("공시목록", []) if isinstance(disclosure_bundle, dict) else []
    candidates = [row for row in rows if isinstance(row, dict) and is_provisional_report(row.get("보고서명"))]
    if not candidates:
        return None
    return max(candidates, key=lambda row: (safe_text(row.get("공시일")), safe_text(row.get("접수번호"))))


def download_document(api_key: str, receipt_no: str) -> bytes:
    return dart_get_bytes(
        DART_DOCUMENT_URL,
        {"crtfc_key": api_key, "rcept_no": receipt_no},
    )


def decode_document(raw: bytes) -> str:
    for encoding in ("utf-8", "cp949", "euc-kr"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def document_parts(content: bytes) -> List[str]:
    if not zipfile.is_zipfile(io.BytesIO(content)):
        return [decode_document(content)]
    texts: List[str] = []
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = sorted(
            [name for name in archive.namelist() if name.lower().endswith((".xml", ".html", ".htm"))],
            key=lambda name: archive.getinfo(name).file_size,
            reverse=True,
        )
        for name in names[:12]:
            try:
                texts.append(decode_document(archive.read(name)))
            except Exception:
                continue
    return texts


def metric_for_cells(cells: Iterable[str], current_metric: str = "") -> str:
    joined = normalize_label(" ".join(cells))
    best = current_metric
    best_length = 0
    for metric, aliases in METRIC_ALIASES.items():
        for alias in aliases:
            token = normalize_label(alias)
            if token in joined and len(token) > best_length:
                best = metric
                best_length = len(token)
    return best


def first_value_after_marker(cells: List[str], marker_tokens: Tuple[str, ...]) -> Optional[float]:
    normalized = [normalize_label(cell) for cell in cells]
    marker_index = -1
    for index, cell in enumerate(normalized):
        if any(token in cell for token in marker_tokens):
            marker_index = index
            break
    start = marker_index + 1 if marker_index >= 0 else 1
    for cell in cells[start:]:
        number = parse_number(cell)
        if number is not None:
            return number
    return None


def parse_tables(html: str) -> Tuple[Dict[str, float], str]:
    soup = BeautifulSoup(html, "html.parser")
    full_text = soup.get_text(" ", strip=True)
    multiplier, unit = detect_unit_multiplier(full_text)
    values: Dict[str, float] = {}
    priorities: Dict[str, int] = {}

    for table in soup.find_all("table"):
        current_metric = ""
        for tr in table.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])]
            if not cells:
                continue
            current_metric = metric_for_cells(cells, current_metric)
            if not current_metric:
                continue
            compact = normalize_label(" ".join(cells))
            if "누계실적" in compact and "당해실적" not in compact:
                continue
            priority = 3 if "당해실적" in compact else 2 if "당기실적" in compact else 1
            number = first_value_after_marker(cells, ("당해실적", "당기실적"))
            if number is None:
                number = first_value_after_marker(cells, tuple())
            if number is None:
                continue
            if priority >= priorities.get(current_metric, -1):
                values[current_metric] = number
                priorities[current_metric] = priority

    if multiplier > 0:
        values = {key: value * multiplier for key, value in values.items()}
    return values, unit


def validate_values(values: Dict[str, float], unit: str) -> List[str]:
    reasons: List[str] = []
    revenue = values.get("매출", 0.0)
    operating = values.get("영업이익", 0.0)
    net = values.get("순이익", 0.0)
    if unit == "미확인":
        reasons.append("금액 단위 미확인")
    if revenue <= 0:
        reasons.append("매출 미확보")
    if operating == 0:
        reasons.append("영업이익 미확보")
    if net == 0:
        reasons.append("순이익 미확보")
    if revenue > 0 and abs(operating) > revenue * 1.2:
        reasons.append("영업이익이 매출보다 비정상적으로 큼")
    if revenue > 0 and abs(net) > revenue * 1.5:
        reasons.append("순이익이 매출보다 비정상적으로 큼")
    return reasons


def parse_provisional_document(content: bytes, disclosure: Dict[str, Any]) -> Dict[str, Any]:
    parts = document_parts(content)
    best_values: Dict[str, float] = {}
    best_unit = "미확인"
    combined_text = ""
    for part in parts:
        combined_text += " " + BeautifulSoup(part, "html.parser").get_text(" ", strip=True)
        values, unit = parse_tables(part)
        if len(values) > len(best_values):
            best_values, best_unit = values, unit

    period = infer_period(safe_text(disclosure.get("공시일")), combined_text)
    reasons = validate_values(best_values, best_unit)
    usable = not reasons
    return {
        "수집상태": "정상" if usable else "검토필요",
        "사용가능": usable,
        "접수번호": safe_text(disclosure.get("접수번호")),
        "공시일": safe_text(disclosure.get("공시일")),
        "보고서명": safe_text(disclosure.get("보고서명")),
        "사업연도": period["사업연도"],
        "분기": period["분기"],
        "기간키": period["기간키"],
        "기간시작일": period["기간시작일"],
        "기간종료일": period["기간종료일"],
        "기간판정출처": period["기간판정출처"],
        "금액단위": best_unit,
        "지표": {
            "매출": round(best_values.get("매출", 0.0), 2),
            "영업이익": round(best_values.get("영업이익", 0.0), 2),
            "순이익": round(best_values.get("순이익", 0.0), 2),
        },
        "데이터품질": 86 if usable and period["기간판정출처"] == "공시원문 날짜범위" else 78 if usable else 35,
        "검증사유": reasons,
        "데이터출처": "금융감독원 OpenDART 공시서류원본",
        "주의": "감사 전 잠정실적이며 정식 분기보고서 제출 시 자동 대체",
    }


def get_latest_provisional_earnings(disclosure_bundle: Dict[str, Any]) -> Dict[str, Any]:
    disclosure = select_latest_disclosure(disclosure_bundle)
    if disclosure is None:
        return {
            "수집상태": "데이터없음",
            "사용가능": False,
            "검증사유": ["최근 잠정실적 공시 없음"],
            "데이터출처": "금융감독원 OpenDART",
        }
    api_key = get_dart_api_key()
    if not api_key:
        period = infer_period(safe_text(disclosure.get("공시일")), "")
        return {
            "수집상태": "실패",
            "사용가능": False,
            "접수번호": safe_text(disclosure.get("접수번호")),
            "공시일": safe_text(disclosure.get("공시일")),
            "보고서명": safe_text(disclosure.get("보고서명")),
            "사업연도": period["사업연도"],
            "분기": period["분기"],
            "기간키": period["기간키"],
            "기간판정출처": period["기간판정출처"],
            "검증사유": ["DART API 키 미확보"],
            "데이터출처": "금융감독원 OpenDART",
        }
    try:
        content = download_document(api_key, safe_text(disclosure.get("접수번호")))
        return parse_provisional_document(content, disclosure)
    except Exception as error:
        period = infer_period(safe_text(disclosure.get("공시일")), "")
        return {
            "수집상태": "실패",
            "사용가능": False,
            "접수번호": safe_text(disclosure.get("접수번호")),
            "공시일": safe_text(disclosure.get("공시일")),
            "보고서명": safe_text(disclosure.get("보고서명")),
            "사업연도": period["사업연도"],
            "분기": period["분기"],
            "기간키": period["기간키"],
            "기간판정출처": period["기간판정출처"],
            "검증사유": [f"{type(error).__name__}: {error}"],
            "데이터출처": "금융감독원 OpenDART 공시서류원본",
        }
