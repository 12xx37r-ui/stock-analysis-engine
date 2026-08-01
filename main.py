import json
import os
from datetime import datetime

from analyzers.disclosure import analyze_disclosures
from analyzers.financial import analyze_financial
from analyzers.global_market import analyze_global_market
from analyzers.valuation import calculate_value
from collectors.dart import get_financial
from collectors.disclosure import get_recent_disclosures
from collectors.global_market import get_global_market_bundle
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


def safe_execute(
    name,
    function,
    fallback,
):
    try:
        return function()

    except Exception as error:
        print(
            name,
            "ERROR:",
            type(error).__name__,
            error,
        )

        return fallback


def build_history_summary(
    history_bundle,
):
    history_bundle = safe_dict(
        history_bundle
    )

    price_history = safe_dict(
        history_bundle.get(
            "가격추세"
        )
    )

    investor_history = safe_dict(
        history_bundle.get(
            "누적수급"
        )
    )

    program_history = safe_dict(
        history_bundle.get(
            "프로그램매매"
        )
    )

    return {
        "가격추세": safe_dict(
            price_history.get(
                "지표"
            )
        ),
        "누적수급": safe_dict(
            investor_history.get(
                "누적"
            )
        ),
        "프로그램매매": safe_dict(
            program_history.get(
                "누적"
            )
        ),
        "수집상태": {
            "전체수집상태": history_bundle.get(
                "전체수집상태",
                "",
            ),
            "가격데이터상태": price_history.get(
                "데이터상태",
                "",
            ),
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
            "누적수급데이터상태": investor_history.get(
                "데이터상태",
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
            "프로그램데이터상태": program_history.get(
                "데이터상태",
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
        "수집오류": history_bundle.get(
            "수집오류",
            [],
        ),
        "데이터출처": history_bundle.get(
            "데이터출처",
            "한국투자증권 KIS",
        ),
    }


def build_global_summary(
    global_bundle,
    global_analysis,
):
    global_bundle = safe_dict(
        global_bundle
    )

    assets = safe_dict(
        global_bundle.get(
            "자산"
        )
    )

    summarized_assets = {}

    for name, asset in assets.items():
        asset = safe_dict(asset)

        summarized_assets[name] = {
            key: value
            for key, value in asset.items()
            if key != "일별데이터"
        }

    return {
        "전체수집상태": global_bundle.get(
            "전체수집상태",
            "",
        ),
        "자산": summarized_assets,
        "분석": safe_dict(
            global_analysis
        ),
        "수집오류": global_bundle.get(
            "수집오류",
            [],
        ),
        "수집시각": global_bundle.get(
            "수집시각",
            "",
        ),
        "데이터출처": global_bundle.get(
            "데이터출처",
            "Yahoo Finance Chart API",
        ),
    }


def build_disclosure_summary(
    disclosure_bundle,
    disclosure_analysis,
):
    disclosure_bundle = safe_dict(
        disclosure_bundle
    )

    disclosures = disclosure_bundle.get(
        "공시목록",
        [],
    )

    if not isinstance(
        disclosures,
        list,
    ):
        disclosures = []

    return {
        "수집상태": disclosure_bundle.get(
            "수집상태",
            "",
        ),
        "응답코드": disclosure_bundle.get(
            "응답코드",
            "",
        ),
        "응답메시지": disclosure_bundle.get(
            "응답메시지",
            "",
        ),
        "조회시작일": disclosure_bundle.get(
            "조회시작일",
            "",
        ),
        "조회종료일": disclosure_bundle.get(
            "조회종료일",
            "",
        ),
        "공시개수": disclosure_bundle.get(
            "공시개수",
            len(disclosures),
        ),
        "최근공시": disclosures[:30],
        "분석": safe_dict(
            disclosure_analysis
        ),
        "데이터출처": disclosure_bundle.get(
            "데이터출처",
            "금융감독원 OpenDART",
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

    history_bundle = safe_execute(
        "HISTORY",
        lambda: get_history_bundle(
            STOCK_CODE,
            market_code=MARKET_CODE,
        ),
        {
            "전체수집상태": "실패",
            "가격추세": {},
            "누적수급": {},
            "프로그램매매": {},
            "수집오류": [],
        },
    )

    market["과거데이터"] = (
        build_history_summary(
            history_bundle
        )
    )

    disclosure_bundle = safe_execute(
        "DISCLOSURE",
        lambda: get_recent_disclosures(
            DART_CODE,
            days=30,
            page_count=100,
        ),
        {
            "수집상태": "실패",
            "응답메시지": "공시 수집 중 예외",
            "공시개수": 0,
            "공시목록": [],
        },
    )

    disclosure_analysis = safe_execute(
        "DISCLOSURE ANALYSIS",
        lambda: analyze_disclosures(
            disclosure_bundle
        ),
        {
            "분석상태": "실패",
            "신호": 0.0,
            "데이터품질": 0,
            "판정": "중립",
        },
    )

    global_bundle = safe_execute(
        "GLOBAL MARKET",
        get_global_market_bundle,
        {
            "전체수집상태": "실패",
            "자산": {},
            "수집오류": [],
        },
    )

    global_analysis = safe_execute(
        "GLOBAL ANALYSIS",
        lambda: analyze_global_market(
            global_bundle
        ),
        {
            "분석상태": "실패",
            "단기신호": 0.0,
            "단기데이터품질": 0.0,
            "중기신호": 0.0,
            "중기데이터품질": 0.0,
        },
    )

    valuation = calculate_value(
        financial,
        market,
    )

    prediction = predict_stock(
        market,
        financial,
        valuation,
        disclosure_analysis=(
            disclosure_analysis
        ),
        global_analysis=(
            global_analysis
        ),
    )

    result = {
        "기업명": COMPANY,
        "DART기업코드": DART_CODE,
        "KIS종목코드": STOCK_CODE,
        "생성시각": (
            datetime.now().isoformat()
        ),
        "재무분석": financial,
        "시장정보": market,
        "공시정보": (
            build_disclosure_summary(
                disclosure_bundle,
                disclosure_analysis,
            )
        ),
        "글로벌시장": (
            build_global_summary(
                global_bundle,
                global_analysis,
            )
        ),
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
