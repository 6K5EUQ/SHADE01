# RadioMaster RP4TD-M — ExpressLRS 2.4GHz Mini True Diversity Receiver

RadioMaster의 ExpressLRS(오픈소스 장거리 RC 링크) 초소형 수신기. RC 송신기(조종기)의 무선 신호를 받아 FC(비행제어) 또는 ESC로 전달하는 역할.

- 제조사: RadioMaster
- 제품명: RP4TD-M ExpressLRS 2.4GHz Mini True Diversity Receiver
- 판매처: radiomasterrc.com, 단가 $19.99 (2026-08-02 확인)
- 리전 옵션: FCC / LBT (전파 규격 지역 옵션, 구매 시 선택)
- 용도: [Striver Mini VTOL](../../../airframes/striver-mini-vtol/README.md) 등 ExpressLRS 기반 RC 시스템의 수신기

## 🔶 확인 필요 (프로토콜 호환)

- 본 수신기의 버스 인터페이스는 **CRSF (Crossfire Protocol)** — TBS Crossfire가 원조이며 ExpressLRS가 채택한 양방향 시리얼 디지털 프로토콜. PPM(아날로그 펄스폭)이나 SBUS(단방향 시리얼)와는 물리/전기적으로 다른 방식이라, FC가 CRSF를 받으려면 그걸 지원하는 UART 포트와 별도 프로토콜 설정이 필요함.
- SHADE 보유 기체의 실제 FC는 **[Holybro Pixhawk 6C Mini](../../fc/holybro-pixhawk-6c-mini/README.md)로 확정**되어 있음 (PDF 원문의 Pixsurvey V3는 SHADE 기체에 쓰이지 않는 참고자료일 뿐). 따라서 확인이 필요한 대상은 Pixsurvey V3가 아니라 **Pixhawk 6C Mini의 Telem 포트가 CRSF를 지원하는지, PX4/ArduPilot에서 어떤 파라미터 설정이 필요한지**임 — 자세한 내용은 [Pixhawk 6C Mini 문서](../../fc/holybro-pixhawk-6c-mini/README.md#🔶-확인-필요) 참조.
- Striver 기체의 RC 시스템(ET10 송신기/수신기)은 [구성 리스트](../../../airframes/striver-mini-vtol/README.md#부품-구성-리스트-configuration-list)상 IND(완제품) 옵션에만 포함되며, 보유 기체는 PNP라 RC 수신기가 미포함 상태였음. 본 RP4TD-M을 그 대체품으로 사용하려는 것으로 추정 — ET10과는 별개의 송신기 생태계(ExpressLRS 지원 송신기 필요)이므로, 조종기(TX)도 ExpressLRS 호환 기종인지 함께 확인 필요.

## 특징 (Features, 원문 요약)

- 미니 사이즈 트루 다이버시티(True Diversity) Gemini 수신기 — 듀얼 2.4GHz 라디오로 신호 민감도, SNR, 안정성 향상
- 클래스 최고 수준의 SNR/RSSI 성능
- 내장 TCXO(온도보상 수정발진기) — 온도 변화에도 고정밀 주파수 유지, 주파수 드리프트 방지
- 최적화된 PCB 설계로 방열 개선
- 업그레이드된 안테나(강성 개선) — 내구성/성능 향상
- 텔레메트리 RF 출력 2×10mW
- 2.4GHz ExpressLRS 내장 송신기/모듈과 전 기종 호환

## 사양 (Specifications)

| 항목 | 값 |
|---|---|
| 타입 | ISM |
| MCU | ESP32 |
| RF 칩 | SX1281 ×2 |
| 안테나 | 65mm 2.4GHz T타입 안테나 ×2 |
| 주파수 대역 | 2.4GHz |
| 최대 갱신률(Refresh Rate) | 500Hz / F1000Hz |
| 텔레메트리 RF 출력 | 최대 2×10mW |
| 동작 전압 | DC 5.0V |
| WiFi 업데이트 | 지원 |
| 무게 | 1.00g (안테나 미포함) / 3.30g (안테나 포함) |
| 크기 | 18.10×16.00mm |
| 펌웨어 버전 | ExpressLRS V3.4.3 사전 설치 |
| FW 타깃 | RadioMaster RP4TD-M 2400 RX |
| 버스 인터페이스 | CRSF |

## 치수 상세

| 항목 | 값 |
|---|---|
| 기판 크기 | 18.10 × 16.00mm |
| 기판 두께 | 2.00mm |
| 전체 높이(안테나 포함) | 79.00mm |
| 안테나 길이 | 65.00mm |

## 패키지 구성 (Package Includes)

| 품목 | 수량 |
|---|---|
| RP4TD-M ExpressLRS True 2.4GHz Diversity Receiver | 1 |
| CRSF wire (CRSF 배선 케이블) | 1 |
| 열수축 튜브(Heat-Shrinkable Tube) | 3 |
| 65mm 2.4GHz T 안테나 (수신기에 사전 장착됨) | 2 |
| User Manual | 1 |

## 사진/자료

| 항목 | 파일 | 비고 |
|---|---|---|
| 제품 페이지 (외형, 가격, 옵션) | [images/01-product-page.png](images/01-product-page.png) | radiomasterrc.com 제품 페이지 캡처 |
| 사양 + TCXO/듀얼 트랜시버/듀얼안테나 설명 | [images/02-specifications-and-tcxo.png](images/02-specifications-and-tcxo.png) | |
| 사양표(재확인) + 무게/크기 실측 + 패키지 구성 | [images/03-specs-weight-size-package.png](images/03-specs-weight-size-package.png) | 저울 실측 사진, 치수 도면 포함 |

> 원본 자료는 radiomasterrc.com 제품 페이지의 풀페이지 스크린샷(PDF, 4페이지)이며, 이 문서에는 제품 정보(사양/패키지 구성)까지만 반영함. 이후 페이지의 리뷰, "You may also like", 사이트 푸터 등은 제외.

## 보유 수량 (SHADE 기체)

- 현재 보유/구매 검토 중 (수량 미정)
- Striver Mini VTOL은 PNP 옵션으로 RC 수신기 미포함 상태였으며, 본 제품이 그 자리를 채울 후보로 확인됨 (위 "확인 필요" 항목 참조)
