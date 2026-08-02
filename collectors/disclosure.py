"""
OpenDART 최근 공시 수집기 V1

기능
- 최근 N일 공시목록 수집
- API 오류·키 누락·공시 없음 구분
- 전체 엔진 중단 방지
- predictor.py에는 아직 연결하지 않음

공식 API
- GET https://opendart.fss.or.kr/api/list.json
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import config

from collectors.dart_http import get_json as dart_get_json


KST = timezone(timedelta(hours=9))
DART_LIST_URL = "https://opendart.fss.or.kr/api/list.json"


def safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def safe_int(value: Any, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(float(str(value).replace(",", "").strip()))
    except (TypeError, ValueError):
        return default


def get_dart_api_key() -> str:
    candidates = (
        getattr(config, "DART_API_KEY", ""),
        getattr(config, "DART_KEY", ""),
        os.getenv("DART_API_KEY", ""),
        os.getenv("DART_KEY", ""),
    )

    for candidate in candidates:
        key = safe_text(candidate)

        if key:
            return key

    return ""


def empty_result(
    status: str,
    message: str,
    corp_code: str,
    start_date: str = "",
    end_date: str = "",
) -> Dict[str, Any]:
    return {
        "수집상태": status,
        "응답코드": "",
        "응답메시지": message,
        "기업코드": corp_code,
        "조회시작일": start_date,
        "조회종료일": end_date,
        "공시개수": 0,
        "공시목록": [],
        "데이터출처": "금융감독원 OpenDART",
    }


def normalize_disclosure(
    row: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "접수번호": safe_text(row.get("rcept_no")),
        "공시일": safe_text(row.get("rcept_dt")),
        "기업명": safe_text(row.get("corp_name")),
        "기업코드": safe_text(row.get("corp_code")),
        "종목코드": safe_text(row.get("stock_code")),
        "보고서명": safe_text(row.get("report_nm")),
        "제출인": safe_text(row.get("flr_nm")),
        "공시유형": safe_text(row.get("pblntf_ty")),
        "공시상세유형": safe_text(row.get("pblntf_detail_ty")),
        "비고": safe_text(row.get("rm")),
    }


def get_recent_disclosures(
    corp_code: str,
    days: int = 30,
    page_count: int = 100,
) -> Dict[str, Any]:
    corp_code = safe_text(corp_code)

    if not corp_code:
        return empty_result(
            "실패",
            "기업코드가 비어 있습니다.",
            corp_code,
        )

    api_key = get_dart_api_key()

    if not api_key:
        return empty_result(
            "실패",
            "DART API 키를 찾지 못했습니다.",
            corp_code,
        )

    days = max(
        min(safe_int(days, 30), 365),
        1,
    )
    page_count = max(
        min(safe_int(page_count, 100), 100),
        1,
    )

    end = datetime.now(KST).date()
    start = end - timedelta(days=days)

    start_date = start.strftime("%Y%m%d")
    end_date = end.strftime("%Y%m%d")

    params = {
        "crtfc_key": api_key,
        "corp_code": corp_code,
        "bgn_de": start_date,
        "end_de": end_date,
        "last_reprt_at": "N",
        "page_no": 1,
        "page_count": page_count,
        "sort": "date",
        "sort_mth": "desc",
    }

    data = dart_get_json(DART_LIST_URL, params)

    response_code = safe_text(data.get("status"))
    response_message = safe_text(data.get("message"))

    if response_code == "013":
        result = empty_result(
            "정상",
            response_message or "조회된 공시가 없습니다.",
            corp_code,
            start_date,
            end_date,
        )
        result["응답코드"] = response_code
        return result

    if response_code != "000":
        result = empty_result(
            "실패",
            response_message or "OpenDART 공시조회 실패",
            corp_code,
            start_date,
            end_date,
        )
        result["응답코드"] = response_code
        return result

    raw_rows = data.get("list", [])

    if not isinstance(raw_rows, list):
        raw_rows = []

    disclosures: List[Dict[str, Any]] = []

    for row in raw_rows:
        if not isinstance(row, dict):
            continue

        normalized = normalize_disclosure(row)

        if not normalized["보고서명"]:
            continue

        disclosures.append(normalized)

    disclosures.sort(
        key=lambda item: (
            item["공시일"],
            item["접수번호"],
        ),
        reverse=True,
    )

    return {
        "수집상태": "정상",
        "응답코드": response_code,
        "응답메시지": response_message,
        "기업코드": corp_code,
        "조회시작일": start_date,
        "조회종료일": end_date,
        "공시개수": len(disclosures),
        "공시목록": disclosures,
        "데이터출처": "금융감독원 OpenDART",
    }
