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

PUBLISHED_STOCK_DIR = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "latest"
    / "stocks"
)

DEFAULT_INDUSTRY_MAP = {
    "005930": "semiconductor",
    "000660": "semiconductor",
    "000990": "semiconductor",
    "042700": "semiconductor",
    "089030": "semiconductor",
}

INDUSTRY_PROFILE_VERSION = "3.1.0"

ELECTRONIC_COMPONENT_KEYWORDS = (
    "삼성전기", "mlcc", "적층세라믹", "카메라모듈", "전자부품",
    "패키지기판", "fc-bga", "fcbga", "pcb", "기판",
)
SEMICONDUCTOR_KEYWORDS = (
    "하이닉스", "반도체", "세미콘", "파운드리", "메모리", "hbm",
)
MEDIA_ENTERTAINMENT_KEYWORDS = (
    "엔터테인먼트", "엔터", "스튜디오", "콘텐츠", "뮤직",
    "음악", "음원", "음반", "아티스트", "미디어", "컬처",
)
SOFTWARE_PLATFORM_KEYWORDS = (
    "소프트웨어", "플랫폼", "클라우드", "인터넷", "솔루션", "게임",
    "인포넷", "인증", "시큐리티",
)
BIOTECH_KEYWORDS = (
    "바이오", "셀트리온", "생명과학", "유전체", "진단",
)
MEDICAL_DEVICE_KEYWORDS = (
    "의료기기", "메디컬", "헬스테크", "의료ai", "의료 AI",
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
    "beauty_consumer",
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
    "medical_devices",
    "shipbuilding",
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
    """Classify a company into an investment/valuation industry profile.

    Priority:
    1) verified stock mapping for structurally ambiguous conglomerates,
    2) precise KSIC subcategory,
    3) strong company-name evidence,
    4) broad KSIC major category,
    5) conservative general fallback.

    This prevents broad names such as "바이오" or coarse two-digit codes from
    overriding a more precise OpenDART industry code.
    """
    code = "".join(character for character in safe_text(industry_code) if character.isdigit())
    name = safe_text(company_name).lower()
    stock = normalize_stock_code(stock_code)

    def row(profile: str, source: str, confidence: int) -> Dict[str, Any]:
        return {
            "산업코드": profile,
            "분류출처": source,
            "분류신뢰도": confidence,
            "산업프로필버전": INDUSTRY_PROFILE_VERSION,
        }

    manual = load_industry_map().get(stock, "none") if stock else "none"
    if manual != "none":
        return row(manual, "검증 종목매핑", 100)

    prefix3 = code[:3]
    prefix4 = code[:4]
    prefix5 = code[:5]
    major = int(code[:2]) if len(code) >= 2 else None

    # Precise KSIC rules. These are evaluated before generic name keywords.
    if prefix5 in {"20422", "20423", "20424"}:
        return row("beauty_consumer", "OpenDART KSIC 20422~20424", 94)
    if prefix3 == "261":
        return row("semiconductor", "OpenDART KSIC 261", 94)
    if prefix3 in {"262", "263", "264", "265", "266"}:
        return row("electronic_components", "OpenDART KSIC 262~266", 94)
    if prefix3 == "271":
        return row("medical_devices", "OpenDART KSIC 271 의료기기", 94)
    if prefix3 == "311":
        return row("shipbuilding", "OpenDART KSIC 311 선박·보트 건조", 94)
    if prefix3 == "581":
        return row("media_entertainment", "OpenDART KSIC 581 출판", 92)
    if prefix3 == "582":
        return row("software_platform", "OpenDART KSIC 582 소프트웨어 개발·공급", 94)
    if prefix3 in {"591", "592", "601", "602"}:
        return row("media_entertainment", "OpenDART KSIC 영화·음악·방송", 94)
    if prefix4 in {"6311", "6312"} or prefix3 == "631":
        return row("software_platform", "OpenDART KSIC 631 포털·호스팅·정보매개", 90)
    if prefix3 == "639":
        return row("services", "OpenDART KSIC 639 기타 정보서비스", 76)
    if prefix5 == "64992":
        # Financial holding companies are in the verified map. Unmapped 64992
        # is treated as a generic holding company so non-financial groups are
        # never valued with the bank/financial-holding model by default.
        return row("holding_company", "OpenDART KSIC 64992 지주회사", 90)

    # Strong name evidence is useful when DART has no code, or where a broad
    # manufacturing/service code does not capture an obvious investment sector.
    if any(keyword in name for keyword in ("지주", "홀딩스", "holdings")):
        return row("holding_company", "기업명 지주회사 키워드", 86)
    if any(keyword in name for keyword in MEDIA_ENTERTAINMENT_KEYWORDS):
        return row("media_entertainment", "미디어·엔터테인먼트 기업명 키워드", 88)
    if any(keyword in name for keyword in MEDICAL_DEVICE_KEYWORDS):
        return row("medical_devices", "의료기기·헬스테크 기업명 키워드", 88)
    if any(keyword in name for keyword in SEMICONDUCTOR_KEYWORDS):
        return row("semiconductor", "반도체 기업명 키워드", 90)
    if any(keyword in name for keyword in ("조선", "오션", "선박")):
        return row("shipbuilding", "조선·해양 기업명 키워드", 92)
    if any(keyword in name for keyword in ("배터리", "에너지솔루션", "리튬", "양극재", "전지")):
        return row("battery", "배터리 기업명 키워드", 88)
    if any(keyword in name for keyword in ("제약", "약품", "파마")):
        return row("pharmaceutical", "제약 기업명 키워드", 86)
    if any(keyword in name for keyword in BIOTECH_KEYWORDS):
        # '바이오' alone can appear in non-biotech company names. When a precise
        # non-health KSIC code is present, keep that code instead of overriding it.
        if not code or major in {21, 70, 72, 86}:
            return row("biotechnology", "바이오·생명과학 기업명 키워드", 88)
    if any(keyword in name for keyword in SOFTWARE_PLATFORM_KEYWORDS):
        if not code or major in {58, 62, 63}:
            return row("software_platform", "소프트웨어·플랫폼 기업명 키워드", 86)
    if (
        "보험" in name or "화재" in name or "손해" in name or "재보험" in name
        or name.endswith("생명") or "생명보험" in name
    ):
        return row("insurance", "보험업 기업명 키워드", 94)

    if major is None:
        return row("general", "업종코드 미확보", 35)

    # Broad KSIC major-category fallback.
    if major == 30:
        result = "automotive"
    elif major == 21:
        result = "pharmaceutical"
    elif major in {41, 42}:
        result = "construction"
    elif major == 65:
        result = "insurance"
    elif major in {64, 66}:
        result = "finance"
    elif major in {10, 11, 12}:
        result = "consumer_staples"
    elif major in {13, 14, 15, 16, 17, 18, 32, 33}:
        result = "consumer_discretionary"
    elif major in {45, 46, 47}:
        result = "retail"
    elif major in {59, 60}:
        result = "media_entertainment"
    elif major == 58:
        result = "services"
    elif major == 61:
        result = "telecom"
    elif major == 62:
        result = "software_platform"
    elif major == 63:
        result = "services"
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

    return row(
        result,
        "OpenDART 기업개황 업종코드 대분류 fallback",
        76 if result != "general" else 48,
    )


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


def read_prior_published_dart_industry_code(stock_code: Any) -> str:
    """Reuse only the raw OpenDART industry code from the last published stock JSON.

    This is a zero-network resilience path. Old valuation classifications are never
    reused; the raw code is passed through the current classifier again.
    """
    normalized = normalize_stock_code(stock_code)
    if not normalized:
        return ""

    path = PUBLISHED_STOCK_DIR / f"{normalized}.json"
    if not path.exists():
        return ""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return ""
        lookup = payload.get("기업조회정보")
        if not isinstance(lookup, dict):
            lookup = {}
        direct = safe_text(lookup.get("OpenDART업종코드"))
        if direct:
            return direct
        overview = lookup.get("OpenDART기업개황")
        if isinstance(overview, dict):
            return safe_text(overview.get("업종코드"))
    except Exception:
        return ""

    return ""


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
            live_industry_code = safe_text(overview.get("업종코드"))
            prior_industry_code = ""
            if not live_industry_code:
                prior_industry_code = read_prior_published_dart_industry_code(normalized)
            effective_industry_code = live_industry_code or prior_industry_code

            mapped_industry = infer_industry_code(normalized)
            classification = classify_dart_industry_detail(
                effective_industry_code,
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
                    "OpenDART업종코드": effective_industry_code,
                    "이전게시업종코드재사용": bool(prior_industry_code and not live_industry_code),
                    "산업분류원본": (
                        "OpenDART 실시간 기업개황"
                        if live_industry_code
                        else "이전 게시 JSON의 OpenDART 원본 업종코드"
                        if prior_industry_code
                        else classification["분류출처"]
                    ),
                    "데이터출처": (
                        "금융감독원 OpenDART"
                        if live_industry_code
                        else "OpenDART + 이전 게시 원본업종 로컬 fallback"
                        if prior_industry_code
                        else "금융감독원 OpenDART"
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
