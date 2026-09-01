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
배터리(6S LiPo)
      │
      ▼
[PM08-CAN]  BAT IN ──내부 션트──► BAT OUT     ← 파워모듈이 직렬로 선행
      │                              │
      └─► CAN/5.2V ──► FC            ▼
                        BAT-IN(스크류터미널) ──► PDB 300A (Side Entry)
                                              │
                    ┌─────────────┬───────────┼───────────┬─────────────┐
                  (XT90)        (XT90)      (XT90)      (XT90)       (XT90)   ← PDB 출력단
                    ┆             ┆           ┆           ┆             ┆
                    ┆   ⚠️ 변환 필요 (ESC 측은 링터미널, XT90 아님)      ┆
                    ▼             ▼           ▼           ▼             ▼
              VTOL ESC #1   VTOL ESC #2  VTOL ESC #3  VTOL ESC #4  크루즈 ESC
             (OT2.5-4 링터미널)                                  (OT2.5-4 링터미널)
```

### ✅ PDB ↔ ESC 커넥터 불일치 — 납땜 개조로 해소 (2026-08-31)

**PDB 출력단은 XT90인데, 보유 ESC 5개는 전원 입력선 끝단이 전부 `OT2.5-4 냉간압착 링터미널`이다.** 암수 문제가 아니라 **커넥터 종류 자체가 다르므로** 그대로는 연결되지 않는다.

| 부품 | 전원 입력 끝단 | 출처 |
|---|---|---|
| VTOL ESC ×4 ([MFE ESC 650 50A](../../esc/mfe-esc-650-50a/README.md#커넥터--단자-구성)) | 16AWG, **OT2.5-4 링터미널** 압착 | 문서 기재 + [product-photos.webp](../../esc/mfe-esc-650-50a/images/product-photos.webp) 실물 사진에서 적색선 끝 링터미널 확인 |
| 크루즈 ESC ×1 ([MFE ESC 6S 100A](../../esc/mfe-esc-6s-100a/README.md#커넥터--단자-구성)) | 12AWG, **OT2.5-4 링터미널** 압착 | 문서 기재 |

PDB의 스크류터미널은 **BAT-IN 입력 전용 1개소**라 ESC 5개를 여기에 물릴 수 없다.

**조치 (완료)** — ESC 측 링터미널을 잘라내고 커넥터를 **직접 납땜**했다. 어댑터 케이블을
거치지 않으므로 접점이 늘어 생기는 발열 지점도 없다. 기체는 이 상태로 비행 중이다.

> 🔴 **전류 정격 문제는 그대로 남아 있고, 실측으로 확인됐다.** 커넥터를 연결 가능하게
> 만들었을 뿐 정격을 올린 것이 아니다. 2026-08-31 비행(453초) 실측:
> **최대 66.8A**, 그중 **270초(60%)를 XT90 연속 정격 45A 위에서** 보냈고 최장 24초 연속이다.
> 예외적 피크가 아니라 정상 운용 영역이 정격을 넘는다 —
> **XT120/AS150 급 교체가 권고가 아니라 필요 항목이다.**
> ([비행 기록](../../../flights/2026-08-31-ground-tests.md))

- **PDB는 [PM08-CAN](../holybro-pm08-can/README.md)의 하류(BAT OUT 쪽)에 위치.** PM08은 배터리와 PDB 사이 직렬(in-line) 연결이며, PDB 입력단에서 병렬 센싱탭을 따는 구조가 아님 (Holybro 제품 페이지 "Battery IN/OUT Options" 표기로 확인, 2026-08-03)
- PDB 배터리 입력은 **BAT-IN 스크류 터미널**로 고정 (고전류 입력용) — PM08의 BAT OUT을 여기에 연결
- 각 ESC는 **XT90** 커넥터로 분기 연결. VTOL ESC(50A) 4개는 XT90 연속 정격 45A를 소폭 상회하므로 순간 정격(90A) 범위 내 단시간 운용으로 간주하되 발열 확인 권장. 크루즈 ESC(100A)는 XT90 연속 정격을 크게 초과하므로 **XT120/AS150급 커넥터 또는 8AWG 직결 검토 필요**
- XT30(2개)은 저전류 주변장치(서보 전원, 탑재장비 등)용으로 사용

> ⚠️ **커넥터 정격 주의**: Holybro 공식 [Connector & Wire Rating](https://docs.holybro.com/power-module-and-pdb/power-module/connector-and-wire-rating) 기준 — XT60 30A / XT90 45A / XT120 60A / AS150 75A / AS300 150A (모두 연속 기준). 보드 자체가 300A를 견뎌도 **커넥터가 병목**이 된다. 배터리 → PM08 → PDB 주 간선은 링터미널 + 8AWG 이상 권장.

## 사진/자료

| 항목 | 파일 | 비고 |
|---|---|---|
| 제품 페이지 (외형, 가격, Top/Side Entry 비교, Feature, 치수도면) | [images/01-product-page-specs-dimensions.png](images/01-product-page-specs-dimensions.png) | holybro.com 제품 페이지 캡처 |

> 원본 자료는 holybro.com 제품 페이지의 풀페이지 스크린샷(PDF, 2페이지)이며, 이 문서에는 "You may also like" 이전까지의 제품 정보만 반영함.

## 보유 수량 (SHADE 기체)

- 1개, PNP 옵션에는 미포함되어 별도 구매
- 연결 대상: [PM08-CAN](../holybro-pm08-can/README.md) BAT OUT → PDB BAT-IN(스크류터미널), 출력 → VTOL ESC ×4 + 크루즈 ESC ×1
- ⚠️ 배터리는 PDB에 직결하지 않고 **PM08을 거쳐서** 들어온다 ([연결 구조](#연결-구조-striver-기체-기준) 참조)
