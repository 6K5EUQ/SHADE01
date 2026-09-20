# SHADE01

**체계 소개 → [shade01.bewe.co.kr/intro](https://shade01.bewe.co.kr/intro)**

![체계 소개](docs/images/05-intro.png)

![비행 중](docs/images/00-flight.jpg)

수직이륙 고정익(VTOL) 기체를 조립해 운용하며, 매 비행의 로그를 수집·분석하고 기록합니다.

| | |
|---|---|
| 기체 | Striver Mini VTOL 4+1 (익폭 2.1m, 7kg) |
| 비행 제어 | PX4 · Pixhawk 6C Mini |
| 기록 | 8일간 55회 비행, 누적 84분 |

---

## 1. 비행 기록을 업로드 하여 자동으로 분석이 이루어집니다

![비행 로그 목록](docs/images/02-loglist.png)

비행별 최고 고도·최대 속도·비행 시간·최대 전류를 표시합니다. 위험 수준의 전류는 붉게 표시됩니다.

---

## 2. 비행 기록을 재생하여 시간대별 분석이 가능합니다

비행 경로를 지도에 표시하고 그래프와 함께 재생합니다.

![비행 분석 화면](docs/images/03-analysis.png)

고도 · 속도 · 자세 · 각속도 · 조종 입력 · 모터 출력 · 전력 · 진동 · 통신 · 링크 여유 · GPS 품질 · 센서 불일치 · CPU · RAM 을 겹쳐 특정 시점의 원인을 추적합니다.

---

## 3. 비행 중인 기체의 상태를 실시간으로 분석합니다

화면에서 실시간으로 확인합니다.

![실시간 화면](docs/images/01-live.png)

---

## 4. 비행 전 기체를 점검합니다

명령 한 줄로 기체 상태를 조회해 비행 가능 여부를 판단합니다.

![비행 전 점검](docs/images/04-preflight.png)

GPS·배터리·failsafe 설정·센서 상태를 확인합니다.

---

## 저장소 구성

| 폴더 | 내용 |
|---|---|
| `flights/` | 비행별 분석 기록 |
| `components/` | 부품별 제원과 배선 |
| `airframes/` | 기체 조립 구성 |
| `tools/` | 로그 수집·분석 프로그램 |
| `tools/fc/` | **FC 에 `extras.txt` 올리기·재부팅·ELRS Hz 재기** — [올리는 절차](tools/fc/README.md) · [재는 절차](tools/fc/MEASURING.md) |
| `web/` | 비행 기록 웹 서비스 |
| `docs/emergency/` | **현장 체크리스트** — 이륙 전 · 이륙 직후 · 비상 |
| `FC_CHANGELOG.md` | FC 변경 이력 |
| `OPERATIONS.md` | **운용 상세** — 기체 식별 · 링크 구성 · 현재 상태 · 다음 비행 전 |
