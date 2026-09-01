# SHADE01 — 기체 단위 관리

이 폴더는 **기체 한 대(SHADE01)** 의 운용 기록을 모은다. repo 최상위의
`components/` 가 "부품이 무엇인가"를 다룬다면, 여기는 **"이 기체에 무슨 일이 있었나"** 를
시간순으로 남긴다.

> 기체 제원·부품 구성은 [Striver Mini VTOL](../airframes/striver-mini-vtol/README.md) 과
> `components/` 를 본다. 여기서 중복 기술하지 않는다.

## 기체 식별

| 항목 | 값 |
|---|---|
| 호출명 | **SHADE01** |
| 기체 | Striver Mini VTOL (4+1) |
| FC | Pixhawk 6C Mini — `PX4_FMU_V6C`, HW `V6C002002` |
| 펌웨어 | **PX4 v1.17.0 커스텀** (`d6f12ad1c4f7`, 빌드 2026-08-11) |
| 컴패니언 | Raspberry Pi 5 `raspb1` — FC 와 **USB 직결** (`/dev/ttyACM0`) |
| 조종기 | RadioMaster Boxer (EdgeTX 2.12.1) |
| 배터리 | Fullymax 6S 16000mAh |

## 폴더 구조

```
SHADE01/
├── README.md            이 문서 — 기체 식별·현재 상태
├── PROCEDURE.md         로그 수집·분석·기록 절차
├── logs/<날짜>/         .ulg 원본 (git 제외 — 아래 참조)
├── flights/             비행/세션별 분석 문서
├── params/              파라미터 스냅샷 (.params)
└── config/              조종기 model00.yml 등 설정 백업
```

> 🔴 **`.ulg` 는 git 에 들어가지 않는다** — repo 최상위 `.gitignore` 에 `*.ulg` 가 있다.
> 로그 원본은 **로컬에만** 남고, git 에는 `flights/` 의 분석 문서만 커밋된다.
> 원본이 필요하면 FC SD 에서 다시 받거나 로컬 `logs/` 를 본다.
> **FC SD 도 언젠가 덮어쓰인다** — 중요한 비행은 분석 문서에 수치를 적어 두는 것이 정본이다.

## 현재 상태 (2026-09-01)

| 항목 | 상태 |
|---|---|
| 링크 | FC USB ↔ raspb1 → UDP 14550 → Tailscale → QGC |
| 비행모드 | S3 6단 로터리 → CH6 ([상세](../components/transmitters/radiomaster-boxer/switch-mapping.md)) |
| 미션 | FC 에 6항목 저장 (사각 루프, WP#1~4 고도 5m) |
| 🔴 지오펜스 | **무제한** — `GF_MAX_HOR_DIST=0`, `GF_MAX_VER_DIST=0`, 폴리곤 0개 |
| 🟡 WP#0 | 고도 3m (나머지는 5m) — 이륙 후 하강 |
| ⚠️ CH7 천이 | 조종기는 보내나 FC 미매핑 |

## 이력

| 날짜 | 사건 |
|---|---|
| 2026-08-31 | 비행모드 S3 6단 전환, `COM_ARM_WO_GPS=1`, 미션 고도 5m, 저전압 RTL |
| 2026-08-31 | FC TELEM2 사망 → **USB 링크로 전환** (raspb1) |
| 2026-08-31 | 지상 테스트 21회 ([세션 기록](flights/2026-08-31-ground-tests.md)) |
| 2026-08-30 | 컴패니언 Pi `raspb2`(고장) → `raspb1` 이설 |
