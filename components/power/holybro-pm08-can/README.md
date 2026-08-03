# Holybro PM08-CAN — Power Module (14S, 200A)

Holybro의 DroneCAN 파워모듈. 배터리 전압/전류를 센싱해 CAN 버스로 FC에 보고하고, FC에 이중화 전원을 공급하는 부품. [Striver Mini VTOL](../../../airframes/striver-mini-vtol/README.md)의 [배전 캐빈](../../../airframes/striver-mini-vtol/README.md#부위별-사진-자료)에 [PDB 300A](../holybro-pdb-300a-side-entry/README.md)와 함께 장착되며, PNP 옵션에는 미포함이라 별도 구매한 부품.

- 제조사: Holybro
- 제품명: PM08-CAN Power Module, 14S, 200A
- 공식 문서: https://docs.holybro.com/power-module-and-pdb/power-module-comparison
- 용도: 배터리 전압/전류 센싱(DroneCAN) + FC 이중화 전원 공급
- 작성 근거: 제품 페이지 스크린샷(PDF)이 없어 Holybro 공식 문서 MCP(`askQuestion`)로 조회한 텍스트 답변을 기반으로 작성함 (PDB 300A 문서는 실제 스크린샷 대조, 본 문서는 스크린샷 미확보 — 스펙 자체는 공식 문서 근거이나 이미지로 직접 검증하지는 못함)

## 사양

| 항목 | 값 |
|---|---|
| 입력 전압 | 7–60V (2S–14S) |
| 연속 전류 | 200A |
| 순간 전류 | 400A @ 25℃ 1초 / 1000A @ 25℃ 1초 미만 |
| 최대 전류 센싱 범위 | 376A |
| 센싱 정확도 | 기본 약 5% (Mission Planner 캘리브레이션으로 개선 가능) |
| FC 전원 출력 | 5.2V / 최대 3A |
| 커넥터(파워모듈 측) | Molex CLIK-Mate 2mm, 6핀 |
| 통신 프로토콜 | DroneCAN |

## 연결 방법

### CAN (센싱 데이터)

PM08의 CAN 커넥터를 [Holybro Pixhawk 6C Mini](../../fc/holybro-pixhawk-6c-mini/README.md)의 **CAN1** 포트에 연결.

| 포트 핀 | 신호 |
|---|---|
| 1 | VCC (+5V) |
| 2 | CANH (+3.3V) |
| 3 | CANL (+3.3V) |
| 4 | GND |

연결 후 파라미터 설정 필요:

| 펌웨어 | 설정 |
|---|---|
| PX4 | `UAVCAN_ENABLE=2`, `UAVCAN_SUB_BAT=2`, `BAT1_SOURCE=External` → 전원 재인가 재시작 |
| ArduPilot | `CAN_P1_DRIVER=1`, `CAN_SLCAN_CPORT=1`, `BATT_MONITOR=8`, `BATT_OPTIONS=1` → 전원 재인가 재시작 |

### FC 전원 출력

PM08은 **5.2V 출력 포트 2개**(독립 회로)를 제공해 FC에 이중화 전원을 공급.

### PDB 연결

[Holybro PDB 300A Side Entry](../holybro-pdb-300a-side-entry/README.md) 제품 페이지에 **"PM08 시리즈 파워모듈과 호환(compatible with PM08 series power modules)"**이라고 명시되어 있어 두 부품의 조합 사용이 공식 확인됨. 다만 PM08과 PDB 사이의 정확한 배선 순서(배터리 → PM08 → PDB 순인지, 배터리 → PDB 입력단에서 PM08이 병렬로 센싱탭을 따는지)는 두 제품 페이지 모두에 다이어그램으로 명시되어 있지 않아 실물/매뉴얼 추가 확인 권장.

## 🔶 확인 필요

- PM08과 PDB 300A 간 정확한 배선 순서(공식 호환은 확인됨, 다이어그램 수준의 배선 절차는 미확인)
- 실제 Striver 기체의 배전 캐빈 구조([08-distribution-cabin.png](../../../airframes/striver-mini-vtol/images/08-distribution-cabin.png))와 대조해 물리적 배치 확인 필요

## 보유 수량 (SHADE 기체)

- 1개, PNP 옵션에는 미포함되어 별도 구매
- 연결 대상: [Holybro Pixhawk 6C Mini](../../fc/holybro-pixhawk-6c-mini/README.md) CAN1 + Power1/2, [PDB 300A Side Entry](../holybro-pdb-300a-side-entry/README.md)
