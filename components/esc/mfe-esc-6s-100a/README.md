# MFE ESC 6100 — 6S 100A (크루즈 모터용)

Makeflyeasy(MFE)에서 Striver Mini VTOL/고정익 시리즈용으로 제작한 브러시리스 ESC. [Striver Mini VTOL](../../../airframes/striver-mini-vtol/README.md)의 **크루즈(추진) 모터**([MFE X4120 KV430](../../motors/mfe-x4120-kv430/README.md)) 구동에 사용되며, 보유 기체(PNP 옵션)에 **1개 포함**되어 있다.

- 제조사: Makeflyeasy (MFE)
- 제품명: "Makeflyeasy 6S 100A ESC Adapted Striver Mini VTOL or Fixed Wing"
- 모델: MFE ESC 6100 (문서 내 배선도 표기 기준. 유사 라인업으로 MFE ESC 1260도 병기됨)
- 판매처: uavmodel.com (UAVMODEL CO., LIMITED, Hong Kong), 단가 $75.70 (2026-08-02 확인)
- 옵션: "striver mini fixed wing 6S 100A" / "striver mini VTOL 6S 100A" 두 배리에이션으로 판매됨 (동일 ESC, 기체 타입별 태깅 차이로 추정)
- 용도: Striver Mini VTOL 크루즈(전방 견인) 모터 또는 순수 고정익기 추진 모터 구동
- 장착 위치: [헤드 캐빈(기수)](../../../airframes/striver-mini-vtol/README.md#부위별-사진-자료) — ESC 내장형, 최대 지원 사이즈 71×38mm

## 성능 사양 (Product Parameters, 원문 기준)

| 항목 | 값 |
|---|---|
| 배터리 | 6S LiPo |
| 연속 전류 | 100A |
| 순간 전류 (10초) | 120A |
| 전원선(Power cable) | 12AWG, 25cm |
| 모터선(Motor Cable) | 12AWG, 42cm |
| 신호선(Signal Cable) | 30선 흑백 트위스트 페어, 46cm |
| 바나나 플러그(Banana head) | 4.0mm 암 커넥터 |
| 냉전압착 단자(Cold Pressed Terminals) | OT2.5-4 |
| 크기 | 74×37×16mm |
| 무게 | 85g |

> Striver Mini VTOL 기체의 크루즈 모터는 [MFE X4120 KV430](../../motors/mfe-x4120-kv430/README.md)(권장 ESC 6S 80–100A)이며, 본 ESC(6S 100A)는 그 권장 범위 상단에 해당해 정상 매칭됨. [구성 리스트](../../../airframes/striver-mini-vtol/README.md#부품-구성-리스트-configuration-list)상 크루즈 ESC 규격(6S 100A)과도 일치.

## 외형 / 단자 구성

기판 외장은 방열 그릴 형태의 알루미늄/플라스틱 하우징(핀 방열 구조)이며, 다음 케이블이 인출된다.

| 커넥터 | 케이블 규격 | 용도 |
|---|---|---|
| 메인 전원 입력(+/−) | 12AWG, 25cm, 끝단 OT2.5-4 냉간압착 단자 | 배터리/파워버스 연결 |
| 모터 출력 3상 | 12AWG, 42cm, 끝단 4.0mm 바나나 플러그(암) | 모터 U/V/W상 |
| 시그널 케이블 | 30선 흑백 트위스트 페어, 46cm | 수신기/FC PWM 신호 입력 |

#### 시그널 커넥터 실물 확인 (2026-08-14)

**3핀 하우징(Harwin Inc. 각인 추정)이며, 양쪽 끝 2핀만 결선되고 가운데 핀은 비어 있다.**

| 핀 위치 | 선 | 용도 | FC 연결 |
|---|---|---|---|
| 끝 | **흰색** | Signal | 채널의 `S` 핀 |
| **가운데** | **없음(빈 슬롯)** | — | `+`(VDD_SERVO) 미사용 |
| 끝 | **검은색** | GND | 채널의 `−` 핀 |

- FC PWM 헤더에 **그대로 꽂힘 — 별도 가공 불필요**.
- `+`를 쓰지 않는 이유: ESC는 [PDB 300A](../../power/holybro-pdb-300a-side-entry/README.md)에서 직접 전원을 받으므로 FC 서보 레일(UBEC 5.3V)이 불필요. GND는 **신호 기준점**으로 필요.
- ⚠️ **가운데가 비어 있어 뒤집어도 물리적으로 꽂힌다.** 뒤집으면 신호↔GND가 반대가 되어 **ESC가 신호를 못 받는다**(가운데 `+`가 비어 있어 소손은 없고 모터만 안 돎). 꽂기 전 FC 실크스크린으로 `S` 핀 위치 확인 후 **흰색을 `S` 쪽**으로 맞출 것.
- ⚠️ [MFE UBEC](../../power/mfe-ubec-3s14s-10a/README.md) 출력 커넥터와 혼동 금지 — UBEC은 반대로 `+`/`−`만 결선되어 있고, 그쪽은 뒤집어 꽂으면 실제로 손상된다.

### 커넥터 궁합 (2026-08-08 확인)

**① 전원 입력 ↔ [PDB 300A](../../power/holybro-pdb-300a-side-entry/README.md#-pdb--esc-커넥터-불일치--납땜-개조로-해소-2026-08-31) — ✅ 납땜 개조로 해소 (2026-08-31)**

본 ESC의 전원 입력은 원래 **OT2.5-4 링터미널**이고 PDB의 ESC 출력단은 **XT90** 이라 그대로는 연결할 수 없었다. 링터미널을 잘라내고 커넥터를 **직접 납땜**하여 해소했다 (2026-08-31).

특히 본 ESC는 **100A 정격으로 XT90의 연속 45A를 크게 초과**한다. 어차피 커넥터를 가공해야 하는 상황이므로, XT90으로 맞추기보다 **XT120/AS150급 커넥터 또는 8AWG 직결**로 올리는 편이 합리적이다 ([PDB 연결 구조](../../power/holybro-pdb-300a-side-entry/README.md#연결-구조-striver-기체-기준) 참조).

**② 모터 출력 3상 ↔ 크루즈 모터 — ⚠️ ESC 측만 확정**

| 쪽 | 커넥터 | 성별 | 근거 |
|---|---|---|---|
| 본 ESC | 4.0mm 바나나 | **암(female)** ✅ | 원문 스펙 기재 |
| [MFE X4120 KV430](../../motors/mfe-x4120-kv430/README.md) | 미상 | **미확인** | 모터 문서에 커넥터 규격 기재 없음("12AWG, 100mm"만), 제품 사진·엔지니어링 도면 모두 리드선 끝단이 프레임 밖으로 잘려 단자 미노출 |

관행상 모터=수/ESC=암이면 맞아떨어지나 **추정이며 확인된 사실이 아니다.** VTOL용 [ESC 650 50A](../mfe-esc-650-50a/README.md)는 **3.5mm로 직경이 다르므로** 혼동하지 말 것 — 두 계통의 바나나 플러그는 서로 호환되지 않는다.

## 배선도 (Wiring Diagram, 원문 기준)

```
Battery ──► ESC(MFE ESC 6100 / MFE ESC 1260) ──(3상)──► Motor
              ▲
              │ Throttle 신호
           Receiver ◄── 6V ── UBEC
```

- 배터리는 ESC 메인 전원 입력으로 직결
- 수신기(Receiver)는 UBEC로 전원(6V) 공급받고, Throttle 신호선을 ESC로 전달
- ESC는 3상 출력으로 모터 구동

전체 다이어그램 원본: [images/02-params-wiring-tuning-cautions-disclaimer.png](images/02-params-wiring-tuning-cautions-disclaimer.png)

## 튜닝 프로세스 (Throttle Travel Calibration Method)

1. **전원 인가(Power up)** → 비프음 1회
2. **스로틀 신호 감지(Throttle signal detected)** → 비프음 1회(긴 음)
3. **스로틀 로커를 중간 이상으로 올림(최대 스로틀 측정 중)** → 측정 중 반복 비프
4. **최대 스로틀 상태로 3초 유지** → 저장 완료 비프 시퀀스 (최대 스로틀 저장됨)
5. **스로틀 로커를 중간 이하로 내림(최소 스로틀 측정 중)** → 측정 중 반복 비프(2연음)
6. **최소 스로틀 상태로 3초 유지** → 저장 완료 비프 시퀀스 (최소 스로틀 저장됨)
7. **스로틀 캘리브레이션 완료** → 비프음 1회, 이후 모터 구동 가능

> 참고(원문 Example): 가장 높은 음(highest tone) = 짧은 비프, 가장 낮은 음(lowest tone) = 긴 비프로 구분됨.

**정상 작동 및 비프음 순서(Normal operation and beep):**

1. 전원 인가(Power up) → 비프음
2. 스로틀 신호 감지 → 비프음
3. 제로 스로틀 감지(Zero throttle detected) → 비프음
4. 이후 모터 구동 가능(OK)

## 주의사항 (Cautions, 원문)

- 모든 납땜은 양호한 기법으로 수행하고, 부품/전선 간 납땜으로 인한 단락을 항상 피할 것
- 단락 및 누전을 피하기 위해 연결부가 잘 절연되어 있는지 확인할 것
- 항상 극성에 주의하고, 전원 공급 전 반드시 재확인할 것
- 브러시리스 ESC를 처음 사용하거나 조종기를 교체한 후에는 스로틀 트래블 캘리브레이션이 필요함
- 플러그를 꽂거나 연결 작업을 할 때는 전원을 끌 것
- ESC의 정격 작동 전류 범위를 초과해서 사용하지 말 것

## 안전/면책 (Disclaimer, 원문 요약)

- Makeflyeasy 항측 시리즈 제품은 민감 품목이며, 제조사는 직간접적 사고에 대해 책임지지 않음. 군사적 용도 사용 금지.
- 어린이 손이 닿지 않는 곳에 보관. 비행 시 군중/위험물로부터 충분히 이격. 음주/피로/정신적 불편 상태에서 비행 금지.

## 사진/자료

| 항목 | 파일 | 비고 |
|---|---|---|
| 제품 페이지 (외형, 4방향 사진, 가격/옵션) | [images/01-product-page.png](images/01-product-page.png) | uavmodel.com 제품 페이지 캡처 |
| 파라미터/배선도/튜닝/주의사항/면책조항 | [images/02-params-wiring-tuning-cautions-disclaimer.png](images/02-params-wiring-tuning-cautions-disclaimer.png) | 원문 스펙시트 |

> 원본 자료는 uavmodel.com 제품 페이지의 풀페이지 스크린샷(PDF, 3페이지)이며, 이 문서에는 **Disclaimer까지의 제품 정보만 반영**함. 이후 페이지의 "You may also like", 관련 상품 추천 등은 제품 스펙과 무관해 제외.

## 보유 수량 (SHADE 기체)

- PNP 옵션 기준 **1개 포함** (크루즈/전방 견인 모터용, [구성 리스트](../../../airframes/striver-mini-vtol/README.md#부품-구성-리스트-configuration-list) 참조)
- 조합 부품: 크루즈 모터 [MFE X4120 KV430](../../motors/mfe-x4120-kv430/README.md), 프로펠러 APC1612
