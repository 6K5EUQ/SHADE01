"""SHADE01 (Striver Mini VTOL 4+1, 신고번호 C2NV2850087) — 콕핏 화면용 3D 모델 (.glb).

    ~/tools/blender-4.5.9-linux-x64/blender -b -P web/model/striver.py -- web/public/model/striver.glb [preview.png]

치수는 제조사 자료(airframes/striver-mini-vtol/images/02-structure 평면도,
README 제원)에서, 도색·표식은 실기 사진(2026-09-26)에서 뽑았다:
익폭 2.10 m, 동체 1.20 m, 동체 높이 0.156 m, 로터암 x=±0.43 m (카본 원형 파이프),
역T 꼬리, 기수 견인 모터. 전체 흰색이고 우익 윗면에 신고번호를 크게 쓴다.
좌익 윗면에는 같은 글씨로 기체명 SHADE01 을 쓴다.

좌표 (Blender): 기수 -Y, 위 +Z, 좌익 +X. glTF 로 내보내면 기수 +Z, 위 +Y.
three.js 쪽이 이름으로 찾는 노드: rotor_LF/RF/LB/RB, prop_nose, gps.
"""
import bpy, bmesh, math, sys
from mathutils import Vector, Matrix

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = argv[0] if argv else 'striver.glb'
PREVIEW = argv[1] if len(argv) > 1 else None

bpy.ops.wm.read_factory_settings(use_empty=True)
scn = bpy.context.scene

# ── 재질 ──────────────────────────────────────────────────────────────
def mat(name, rgb, rough=0.5, metal=0.0, clear=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (*rgb, 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    if clear:
        b.inputs['Coat Weight'].default_value = clear
    return m

def srgb(h):
    h = h.lstrip('#')
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)

FOAM = mat('foam', srgb('#f1f2f3'), 0.6)
PANEL = mat('panel', srgb('#f7f7f8'), 0.35)          # 날개 가운데 판 — 광택이 조금 다르다
BLACK = mat('black', srgb('#17181b'), 0.5)
INK = mat('ink', srgb('#111214'), 0.7)               # 표식 글씨
CARBON = mat('carbon', srgb('#202226'), 0.3, 0.3, 0.6)
GROOVE = mat('groove', srgb('#c9ccd0'), 0.6)         # 조종면 힌지 홈·판 이음새
ALU = mat('alu', srgb('#c3c7cc'), 0.28, 0.95)
GLASS = mat('dark_grey', srgb('#2e3238'), 0.35, 0.2)
BATT = mat('battery', srgb('#2a2e36'), 0.45)
LABEL = mat('label_red', srgb('#c8302d'), 0.5)
PCB = mat('pcb', srgb('#1f2a24'), 0.5)
GOLD = mat('gold', srgb('#c9a24a'), 0.3, 0.9)
PMBLUE = mat('pm_blue', srgb('#2b4c7e'), 0.4)
XT = mat('xt_yellow', srgb('#e0b51f'), 0.5)
BAYVOL = mat('bayvol', srgb('#3e6ae1'), 0.5)     # 탑재칸 클릭 영역 — 화면에서는 안 그린다

def obj(name, me, m=None, parent=None, smooth=True):
    o = bpy.data.objects.new(name, me)
    scn.collection.objects.link(o)
    if m:
        me.materials.append(m)
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    if parent:
        o.parent = parent
    return o

def modifier_apply(o, kind, **kw):
    md = o.modifiers.new(kind.lower(), kind)
    for k, v in kw.items():
        setattr(md, k, v)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.modifier_apply(modifier=md.name)
    o.select_set(False)

# ── 단면 도구 ─────────────────────────────────────────────────────────
def naca(n=36, t=0.12, m=0.02, p=0.4):
    """(u, v) 루프. u 0=앞전 1=뒷전, v 는 시위 대비 두께. 윗면 TE→LE, 아랫면 LE→TE."""
    def at(x):
        yt = 5 * t * (0.2969 * math.sqrt(x) - 0.126 * x - 0.3516 * x * x + 0.2843 * x ** 3 - 0.1036 * x ** 4)
        yc = (m / (p * p) * (2 * p * x - x * x)) if x < p else (m / ((1 - p) ** 2) * ((1 - 2 * p) + 2 * p * x - x * x))
        return yc + yt, yc - yt
    pts = []
    for i in range(n, -1, -1):
        x = (1 - math.cos(math.pi * i / n)) / 2
        pts.append((x, at(x)[0]))
    for i in range(1, n):
        x = (1 - math.cos(math.pi * i / n)) / 2
        pts.append((x, at(x)[1]))
    return pts

AF = naca(40, 0.125, 0.025, 0.38)
AFT = naca(30, 0.09, 0.0, 0.4)

def loft(name, rings, m, cap=True, parent=None, smooth=True):
    """rings: [[Vector,...], ...] 같은 개수의 닫힌 고리. 사이를 사각면으로 잇는다."""
    bm = bmesh.new()
    vs = [[bm.verts.new(p) for p in r] for r in rings]
    n = len(rings[0])
    for a, b in zip(vs, vs[1:]):
        for j in range(n):
            bm.faces.new((a[j], a[(j + 1) % n], b[(j + 1) % n], b[j]))
    if cap:
        bm.faces.new(list(reversed(vs[0])))
        bm.faces.new(vs[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    return obj(name, me, m, parent, smooth)

def wing_ring(x, le_y, chord, z, prof=AF, thick=1.0, twist=0.0):
    r = []
    for u, v in prof:
        yy = le_y + u * chord
        zz = z + v * chord * thick
        # 비틀림(앞전 기준)
        dy, dz = yy - le_y, zz - z
        c, s = math.cos(twist), math.sin(twist)
        r.append(Vector((x, le_y + dy * c - dz * s, z + dy * s + dz * c)))
    return r

def airfoil_top(u, prof=AF):
    """윗면 v(u) — 데칼·힌지선 높이."""
    up = prof[:len(prof) // 2 + 1][::-1]  # LE→TE
    for (u0, v0), (u1, v1) in zip(up, up[1:]):
        if u0 <= u <= u1:
            return v0 + (v1 - v0) * (u - u0) / max(1e-9, u1 - u0)
    return 0.0

def split_prof(prof, uc, rear):
    """단면을 시위 uc 에서 자른다. rear=False 면 앞부분(0..uc), True 면 조종면(uc..1).
    둘 다 닫힌 고리이고 잘린 면은 평평하다. uc 가 같으면 고리 점 개수도 같다."""
    n = len(prof) // 2
    up = prof[:n + 1]                     # TE→LE (u 1→0)
    lo = prof[n + 1:]                     # LE→TE (u 0→1), 양 끝 제외
    lo_full = [prof[n]] + lo + [prof[0]]
    def at(seq, u):
        for (u0, v0), (u1, v1) in zip(seq, seq[1:]):
            if min(u0, u1) <= u <= max(u0, u1):
                return (u, v0 + (v1 - v0) * (u - u0) / ((u1 - u0) or 1e-9))
        return (u, 0.0)
    cu, cl = at(up, uc), at(lo_full, uc)
    if not rear:
        return [cu] + [q for q in up if q[0] < uc] + [q for q in lo if q[0] < uc] + [cl]
    return [q for q in up if q[0] > uc] + [cu, cl] + [q for q in lo if q[0] > uc]

def surface(name, rings, h0, h1, m=None):
    """조종면 — 힌지 h0→h1 을 로컬 Z 축으로 둔 객체로 만든다.
    화면(three.js)은 이 노드를 로컬 Y(= Blender 로컬 Z) 둘레로 돌린다."""
    axis = (h1 - h0).normalized()
    q = axis.to_track_quat('Z', 'Y')
    inv = q.inverted()
    piv = (h0 + h1) / 2
    o = loft(name, [[inv @ (v - piv) for v in r] for r in rings], m or FOAM, parent=root)
    o.location = piv
    o.rotation_mode = 'QUATERNION'
    o.rotation_quaternion = q
    return o

# ── 동체 ─────────────────────────────────────────────────────────────
# (y, 반폭, 윗면 z, 아랫면 z) — 기수(-Y)에서 꼬리로.
FUS = [
    (-0.520, 0.028, 0.020, -0.022),
    (-0.505, 0.036, 0.028, -0.030),
    (-0.470, 0.052, 0.044, -0.048),
    (-0.420, 0.070, 0.060, -0.064),
    (-0.350, 0.086, 0.074, -0.076),
    (-0.260, 0.097, 0.083, -0.080),
    (-0.150, 0.101, 0.086, -0.078),
    (-0.040, 0.098, 0.084, -0.072),
    (0.060, 0.088, 0.078, -0.062),
    (0.150, 0.070, 0.066, -0.048),
    (0.240, 0.050, 0.052, -0.034),
    (0.340, 0.036, 0.040, -0.026),
    (0.460, 0.029, 0.032, -0.021),
    (0.580, 0.025, 0.028, -0.018),
    (0.660, 0.022, 0.026, -0.016),
    (0.700, 0.016, 0.022, -0.012),
]
SEG = 48

def fus_ring(y, w, zt, zb, e=2.4, scale=1.0):
    r = []
    zc, h = (zt + zb) / 2, (zt - zb) / 2
    for i in range(SEG):
        a = 2 * math.pi * i / SEG
        c, s = math.cos(a), math.sin(a)
        x = w * scale * math.copysign(abs(c) ** (2 / e), c)
        z = zc + h * scale * math.copysign(abs(s) ** (2 / e), s)
        # 배를 약간 납작하게
        if z < zc:
            z = zc + (z - zc) * 0.92
        r.append(Vector((x, y, z)))
    return r

def fus_at(y):
    for a, b in zip(FUS, FUS[1:]):
        if a[0] <= y <= b[0]:
            t = (y - a[0]) / (b[0] - a[0])
            return tuple(a[i] + (b[i] - a[i]) * t for i in range(4))
    return FUS[-1]

root = bpy.data.objects.new('SHADE01', None)
scn.collection.objects.link(root)

fus = loft('fuselage', [fus_ring(*s) for s in FUS], FOAM, parent=root)
modifier_apply(fus, 'SUBSURF', levels=2)

def band(name, y, width, m, scale=1.004, parent=root):
    """동체를 감는 띠 (해치 이음새·결합부)."""
    rings = []
    for dy in (-width / 2, width / 2):
        yy, w, zt, zb = fus_at(y + dy)
        rings.append(fus_ring(yy, w, zt, zb, scale=scale))
    o = loft(name, rings, m, cap=False, parent=parent)
    modifier_apply(o, 'SOLIDIFY', thickness=0.0008)
    return o

# 꼬리붐 결합부 — 굵은 검정 링 하나와 가는 이음새
band('boom_ring', 0.215, 0.022, BLACK, scale=1.03)
band('boom_seam', 0.245, 0.004, BLACK, scale=1.02)

# 윗면 해치 이음새 — 가는 회색 선
def top_strip(name, y0, y1, xoff, m, wid=0.004, lift=0.0008):
    rings = []
    n = 14
    for k in range(n + 1):
        y = y0 + (y1 - y0) * k / n
        _, w, zt, zb = fus_at(y)
        x = math.copysign(min(abs(xoff), w * 0.8), xoff)
        zc, h = (zt + zb) / 2, (zt - zb) / 2
        z = zc + h * max(0.0, 1 - (abs(x) / w) ** 2.4) ** (1 / 2.4) + lift
        rings.append([Vector((x - wid / 2, y, z)), Vector((x + wid / 2, y, z)),
                      Vector((x + wid / 2, y, z - 0.002)), Vector((x - wid / 2, y, z - 0.002))])
    return loft(name, rings, m, parent=root, smooth=False)

top_strip('hatch_l', -0.43, -0.25, 0.045, GROOVE)
top_strip('hatch_r', -0.43, -0.25, -0.045, GROOVE)

def box(name, size, loc, m, parent=root, rot=(0, 0, 0), bevel=0.0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    bm.to_mesh(me)
    bm.free()
    o = obj(name, me, m, parent, smooth=False)
    o.location = loc
    o.rotation_euler = rot
    if bevel:
        modifier_apply(o, 'BEVEL', width=bevel, segments=2)
    return o

def cyl(name, r, h, loc, m, parent=root, rot=(0, 0, 0), verts=32, r2=None):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=verts, radius1=r, radius2=r if r2 is None else r2, depth=h)
    bm.to_mesh(me)
    bm.free()
    o = obj(name, me, m, parent)
    o.location = loc
    o.rotation_euler = rot
    return o

def surf_z(y, x=0.0):
    _, w, zt, zb = fus_at(y)
    zc, h = (zt + zb) / 2, (zt - zb) / 2
    return zc + h * max(0.0, 1 - (abs(x) / w) ** 2.4) ** (1 / 2.4)

# 배 — 검정 스키드
belly = [fus_ring(y, w * 0.5, zb + 0.010, zb - 0.002) for y, w, zt, zb in
         [fus_at(v) for v in (-0.40, -0.36, -0.28, -0.15, -0.04, 0.02)]]
bo = loft('belly', belly, BLACK, parent=root)
modifier_apply(bo, 'SUBSURF', levels=1)

# ── 기수 모터·프롭 (검정) ─────────────────────────────────────────────
cyl('nose_mount', 0.029, 0.010, (0, -0.522, -0.001), BLACK, rot=(math.pi / 2, 0, 0))
cyl('nose_motor', 0.026, 0.030, (0, -0.542, -0.001), GLASS, rot=(math.pi / 2, 0, 0))
cyl('nose_motor_band', 0.0265, 0.006, (0, -0.535, -0.001), ALU, rot=(math.pi / 2, 0, 0))

def blade_mesh(name, R, root_c, tip_c, m, thick=0.004, pitch=0.25, n=14):
    """평면형 날 한 장 — 허브(원점)에서 +X 로 뻗는다. 뿌리에서 끝으로 비틀림이 준다."""
    rings = []
    for k in range(n + 1):
        t = k / n
        x = 0.012 + (R - 0.012) * t
        c = root_c + (tip_c - root_c) * t ** 0.8
        c *= (1 - (t ** 6) * 0.55)
        if t < 0.12:
            c = root_c * (0.55 + 0.45 * t / 0.12)
        tw = pitch * (1 - 0.6 * t)
        th = thick * (1 - 0.6 * t)
        prof = [(-0.3, 0), (0.0, 0.5), (0.5, 0.35), (0.7, 0.0), (0.5, -0.25), (0.0, -0.35)]
        ring = []
        for u, v in prof:
            yy, zz = u * c, v * th
            ring.append(Vector((x, yy * math.cos(tw) - zz * math.sin(tw), yy * math.sin(tw) + zz * math.cos(tw))))
        rings.append(ring)
    o = loft(name, rings, m)
    return o

def propeller(name, R, root_c, tip_c, m, hub_m, loc, axis='Z'):
    """2엽 프롭 — 빈 객체(회전축) 아래에 날 두 장과 허브. 회전은 이 객체의 로컬 Z(glTF Y)."""
    e = bpy.data.objects.new(name, None)
    scn.collection.objects.link(e)
    e.parent = root
    e.location = loc
    if axis == 'Y':
        e.rotation_euler = (math.pi / 2, 0, 0)
    for k in range(2):
        b = blade_mesh(f'{name}_b{k}', R, root_c, tip_c, m)
        b.parent = e
        b.rotation_euler = (0, 0, math.pi * k)
    hub = cyl(f'{name}_hub', 0.013, 0.012, (0, 0, 0), hub_m, parent=e)
    return e

pn = propeller('prop_nose', 0.18, 0.030, 0.016, CARBON, BLACK, (0, -0.563, -0.001), axis='Y')
sp = cyl('spinner', 0.015, 0.032, (0, 0, 0.019), BLACK, parent=pn, r2=0.002)

# ── 날개 ─────────────────────────────────────────────────────────────
LE0, C0, Z0 = -0.245, 0.285, 0.080       # 뿌리 앞전·시위·높이
DIH = 0.022                              # 상반각 (z/x)
TWK = 0.2                                # 비틀림 반영 비율
def wing_sec(x):
    """(앞전 y, 시위, 높이 z, 비틀림) — 끝 0.12 m 는 둥글게 줄며 위로 휜다 (실기 정면 사진)."""
    ax = abs(x)
    if ax <= 0.93:
        c = C0 - (C0 - 0.255) * (ax / 0.93)
        le = LE0 + 0.010 * ax / 0.93
        zup = 0.0
    else:
        t = (ax - 0.93) / 0.12
        c = 0.255 - 0.10 * t ** 2.2
        le = LE0 + 0.010 + 0.05 * t ** 2.4
        zup = 0.032 * t ** 2
    return le, c, Z0 + ax * DIH + zup, -0.035 * ax / 1.05

XS = [-1.05, -1.045, -1.035, -1.02, -1.0, -0.975, -0.95, -0.93, -0.85, -0.6, -0.3, -0.1, 0.0,
      0.1, 0.3, 0.6, 0.85, 0.93, 0.95, 0.975, 1.0, 1.02, 1.035, 1.045, 1.05]
UA, AX0, AX1 = 0.72, 0.50, 0.95        # 에일러론 힌지 시위 비율, 스팬 구간
def wring(x, prof=AF):
    le, c, z, tw = wing_sec(x)
    return wing_ring(x, le, c, z, prof=prof, twist=tw * TWK)
def whinge(x):
    le, c, z, tw = wing_sec(x)
    return wring(x, [(UA, (airfoil_top(UA) + min(v for u, v in AF if abs(u - UA) < 0.05)) / 2)])[0]
loft('wing', [wring(x) for x in (-0.5, -0.3, -0.1, 0.0, 0.1, 0.3, 0.5)], FOAM, parent=root)
for sgn in (-1, 1):
    s = 'L' if sgn > 0 else 'R'
    mid = sorted(sgn * x for x in (0.5, 0.6, 0.7, 0.85, 0.93, 0.95))
    tip = sorted(sgn * x for x in (0.95, 0.975, 1.0, 1.02, 1.035, 1.045, 1.05))
    loft(f'wing_mid_{s}', [wring(x, split_prof(AF, UA, False)) for x in mid], FOAM, parent=root)
    loft(f'wing_tip_{s}', [wring(x) for x in tip], FOAM, parent=root)
    surface(f'aileron_{s}', [wring(x, split_prof(AF, UA, True)) for x in mid], whinge(mid[0]), whinge(mid[-1]))

def wing_top(x, y):
    """날개 윗면 높이 — 표식·선을 표면에 붙일 때 쓴다."""
    le, c, z, tw = wing_sec(x)
    u = min(1.0, max(0.0, (y - le) / c))
    t = tw * TWK
    return z + u * c * math.sin(t) + airfoil_top(u) * c * math.cos(t)

def wing_band(name, x0, x1, m, grow=1.02, n=4):
    rs = []
    for k in range(n + 1):
        x = x0 + (x1 - x0) * k / n
        le, c, z, tw = wing_sec(x)
        cc = c * grow
        rs.append(wing_ring(x, le - (cc - c) * 0.5, cc, z - 0.0005, thick=grow, twist=tw * TWK))
    return loft(name, rs, m, parent=root)

def surface_line(name, x0, x1, u, m, wid=0.003, n=10):
    """날개 윗면을 따라 스팬 방향으로 가는 선 (시위 비율 u, x0→x1)."""
    rings = []
    for k in range(n + 1):
        x = x0 + (x1 - x0) * k / n
        le, c, _, _ = wing_sec(x)
        y = le + u * c
        z = wing_top(x, y) + 0.0006
        rings.append([Vector((x, y - wid / 2, z)), Vector((x, y + wid / 2, z)),
                      Vector((x, y + wid / 2, z - 0.0015)), Vector((x, y - wid / 2, z - 0.0015))])
    return loft(name, rings, m, parent=root, smooth=False)

def chord_line(name, x, u0, u1, m, wid=0.003, n=12):
    """날개 윗면 시위 방향의 가는 선 (판 이음새)."""
    rings = []
    for k in range(n + 1):
        le, c, _, _ = wing_sec(x)
        y = le + (u0 + (u1 - u0) * k / n) * c
        z = wing_top(x, y) + 0.0006
        rings.append([Vector((x - wid / 2, y, z)), Vector((x + wid / 2, y, z)),
                      Vector((x + wid / 2, y, z - 0.0015)), Vector((x - wid / 2, y, z - 0.0015))])
    return loft(name, rings, m, parent=root, smooth=False)

for sgn in (-1, 1):
    s = 'L' if sgn > 0 else 'R'
    # 날개-동체 결합부 검정 띠
    xs = sorted((sgn * 0.100, sgn * 0.116))
    wing_band(f'root_band_{s}', xs[0], xs[1], BLACK, grow=1.03, n=1)
    # 가운데 판(광택)과 바깥 판 이음새
    xs = sorted((sgn * 0.116, sgn * 0.47))
    wing_band(f'center_panel_{s}', xs[0], xs[1], PANEL, grow=1.004, n=6)
    chord_line(f'panel_seam_{s}', sgn * 0.47, 0.02, 0.98, GROOVE)
    # 에일러론 힌지 홈 · 힌지 세 개 · 서보 혼 덮개
    for k, xx in enumerate((0.56, 0.72, 0.88)):
        x = sgn * xx
        le, c, _, _ = wing_sec(x)
        y = le + 0.72 * c
        box(f'hinge_{s}{k}', (0.004, 0.022, 0.0015), (x, y, wing_top(x, y) + 0.0007), BLACK)
        box(f'hinge_{s}{k}a', (0.012, 0.003, 0.0015), (x, y - 0.011, wing_top(x, y - 0.011) + 0.0007), BLACK)
        box(f'hinge_{s}{k}b', (0.012, 0.003, 0.0015), (x, y + 0.011, wing_top(x, y + 0.011) + 0.0007), BLACK)
    x = sgn * 0.64
    le, c, _, _ = wing_sec(x)
    y = le + 0.84 * c
    box(f'servo_{s}', (0.028, 0.022, 0.0015), (x, y, wing_top(x, y) + 0.0007), BLACK)

# ── 표식 — 글자를 메시로 만들어 표면에 눌러 붙인다 ─────────────────────
FONT = None
# 실기 신고번호는 Arial Narrow Bold 계열 — 같은 폭의 Liberation Sans Narrow Bold 를 쓴다
import os
for f in ('/usr/share/fonts/truetype/liberation/LiberationSansNarrow-Bold.ttf',
          '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'):
    if os.path.exists(f):
        FONT = bpy.data.fonts.load(f)
        break

def lettering(name, body, length, place, m=INK, k=None):
    """body 를 폭 length 로 맞춘 평면 글자(+X 로 읽힘, 윗변 +Y)로 만들고
    place(tx, ty) → Vector 로 꼭짓점마다 옮긴다. 곡면을 따라가게 잘게 나눈다."""
    cu = bpy.data.curves.new(name, 'FONT')
    cu.body = body
    if FONT:
        cu.font = FONT
    cu.align_x = 'CENTER'
    cu.align_y = 'CENTER'
    cu.fill_mode = 'BOTH'
    cu.resolution_u = 4
    o = bpy.data.objects.new(name, cu)
    scn.collection.objects.link(o)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.convert(target='MESH')
    o.select_set(False)
    me = o.data
    xs = [v.co.x for v in me.vertices]
    if k is None:
        k = length / (max(xs) - min(xs))
    half = (max(xs) - min(xs)) * k / 2
    bm = bmesh.new()
    bm.from_mesh(me)
    # 곡면을 따라가도록 1 cm 격자로 자른다 (글자 모양은 그대로 둔다)
    lo = [min(v.co[i] for v in bm.verts) for i in (0, 1)]
    hi = [max(v.co[i] for v in bm.verts) for i in (0, 1)]
    step = 0.01 / k
    for i, no in ((0, (1, 0, 0)), (1, (0, 1, 0))):
        t = lo[i] + step
        while t < hi[i]:
            co = [0, 0, 0]; co[i] = t
            bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=co, plane_no=no)
            t += step
    bmesh.ops.triangulate(bm, faces=bm.faces)
    for v in bm.verts:
        v.co = place(v.co.x * k, v.co.y * k, half)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    me.materials.append(m)
    for p in me.polygons:
        p.use_smooth = False
    o.parent = root
    return k

# 신고번호 — 우익(-X) 윗면, 뿌리→끝으로 읽히고 글자 윗변이 앞전 쪽 (실기와 같다)
REG = 'C2NV2850087'
RX0, RX1 = 0.16, 0.88
def reg_place(tx, ty, half):
    x = -((RX0 + RX1) / 2 + tx)       # 읽는 방향 = -X
    le, c, _, _ = wing_sec(x)
    y = le + 0.38 * c - ty            # 윗변 = 앞전(-Y)
    return Vector((x, y, wing_top(x, y) + 0.0009))
REG_K = lettering('registration', REG, RX1 - RX0, reg_place)

# 기체명 — 좌익(+X) 윗면, 신고번호와 같은 글자 크기·방향 (뒤에서 읽힘), 뿌리 쪽에서 시작
def name_place(tx, ty, half):
    x = RX0 + half - tx               # 읽는 방향 = -X (끝→뿌리)
    le, c, _, _ = wing_sec(x)
    y = le + 0.38 * c - ty
    return Vector((x, y, wing_top(x, y) + 0.0009))
lettering('name', 'SHADE01', None, name_place, k=REG_K)

# ── 꼬리 ─────────────────────────────────────────────────────────────
HT_LE, HT_C, HT_Z = 0.545, 0.14, 0.010
def ht_sec(x):
    ax = abs(x)
    if ax <= 0.28:
        return HT_LE + 0.01 * ax / 0.28, HT_C - 0.012 * ax / 0.28
    t = (ax - 0.28) / 0.055
    return HT_LE + 0.01 + 0.035 * t ** 2, HT_C - 0.012 - 0.05 * t ** 1.6
hx = [-0.335, -0.332, -0.325, -0.31, -0.28, -0.15, 0.0, 0.15, 0.28, 0.31, 0.325, 0.332, 0.335]
UE = 0.66
hring = lambda x, prof=AFT: wing_ring(x, *ht_sec(x), HT_Z, prof=prof)
def hhinge(x):
    le, c = ht_sec(x)
    return Vector((x, le + UE * c, HT_Z))
loft('htail', [hring(x) for x in (-0.03, 0.0, 0.03)], FOAM, parent=root)
for sgn in (-1, 1):
    s = 'L' if sgn > 0 else 'R'
    mid = sorted(sgn * x for x in (0.03, 0.1, 0.2, 0.28, 0.30))
    tip = sorted(sgn * x for x in (0.30, 0.31, 0.325, 0.332, 0.335))
    loft(f'htail_mid_{s}', [hring(x, split_prof(AFT, UE, False)) for x in mid], FOAM, parent=root)
    loft(f'htail_tip_{s}', [hring(x) for x in tip], FOAM, parent=root)
    surface(f'elevator_{s}', [hring(x, split_prof(AFT, UE, True)) for x in mid], hhinge(mid[0]), hhinge(mid[-1]))
for sgn in (-1, 1):
    # 뿌리 앞전 검정 띠 · 엘리베이터 힌지 홈
    xs = sorted((sgn * 0.02, sgn * 0.075))
    rs = []
    for x in [xs[0] + (xs[1] - xs[0]) * k / 3 for k in range(4)]:
        le, c = ht_sec(x)
        rs.append(wing_ring(x, le - 0.001, c * 0.30, HT_Z - 0.0003, prof=AFT, thick=3.6))
    loft(f'ht_root_{sgn}', rs, BLACK, parent=root)

# 수직꼬리 — 앞전이 크게 후퇴하고 위 뒤쪽이 둥글다
def vt_ring(z, le, c):
    return [Vector((v * c, le + u * c, z)) for u, v in AFT]
VT = [(0.012, 0.455, 0.235), (0.05, 0.475, 0.222), (0.12, 0.510, 0.195), (0.20, 0.548, 0.165),
      (0.255, 0.572, 0.143), (0.285, 0.588, 0.122), (0.300, 0.603, 0.098), (0.306, 0.618, 0.07)]
UR = 0.66
def vt_ring_p(z, le, c, prof):
    return [Vector((v * c, le + u * c, z)) for u, v in prof]
VT_R = [q for q in VT if q[0] <= 0.285]
loft('vtail', [vt_ring_p(*q, split_prof(AFT, UR, False)) for q in VT_R], FOAM, parent=root)
loft('vtail_top', [vt_ring(*q) for q in VT if q[0] >= 0.285], FOAM, parent=root)
rh = lambda q: Vector((0, q[1] + UR * q[2], q[0]))
surface('rudder', [vt_ring_p(*q, split_prof(AFT, UR, True)) for q in VT_R], rh(VT_R[0]), rh(VT_R[-1]))

def vt_at(z):
    for a, b in zip(VT, VT[1:]):
        if a[0] <= z <= b[0]:
            t = (z - a[0]) / (b[0] - a[0])
            return a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t
    return VT[-1][1], VT[-1][2]

def vt_side(y, z, sgn, lift=0.0008):
    le, c = vt_at(z)
    u = min(1.0, max(0.0, (y - le) / c))
    return Vector((sgn * (airfoil_top(u, AFT) * c + lift), y, z))

for sgn in (-1, 1):
    # 러더 서보 판 · 힌지 세 개
    box(f'rudder_servo_{sgn}', (0.002, 0.036, 0.036), vt_side(0.64, 0.05, sgn, 0.0012), BLACK)
    for k, zz in enumerate((0.07, 0.14, 0.21)):
        le, c = vt_at(zz)
        box(f'rudder_hinge_{sgn}{k}', (0.0015, 0.022, 0.004), vt_side(le + 0.66 * c, zz, sgn), BLACK)

# ── VTOL 로터암 (카본 원형 파이프) ─────────────────────────────────────
ARM_Y0, ARM_Y1 = -0.585, 0.275
FRONT_Y, BACK_Y = -0.56, 0.25
for sgn in (-1, 1):
    x = sgn * 0.43
    le, c, z, tw = wing_sec(x)
    zb = z + min(v for u, v in AF) * c    # 날개 아랫면
    az = zb - 0.013
    cyl(f'arm_{"L" if sgn > 0 else "R"}', 0.011, ARM_Y1 - ARM_Y0, (x, (ARM_Y0 + ARM_Y1) / 2, az), CARBON,
        rot=(math.pi / 2, 0, 0), verts=24)
    # 날개 고정 클램프
    for yy in (le + 0.035, le + c - 0.045):
        box(f'clamp_{sgn}_{yy:.2f}', (0.032, 0.026, 0.030), (x, yy, az + 0.004), BLACK, bevel=0.003)
    for name_k, yy in (('F', FRONT_Y), ('B', BACK_Y)):
        s = ('L' if sgn > 0 else 'R') + name_k
        d = -1 if name_k == 'F' else 1
        # 접이 관절 — 검정 슬리브
        cyl(f'fold_{s}', 0.015, 0.05, (x, yy - d * 0.085, az), BLACK, rot=(math.pi / 2, 0, 0), verts=24)
        cyl(f'fold_knob_{s}', 0.009, 0.036, (x, yy - d * 0.085, az), BLACK, rot=(0, math.pi / 2, 0), verts=16)
        # 모터 받침 — 파이프 끝을 감싸는 검정 블록과 그 아래 원통(착지부)
        box(f'mount_{s}', (0.034, 0.05, 0.03), (x, yy - d * 0.01, az), BLACK, bevel=0.004)
        cyl(f'pod_{s}', 0.024, 0.055, (x, yy, az - 0.035), BLACK, verts=32)
        cyl(f'pod_cap_{s}', 0.02, 0.004, (x, yy, az - 0.064), GLASS, verts=32)
        # 모터 (M4112 — 지름 46, 높이 ~28)
        mz = az + 0.015
        cyl(f'motor_base_{s}', 0.022, 0.006, (x, yy, mz + 0.003), BLACK)
        cyl(f'motor_{s}', 0.023, 0.024, (x, yy, mz + 0.018), GLASS)
        cyl(f'motor_label_{s}', 0.0233, 0.006, (x, yy, mz + 0.016), ALU)
        cyl(f'motor_cap_{s}', 0.016, 0.006, (x, yy, mz + 0.033), BLACK)
        # 프롭 (카본 2엽, 지름 ~0.43)
        p = propeller(f'rotor_{s}', 0.215, 0.038, 0.020, CARBON, BLACK, (x, yy, mz + 0.041))
        p.rotation_euler = (0, 0, {'LF': 0.4, 'RF': 1.9, 'LB': 2.7, 'RB': 0.9}[s])

# GPS — 날개 앞 동체 윗면의 검정 모듈 · 흰 안테나 받침
gy = -0.285
gps = box('gps', (0.042, 0.036, 0.012), (0, gy, surf_z(gy) + 0.004), BLACK, bevel=0.003)
box('gps_bracket', (0.05, 0.008, 0.01), (0, gy + 0.03, surf_z(gy + 0.03) + 0.003), BLACK, bevel=0.002)
cyl('top_stub', 0.004, 0.016, (0, gy + 0.075, surf_z(gy + 0.075) + 0.008), FOAM, verts=12)
box('top_stub_t', (0.018, 0.004, 0.004), (0, gy + 0.075, surf_z(gy + 0.075) + 0.016), FOAM)

# ── 탑재칸 · 해치 · 내부 부품 ─────────────────────────────────────────
# 칸 구획은 제조사 캐빈 구성(airframes/striver-mini-vtol/README.md 「구조/캐빈별 사양」)
# 순서를 따르고, 부품은 components/*/README.md 의 치수다. 화면이 칸을 누르면
# 해치를 들고 동체를 반투명하게 해 이것들이 보인다.
def fus_arc(y, a0, a1, scale, n=20):
    _, w, zt, zb = fus_at(y)
    zc, h = (zt + zb) / 2, (zt - zb) / 2
    e = 2.4
    out = []
    for k in range(n + 1):
        a = a0 + (a1 - a0) * k / n
        c, s_ = math.cos(a), math.sin(a)
        out.append(Vector((w * scale * math.copysign(abs(c) ** (2 / e), c), y,
                           zc + h * scale * math.copysign(abs(s_) ** (2 / e), s_))))
    return out

def hatch(name, y0, y1, n=10):
    rings = []
    for k in range(n + 1):
        y = y0 + (y1 - y0) * k / n
        outer = fus_arc(y, math.radians(22), math.radians(158), 1.014)
        inner = fus_arc(y, math.radians(22), math.radians(158), 1.002)
        rings.append(outer + inner[::-1])
    o = loft(name, rings, FOAM, parent=root)
    return o

hatch('hatch_F', -0.44, -0.255)
hatch('hatch_R', 0.055, 0.19)

BAYS = {'head': (-0.525, -0.40), 'battery': (-0.40, -0.155), 'power': (-0.155, -0.05),
        'payload': (-0.05, 0.11), 'fc': (0.11, 0.20)}
# 칸 영역은 동체 곡면을 그대로 따른다 — 그 구간의 동체 단면을 조금 키워 잇는다.
# 화면은 양 끝 단면의 테두리만 선으로 긋고 안을 옅게 칠한다.
for k, (y0, y1) in BAYS.items():
    ys = [y0 + (y1 - y0) * i / 8 for i in range(9)]
    loft(f'bay_{k}', [fus_ring(*fus_at(y), scale=1.03) for y in ys], BAYVOL, parent=root)
# GPS — 모듈 모양(둥근 판)에 맞춘다
cyl('bay_gps', 0.034, 0.03, (0, gy, surf_z(gy) + 0.006), BAYVOL, verts=32)

# 기수 — 크루즈 ESC (MFE ESC 6100, 74×37×16)
box('in_head_esc', (0.037, 0.074, 0.016), (0, -0.455, -0.012), BLACK, bevel=0.002)
for k in range(4):
    box(f'in_head_esc_fin{k}', (0.03, 0.004, 0.003), (0, -0.48 + k * 0.016, -0.003), GLASS)
# 배터리 — Fullymax 6S 16000mAh (196.5×89×59), XT90
box('in_battery', (0.089, 0.1965, 0.059), (0, -0.285, -0.012), BATT, bevel=0.004)
box('in_battery_label', (0.0905, 0.03, 0.0605), (0, -0.25, -0.012), LABEL, bevel=0.004)
box('in_battery_xt90', (0.021, 0.02, 0.011), (0.015, -0.392, -0.004), XT, bevel=0.002)
# 배전 — PDB 300A · PM08-CAN · UBEC
box('in_power_pdb', (0.06, 0.075, 0.004), (0, -0.10, -0.05), PCB)
for k in range(5):
    box(f'in_power_xt{k}', (0.011, 0.009, 0.008), (-0.024 + k * 0.012, -0.132, -0.044), XT)
box('in_power_pm08', (0.036, 0.045, 0.016), (0.02, -0.095, -0.036), PMBLUE, bevel=0.002)
box('in_power_ubec', (0.033, 0.055, 0.013), (-0.022, -0.095, -0.037), BLACK, bevel=0.002)
# 탑재 — SDR 페이로드 (탑재칸 220×150×110)
box('in_payload_sdr', (0.09, 0.13, 0.045), (0, 0.03, -0.022), ALU, bevel=0.004)
for k in range(3):
    cyl(f'in_payload_port{k}', 0.004, 0.008, (-0.025 + k * 0.025, -0.036, -0.018), GOLD, rot=(math.pi / 2, 0, 0), verts=12)
# FC — Pixhawk 6C Mini (54×39×18) · RP4TD-M 수신기
box('in_fc_fmu', (0.039, 0.054, 0.016), (0, 0.15, -0.012), GLASS, bevel=0.003)
box('in_fc_cap', (0.037, 0.052, 0.002), (0, 0.15, -0.003), ALU, bevel=0.001)
box('in_fc_rx', (0.018, 0.03, 0.007), (0.03, 0.15, -0.014), BLACK)
for sgn in (-1, 1):
    cyl(f'in_fc_rx_ant{sgn}', 0.0015, 0.05, (0.03 + sgn * 0.006, 0.18, -0.008), BLACK, rot=(math.pi / 2 - 0.3, 0, 0), verts=8)

# ── 내보내기 ─────────────────────────────────────────────────────────
bpy.ops.object.select_all(action='SELECT')
bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB', use_selection=False,
                          export_yup=True, export_apply=True, export_materials='EXPORT')
print('wrote', OUT)

if PREVIEW:
    for o in scn.objects:
        if o.name.startswith('bay_'):
            o.hide_render = True
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam'))
    scn.collection.objects.link(cam)
    cam.data.lens = 55
    cam.location = (-2.3, 2.2, 1.7)
    d = Vector((0, 0, 0.05)) - cam.location
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    scn.camera = cam
    sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN'))
    sun.data.energy = 3.5
    sun.rotation_euler = (0.6, 0.3, 0.8)
    scn.collection.objects.link(sun)
    w = bpy.data.worlds.new('w'); scn.world = w
    w.use_nodes = True
    w.node_tree.nodes['Background'].inputs[0].default_value = (0.9, 0.88, 0.89, 1)
    w.node_tree.nodes['Background'].inputs[1].default_value = 0.8
    scn.render.engine = 'CYCLES'
    scn.cycles.samples = 48
    scn.cycles.device = 'CPU'
    scn.render.resolution_x, scn.render.resolution_y = 1400, 900
    scn.render.filepath = PREVIEW
    bpy.ops.render.render(write_still=True)
    # 위에서
    cam.location = (0, 0, 4.2); cam.rotation_euler = (0, 0, 0); cam.data.lens = 50
    scn.render.filepath = PREVIEW.replace('.png', '_top.png')
    bpy.ops.render.render(write_still=True)
