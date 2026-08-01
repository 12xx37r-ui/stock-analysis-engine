import json
import os
from datetime import datetime

from analyzers.financial import analyze_financial
from analyzers.valuation import calculate_value
from collectors.dart import get_financial
from collectors.history import get_history_bundle
from collectors.market import get_market_data
from predictor import predict_stock


COMPANY = "삼성전자"
DART_CODE = "00126380"
STOCK_CODE = "005930"
MARKET_CODE = "K"


def safe_dict(value):
    if isinstance(value, dict):
        return value
    return {}


def build_history_summary(history_bundle):
    price_history = safe_dict(
        history_bundle.get("가격추세")
    )
    investor_history = safe_dict(
        history_bundle.get("누적수급")
    )
    program_history = safe_dict(
        history_bundle.get("프로그램매매")
    )

    return {
        "가격추세": safe_dict(
            price_history.get("지표")
        ),
        "누적수급": safe_dict(
            investor_history.get("누적")
        ),
        "프로그램매매": safe_dict(
            program_history.get("누적")
        ),
        "수집상태": {
            "가격응답상태": price_history.get(
                "응답상태",
                "",
            ),
            "가격응답메시지": price_history.get(
                "응답메시지",
                "",
            ),
            "가격데이터개수": price_history.get(
                "데이터개수",
                0,
            ),
            "가격최초일": price_history.get(
                "최초일",
                "",
            ),
            "가격최종일": price_history.get(
                "최종일",
                "",
            ),
            "누적수급응답상태": investor_history.get(
                "응답상태",
                "",
            ),
            "누적수급응답메시지": investor_history.get(
                "응답메시지",
                "",
            ),
            "누적수급데이터개수": investor_history.get(
                "데이터개수",
                0,
            ),
            "누적수급최초일": investor_history.get(
                "최초일",
                "",
            ),
            "누적수급최종일": investor_history.get(
                "최종일",
                "",
            ),
            "프로그램응답상태": program_history.get(
                "응답상태",
                "",
            ),
            "프로그램응답메시지": program_history.get(
                "응답메시지",
                "",
            ),
            "프로그램데이터개수": program_history.get(
                "데이터개수",
                0,
            ),
        },
        "데이터출처": history_bundle.get(
            "데이터출처",
            "한국투자증권 KIS",
        ),
    }


def save_result(result):
    os.makedirs(
        "output",
        exist_ok=True,
    )

    output_path = os.path.join(
        "output",
        "samsung.json",
    )

    with open(
        output_path,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            result,
            file,
            ensure_ascii=False,
            indent=2,
        )

    return output_path


def main():
    print("START ENGINE")

    dart_raw = get_financial(
        DART_CODE
    )

    financial = analyze_financial(
        dart_raw
    )

    market = get_market_data(
        STOCK_CODE
    )

    history_bundle = get_history_bundle(
        STOCK_CODE,
        market_code=MARKET_CODE,
    )

    history_summary = build_history_summary(
        history_bundle
    )

    market["과거데이터"] = history_summary

    valuation = calculate_value(
        financial,
        market,
    )

    prediction = predict_stock(
        market,
        financial,
        valuation,
    )

    result = {
        "기업명": COMPANY,
        "DART기업코드": DART_CODE,
        "KIS종목코드": STOCK_CODE,
        "생성시각": datetime.now().isoformat(),
        "재무분석": financial,
        "시장정보": market,
        "가치평가": valuation,
        "주가예측": prediction,
    }

    output_path = save_result(
        result
    )

    print(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        )
    )

    print(
        "OUTPUT SAVED:",
        output_path,
    )


if __name__ == "__main__":
    main()
