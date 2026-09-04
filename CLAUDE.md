# SHADE01 — 작업 전 지침

Striver Mini VTOL(4+1) 기체 한 대의 운용 저장소.

## 🔴 FC 를 만지기 전에 [`FC_CHANGELOG.md`](FC_CHANGELOG.md) 를 읽어라

기체 FC 의 값이 바뀌는 작업 — **파라미터 쓰기, 캘리브레이션, 펌웨어 플래시,
미션·지오펜스 업로드, 액추에이터 재배치** — 은 전부 거기에 기록한다.
**읽는 것도 쓰는 것도 의무다.** 마지막 변경을 모른 채 만지면 스냅샷과 실기가
어긋난 것을 모르고 낡은 값을 정본으로 착각한다.

작업 후 기록 → **커밋·푸시까지** 해야 끝난다. 로컬에만 두면 다른 PC 가 못 읽는다.

FC 는 PC 4대 어디에서나 브리지로 쓸 수 있고 상행이 열려 있다. `PARAM_SET` 한 줄로
ARM·모드변경·미션업로드가 실기에 들어간다 — 그래서 기록이 유일한 추적 수단이다.

## 지금 걸려 있는 제한

🔴 **고정익 사용 금지 — 쿼드 전용** (2026-09-04). 에어스피드 영점 미해결.
천이 진입 경로 4곳을 닫아 뒀다. 푸는 순서가 정해져 있다 —
[README](README.md#-고정익-사용-금지--쿼드-전용-2026-09-04).

## 문서 지도

| 파일 | 내용 |
|---|---|
| [`README.md`](README.md) | 기체 식별·링크 구성·현재 상태·다음 비행 전 |
| [`FC_CHANGELOG.md`](FC_CHANGELOG.md) | **FC 변경 이력 — 작업 전 필독** |
| [`PROCEDURE.md`](PROCEDURE.md) | 로그 수집 → 분석 → 기록 절차 |
| [`config/SETTINGS.md`](config/SETTINGS.md) | 파라미터 스냅샷 사람이 읽는 정리본 |
| [`gcs/ACCESS.md`](gcs/ACCESS.md) | PC 별 Tailscale 주소·계정·제약 |
| [`flights/`](flights/) | 비행별 분석 — `.ulg` 가 사라져도 남는 정본 |

## 알아 둘 것

- **`.ulg` 는 git 에 안 들어간다** (`.gitignore`). 수치를 문서로 남기는 것이 유일한
  영구 기록이다. 정본 보관소는 [shade01.bewe.co.kr](https://shade01.bewe.co.kr).
- **로그는 `logs/` 에 평면으로 쌓는다.** 날짜 하위폴더를 만들지 마라 —
  `_repair()` 가 같은 디렉토리의 형제 로그만 기증자로 쓴다.
- **`pyulog` 를 직접 부르지 마라.** 잘린 메시지에서 조용히 멈춘다. `./qgc` 를 거쳐라.
- **`ku` 는 GitHub 이 될 때도 안 될 때도 있다** (학교 DNS). 안 되면 Tailscale 로
  다른 PC 를 경유한다 — [gcs/ACCESS.md](gcs/ACCESS.md).
- **`rim3` 은 push 권한이 없다.** `gh` 가 `yyrrm` 계정으로 로그인돼 있어서다
  (2026-09-04 확인). 커밋 신원은 `6k5euq` 로 고쳤으나 **자격증명은 그대로**다 —
  풀려면 `rim3` 에서 `gh auth login` 을 6K5EUQ 로 다시 해야 한다. fetch 는 된다.
