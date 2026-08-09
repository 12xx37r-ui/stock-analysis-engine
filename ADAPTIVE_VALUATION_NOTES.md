# Adaptive Fundamental Valuation V1 변경 요약

## 목적
기존 valuation-contract-v4를 폐기하지 않고 보존한 채, 특정 기업군에서 발생하던 과도한 저평가 왜곡을 줄이기 위한 보조/승격 계층을 추가했습니다. 시장가격은 내재가치 산식에 사용하지 않습니다.

## 핵심 원칙
- 현재 재무기초가치: TTM/정상화 EPS, 순자산(PBR), 잔여이익, 정상화 FCF, 그레이엄 결합가치의 독립 앵커를 사용합니다.
- 미래 증분가치: 기존 future-growth-v1.1.0의 객관적 게이트를 통과한 미래 총가치가 현재 재무기초가치를 초과하는 부분만 인정합니다.
- 이중계산 방지: `미래증분가치 = max(0, 미래총가치 - 현재재무기초가치)`로 정의합니다.
- 현재가 독립성: 현재가를 12만원과 240만원으로 바꾸는 회귀시험에서도 삼성전기의 재무적정가가 동일함을 검증했습니다.
- 회귀 억제: V1은 `beauty_consumer`와 강한 증거가 있는 `electronic_components`에만 적응형 승격을 허용합니다. 반도체 등 기존에 잘 작동하던 프로필은 V1에서 건드리지 않습니다.

## 산업분류 개선
기존에는 KSIC 20번대가 광범위하게 `materials`로 들어가 LG생활건강/아모레퍼시픽 같은 브랜드 소비재가 화학·소재 멀티플의 영향을 받을 수 있었습니다. V1은 세부 코드 20422/20423/20424를 `beauty_consumer`로 분리합니다. 회사명 하드코딩이 아닙니다.

## 실제 저장 스냅샷 재계산
- LG생활건강: 50,891원 → 276,183원 (현재 재무기초 276,183원, 미래 증분 0원)
- 아모레퍼시픽: 66,895원 → 130,230원 (현재 재무기초 91,684원 + 미래 증분 38,546원)
- 삼성전기: 274,948원 → 423,165원 (현재 재무기초 187,123원 + 미래 증분 236,042원)

68개 사용 가능 저장 스냅샷을 원본 엔진과 동일 입력으로 재계산했을 때 0.1% 이상 변한 종목은 위 3개뿐이고, 65개는 기존 v4 결과와 정확히 동일했습니다. 중앙값 변화배수는 1.0입니다.

## 해석 주의
이 패치는 시장가를 정답으로 학습하거나 시장가에 수렴시키지 않습니다. LG생활건강·아모레퍼시픽은 기존의 구조적 저평가 왜곡이 크게 줄었지만, 삼성전기는 127.8만원의 저장 시장가 대비 42.3만원으로 여전히 큰 괴리가 남습니다. 이는 현재 재무와 FY3/FY4까지의 객관적 성장 입력으로 설명할 수 없는 높은 시장 프리미엄을 임의로 적정가에 더하지 않았기 때문입니다.

따라서 이번 V1은 "괴리를 무조건 메우는 엔진"이 아니라 "잘못된 업종/실적 저점 고정/미래 성장 이중계산을 줄이고, 근거가 있는 미래 증분만 더하는 엔진"입니다.

## 검증
통과: compileall, valuation profiles, future growth model, valuation pipeline v4, valuation contract v4, industry profiles, insurance financials, signal bridge, SDI trough, universe catalog, sampling plan, adaptive fundamental value regression.

원본 ZIP 자체에서 이미 재현되는 별도 검증기 오류도 있습니다: cache coherence 인자 불일치, price pipeline import 불일치, stale latest index, forward/calibration output 파일 부재. 이번 패치 원인과 구분하기 위해 validation report에 기록했습니다.

## Strategic Forward V0.2 추가
Adaptive V1의 최종가를 즉시 다시 변경하지 않고, `analyzers/strategic_forward_value.py`가 별도의 Shadow 전략가치를 산출합니다. 산업·애널리스트 기대·검증된 글로벌 거시·감사 가능한 SOTP 자료가 있을 때만 미래 증분가치를 단계적으로 인정하며, 근거가 없으면 미래가치를 강하게 억제합니다. 자세한 내용은 `STRATEGIC_FORWARD_ENGINE_NOTES.md`와 `strategic_forward_validation_report.json`을 참조하세요.
