"""OpenDART annual financial analysis.

This module keeps the legacy output keys used by the predictor and GAS, while
normalising account aliases and applying a separate quality score to banks,
card companies and insurers.  Financial institutions are not penalised for the
high liability ratios that are inherent to their business model.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


FINANCIAL_ANALYSIS_REVISION = "financial-quality-v2.1.0-current-ratio"
FINANCIAL_SECTOR_CODES = {"finance", "insurance"}


def num(value: Any, default: float = 0.0) -> float:
    try:
        if value in (None, ""):
            return default
        text = str(value).replace(",", "").replace(" ", "").strip()
        if text in {"", "-", "--", "N/A", "nan", "None"}:
            return default
        if text.startswith("(") and text.endswith(")"):
            text = "-" + text[1:-1]
        return float(text)
    except (TypeError, ValueError):
        return default


def clean_name(value: Any) -> str:
    return (
        str(value or "")
        .replace(" ", "")
        .replace("\n", "")
        .replace("\t", "")
        .replace("·", "")
        .strip()
    )


ACCOUNT_ALIASES: Dict[str, Tuple[str, ...]] = {
    "revenue": (
        "매출액",
        "수익(매출액)",
        "영업수익",
        "총영업수익",
        "보험수익",
        "보험서비스수익",
        "보험계약수익",
        "보험영업수익",
        "보험료수익",
        "수입보험료",
        "이자수익",
        "순영업수익",
        "카드수익",
        "신용판매수익",
        "매출",
    ),
    "operating": (
        "영업이익",
        "영업이익(손실)",
        "영업손익",
        "보험손익",
        "보험영업손익",
        "보험영업이익",
        "보험서비스손익",
        "보험서비스결과",
    ),
    "net": (
        "당기순이익",
        "당기순이익(손실)",
        "연결당기순이익",
        "분기순이익",
        "반기순이익",
        "분기연결순이익",
        "반기연결순이익",
        "지배기업소유주지분순이익",
        "지배기업의소유주에게귀속되는당기순이익",
        "지배기업소유주에게귀속되는당기순이익",
        "지배기업소유주귀속당기순이익",
        "지배주주순이익",
    ),
    "equity": ("자본총계", "지배기업소유주지분", "지배기업의소유주에게귀속되는자본"),
    "debt": ("부채총계",),
    "current_assets": ("유동자산", "유동자산합계", "총유동자산"),
    "current_liabilities": ("유동부채", "유동부채합계", "총유동부채"),
}


def _normalised_aliases(key: str) -> List[str]:
    return [clean_name(item) for item in ACCOUNT_ALIASES[key]]


def find_account(data: Dict[str, Any], aliases: Sequence[str]) -> Optional[Dict[str, Any]]:
    rows = [row for row in data.get("list", []) if isinstance(row, dict)]
    wanted = [clean_name(item) for item in aliases]

    # Prefer exact standardised account names.
    for row in rows:
        if clean_name(row.get("account_nm")) in wanted:
            return row

    # OpenDART sometimes appends parenthetical descriptions.  Only use a
    # partial match for sufficiently specific aliases to avoid selecting a
    # subtotal with a similar short name.
    candidates: List[Tuple[int, int, Dict[str, Any]]] = []
    for row in rows:
        account_name = clean_name(row.get("account_nm"))
        for alias in wanted:
            if len(alias) >= 4 and (alias in account_name or account_name in alias):
                order = int(num(row.get("ord"), 999999))
                candidates.append((abs(len(account_name) - len(alias)), order, row))
                break
    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[0][2]


def _amounts(row: Optional[Dict[str, Any]]) -> Tuple[float, float, float]:
    if not row:
        return (0.0, 0.0, 0.0)
    return (
        num(row.get("thstrm_amount")),
        num(row.get("frmtrm_amount")),
        num(row.get("bfefrmtrm_amount")),
    )


def growth(current: float, previous: float) -> float:
    if previous == 0:
        return 0.0
    return ((current - previous) / abs(previous)) * 100.0


def cagr(current: float, old: float, years: int = 2) -> Optional[float]:
    if years <= 0 or current <= 0 or old <= 0:
        return None
    return (math.pow(current / old, 1.0 / years) - 1.0) * 100.0


def _score_band(value: Optional[float], bands: Sequence[Tuple[float, int]]) -> int:
    if value is None or not math.isfinite(value):
        return 0
    for threshold, points in bands:
        if value >= threshold:
            return points
    return 0


def _financial_sector_score(
    *,
    industry_code: str,
    roe: float,
    revenue_cagr: Optional[float],
    operating_cagr: Optional[float],
    net_cagr: Optional[float],
    net_values: Sequence[float],
    equity_now: float,
    equity_old: float,
) -> Tuple[int, str, List[str], List[str], Dict[str, int]]:
    components = {
        "ROE": _score_band(roe, ((12.0, 30), (8.0, 24), (5.0, 16), (0.0, 8))),
        "수익성장": _score_band(revenue_cagr, ((10.0, 15), (5.0, 12), (0.0, 8), (-5.0, 4))),
        "영업이익성장": _score_band(operating_cagr, ((10.0, 15), (0.0, 10), (-10.0, 4))),
        "순이익성장": _score_band(net_cagr, ((10.0, 20), (0.0, 14), (-10.0, 6))),
        "이익지속성": 10 if len(net_values) >= 3 and all(value > 0 for value in net_values[:3]) else 0,
        "자본성장": 10 if equity_now > 0 and equity_old > 0 and equity_now >= equity_old else 0,
    }
    score = int(sum(components.values()))

    if score >= 80:
        grade = "금융·보험업 품질 우수"
    elif score >= 65:
        grade = "금융·보험업 품질 양호"
    elif score >= 45:
        grade = "금융·보험업 보통"
    else:
        grade = "금융·보험업 주의"

    good: List[str] = []
    bad: List[str] = []
    if roe >= 8:
        good.append(f"ROE {roe:.2f}%로 금융업 자본수익성이 양호합니다.")
    else:
        bad.append(f"ROE {roe:.2f}%로 금융업 자본수익성이 낮은 편입니다.")

    revenue_label = "보험수익" if industry_code == "insurance" else "영업수익"
    if revenue_cagr is None:
        bad.append(f"{revenue_label} 2년 CAGR을 계산할 과거 자료가 부족합니다.")
    elif revenue_cagr >= 0:
        good.append(f"{revenue_label} 2년 CAGR이 {revenue_cagr:.2f}%입니다.")
    else:
        bad.append(f"{revenue_label} 2년 CAGR이 {revenue_cagr:.2f}%로 감소했습니다.")

    if net_cagr is not None and net_cagr >= 0:
        good.append(f"순이익 2년 CAGR이 {net_cagr:.2f}%입니다.")
    elif net_cagr is not None:
        bad.append(f"순이익 2년 CAGR이 {net_cagr:.2f}%로 감소했습니다.")

    if components["이익지속성"]:
        good.append("최근 3개 연도 순이익이 모두 흑자입니다.")
    else:
        bad.append("최근 3개 연도 이익 지속성을 확인해야 합니다.")

    # Do not penalise the ordinary debt ratio of insurers/banks/card firms.
    good.append("금융·보험업 특성상 일반 제조업 부채비율 기준은 점수에서 제외했습니다.")
    return score, grade, good, bad, components


def _general_score(
    *,
    roe: float,
    debt_ratio: float,
    sales_growth: float,
    op_growth: float,
    op_margin: float,
) -> Tuple[int, str, List[str], List[str], Dict[str, int]]:
    score = 0
    good: List[str] = []
    bad: List[str] = []
    components: Dict[str, int] = {}

    if roe >= 15:
        components["ROE"] = 20
        good.append("ROE가 높아 자기자본 활용 능력이 우수합니다.")
    elif roe >= 10:
        components["ROE"] = 10
        good.append("ROE는 양호하지만 최고 수준은 아닙니다.")
    else:
        components["ROE"] = 0
        bad.append(f"ROE {roe:.2f}%로 수익성 개선이 필요합니다.")

    if debt_ratio <= 50:
        components["재무안정성"] = 20
        good.append("부채비율이 낮아 재무 안전성이 좋습니다.")
    else:
        components["재무안정성"] = 0
        bad.append("부채 부담이 높은 편입니다.")

    if sales_growth > 10:
        components["매출성장"] = 15
        good.append("최근 매출 성장 흐름이 좋습니다.")
    else:
        components["매출성장"] = 0
        bad.append("매출 성장성이 강한지 확인이 필요합니다.")

    if op_growth > 10:
        components["영업이익성장"] = 20
        good.append("영업이익 성장성이 우수합니다.")
    else:
        components["영업이익성장"] = 0
        bad.append("영업이익 성장성이 약합니다.")

    if op_margin >= 10:
        components["영업이익률"] = 15
        good.append("영업이익률이 좋아 높은 수익성을 보여줍니다.")
    else:
        components["영업이익률"] = 0

    score = int(sum(components.values()))
    grade = "버핏형 우수기업" if score >= 75 else "투자검토 가능" if score >= 55 else "조건 미달"
    return score, grade, good, bad, components


def analyze_financial(data: Dict[str, Any], industry_code: str = "none") -> Dict[str, Any]:
    data = data if isinstance(data, dict) else {}
    industry_code = str(industry_code or "none").strip().lower()

    revenue = find_account(data, ACCOUNT_ALIASES["revenue"])
    operating = find_account(data, ACCOUNT_ALIASES["operating"])
    net = find_account(data, ACCOUNT_ALIASES["net"])
    equity = find_account(data, ACCOUNT_ALIASES["equity"])
    debt = find_account(data, ACCOUNT_ALIASES["debt"])
    current_assets = find_account(data, ACCOUNT_ALIASES["current_assets"])
    current_liabilities = find_account(data, ACCOUNT_ALIASES["current_liabilities"])

    sales_now, sales_prev, sales_old = _amounts(revenue)
    op_now, op_prev, op_old = _amounts(operating)
    net_now, net_prev, net_old = _amounts(net)
    equity_now, equity_prev, equity_old = _amounts(equity)
    debt_now, _, _ = _amounts(debt)
    current_assets_now, _, _ = _amounts(current_assets)
    current_liabilities_now, _, _ = _amounts(current_liabilities)

    roe = (net_now / equity_now * 100.0) if equity_now else 0.0
    debt_ratio = (debt_now / equity_now * 100.0) if equity_now else 0.0
    op_margin = (op_now / sales_now * 100.0) if sales_now else 0.0
    net_margin = (net_now / sales_now * 100.0) if sales_now else 0.0
    current_ratio = (
        current_assets_now / current_liabilities_now * 100.0
        if current_liabilities_now > 0
        else None
    )

    sales_growth = growth(sales_now, sales_old)
    op_growth = growth(op_now, op_old)
    net_growth = growth(net_now, net_old)
    sales_cagr = cagr(sales_now, sales_old, 2)
    op_cagr = cagr(op_now, op_old, 2)
    net_cagr = cagr(net_now, net_old, 2)
    equity_cagr = cagr(equity_now, equity_old, 2)

    if industry_code in FINANCIAL_SECTOR_CODES:
        score, grade, good, bad, components = _financial_sector_score(
            industry_code=industry_code,
            roe=roe,
            revenue_cagr=sales_cagr,
            operating_cagr=op_cagr,
            net_cagr=net_cagr,
            net_values=(net_now, net_prev, net_old),
            equity_now=equity_now,
            equity_old=equity_old,
        )
        evaluation_basis = "금융·보험업 전용 품질평가"
    else:
        score, grade, good, bad, components = _general_score(
            roe=roe,
            debt_ratio=debt_ratio,
            sales_growth=sales_growth,
            op_growth=op_growth,
            op_margin=op_margin,
        )
        evaluation_basis = "일반기업 버핏형 품질평가"

    growth_metrics: Dict[str, Any] = {
        "매출3년성장률": round(sales_growth, 2),
        "영업이익3년성장률": round(op_growth, 2),
        "순이익3년성장률": round(net_growth, 2),
        "매출2년CAGR": round(sales_cagr, 2) if sales_cagr is not None else None,
        "영업이익2년CAGR": round(op_cagr, 2) if op_cagr is not None else None,
        "순이익2년CAGR": round(net_cagr, 2) if net_cagr is not None else None,
        "자본2년CAGR": round(equity_cagr, 2) if equity_cagr is not None else None,
    }
    if industry_code == "insurance":
        growth_metrics["보험수익2년CAGR"] = growth_metrics["매출2년CAGR"]
    elif industry_code == "finance":
        growth_metrics["영업수익2년CAGR"] = growth_metrics["매출2년CAGR"]

    return {
        "재무분석모형버전": FINANCIAL_ANALYSIS_REVISION,
        "재무지표": {
            "ROE": round(roe, 2),
            "부채비율": round(debt_ratio, 2),
            "유동비율": (
                None
                if industry_code in FINANCIAL_SECTOR_CODES
                else round(current_ratio, 2) if current_ratio is not None else None
            ),
            "영업이익률": round(op_margin, 2),
            "순이익률": round(net_margin, 2),
        },
        "성장지표": growth_metrics,
        "버핏평가": {
            "점수": score,
            "판정": grade,
            "평가기준": evaluation_basis,
            "점수구성": components,
            "좋은점": good,
            "주의점": bad,
        },
        "투자자해설": {
            "ROE": "ROE는 회사가 주주의 돈을 이용해 얼마나 많은 이익을 만드는지 나타냅니다. 높을수록 자본 활용 능력이 좋습니다.",
            "부채비율": (
                "금융·보험업은 고객예수금·보험계약부채 등 사업구조상 부채가 커서 일반 제조업 기준으로 평가하지 않습니다."
                if industry_code in FINANCIAL_SECTOR_CODES
                else "부채비율은 회사가 가진 자기 돈 대비 빚의 규모입니다. 낮을수록 경기 침체에도 버틸 힘이 있습니다."
            ),
            "유동비율": (
                "금융·보험업은 유동자산·유동부채 구조가 일반 제조업과 달라 일반기업 유동비율 기준으로 평가하지 않습니다."
                if industry_code in FINANCIAL_SECTOR_CODES
                else "유동비율은 유동자산을 유동부채로 나눈 값입니다. 100% 이상이면 1년 안에 현금화 가능한 자산이 단기부채보다 많다는 뜻입니다."
            ),
            "영업이익률": "영업이익률은 본업에서 발생한 수익 대비 영업이익의 비율입니다.",
        },
        "원본": {
            "매출": sales_now,
            "매출전기": sales_prev,
            "매출전전기": sales_old,
            "영업이익": op_now,
            "영업이익전기": op_prev,
            "영업이익전전기": op_old,
            "순이익": net_now,
            "순이익전기": net_prev,
            "순이익전전기": net_old,
            "자본": equity_now,
            "자본전기": equity_prev,
            "자본전전기": equity_old,
            "부채": debt_now,
            "유동자산": current_assets_now,
            "유동부채": current_liabilities_now,
            "유동자산계정명": current_assets.get("account_nm") if current_assets else "",
            "유동부채계정명": current_liabilities.get("account_nm") if current_liabilities else "",
            "매출계정명": revenue.get("account_nm") if revenue else "",
            "영업이익계정명": operating.get("account_nm") if operating else "",
            "순이익계정명": net.get("account_nm") if net else "",
        },
    }
