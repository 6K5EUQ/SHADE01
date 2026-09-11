# FC 에 올리기 — `extras.txt` · 미션

| 도구 | 대상 | 경로 |
|---|---|---|
| [`extras_push.py`](extras_push.py) | `/fs/microsd/etc/extras.txt` (TELEM1 스트림) | MAVFTP |
| [`mission_push.py`](mission_push.py) | **미션 전량** | MISSION 프로토콜 |
| [`reboot.py`](reboot.py) | 재부팅 | — |

둘 다 `backup` / `verify` / `push` 세 갈래이고 **`push` 만 FC 에 쓴다.**
붙을 때마다 `SAFETY_ARMED` 를 보고 **ARM 이면 중단**한다.

미션은 [`missions/README.md`](../../missions/README.md) 가 정본이다 —
금지 명령(84·85·3000)과 5초 호버를 적는 법이 거기 있다.

---

## `extras.txt`

FC SD 의 `/fs/microsd/etc/extras.txt` 를 MAVFTP 로 받고 올린다.
2026-09-11 실제 적용에 쓴 스크립트다.

🔴 **FC 에 쓴다.** 작업 전 [`FC_CHANGELOG.md`](../../FC_CHANGELOG.md) 를 읽어라.

## 순서

```bash
# rim3 (FC 가 붙은 PC) 에서
systemctl --user stop shade-bridge          # 포트 독점 해제 — kill 금지

.venv/bin/python tools/fc/extras_push.py backup --backup ~/fc-backup/extras.txt.fcbak-$(date +%Y%m%d-%H%M%S)
.venv/bin/python tools/fc/extras_push.py verify --backup <위 파일> --new config/extras.txt
.venv/bin/python tools/fc/extras_push.py push   --new config/extras.txt
.venv/bin/python tools/fc/reboot.py         # extras.txt 는 부팅 때만 읽힌다

systemctl --user start shade-bridge         # 🔴 반드시 되살린다
```

## 지켜지는 것

| | |
|---|---|
| ARM 검사 | FC 에 붙을 때마다 `SAFETY_ARMED` 를 보고, ARM 이면 **중단**한다 |
| 첫 줄 | `verify` 가 `ms5525dso …`(에어스피드 기동)를 바이트로 대조한다. 다르면 중단 |
| 되읽기 | `push` 가 올린 뒤 **새 연결로** 되읽어 CRC32 를 대조한다 |
| 백업 | `backup` 없이 `push` 하지 마라. 되돌릴 근거가 사라진다 |

## 함정

- ⚠️ **`cmd_put` 직후 같은 세션으로 되읽으면 `no sessions available`.** 쓰기 세션이
  안 닫혀서다. 스크립트는 연결을 새로 연다 — 이 에러가 나도 **업로드는 성공했을 수
  있다.** 되읽기 CRC 로만 판정해라.
- ⚠️ **`-r 0` 은 스트림을 끄지 않고 `inf` 로 켠다.** 억제는 `-r 0.01`.
- ⚠️ **`SET_MESSAGE_INTERVAL` 로는 TELEM1 이 안 바뀐다.** 레이트는 MAVLink
  인스턴스별이고 USB 직결·브리지는 전부 USB 인스턴스다. `extras.txt` + 재부팅뿐이다.
- ⚠️ **USB 로 보이는 Hz 는 TELEM1 의 Hz 가 아니다.** ELRS 실측은 백팩 경로로 해야 한다.
