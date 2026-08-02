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


# GitHub Actions에서는 기본적으로 KIS 인증을 사용하지 않는다.
# KIS 실시간 현재가·수급은 GAS의 단일 토큰 관리자가 담당한다.
KIS_DISABLED = env_flag("KIS_DISABLED", default=False)
