# Holybro PM08-CAN — Power Module (14S, 200A)

Holybro의 DroneCAN 파워모듈. 배터리 전압/전류를 센싱해 CAN 버스로 FC에 보고하고, FC에 전원을 공급하는 부품. [Striver Mini VTOL](../../../airframes/striver-mini-vtol/README.md)의 [배전 캐빈](../../../airframes/striver-mini-vtol/README.md#부위별-사진-자료)에 [PDB 300A](../holybro-pdb-300a-side-entry/README.md)와 함께 장착되며, PNP 옵션에는 미포함이라 별도 구매한 부품.

- 제조사: Holybro
- 제품명: PM08-CAN Power Module, 14S, 200A
- 공식 문서: https://docs.holybro.com/power-module-and-pdb/power-module-comparison
- 제품 페이지: https://holybro.com/products/dronecan-pm08-power-module-14s-200a
- 용도: 배터리 전압/전류 센싱(DroneCAN) + FC 전원 공급
- ⚠️ **본 기체에서는 FC 전원 이중화 불가** — [Pixhawk 6C Mini](../../fc/holybro-pixhawk-6c-mini/README.md)에 Power2 포트가 없음. 자세한 내용은 [FC 연결](#fc-연결-pixhawk-6c-mini) 참조
- **배선 위치: 배터리와 부하 사이 직렬(in-line)** — 자세한 내용은 [전력 경로](#전력-경로-inline-passthrough) 참조
- 작성 근거: 제품 페이지 스크린샷(PDF)이 없어 Holybro 공식 문서 MCP(`askQuestion`)로 조회한 텍스트 답변을 기반으로 작성함 (PDB 300A 문서는 실제 스크린샷 대조, 본 문서는 스크린샷 미확보 — 스펙 자체는 공식 문서 근거이나 이미지로 직접 검증하지는 못함). 전력 경로 구조는 Holybro 제품 페이지의 "Battery IN/OUT Options" 표기로 확인(2026-08-03).

## 사양

| 항목 | 값 |
|---|---|
| 프로세서 | STM32F405RG 168MHz, 1024KB Flash, 196KB RAM |
| 입력 전압 | 7–60.9V (2S–14S) |
| 연속 전류 | 200A |
| 순간 전류 | 400A @ 25℃ 1초 / 1000A @ 25℃ 1초 미만 |
| 최대 전류 센싱 범위 | 376A |
| 전압 정확도 | ±0.1V |
| 전류 정확도 | ±5% (Mission Planner 캘리브레이션으로 개선 가능) |
| 온도 정확도 | ±1℃ |
| **전력선 규격** | **8AWG (고연선 실리콘 절연)** — 모듈에 사전 결선되어 출고 |
| 동작 온도 | -25℃ ~ 85℃ |
| 부가 기능 | 갈바닉 절연 홀효과 전류센서(AEC-Q100 Grade 1), 고정밀 온도센서, 센서/BEC 보드 분리 설계(노이즈 저감), **CAN 종단저항 소프트웨어 토글**, 펌웨어 업그레이드·캘리브레이션 지원 |
| 가격 | $85.00 (2026-08-08 확인) / SKU 15030 |
| FC 전원 출력 | 5.2V(공식 스펙표) / **본체 실크 5.3V** / 최대 3A, 독립 회로 2계통 (본 기체에서는 1계통만 사용 — [FC 연결](#fc-연결-pixhawk-6c-mini) 참조) |
| 배터리 IN/OUT 커넥터 옵션 | XT90 / Tinned Wire(피복 벗긴 선) / XT90 + 링터미널 → **보유 개체는 XT90 + 링터미널 사양** (실물 사진 확인, 2026-08-04) |
| FC 연결 커넥터 | Molex CLIK-Mate 2mm, 6핀 — **본체에 `POWER1` / `POWER2` 2개 실장** (각 5.3V/3A, 실물 사진 확인). 공식 스펙표는 규격만 적고 개수를 생략 |
| 크기 / 무게 | 45×41×26mm (케이블 제외) / 185g (케이블 포함) |
| 케이스 | 알루미늄 (방열) |
| 통신 프로토콜 | DroneCAN |

## 전력 경로 (in-line passthrough)

**PM08은 배터리와 부하 사이에 직렬로 들어간다.** 배터리를 PDB에 직결하고 PM08을 옆에서 병렬로 따는 구조가 아니다. 그렇게 배선하면 전류 측정이 되지 않는다.

근거:

| 근거 | 의미 |
|---|---|
| Holybro 제품 페이지가 커넥터 옵션을 **"Battery IN/OUT Options"**로 명시 | IN/OUT 두 단자가 물리적으로 분리 존재 |
| 연속 200A / 순간 1000A **전류 정격**을 가짐 | 주 전류가 통과하므로 정격이 필요 (병렬 센싱탭이면 불필요한 스펙) |
| 최대 전류 센싱 376A + 알루미늄 방열 케이스 + 185g | 내부 션트 저항 발열 → 주 전류가 모듈을 관통 |

```
배터리(6S LiPo) — [Fullymax 6S 16000mAh (XT90-S)](../../batteries/fullymax-6s-16000mah/README.md)
   │  XT90-S ⟷ XT90
   ▼
PM08-CAN  [BAT IN: XT90] ──내부 션트──► [BAT OUT: 링터미널]
   │                                          │
   │  POWER1 (CLIK-Mate 2.0mm 6핀)            │  8AWG + 링터미널
   ├─► 5.3V/3A ──► FC Power1 (JST-GH 6핀)     │
   ├─► CAN 신호 ─► FC CAN1   (JST-GH 4핀)     │
   │   └ 분기 어댑터 케이블 필요               │
   │                                          ▼
   │  POWER2 ─► 미사용 (6C Mini에 Power2 없음)
                                    PDB 300A [BAT-IN 스크류터미널]
                                              │
                          ┌────┬────┬────┬────┴────┬────────┐
                        VTOL ESC ×4      크루즈 ESC   XT30→UBEC
```

**보유 개체 커넥터 (실물 사진 확인, 2026-08-04)**

| 단자 | 커넥터 | 성별 | 상대 |
|---|---|---|---|
| BAT IN | **XT90** (노란색) | **암(female)** — 마감면 평평, 핀 돌출 없음, 전선 쪽 수축 슬리브 칼라 (사진 판독 2026-08-08) | 배터리 [XT90-S **수**](../../batteries/fullymax-6s-16000mah/README.md#암수성별-대조--확인됨-제품-사진-판독-2026-08-08) → ✅ 그대로 체결 |
| BAT OUT | **링터미널** (압착 완료) | — (나사 체결) | PDB BAT-IN 스크류터미널 |
| POWER1 | CLIK-Mate 2.0mm 6핀 | — | FC Power1 + CAN1 (분기 필요) |
| POWER2 | CLIK-Mate 2.0mm 6핀 | — | 미사용 |

BAT OUT 쪽이 링터미널이므로 **PDB 스크류터미널과는 나사 조임으로 바로 체결**된다. 이 구간은 커넥터 병목이 없다.

BAT IN 쪽은 **암수 대조 확인 완료** — 배터리(수) ↔ PM08(암)으로 XT90 계열 관행에 맞는 정상 방향이며 변환 없이 체결된다. 단, **암수가 맞는 것과 전류 용량은 별개**로 아래 45A 병목은 그대로 남는다.

### ⚠️ 전류 용량 주의

1. **시스템 상한은 PM08의 200A** — PDB는 300A지만 직렬 경로상 PM08이 병목. Striver Mini 4+1 구성의 이론상 피크는 VTOL 4×50A + 크루즈 100A = 300A이므로, 실사용(호버 상승 시 순간 최대) 전류가 200A를 넘지 않는지 확인 필요.
2. ⚠️ **배터리 → PM08 구간이 XT90이라 실제 병목** — Holybro 공식 [Connector & Wire Rating](https://docs.holybro.com/power-module-and-pdb/power-module/connector-and-wire-rating) 기준 XT90은 10AWG에서 **연속 45A / 순간 90A**.
   - 보유 개체는 BAT IN이 XT90, 배터리도 [XT90-S](../../batteries/fullymax-6s-16000mah/README.md)이므로 **이 구간이 45A로 제한**된다. 7kg급 VTOL 호버링 전류는 이를 크게 상회한다.
   - BAT OUT(링터미널) → PDB(스크류터미널) 구간은 병목 없음.
   - **대책**: ① 배터리·PM08 양쪽 커넥터를 AS150/XT120급으로 교체, ② 또는 이륙·상승 시 단시간 초과로 간주하고 **첫 비행 후 커넥터 발열 반드시 확인**. XT90-S는 스파크 방지 저항이 내장되어 일반 XT90보다 발열에 불리할 수 있다.

## FC 연결 (Pixhawk 6C Mini)

Holybro 공식 문서 기준 PM08-CAN은 **"CAN 버스를 가진 모든 Pixhawk 표준 FC"**에 적용 가능하며, [Pixhawk 6C Mini](../../fc/holybro-pixhawk-6c-mini/README.md)는 CAN1/CAN2를 보유하므로 **호환 성립**. 단, 공식 문서가 6C Mini를 호환 모델로 명시적으로 열거하지는 않음 (2026-08-03 Holybro 문서 MCP 조회).

⚠️ **무개조 플러그앤플레이가 아님.** 아래 두 가지 제약이 있다.

### 1. 커넥터 규격/핀 수 불일치 → 분기 케이블 필요

PM08은 전원과 CAN을 **한 개의 6핀 커넥터에 통합**해 내보내지만, 6C Mini는 이를 **두 개의 다른 포트**로 나눠 받는다. 커넥터 규격도 서로 다르다.

| 구분 | PM08-CAN 쪽 | Pixhawk 6C Mini 쪽 |
|---|---|---|
| 커넥터 | Molex CLIK-Mate **2.0mm** | JST-GH **1.25mm** |
| 포트 | Power & CAN 통합 **6핀** 1개 | CAN1 **4핀** + Power1 **6핀** (2개로 분리) |

따라서 PM08 6핀 → (CAN 4핀 + Power 6핀) **분기 어댑터 케이블**이 필요하다.

6C Mini 측 포트 핀맵:

| CAN1 (4핀) | 신호 |
|---|---|
| 1 | VCC |
| 2 | CAN1_H |
| 3 | CAN1_L |
| 4 | GND |

| Power1 (6핀) | 신호 |
|---|---|
| 1–2 | VDD5V_BRICK1 (in) |
| 3 | CURRENT1 |
| 4 | VOLTAGE1 |
| 5–6 | GND |

> CURRENT1/VOLTAGE1은 아날로그 파워모듈용 센싱 핀. PM08은 센싱을 CAN으로 보내므로 이 두 핀은 미사용으로 남을 것으로 보이나, 실물 검증 필요 ([확인 필요](#-확인-필요) 참조).

#### PM08 POWER1 / POWER2 6핀 배열 — ✅ 확정

Holybro 제품 페이지 **Pinout 도해**로 확인 (2026-08-08). POWER1·POWER2 **동일 배열**.

| 핀 | 신호 | → Pixhawk 6C Mini |
|---|---|---|
| 1 | **5V** | Power1 핀1 (VDD5V_BRICK1) |
| 2 | **5V** | Power1 핀2 (VDD5V_BRICK1) |
| 3 | **CAN-H** | **CAN1 핀2** (CAN1_H) |
| 4 | **CAN-L** | **CAN1 핀3** (CAN1_L) |
| 5 | **GND** | Power1 핀5 |
| 6 | **GND** | Power1 핀6 + **CAN1 핀4** (GND 공유) |

> 출처: [03-product-page-pinout.pdf](images/03-product-page-pinout.pdf) p.2 "Pinout" 섹션 — 커넥터 실물 사진 아래 핀 배열 도해에 `5V / 5V / CAN-H / CAN-L / GND / GND` 표기.

**분기 케이블 결선표** (PM08 6핀 → FC 2포트):

```
PM08 POWER1                    Pixhawk 6C Mini
─────────────                  ────────────────
1 (5V)    ──────────────────►  Power1 핀1
2 (5V)    ──────────────────►  Power1 핀2
5 (GND)   ──────────────────►  Power1 핀5
6 (GND)   ──┬───────────────►  Power1 핀6
            └───────────────►  CAN1 핀4 (GND)
3 (CAN-H) ──────────────────►  CAN1 핀2
4 (CAN-L) ──────────────────►  CAN1 핀3
                               CAN1 핀1 (VCC) — 미결선(주1)
                               Power1 핀3·4 (CURRENT1/VOLTAGE1) — 미결선(주2)
```

- **주1**: 6C Mini CAN1 핀1(VCC +5V)은 CAN 주변장치에 전원을 공급하는 출력. PM08은 자체 전원으로 동작하므로 연결하지 않는다. 연결하면 5V 소스가 충돌할 수 있다.
- **주2**: Power1 핀3·4는 아날로그 파워모듈용 센싱 핀. PM08은 센싱을 CAN으로 보내므로 비워둔다.
- GND는 Power1·CAN1 양쪽에 필요하므로 PM08 6번 핀에서 분기하거나, 5·6번을 나눠 쓴다.

### 2. FC 전원 이중화 불가

**Pixhawk 6C Mini에는 Power2 포트가 없다** (표준 Pixhawk 6C에는 존재하나 Mini에서는 제외됨 — Holybro "Pixhawk 6C Mini Difference" 문서). PM08이 독립 5.2V 2계통을 제공해도 FC가 한 계통만 수용하므로, **이 조합에서 FC 전원 이중화는 성립하지 않는다.** PM08의 2번 출력은 유휴로 남는다.

Striver 기체의 [배전 캐빈 사양](../../../airframes/striver-mini-vtol/README.md#구조캐빈별-사양)에 "2채널 이중화 비행제어 전원 공급(옵션)"이 있으나, 이는 FC 쪽 입력이 2개일 때 성립하는 것이므로 6C Mini로는 활용 불가.

### 3. 파라미터 설정

연결 후 파라미터 설정 필요:

| 펌웨어 | 설정 |
|---|---|
| PX4 | `UAVCAN_ENABLE=2`, `UAVCAN_SUB_BAT=2`, `BAT1_SOURCE=External` → 전원 재인가 재시작 |
| ArduPilot | `CAN_P1_DRIVER=1`, `CAN_SLCAN_CPORT=1`, `BATT_MONITOR=8`, `BATT_OPTIONS=1` → 전원 재인가 재시작 |

### PDB 연결

[Holybro PDB 300A Side Entry](../holybro-pdb-300a-side-entry/README.md) 제품 페이지에 **"PM08 시리즈 파워모듈과 호환(compatible with PM08 series power modules)"**이라고 명시되어 있어 두 부품의 조합 사용이 공식 확인됨.

배선 순서는 **배터리 → PM08(BAT IN → BAT OUT) → PDB BAT-IN 스크류터미널 → 각 ESC**. PM08이 직렬로 들어가므로 PDB는 PM08의 OUT 쪽에 위치한다 ([전력 경로](#전력-경로-inline-passthrough) 참조).

## 🔶 확인 필요

- ~~PM08과 PDB 300A 간 정확한 배선 순서~~ → **해소(2026-08-03)**: 제품 페이지 "Battery IN/OUT Options" 표기로 직렬(in-line) 구조 확인
- ~~Pixhawk 6C Mini와의 호환 여부~~ → **해소(2026-08-03)**: 공식 문서상 CAN 버스 보유 Pixhawk 표준 FC에 적용 가능, 6C Mini는 CAN1/CAN2 보유 → 호환. 단 [분기 케이블 필요 + 이중화 불가](#fc-연결-pixhawk-6c-mini)
- ~~보유 개체의 실제 IN/OUT 커넥터 옵션~~ → **해소(2026-08-04)**: 실물 사진으로 **XT90(BAT IN) + 링터미널(BAT OUT)** 사양 확인. BAT OUT→PDB는 병목 없으나, **배터리→PM08 XT90 구간이 45A 병목으로 남음** ([전류 용량 주의](#️-전류-용량-주의) 2항)
- ~~PM08 6핀 커넥터의 핀 배열 미확보~~ → **해소(2026-08-08)**: 제품 페이지 Pinout 도해로 `5V / 5V / CAN-H / CAN-L / GND / GND` 확정. [결선표](#pm08-power1--power2-6핀-배열---확정) 참조
- ~~배터리 ↔ PM08 BAT IN 암수 대조~~ → **해소(2026-08-08)**: 제품 사진 판독으로 **배터리 XT90-S = 수(male), PM08 BAT IN = 암(female)** 확인 → 변환 없이 체결 가능. XT90 계열 관행에 맞는 정상 방향이며, XT90-S의 프리차지 저항은 수 커넥터 측 내장이라 일반 XT90 암과 물려도 스파크 방지 정상 작동. **단 전류 병목(연속 45A)은 그대로 남음** ([전류 용량 주의](#️-전류-용량-주의) 2항)
- ⚠️ **분기 케이블은 동봉되지 않음** — 제품 사진상 모듈에는 **8AWG 전력선 2가닥만 사전 결선**되어 있고, POWER1/POWER2는 **기판 실장 소켓**이다. "Weight 185g (Include Cable)"의 Cable은 이 전력선을 가리킨다. 즉 **PM08 6핀 → (FC Power1 6핀 + FC CAN1 4핀) 분기 케이블은 자작 또는 별도 구매가 필요**하다.
  - 필요 부품: Molex CLIK-Mate 2.0mm 6핀 하우징+압착단자, JST-GH 1.25mm 6핀·4핀 하우징+압착단자, 28AWG 전선
  - 참고: 제품 페이지 "You may also like"에 [CAN Hub $27.59](https://holybro.com/products/can-hub) 노출 — CAN 노드가 늘어날 때 배선 정리용으로 검토 가능
- **Power1의 CURRENT1/VOLTAGE1 미결선 상태로 CAN 센싱만 동작하는지 실물 검증** — 이론상 문제없으나 파라미터 설정과 함께 확인 필요
- Power1의 CURRENT1/VOLTAGE1(아날로그 센싱 핀)을 미사용으로 두고 CAN 센싱만으로 동작하는지 파라미터 설정과 함께 검증 필요
- 실제 Striver 기체의 배전 캐빈 구조([08-distribution-cabin.png](../../../airframes/striver-mini-vtol/images/08-distribution-cabin.png))와 대조해 물리적 배치 확인 필요

## 보유 수량 (SHADE 기체)

- 1개, PNP 옵션에는 미포함되어 별도 구매
- 연결 대상: [Holybro Pixhawk 6C Mini](../../fc/holybro-pixhawk-6c-mini/README.md) CAN1 + Power1(1계통만), [PDB 300A Side Entry](../holybro-pdb-300a-side-entry/README.md)
- ⚠️ 분기 어댑터 케이블 필요, FC 전원 이중화 불가 ([FC 연결](#fc-연결-pixhawk-6c-mini) 참조)
