"""
OpenDART 기업 자동 조회기 V2

기능
- 6자리 종목코드로 기업명과 DART 고유번호 자동 조회
- OpenDART corpCode.xml ZIP 다운로드·파싱
- 로컬 JSON 캐시
- 기존 get_company_code(company_name) 인터페이스 유지
- 반도체 산업코드 자동 추론
"""

import io
import json
import os
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List
from xml.etree import ElementTree

import requests

import config


DART_CORP_CODE_URL = (
    "https://opendart.fss.or.kr/api/"
    "corpCode.xml"
)

CACHE_PATH = Path(
    ".cache/dart_corp_codes.json"
)

CACHE_MAX_AGE_SECONDS = (
    7 * 24 * 60 * 60
)

FALLBACK_COMPANIES = {
    "005930": {
        "기업명": "삼성전자",
        "DART기업코드": "00126380",
        "종목코드": "005930",
    },
}

SEMICONDUCTOR_STOCK_CODES = {
    "005930",  # 삼성전자
    "000660",  # SK하이닉스
}


def safe_text(
    value: Any,
    default: str = "",
) -> str:
    if value is None:
        return default

    return str(value).strip()


def normalize_stock_code(
    stock_code: Any,
) -> str:
    text = safe_text(
        stock_code
    )

    if not text:
        return ""

    if text.isdigit():
        return text.zfill(6)

    return text


def get_dart_api_key() -> str:
    candidates = (
        getattr(
            config,
            "DART_API_KEY",
            "",
        ),
        getattr(
            config,
            "DART_KEY",
            "",
        ),
        os.getenv(
            "DART_API_KEY",
            "",
        ),
        os.getenv(
            "DART_KEY",
            "",
        ),
    )

    for candidate in candidates:
        key = safe_text(
            candidate
        )

        if key:
            return key

    return ""


def read_cache() -> List[Dict[str, str]]:
    try:
        if not CACHE_PATH.exists():
            return []

        age = (
            time.time()
            - CACHE_PATH.stat().st_mtime
        )

        if age > CACHE_MAX_AGE_SECONDS:
            return []

        data = json.loads(
            CACHE_PATH.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(
            data,
            list,
        ):
            return []

        return [
            item
            for item in data
            if isinstance(
                item,
                dict,
            )
        ]

    except Exception:
        return []


def write_cache(
    companies: List[Dict[str, str]],
) -> None:
    try:
        CACHE_PATH.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        CACHE_PATH.write_text(
            json.dumps(
                companies,
                ensure_ascii=False,
                separators=(",", ":"),
            ),
            encoding="utf-8",
        )

    except Exception as error:
        print(
            "COMPANY CACHE WARNING:",
            type(error).__name__,
            error,
        )


def parse_corp_code_zip(
    content: bytes,
) -> List[Dict[str, str]]:
    with zipfile.ZipFile(
        io.BytesIO(content)
    ) as archive:
        xml_names = [
            name
            for name in archive.namelist()
            if name.lower().endswith(
                ".xml"
            )
        ]

        if not xml_names:
            raise RuntimeError(
                "corpCode ZIP 안에 XML이 없습니다."
            )

        xml_data = archive.read(
            xml_names[0]
        )

    root = ElementTree.fromstring(
        xml_data
    )

    companies: List[
        Dict[str, str]
    ] = []

    for item in root.findall(
        "list"
    ):
        corp_code = safe_text(
            item.findtext(
                "corp_code"
            )
        )
        corp_name = safe_text(
            item.findtext(
                "corp_name"
            )
        )
        stock_code = normalize_stock_code(
            item.findtext(
                "stock_code"
            )
        )
        modify_date = safe_text(
            item.findtext(
                "modify_date"
            )
        )

        if not (
            corp_code
            and corp_name
        ):
            continue

        companies.append(
            {
                "기업명": corp_name,
                "DART기업코드": corp_code,
                "종목코드": stock_code,
                "최종변경일": modify_date,
            }
        )

    return companies


def download_company_list() -> List[Dict[str, str]]:
    api_key = get_dart_api_key()

    if not api_key:
        raise RuntimeError(
            "DART API 키를 찾지 못했습니다."
        )

    response = requests.get(
        DART_CORP_CODE_URL,
        params={
            "crtfc_key": api_key,
        },
        timeout=30,
    )

    response.raise_for_status()

    companies = parse_corp_code_zip(
        response.content
    )

    if not companies:
        raise RuntimeError(
            "OpenDART 기업목록이 비어 있습니다."
        )

    write_cache(
        companies
    )

    return companies


def get_company_list(
    force_refresh: bool = False,
) -> List[Dict[str, str]]:
    if not force_refresh:
        cached = read_cache()

        if cached:
            return cached

    return download_company_list()


def infer_industry_code(
    stock_code: Any,
) -> str:
    normalized = normalize_stock_code(
        stock_code
    )

    if normalized in (
        SEMICONDUCTOR_STOCK_CODES
    ):
        return "semiconductor"

    return "none"


def resolve_company(
    stock_code: Any,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    normalized = normalize_stock_code(
        stock_code
    )

    if not normalized:
        return {
            "수집상태": "실패",
            "응답메시지": (
                "종목코드가 비어 있습니다."
            ),
            "기업명": "",
            "DART기업코드": "",
            "종목코드": "",
            "산업코드": "none",
        }

    try:
        companies = get_company_list(
            force_refresh=force_refresh
        )

        for company in companies:
            if normalize_stock_code(
                company.get(
                    "종목코드"
                )
            ) != normalized:
                continue

            result = dict(company)
            result.update(
                {
                    "수집상태": "정상",
                    "응답메시지": "",
                    "산업코드": (
                        infer_industry_code(
                            normalized
                        )
                    ),
                    "데이터출처": (
                        "금융감독원 OpenDART"
                    ),
                }
            )

            return result

        return {
            "수집상태": "실패",
            "응답메시지": (
                f"OpenDART 기업목록에서 "
                f"{normalized} 종목을 찾지 못했습니다."
            ),
            "기업명": "",
            "DART기업코드": "",
            "종목코드": normalized,
            "산업코드": (
                infer_industry_code(
                    normalized
                )
            ),
            "데이터출처": (
                "금융감독원 OpenDART"
            ),
        }

    except Exception as error:
        fallback = FALLBACK_COMPANIES.get(
            normalized
        )

        if fallback:
            result = dict(
                fallback
            )
            result.update(
                {
                    "수집상태": "부분성공",
                    "응답메시지": (
                        f"OpenDART 기업목록 조회 실패로 "
                        f"내장값 사용: "
                        f"{type(error).__name__}: "
                        f"{error}"
                    ),
                    "산업코드": (
                        infer_industry_code(
                            normalized
                        )
                    ),
                    "데이터출처": (
                        "내장 비상값"
                    ),
                }
            )

            return result

        return {
            "수집상태": "실패",
            "응답메시지": (
                f"{type(error).__name__}: "
                f"{error}"
            ),
            "기업명": "",
            "DART기업코드": "",
            "종목코드": normalized,
            "산업코드": (
                infer_industry_code(
                    normalized
                )
            ),
            "데이터출처": (
                "금융감독원 OpenDART"
            ),
        }


def get_company_code(
    company_name: Any,
) -> str:
    target = safe_text(
        company_name
    )

    if not target:
        return ""

    try:
        companies = get_company_list()

        for company in companies:
            if safe_text(
                company.get(
                    "기업명"
                )
            ) == target:
                return safe_text(
                    company.get(
                        "DART기업코드"
                    )
                )

    except Exception:
        for fallback in (
            FALLBACK_COMPANIES.values()
        ):
            if fallback[
                "기업명"
            ] == target:
                return fallback[
                    "DART기업코드"
                ]

    return ""
