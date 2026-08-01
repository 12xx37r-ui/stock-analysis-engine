import json
import os
import time
from datetime import datetime, timedelta, timezone

import requests

from config import (
    KIS_APP_KEY,
    KIS_APP_SECRET,
    KIS_BASE_URL,
)


ACCESS_TOKEN = None
TOKEN_FILE = "kis_token.json"
KST = timezone(timedelta(hours=9))


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


def get_access_token(force=False):
    global ACCESS_TOKEN

    if ACCESS_TOKEN and not force:
        return ACCESS_TOKEN

    if not force:
        saved_token = load_token()

        if saved_token:
            return saved_token

    print("REQUEST TOKEN")

    url = KIS_BASE_URL + "/oauth2/tokenP"

    body = {
        "grant_type": "client_credentials",
        "appkey": KIS_APP_KEY,
        "appsecret": KIS_APP_SECRET,
    }

    try:
        response = requests.post(
            url,
            json=body,
            timeout=15,
        )
        response.raise_for_status()

        data = response.json()
        token = data.get("access_token")

        if token:
            ACCESS_TOKEN = token
            save_token(token)
            print("TOKEN OK")
            return token

        print(
            "TOKEN FAIL:",
            data.get("error_description")
            or data.get("msg1")
            or data,
        )

    except Exception as error:
        print("TOKEN ERROR:", error)

    ACCESS_TOKEN = None
    return None


def kis_request(tr_id, path, params):
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
