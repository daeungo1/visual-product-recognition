---
title: Visual Guide 연결형 PoC API 계약
description: Android와 실제 Azure 어댑터가 공유하는 HTTPS, 단말 페어링, 식별 및 세션 계약
ms.date: 2026-10-26
ms.topic: reference
---

## 범위와 인증

기존 로컬 데모 경로는 유지한다. 연결형 경로는 `/v1`을 사용한다.
클라우드 모드는 Cosmos, 비공개 Blob, AI Search, SigLIP2와 실제 Foundry 모델을 사용한다.
설정이나 호출이 실패하면 오류를 반환하며 SQLite, 임의 후보 또는 고정 판정으로 대체하지 않는다.

휴대폰은 운영자가 발급한 일회용 무작위 페어링 코드로 접속한다.
코드와 bearer token의 원문은 서버 데이터베이스에 저장하지 않고 해시만 저장한다.
코드는 한 번만 사용할 수 있고, 단말 토큰에는 만료와 device 또는 admin 범위가 있다.
일반 단말은 자신의 세션만 읽고 진행할 수 있다.
APK에는 관리자 코드, Azure 키 또는 토큰을 포함하지 않는다.
이 페어링은 PoC 단말 등록용이며 기업 사용자 SSO를 구현했다고 표시하지 않는다.

## 페어링

`POST /v1/pair`는 인증 없이 HTTPS로 호출한다.
코드 길이는 8~256자다. Android도 전송 전에 같은 한도를 검사하고
제어문자를 거부하며 입력을 몰래 잘라 다른 코드로 전송하지 않는다.

```json
{"code":"operator-issued-one-time-random-code"}
```

성공 응답은 다음 필드를 가진다.

```json
{
  "token_type": "Bearer",
  "access_token": "opaque-device-token",
  "expires_in": 86400,
  "device_id": "uuid",
  "scope": "device"
}
```

이후 `/v1` 요청에는 `Authorization: Bearer <access_token>`을 사용한다.
잘못되거나 소비되거나 만료된 코드는 401, 과도한 시도는 429로 처리한다.
동일 코드를 동시에 소비하는 두 요청이 모두 성공해서는 안 된다.

## 카탈로그와 가이드

`GET /v1/catalog`는 기존 카탈로그 형식을 유지한다.
`GET /v1/guides/{id}`도 기존 `id`, `target_id`, `title`, `demo`, `steps` 형식을 유지한다.
각 단계는 `id`, `button_id`, `instruction`, `expected_display`를 가진다.
게시 가이드 제목은 1~500자, 단계는 1~128개이며 단계 ID는 고유해야 한다.
Android DTO와 Python 계약의 경계값을 양쪽 단위 테스트로 검증한다.
실제품 가이드는 적용 모델, 공식 출처와 검수 상태가 있는 자산만 게시한다.

`GET /v1/models/{target_id}`의 연결형 타깃 형식은 다음과 같다.
좌표 값은 구조 설명용이며 실제 값은 기존 승인된 패널 지도를 변환해 사용한다.

```json
{
  "id": "original-demo-remote-v1",
  "reference_width_m": 0.16,
  "reference_image_url": "/v1/models/original-demo-remote-v1/reference",
  "image_width": 1000,
  "image_height": 1600,
  "display": {"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.3},
  "buttons": {
    "power": {"left": 0.1, "top": 0.4, "right": 0.9, "bottom": 0.5}
  }
}
```

`GET /v1/models/{target_id}/reference`는 인증된 이미지 바이트를 반환한다.
위 `reference_image_url`은 같은 API 원점의 상대 경로이며 외부 URL로 토큰을 보내지 않는다.

## 실제 이미지 식별

`POST /v1/identify`:

```json
{
  "category": "aircon",
  "target_kind": "remote",
  "image_base64": "raw-base64-jpeg-or-png",
  "ocr_text": ""
}
```

카테고리는 `aircon`, `tv`, `airdresser`, 대상은 `body`, `remote`, `screen`이다.
입력 바이트와 해상도를 제한한다.
SigLIP2 이미지 임베딩으로 AI Search를 조회한 뒤 실제 VLM으로 후보의 시각적 적합성을 확인한다.
VLM이 등록되지 않은 제품 ID를 만들어 반환해서는 안 된다.

```json
{
  "status": "candidates",
  "requires_confirmation": true,
  "candidates": [
    {
      "product_id": "demo-aircon",
      "model": "Original synthetic demo",
      "target_id": "original-demo-remote-v1",
      "guide_ids": ["demo-aircon"],
      "search_score": 1.0,
      "demo": true
    }
  ],
  "provider": "siglip2-search-vlm"
}
```

등록 대상과 맞지 않으면 `status=unknown`, 빈 후보 목록,
`requires_confirmation=false`를 반환한다.
검색 점수는 모델 식별 확률이 아니다. 후보는 사용자가 확인하며 공용 리모컨만으로
정확한 본체 모델이 증명됐다고 처리하지 않는다.

## 세션과 진행

`POST /v1/sessions`, `GET /v1/sessions/{id}`,
`POST /v1/sessions/{id}/events`는 기존 요청 및 응답 형식을 유지한다.
서버는 세션의 소유 단말, 현재 단계와 중복 이벤트 ID를 검사한다.
같은 ID와 같은 입력은 같은 결과를 반환하고 같은 ID에 다른 입력을 재사용하면 409다.
Cosmos의 조건부 쓰기로 동시 진행과 중복 소비를 방지한다.

진행 이벤트는 다음 형식이다.

```json
{
  "event_id": "uuid",
  "step_id": "power",
  "source": "manual",
  "observed_text": null,
  "verification_id": null
}
```

`source`는 `manual`, `ocr`, `vlm`이다.
OCR 진행은 현재 단계의 목표 문구와 일치하는 관측이 있어야 한다.
VLM 진행에는 서버에서 현재 단계에 발급한 만료 전 확인 ID가 필요하다.
클라우드 모드의 앱은 서버의 승인 없이 다음 단계가 완료됐다고 표시하지 않는다.

## VLM 확인

`POST /v1/sessions/{id}/verify`:

```json
{"step_id":"power","image_base64":"raw-base64-display-crop"}
```

응답:

```json
{
  "status": "pass",
  "step_id": "power",
  "reason": "Expected display state is visible.",
  "verification_id": "short-lived-proof-id",
  "expires_in": 30,
  "model_deployment": "guide-verify"
}
```

`status`는 `pass`, `fail`, `unsure`다. pass 외에는 유효한 진행 증거를 발급하지 않는다.
사진 판정은 자동으로 세션을 진행하지 않으며 뒤따르는 이벤트 요청에서 증거를 소비한다.
지연된 이전 단계의 응답은 다음 단계를 완료시킬 수 없다.

## 운영자 기능

운영자 CLI는 Azure CLI 자격 증명으로 기준 이미지, 검수된 가이드와 패널 지도를 등록한다.
일반 단말은 원본 자산을 등록하거나 검색 인덱스를 수정할 수 없다.

`POST /v1/admin/reindex`는 admin 범위에서만 허용한다.
검수된 등록 이미지로 실제 임베딩을 계산해 AI Search에 업로드한다.
응답에는 인덱싱 건수, 차원과 모델 버전을 표시한다.

`POST /v1/admin/draft-guide`는 admin 범위에서만 허용한다.
출처 URL, 텍스트, 적용 모델을 입력받아 실제 작성 모델로 초안을 만든다.
응답은 반드시 `review_status=draft`이며 자동으로 실제품 카탈로그에 게시하지 않는다.

## 상태와 오류

`/healthz`는 익명 liveness, `/readyz`는 구성한 모드의 실제 의존성 준비 상태다.
클라우드 모드의 `/readyz`는 모델 로드, Cosmos와 Search 준비를 확인한다.
미설정, 서비스 장애와 시간 초과는 구분된 503 및 504로 표면화한다.
401 인증, 404 미등록 또는 다른 소유자의 세션, 409 순서 또는 재사용 충돌,
413 크기 초과, 429 과부하를 성공 응답으로 바꾸지 않는다.
