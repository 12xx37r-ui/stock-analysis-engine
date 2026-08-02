import json
import os
import time
from datetime import datetime, timedelta, timezone

import requests

from config import (
    KIS_APP_KEY,
    KIS_APP_SECRET,
    KIS_BASE_URL,
    KIS_DISABLED,
)


ACCESS_TOKEN = None
TOKEN_FILE = "kis_token.json"
KST = timezone(timedelta(hours=9))

TOKEN_FAILURE_UNTIL = 0.0
TOKEN_FAILURE_MESSAGE = ""
TOKEN_FAILURE_LOGGED = False
TOKEN_FAILURE_COOLDOWN_SECONDS = 300
TOKEN_REQUEST_ATTEMPTS = 2
TOKEN_CONNECT_TIMEOUT = 8
TOKEN_READ_TIMEOUT = 20


def safe_float(value):
    try:
        if value in (None, ""):
            return 0.0

        return float(str(value).replace(",", ""))

    except (TypeError, ValueError):
        return 0.0


def load_token():
    global ACCESS_TOKEN

    if not os.path.exists(TOKEN_FILE):
        return None

    try:
        with open(TOKEN_FILE, "r", encoding="utf-8") as file:
            data = json.load(file)

        token = data.get("access_token")

        if token:
            ACCESS_TOKEN = token
            print("TOKEN LOADED")
            return token

    except Exception as error:
        print("TOKEN LOAD ERROR:", error)

    return None


def save_token(token):
    try:
        with open(TOKEN_FILE, "w", encoding="utf-8") as file:
            json.dump(
                {
                    "access_token": token,
                    "saved_at": datetime.now(KST).isoformat(),
                },
                file,
                ensure_ascii=False,
                indent=2,
            )

    except Exception as error:
        print("TOKEN SAVE ERROR:", error)


def clear_token():
    global ACCESS_TOKEN

    ACCESS_TOKEN = None

    try:
        if os.path.exists(TOKEN_FILE):
            os.remove(TOKEN_FILE)

    except Exception as error:
        print("TOKEN FILE DELETE ERROR:", error)


def clear_token_failure():
    global TOKEN_FAILURE_UNTIL
    global TOKEN_FAILURE_MESSAGE
    global TOKEN_FAILURE_LOGGED

    TOKEN_FAILURE_UNTIL = 0.0
    TOKEN_FAILURE_MESSAGE = ""
    TOKEN_FAILURE_LOGGED = False


def mark_token_failure(message):
    global TOKEN_FAILURE_UNTIL
    global TOKEN_FAILURE_MESSAGE
    global TOKEN_FAILURE_LOGGED

    TOKEN_FAILURE_UNTIL = (
        time.monotonic()
        + TOKEN_FAILURE_COOLDOWN_SECONDS
    )
    TOKEN_FAILURE_MESSAGE = str(
        message
        or "토큰 발급 실패"
    )
    TOKEN_FAILURE_LOGGED = False


def token_failure_active():
    return (
        time.monotonic()
        < TOKEN_FAILURE_UNTIL
    )


def get_token_failure_message():
    return (
        TOKEN_FAILURE_MESSAGE
        or "토큰 발급 실패"
    )


def get_access_token(force=False):
    global ACCESS_TOKEN
    global TOKEN_FAILURE_LOGGED

    if KIS_DISABLED:
        # GitHub 정기·일괄 분석은 KIS 토큰을 발급하지 않는다.
        # 실시간 KIS 데이터는 GAS에서 1일 1회 발급한 토큰으로 보강한다.
        return None

    if ACCESS_TOKEN and not force:
        return ACCESS_TOKEN

    if not KIS_APP_KEY or not KIS_APP_SECRET:
        message = (
            "KIS_APP_KEY 또는 "
            "KIS_APP_SECRET가 없습니다."
        )
        mark_token_failure(message)
        print("TOKEN CONFIG ERROR:", message)
        return None

    if (
        not force
        and token_failure_active()
    ):
        if not TOKEN_FAILURE_LOGGED:
            print(
                "TOKEN COOLDOWN ACTIVE:",
                get_token_failure_message(),
            )
            TOKEN_FAILURE_LOGGED = True

        return None

    if not force:
        saved_token = load_token()

        if saved_token:
            return saved_token

    if force:
        clear_token_failure()

    url = KIS_BASE_URL + "/oauth2/tokenP"

    body = {
        "grant_type": "client_credentials",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
    }

    last_error = ""

    for attempt in range(
        1,
        TOKEN_REQUEST_ATTEMPTS + 1,
    ):
        print(
            "REQUEST TOKEN",
            f"{attempt}/{TOKEN_REQUEST_ATTEMPTS}",
        )

        try:
            response = requests.post(
                url,
                json=body,
                timeout=(
                    TOKEN_CONNECT_TIMEOUT,
                    TOKEN_READ_TIMEOUT,
                ),
            )

            response.raise_for_status()

            data = response.json()
            token = data.get("access_token")

            if token:
                ACCESS_TOKEN = token
                clear_token_failure()
                save_token(token)
                print("TOKEN OK")
                return token

            last_error = str(
                data.get("error_description")
                or data.get("msg1")
                or data
            )

            print(
                "TOKEN FAIL:",
                last_error,
            )

            break

        except Exception as error:
            last_error = (
                f"{type(error).__name__}: "
                f"{error}"
            )

            print(
                "TOKEN ERROR:",
                last_error,
            )

            if attempt < TOKEN_REQUEST_ATTEMPTS:
                wait_seconds = 3
                print(
                    "TOKEN RETRY WAIT:",
                    wait_seconds,
                )
                time.sleep(
                    wait_seconds
                )

    ACCESS_TOKEN = None

    mark_token_failure(
        last_error
        or "토큰 발급 실패"
    )

    return None


def kis_request(tr_id, path, params):
    if KIS_DISABLED:
        return {
            "rt_cd": "KIS_DISABLED",
            "msg_cd": "",
            "msg1": "GitHub KIS 호출 비활성화 · GAS 중앙 토큰 사용",
            "output": [],
        }

    token_reissued = False

    for attempt in range(3):
        token = get_access_token()

        if not token:
            return {
                "rt_cd": "TOKEN_ERROR",
                "msg_cd": "",
                "msg1": "토큰 발급 실패",
                "output": [],
            }

        headers = {
            "authorization": "Bearer " + token,
            "appkey": KIS_APP_KEY,
            "appsecret": KIS_APP_SECRET,
            "tr_id": tr_id,
            "custtype": "P",
        }

        try:
            time.sleep(1.5)

            response = requests.get(
                KIS_BASE_URL + path,
                headers=headers,
                params=params,
                timeout=15,
            )
            response.raise_for_status()

            data = response.json()

            msg_code = str(data.get("msg_cd", ""))
            message = str(data.get("msg1", ""))

            rate_limited = (
                msg_code == "EGW00201"
                or "초당 거래건수" in message
                or "초당" in message
            )

            if rate_limited:
                print("KIS RATE LIMIT WAIT")
                time.sleep(5 + attempt)
                continue

            token_error = (
                "토큰" in message
                or "TOKEN" in message.upper()
                or msg_code in {
                    "EGW00121",
                    "EGW00122",
                    "EGW00123",
                }
            )

            if token_error and not token_reissued:
                print("TOKEN REISSUE")

                clear_token()
                token_reissued = True

                new_token = get_access_token(force=True)

                if not new_token:
                    return {
                        "rt_cd": "TOKEN_ERROR",
                        "msg_cd": msg_code,
                        "msg1": "토큰 재발급 실패",
                        "output": [],
                    }

                continue

            return data

        except Exception as error:
            print("KIS REQUEST ERROR:", error)
            time.sleep(2 + attempt)

    return {
        "rt_cd": "REQUEST_ERROR",
        "msg_cd": "",
        "msg1": "KIS 요청 실패",
        "output": [],
    }


def get_stock_price(stock_code):
    data = kis_request(
        "FHKST01010100",
        "/uapi/domestic-stock/v1/quotations/inquire-price",
        {
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_INPUT_ISCD": stock_code,
        },
    )

    output = data.get("output", {})

    if isinstance(output, dict):
        return output

    return {}


def extract_investor_row(data):
    investor_keys = {
        "frgn_ntby_qty",
        "orgn_ntby_qty",
        "prsn_ntby_qty",
    }

    for output_name in ("output2", "output", "output1"):
        output = data.get(output_name)

        if isinstance(output, dict):
            if investor_keys.intersection(output.keys()):
                return output

        if isinstance(output, list):
            for row in output:
                if not isinstance(row, dict):
                    continue

                if investor_keys.intersection(row.keys()):
                    return row

    return {}


def recent_business_dates(maximum_days=7):
    current_date = datetime.now(KST).date()
    dates = []
    offset = 0

    while len(dates) < maximum_days and offset < 20:
        target_date = current_date - timedelta(days=offset)
        offset += 1

        if target_date.weekday() >= 5:
            continue

        dates.append(target_date.strftime("%Y%m%d"))

    return dates


def get_investor_trade(stock_code):
    last_data = {}
    last_message = ""

    for query_date in recent_business_dates(maximum_days=7):
        data = kis_request(
            "FHPTJ04160001",
            "/uapi/domestic-stock/v1/quotations/inquire-investor",
            {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": stock_code,
                "FID_INPUT_DATE_1": query_date,
                "FID_ORG_ADJ_PRC": "0",
                "FID_ETC_CLS_CODE": "00",
            },
        )

        last_data = data
        last_message = str(data.get("msg1", ""))

        row = extract_investor_row(data)

        if not row:
            print(
                "INVESTOR DATA EMPTY:",
                query_date,
                last_message,
            )

            if data.get(
                "rt_cd"
            ) in {
                "TOKEN_ERROR",
                "REQUEST_ERROR",
            }:
                print(
                    "INVESTOR DATA ABORT:",
                    data.get(
                        "rt_cd"
                    ),
                    last_message,
                )
                break

            continue

        foreign_net = safe_float(row.get("frgn_ntby_qty"))
        institution_net = safe_float(row.get("orgn_ntby_qty"))
        individual_net = safe_float(row.get("prsn_ntby_qty"))

        print(
            "INVESTOR DATA OK:",
            query_date,
            foreign_net,
            institution_net,
            individual_net,
        )

        return {
            "외국인순매수": foreign_net,
            "기관순매수": institution_net,
            "개인순매수": individual_net,
            "조회일": row.get("stck_bsop_date") or query_date,
            "응답상태": data.get("rt_cd", ""),
            "응답메시지": last_message,
        }

    print("INVESTOR DATA FAILED:", last_message)

    return {
        "외국인순매수": 0.0,
        "기관순매수": 0.0,
        "개인순매수": 0.0,
        "조회일": "",
        "응답상태": last_data.get("rt_cd", ""),
        "응답메시지": last_message,
    }
