"""
기업 뉴스 수집·규칙형 분석기 V1.0

- 별도 API 키 없이 Google News RSS를 기본 사용한다.
- 제목과 발행일만 이용해 최근 30일 뉴스의 방향성을 정량화한다.
- 뉴스가 없거나 RSS가 실패하면 명시적으로 실패 처리하며, 임의 추정하지 않는다.
"""

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any, Dict, List
from urllib.parse import quote_plus
import re
import xml.etree.ElementTree as ET

import requests


POSITIVE_RULES = {
    "실적": 16,
    "영업이익 증가": 18,
    "사상 최대": 20,
    "최대 실적": 20,
    "흑자전환": 22,
    "수주": 12,
    "공급계약": 15,
    "증설": 10,
    "투자 확대": 8,
    "신제품": 7,
    "점유율 확대": 12,
    "목표가 상향": 10,
    "매수": 5,
    "배당 확대": 10,
    "자사주": 9,
    "승인": 8,
    "허가": 8,
    "파트너십": 7,
}

NEGATIVE_RULES = {
    "실적 부진": -16,
    "영업손실": -20,
    "적자전환": -22,
    "하향": -8,
    "목표가 하향": -10,
    "리콜": -12,
    "소송": -10,
    "횡령": -22,
    "배임": -22,
    "유상증자": -12,
    "감산": -8,
    "수요 둔화": -10,
    "재고 증가": -8,
    "규제": -7,
    "경고": -6,
    "급락": -8,
    "매도": -5,
}


def safe_text(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def clean_title(value: Any) -> str:
    text = unescape(safe_text(value))
    text = re.sub(r"\s+-\s+[^-]{1,40}$", "", text).strip()
    return re.sub(r"\s+", " ", text)


def parse_pub_date(value: Any) -> datetime:
    text = safe_text(value)
    if not text:
        return datetime.now(timezone.utc)

    try:
        parsed = parsedate_to_datetime(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return datetime.now(timezone.utc)


def title_score(title: str) -> Dict[str, Any]:
    score = 0.0
    matched: List[str] = []

    for keyword, weight in POSITIVE_RULES.items():
        if keyword in title:
            score += weight
            matched.append(keyword)

    for keyword, weight in NEGATIVE_RULES.items():
        if keyword in title:
            score += weight
            matched.append(keyword)

    return {
        "score": clamp(score, -35.0, 35.0),
        "matched": matched,
    }


def judgment(signal: float) -> str:
    if signal >= 45:
        return "매우 긍정"
    if signal >= 15:
        return "긍정"
    if signal <= -45:
        return "매우 부정"
    if signal <= -15:
        return "부정"
    return "중립"


def get_company_news(company_name: str, maximum_items: int = 30) -> Dict[str, Any]:
    company_name = safe_text(company_name)

    if not company_name:
        return {
            "수집상태": "실패",
            "응답메시지": "기업명이 비어 있습니다.",
            "뉴스개수": 0,
            "뉴스목록": [],
            "분석": {
                "분석상태": "실패",
                "신호": 0.0,
                "데이터품질": 0.0,
                "판정": "중립",
            },
        }

    query = quote_plus(f'"{company_name}" 주식 OR 실적 OR 수주 OR 투자')
    url = (
        "https://news.google.com/rss/search"
        f"?q={query}&hl=ko&gl=KR&ceid=KR:ko"
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
        ),
        "Accept": "application/rss+xml,application/xml,text/xml,*/*",
    }

    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except Exception as error:
        return {
            "수집상태": "실패",
            "응답메시지": f"{type(error).__name__}: {error}",
            "뉴스개수": 0,
            "뉴스목록": [],
            "분석": {
                "분석상태": "실패",
                "신호": 0.0,
                "데이터품질": 0.0,
                "판정": "중립",
            },
            "데이터출처": "Google News RSS",
        }

    now = datetime.now(timezone.utc)
    items: List[Dict[str, Any]] = []
    seen = set()

    for node in root.findall(".//item"):
        title = clean_title(node.findtext("title"))
        link = safe_text(node.findtext("link"))
        source_node = node.find("source")
        source = safe_text(source_node.text if source_node is not None else "")
        published = parse_pub_date(node.findtext("pubDate"))

        if not title or title in seen:
            continue
        seen.add(title)

        score_info = title_score(title)
        age_days = max(0.0, (now - published).total_seconds() / 86400.0)
        recency_weight = clamp(1.0 - age_days / 45.0, 0.35, 1.0)
        weighted_score = score_info["score"] * recency_weight

        items.append(
            {
                "제목": title,
                "링크": link,
                "언론사": source,
                "발행시각UTC": published.isoformat(),
                "경과일": round(age_days, 2),
                "원점수": round(score_info["score"], 2),
                "최종점수": round(weighted_score, 2),
                "매칭규칙": score_info["matched"],
            }
        )

        if len(items) >= max(5, maximum_items):
            break

    if not items:
        return {
            "수집상태": "데이터없음",
            "응답메시지": "최근 기업 뉴스가 없습니다.",
            "뉴스개수": 0,
            "뉴스목록": [],
            "분석": {
                "분석상태": "데이터없음",
                "신호": 0.0,
                "데이터품질": 0.0,
                "판정": "중립",
            },
            "데이터출처": "Google News RSS",
        }

    directional_items = [item for item in items if abs(item["최종점수"]) > 0]
    score_sum = sum(item["최종점수"] for item in directional_items)
    divisor = max(1.0, min(8.0, len(directional_items)))
    signal = clamp(score_sum / divisor * 3.0, -100.0, 100.0)
    quality = clamp(35.0 + len(items) * 2.0 + len(directional_items) * 2.5, 35.0, 88.0)

    positive = [item for item in items if item["최종점수"] > 0]
    negative = [item for item in items if item["최종점수"] < 0]
    neutral = [item for item in items if item["최종점수"] == 0]

    return {
        "수집상태": "정상",
        "응답메시지": "",
        "뉴스개수": len(items),
        "뉴스목록": items,
        "분석": {
            "분석상태": "정상",
            "신호": round(signal, 2),
            "데이터품질": round(quality, 1),
            "판정": judgment(signal),
            "긍정뉴스개수": len(positive),
            "부정뉴스개수": len(negative),
            "중립뉴스개수": len(neutral),
            "긍정뉴스": positive[:5],
            "부정뉴스": negative[:5],
            "설명": "최근 뉴스 제목의 실적·수주·투자·증자·소송 등 규칙과 시간가중치를 합성합니다.",
        },
        "데이터출처": "Google News RSS",
        "수집시각UTC": now.isoformat(),
    }
