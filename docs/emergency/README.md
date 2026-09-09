# 비상 절차 문서

현장에서 종이로 들고 보는 체크리스트 3종. `.md` 가 원본, `.pdf` 는 인쇄용이다.

| 문서 | 언제 |
|---|---|
| [`01-preflight.md`](01-preflight.md) · [PDF](01-preflight.pdf) | 배터리 연결 전 ~ ARM 직전 |
| [`02-postlaunch.md`](02-postlaunch.md) · [PDF](02-postlaunch.pdf) | 이륙 직후 단계별 확장 + 상시 감시 |
| [`03-emergency.md`](03-emergency.md) · [PDF](03-emergency.pdf) | 비행 전에 외워 둔다. 현장에서는 「즉시 판단표」한 장 |

## 값은 2026-09-09 FC 실측 기준이다

**정본은 언제나 FC 다.** [`FC_CHANGELOG.md`](../../FC_CHANGELOG.md) 에 그 이후 변경이 있으면
이 문서보다 그쪽이 최신이다. FC 값을 바꿨으면 여기 표도 같이 고쳐라.

🔴 **`.pdf` 는 아직 2026-09-05 판이다 — 인쇄본을 들고 나가기 전에 다시 만들어라.**
9/9 대조에서 `.md` 를 크게 고쳤다. 그 전 판은 이렇게 틀려 있었다:

| 항목 | 옛 판(틀림) | 실제 |
|---|---|---|
| 지오펜스 | `GF_ACTION=2` Hold, 150/50 m | **꺼짐** (`0`, 거리 0) — 기체가 안 멈춘다 |
| 데이터링크 상실 | `NAV_DLL_ACT=0` 동작 없음 | **`2` RTL** — 10초 뒤 복귀한다 |
| RTL 고도 | 60 / 30 m | **20 / 10 m** |
| 미션 이착륙 | 84/85 여야 한다 | **22/21 이어야 한다** (84 는 고정익 전환을 건다) |
| 도달 반경 | 10 m | **3 m** |

## PDF 다시 만들기

```bash
python3 tools/md2pdf.py docs/emergency/01-preflight.md /tmp/out.html
google-chrome --headless --disable-gpu --no-pdf-header-footer \
  --print-to-pdf=docs/emergency/01-preflight.pdf file:///tmp/out.html
```
