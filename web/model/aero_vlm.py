#!/usr/bin/env python3
# 콕핏 「공력」 탭 값의 출처 — pip install aerosandbox (4.2) 후 python aero_vlm.py
# 결과는 cockpit.js 의 AERO 에 손으로 옮긴다. 형상(striver.py)을 고치면 다시 돌려라.
# striver.py 형상(Blender 모델)을 그대로 옮긴 VLM/AeroBuildup 해석.
# 좌표: 모델 y(앞=-) → asb x(뒤=+), 모델 x(스팬) → asb y, 모델 z → asb z.
import aerosandbox as asb, aerosandbox.numpy as np, math, json
AF = asb.Airfoil("naca2412"); AFT = asb.Airfoil("naca0009")
LE0, C0, Z0, DIH = -0.245, 0.285, 0.080, 0.022
def wing_sec(ax):
    if ax <= 0.93:
        c = C0 - (C0 - 0.255) * (ax / 0.93); le = LE0 + 0.010 * ax / 0.93; zup = 0
    else:
        t = (ax - 0.93) / 0.12; c = 0.255 - 0.10 * t ** 2.2; le = LE0 + 0.010 + 0.05 * t ** 2.4; zup = 0.032 * t ** 2
    return le, c, Z0 + ax * DIH + zup, -0.035 * ax / 1.05 * 0.2
def wxsec(ax, cs=None):
    le, c, z, tw = wing_sec(ax)
    return asb.WingXSec(xyz_le=[le, ax, z], chord=c, twist=math.degrees(tw), airfoil=AF, control_surfaces=cs or [])
ail = lambda: [asb.ControlSurface(name="aileron", symmetric=False, hinge_point=0.72, deflection=0)]
wing = asb.Wing(name="wing", symmetric=True, xsecs=[wxsec(0), wxsec(0.5, ail()), wxsec(0.93, ail()), wxsec(1.0), wxsec(1.05)])
HT_LE, HT_C, HT_Z = 0.545, 0.14, 0.010
def ht(ax, de):
    if ax <= 0.28: le, c = HT_LE + 0.01 * ax / 0.28, HT_C - 0.012 * ax / 0.28
    else:
        t = (ax - 0.28) / 0.055; le, c = HT_LE + 0.01 + 0.035 * t ** 2, HT_C - 0.012 - 0.05 * t ** 1.6
    # VLM 은 조종면 꺾임을 안 그린다 — 승강타 각 de 를 꼬리 전체 붙임각 τ·de 로 대신한다 (34% 시위 플랩 τ≈0.55)
    return asb.WingXSec(xyz_le=[le, ax, HT_Z], chord=c, airfoil=AFT, twist=0.55 * de)
def htail(de=0.0): return asb.Wing(name="htail", symmetric=True, xsecs=[ht(0, de), ht(0.28, de), ht(0.335, de)])
VT = [(0.012, 0.455, 0.235), (0.12, 0.510, 0.195), (0.255, 0.572, 0.143), (0.306, 0.618, 0.07)]
vtail = asb.Wing(name="vtail", xsecs=[asb.WingXSec(xyz_le=[le, 0, z], chord=c, airfoil=AFT) for z, le, c in VT])
fus = asb.Fuselage(name="fus", xsecs=[asb.FuselageXSec(xyz_c=[x, 0, z], radius=r) for x, z, r in
      [(-0.56, 0.0, 0.01), (-0.50, 0.0, 0.045), (-0.35, 0.02, 0.075), (-0.15, 0.03, 0.08), (0.05, 0.02, 0.06), (0.30, 0.01, 0.035), (0.55, 0.01, 0.02), (0.64, 0.01, 0.01)]])
CG_X = -0.155   # 로터 중심 (앞뒤 모터 출력 균형 58.5% / 57.5% — 9/11 로그) 
def plane(de=0.0):
    return asb.Airplane(name="striver", xyz_ref=[CG_X, 0, 0.05], wings=[wing, htail(de), vtail], fuselages=[fus],
                        s_ref=wing.area(), c_ref=wing.mean_aerodynamic_chord(), b_ref=wing.span())
p0 = plane()
out = {"S": p0.s_ref, "MAC": p0.c_ref, "b": p0.b_ref, "AR": p0.b_ref**2 / p0.s_ref, "S_ht": htail().area(), "S_vt": vtail.area()}
V = 19.0; rho = 1.225; m = 6.8; g = 9.81
alphas = np.linspace(-4, 14, 10)
res = []
for a in alphas:
    op = asb.OperatingPoint(velocity=V, alpha=a)
    ab = asb.AeroBuildup(airplane=p0, op_point=op).run()
    vl = asb.VortexLatticeMethod(airplane=p0, op_point=op, spanwise_resolution=8, chordwise_resolution=6).run()
    res.append((float(a), float(vl["CL"]), float(vl["Cm"]), float(np.ravel(ab["CL"])[0]), float(np.ravel(ab["CD"])[0]), float(np.ravel(ab["Cm"])[0])))
out["polar"] = res
# 중립점 (VLM)
a1, a2 = 2.0, 6.0
def vlm(a, de=0.0, pl=None):
    return asb.VortexLatticeMethod(airplane=pl or plane(de), op_point=asb.OperatingPoint(velocity=V, alpha=a), spanwise_resolution=8, chordwise_resolution=6).run()
r1, r2 = vlm(a1), vlm(a2)
CLa = (r2["CL"] - r1["CL"]) / (a2 - a1); Cma = (r2["Cm"] - r1["Cm"]) / (a2 - a1)
x_np = CG_X - Cma / CLa * p0.c_ref
out.update({"CLa_per_deg": float(CLa), "Cma_per_deg": float(Cma), "x_np": float(x_np), "static_margin_pct": float((x_np - CG_X) / p0.c_ref * 100),
            "cg_pct_rootchord": (CG_X - LE0) / C0 * 100})
# 승강타 효과 (+ = 뒷전 아래)
rd = vlm(2.0, de=5.0); r0 = vlm(2.0, de=0.0)
out["dCm_per_deg_elev"] = float((rd["Cm"] - r0["Cm"]) / 5.0)
# 트림: 순항 속도별 필요 CL·받음각·승강타
trim = []
for Vc in (14, 16, 18, 19, 21, 24):
    CLreq = m * g / (0.5 * rho * Vc**2 * p0.s_ref)
    a_tr = (CLreq - float(r0["CL"]) + 2.0 * float(CLa)) / float(CLa)    # 선형
    cm_a = float(r0["Cm"]) + (a_tr - 2.0) * float(Cma)
    de_tr = -cm_a / out["dCm_per_deg_elev"]
    trim.append((Vc, CLreq, a_tr, de_tr))
out["trim"] = trim
out["Vstall_CLmax1.2"] = (2 * m * g / (rho * p0.s_ref * 1.2)) ** 0.5
out["Vstall_CLmax1.0"] = (2 * m * g / (rho * p0.s_ref * 1.0)) ** 0.5
pol=out.pop("polar")
print(json.dumps({k:(round(v,4) if isinstance(v,float) else v) for k,v in out.items() if k!="trim"}, default=float))
print("alpha  CL_vlm  Cm_vlm | CL_ab  CD_ab  L/D  Cm_ab")
for a,cl,cm,cla,cd,cma in pol: print(f"{a:5.1f} {cl:6.3f} {cm:7.3f} | {cla:6.3f} {cd:6.4f} {cla/cd:5.1f} {cma:7.3f}")
print("V  CLreq  alpha_trim  elev_trim(+=TE down)")
for t in out["trim"]: print("%4.0f %6.3f %7.2f %8.2f" % tuple(t))
