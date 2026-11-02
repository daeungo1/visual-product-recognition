---
title: Visual Product Guide
description: GPT 기반 모바일 제품 조작 부위 Overlay PoC
---

## 모바일 카메라 앱

[카메라로 Visual Product Guide 테스트하기](https://azapi5ovedhtoyg74w.calmcoast-1ab8f441.swedencentral.azurecontainerapps.io/demo/login)

모바일 브라우저에서 링크를 열고 별도로 전달된 임시 접근 코드를 입력한다.

## 프로젝트 개요

카메라로 검수된 제품을 비추면 공식 설명서 근거로 현재 조작 부위를
Overlay로 안내하는 모바일 브라우저 PoC다.

## 현재 상태

첫 지원 제품은 삼성 Bespoke AI 콤보 25/18kg 다크스틸
`WD80H25BHS`다. 공식 한국어 사용 설명서의 SHA-256, 모델 적용 범위와
페이지 근거를 reviewed registry에서 검증한다.

현재 구현은 다음 원칙을 따른다.

* 정확한 제품코드와 검수된 설명서가 일치해야 가이드를 사용한다.
* 세제함 전면 덮개와 조작부를 독립 target으로 분석한다.
* target마다 GPT-6.1 Terra 제안 세 개 중 두 개 이상이 공간적으로
  일치해야 위치를 승인한다.
* 합의하지 못한 target만 검수된 상대 위치로 crop해 한 번 재분석한다.
* 좌표는 전송 이미지 기준 절대 픽셀로 반환하고 crop 좌표는 서버가
  원본 좌표로 변환한다.
* `located`, `not_visible`, `uncertain`을 target마다 반환해 부분 성공을
  보존한다.
* P3의 SAM 3.1과 비디오 추적은 P0~P2 평가 이후로 보류한다.

## 문서

* [재구축 설계](docs/superpowers/specs/2026-11-01-visual-guide-rebuild-design.md)
* [구현 계획](docs/superpowers/plans/2026-11-01-visual-guide-rebuild.md)
* [WD80H25BHS P0-P2 설계](docs/superpowers/specs/2026-11-02-wd80h25bhs-p0-p2-design.md)
* [WD80H25BHS P0-P2 구현 계획](docs/superpowers/plans/2026-11-02-wd80h25bhs-p0-p2.md)

## WD80H25BHS 설명서 근거

* 18쪽은 조작부, 일반·선택 세제함과 세제함 전면 덮개를 제품 구성으로
  식별한다.
* 22쪽은 세제함 전면 덮개가 제품 전면 하단에 있으며 덮개 상단 가운데를
  눌러 연다고 설명한다.
* 27쪽은 조작부가 제품 전면 상단 가운데에 있다고 설명한다.

따라서 제품 상단 오른쪽 사각 덮개는 세제 투입구로 안내하지 않는다.

## 실사 평가

세 개의 제공 이미지에서 두 target을 각각 세 번 평가했다.

| Target | Located | Point-in-box | 평균 IoU | 최소 IoU | False not-visible |
|---|---:|---:|---:|---:|---:|
| 세제함 전면 덮개 | 9/9 | 9/9 | 0.781 | 0.636 | 0 |
| 조작부 | 9/9 | 9/9 | 0.684 | 0.636 | 0 |

요청 단위 지연은 p50 20.858초, 최대 26.111초였다. 세 catalog 이미지에서는
전체 사진 합의가 성립해 adaptive crop 재시도는 발생하지 않았다.

## 배포된 모바일 PoC

페이지는 후면 카메라 촬영 또는 사진 선택을 제공한다. 사진은 8MP 이하로
브라우저에서 축소되고 요청 단위로 GPT-6.1 Terra에 전달된다. 현재 화면은
검수된 설명서 근거를 사용하는 위치 grounding 실험이며 전체 세탁 절차를
대체하지 않는다.
