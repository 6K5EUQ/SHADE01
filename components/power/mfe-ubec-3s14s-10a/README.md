# MFE UBEC — 3S-14S 10A (조종면 서보 전원)

Makeflyeasy(MFE)의 외장형 전압 레귤레이터(UBEC). [Striver Mini VTOL](../../../airframes/striver-mini-vtol/README.md)의 [구성 리스트](../../../airframes/striver-mini-vtol/README.md#부품-구성-리스트-configuration-list)에 PNP/PIX 옵션 기준 **1개 포함**된 부품으로, 서보(조종면)에 안정적인 전원을 공급하는 역할.

- 제조사: Makeflyeasy (MFE)
- 제품명: "Makeflyeasy 14S UBEC 10A High Voltage Other Tools"
- 판매처: uavmodel.com (UAVMODEL)
- 용도: 조종면 서보([MFE 3054](../../servos/mfe-s3054/README.md) ×5) 전원 안정화 공급

## 제품 설명 (원문 요약)

MFE UBEC는 주로 조종면 서보(steering gear)에 전원을 공급하는 고성능 외장형 전압 레귤레이터 모듈. 서보가 파워 시스템에 주는 간섭을 줄이고, 서보에 큰 부하가 걸렸을 때 발생할 수 있는 토크 부족 현상을 방지한다. 효율적인 DC-DC 설계로 3-14S 리튬배터리 입력을 받아 감압된 출력을 최대 10A까지 안정적으로 공급한다.

## 사양

| 항목 | 값 |
|---|---|
| 입력 | 3S–14S LiPo |
| 지속 전류 | 10A |
| 순간 전류 | 20A (10초) |
| 크기 | 55×33×13mm |
| 무게 | 57g |
| 입력 전원선 | 적/흑, 18AWG, 60cm |
| 출력 전원선 | 듀얼 적/흑, 22AWG, 15cm, 조종면(서보) 암 커넥터 장착 |

## 🔶 확인 필요 (출력 전압 표기 불일치)

**제품 스펙표와 실물 라벨의 출력 전압이 서로 다르게 표기되어 있다.**

| 출처 | 표기 전압 |
|---|---|
| 제품 설명/스펙표 ("Product Description") | **5.3V** ("depressurized 5.3V outputs") |
| 실물 하우징 인쇄 라벨 | **6V** ("3S-14S 6V 10A") |

기체 문서의 [구성 리스트](../../../airframes/striver-mini-vtol/README.md#부품-구성-리스트-configuration-list)에는 "UBEC | 3S–14S, 5.3V 10A"로 스펙표 쪽 수치(5.3V)가 반영되어 있었음. 실물 라벨(6V)과 다른 이유는 불명 — 개정판/로트 차이, 표기 오류, 또는 실측 출력이 무부하 시 6V이고 스펙표는 부하 시 감압값(5.3V)을 표기했을 가능성 등 여러 시나리오가 있을 수 있으나 확정 근거 없음. **서보([MFE 3054](../../servos/mfe-s3054/README.md), 동작전압 4.8–6.0V) 정격 상한(6.0V)과 라벨 표기(6V)가 정확히 맞닿아 있어, 실측치가 6V에 더 가깝다면 서보 정격 한계에 걸칠 수 있으므로 실물 멀티미터 측정 권장.**

## 커넥터 / 케이블 구성

| 방향 | 케이블 | 커넥터 |
|---|---|---|
| 입력(INPUT) | 적/흑 굵은선, 18AWG, 60cm | 나선(피복만 벗겨진 상태, 실물 사진에서 확인 — 압착단자/플러그 없음) |
| 출력(OUTPUT) | 듀얼 적/흑, 22AWG, 15cm ×2조 | 표준 서보 커넥터(암, 3핀 하우징) — 실물 사진에서 2개 출력선 확인 |

> 입력선이 나선(bare wire) 상태이므로, 배터리/파워버스에 연결하려면 사용자가 직접 압착단자 또는 커넥터를 납땜/체결해야 함. Striver 기체의 [배전 캐빈](../../../airframes/striver-mini-vtol/README.md#구조캐빈별-사양)이 "서보 전원 1계통"을 지원한다고 명시된 부분과 연관 — 이 UBEC의 입력이 그 배전 캐빈의 서보 전원 라인에서 분기되는 것으로 추정되나, 정확한 분기 지점(PDB 출력단인지 별도 라인인지)은 확인 필요.

## 사진/자료

| 항목 | 파일 | 비고 |
|---|---|---|
| 제품 사진 (본체 상세, 확대 가능) | [images/01-product-photos.png](images/01-product-photos.png) | uavmodel.com 제품 페이지 캡처 |
| 제품 설명 + 스펙표 | [images/02-description-specs.png](images/02-description-specs.png) | 입출력 케이블 규격 포함 |
| 배선 연결 상태 실물 사진 | [images/03-wired-product-photo.png](images/03-wired-product-photo.png) | 실물 라벨 "3S-14S 6V 10A" 확인 — 스펙표(5.3V)와 표기 불일치 |

## Striver Mini VTOL 연동

| 항목 | 내용 |
|---|---|
| 구성표 표기 | "UBEC, 3S–14S, 5.3V 10A" — PNP·PIX 옵션에만 포함(1개), PRO·CAN·IND 옵션은 미포함 |
| 급전 대상 | 조종면 서보 ×5 ([MFE 3054](../../servos/mfe-s3054/README.md)) |
| 관련 캐빈 | [배전(Distribution) 캐빈](../../../airframes/striver-mini-vtol/README.md#구조캐빈별-사양) — "서보 전원 1계통" 항목과 연관 추정 |

## 보유 수량 (SHADE 기체)

- PNP 옵션 기준 **1개 포함**
- 급전 대상: 조종면 서보 5개
- 실물 확보 시 출력 전압(5.3V vs 6V, 위 "확인 필요" 참조) 멀티미터 실측 권장
