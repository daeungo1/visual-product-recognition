---
title: Visual Product Guide
description: GPT 기반 모바일 제품 조작 부위 Overlay PoC
---

## 모바일 카메라 앱

[카메라로 Visual Product Guide 테스트하기](https://azapi5ovedhtoyg74w.calmcoast-1ab8f441.swedencentral.azurecontainerapps.io/demo/login)

모바일 브라우저에서 링크를 열고 별도로 전달된 임시 접근 코드를 입력한다.

## 프로젝트 개요

카메라로 등록 제품을 비추면 검수된 필터 교체 절차의 현재 조작 부위를
Overlay로 안내하는 Android PoC를 새로 구축한다.

## 현재 상태

기존 합성 데모, 웹 데모, API, 인프라 코드는 제거했다. 루트 Git 이력과
고객 참고용 `VELA-photo-guide-lab-202610/VELA-photo-guide-lab` 저장소만 보존했다.
VELA 저장소의 코드와 고객 사진은 새 제품 코드에 복사하지 않는다.

새 구현은 다음 원칙을 따른다.

* GPT-6.1 Terra가 제품, 공식 가이드, 현재 단계와 조작 영역을 판단한다.
* GPT-6.1 Sol은 불확실한 사례의 선택적 재판정에만 사용한다.
* 모델은 절대 픽셀 좌표와 명시적인 `located`, `not_visible`, `uncertain`
  상태를 반환한다.
* 사용자가 후보 영역을 확인한 뒤 Android가 ARCore로 실시간 추적한다.
* 카메라 프레임을 지속적으로 업로드하지 않는다.
* 단계가 바뀌거나 추적이 끊기면 이전 Overlay를 즉시 폐기한다.
* 실제 제품 가이드는 정확한 모델, 공식 출처, 상태별 사진과 사람 검수를
  갖춘 뒤에만 게시한다.

## 문서

* [재구축 설계](docs/superpowers/specs/2026-11-01-visual-guide-rebuild-design.md)
* [구현 계획](docs/superpowers/plans/2026-11-01-visual-guide-rebuild.md)

## 다음 입력

첫 vertical slice에는 실제 제품 2~3개가 필요하다. 제품마다 정확한 모델코드,
공식 필터 교체 문서, 닫힌 상태, 열린 상태, 필터 노출 상태의 사용 권한 있는
원본 사진을 준비한다.

## 배포된 모바일 PoC

페이지는 후면 카메라 촬영 또는 사진 선택을 제공한다. 사진은 8MP 이하로
브라우저에서 축소되고 요청 단위로 GPT-6.1 Terra에 전달되며 API 서버에
보관되지 않는다. 이 화면은 위치 grounding 실험이며 공식 삼성 필터 교체
절차가 아니다.
