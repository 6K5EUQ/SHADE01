"""Striver Mini VTOL 4+1 — 콕핏 화면용 3D 모델 (.glb) 을 만든다.

    ~/tools/blender-4.5.9-linux-x64/blender -b -P web/model/striver.py -- web/public/model/striver.glb [preview.png]

치수는 제조사 자료(airframes/striver-mini-vtol/images/02-structure 평면도,
README 제원)에서 뽑았다: 익폭 2.10 m, 동체 1.20 m, 동체 높이 0.156 m,
로터암 x=±0.43 m (744 mm 카본 각파이프), 역T 꼬리, 기수 견인 모터.

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

FOAM = mat('foam', srgb('#eef0f1'), 0.55)
BLACK = mat('black', srgb('#1b1d20'), 0.45)
CARBON = mat('carbon', srgb('#23262b'), 0.28, 0.35, 0.6)
RED = mat('red', srgb('#c9302c'), 0.4)
ALU = mat('alu', srgb('#c3c7cc'), 0.28, 0.95)
BLUE = mat('blue', srgb('#1f6fe0'), 0.3, 0.85)
PROPG = mat('prop_grey', srgb('#9aa1a8'), 0.4)
STICK = mat('sticker', srgb('#e2a41f'), 0.5)
GLASS = mat('dark_grey', srgb('#3a3f46'), 0.35, 0.2)

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

for i, y in enumerate((-0.36, -0.235, 0.075, 0.20)):
    band(f'seam{i}', y, 0.006, BLACK)

# 윗면 해치 테두리 — 날개 앞뒤로 검은 가장자리
def top_strip(name, y0, y1, xoff, m, wid=0.010, lift=0.0015):
    rings = []
    n = 14
    for k in range(n + 1):
        y = y0 + (y1 - y0) * k / n
        _, w, zt, zb = fus_at(y)
        # 윗면 곡선 위의 점 (초타원 근사)
        x = math.copysign(min(abs(xoff), w * 0.8), xoff)
        zc, h = (zt + zb) / 2, (zt - zb) / 2
        z = zc + h * max(0.0, 1 - (abs(x) / w) ** 2.4) ** (1 / 2.4) + lift
        rings.append([Vector((x - wid / 2, y, z)), Vector((x + wid / 2, y, z)),
                      Vector((x + wid / 2, y, z - 0.003)), Vector((x - wid / 2, y, z - 0.003))])
    return loft(name, rings, m, parent=root, smooth=False)

top_strip('hatch_l', -0.34, -0.245, 0.05, BLACK)
top_strip('hatch_r', -0.34, -0.245, -0.05, BLACK)
top_strip('hatch_l2', 0.085, 0.19, 0.035, BLACK)
top_strip('hatch_r2', 0.085, 0.19, -0.035, BLACK)

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

# 윗면 스티커 3장 (주황)
for i, y in enumerate((-0.30, -0.19, 0.12)):
    box(f'sticker{i}', (0.028, 0.022, 0.001), (0.0 if i != 1 else 0.03, y, surf_z(y) + 0.0008), STICK)
# ESC 통풍 덮개 — 기수 옆면 검은 격자판
for sgn in (-1, 1):
    y = -0.40
    _, w, zt, zb = fus_at(y)
    g = box(f'esc_cover{"L" if sgn > 0 else "R"}', (0.002, 0.05, 0.028), (sgn * w * 0.97, y, (zt + zb) / 2 - 0.004), BLACK,
            rot=(0, 0, sgn * -0.25))
    for k in range(4):
        box(f'esc_slot{sgn}{k}', (0.0025, 0.04, 0.0025), (sgn * w * 0.975, y, (zt + zb) / 2 - 0.014 + k * 0.0065), GLASS,
            rot=(0, 0, sgn * -0.25))
# 배 스키드 — 검은 판
belly = [fus_ring(y, w * 0.55, zb + 0.012, zb - 0.002) for y, w, zt, zb in
         [fus_at(v) for v in (-0.43, -0.40, -0.30, -0.15, -0.02, 0.06, 0.09)]]
bo = loft('belly', belly, BLACK, parent=root)
modifier_apply(bo, 'SUBSURF', levels=1)

# ── 기수 모터·프롭 ────────────────────────────────────────────────────
cyl('nose_mount', 0.030, 0.012, (0, -0.524, -0.001), BLACK, rot=(math.pi / 2, 0, 0))
cyl('nose_motor', 0.027, 0.030, (0, -0.545, -0.001), BLUE, rot=(math.pi / 2, 0, 0))
cyl('nose_motor_band', 0.0275, 0.008, (0, -0.537, -0.001), ALU, rot=(math.pi / 2, 0, 0))

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

pn = propeller('prop_nose', 0.165, 0.030, 0.018, PROPG, BLUE, (0, -0.566, -0.001), axis='Y')
sp = cyl('spinner', 0.016, 0.03, (0, 0, 0.018), BLUE, parent=pn, r2=0.002)

# ── 날개 ─────────────────────────────────────────────────────────────
LE0, C0, Z0 = -0.245, 0.285, 0.080       # 뿌리 앞전·시위·높이
DIH = 0.025                              # 상반각 (z/x)
def wing_sec(x):
    ax = abs(x)
    # 끝 0.12 m 는 앞전이 둥글게 뒤로 말린다
    if ax <= 0.93:
        c = C0 - (C0 - 0.25) * (ax / 0.93)
        le = LE0 + 0.012 * ax / 0.93
    else:
        t = (ax - 0.93) / 0.12
        c = 0.25 - 0.12 * t ** 1.8
        le = LE0 + 0.012 + 0.10 * t ** 2.2
    return le, c, Z0 + ax * DIH, -0.035 * ax / 1.05

XS = [-1.05, -1.04, -1.02, -0.99, -0.96, -0.93, -0.85, -0.6, -0.3, -0.1, 0.0,
      0.1, 0.3, 0.6, 0.85, 0.93, 0.96, 0.99, 1.02, 1.04, 1.05]
rings = []
for x in XS:
    le, c, z, tw = wing_sec(x)
    rings.append(wing_ring(x, le, c, z, twist=tw * 0.2))
wing = loft('wing', rings, FOAM, parent=root)

def wing_band(name, x0, x1, m, grow=1.02, n=4):
    rs = []
    for k in range(n + 1):
        x = x0 + (x1 - x0) * k / n
        le, c, z, tw = wing_sec(x)
        cc = c * grow
        rs.append(wing_ring(x, le - (cc - c) * 0.5, cc, z - 0.0005, thick=grow))
    return loft(name, rs, m, parent=root)

# 붉은 날개 끝 · 날개-동체 결합부 검은 띠 · 로터암 고정 띠
for sgn in (-1, 1):
    s = 'L' if sgn > 0 else 'R'
    xs = sorted((sgn * 0.995, sgn * 1.05))
    wing_band(f'tip_{s}', xs[0], xs[1], RED, grow=1.015)
    xs = sorted((sgn * 0.105, sgn * 0.125))
    wing_band(f'root_band_{s}', xs[0], xs[1], BLACK, grow=1.03, n=1)
    xs = sorted((sgn * 0.40, sgn * 0.412))
    wing_band(f'arm_band_{s}', xs[0], xs[1], BLACK, grow=1.025, n=1)
    xs = sorted((sgn * 0.448, sgn * 0.46))
    wing_band(f'arm_band2_{s}', xs[0], xs[1], BLACK, grow=1.025, n=1)

# 에일러론 힌지선 · 끝 아랫면 검은 패치
for sgn in (-1, 1):
    s = 'L' if sgn > 0 else 'R'
    for u, x0, x1 in ((0.74, 0.56, 0.95),):
        pts = []
        for k in range(9):
            x = sgn * (x0 + (x1 - x0) * k / 8)
            le, c, z, tw = wing_sec(x)
            y = le + u * c
            zz = z + airfoil_top(u) * c + 0.0006
            pts.append((x, y, zz))
        for (xa, ya, za), (xb, yb, zb_) in zip(pts, pts[1:]):
            mid = Vector(((xa + xb) / 2, (ya + yb) / 2, (za + zb_) / 2))
            box(f'hinge_{s}_{xa:.2f}', (abs(xb - xa) + 0.002, 0.003, 0.0012), mid, BLACK)
    # 서보 덮개 (작은 검은 사각) + 혼
    x = sgn * 0.62
    le, c, z, tw = wing_sec(x)
    box(f'servo_{s}', (0.03, 0.018, 0.0012), (x, le + 0.62 * c, z + airfoil_top(0.62) * c + 0.0006), BLACK)

# 윙렛 모양 아랫면 검정 (날개 끝 뒤쪽)
# STRIVER 데칼 — 날개 윗면·수평꼬리
def decal(name, body, size, loc, rot_z, m=BLACK):
    cu = bpy.data.curves.new(name, 'FONT')
    cu.body = body
    cu.size = size
    cu.align_x = 'CENTER'
    cu.align_y = 'CENTER'
    cu.extrude = 0.0004
    o = bpy.data.objects.new(name, cu)
    scn.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (0, 0, rot_z)
    bpy.context.view_layer.objects.active = o
    o.select_set(True)
    bpy.ops.object.convert(target='MESH')
    o.select_set(False)
    o.data.materials.append(m)
    o.parent = root
    return o

for sgn in (-1, 1):
    x = sgn * 0.74
    le, c, z, tw = wing_sec(x)
    u = 0.33
    decal(f'striver_{sgn}', 'STRIVER', 0.042, (x, le + u * c, z + airfoil_top(u) * c + 0.0012), math.pi if sgn > 0 else 0)
    # 로고 옆 쉐브론
    x = sgn * 0.30
    le, c, z, tw = wing_sec(x)
    for k in range(3):
        u = 0.18 + k * 0.07
        decal(f'chev_{sgn}_{k}', '›', 0.03, (x, le + u * c, z + airfoil_top(u) * c + 0.0012), -math.pi / 2)

# ── 꼬리 ─────────────────────────────────────────────────────────────
HT_LE, HT_C, HT_Z = 0.545, 0.14, 0.010
def ht_sec(x):
    ax = abs(x)
    if ax <= 0.28:
        return HT_LE + 0.01 * ax / 0.28, HT_C - 0.012 * ax / 0.28
    t = (ax - 0.28) / 0.055
    return HT_LE + 0.01 + 0.045 * t ** 2, HT_C - 0.012 - 0.06 * t ** 1.6
hx = [-0.335, -0.33, -0.32, -0.30, -0.28, -0.15, 0.0, 0.15, 0.28, 0.30, 0.32, 0.33, 0.335]
ht = loft('htail', [wing_ring(x, *ht_sec(x), HT_Z, prof=AFT) for x in hx], FOAM, parent=root)
for sgn in (-1, 1):
    xs = sorted((sgn * 0.30, sgn * 0.335))
    rs = []
    for x in [xs[0] + (xs[1] - xs[0]) * k / 4 for k in range(5)]:
        le, c = ht_sec(x)
        rs.append(wing_ring(x, le - c * 0.01, c * 1.02, HT_Z - 0.0003, prof=AFT, thick=1.02))
    loft(f'ht_tip_{sgn}', rs, BLACK, parent=root)
    x = sgn * 0.17
    le, c = ht_sec(x)
    decal(f'ht_striver_{sgn}', 'STRIVER', 0.026, (x, le + 0.4 * c, HT_Z + airfoil_top(0.4, AFT) * c + 0.001), math.pi if sgn > 0 else 0)
    # 엘리베이터 힌지
    le, c = ht_sec(sgn * 0.16)
    box(f'elev_hinge_{sgn}', (0.26, 0.003, 0.0012), (sgn * 0.16, le + 0.68 * c, HT_Z + airfoil_top(0.68, AFT) * c + 0.0005), BLACK)

# 수직꼬리 — 높고 약간 후퇴, 위 끝 검은 캡
def vt_ring(z, le, c):
    return [Vector((v * c, le + u * c, z)) for u, v in AFT]
VT = [(0.012, 0.470, 0.215), (0.06, 0.485, 0.205), (0.14, 0.515, 0.185), (0.22, 0.545, 0.160),
      (0.275, 0.565, 0.140), (0.292, 0.575, 0.125), (0.298, 0.590, 0.100)]
vt = loft('vtail', [vt_ring(*s) for s in VT], FOAM, parent=root)
loft('vt_cap', [vt_ring(z, le - 0.002, c * 1.03) for z, le, c in VT[-3:]], BLACK, parent=root)
# ── VTOL 로터암 ───────────────────────────────────────────────────────
ARM_Y0, ARM_Y1 = -0.585, 0.275
FRONT_Y, BACK_Y = -0.56, 0.25
for sgn in (-1, 1):
    x = sgn * 0.43
    le, c, z, tw = wing_sec(x)
    zb = z - 0.012 * c / 0.28 * 0 + min(v for u, v in AF) * c   # 날개 아랫면
    az = zb - 0.011
    arm = box(f'arm_{"L" if sgn > 0 else "R"}', (0.020, ARM_Y1 - ARM_Y0, 0.020), (x, (ARM_Y0 + ARM_Y1) / 2, az), CARBON, bevel=0.002)
    # 날개 고정 클램프
    for yy in (le + 0.03, le + c - 0.04):
        box(f'clamp_{sgn}_{yy:.2f}', (0.030, 0.024, 0.026), (x, yy, az + 0.004), BLACK, bevel=0.002)
    for name_k, yy in (('F', FRONT_Y), ('B', BACK_Y)):
        s = ('L' if sgn > 0 else 'R') + name_k
        d = -1 if name_k == 'F' else 1
        # 알루미늄 접이 관절 (끝 쪽)
        box(f'fold_{s}', (0.028, 0.034, 0.026), (x, yy - d * 0.045, az), ALU, bevel=0.003)
        cyl(f'fold_pin_{s}', 0.006, 0.034, (x, yy - d * 0.045, az), BLACK, rot=(0, math.pi / 2, 0), verts=16)
        # 모터 마운트 판
        box(f'mount_{s}', (0.05, 0.05, 0.004), (x, yy, az + 0.012), ALU, bevel=0.0015)
        # 모터 (M4112 — 지름 46, 높이 ~28)
        mz = az + 0.014
        cyl(f'motor_base_{s}', 0.021, 0.006, (x, yy, mz + 0.003), BLACK)
        cyl(f'motor_{s}', 0.023, 0.024, (x, yy, mz + 0.018), GLASS)
        cyl(f'motor_ring_{s}', 0.0235, 0.004, (x, yy, mz + 0.026), ALU)
        cyl(f'motor_cap_{s}', 0.016, 0.006, (x, yy, mz + 0.033), BLACK)
        # 아래로 향한 착륙 다리
        cyl(f'leg_{s}', 0.005, 0.07, (x, yy - d * 0.02, az - 0.042), BLACK, verts=12)
        cyl(f'foot_{s}', 0.011, 0.006, (x, yy - d * 0.02, az - 0.078), BLACK, verts=16)
        # 프롭 (카본 2엽, 지름 0.40)
        p = propeller(f'rotor_{s}', 0.20, 0.036, 0.020, CARBON, BLACK, (x, yy, mz + 0.041))
        p.rotation_euler = (0, 0, {'LF': 0.4, 'RF': 1.9, 'LB': 2.7, 'RB': 0.9}[s])

# GPS 마스트 · 수신 안테나
gy = 0.33
g = cyl('gps_mast', 0.004, 0.07, (0, gy, surf_z(gy) + 0.035), BLACK, verts=12)
gps = cyl('gps', 0.026, 0.012, (0, gy, surf_z(gy) + 0.074), GLASS)
cyl('gps_top', 0.022, 0.003, (0, gy, surf_z(gy) + 0.0815), BLACK)
ay = 0.02
ant = cyl('antenna', 0.0035, 0.13, (0, ay, Z0 + 0.012 + 0.065), BLACK, verts=12, r2=0.0025)
cyl('antenna_base', 0.008, 0.01, (0, ay, Z0 + 0.016), BLACK)
# 피토관 — 좌익 앞전
cyl('pitot', 0.003, 0.11, (0.62, LE0 + 0.012 * 0.62 / 0.93 - 0.03, Z0 + 0.62 * DIH - 0.004), ALU, rot=(math.pi / 2, 0, 0), verts=10)

# ── 내보내기 ─────────────────────────────────────────────────────────
bpy.ops.object.select_all(action='SELECT')
bpy.ops.export_scene.gltf(filepath=OUT, export_format='GLB', use_selection=False,
                          export_yup=True, export_apply=True, export_materials='EXPORT')
print('wrote', OUT)

if PREVIEW:
    cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam'))
    scn.collection.objects.link(cam)
    cam.data.lens = 55
    cam.location = (2.6, 2.4, 1.6)
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
