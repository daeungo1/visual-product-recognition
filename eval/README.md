---
title: PoC 관측 데이터 평가
description: 독립 정답 라벨로 식별, 정합 및 초심자 완주 지표를 계산하는 방법
ms.date: 2026-10-21
ms.topic: how-to
---

## 실행

프로젝트 루트에서 실제로 수집하고 라벨링한 JSON을 입력한다.

```powershell
python .\eval\run_eval.py .\eval\datasets\observations.json --output .\eval\reports\measured.json
```

러너는 Python 표준 라이브러리만 사용한다.
입력 파일을 자동 생성하지 않으며 입력 파일과 같은 경로로 덮어쓰지 않는다.
측정값이 없으면 `null`, `status=insufficient_data`와 경고를 반환한다.
입력 오류는 stderr에 설명을 쓰고 종료 코드 2를 반환한다.

현재 실제품 데이터와 실제품 성능 보고서는 없다.
테스트의 작은 인공 관측값은 계산식 단위 테스트용이며 PoC 결과가 아니다.

## 입력 구조

루트에는 아래 세 배열이 반드시 있어야 한다. 알 수 없는 필드와 중복 ID는 거부한다.

```json
{
  "identification": [],
  "alignment": [],
  "sessions": []
}
```

빈 배열은 형식 설명용으로 유효하지만 성공한 평가를 의미하지 않는다.
원본 촬영과 API 원시 응답은 별도로 보관하고 이 관측 형식으로 변환한다.
참가자 이름 대신 익명 ID를 사용한다.

### 식별 관측

| 필드 | 의미 |
|------|------|
| sample_id | 중복되지 않는 촬영 또는 식별 시도 ID |
| expected_model_id | 독립적으로 확인한 모델 ID, 미등록 대상은 null 허용 |
| candidate_model_ids | 자동 검색의 순서 있는 고유 모델 후보, 실패와 unknown은 빈 배열 |
| registered | 정답 모델이 당시 등록 목록에 있었는지 여부 |
| manual_selection | 사용자가 후보를 고르거나 모델을 수동 선택했는지 여부 |
| latency_ms | 기기에서 측정한 전체 식별 지연, 미측정이면 null |

등록 대상 전체 시도가 Top-1 및 Top-3 정확도의 분모다.
unknown이나 빈 후보를 분모에서 제외하지 않는다.
사람이 모델을 맞혀도 자동 후보를 수정하지 않고 수동 선택만 별도로 집계한다.
미등록 대상의 후보 발생률은 `unsupported_candidate_rate`다.
이는 자동 모델 확정률이나 검색 점수의 확률 보정을 뜻하지 않는다.

### 정합 관측

| 필드 | 의미 |
|------|------|
| frame_id | 중복되지 않는 프레임 ID |
| target_visible | 라벨러가 대상이 관찰 가능한 프레임이라고 확인했는지 |
| tracking_valid | 해당 프레임의 실제 FULL_TRACKING 여부 |
| overlay_visible | 실제 하이라이트 표시 여부 |
| predicted_center | 표시한 중심의 [x, y] 픽셀 좌표, 숨김 상태에서는 null |
| true_button_rect | 독립 정답 버튼 영역 [left, top, right, bottom], 대상 비관찰 시 null 허용 |
| observation_ms | 프레임이 대표하는 양수 관찰 시간 |
| tracking_ms | 추적 및 오버레이 처리 시간, 미측정이면 null |

중심 오차는 유클리드 픽셀 거리다.
정규화 오차는 이를 정답 버튼의 짧은 변 길이로 나눈 값이다.
p95는 정렬된 관측의 `(n - 1) * 0.95` 위치를 선형 보간하는 inclusive 방식이다.

정확한 안내 가용률의 분모는 `target_visible` 관찰 시간 전체다.
추적 실패와 하이라이트 누락을 분모에서 버리지 않는다.
분자는 유효 추적 및 실제 표시 상태이며 정규화 오차가 0.25 이하인 시간이다.
따라서 실패 프레임을 숨겨 p95만 좋게 만드는 경우도 가용률과 누락 수에 반영된다.
추적이 유효하지 않은데 표시한 프레임과 시야 밖 표시도 따로 집계한다.

### 사용자 시험

| 필드 | 의미 |
|------|------|
| participant_id | 익명 참가자 ID |
| scenario_id | 시험 시나리오 ID |
| novice | 해당 작업을 처음 수행하는 참가자인지 |
| completed | 작업 완료 여부 |
| assisted | 상담원 등 다른 사람의 도움을 받았는지 |
| elapsed_ms | 실패와 타임아웃도 포함한 시험 소요 시간 |
| manual_confirmations | 앱의 수동 확인 사용 횟수 |

같은 참가자와 시나리오의 중복 레코드는 거부한다.
최초 시험 기록을 사용하며 반복 시험은 별도 시나리오 또는 별도 분석으로 구분한다.
초심자의 완료 및 외부 도움 없음이 함께 만족되어야 무도움 완주로 계산한다.
앱의 수동 확인은 외부 도움과 다른 지표다.

시나리오별 참가자가 5명 미만이면 `meets_80_percent_target`은 null이다.
5명 이상일 때 무도움 완주율 80% 이상 여부를 계산한다.
작은 PoC의 관측 비율은 모집단 성능의 통계적 보증이 아니다.

## 검증

러너 구현 전 실패 테스트를 확인한 뒤 계산식을 구현했다.
아래 테스트 13개와 기존 Ruff 규칙을 통과했다.

```powershell
Set-Location .\server
uv run --no-sync pytest ..\eval\tests\test_eval.py -q
uv run --no-sync ruff check --config .\pyproject.toml ..\eval
```

검증에는 빈 데이터, 자동 및 수동 구분, 미지원 후보, 시간 가중 가용률,
오래된 하이라이트, 정규화 및 p95 경계, 초심자 4/5 완주,
부족한 참가자 수, NaN·무한대·잘못된 숫자와 중복 참가자가 포함된다.
