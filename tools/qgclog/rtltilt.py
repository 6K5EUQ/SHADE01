#!/usr/bin/env python3
"""RTL 구간의 경사·자세변화율·수평가속을 잰다.

    rtltilt.py <로그.ulg> [...]

## 왜 필요한가 (2026-09-15)

조종자가 "RTL 이 속도를 내려고 롤·피치를 너무 급격히 튼다" 고 지적했고, 실측하니
맞았다 — 출발 1~2초에 경사가 **20~22°** 까지 튀었다 (평균은 2~4°).

`MPC_ACC_HOR` 3.0 → 2.0, `MPC_JERK_AUTO` 4.0 → 2.0 으로 낮췄으므로
**다음 야외 비행에서 이 도구로 다시 재어 효과를 확인한다.**

기대: 경사 최대 **12~14°**. 그만큼 안 내려가면 `MPC_ACC_HOR` 가 아니라 다른
값이 지배하는 것이다 (`MPC_ACC_HOR_MAX`·`MPC_XY_TRAJ_P` 를 본다).

🔴 **경사와 가속은 같은 것의 두 표현이다** — `수평가속 = g·tan(경사)`.
   3.4 m/s² 가 19.4° 다. 둘 중 하나만 봐도 되지만 같이 찍어 서로 검산한다.
"""

import sys, warnings, numpy as np
sys.path.insert(0,'tools/qgclog'); warnings.filterwarnings('ignore')
import qgclog
def g(u,n):
    for d in u.data_list:
        if d.name==n: return d.data
for f in sys.argv[1:]:
    u,_=qgclog._load(f)
    vs=g(u,'vehicle_status'); att=g(u,'vehicle_attitude'); lp=g(u,'vehicle_local_position')
    if not (vs and att and lp): continue
    tv=np.asarray(vs['timestamp'],float)/1e6; nav=np.asarray(vs['nav_state'],int)
    r=np.where(nav==5)[0]
    if not len(r): continue
    t0,t1=tv[r[0]],tv[r[-1]]
    # 쿼터니언 → 롤/피치
    ta=np.asarray(att['timestamp'],float)/1e6
    q=[np.asarray(att['q[%d]'%i],float) for i in range(4)]
    w,x,y,z=q
    roll=np.degrees(np.arctan2(2*(w*x+y*z), 1-2*(x*x+y*y)))
    pitch=np.degrees(np.arcsin(np.clip(2*(w*y-z*x),-1,1)))
    m=(ta>=t0)&(ta<=t1)
    tilt=np.hypot(roll[m],pitch[m])
    # 변화율 (deg/s)
    tt=ta[m]
    dr=np.abs(np.diff(roll[m])/np.maximum(np.diff(tt),1e-3))
    dp=np.abs(np.diff(pitch[m])/np.maximum(np.diff(tt),1e-3))
    tl=np.asarray(lp['timestamp'],float)/1e6
    vx=np.asarray(lp['vx'],float); vy=np.asarray(lp['vy'],float)
    ml=(tl>=t0)&(tl<=t1)
    hs=np.hypot(vx[ml],vy[ml])
    acc=np.abs(np.diff(hs)/np.maximum(np.diff(tl[ml]),1e-3))
    print('=== %s ===' % f.split('/')[-1][:26])
    print('  경사(tilt)  최대 %.1f°   평균 %.1f°' % (tilt.max(), tilt.mean()))
    print('  롤          최대 %+.1f° ~ %+.1f°' % (roll[m].min(), roll[m].max()))
    print('  피치        최대 %+.1f° ~ %+.1f°' % (pitch[m].min(), pitch[m].max()))
    print('  롤 변화율   최대 %.0f °/s  (95%%값 %.0f)' % (dr.max(), np.percentile(dr,95)))
    print('  피치 변화율 최대 %.0f °/s  (95%%값 %.0f)' % (dp.max(), np.percentile(dp,95)))
    print('  수평가속    최대 %.2f m/s²' % acc.max())
