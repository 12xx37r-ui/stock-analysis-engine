import os


DART_API_KEY = os.getenv(
    "DART_API_KEY"
)


KIS_APP_KEY = os.getenv(
    "KIS_APP_KEY"
)


KIS_APP_SECRET = os.getenv(
    "KIS_APP_SECRET"
)


KIS_BASE_URL = (
    "https://openapi.koreainvestment.com:9443"
)


def env_flag(name: str, default: bool = False) -> bool:
    value = str(os.getenv(name, "1" if default else "0") or "").strip().lower()
    return value in {"1", "true", "yes", "on", "enabled"}


# KIS_DISABLED=1이면 KIS 전용 수급·프로그램 호출을 건너뛴다.
# GitHub Actions는 저장소 비밀키가 있을 때만 23시간 토큰 캐시를 사용한다.
KIS_DISABLED = env_flag("KIS_DISABLED", default=False)


KIS_TOKEN_FILE = os.getenv(
    "KIS_TOKEN_FILE",
    ".cache/kis_token.json",
)


def env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


KIS_TOKEN_REUSE_HOURS = env_float(
    "KIS_TOKEN_REUSE_HOURS",
    23.0,
)
