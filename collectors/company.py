"""
OpenDART 기업 자동 조회기 V3.0

기능
- 6자리 종목코드로 기업명과 DART 고유번호 자동 조회
- OpenDART corpCode.xml ZIP 다운로드·파싱
- 로컬 JSON 캐시
- 기존 get_company_code(company_name) 인터페이스 유지
- 외부 산업 매핑 파일 기반 자동 분류
- 매핑 파일 오류 시 내장값으로 안전 복구
"""

import io
import json
import os
import time
import zipfile
from pathlib import Path
from typing import Any, Dict, List
from xml.etree import ElementTree

import config

from collectors.dart_http import get_bytes as dart_get_bytes
from collectors.dart_http import get_json as dart_get_json


DART_CORP_CODE_URL = (
    "https://opendart.fss.or.kr/api/"
    "corpCode.xml"
)

DART_COMPANY_URL = (
    "https://opendart.fss.or.kr/api/"
    "company.json"
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

INDUSTRY_MAP_PATH = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "industry_map.json"
)

DEFAULT_INDUSTRY_MAP = {
    "005930": "semiconductor",
    "000660": "semiconductor",
    "000990": "semiconductor",
    "042700": "semiconductor",
    "089030": "semiconductor",
}

INDUSTRY_PROFILE_VERSION = "3.0.0"

ELECTRONIC_COMPONENT_KEYWORDS = (
    "삼성전기", "mlcc", "적층세라믹", "카메라모듈", "전자부품",
    "패키지기판", "fc-bga", "fcbga", "pcb", "기판",
)
SEMICONDUCTOR_KEYWORDS = (
    "하이닉스", "반도체", "세미콘", "파운드리", "메모리", "hbm",
)


VALUATION_INDUSTRIES = {
    "semiconductor",
    "electronic_components",
    "automotive",
    "battery",
    "biotechnology",
    "pharmaceutical",
    "construction",
    "finance",
    "insurance",
    "consumer_staples",
    "consumer_discretionary",
    "retail",
    "media_entertainment",
    "software_platform",
    "telecom",
    "utilities",
    "materials",
    "industrial",
    "transportation",
    "real_estate",
    "healthcare",
    "energy",
    "holding_company",
    "services",
    "general",
    "none",
}


def classify_dart_industry_detail(
    industry_code: Any,
    company_name: Any = "",
    stock_code: Any = "",
) -> Dict[str, Any]:
    """OpenDART 업종코드와 기업명을 가치평가 프로필로 세분화한다.

    26번 제조업 전체를 반도체로 몰던 기존 오류를 제거한다.
    261은 반도체, 262~266은 전자부품·IT하드웨어로 분리한다.
    """
    code = "".join(character for character in safe_text(industry_code) if character.isdigit())
    name = safe_text(company_name).lower()
    stock = normalize_stock_code(stock_code)

    manual = load_industry_map().get(stock, "none") if stock else "none"
    if manual != "none":
        return {
            "산업코드": manual,
            "분류출처": "수동 종목매핑",
            "분류신뢰도": 100,
            "산업프로필버전": INDUSTRY_PROFILE_VERSION,
        }

    if any(keyword in name for keyword in ("지주", "홀딩스", "holdings")):
        return {"산업코드": "holding_company", "분류출처": "기업명 키워드", "분류신뢰도": 86, "산업프로필버전": INDUSTRY_PROFILE_VERSION}
    if any(keyword in name for keyword in ELECTRONIC_COMPONENT_KEYWORDS):
        return {"산업코드": "electronic_components", "분류출처": "전자부품 키워드", "분류신뢰도": 92, "산업프로필버전": INDUSTRY_PROFILE_VERSION}
    if any(keyword in name for keyword in SEMICONDUCTOR_KEYWORDS):
        return {"산업코드": "semiconductor", "분류출처": "반도체 키워드", "분류신뢰도": 90, "산업프로필버전": INDUSTRY_PROFILE_VERSION}
    if any(keyword in name for keyword in ("배터리", "에너지솔루션", "리튬", "양극재", "전지")):
        return {"산업코드": "battery", "분류출처": "기업명 키워드", "분류신뢰도": 88, "산업프로필버전": INDUSTRY_PROFILE_VERSION}
    if any(keyword in name for keyword in ("바이오", "셀트리온")):
        return {"산업코드": "biotechnology", "분류출처": "기업명 키워드", "분류신뢰도": 86, "산업프로필버전": INDUSTRY_PROFILE_VERSION}
    if any(keyword in name for keyword in ("제약", "약품", "파마")):
        return {"산업코드": "pharmaceutical", "분류출처": "기업명 키워드", "분류신뢰도": 86, "산업프로필버전": INDUSTRY_PROFILE_VERSION}
    if any(keyword in name for keyword in ("엔터", "엔터테인먼트", "스튜디오", "콘텐츠")):
        return {"산업코드": "media_entertainment", "분류출처": "기업명 키워드", "분류신뢰도": 82, "산업프로필버전": INDUSTRY_PROFILE_VERSION}
    if any(keyword in name for keyword in ("소프트", "플랫폼", "클라우드")):
        return {"산업코드": "software_platform", "분류출처": "기업명 키워드", "분류신뢰도": 82, "산업프로필버전": INDUSTRY_PROFILE_VERSION}

    if len(code) < 2:
        return {"산업코드": "general", "분류출처": "업종코드 미확보", "분류신뢰도": 35, "산업프로필버전": INDUSTRY_PROFILE_VERSION}

    prefix3 = code[:3]
    major = int(code[:2])
    if prefix3 == "261":
        result = "semiconductor"
    elif prefix3 in {"262", "263", "264", "265", "266"}:
        result = "electronic_components"
    elif major == 30:
        result = "automotive"
    elif major == 21:
        result = "pharmaceutical"
    elif major in {41, 42}:
        result = "construction"
    elif major in {64, 65}:
        result = "finance"
    elif major == 66:
        result = "insurance"
    elif major in {10, 11, 12}:
        result = "consumer_staples"
    elif major in {13, 14, 15, 16, 17, 18, 32, 33}:
        result = "consumer_discretionary"
    elif major in {45, 46, 47}:
        result = "retail"
    elif major in {58, 59, 60}:
        result = "media_entertainment"
    elif major in {61, 62, 63}:
        result = "software_platform" if major in {62, 63} else "telecom"
    elif major in {35, 36, 37, 38, 39}:
        result = "utilities"
    elif major in {19, 20, 22, 23, 24, 25}:
        result = "materials"
    elif major in {27, 28, 29, 31}:
        result = "industrial"
    elif major in {49, 50, 51, 52}:
        result = "transportation"
    elif major == 68:
        result = "real_estate"
    elif major == 86:
        result = "healthcare"
    elif major in {5, 6, 7, 8}:
        result = "energy"
    elif major in {69, 70, 71, 72, 73, 74, 75, 85, 90, 91, 94, 95, 96}:
        result = "services"
    else:
        result = "general"

    return {
        "산업코드": result,
        "분류출처": "OpenDART 기업개황 업종코드 세분류",
        "분류신뢰도": 92 if prefix3 in {"261", "262", "263", "264", "265", "266"} else 72 if result != "general" else 48,
        "산업프로필버전": INDUSTRY_PROFILE_VERSION,
    }


def classify_dart_industry(
    industry_code: Any,
    company_name: Any = "",
    stock_code: Any = "",
) -> str:
    return safe_text(
        classify_dart_industry_detail(industry_code, company_name, stock_code).get("산업코드"),
        "general",
    )


def get_company_overview(corp_code: Any) -> Dict[str, Any]:
    corp_code = safe_text(corp_code)
    api_key = get_dart_api_key()

    if not corp_code or not api_key:
        return {
            "수집상태": "실패",
            "응답메시지": "기업코드 또는 DART API 키가 없습니다.",
        }

    try:
        data = dart_get_json(
            DART_COMPANY_URL,
            {
                "crtfc_key": api_key,
                "corp_code": corp_code,
            },
        )

        if not isinstance(data, dict):
            raise RuntimeError("기업개황 응답이 딕셔너리가 아닙니다.")

        status = safe_text(data.get("status"))
        if status != "000":
            return {
                "수집상태": "실패",
                "응답코드": status,
                "응답메시지": safe_text(data.get("message")),
            }

        return {
            "수집상태": "정상",
            "응답코드": status,
            "응답메시지": "",
            "업종코드": safe_text(data.get("induty_code")),
            "법인구분": safe_text(data.get("corp_cls")),
            "대표자": safe_text(data.get("ceo_nm")),
            "설립일": safe_text(data.get("est_dt")),
            "결산월": safe_text(data.get("acc_mt")),
            "홈페이지": safe_text(data.get("hm_url")),
        }

    except Exception as error:
        return {
            "수집상태": "실패",
            "응답메시지": f"{type(error).__name__}: {error}",
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

    content = dart_get_bytes(
        DART_CORP_CODE_URL,
        {
            "crtfc_key": api_key,
        },
    )

    companies = parse_corp_code_zip(
        content
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


def load_industry_map() -> Dict[str, str]:
    mapping = dict(
        DEFAULT_INDUSTRY_MAP
    )

    try:
        if not INDUSTRY_MAP_PATH.exists():
            return mapping

        payload = json.loads(
            INDUSTRY_MAP_PATH.read_text(
                encoding="utf-8"
            )
        )

        industries = payload.get(
            "industries",
            {}
        )

        if not isinstance(
            industries,
            dict,
        ):
            return mapping

        file_mapping: Dict[
            str,
            str,
        ] = {}

        for industry_code, detail in (
            industries.items()
        ):
            if not isinstance(
                detail,
                dict,
            ):
                continue

            stock_codes = detail.get(
                "stock_codes",
                {}
            )

            if isinstance(
                stock_codes,
                list,
            ):
                iterable = (
                    (
                        code,
                        "",
                    )
                    for code in stock_codes
                )

            elif isinstance(
                stock_codes,
                dict,
            ):
                iterable = (
                    stock_codes.items()
                )

            else:
                continue

            for stock_code, _company_name in (
                iterable
            ):
                normalized = (
                    normalize_stock_code(
                        stock_code
                    )
                )

                if not normalized:
                    continue

                file_mapping[
                    normalized
                ] = safe_text(
                    industry_code
                )

        if file_mapping:
            mapping.update(
                file_mapping
            )

    except Exception as error:
        print(
            "INDUSTRY MAP WARNING:",
            type(error).__name__,
            error,
        )

    return mapping


def infer_industry_code(
    stock_code: Any,
) -> str:
    normalized = normalize_stock_code(
        stock_code
    )

    if not normalized:
        return "none"

    return load_industry_map().get(
        normalized,
        "none",
    )


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
            overview = get_company_overview(
                result.get("DART기업코드")
            )
            mapped_industry = infer_industry_code(normalized)
            classification = classify_dart_industry_detail(
                overview.get("업종코드"),
                result.get("기업명"),
                normalized,
            )
            valuation_industry = mapped_industry if mapped_industry != "none" else classification["산업코드"]
            if mapped_industry != "none":
                classification = {
                    "산업코드": mapped_industry,
                    "분류출처": "수동 종목매핑",
                    "분류신뢰도": 100,
                    "산업프로필버전": INDUSTRY_PROFILE_VERSION,
                }
            result.update(
                {
                    "수집상태": "정상",
                    "응답메시지": "",
                    "산업코드": valuation_industry,
                    "가치평가산업코드": valuation_industry,
                    "산업분류출처": classification["분류출처"],
                    "산업분류신뢰도": classification["분류신뢰도"],
                    "산업프로필버전": classification["산업프로필버전"],
                    "OpenDART기업개황": overview,
                    "OpenDART업종코드": overview.get("업종코드", ""),
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
                    "가치평가산업코드": (
                        infer_industry_code(
                            normalized
                        )
                    ),
                    "산업분류출처": "내장 종목매핑",
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
