#!/usr/bin/env python3
"""같은 파일을 여러 번 받아 **바이트 다수결**로 원본을 복원한다.

    fcvote.py <원격경로> <로컬경로> [횟수]
    fcvote.py /fs/microsd/log/2026-09-05/09_17_20.ulg out.ulg 5

## 왜 필요한가 (2026-09-06 실측)

FC 가 SD 를 읽을 때마다 **다른 바이트**를 낸다. 같은 파일을 6번 받으면 크기는
같고 md5 는 6개 다 다르다. 손상은 **512바이트 섹터 단위**로 나타나고, 한 번
읽을 때 2278섹터 중 **7~14개**가 어긋난다 (약 1.4%).

그런데 **어긋나는 섹터가 읽기마다 다르다.** 그래서 여러 번 받아 위치별로
가장 많이 나온 바이트를 고르면 원본이 복원된다.

실측 6회 다수결:

| | |
|---|---|
| 의견이 갈린 바이트 | 878 |
| **과반 미달** | **0** |
| leave-one-out(5개) 결과 | **6/6 이 전체 다수결과 동일** |

복원 결과의 PX4 CRC 는 `0xb07bcdd5` 였는데, 이는 **FC 자신이 낸 CRC 값 중
하나**다 — 독립적인 교차검증이다. 반면 그때 서버에 있던 사본의 CRC 는 FC 가
한 번도 낸 적이 없었고, 분석값도 달랐다 (19초·66mAh vs 진짜 20초·68mAh).

⚠️ **근본 해결이 아니다.** SD 카드를 갈아라 — `fccrc.py` 로 재검증할 수 있다.
이건 카드를 갈기 전까지, 또는 이미 지나간 비행을 정확히 건져야 할 때 쓴다.

## 비용

받는 횟수만큼 곱해진다. 1.17MB 가 회당 6초였으니 5회면 30초다.
큰 파일(22MB)은 회당 45초라 5회면 4분이다.

## 쓰는 법

FC 가 USB 로 붙어 있는 PC 에서 돌린다. **브리지를 먼저 멈춰야 한다.**

    ssh rim3@rim3 'systemctl --user stop shade-bridge.service'
    scp tools/qgclog/{fcvote.py,fcfetch.py} rim3@rim3:/tmp/
    ssh rim3@rim3 'cd /tmp && ~/.venv-mav/bin/python fcvote.py <원격> <로컬> 5'
    ssh rim3@rim3 'systemctl --user start shade-bridge.service'
"""
import collections
import hashlib
import os
import sys
import time
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/tmp")          # FC 쪽 PC 로 복사해 쓸 때

from fcfetch import cmd_get, connect                       # noqa: E402

# 5회면 leave-one-out 이 안정되는 것을 실측했다. 3회는 두 표가 갈릴 때
# 과반이 안 나올 수 있어 권하지 않는다.
DEFAULT_N = 5

# 이보다 적은 표차로 정해진 바이트가 있으면 경고한다 — 표본이 모자란 것이다.
_WEAK_MARGIN = 2


def px4_crc32(data):
    """PX4(NuttX crc32part, 초기값 0) 방식. `fccrc.py` 와 같은 식이다."""
    return zlib.crc32(data, 0xFFFFFFFF) ^ 0xFFFFFFFF


def fetch_many(remote, n, device="/dev/ttyACM0", baud=115200, tmpdir="/tmp"):
    """n 회 받아 바이트열 리스트를 낸다. 크기가 다른 판본은 버린다."""
    out = []
    for i in range(1, n + 1):
        # 🔴 FC 는 한 연결에 파일 하나만 내준다. 매번 다시 붙는다.
        m, ftp = connect(device, baud)
        local = os.path.join(tmpdir, "_vote_%d.bin" % i)
        t0 = time.time()
        err, size, el = cmd_get(ftp, remote, local, quiet=True)
        m.close()
        try:
            with open(local, "rb") as f:
                data = f.read()
        except OSError as e:
            print("  %d: 읽기 실패 %s" % (i, e), flush=True)
            continue
        finally:
            try:
                os.unlink(local)
            except OSError:
                pass
        print("  %d: %d바이트  md5=%s  %.0f초"
              % (i, len(data), hashlib.md5(data).hexdigest()[:12], el), flush=True)
        if err:
            print("     err=%s — 버린다" % err, flush=True)
            continue
        out.append(data)
        time.sleep(0.5)
    return out


def vote(samples):
    """(복원된 bytes, 통계). 크기가 다수와 다른 판본은 이미 걸러졌다고 본다."""
    sizes = collections.Counter(len(s) for s in samples)
    size, _ = sizes.most_common(1)[0]
    keep = [s for s in samples if len(s) == size]
    dropped = len(samples) - len(keep)

    out = bytearray(size)
    contested = weak = 0
    for i in range(size):
        c = collections.Counter(s[i] for s in keep)
        (best, n1), = c.most_common(1)
        out[i] = best
        if n1 < len(keep):
            contested += 1
            n2 = c.most_common(2)[1][1] if len(c) > 1 else 0
            if n1 - n2 < _WEAK_MARGIN:
                weak += 1
    return bytes(out), {"used": len(keep), "dropped": dropped,
                        "contested": contested, "weak": weak}


def main():
    if len(sys.argv) < 3:
        sys.exit("사용법: fcvote.py <원격경로> <로컬경로> [횟수]")
    remote, local = sys.argv[1], sys.argv[2]
    n = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_N
    if n < 3:
        sys.exit("횟수는 3 이상이어야 다수결이 성립한다 (권장 5)")

    print("%s — %d회 받아 다수결" % (remote, n))
    samples = fetch_many(remote, n)
    if len(samples) < 3:
        sys.exit("성공한 판본이 %d개뿐이다 — 다수결 불가" % len(samples))

    data, st = vote(samples)
    with open(local, "wb") as f:
        f.write(data)

    print()
    print("복원: %s" % local)
    print("  표본 %d개 사용%s" % (st["used"],
          " (크기 다른 %d개 버림)" % st["dropped"] if st["dropped"] else ""))
    print("  의견 갈린 바이트 %d개, 표차 1 이하 %d개" % (st["contested"], st["weak"]))
    print("  md5=%s  px4crc=0x%08x"
          % (hashlib.md5(data).hexdigest(), px4_crc32(data)))
    if st["weak"]:
        print("  ⚠️ 표차가 아슬아슬한 자리가 있다 — 횟수를 늘려라 (예: 7)")
    # 판본 하나를 빼도 결과가 같은지 — 표본이 충분한지 보는 가장 싼 검사다.
    if len(samples) >= 4:
        alt, _ = vote(samples[:-1])
        print("  leave-one-out: %s" % ("동일 (안정)" if alt == data else "⚠️ 다름 — 횟수를 늘려라"))


if __name__ == "__main__":
    main()
