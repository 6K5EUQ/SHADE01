# MFE ESC 650 — 6S 50A (VTOL 모터용)

Makeflyeasy(MFE)에서 Striver Mini VTOL 시리즈용으로 커스텀 제작한 브러시리스 ESC. [Striver Mini VTOL](../../../airframes/striver-mini-vtol/README.md)의 **VTOL(수직 이착륙) 모터 4기**에 1개씩 장착되는 부품이며, 보유 기체(PNP 옵션)에 **4개 포함**되어 있다.

- 제조사: Makeflyeasy (MFE)
- 제품명: MFE ESC 650, "Makeflyeasy 6S 50A ESC Striver mini VTOL Hero VTOL Factory Custom Multi-rotor ESC"
- 용도: Striver Mini VTOL 4+1/4+2 기체의 VTOL 로터암 모터 구동
- 장착 위치: [로터암-모터 결합부 내부](../../../airframes/striver-mini-vtol/README.md#부위별-사진-자료) (탄소튜브 로터암 안에 삽입, 방열 실리콘 패드 + 알루미늄 커버로 마감)

## ⚠️ 모터 호환 경고 (제조사 원문)

> **MFE 6S 50A high-voltage ESC is deeply optimized according to the internal resistance and inductive reactance of MFE 5008 KV400 motor**, featuring smooth starting and efficient power output. Temporarily do not support other models of motors, there may be a risk of starting jamming, high current blocking and burning, please use with caution.

즉 이 ESC는 **MFE 5008 KV400 모터 전용으로 펌웨어/드라이브 특성이 최적화**되어 있으며, 다른 모터와 조합 시 시동 걸림(jamming)·과전류·소손 위험이 있다고 제조사가 명시함.

> 🔶 **확인 필요(불일치, 미해소)**: [Striver Mini VTOL 구성표](../../../airframes/striver-mini-vtol/README.md#부품-구성-리스트-configuration-list)에는 VTOL 모터가 **M4112 KV460**로 기재되어 있으나, 본 ESC 경고문은 **5008 KV400** 모터 기준으로 되어 있음. [MFE M4112 KV460 문서](../../motors/mfe-m4112-kv460/README.md)의 제조사 공식 스펙시트를 확인한 결과, 모델명은 "KV460"이지만 Technical Parameters 표의 실측 KV는 400으로 기재되어 있어 **숫자(400)만 우연히 일치**함. 프레임 표기("5008" vs "M4112", 49.8×27mm)는 여전히 다르므로, **동일 모델이라고 단정할 수 없음** — 실물 모터 라벨 대조 전까지는 별개 모델일 가능성을 열어둘 것. 전류 정격(ESC 50A / 모터 권장 ESC 50A)도 숫자만 같을 뿐, 이 역시 "확인된 매칭"이 아니라 "우연히 같은 숫자"로 취급.

## 성능 사양 (Product Parameter, 원문 기준)

| 항목 | 값 |
|---|---|
| 배터리 | 6S LiPo |
| 연속 전류 | 50A |
| 순간 전류 (10초) | 70A |
| BEC | 없음 (NO BEC — 별도 전원 필요) |
| 무게 | 49g |
| 전원선(Power Wire) | 16AWG, 51.5cm |
| 모터선(Motor Wire) | 16AWG, 4cm |
| 신호선(Signal Wire) | 30선 흑백 더블 트위스트 페어, 46cm |
| 바나나 플러그 | 3.5mm 암 커넥터 |
| 압착 단자(Pressed Terminals) | OT2.5-4 (링터미널) |
| 냉각 방식 | 방열 실리콘 패드 + 알루미늄 하우징(핀 방열 구조), 로터암 탄소튜브 내부 삽입형 |
| 폼팩터 | 로터암(원형 탄소튜브) 내장형, 끝단에 알루미늄 커버 체결 |

> 참고: PDF 원문 구버전 스펙시트에서는 VTOL ESC가 "6S 40A"로 기재되어 있었으나, 최신 구성표 및 실제 보유 기체 기준은 **6S 50A**(본 문서 대상)이다.

## 외형 / 단자 구성

기판 위에서 확인 가능한 커넥터 및 단자 (사진: [images/product-photos.webp](images/product-photos.webp)):

| 커넥터 | 케이블 색상/형태 | 용도 |
|---|---|---|
| 메인 전원 입력(+) | 굵은 적색 실리콘 케이블 16AWG, 끝단 OT2.5-4 링터미널 압착 | 배터리/파워버스 B+ |
| 메인 전원 입력(−) | 굵은 흑색 실리콘 케이블 16AWG, 끝단 OT2.5-4 링터미널 압착 | 배터리/파워버스 B− |
| 모터 출력 3상 | 흑색 케이블 3가닥, 16AWG 4cm, 끝단 3.5mm 바나나 플러그(암) | 모터 U/V/W상 |
| 시그널 케이블 | 흑백 30선 더블 트위스트 페어, 46cm | FC 연결용 (원문에 PWM/5V/GND 각 선 배정은 명시 안 됨 — 통상적인 3선 구성 추정, 실물/멀티미터로 확인 권장) |

기판 뒷면에는 방열용 대형 커패시터 2개(A2146 각인)와 전원 입력 패드(+/−)가 노출되어 있으며, 이 면이 로터암 탄소튜브 접촉/방열면 쪽으로 장착된다.

## 케이블 규격 정리

| 케이블 | 규격 | 길이 | 비고 |
|---|---|---|---|
| 전원선(적/흑 굵은선) | 16AWG, 실리콘 피복 | 51.5cm | 배터리~ESC 또는 파워분배보드~ESC. 끝단 OT2.5-4 링터미널 압착 가공 |
| 모터 출력선 | 16AWG, 3가닥 | 4cm | ESC 기판 직결, 끝단 3.5mm 바나나 플러그(암)로 모터와 결선 |
| 신호선 | 30선 흑백 더블 트위스트 페어 | 46cm | ESC ↔ FC/신호분배보드 (원문에 개별 선 배정 명시 없음, PWM/5V/GND는 추정) |

## 배선도 (Wiring Chart, 원문 기준)

```
Battery(+/−) ──┬──────────────► ESC ──(3상)──► Motor
               │
               └─► UBEC (또는 수신기 전용 배터리) ──6V──► Receiver ──Throttle──► ESC
```

- 배터리 전원은 ESC로 직결
- 수신기(Receiver)는 UBEC 또는 별도 수신기 전용 배터리로 6V 전원 공급
- 수신기의 Throttle 신호선이 ESC로 입력됨

전체 다이어그램 원본: [images/parameters-and-tuning.webp](images/parameters-and-tuning.webp)

## 튜닝 프로세스 (Throttle Travel Tuning)

**스로틀 캘리브레이션 (Beeps 기준):**

1. 전원 인가(Power up) → 비프음 1회
2. 스로틀 신호 감지(아밍 시퀀스 시작) → 비프음 1회(긴 음)
3. 스로틀을 중간 이상으로 올린 상태에서 측정(최대 스로틀 측정 중) → 짧은 비프 반복
4. 최대 스로틀 상태로 3초 유지 시 → 저장 완료 비프 시퀀스 (최대값 저장됨)
5. 스로틀을 중간 이하로 내린 상태에서 측정(최소 스로틀 측정 중) → 짧은 비프 반복(2연음)
6. 최소 스로틀 상태로 3초 유지 시 → 저장 완료 비프 시퀀스 (최소값 저장됨)
7. 이 시점에서 캘리브레이션 값이 저장됨. 이후 ESC 전원을 끄거나 그대로 계속 사용 가능

**정상 부팅 절차 (Normal Boot-up Process):**

1. 송신기(RC)를 스로틀 최저 위치로 설정한 뒤 전원을 켠다
2. 배터리를 연결한다 → 약 1초 후 모터에서 "1-2-3" 음 + "1-" 비프음이 울리면 ESC 준비 완료(arm)

## 연결 방법 (조립 순서)

Assembly Process 참고 사진: [images/assembly-process.webp](images/assembly-process.webp)

1. **배선 통과**: 로터암(탄소튜브) 안으로 케이블을 먼저 통과시킨 뒤, ESC 기판을 튜브 끝단에 삽입한다.
2. **방열 실리콘 패드 부착**: ESC 기판 발열 부품(모스펫 등) 위에 방열 실리콘 패드를 부착해 알루미늄 커버와의 열전달을 확보한다.
3. **커버 체결**: 알루미늄 방열 커버를 씌우고 4개 모서리 나사를 조여 고정한다.
4. **전원/신호 연결**: 굵은 적/흑 전원선을 파워 배전 라인(6S 파워버스)에 연결하고, 신호선을 FC의 해당 모터 채널(예: Pixsurvey V3 기준 A1/A2/A3/A4)에 연결한다. 모터 출력 3상을 VTOL 모터에 결선한다.
5. **캘리브레이션**: 최초 장착 후 위 "튜닝 프로세스" 절차대로 스로틀 최대/최소값 캘리브레이션 수행.

> ⚠️ [Striver Mini VTOL 배선 다이어그램](../../../airframes/striver-mini-vtol/README.md#4-1-모드-배선-다이어그램-요약-참고용--pixsurvey-v3-fc-기준-pnp에는-fc-미포함) 참고 시, 전원 인가 전 반드시 커넥터 배선 순서 1:1 대응을 확인할 것 (단락 방지, 제조사 원문 경고 사항).

## 패키징

제품은 "MFE ESC 650 / 50A / 6S LiPo / NO BEC" 라벨이 붙은 박스에 개별 포장되어 공급된다.

## 사진 자료

| 항목 | 파일 | 비고 |
|---|---|---|
| 제품 사진 (상단/하단/배선 전체) | [images/product-photos.webp](images/product-photos.webp) | 기판 앞/뒤면, 전원단자 클로즈업 포함 |
| 제품 파라미터 + 배선도 + 튜닝 프로세스 | [images/parameters-and-tuning.webp](images/parameters-and-tuning.webp) | 원문 스펙시트 |
| 조립 과정 (배선 통과 → 방열패드 → 커버 체결) | [images/assembly-process.webp](images/assembly-process.webp) | 원문 제조사 조립 가이드 |

## 보유 수량 (SHADE 기체)

- PNP 옵션 기준 **4개 포함** (VTOL 모터 4기 대응)
- 사용 전 반드시 실제 장착된 VTOL 모터가 **5008 KV400**인지 확인할 것 (위 "모터 호환 경고" 참조)
