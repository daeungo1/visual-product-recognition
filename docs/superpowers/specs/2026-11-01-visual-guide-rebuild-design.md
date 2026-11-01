# Visual Guide Rebuild Design

## Intent

등록된 가전제품의 필터 교체 문제를 사용자가 설명하고 카메라로 제품을
보여주면, 앱이 검수된 절차의 현재 조작 부위를 Overlay로 안내한다.
첫 범위는 실제 제품 2~3개와 제품별 필터 교체 시나리오 하나다.

## Goals

* 정확한 모델코드와 공식 출처가 있는 제품만 지원한다.
* 현재 단계에 필요한 부품 하나만 찾고 안내한다.
* 모델의 불확실성과 대상 미검출을 명시적 비성공 상태로 처리한다.
* 사용자 확인 후 단말에서 Overlay를 추적한다.
* 조작 결과 상태를 확인한 뒤 다음 단계로 진행한다.
* 모델, 문서, 위치, 추적과 단계 검증을 독립적으로 평가한다.

## Non-goals

* 임의의 가전제품을 zero-shot으로 지원하지 않는다.
* GPT 또는 SAM을 카메라 매 프레임 호출하지 않는다.
* 실제 제품 사진 없이 YOLO 계열 모델을 학습하지 않는다.
* 공식 절차가 없는 문제를 모델 지식으로 보완하지 않는다.
* 무검수 좌표와 절차를 실제 제품 지원 기능으로 게시하지 않는다.
* 첫 단계에서 웹 데모, SQLite 데모 또는 Azure 인프라를 재구축하지 않는다.

## Constraints

* `core/src/commonMain`은 Android, ARCore, ML Kit, HTTP와 Azure SDK를 참조하지 않는다.
* 기본 추론 모델은 GPT-6.1 Terra다.
* GPT-6.1 Sol은 불확실한 사례의 선택적 재판정에만 사용한다.
* 모델 응답은 JSON Schema 기반 Structured Outputs를 사용한다.
* 위치는 전송 이미지 기준 절대 픽셀 `XYXY`와 중심점으로 표현한다.
* 모델 응답 상태는 `located`, `not_visible`, `uncertain`으로 제한한다.
* 연속 영상은 업로드하지 않고 사용자가 동의한 단계별 사진만 전송한다.
* 추적 상실, 일시 중지, 제품 변경과 단계 변경 시 Overlay를 숨긴다.
* 합성 자산과 실제 제품 자산을 동일 카탈로그에 섞지 않는다.
* VELA 고객 저장소의 코드, 문서와 사진은 참고 근거로만 사용한다.

## Approaches

### Selected approach

GPT가 검수된 가이드와 현재 상태를 판단하고 한 장의 사진에서 현재 부품의
point와 box를 제안한다. 서버는 여러 제안의 합의와 문서 적합성을 검사하고,
사용자가 후보를 확인한다. Android는 확인된 영역을 ARCore로 추적하며 단계
전환 시 이전 anchor를 폐기한다.

### Deferred approach

GPT의 작은 부품 위치 품질이 기준을 충족하지 못하면 SAM 3를 서버 측
영역 정제기로 추가한다. SAM 3는 단계당 한 번만 실행하며 런타임 추적기로
사용하지 않는다.

### Rejected approach

YOLOE는 AGPL-3.0이고 현재 실제 제품 라벨이 부족하므로 초기 제품 코드에서
제외한다. 서버 매 프레임 검출과 마지막 pose 기반 고정 Overlay도 제외한다.

## Architecture

```text
Android camera
  -> explicit snapshot consent
  -> FastAPI orchestration
     -> exact product and guide applicability gate
     -> GPT-6.1 Terra structured region proposal
     -> optional GPT-6.1 Sol adjudication
     -> consensus and refusal policy
  -> user confirms candidate
  -> Android ARCore tracking and Overlay
  -> OCR, visual state verification, or manual confirmation
  -> server-approved next step
```

## Domain contracts

### Guide

Each published guide contains exact applicable model codes, an official source,
review status and ordered steps. Each step defines the required state, action,
target part, expected state and verification mode.

### Region proposal

A region proposal contains the source image width and height, step identifier,
component identifier, status, point, box and evidence text. `point` and `box`
must be absent unless status is `located`.

### Session

The server owns the current step. Events are idempotent and may advance only the
current unfinished step. Manual, OCR and VLM evidence remain distinct.

### Tracking

The Android adapter publishes an Overlay only while the confirmed target has
current full tracking. Any generation, step, product or state change invalidates
the previous tracking evidence.

## Data and privacy

Product assets live in versioned, reviewed directories. Raw customer photos are
not committed. The API validates format, dimensions and size before model calls.
Request bodies, images, pairing codes and tokens are never logged.

## Evaluation

The evaluation set contains supported, unsupported, occluded, blurred,
wrong-model and target-absent cases. Metrics include guide applicability,
point-in-ground-truth, IoU thresholds, refusal accuracy, stale Overlay frames,
step-verification accuracy, latency and model cost.

## Rollout

The first milestone builds contracts and fake adapters without paid model calls.
The second compares GPT model variants on reviewed photos. The third integrates
the Android tracker. SAM 3 is added only if measured location quality requires it.
