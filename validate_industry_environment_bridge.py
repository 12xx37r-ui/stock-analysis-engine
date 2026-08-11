"""Static/fixture validation for the stock <-> industry environment bridge."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import collectors.industry_environment as bridge
from predictor import apply_industry_environment_overlay


def payload(generated_at=None, quality=73.7, allowed=True, adjustment=0.33):
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    return {
        "schema_version": "1.0.0",
        "engine_version": "1.0.4-test",
        "generated_at_utc": generated_at,
        "by_profile_key": {
            "semiconductor": {
                "industry_label": "반도체",
                "current_score": 46.5,
                "current_band": "중립",
                "forecast_3m_score": 47.7,
                "forecast_3m_band": "중립",
                "delta_points": 1.3,
                "direction": "개선",
                "quality_score": quality,
                "bounded_direction_adjustment_points": adjustment,
                "allowed_as_auxiliary": allowed,
                "allowed_as_primary": False,
            },
            "biotechnology": {
                "industry_label": "바이오·제약",
                "current_score": 57.4,
                "current_band": "중립",
                "forecast_3m_score": 51.6,
                "forecast_3m_band": "중립",
                "delta_points": -5.9,
                "direction": "악화",
                "quality_score": 74.8,
                "bounded_direction_adjustment_points": -0.52,
                "allowed_as_auxiliary": True,
                "allowed_as_primary": False,
            },
        },
        "alias_to_profile_key": {
            "semiconductor": "semiconductor",
            "반도체": "semiconductor",
            "biotechnology": "biotechnology",
            "바이오·제약": "biotechnology",
        },
        "usage_rule": "bounded auxiliary only",
    }


class FakeResponse:
    def __init__(self, data):
        self.status_code = 200
        self._data = data
        self.headers = {"ETag": '"test"'}

    def raise_for_status(self):
        return None

    def json(self):
        return self._data


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    original_cache = bridge.CACHE_FILE
    original_ttl = bridge.CACHE_TTL_SECONDS
    original_stale = bridge.STALE_IF_ERROR_SECONDS
    original_max_age = bridge.MAX_SOURCE_AGE_SECONDS
    original_min_quality = bridge.MIN_QUALITY_SCORE
    old_local = os.environ.pop("INDUSTRY_ENV_BRIDGE_LOCAL_FILE", None)
    old_url = os.environ.get("INDUSTRY_ENV_BRIDGE_URL")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        bridge.CACHE_FILE = tmp_path / "industry_bridge_cache.json"
        bridge.CACHE_TTL_SECONDS = 21600
        bridge.STALE_IF_ERROR_SECONDS = 432000
        bridge.MAX_SOURCE_AGE_SECONDS = 432000
        bridge.MIN_QUALITY_SCORE = 60.0
        os.environ["INDUSTRY_ENV_BRIDGE_URL"] = "https://example.invalid/bridge.json"

        try:
            bridge.reset_runtime_cache_for_tests()
            calls = {"count": 0}

            def fake_get(*args, **kwargs):
                calls["count"] += 1
                return FakeResponse(payload())

            with patch("collectors.industry_environment.requests.get", side_effect=fake_get):
                first = bridge.get_industry_environment("semiconductor")
                second = bridge.get_industry_environment("semiconductor")
                mapped = bridge.get_industry_environment("pharmaceutical")

            assert_true(first.get("사용가능") is True, "fresh semiconductor bridge unavailable")
            assert_true(second.get("사용가능") is True, "memory reuse failed")
            assert_true(mapped.get("매핑산업코드") == "biotechnology", "compatibility mapping failed")
            assert_true(calls["count"] == 1, f"network call count expected 1, got {calls['count']}")
            assert_true(first.get("주신호사용허용") is False, "primary use gate not preserved")
            assert_true(first.get("개별종목방향보정점수") == 0.33, "bounded adjustment changed")
            assert_true(first.get("보정최대절대값") == 0.33, "missing upstream max must not invent headroom")

            # Simulate the next sequential subprocess in weekly_sampler: memory is
            # empty, but the prior process already wrote the disk cache. It must
            # reuse that cache without a second GitHub request.
            bridge.reset_runtime_cache_for_tests()
            with patch("collectors.industry_environment.requests.get") as disk_network:
                disk_reuse = bridge.get_industry_environment("semiconductor")
            assert_true(disk_reuse.get("사용가능") is True, "disk cache reuse failed")
            assert_true(disk_reuse.get("캐시모드") == "disk_cache", "disk cache mode not reported")
            assert_true(disk_network.call_count == 0, "fresh disk cache triggered duplicate network call")

            bundle, analysis = bridge.build_environment_replacement("semiconductor", first)
            assert_true(bundle.get("전체수집상태") == "정상", "replacement bundle failed")
            assert_true(analysis.get("산업환경3개월", {}).get("점수") == 47.7, "3m score missing")
            assert_true(analysis.get("중기산업선행") == {}, "3m bridge incorrectly promoted to primary mid axis")
            assert_true(analysis.get("장기산업사이클") == {}, "3m bridge incorrectly extrapolated to long axis")

            base_prediction = {
                "점수": 50,
                "상승확률": 50,
                "판정": "중립",
                "신뢰도": 70,
                "근거": [],
            }
            adjusted = apply_industry_environment_overlay(dict(base_prediction), first)
            overlay = adjusted.get("산업환경보조오버레이", {})
            assert_true(overlay.get("적용") is True, "auxiliary overlay not applied")
            assert_true(abs(overlay.get("적용보정점수", 0.0) - 0.33) < 1e-9, "overlay amount mismatch")
            assert_true(overlay.get("보조전용") is True, "overlay auxiliary-only marker missing")

            # Low quality must not enter the stock model.
            low_path = tmp_path / "low.json"
            low_path.write_text(json.dumps(payload(quality=59.9), ensure_ascii=False), encoding="utf-8")
            os.environ["INDUSTRY_ENV_BRIDGE_LOCAL_FILE"] = str(low_path)
            low = bridge.get_industry_environment("semiconductor")
            assert_true(low.get("사용가능") is False, "low-quality bridge incorrectly accepted")

            # Stale source must be explicitly held in 연결대기, never converted to neutral.
            stale_path = tmp_path / "stale.json"
            stale_generated = (datetime.now(timezone.utc) - timedelta(days=6)).isoformat()
            stale_path.write_text(json.dumps(payload(generated_at=stale_generated), ensure_ascii=False), encoding="utf-8")
            os.environ["INDUSTRY_ENV_BRIDGE_LOCAL_FILE"] = str(stale_path)
            stale = bridge.get_industry_environment("semiconductor")
            assert_true(stale.get("사용가능") is False, "stale bridge incorrectly accepted")
            assert_true(stale.get("수집상태") == "연결대기", "stale state not surfaced")

            # Unmapped broad industry must not call the bridge at all.
            os.environ.pop("INDUSTRY_ENV_BRIDGE_LOCAL_FILE", None)
            bridge.reset_runtime_cache_for_tests()
            with patch("collectors.industry_environment.requests.get") as mocked:
                unmapped = bridge.get_industry_environment("materials")
            assert_true(unmapped.get("사용가능") is False, "ambiguous materials profile guessed")
            assert_true(mocked.call_count == 0, "unmapped profile triggered unnecessary network call")

        finally:
            bridge.CACHE_FILE = original_cache
            bridge.CACHE_TTL_SECONDS = original_ttl
            bridge.STALE_IF_ERROR_SECONDS = original_stale
            bridge.MAX_SOURCE_AGE_SECONDS = original_max_age
            bridge.MIN_QUALITY_SCORE = original_min_quality
            bridge.reset_runtime_cache_for_tests()
            if old_local is not None:
                os.environ["INDUSTRY_ENV_BRIDGE_LOCAL_FILE"] = old_local
            else:
                os.environ.pop("INDUSTRY_ENV_BRIDGE_LOCAL_FILE", None)
            if old_url is not None:
                os.environ["INDUSTRY_ENV_BRIDGE_URL"] = old_url
            else:
                os.environ.pop("INDUSTRY_ENV_BRIDGE_URL", None)

    print("INDUSTRY ENVIRONMENT BRIDGE VALIDATION: PASS")
    print("- fresh schema/freshness/quality gate: PASS")
    print("- pharmaceutical -> biotechnology compatibility: PASS")
    print("- one HTTP request + memory reuse contract: PASS")
    print("- fresh disk cache reuse across sequential-process simulation: PASS")
    print("- ambiguous profile no-call guard: PASS")
    print("- 3M bridge kept out of primary mid/long axes: PASS")
    print("- bounded auxiliary overlay only: PASS")


if __name__ == "__main__":
    main()
