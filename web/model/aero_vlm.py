#!/usr/bin/env python3
# 콕핏 「공력」 탭 값의 출처 — pip install aerosandbox (4.2) 후 python aero_vlm.py [CG_x m] [무게 kg]
# 결과는 cockpit.js 의 AERO 에 손으로 옮긴다. 형상(striver.py)을 고치면 같이 고치고 다시 돌려라.
# 제조사 평면도(airframes/striver-mini-vtol/images/02, 정사영)에서 픽셀로 잰 치수. 축척 = 날개폭 2100 mm (동체 1217 mm 로 1.4% 일치)
# x 뒤+, y 오른쪽, z 위. 원점 = 날개 앞전(뿌리)
import aerosandbox as asb, aerosandbox.numpy as np, json, math, sys
AF = asb.Airfoil("naca2412"); AFT = asb.Airfoil("naca0009")
W = [(0.0,0.300),(0.126,0.300),(0.315,0.298),(0.525,0.291),(0.735,0.277),(0.892,0.265),(0.945,0.260),(0.976,0.254),(0.998,0.242),(1.018,0.222),(1.034,0.194),(1.045,0.161)]
LEoff = {0.998:0.015,1.018:0.036,1.034:0.062,1.045:0.093,0.976:0.006,0.945:0.002}   # 끝 둥근 앞전
DIH=0.022
wing=asb.Wing(name="wing",symmetric=True,xsecs=[asb.WingXSec(xyz_le=[LEoff.get(y,0),y,y*DIH],chord=c,airfoil=AF,twist=-0.4*y) for y,c in W])
# 수평꼬리: 앞전 0.755~0.787 m, 뒷전 0.933 m, 반폭 0.327 m
HT=[(0.0,0.755,0.180),(0.082,0.758,0.175),(0.164,0.769,0.164),(0.229,0.778,0.155),(0.279,0.786,0.147),(0.327,0.800,0.125)]
def htail(de=0.0): return asb.Wing(name="htail",symmetric=True,xsecs=[asb.WingXSec(xyz_le=[x,y,-0.07],chord=c,airfoil=AFT,twist=0.55*de) for y,x,c in HT])
VT=[(0.0,0.69,0.235),(0.12,0.745,0.195),(0.255,0.807,0.143),(0.306,0.853,0.07)]   # 수직꼬리는 사진 추정 그대로
vtail=asb.Wing(name="vtail",xsecs=[asb.WingXSec(xyz_le=[x,0,z-0.07],chord=c,airfoil=AFT) for z,x,c in VT])
fus=asb.Fuselage(name="fus",xsecs=[asb.FuselageXSec(xyz_c=[x,0,z],radius=r) for x,z,r in
   [(-0.275,-0.05,0.01),(-0.22,-0.05,0.045),(-0.08,-0.03,0.075),(0.10,-0.03,0.08),(0.30,-0.05,0.06),(0.55,-0.06,0.035),(0.80,-0.07,0.02),(0.94,-0.07,0.01)]])
CG_X = float(sys.argv[1]) if len(sys.argv)>1 else 0.090      # 로터 중심 — 앞 로터 −0.292, 뒤 +0.473 의 가운데 = 0.090 (뿌리 시위 30%)
M = float(sys.argv[2]) if len(sys.argv)>2 else 6.8
def plane(de=0.0): return asb.Airplane(name="s",xyz_ref=[CG_X,0,0],wings=[wing,htail(de),vtail],fuselages=[fus],s_ref=wing.area(),c_ref=wing.mean_aerodynamic_chord(),b_ref=wing.span())
p0=plane(); V=19; rho=1.225
vlm=lambda a,de=0.0: asb.VortexLatticeMethod(airplane=plane(de),op_point=asb.OperatingPoint(velocity=V,alpha=a),spanwise_resolution=8,chordwise_resolution=6).run()
r1,r2=vlm(2.0),vlm(6.0); CLa=(r2["CL"]-r1["CL"])/4; Cma=(r2["Cm"]-r1["Cm"])/4
xnp=CG_X-Cma/CLa*p0.c_ref; de=(vlm(2.0,5.0)["Cm"]-r1["Cm"])/5
# 최대 양력계수: 익형(NACA2412, Re≈3.5e5) 실속 받음각 근처에서 AeroBuildup
ab=[(a,float(np.ravel(asb.AeroBuildup(airplane=p0,op_point=asb.OperatingPoint(velocity=15,alpha=a)).run()["CL"])[0])) for a in range(8,19)]
clmax=max(c for a,c in ab)
o=dict(S=p0.s_ref,MAC=p0.c_ref,AR=p0.b_ref**2/p0.s_ref,S_ht=htail().area(),Vh=htail().area()*(0.80+0.25*0.16-CG_X)/(p0.s_ref*p0.c_ref),
  CLa=float(CLa),SM=float((xnp-CG_X)/p0.c_ref*100),xnp=float(xnp),CG_pct=CG_X/0.300*100,dCm_de=float(de),
  CLmax_buildup=clmax,Vs_buildup=math.sqrt(2*M*9.81/(rho*p0.s_ref*clmax)),Vs_cl10=math.sqrt(2*M*9.81/(rho*p0.s_ref*1.0)),Vs_cl12=math.sqrt(2*M*9.81/(rho*p0.s_ref*1.2)))
tr=[]
for Vc in (14,16,18,19,21,24):
    CL=M*9.81/(0.5*rho*Vc**2*p0.s_ref); a=2+(CL-float(r1["CL"]))/float(CLa); cm=float(r1["Cm"])+(a-2)*float(Cma); tr.append((Vc,round(CL,3),round(a,2),round(-cm/float(de),2)))
o["trim"]=tr
print(json.dumps({k:(round(v,4) if isinstance(v,float) else v) for k,v in o.items()}))
ld=[(a,float(np.ravel((r:=asb.AeroBuildup(airplane=p0,op_point=asb.OperatingPoint(velocity=19,alpha=a)).run())["CL"])[0])/float(np.ravel(r["CD"])[0])) for a in range(0,9)]
print('LDmax', max(ld,key=lambda t:t[1]))
