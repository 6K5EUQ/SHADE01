# MFE X4120 KV430 — 크루즈 모터

Makeflyeasy(MFE)의 고효율 브러시리스 모터. [Striver Mini VTOL](../../../airframes/striver-mini-vtol/README.md)의 **크루즈(추진) 모터**로 사용되며, 4+1 모드에서는 기수(헤드 캐빈)의 전방 견인(pull) 모터 1기로 장착된다.

- 제조사: Makeflyeasy (MFE)
- 제품명: MFE High Efficiency Motor 4120 KV430 — "Striver mini VTOL Cruise motor"
- 모델: X4120, KV430
- 원산지: 중국(Made in China)
- 용도: Striver Mini VTOL 4+1/4+2 기체의 크루즈(순항 추진) 모터
- 장착 위치: [헤드 캐빈(기수)](../../../airframes/striver-mini-vtol/README.md#부위별-사진-자료) — PC 합금 플라스틱 모터 베이스, 최대 외경 φ60mm까지 지원

## 특징 (원문 요약)

- **고속·고효율(High-speed and efficient)**: 4120 KV430, 고출력 밀도로 APC 1612E 프로펠러와 조합 시 안정적 출력
- **능동 냉각(Active cooling)**: 로터에 내장된 "팬" 구조가 가이드 홈을 통해 능동 방열, 동력 변환 효율 향상
- **저동손 고출력(Low copper loss – high power)**: 군용 등급 내열 에나멜선 사용, 순수 수작업 권선으로 홈 충진율 향상 → 발열 감소, 출력 밀도 증가
- **동적으로 강력(Dynamically powerful)**, **견고하고 내구성 있음(Sturdy and durable)**

## 기본 파라미터 (Basic Parameters)

| 항목 | 값 |
|---|---|
| 모터 모델 | 4120 KV430 |
| 슬롯/폴 구성 (Slot level construction) | 12N14P |
| 스테이터 코어 | 특수 표면 방청 처리 |
| 모터 크기 | 50×47.5mm |
| 에나멜선 등급 | 200℃ 내열 |
| 마그넷 등급 | 180℃ 내열 |
| 마그넷 형상 | 아치형(arch) |
| 출력선 규격 | 12AWG, 100mm |
| 로터 동적 밸런스 테스트 | ≤5mg |
| 코일 내전압 테스트 | 500V AC |
| 프로펠러 장착 홀 위치 | M3⌀12×4 |
| 모터 장착 홀 위치 | M4⌀8×4 |

## 성능 파라미터 (Performance Parameters)

| 항목 | 값 |
|---|---|
| KV | 430 |
| 정격 전압 | 6S |
| 무부하 전류 | 1.5A / 10V |
| 내부 저항 | 26mΩ |
| 최대 전류 | 79A / 30초 |
| 최대 출력 | 2425W |
| 최대 추력(Maximum pull) | 5800g (단축 기준) |
| 모터 무게 | 307g |
| 권장 ESC | 6S 80–100A |
| 권장 프로펠러 | APC 1612E |

> Striver Mini VTOL 기체의 크루즈 ESC는 **6S 100A**([구성 리스트](../../../airframes/striver-mini-vtol/README.md#부품-구성-리스트-configuration-list) 참조)로, 본 모터의 권장 범위(6S 80–100A) 내에 부합함.

## 테스트 데이터 (Test Parameters, 24V 기준 / APC 1612 프로펠러)

| 전류(A) | 추력(g) | 출력(W) | 효율(g/W) |
|---|---|---|---|
| 1.3 | 264 | 31.2 | 8.462 |
| 2.4 | 461 | 57.6 | 8.003 |
| 3.4 | 638 | 81.6 | 7.819 |
| 4.3 | 756 | 103.2 | 7.326 |
| 5.5 | 844 | 132 | 6.394 |
| 6.8 | 1031 | 163.2 | 6.317 |
| 9.8 | 1371 | 235.2 | 5.829 |
| 12.6 | 1714 | 302.4 | 5.668 |
| 14.5 | 1973 | 348 | 5.670 |
| 18.0 | 2335 | 432 | 5.405 |
| 24.2 | 2934 | 580.8 | 5.052 |
| 30.5 | 3475 | 732 | 4.747 |
| 38.5 | 3899 | 924 | 4.220 |
| 45.3 | 4378 | 1087.2 | 4.027 |
| 50.0 | 4612 | 1200 | 3.843 |
| 62.1 | 4754 | 1490.4 | 3.190 |
| 69.3 | 5024 | 1663.2 | 3.021 |
| 79.0 | 5501 | 1896 | 2.901 |

전류가 증가할수록 추력 대비 효율(g/W)은 감소하는 경향(8.46 → 2.90). 순항 구간에서는 저전류 영역(효율 6~8 g/W대)을 사용하는 것이 배터리 효율 측면에서 유리함. [항속 성능](../../../airframes/striver-mini-vtol/README.md#항속-성능)(순항속도 18–21m/s 기준)과 대조해 실비행 전류 구간 참고 가능.

## 엔지니어링 도면 치수 요약

| 항목 | 값 |
|---|---|
| 전장 (도면 표기 "50") | 50mm (커넥터 포함 여부는 도면에 라벨 없음, 추정) |
| 전장 (도면 표기 "47.5") | 47.5mm |
| 바디 외경 | ⌀50mm |
| 축 관련 치수 (도면 표기 "⌀14") | ⌀14mm (샤프트 관통 축경인지 도면에 명시 없음, 위치상 추정) |
| 출력선 길이 | 110mm |
| 모터 장착 홀 | 4×M4×0.7, ⌀30.0 PCD |
| 프로펠러 장착 홀 | 4×M3×0.5, ⌀17.0 PCD |
| 샤프트 어댑터(패들시트) 관련 | ⌀3.1/⌀10.4 (핀), ⌀10.5/⌀25.0 (와셔), M8 나사부 22.0/28.0/36.0mm, 8×⌀3.2 홀 (⌀27.0/⌀15.0/⌀14.0/⌀17.0/**⌀8.0** PCD) |

상세 도면 원본: [images/05-engineering-drawings.webp](images/05-engineering-drawings.webp)

## 패킹 리스트 (Packing list)

| 품목 | 수량 |
|---|---|
| 4120 KV430 모터 본체 | 1개 |
| 패들 시트(Paddle seat, 프로펠러 어댑터) | 1개 |
| 프로펠러 장착 나사 M3×10mm | 4개 |
| 모터 장착 나사 M4×8mm | 4개 |

## 사진/자료

| 항목 | 파일 |
|---|---|
| 제품 개요 (모델명, 외형) | [images/01-overview.webp](images/01-overview.webp) |
| 성능 개요 (307g, 최대추력 5800g) | [images/02-performance-output.webp](images/02-performance-output.webp) |
| 능동 냉각 구조 | [images/03-active-cooling.webp](images/03-active-cooling.webp) |
| 저동손 권선 구조 (스테이터 클로즈업) | [images/04-low-copper-loss.webp](images/04-low-copper-loss.webp) |
| 엔지니어링 도면 | [images/05-engineering-drawings.webp](images/05-engineering-drawings.webp) |
| 기본/성능 파라미터 표 | [images/06-basic-and-performance-parameters.webp](images/06-basic-and-performance-parameters.webp) |
| 테스트 파라미터 표 + 효율 곡선 그래프 | [images/07-test-parameters.webp](images/07-test-parameters.webp) |
| 패킹 리스트 + 면책조항 | [images/08-packing-list-disclaimer.webp](images/08-packing-list-disclaimer.webp) |

## 안전/면책 (원문 요약)

- Makeflyeasy 항측 시리즈 제품은 민감 품목이며, 제조사는 직간접적 사고에 대해 책임지지 않음. 군사적 용도 사용 금지.
- 어린이 손이 닿지 않는 곳에 보관. 비행 시 군중/위험물로부터 충분히 이격. 음주/피로/정신적 불편 상태에서 비행 금지.

## 보유 수량 (SHADE 기체)

- PNP 옵션 기준 **1개 포함** (크루즈/전방 견인 모터, [구성 리스트](../../../airframes/striver-mini-vtol/README.md#부품-구성-리스트-configuration-list) 참조)
- 조합 부품: 크루즈 ESC 6S 100A ([MFE ESC 6100](../../esc/mfe-esc-6s-100a/README.md)), 프로펠러 APC1612
