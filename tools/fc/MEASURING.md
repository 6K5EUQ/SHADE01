# ELRS 로 무엇이 몇 Hz 로 오는지 재기

**조종기 링크(TELEM1)의 실제 도착 Hz 를 센다.** 읽기 전용 — FC 로 아무것도 안 보낸다
(백팩을 깨우는 UDP 하트비트만 나간다).

## 왜 따로 재야 하나

🔴 **USB 로 보이는 Hz 는 TELEM1 의 Hz 가 아니다.** 스트림 레이트는 MAVLink
**인스턴스별**이라 USB 직결·브리지로 본 값은 ELRS 와 무관하다. `extras.txt` 를
고친 뒤 "먹었나" 를 확인하려면 **반드시 백팩 경로로** 재야 한다.

🔴 **트래커(`/api/state`)의 `packets`·`bytes` 로는 못 잰다.** 두 경로를 합산한
값이라 ELRS 만 떼어내지 못한다. 소켓을 직접 받아야 한다.

## 절차

백팩은 **자기를 마지막으로 찌른 클라이언트에게** 보낸다. `mav_live.py` 가
`10.0.0.100:14550` 을 쥐고 있으면 우리 소켓에는 한 패킷도 안 온다 — 그래서
트래커를 잠시 멈추고 그 자리를 받는다. ([포트 절차](../../FC_CHANGELOG.md#-포트를-쓰는-작업은-상태-파악--잠시-끄고--우리-것--되살리기))

```bash
# rim3 에서. 백팩 AP 에 붙어 있어야 한다 (ESSID "ExpressLRS TX Backpack …")
iwgetid; ip -4 addr show wlo1 | grep inet     # 10.0.0.100/24 여야 한다

systemctl --user is-active shade-live shade-backpack   # 끄기 전 상태를 적어 둔다
systemctl --user stop shade-live                        # 🔴 poker 는 켜 둔다
for i in $(seq 1 15); do ss -ulnp | grep -q "10.0.0.100:14550" || break; sleep 1; done

.venv/bin/python tools/fc/elrs_hz.py 90                 # 90초 권장

systemctl --user start shade-live                       # 🔴 반드시 되살린다
```

## 읽는 법

- **도달률 90% 이상이면 정상이다.** 2026-09-11 실측은 자세 10Hz 설정에 **9.42Hz(94%)**.
- **`BAD_DATA` 가 0 이 아니면** 링크가 포화에 가깝다는 뜻이다. 늘어나면 되돌려라.
- **총 B/s 를 `MAV_0_RATE`(현재 1400) 와 비교한다.** 실측은 계산보다 낮게 나온다 —
  PX4 가 페이로드 뒤쪽 0 바이트를 잘라서다. 계산 1145 → 실측 738 B/s 였다.
- **최대공백(max gap)이 EdgeTX 임계 20초를 넘으면** 그 센서가 "Sensor lost" 를 만든다.

## 함정

- ⚠️ **`pin` 이 풀린다.** `shade-live` 를 재시작하면 auto 로 돌아간다. 화면에서 ELRS 를
  계속 보려면 데이터 원천 배지를 다시 눌러라.
- ⚠️ **`UNKNOWN_###`** 는 pymavlink 사전에 없는 PX4 전용 메시지다. 합쳐서 20 B/s 쯤이라
  무시해도 된다.
- ⚠️ **지상 정지 값이다.** 비행 중에는 거리·자세로 `txbuf` 가 떨어져 PX4 가 깎는다
  (`MAV_0_RADIO_CTL=1`). 비행 중 값을 알고 싶으면 `.tlog` 로 재야 한다.
- ⚠️ **배터리 미연결이면** `BATTERY_STATUS` 가 안 잡힌다. 0 Hz 로 보여도 고장이 아니다.
