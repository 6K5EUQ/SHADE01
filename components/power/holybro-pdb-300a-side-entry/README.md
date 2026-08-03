# Holybro Power Distribution Board (PDB) 300A — Side Entry

Holybro의 고전류 파워 분배 보드. 배터리 전원을 각 ESC(VTOL ×4, 크루즈 ×1)로 분배하는 역할. [Striver Mini VTOL](../../../airframes/striver-mini-vtol/README.md)의 [배전(Distribution) 캐빈](../../../airframes/striver-mini-vtol/README.md#부위별-사진-자료)에 장착되며, PNP 옵션에는 미포함이라 별도 구매한 부품.

- 제조사: Holybro
- 제품명: Power Distribution Board (PDB) 300A - Side Entry
- SKU: 18139
- 판매처: holybro.com, 단가 $25.00 (2026-08-02 확인)
- 공식 문서: https://holybro.com/products/power-distribution-board-pdb-300a-side-entry
- 용도: 배터리 → 각 ESC([MFE ESC 650](../../esc/mfe-esc-650-50a/README.md) ×4, [MFE ESC 6100](../../esc/mfe-esc-6s-100a/README.md) ×1) 전원 분배
- 호환: **PM08 시리즈 파워모듈과 호환** — [Holybro PM08-CAN](../holybro-pm08-can/README.md)과 함께 사용 가능

## 특징 (Features, 원문 요약)

- XT90 & XT30 사전 납땜(pre-soldered) 제공
- 연속 전류(Continuous Current): **300A**
- 순간 전류(Burst Current): **1000A**
- 10oz 구리 PCB 설계 — 고전류 부하에서 우수한 방열/전도성 확보
- M3 마운팅홀

## 커넥터 구성 (Side Entry 버전, SKU 18139)

| 커넥터 | 수량 | 방향 |
|---|---|---|
| XT90 | 5개 | 측면(side-facing) |
| XT30 | 2개 | 측면(side-facing) |
| 고전류 스크류 터미널(High current screw terminals) | — | BAT-IN 입력용 |

> Top Entry 버전(SKU 18138, 별도 제품)은 XT90 6개(상향) + XT30 2개(상향) + 스크류터미널 구성으로, 커넥터 방향(측면 vs 상향)만 다르고 나머지 스펙은 동일.

## 치수 (Dimensions)

| 항목 | 값 |
|---|---|
| 보드 크기 | 80×80mm |
| 커넥터 배치 간격 | 70×70mm (M3 마운팅홀 기준) |
| 보드 높이(측면 커넥터 돌출부 포함) | 약 20mm |
| 마운팅홀 | M3 |

상세 치수 도면 원본: [images/01-product-page-specs-dimensions.png](images/01-product-page-specs-dimensions.png)

## 연결 구조 (Striver 기체 기준)

```
배터리(6S LiPo) ──BAT-IN(스크류터미널)──► PDB 300A (Side Entry)
                                              │
                    ┌─────────────┬───────────┼───────────┬─────────────┐
                    ▼             ▼           ▼           ▼             ▼
              VTOL ESC #1   VTOL ESC #2  VTOL ESC #3  VTOL ESC #4  크루즈 ESC
              (XT90/XT30)   (XT90/XT30)  (XT90/XT30)  (XT90/XT30)  (XT90/XT30)
```

- 배터리 입력은 **BAT-IN 스크류 터미널**로 고정 (고전류 입력용)
- 각 ESC는 **XT90(고전류) 또는 XT30(저전류)** 커넥터로 분기 연결 — VTOL ESC(50A)/크루즈 ESC(100A) 모두 XT90 용량(90A 연속) 이내이므로 XT90 사용 권장
- [Holybro PM08-CAN](../holybro-pm08-can/README.md)과 공식 호환 확인됨 — PM08이 이 배터리 라인의 전압/전류를 센싱하는 구조로 추정 (정확한 분기 지점은 실물/매뉴얼 추가 확인 권장)

## 사진/자료

| 항목 | 파일 | 비고 |
|---|---|---|
| 제품 페이지 (외형, 가격, Top/Side Entry 비교, Feature, 치수도면) | [images/01-product-page-specs-dimensions.png](images/01-product-page-specs-dimensions.png) | holybro.com 제품 페이지 캡처 |

> 원본 자료는 holybro.com 제품 페이지의 풀페이지 스크린샷(PDF, 2페이지)이며, 이 문서에는 "You may also like" 이전까지의 제품 정보만 반영함.

## 보유 수량 (SHADE 기체)

- 1개, PNP 옵션에는 미포함되어 별도 구매
- 연결 대상: 배터리(BAT-IN), VTOL ESC ×4, 크루즈 ESC ×1, [PM08-CAN](../holybro-pm08-can/README.md)
