# 배포 주의 — v0.2.1

이 패키지는 ZIP을 풀었을 때 보이는 `main.py`, `analyzers`, `collectors`, `.github` 등을 **GitHub 저장소의 루트에 직접 업로드**해야 합니다. 기존 저장소의 `data/latest/stocks/*.json`이 남아 있어도 GAS가 Strategic 필드가 없는 구형 JSON을 감지해 해당 종목만 on-demand 재생성합니다. 새 워크플로는 생성 JSON에 `전략미래가치` v0.2.1 필드가 없으면 게시를 실패시켜 구버전 코드가 조용히 사용되는 문제를 막습니다.

# Strategic Forward Valuation Engine V0.3.1 — Consensus + Shadow + Low-Load 검증판

## 목적
기존 Adaptive Fundamental V1 / valuation-contract-v4를 뜯어고치지 않고, 별도 엔진으로 다음을 결합합니다.

1. 현재 재무기초가치
2. 감사 가능한 SOTP(자료가 있을 때만)
3. 기업 자체 실적가속
4. 산업의 현재·장기 성장 신호
5. 애널리스트 실적 컨센서스 수정 방향(자료가 있을 때만)
6. 별도 글로벌 거시 엔진의 검증 통과 신호

최종 주가를 맞추는 엔진이 아니라, **확인 가능한 미래 현금창출 근거가 있는 만큼만 미래 증분가치를 인정**하는 보조 엔진입니다.

## 핵심 원칙
- 회사 현재가, 시가총액, 시장 PER/PBR을 적정가 산식에 사용하지 않습니다.
- 애널리스트 목표주가를 가치에 직접 넣지 않습니다.
- 실적 컨센서스가 없으면 “없는 것”으로 처리하고 임의 추정하지 않습니다.
- 산업 선행자료가 없으면 산업 프리미엄은 0점입니다.
- 산업·시장기대가 모두 부족하면 원시 미래증분가치의 최대 12%만 인정합니다.
- 산업 증거만 있고 실제 컨센서스가 없으면 최대 45%만 인정합니다.
- 글로벌 거시는 새 가치를 만들지 않습니다. 검증 게이트를 통과한 경우에만 미래가치 실현률을 0.80~1.10 범위에서 조정합니다.
- 진짜 SOTP는 2개 이상의 감사 가능한 사업부 가치와 희석주식수가 있을 때만 사용합니다. 자료가 없으면 기존 기초가치로 fallback합니다.
- 기본 모드는 `shadow`이며 기존 `재무적정가`를 덮어쓰지 않습니다.

## 글로벌 매크로 연결
`collectors/strategic_context.py`가 별도 글로벌 매크로 저장소의 `cards_8_12_bundle.json` 한 파일만 읽습니다.

기본 URL:
`https://raw.githubusercontent.com/12xx37r-ui/global-macro-data-collector/main/public/data/cards_8_12_bundle.json`

업로드된 글로벌 매크로 엔진의 Card 8은 이미 `fed-futures-collector`의 `latest.json`을 읽도록 설계되어 있으므로, 이 주식엔진에서 Fed 엔진을 다시 중복 호출하지 않습니다.

환경변수:
- `GLOBAL_MACRO_BUNDLE_URL`: 다른 raw JSON 주소 사용
- `STRATEGIC_MACRO_LOCAL_FILE`: 로컬 fixture 사용(검증/개발)
- `STRATEGIC_MACRO_CACHE_TTL_SECONDS`: 프로세스 메모리 캐시 TTL, 기본 1800초

## V0.2 외부 호출 최소화 반영
- Strategic Forward 모듈은 **먼저 로컬 계산**합니다. 원시 미래증분가치가 0이거나 인정률이 0이면 글로벌 매크로 feed를 아예 호출하지 않습니다.
- 글로벌 매크로가 필요할 때도 `cards_8_12_bundle.json` **한 파일만** 읽습니다. Fed 엔진을 다시 호출하지 않습니다.
- 동일 Python 프로세스에서는 메모리 캐시를 재사용합니다.
- 프로세스가 달라도 `.cache/strategic_macro_context.json` 디스크 캐시를 재사용하며 기본 TTL은 6시간입니다.
- stale cache 갱신 시 ETag/Last-Modified 기반 조건부 요청을 사용합니다. 서버가 304를 반환하면 JSON 본문을 다시 받지 않습니다.
- 외부 요청 실패 시 72시간 이내 last-known-good를 재사용하고 반복 재시도하지 않습니다.
- lock file로 동시 stale 갱신의 중복 요청을 줄이고, 캐시는 atomic replace로 기록합니다.
- `run.yml`에는 6시간 슬롯 단위의 GitHub Actions 캐시를 추가했습니다. on-demand workflow는 기존 `.cache` 전체 캐시를 그대로 재사용합니다.
- 애널리스트/산업/SOTP 계산 때문에 새로운 API를 추가하지 않았습니다. 이미 수집된 주식엔진 입력을 로컬 계산에 재사용합니다.

고정 원칙: **기능 정확성을 유지하면서 외부 API·UrlFetch·GitHub 호출을 최소화하고, 중복 호출 방지·캐싱·배치 처리·로컬 계산을 우선 적용합니다.**

## 실제 68개 저장 스냅샷 시뮬레이션
현재 업로드된 글로벌 매크로 스냅샷의 Card 11 품질게이트가 미통과이므로, 거시는 가치에 영향을 주지 않고 중립(1.0배) 처리되었습니다.

### 삼성전기
- 기존 Adaptive 펀더멘털 적정가: 423,165원
- 새 Shadow 기초가치: 187,123원
- 원시 미래증분가치: 236,042원
- 산업 성장증거: 있음
- 실제 애널리스트 컨센서스: 없음
- 정책상 미래가치 인정률: 45% 상한
- 인정 미래증분가치: 106,219원
- Strategic Shadow 적정가: **293,342원**
- 표시: `미래성장가치 반영 높음 · +106,219원`

실제 컨센서스가 강하게 상향되는 합성 시나리오에서는 동일 재무/산업 입력으로:
- 미래가치 인정률: 73.12%
- 미래증분가치: 172,597원
- Strategic Shadow 적정가: **359,720원**

즉 시장가격에 맞춰 올리는 것이 아니라, **실적 컨센서스 증거가 실제로 들어올 때만** 추가 미래가치가 승격됩니다.

### LG생활건강
- 기초가치: 276,183원
- 산업 선행 데이터: 현재 없음
- 실제 애널리스트 컨센서스: 없음
- 원시 미래가치 모델: 사용불가
- 미래증분가치: 0원
- Strategic Shadow 적정가: **276,183원**
- 표시: `미래성장가치 반영 낮음`

즉 LG생활건강의 기존 극단 왜곡은 산업분류/현재 재무가치 정상화에서 해결하고, 근거 없는 미래 프리미엄은 추가하지 않습니다.

### 아모레퍼시픽
- 기초가치: 91,684원
- 원시 미래증분가치: 38,546원
- 산업 선행 데이터: 없음
- 실제 애널리스트 컨센서스: 없음
- 미래가치 인정률: 12% 상한
- 인정 미래증분가치: 4,626원
- Strategic Shadow 적정가: **96,310원**

## 검증 결과
### 주식엔진
통과:
- `python -m compileall -q .`
- `validate_valuation_profiles.py`
- `validate_future_growth_model.py`
- `validate_valuation_pipeline_v4.py`
- `validate_valuation_contract.py`
- `validate_industry_profiles.py`
- `validate_insurance_financials.py`
- `validate_signal_bridge.py`
- `validate_sdi_trough.py`
- `validate_universe_catalog.py`
- `validate_sampling_plan.py`
- `validate_adaptive_fundamental_value.py`
- `validate_strategic_forward_value.py`

Strategic 전용 검증:
- 68개 저장 스냅샷 시뮬레이션
- 회사 현재가 10만원 ↔ 300만원 변경 시 Strategic 적정가 동일
- 산업+컨센서스 부재 미래가치 12% 상한 검증
- 산업만 존재/컨센서스 부재 45% 상한 검증
- 약한 컨센서스 → 강한 컨센서스 순으로 적정가 단조 증가 검증
- 검증 미통과 거시 → 조정 0 검증
- 검증 통과 악화 거시 → 미래가치 감소, 우호 거시 → 미래가치 증가 검증
- SOTP 2개 사업부 미만 차단 / 2개 이상 합산 및 순현금·비지배지분 단일조정 검증

### 별도 글로벌 매크로 엔진
업로드된 엔진 테스트: **28 passed**

### Fed 정책 엔진
업로드된 엔진 테스트: **19 passed, 1 skipped**

## 현재 검증으로 말할 수 있는 것 / 없는 것
### 말할 수 있는 것
- 현재가에 맞추지 않는 가격독립 구조입니다.
- 시장/산업 기대자료가 없을 때 미래가치가 과도하게 붙지 않도록 작동합니다.
- 기존 적정가 엔진은 shadow 단계에서 그대로 보존됩니다.
- 증거가 강해질수록 미래가치가 단조 증가하고, 검증된 나쁜 거시는 미래가치를 깎는 방향으로 작동합니다.
- SOTP는 자료가 없으면 만들지 않습니다.

### 아직 말할 수 없는 것
현재 ZIP에는 과거 시점별 애널리스트 EPS revision, 사업부별 SOTP 입력, 산업/거시 real-time vintage가 충분히 축적되어 있지 않습니다. 따라서 **“이 Strategic 적정가가 향후 시장가격을 더 정확히 맞힌다”는 실전 OOS 통계검증은 아직 할 수 없습니다.**

Production 승격 조건은 historical vintage가 누적된 뒤 walk-forward 방식으로 별도 검증하는 것이 안전합니다. 그 전까지는 `shadow` 유지가 권장됩니다.

## GitHub web-upload slim package
This distribution intentionally omits generated `data/latest/stocks/*.json`,
`data/latest/index.json`, valuation audit, and other runtime cache outputs so the
initial web upload stays below 100 files. GitHub Actions/on-demand publication
recreates those files. Strategic regression snapshots live under
`fixtures/strategic/` so validation does not depend on the runtime cache.


## V0.3.1 핵심 변경
- 미래가치 후보가 있는 종목만 외부 FY1 EPS 컨센서스를 1회 지연수집합니다.
- 종목별 24시간 디스크/메모리 캐시, 실패 시 7일 last-known-good를 사용하며 retry loop는 없습니다.
- 목표주가는 진단용으로만 저장하고 적정가/기대점수에는 0% 반영합니다.
- 산업 바스켓에 대상기업 자체가 포함되면 해당 주가 행과 오염된 시장폭/상대강도를 가치근거에서 제외합니다.
- 글로벌 거시는 기존 별도 엔진 bundle만 지연/캐시 조회하며 새 값을 만들지 않습니다.


## V0.3.1 치명오류 방지 패치
- Strategic 기초가치는 `현재재무기초가치`를 우선 사용합니다. 이 값이 없고 FY1/FY2·미래성장이 섞일 수 있는 기존 라이브 적정가만 있으면 미래증분 추가를 **0으로 차단**합니다.
- 검증된 SOTP가 있으면 그 SOTP를 현재기초가치로 사용한 뒤 미래증분을 별도로 계산합니다.
- SOTP는 `audit_status=verified|audited`, 기준일, 통화, 2개 이상 독립 사업부 EV, 사업부별 출처, 희석주식수, 순부채 조정 원천을 모두 요구합니다. Equity/EV 혼합은 이중조정 위험 때문에 차단합니다.
- 기존 `복합기업 대용 가치합산`은 진짜 SOTP가 아니므로 **진단값만 유지하고 최종 기준가에는 반영하지 않습니다.**
