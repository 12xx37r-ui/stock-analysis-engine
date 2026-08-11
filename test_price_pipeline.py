from __future__ import annotations

import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from collectors import market as market_collector
from collectors import price as price_module
from collectors import kis as kis_collector
from collectors.market import finalize_market_data, parse_yahoo_market
from collectors.price import (
    KST,
    PRICE_SCHEMA_VERSION,
    candidate,
    choose_candidate,
    suppress_unverified_price_judgment,
    validate_candidate,
)
from feed_contract import inspect_published_stock

FIXED_NOW = datetime(2026, 8, 6, 0, 33, tzinfo=KST)
LATEST_DATE = "2026-08-05"


def yahoo_payload(close, volume, exchange, regular_price, market_cap, shares, previous=None):
    timestamp = int(datetime(2026, 8, 5, 15, 30, tzinfo=KST).timestamp())
    previous = previous or close * 0.98
    return {
        "chart": {
            "error": None,
            "result": [{
                "meta": {
                    "regularMarketPrice": regular_price,
                    "regularMarketTime": timestamp,
                    "chartPreviousClose": previous,
                    "currency": "KRW",
                    "exchangeName": exchange,
                    "marketCap": market_cap,
                    "sharesOutstanding": shares,
                },
                "timestamp": [timestamp],
                "indicators": {
                    "quote": [{
                        "open": [close * 0.97],
                        "high": [close * 1.02],
                        "low": [close * 0.96],
                        "close": [close],
                        "volume": [volume],
                    }],
                    "adjclose": [{"adjclose": [regular_price]}],
                },
            }],
        }
    }


def technical(close, date_text=LATEST_DATE, volume=100000):
    ts = int(datetime.fromisoformat(date_text + "T15:30:00+09:00").timestamp())
    return {
        "수집상태": "정상",
        "최종일": date_text,
        "최근일봉": [{
            "timestamp": ts,
            "시각UTC": datetime.fromtimestamp(ts, tz=KST).astimezone(price_module.UTC).isoformat(),
            "종가": close,
            "거래량": volume,
        }],
        "일봉": {"latestClose": close, "available": True},
    }


def fundamentals(shares):
    return {"주식총수": {"발행주식수": shares, "유통주식수": shares, "가치평가주식수": shares}}


class PricePipelineTests(unittest.TestCase):
    def choose_yahoo(self, code, close, stale_meta, shares, market_cap, exchange="KOE"):
        wrong = parse_yahoo_market(
            code + ".KS",
            yahoo_payload(close, 500000, exchange, stale_meta, market_cap, shares),
            code,
        )
        right = parse_yahoo_market(
            code + ".KQ",
            yahoo_payload(close, 500000, exchange, stale_meta, market_cap, shares),
            code,
        )
        selected, checked = choose_candidate(
            [wrong, right],
            stock_code=code,
            expected_market="Q",
            share_count=shares,
            technical_bundle=technical(close),
            at=FIXED_NOW,
        )
        return selected, checked

    def test_lunit_regression_stale_regular_market_price_is_ignored(self):
        shares = 74_000_000 + int("328130"[-3:])
        close = 10_000 + int("328130"[-3:])
        selected, checked = self.choose_yahoo("328130", close, close * 4.3, shares, close * shares)
        self.assertIsNotNone(selected)
        self.assertEqual(selected["가격"], close)
        self.assertEqual(selected["심볼"], "328130.KQ")
        self.assertFalse(selected["조정주가여부"])
        rejected_ks = next(row for row in checked if row.get("심볼") == "328130.KS")
        self.assertFalse(rejected_ks["최종채택"])
        self.assertTrue(any("심볼" in reason for reason in rejected_ks["거부사유"]))

    def test_dream_security_regression_old_meta_is_ignored(self):
        shares = 100_000_000 + int("203650"[-3:])
        close = 2_000 + int("203650"[-2:])
        selected, _ = self.choose_yahoo("203650", close, close * 1.4, shares, close * shares)
        self.assertEqual(selected["가격"], close)
        self.assertEqual(selected["가격기준일"], LATEST_DATE)
        self.assertEqual(selected["가격출처"], "Yahoo Finance Chart API")

    def test_korea_information_certificate_regression_old_meta_is_ignored(self):
        shares = 40_000_000 + int("053300"[-3:])
        close = 4_000 + int("053300"[-3:])
        selected, _ = self.choose_yahoo("053300", close, close * 0.93, shares, close * shares)
        self.assertEqual(selected["가격"], close)
        self.assertEqual(selected["가격종류"], "KRX 종가")

    def test_normal_company_price_is_preserved(self):
        shares = 1000000
        row = candidate(
            "005930", market="K", trading_market="KRX", price=80000,
            price_date=LATEST_DATE, price_time="15:30:00", collected_at=FIXED_NOW,
            source="Yahoo Finance Chart API", price_type="KRX 종가", adjusted=False,
            volume=1000000, market_cap=80000 * shares, source_share_count=shares,
            symbol="005930.KS", exchange="KSC",
        )
        checked = validate_candidate(row, stock_code="005930", expected_market="K", share_count=shares,
                                     technical_bundle=technical(80000), at=FIXED_NOW)
        self.assertTrue(checked["최종채택"])
        self.assertEqual(checked["시가총액일관성결과"], "통과")

    def test_adjusted_close_is_rejected(self):
        row = candidate(
            "000001", market="K", trading_market="KRX", price=10000,
            price_date=LATEST_DATE, price_time="15:30:00", collected_at=FIXED_NOW,
            source="test", price_type="KRX 종가", adjusted=True, volume=100,
        )
        checked = validate_candidate(row, stock_code="000001", expected_market="K", at=FIXED_NOW)
        self.assertFalse(checked["최종채택"])
        self.assertIn("Adjusted Close 또는 조정주가", checked["거부사유"])

    def test_old_price_is_rejected(self):
        old_date = (FIXED_NOW.date() - timedelta(days=30)).isoformat()
        row = candidate(
            "000001", market="K", trading_market="KRX", price=10000,
            price_date=old_date, price_time="15:30:00", collected_at=FIXED_NOW,
            source="test", price_type="KRX 종가", adjusted=False, volume=100,
        )
        checked = validate_candidate(row, stock_code="000001", expected_market="K", at=FIXED_NOW)
        self.assertFalse(checked["최종채택"])
        self.assertTrue(any("오래된 가격" in reason for reason in checked["거부사유"]))

    def test_market_cap_multiple_mismatch_is_blocked(self):
        shares = 1000000
        row = candidate(
            "000001", market="K", trading_market="KRX", price=10000,
            price_date=LATEST_DATE, price_time="15:30:00", collected_at=FIXED_NOW,
            source="test", price_type="KRX 종가", adjusted=False, volume=100,
            market_cap=10000 * shares * 4, source_share_count=shares,
        )
        checked = validate_candidate(row, stock_code="000001", expected_market="K", share_count=shares, at=FIXED_NOW)
        self.assertFalse(checked["최종채택"])
        self.assertEqual(checked["시가총액일관성결과"], "실패")

    def test_share_count_change_invalidates_unverified_candidate(self):
        row = candidate(
            "000001", market="K", trading_market="KRX", price=10000,
            price_date=LATEST_DATE, price_time="15:30:00", collected_at=FIXED_NOW,
            source="test", price_type="KRX 종가", adjusted=False, volume=100,
            source_share_count=1000000,
        )
        checked = validate_candidate(row, stock_code="000001", expected_market="K", share_count=2000000, at=FIXED_NOW)
        self.assertFalse(checked["최종채택"])
        self.assertTrue(checked["기업행위의심여부"])


    def test_post_corporate_action_market_pair_can_validate_without_changing_dart_shares(self):
        financial_shares = 29_000_000
        source_shares = 74_000_000
        close = 10_100
        row = candidate(
            "328130", market="Q", trading_market="KRX", price=close,
            price_date=LATEST_DATE, price_time="15:30:00", collected_at=FIXED_NOW,
            source="Yahoo Finance Chart API", price_type="KRX 종가", adjusted=False,
            volume=500_000, market_cap=close * source_shares,
            source_share_count=source_shares, symbol="328130.KQ", exchange="KOE",
        )
        checked = validate_candidate(
            row,
            stock_code="328130",
            expected_market="Q",
            share_count=financial_shares,
            technical_bundle=technical(close),
            at=FIXED_NOW,
        )
        self.assertTrue(checked["최종채택"], checked["거부사유"])
        self.assertTrue(checked["기업행위의심여부"])
        self.assertEqual(checked["발행주식수"], source_shares)
        self.assertEqual(checked["재무발행주식수"], financial_shares)
        self.assertEqual(checked["시가총액일관성결과"], "통과")

    def test_kis_disabled_calls_no_token_endpoint(self):
        with mock.patch.object(kis_collector, "KIS_DISABLED", True), \
             mock.patch.object(kis_collector.requests, "post") as post:
            self.assertIsNone(kis_collector.get_access_token())
            disabled = kis_collector.kis_request("TEST", "/test", {})
        post.assert_not_called()
        self.assertEqual(disabled["rt_cd"], "KIS_DISABLED")

    def test_valid_central_token_is_reused_without_issuance(self):
        valid_until = datetime.now(price_module.UTC) + timedelta(hours=6)
        with mock.patch.object(kis_collector, "KIS_DISABLED", False), \
             mock.patch.object(kis_collector, "ACCESS_TOKEN", "central-reused-token"), \
             mock.patch.object(kis_collector, "ACCESS_TOKEN_EXPIRES_AT", valid_until), \
             mock.patch.object(kis_collector.requests, "post") as post:
            tokens = [kis_collector.get_access_token() for _ in range(5)]
        post.assert_not_called()
        self.assertEqual(tokens, ["central-reused-token"] * 5)

    def test_parallel_collectors_reuse_same_valid_central_token(self):
        valid_until = datetime.now(price_module.UTC) + timedelta(hours=6)
        with mock.patch.object(kis_collector, "KIS_DISABLED", False), \
             mock.patch.object(kis_collector, "ACCESS_TOKEN", "central-reused-token"), \
             mock.patch.object(kis_collector, "ACCESS_TOKEN_EXPIRES_AT", valid_until), \
             mock.patch.object(kis_collector.requests, "post") as post, \
             ThreadPoolExecutor(max_workers=8) as executor:
            tokens = list(executor.map(lambda _: kis_collector.get_access_token(), range(24)))
        post.assert_not_called()
        self.assertEqual(tokens, ["central-reused-token"] * 24)

    def test_all_sources_fail_returns_price_unavailable(self):
        market = {"종목코드": "000001", "_가격후보": [], "현재가": 99999}
        with mock.patch.object(price_module, "PRICE_CACHE_DIR", Path("/definitely/not/a/cache")):
            result = finalize_market_data(market, "000001", "K", fundamentals(1000000), technical(10000))
        self.assertEqual(result["현재가"], 0.0)
        self.assertEqual(result["현재가수집상태"], "현재가 확인 불가")
        self.assertFalse(result["가격진단"]["최종채택"])

    def test_kis_disabled_path_does_not_call_token_manager(self):
        with mock.patch.object(market_collector, "get_stock_price", return_value={}), \
             mock.patch.object(market_collector, "get_investor_trade", return_value={}), \
             mock.patch.object(market_collector, "get_yahoo_market_candidates", return_value=[]), \
             mock.patch("collectors.kis.get_access_token") as token:
            result = market_collector.get_market_data("000001", market_code="K")
        token.assert_not_called()
        self.assertEqual(result["현재가수집상태"], "검증대기")

    def test_krx_nxt_are_not_mixed(self):
        row = candidate(
            "000001", market="K", trading_market="NXT", price=10000,
            price_date=LATEST_DATE, price_time="18:00:00", collected_at=FIXED_NOW,
            source="test", price_type="KRX 종가", adjusted=False, volume=100,
        )
        checked = validate_candidate(row, stock_code="000001", expected_market="K", at=FIXED_NOW)
        self.assertFalse(checked["최종채택"])
        self.assertTrue(any("NXT" in reason for reason in checked["거부사유"]))

    def test_krx_holiday_calendar_uses_previous_real_session(self):
        holiday_noon = datetime(2026, 8, 17, 12, 0, tzinfo=KST)
        self.assertEqual(
            price_module.latest_allowed_trade_date(holiday_noon).isoformat(),
            "2026-08-14",
        )
        ok, status, _ = price_module.evaluate_freshness(
            datetime(2026, 8, 14, tzinfo=KST).date(),
            at=holiday_noon,
        )
        self.assertTrue(ok, status)

    def test_intraday_previous_real_session_is_allowed_after_weekend(self):
        monday_noon = datetime(2026, 8, 10, 12, 0, tzinfo=KST)
        ok, status, _ = price_module.evaluate_freshness(
            datetime(2026, 8, 7, tzinfo=KST).date(),
            at=monday_noon,
        )
        self.assertTrue(ok, status)
        self.assertEqual(status, "장중 직전 거래일 종가")

    def test_kis_candidate_uses_response_trade_date_and_time_when_present(self):
        output = {
            "stck_prpr": "10000",
            "acml_vol": "1000",
            "stck_bsop_date": "20260805",
            "stck_cntg_hour": "152927",
            "rprs_mrkt_kor_name": "코스닥",
        }
        with mock.patch.object(market_collector, "now_kst", return_value=FIXED_NOW):
            row = market_collector._kis_candidate("000001", "Q", output)
        self.assertEqual(row["가격기준일"], "2026-08-05")
        self.assertEqual(row["가격기준시각"], "15:29:27")
        self.assertEqual(row["시장구분"], "KOSDAQ")

    def test_unverified_price_suppresses_only_price_judgment(self):
        valuation = {"기본적정가": 12345, "현재가": 0, "현재가대비": 0, "판단": "적정"}
        unavailable = {
            "현재가수집상태": "현재가 확인 불가",
            "현재가응답메시지": "오래된 가격",
        }
        suppressed = suppress_unverified_price_judgment(valuation, unavailable)
        self.assertEqual(suppressed["기본적정가"], 12345)
        self.assertEqual(suppressed["판단"], "현재가 확인 불가")
        self.assertFalse(suppressed["가격기반판정가능"])
        verified = suppress_unverified_price_judgment(
            valuation,
            {"현재가수집상태": "정상"},
        )
        self.assertEqual(verified, valuation)

    def test_utc_kst_trade_date_is_correct(self):
        payload = yahoo_payload(10000, 100, "KSC", 10000, 10000000000, 1000000)
        row = parse_yahoo_market("000001.KS", payload, "000001")
        self.assertEqual(row["가격기준일"], LATEST_DATE)

    def test_old_json_is_ineligible_for_active_feed(self):
        old = {
            "KIS종목코드": "000001",
            "시장정보": {"현재가": 10000},
            "주가예측": {}, "가치평가": {}, "화면브리지": {},
        }
        eligible, reasons = inspect_published_stock(old, "000001")
        self.assertFalse(eligible)
        self.assertIn("현재가 검증 스키마 불일치", reasons)

    def test_price_schema_unavailable_state_is_backward_compatible(self):
        stock = {
            "KIS종목코드": "000001",
            "시장정보": {
                "현재가": 0,
                "가격진단": {
                    "가격스키마버전": PRICE_SCHEMA_VERSION,
                    "최종채택": False,
                    "거부사유": ["검증 가능한 최신 가격 없음"],
                },
            },
            "주가예측": {"엔진버전": "6.8.0-valuation-contract-v4"},
            "가치평가": {
                "가치평가엔진버전": "6.8.0-valuation-contract-v4",
                "가치평가계약버전": "4.0",
                "산업프로필버전": "3.0.1",
                "가치평가모형개정버전": "future-growth-v1.1.0-price-independent",
                "미래성장모형": {"사용가능": False, "차단사유": ["자료 부족"]},
                "데이터자격검사": {"통과": False, "중단사유": ["자료 부족"]},
                "최종값사용가능": False,
            },
            "화면브리지": {"스키마버전": "2.0", "종목코드": "000001"},
        }
        eligible, reasons = inspect_published_stock(stock, "000001")
        self.assertTrue(eligible, reasons)

    def test_price_cache_schema_key_and_share_change(self):
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(price_module, "PRICE_CACHE_DIR", Path(temp)):
                row = candidate(
                    "000001", market="K", trading_market="KRX", price=10000,
                    price_date=LATEST_DATE, price_time="15:30:00", collected_at=FIXED_NOW,
                    source="test", price_type="KRX 종가", adjusted=False, volume=100,
                )
                row["최종채택"] = True
                with mock.patch.object(price_module, "now_kst", return_value=FIXED_NOW):
                    price_module.write_price_cache(row, 1000000)
                    hit = price_module.read_price_cache("000001", "K", share_count=1000000)
                    miss = price_module.read_price_cache("000001", "K", share_count=2000000)
                self.assertIsNotNone(hit)
                self.assertTrue(hit["캐시사용여부"])
                self.assertIsNone(miss)
                files = list(Path(temp).glob("*.json"))
                self.assertEqual(len(files), 1)
                payload = json.loads(files[0].read_text(encoding="utf-8"))
                self.assertEqual(payload["캐시버전"], PRICE_SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main(verbosity=2)
