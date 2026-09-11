#!/usr/bin/env python3
"""받은 `.ulg` 가 온전한지 본다. 깨진 것만 이름을 찍는다.

    logcheck.py <파일...>

종료코드 0 = 전부 온전, 1 = 하나라도 의심

## 왜 필요한가 (2026-09-11)

`fcfetch.py` 는 **크기만 맞으면 성공**으로 친다. MAVFTP 전송은 512바이트
블록 단위로 조용히 어긋나는데(FLIGHT-SYNC.md), 그래도 파일 크기는 그대로라
`✅ 받았다` 가 찍히고 아무도 모른 채 서버까지 올라간다.

실제로 그 일이 났다. `2026-09-11_08_26_41.ulg` (9.0MB) 는 정의 섹션 중간이
깨져 **토픽 65개만** 읽혔다 — 같은 날 다른 편은 88~101개다. 그 결과 웹
로그 뷰어에서 전력·진동·모터출력·GPS·센서불일치 **다섯 단이 통째로 사라졌다.**
사용자가 "전류 항목이 없다" 고 지적해서야 발견됐다.

## 무엇으로 잡나 — 핵심 토픽의 유무

🔴 **CRC 로는 못 잡는다.** FLIGHT-SYNC.md 「그래서 단순 CRC 검증은 넣지
않았다」 참조: 한 연결에서 CalcFileCRC32 를 연속 호출하면 값이 흔들리고,
새 연결로 재도 9MB 짜리는 계산이 타임아웃된다 (실측 3회 중 2회 err=1).

대신 **파싱해서 있어야 할 토픽이 있는지** 본다. 아래 목록은 이 기체가
arm 한 로그라면 예외 없이 남기는 것들이다. 하나라도 없으면 정의 섹션이
깨졌다는 뜻이다.

실측 대조 (2026-09-01 세션 14편):

| | 토픽 수 | 판정 |
|---|---|---|
| 정상 10편 | 81~96 | 통과 |
| 04_49_38 | 44 | 🔴 actuator_armed 없음 — 분석도 실패 |
| 05_18_33 | 42 | 🔴 battery·imu·gps 없음 |
| 05_19_39 | 0 | 🔴 전부 없음 |
| 06_41_04 | 49 | 🔴 battery·imu·gps 없음 (0.14MB, 원래 안 받는 크기) |

**오탐이 없었다** — 걸린 넷은 전부 실제로 깨졌거나 분석이 안 되는 것이다.

## 걸리면 어떻게 하나

`./shade01 sync --verify` 로 그 파일만 다시 받는다. 5회 받아 바이트
다수결로 복원한다 — 어긋나는 블록이 매번 달라서 다수결이 원본을 되살린다.

한 편만 고칠 거면 `fcvote.py` 를 직접 부르는 편이 빠르다:

    tools/qgclog/fcvote.py /fs/microsd/log/<날짜>/<이름>.ulg <저장경로> 5
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# 🔴 arm 한 로그라면 반드시 있는 토픽. 없으면 정의 섹션이 깨진 것이다.
#    지상에서 arm 도 안 한 로그(0.2MB 대)는 애초에 sync 가 안 받으므로
#    여기까지 오지 않는다.
CORE = [
    'actuator_armed',            # 없으면 analyse() 자체가 못 돈다
    'vehicle_attitude',
    'vehicle_local_position',
    'battery_status',            # 전력 차트
    'vehicle_imu_status',        # 진동 차트
    'sensor_gps',                # GPS 품질 차트
]

# 토픽 수 하한. 이 기체 정상 로그는 81~101개였다 (2026-09-01·09-11 실측).
# 60 은 그보다 한참 아래라 정상을 걸지 않는다.
MIN_TOPICS = 60


def check(path):
    """(ok, 사유) — ok=False 면 다시 받아야 한다."""
    import warnings
    warnings.filterwarnings('ignore')
    import contextlib
    import qgclog
    try:
        with open(os.devnull, 'w') as dn, \
                contextlib.redirect_stdout(dn), contextlib.redirect_stderr(dn):
            ulog, _ = qgclog._load(path)
    except Exception as exc:
        return False, '파싱 실패: %s' % str(exc)[:60]

    names = {d.name for d in ulog.data_list}
    missing = [n for n in CORE if n not in names]
    if missing:
        return False, '핵심 토픽 %d개 없음: %s (토픽 %d개)' % (
            len(missing), ', '.join(missing[:3]), len(names))
    if len(names) < MIN_TOPICS:
        return False, '토픽이 %d개뿐이다 (정상 81~101)' % len(names)
    return True, '토픽 %d개' % len(names)


def main():
    if len(sys.argv) < 2:
        print(__doc__.split('\n')[2].strip())
        return 2
    bad = 0
    for p in sys.argv[1:]:
        if not os.path.exists(p):
            print('   ✗ %-30s 파일이 없다' % os.path.basename(p))
            bad += 1
            continue
        ok, why = check(p)
        if not ok:
            print('   🔴 %-30s %s' % (os.path.basename(p), why))
            bad += 1
    if bad:
        print('   → 다시 받아라: ./shade01 sync --verify '
              '(5회 다수결로 복원한다)')
    return 1 if bad else 0


if __name__ == '__main__':
    sys.exit(main())
