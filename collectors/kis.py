import hashlib
import json
import os
import time
from pathlib import Path
from datetime import datetime, timedelta, timezone

import requests

from config import (
    KIS_APP_KEY,
    KIS_APP_SECRET,
    KIS_BASE_URL,
    KIS_DISABLED,
    KIS_TOKEN_FILE,
    KIS_TOKEN_REUSE_HOURS,
)


ACCESS_TOKEN = None
ACCESS_TOKEN_EXPIRES_AT = None
TOKEN_FILE = KIS_TOKEN_FILE
KST = timezone(timedelta(hours=9))

TOKEN_FAILURE_UNTIL = 0.0
TOKEN_FAILURE_MESSAGE = ""
TOKEN_FAILURE_LOGGED = False
TOKEN_FAILURE_COOLDOWN_SECONDS = 300
TOKEN_REQUEST_ATTEMPTS = 2
TOKEN_CONNECT_TIMEOUT = 8
TOKEN_READ_TIMEOUT = 20
TOKEN_EXPIRY_BUFFER_SECONDS = 300


def credential_fingerprint():
    source = "|".join([
        str(KIS_BASE_URL or ""),
        str(KIS_APP_KEY or ""),
        str(KIS_APP_SECRET or ""),
    ])
    return hashlib.sha256(source.encode("utf-8")).hexdigest()[:24]


def token_path():
    path = Path(TOKEN_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def parse_datetime(value):
    text = str(value or "").strip()
    if not text:
        return None

    candidates = [
        text,
        text.replace("Z", "+00:00"),
        text.replace("/", "-"),
    ]

    for candidate in candidates:
        try:
            parsed = datetime.fromisoformat(candidate)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=KST)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y%m%d%H%M%S",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            parsed = datetime.strptime(text, fmt).replace(tzinfo=KST)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass

    return None


def token_is_reusable(data):
    if not isinstance(data, dict):
        return False

    if data.get("credential_fingerprint") != credential_fingerprint():
        return False

    expires_at = parse_datetime(data.get("expires_at"))
    if expires_at is None:
        saved_at = parse_datetime(data.get("saved_at"))
        if saved_at is None:
            return False
        expires_at = saved_at + timedelta(hours=max(1.0, KIS_TOKEN_REUSE_HOURS))

    now = datetime.now(timezone.utc)
    return expires_at > now + timedelta(seconds=TOKEN_EXPIRY_BUFFER_SECONDS)


def load_token():
    global ACCESS_TOKEN
    global ACCESS_TOKEN_EXPIRES_AT

    path = token_path()
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        token = str(data.get("access_token") or "").strip()

        if token and token_is_reusable(data):
            ACCESS_TOKEN = token
            ACCESS_TOKEN_EXPIRES_AT = parse_datetime(data.get("expires_at"))
            print("TOKEN CACHE REUSED:", path)
            return token

        print("TOKEN CACHE EXPIRED OR MISMATCH:", path)
        clear_token()

    except Exception as error:
        print("TOKEN LOAD ERROR:", error)

    return None


def save_token(token, expires_at=None):
    global ACCESS_TOKEN_EXPIRES_AT

    path = token_path()
    now = datetime.now(timezone.utc)
    parsed_expiry = parse_datetime(expires_at)

    if parsed_expiry is None:
        parsed_expiry = now + timedelta(hours=max(1.0, KIS_TOKEN_REUSE_HOURS))

    ACCESS_TOKEN_EXPIRES_AT = parsed_expiry
    payload = {
        "access_token": token,
        "saved_at": now.isoformat(),
        "expires_at": parsed_expiry.isoformat(),
        "credential_fingerprint": credential_fingerprint(),
        "token_source": "KIS client_credentials",
    }

    temporary = path.with_suffix(path.suffix + ".tmp")

    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temporary, path)
        print("TOKEN CACHE SAVED:", path)
    except Exception as error:
        print("TOKEN SAVE ERROR:", error)
        try:
            temporary.unlink(missing_ok=True)
        except Exception:
            pass


def clear_token():
    global ACCESS_TOKEN
    global ACCESS_TOKEN_EXPIRES_AT

    ACCESS_TOKEN = None
    ACCESS_TOKEN_EXPIRES_AT = None

    try:
        token_path().unlink(missing_ok=True)
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
        # 비밀키가 없는 환경에서는 KIS 전용 자료를 건너뛴다.
        # 가격·차트는 Yahoo 보완 경로가 계속 작동한다.
        return None

    if ACCESS_TOKEN and not force:
        if (
            ACCESS_TOKEN_EXPIRES_AT is None
            or ACCESS_TOKEN_EXPIRES_AT > datetime.now(timezone.utc) + timedelta(seconds=TOKEN_EXPIRY_BUFFER_SECONDS)
        ):
            return ACCESS_TOKEN
        clear_token()

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
                save_token(token, data.get("access_token_token_expired"))
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
            "/uapi/domestic-stock/v1/quotations/investor-trade-by-stock-daily",
            {
                "FID_COND_MRKT_DIV_CODE": "J",
                "FID_INPUT_ISCD": stock_code,
                "FID_INPUT_DATE_1": query_date,
                "FID_ORG_ADJ_PRC": "",
                "FID_ETC_CLS_CODE": "",
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
                "KIS_DISABLED",
                "TOKEN_ERROR",
                "REQUEST_ERROR",
                "CONFIG_ERROR",
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
