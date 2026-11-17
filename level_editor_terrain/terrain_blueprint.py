# -*- coding: utf-8 -*-
"""
LLMが出力した地形ブループリント（設計仕様JSON）を、
空間アルゴリズムによるスプライン制御点（custom_radius / custom_tilt 含む）と
Geometry Nodes パラメータへコンパイルするモジュール。
旧来の生座標配列JSONに対する後方互換フォールバックも提供する。
"""
import math
import random
import time

ARCHETYPES = (
    "BASIN_CITY",
    "CANYON_HIGHWAY",
    "ALPINE_VALLEY",
    "COASTAL_RIDGE",
    "VOLCANIC_CALDERA",
    "PLAINS_METROPOLIS",
    "PLATEAU_MESA",
)

ROAD_TOPOLOGIES = (
    "RING_AND_SPOKE",
    "CROSS_VALLEY",
    "COASTAL_CORRIDOR",
    "MOUNTAIN_PASS",
    "GRID_ORGANIC",
    "HIGHWAY_SPINE",
)

ORIENTATION_ANGLES = {
    "NORTH_SOUTH": 0.0,
    "EAST_WEST": math.pi * 0.5,
    "NW_SE": -math.pi * 0.25,
    "NE_SW": math.pi * 0.25,
    "RADIAL": 0.0,
}


def _clamp(val, min_v, max_v):
    return max(min_v, min(max_v, val))


def _pseudo_noise(t, seed=1):
    return (
        math.sin(t * 7.3 + seed * 1.7) * 0.55
        + math.sin(t * 15.1 - seed * 2.9) * 0.30
        + math.cos(t * 27.7 + seed * 4.3) * 0.15
    )


def _rotate_xy(x, y, angle):
    ca = math.cos(angle)
    sa = math.sin(angle)
    return x * ca - y * sa, x * sa + y * ca


def _lerp_pt(p1, p2, t):
    return [
        p1[0] + (p2[0] - p1[0]) * t,
        p1[1] + (p2[1] - p1[1]) * t,
        p1[2] + (p2[2] - p1[2]) * t,
    ]


def _resolve_region_center(region, bound):
    """地域名から代表中心座標 (x, y) を返す"""
    r = (region or "CENTER").upper().strip()
    d = bound * 0.52
    mapping = {
        "CENTER": (0.0, 0.0),
        "NORTH": (0.0, d),
        "SOUTH": (0.0, -d),
        "EAST": (d, 0.0),
        "WEST": (-d, 0.0),
        "NORTH_EAST": (d * 0.85, d * 0.85),
        "NORTHEAST": (d * 0.85, d * 0.85),
        "NORTH_WEST": (-d * 0.85, d * 0.85),
        "NORTHWEST": (-d * 0.85, d * 0.85),
        "SOUTH_EAST": (d * 0.85, -d * 0.85),
        "SOUTHEAST": (d * 0.85, -d * 0.85),
        "SOUTH_WEST": (-d * 0.85, -d * 0.85),
        "SOUTHWEST": (-d * 0.85, -d * 0.85),
        "PERIMETER": (0.0, 0.0),
    }
    return mapping.get(r, (0.0, 0.0))


def _resolve_region_span(region, bound, orientation="NORTH_SOUTH", is_mountain=True):
    """地域名からスプラインの開始点・終了点 (p_start, p_end) を返す"""
    r = (region or "NORTH").upper().strip()
    e = bound * 0.92
    m = bound * 0.56

    span_map = {
        "NORTH_SOUTH": ([0.0, e, 0.0], [0.0, -e, 0.0]),
        "NORTH_TO_SOUTH": ([0.0, e, 0.0], [0.0, -e, 0.0]),
        "SOUTH_TO_NORTH": ([0.0, -e, 0.0], [0.0, e, 0.0]),
        "EAST_WEST": ([-e, 0.0, 0.0], [e, 0.0, 0.0]),
        "WEST_TO_EAST": ([-e, 0.0, 0.0], [e, 0.0, 0.0]),
        "EAST_TO_WEST": ([e, 0.0, 0.0], [-e, 0.0, 0.0]),
        "SOUTH_TO_CENTER": ([0.0, -e, 0.0], [0.0, -bound * 0.08, 0.0]),
        "NORTH_TO_CENTER": ([0.0, e, 0.0], [0.0, bound * 0.08, 0.0]),
        "EAST_TO_CENTER": ([e, 0.0, 0.0], [bound * 0.08, 0.0, 0.0]),
        "WEST_TO_CENTER": ([-e, 0.0, 0.0], [-bound * 0.08, 0.0, 0.0]),
        "NW_TO_SE": ([-e * 0.85, e * 0.85, 0.0], [e * 0.85, -e * 0.85, 0.0]),
        "NE_TO_SW": ([e * 0.85, e * 0.85, 0.0], [-e * 0.85, -e * 0.85, 0.0]),
        "NORTH": ([-e * 0.82, m, 0.0], [e * 0.82, m * 0.92, 0.0]),
        "SOUTH": ([-e * 0.82, -m, 0.0], [e * 0.82, -m * 0.92, 0.0]),
        "EAST": ([m, -e * 0.82, 0.0], [m * 0.92, e * 0.82, 0.0]),
        "WEST": ([-m, -e * 0.82, 0.0], [-m * 0.92, e * 0.82, 0.0]),
        "NORTH_EAST": ([0.0, e * 0.85, 0.0], [e * 0.85, 0.0, 0.0]),
        "NORTH_WEST": ([-e * 0.85, 0.0, 0.0], [0.0, e * 0.85, 0.0]),
        "SOUTH_EAST": ([e * 0.85, 0.0, 0.0], [0.0, -e * 0.85, 0.0]),
        "SOUTH_WEST": ([0.0, -e * 0.85, 0.0], [-e * 0.85, 0.0, 0.0]),
    }
    if r in span_map:
        return span_map[r]

    # CENTER / UNKNOWN の場合は orientation に沿って横断させる
    ang = ORIENTATION_ANGLES.get((orientation or "NORTH_SOUTH").upper(), 0.0)
    if is_mountain:
        ang += math.pi * 0.5
    sx, sy = _rotate_xy(0.0, e * 0.82, ang)
    ex, ey = _rotate_xy(0.0, -e * 0.82, ang)
    return [sx, sy, 0.0], [ex, ey, 0.0]


def _build_winding_feature_spline(
    p_start,
    p_end,
    bound,
    num_pts=8,
    meander_amp=0.14,
    height_scale=1.0,
    width_scale=1.0,
    seed=1,
    taper_ends=True,
    start_tilt=None,
    end_tilt=-0.80,
):
    """
    2点間に有機的に蛇行するスプライン制御点リスト（custom_radius / custom_tilt 付き）を生成する。
    端点は必ず tilt=-0.80 へ滑らかに減衰させ（start_tilt指定時は分岐点の高さに一致）、
    内部 tilt は [-0.30, +0.60] の緩やかな勾配に制限して垂直崖を防止する。
    """
    dx = p_end[0] - p_start[0]
    dy = p_end[1] - p_start[1]
    length = math.hypot(dx, dy)
    if length < 1e-3:
        return []

    nx = -dy / length
    ny = dx / length
    pts = []

    for i in range(num_pts):
        t = i / float(num_pts - 1)
        bx = p_start[0] + dx * t
        by = p_start[1] + dy * t

        # 端点は固定に近くし、中間部で自然に蛇行させる（分岐始点 t=0 も厳密に一致）
        envelope = math.sin(math.pi * t)
        wave = (
            math.sin(math.pi * t * 1.5 + seed * 0.9) * 0.6
            + _pseudo_noise(t, seed=seed) * 0.5
        )
        start_lock = t if start_tilt is not None else 1.0
        offset = length * meander_amp * (0.25 + 0.75 * envelope) * wave * min(1.0, start_lock * 2.5)
        px = _clamp(bx + nx * offset, -bound, bound)
        py = _clamp(by + ny * offset, -bound, bound)

        if taper_ends:
            width_profile = 0.75 + 0.40 * (math.sin(math.pi * t) ** 0.65)
        else:
            width_profile = 0.85 + 0.20 * math.sin(math.pi * t)

        local_var = 1.0 + _pseudo_noise(t * 1.5, seed=seed + 11) * 0.12
        radius_attr = _clamp(width_scale * width_profile * local_var, 0.65, 1.75)

        interior_tilt = _clamp((height_scale - 1.0) * 0.45 + _pseudo_noise(t * 1.5, seed=seed + 11) * 0.16, -0.30, 0.60)
        if start_tilt is not None:
            if t <= 0.30:
                u = t / 0.30
                s = u * u * (3.0 - 2.0 * u)
                tilt_attr = start_tilt * (1.0 - s) + interior_tilt * s
            elif t >= 0.65:
                u = (t - 0.65) / 0.35
                s = u * u * (3.0 - 2.0 * u)
                tilt_attr = interior_tilt * (1.0 - s) + end_tilt * s
            else:
                tilt_attr = interior_tilt
        elif taper_ends:
            env_h = math.sin(math.pi * t) ** 0.75
            tilt_attr = end_tilt + (interior_tilt - end_tilt) * env_h
        else:
            edge_fade = min(1.0, min(t, 1.0 - t) / 0.20)
            s = edge_fade * edge_fade * (3.0 - 2.0 * edge_fade)
            tilt_attr = end_tilt + (interior_tilt - end_tilt) * s

        pts.append({
            "co": [px, py, 0.0],
            "radius": radius_attr,
            "tilt": _clamp(tilt_attr, -0.80, 0.60),
        })

    return pts


def _build_ring_feature_spline(
    center,
    ring_radius,
    bound,
    num_pts=12,
    height_scale=1.0,
    width_scale=1.0,
    seed=7,
    arc_fraction=0.82,
    start_angle=0.25,
):
    """盆地外縁やカルデラ外輪山向けの馬蹄形・環状スプラインを生成する。"""
    cx, cy = center
    pts = []
    total_ang = 2.0 * math.pi * arc_fraction
    for i in range(num_pts):
        t = i / float(num_pts - 1)
        th = start_angle + total_ang * t
        r_jitter = 1.0 + _pseudo_noise(t * 2.0, seed=seed) * 0.16
        r = ring_radius * r_jitter
        px = _clamp(cx + math.cos(th) * r, -bound, bound)
        py = _clamp(cy + math.sin(th) * r, -bound, bound)

        profile = 0.75 + 0.35 * (math.sin(math.pi * t) ** 0.6)
        local_var = 1.0 + _pseudo_noise(t * 3.0, seed=seed + 5) * 0.14
        radius_attr = _clamp(width_scale * profile * local_var, 0.65, 1.75)

        interior_tilt = _clamp((height_scale - 1.0) * 0.45 + _pseudo_noise(t * 3.0, seed=seed + 5) * 0.16, -0.30, 0.60)
        env_h = math.sin(math.pi * t) ** 0.70
        tilt_attr = -0.80 + (interior_tilt + 0.80) * env_h

        pts.append({
            "co": [px, py, 0.0],
            "radius": radius_attr,
            "tilt": _clamp(tilt_attr, -0.80, 0.60),
        })
    return pts


def _default_zones_for_archetype(archetype, orientation):
    """zones が省略された場合に archetype から標準的な構成を補完する。"""
    arch = (archetype or "BASIN_CITY").upper()
    if arch == "BASIN_CITY":
        return [
            {"type": "CITY", "region": "CENTER", "scale": 1.1},
            {"type": "MOUNTAIN_RANGE", "region": "PERIMETER", "height_scale": 1.35, "width_scale": 1.15},
            {"type": "VALLEY", "region": "SOUTH_TO_CENTER", "depth_scale": 1.1, "width_scale": 0.85},
        ]
    if arch == "CANYON_HIGHWAY":
        span = "EAST_WEST" if orientation == "EAST_WEST" else "NORTH_SOUTH"
        return [
            {"type": "VALLEY", "region": span, "depth_scale": 1.6, "width_scale": 1.1},
            {"type": "MOUNTAIN_RANGE", "region": "EAST" if span == "NORTH_SOUTH" else "NORTH", "height_scale": 1.2, "width_scale": 1.0},
            {"type": "MOUNTAIN_RANGE", "region": "WEST" if span == "NORTH_SOUTH" else "SOUTH", "height_scale": 1.15, "width_scale": 1.0},
        ]
    if arch == "ALPINE_VALLEY":
        return [
            {"type": "MOUNTAIN_RANGE", "region": "NORTH", "height_scale": 1.7, "width_scale": 1.25},
            {"type": "MOUNTAIN_RANGE", "region": "WEST", "height_scale": 1.4, "width_scale": 1.1},
            {"type": "VALLEY", "region": "NW_TO_SE", "depth_scale": 1.35, "width_scale": 0.9},
        ]
    if arch == "VOLCANIC_CALDERA":
        return [
            {"type": "MOUNTAIN_RANGE", "region": "PERIMETER", "height_scale": 1.65, "width_scale": 1.2},
            {"type": "VALLEY", "region": "CENTER", "depth_scale": 1.4, "width_scale": 1.3},
        ]
    if arch == "COASTAL_RIDGE":
        return [
            {"type": "CITY", "region": "WEST", "scale": 1.0},
            {"type": "MOUNTAIN_RANGE", "region": "EAST", "height_scale": 1.45, "width_scale": 1.15},
        ]
    if arch == "PLATEAU_MESA":
        return [
            {"type": "MOUNTAIN_RANGE", "region": "NORTH_EAST", "height_scale": 1.3, "width_scale": 1.4},
            {"type": "VALLEY", "region": "SOUTH_WEST", "depth_scale": 1.4, "width_scale": 1.0},
        ]
    # PLAINS_METROPOLIS
    return [
        {"type": "CITY", "region": "CENTER", "scale": 1.35},
    ]


def _smooth_catmull_rom(points, max_seg_len=60.0, bound=17600.0):
    """折れ線を滑らかな曲線座標配列に変換する。"""
    if len(points) < 2:
        return [[_clamp(p[0], -bound, bound), _clamp(p[1], -bound, bound), p[2]] for p in points]
    if len(points) == 2:
        p1, p2 = points[0], points[1]
        dist = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        n = max(2, int(math.ceil(dist / max_seg_len)))
        return [
            [
                _clamp(p1[0] + (p2[0] - p1[0]) * i / n, -bound, bound),
                _clamp(p1[1] + (p2[1] - p1[1]) * i / n, -bound, bound),
                0.0,
            ]
            for i in range(n + 1)
        ]

    p_start = [2 * points[0][0] - points[1][0], 2 * points[0][1] - points[1][1], points[0][2]]
    p_end = [2 * points[-1][0] - points[-2][0], 2 * points[-1][1] - points[-2][1], points[-1][2]]
    ext = [p_start] + points + [p_end]

    smoothed = []
    for i in range(len(points) - 1):
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        chord = math.hypot(p2[0] - p1[0], p2[1] - p1[1])
        n_sub = max(3, int(math.ceil(chord / max_seg_len)))
        for s in range(n_sub):
            t = s / float(n_sub)
            t2 = t * t
            t3 = t2 * t
            f0 = -0.5 * t3 + t2 - 0.5 * t
            f1 = 1.5 * t3 - 2.5 * t2 + 1.0
            f2 = -1.5 * t3 + 2.0 * t2 + 0.5 * t
            f3 = 0.5 * t3 - 0.5 * t2
            x = p0[0] * f0 + p1[0] * f1 + p2[0] * f2 + p3[0] * f3
            y = p0[1] * f0 + p1[1] * f1 + p2[1] * f2 + p3[1] * f3
            smoothed.append([_clamp(x, -bound, bound), _clamp(y, -bound, bound), 0.0])
    smoothed.append([_clamp(points[-1][0], -bound, bound), _clamp(points[-1][1], -bound, bound), 0.0])
    return smoothed


def smooth_and_resample_road(
    pts,
    spacing=15.0,
    chaikin_iters=2,
    max_turn_deg=12.0,
    min_dist=5.0,
    is_cyclic=False,
    clamp_limit=18000.0,
):
    """
    道路制御点列全体に対して単一パイプラインで平滑化を行う:
      1. 40m 間隔のアンカー抽出（重複頂点マージおよび鋭角V字スパイク除去を含む）
      2. Chaikin コーナーカッティング 2回
      3. ラプラシアン中点緩和（両端固定）で隣接セグメント折れ角をすべて <= 12° に収める
      4. 15m 間隔（spacing）の均一リサンプリング
    """
    if not pts or len(pts) < 2:
        return pts

    def _pt_xyz(p):
        return [
            _clamp(float(p[0]), -clamp_limit, clamp_limit),
            _clamp(float(p[1]), -clamp_limit, clamp_limit),
            float(p[2]) if len(p) >= 3 else 0.0,
        ]

    # 1. 重複頂点 (< min_dist) のマージ
    def _dedup(seq, min_d):
        if not seq:
            return []
        out = [_pt_xyz(seq[0])]
        for p in seq[1:]:
            q = _pt_xyz(p)
            if math.hypot(q[0] - out[-1][0], q[1] - out[-1][1]) >= min_d:
                out.append(q)
        if len(out) == 1 and len(seq) >= 2:
            out.append(_pt_xyz(seq[-1]))
        elif not is_cyclic and len(seq) >= 2:
            end_p = _pt_xyz(seq[-1])
            if math.hypot(end_p[0] - out[-1][0], end_p[1] - out[-1][1]) < min_d and len(out) >= 2:
                out[-1] = end_p
            elif math.hypot(end_p[0] - out[-1][0], end_p[1] - out[-1][1]) >= 1e-3:
                out.append(end_p)
        return out

    cleaned = _dedup(pts, min_dist)
    if len(cleaned) < 2:
        return cleaned

    # 鋭角V字折り返しの事前除去
    for _ in range(3):
        if len(cleaned) < 3:
            break
        filtered = [cleaned[0]]
        for i in range(1, len(cleaned) - 1):
            p_prev = filtered[-1]
            p_curr = cleaned[i]
            p_next = cleaned[i + 1]
            ux, uy = p_curr[0] - p_prev[0], p_curr[1] - p_prev[1]
            vx, vy = p_next[0] - p_curr[0], p_next[1] - p_curr[1]
            lu, lv = math.hypot(ux, uy), math.hypot(vx, vy)
            if lu < 1e-3 or lv < 1e-3:
                continue
            cos_t = (ux * vx + uy * vy) / (lu * lv)
            if cos_t < -0.15:
                filtered.append([
                    0.5 * (p_prev[0] + p_next[0]),
                    0.5 * (p_prev[1] + p_next[1]),
                    0.5 * (p_prev[2] + p_next[2]),
                ])
            else:
                filtered.append(p_curr)
        filtered.append(cleaned[-1])
        cleaned = _dedup(filtered, min_dist)

    def _resample_by_step(seq, step_len, cyclic=False):
        if len(seq) < 2:
            return seq
        work = list(seq) + ([seq[0]] if cyclic else [])
        cum = [0.0]
        for i in range(1, len(work)):
            d = math.hypot(work[i][0] - work[i - 1][0], work[i][1] - work[i - 1][1])
            cum.append(cum[-1] + d)
        total = cum[-1]
        if total < step_len:
            return list(seq)
        n_steps = max(2, int(round(total / step_len)))
        actual_step = total / float(n_steps)
        res = []
        seg_idx = 0
        count = n_steps if cyclic else n_steps + 1
        for k in range(count):
            target_s = min(total, k * actual_step)
            while seg_idx < len(cum) - 2 and cum[seg_idx + 1] < target_s:
                seg_idx += 1
            s0, s1 = cum[seg_idx], cum[seg_idx + 1]
            t = (target_s - s0) / max(1e-6, s1 - s0) if s1 > s0 else 0.0
            a, b = work[seg_idx], work[seg_idx + 1]
            res.append([
                _clamp(a[0] + (b[0] - a[0]) * t, -clamp_limit, clamp_limit),
                _clamp(a[1] + (b[1] - a[1]) * t, -clamp_limit, clamp_limit),
                a[2] + (b[2] - a[2]) * t,
            ])
        return res

    # ① 40m 間隔のアンカー抽出
    total_len = sum(
        math.hypot(cleaned[i][0] - cleaned[i - 1][0], cleaned[i][1] - cleaned[i - 1][1])
        for i in range(1, len(cleaned))
    )
    anchor_step = 40.0 if total_len >= 100.0 else max(15.0, total_len * 0.35)
    chaikin_pts = _resample_by_step(cleaned, anchor_step, cyclic=is_cyclic)

    # ② Chaikin コーナーカッティング 2回
    for _ in range(max(1, int(chaikin_iters))):
        if len(chaikin_pts) < 2:
            break
        n_c = len(chaikin_pts)
        next_pts = []
        if is_cyclic:
            for i in range(n_c):
                p0 = chaikin_pts[i]
                p1 = chaikin_pts[(i + 1) % n_c]
                q = [0.75 * p0[0] + 0.25 * p1[0], 0.75 * p0[1] + 0.25 * p1[1], 0.75 * p0[2] + 0.25 * p1[2]]
                r = [0.25 * p0[0] + 0.75 * p1[0], 0.25 * p0[1] + 0.75 * p1[1], 0.25 * p0[2] + 0.75 * p1[2]]
                next_pts.append(q)
                next_pts.append(r)
        else:
            next_pts.append(list(chaikin_pts[0]))
            for i in range(n_c - 1):
                p0 = chaikin_pts[i]
                p1 = chaikin_pts[i + 1]
                q = [0.75 * p0[0] + 0.25 * p1[0], 0.75 * p0[1] + 0.25 * p1[1], 0.75 * p0[2] + 0.25 * p1[2]]
                r = [0.25 * p0[0] + 0.75 * p1[0], 0.25 * p0[1] + 0.75 * p1[1], 0.25 * p0[2] + 0.75 * p1[2]]
                next_pts.append(q)
                next_pts.append(r)
            next_pts.append(list(chaikin_pts[-1]))
        chaikin_pts = next_pts

    # ③ ラプラシアン中点緩和（両端固定）で隣接セグメント折れ角を <= 12° に収める
    cos_limit = math.cos(math.radians(max_turn_deg))
    relaxed = _dedup(chaikin_pts, min_dist * 0.5)
    for _ in range(36):
        n_r = len(relaxed)
        if n_r < 3:
            break
        bad_indices = set()
        idx_range = range(n_r) if is_cyclic else range(1, n_r - 1)
        for i in idx_range:
            p_prev = relaxed[(i - 1) % n_r]
            p_curr = relaxed[i]
            p_next = relaxed[(i + 1) % n_r]
            ux, uy = p_curr[0] - p_prev[0], p_curr[1] - p_prev[1]
            vx, vy = p_next[0] - p_curr[0], p_next[1] - p_curr[1]
            lu, lv = math.hypot(ux, uy), math.hypot(vx, vy)
            if lu < 1e-4 or lv < 1e-4:
                continue
            cos_a = (ux * vx + uy * vy) / (lu * lv)
            if cos_a < cos_limit:
                for nb in range(i - 2, i + 3):
                    if is_cyclic:
                        bad_indices.add(nb % n_r)
                    elif 1 <= nb < n_r - 1:
                        bad_indices.add(nb)
        if not bad_indices:
            break
        updated = [list(p) for p in relaxed]
        for i in bad_indices:
            p_prev = relaxed[(i - 1) % n_r]
            p_curr = relaxed[i]
            p_next = relaxed[(i + 1) % n_r]
            updated[i][0] = _clamp(0.35 * p_prev[0] + 0.30 * p_curr[0] + 0.35 * p_next[0], -clamp_limit, clamp_limit)
            updated[i][1] = _clamp(0.35 * p_prev[1] + 0.30 * p_curr[1] + 0.35 * p_next[1], -clamp_limit, clamp_limit)
            updated[i][2] = 0.35 * p_prev[2] + 0.30 * p_curr[2] + 0.35 * p_next[2]
        relaxed = updated

    # ④ 15m 均一リサンプリング + 最終折れ角チェック (<= 12°)
    resampled = _resample_by_step(relaxed, spacing, cyclic=is_cyclic)
    resampled = _dedup(resampled, min_dist)
    for _ in range(24):
        n_r = len(resampled)
        if n_r < 3:
            break
        bad_indices = set()
        idx_range = range(n_r) if is_cyclic else range(1, n_r - 1)
        for i in idx_range:
            p_prev = resampled[(i - 1) % n_r]
            p_curr = resampled[i]
            p_next = resampled[(i + 1) % n_r]
            ux, uy = p_curr[0] - p_prev[0], p_curr[1] - p_prev[1]
            vx, vy = p_next[0] - p_curr[0], p_next[1] - p_curr[1]
            lu, lv = math.hypot(ux, uy), math.hypot(vx, vy)
            if lu < 1e-4 or lv < 1e-4:
                continue
            cos_a = (ux * vx + uy * vy) / (lu * lv)
            if cos_a < cos_limit:
                for nb in range(i - 2, i + 3):
                    if is_cyclic:
                        bad_indices.add(nb % n_r)
                    elif 1 <= nb < n_r - 1:
                        bad_indices.add(nb)
        if not bad_indices:
            break
        updated = [list(p) for p in resampled]
        for i in bad_indices:
            p_prev = resampled[(i - 1) % n_r]
            p_curr = resampled[i]
            p_next = resampled[(i + 1) % n_r]
            updated[i][0] = _clamp(0.35 * p_prev[0] + 0.30 * p_curr[0] + 0.35 * p_next[0], -clamp_limit, clamp_limit)
            updated[i][1] = _clamp(0.35 * p_prev[1] + 0.30 * p_curr[1] + 0.35 * p_next[1], -clamp_limit, clamp_limit)
            updated[i][2] = 0.35 * p_prev[2] + 0.30 * p_curr[2] + 0.35 * p_next[2]
        resampled = _dedup(updated, min_dist)

    return resampled


def _build_road_network(topology, orientation, has_city, city_center, city_scale, bound, scale_f, rng):
    """
    ProceduralCityGenerator.generate_road_network() と最も美しく連携できる
    「都市中心を緩やかに貫通する1〜2本の開いた幹線スプライン（4〜5点の自然なS字カーブ）」を生成する。
    都市外の峠道・海岸道路などは extra_roads として分離し、ProceduralCityGenerator を通さず独立追加する。
    """
    city_seed_roads = []
    extra_roads = []
    extra_metadata = []

    cx, cy = city_center[0], city_center[1]
    topo = (topology or "RING_AND_SPOKE").upper().strip()
    ang = ORIENTATION_ANGLES.get((orientation or "NORTH_SOUTH").upper(), 0.0)
    span_half = min(bound * 0.92, 16000.0 * (scale_f / 2.0))

    def make_s_curve(axis_angle, amp_ratio=0.05, center_x=cx, center_y=cy, num_pts=5):
        pts = []
        for i in range(num_pts):
            t = i / float(num_pts - 1)
            s = (t - 0.5) * 2.0 * span_half
            # 中心点 (t=0.5) は必ず (center_x, center_y) 付近を通過し、両側へ緩やかにS字蛇行
            lat = math.sin((t - 0.5) * math.pi * 2.0) * span_half * amp_ratio
            rx, ry = _rotate_xy(s, lat, axis_angle)
            pts.append([
                _clamp(center_x + rx, -bound, bound),
                _clamp(center_y + ry, -bound, bound),
                0.0,
            ])
        return pts

    if has_city:
        # ProceduralCityGenerator に渡す開いた幹線スプライン（4〜5点の自然なS字カーブ）
        main_ang = ang + math.pi * 0.5 if topo == "CROSS_VALLEY" else ang
        city_seed_roads.append(make_s_curve(main_ang, amp_ratio=0.045, num_pts=5))

        if topo in ("RING_AND_SPOKE", "GRID_ORGANIC", "CROSS_VALLEY"):
            city_seed_roads.append(make_s_curve(main_ang + math.pi * 0.5, amp_ratio=0.04, num_pts=5))

        # 都市外の峠道・海岸道路が指定されている場合は extra_roads に独立追加
        if topo in ("MOUNTAIN_PASS", "COASTAL_CORRIDOR"):
            pass_pts = make_s_curve(ang, amp_ratio=0.12, center_x=cx * 0.4, center_y=cy * 0.4, num_pts=7)
            extra_roads.append(_smooth_catmull_rom(pass_pts, max_seg_len=80.0, bound=bound))
            extra_metadata.append({"is_main": True, "type": topo})
    else:
        # 都市なし（純粋な自然地形）: ProceduralCityGenerator を通さず、地形を縫う独立幹線道路のみ生成
        amp = 0.14 if topo in ("MOUNTAIN_PASS", "COASTAL_CORRIDOR") else 0.07
        raw = make_s_curve(ang, amp_ratio=amp, center_x=0.0, center_y=0.0, num_pts=7)
        extra_roads.append(_smooth_catmull_rom(raw, max_seg_len=80.0, bound=bound))
        extra_metadata.append({"is_main": True, "type": topo})

    return city_seed_roads, extra_roads, extra_metadata


def is_blueprint_format(raw_data):
    """LLM出力が新ブループリント形式か旧生座標形式かを判定する。"""
    if not isinstance(raw_data, dict):
        return False
    blueprint_keys = {"archetype", "zones", "relief_level", "ridge_sharpness", "road_topology"}
    return any(k in raw_data for k in blueprint_keys)


def _convert_legacy_splines(spline_list):
    """旧形式 [[x,y,z], ...] を制御点辞書形式 [{"co":..., "radius":1.0, "tilt":0.0}, ...] へ変換。"""
    converted = []
    for pts in spline_list or []:
        if not isinstance(pts, (list, tuple)) or len(pts) < 2:
            continue
        item = []
        for p in pts:
            if isinstance(p, dict) and "co" in p:
                item.append(p)
            elif isinstance(p, (list, tuple)) and len(p) >= 2:
                z = float(p[2]) if len(p) >= 3 else 0.0
                item.append({"co": [float(p[0]), float(p[1]), z], "radius": 1.0, "tilt": 0.0})
        if len(item) >= 2:
            converted.append(item)
    return converted


def _compile_legacy(raw_data, preset, terrain_scale, prompt):
    """旧来の生座標JSONが返された場合の後方互換コンパイラ。"""
    is_40km = (terrain_scale == "40KM")
    default_size = 40000.0 if is_40km else 20000.0
    size_x = float(raw_data.get("terrain_size_x", default_size))
    size_y = float(raw_data.get("terrain_size_y", size_x))
    scale_f = size_x / 20000.0

    raw_height = raw_data.get("terrain_height")
    if raw_height is not None:
        terrain_height = float(raw_height)
    elif preset == "FLAT":
        terrain_height = 5.0
    elif preset == "MOUNTAINS":
        terrain_height = 350.0 * scale_f
    else:
        terrain_height = 90.0 * scale_f

    roads = raw_data.get("roads", []) or []
    p_lower = (prompt or "").lower()
    has_city = bool(roads) or any(k in p_lower for k in ("街", "都市", "city", "town"))
    city_center = [size_x * 0.2, 0.0, 0.0]
    if roads and roads[0]:
        xs = [p[0] for s in roads for p in s if len(p) >= 2]
        ys = [p[1] for s in roads for p in s if len(p) >= 2]
        if xs and ys:
            city_center = [sum(xs) / len(xs), sum(ys) / len(ys), 0.0]

    road_meta = [{"is_main": True, "type": "LEGACY_ROAD"} for _ in roads]
    city_scale = 1.0
    archetype = "LEGACY"
    road_topology = "LEGACY"
    active_seed = 2026
    noise_offset = (0.0, 0.0, 0.0)

    city_grade_radius = (2600.0 * _clamp(city_scale, 0.7, 1.8)) if has_city else 0.0
    city_style = detect_city_style(prompt=prompt, archetype=archetype, seed=active_seed)
    has_tunnels = (
        bool(raw_data.get("mountains"))
        or bool(raw_data.get("has_tunnels", False))
        or (str(road_topology).upper() == "TUNNEL_HIGHWAY")
        or (str(archetype).upper() == "RIDGE_DIVIDE")
        or any(k in (prompt or "").lower() for k in ("トンネル", "地下", "貫通", "tunnel", "underground"))
    )

    return {
        "seed": active_seed,
        "city_style": city_style,
        "has_tunnels": has_tunnels,
        "prompt": prompt,
        "noise_offset": noise_offset,
        "city_grade_radius": city_grade_radius,
        "terrain_size_x": size_x,
        "terrain_size_y": size_y,
        "terrain_height": terrain_height,
        "noise_scale": 0.00022 / scale_f,
        "ridge_sharpness": 0.5,
        "mountain_height": 420.0 * scale_f,
        "mountain_radius": 1400.0 * scale_f,
        "valley_depth": 380.0 * scale_f,
        "valley_radius": 1500.0 * scale_f,
        "water_level": raw_data.get("water_level"),
        "has_city": has_city,
        "city_center": city_center,
        "city_scale": 1.0,
        "mountains": _convert_legacy_splines(raw_data.get("mountains", [])),
        "valleys": _convert_legacy_splines(raw_data.get("valleys", [])),
        "roads": roads,
        "road_metadata": road_meta,
        "archetype": "LEGACY",
        "road_topology": "LEGACY",
    }


def compile_blueprint(raw_data, preset="AUTO", terrain_scale="40KM", prompt="", seed=None):
    """
    ブループリントJSON（または旧形式JSON）を、スプライン制御点群と
    Geometry Nodes 用パラメータ辞書へコンパイルする。
    """
    active_seed = int(seed) if (seed is not None and int(seed) > 0) else (int(time.time() * 1000) % 1000000 or 1)
    if not is_blueprint_format(raw_data):
        legacy_res = _compile_legacy(raw_data or {}, preset, terrain_scale, prompt)
        legacy_res["seed"] = active_seed
        legacy_res["noise_offset"] = (float(active_seed % 997) * 3.1, float(active_seed % 991) * 2.7, 0.0)
        legacy_res["city_grade_radius"] = 2800.0 if legacy_res.get("has_city") else 0.0
        legacy_res["has_tunnels"] = (
            bool(legacy_res.get("mountains"))
            or any(
                k in (prompt or "").lower() for k in ("トンネル", "地下", "貫通", "tunnel", "underground")
            )
        )
        return legacy_res

    is_40km = (terrain_scale == "40KM")
    size_x = 40000.0 if is_40km else 20000.0
    size_y = size_x
    scale_f = size_x / 20000.0
    bound = (size_x * 0.5) * 0.88

    archetype = str(raw_data.get("archetype", "BASIN_CITY")).upper()
    orientation = str(raw_data.get("orientation", "NORTH_SOUTH")).upper()
    road_topology = str(raw_data.get("road_topology", "RING_AND_SPOKE")).upper()

    p_raw = prompt or ""
    p_low = p_raw.lower()
    full_city_keywords = (
        "すべて街", "全部街", "全域が街", "全域都市", "一面ビル", "全面都市",
    )
    explicit_mt_request = any(k in p_low for k in ("山", "岳", "嶺", "峰", "mountain", "ridge", "alps", "peak", "カルデラ", "火山"))
    explicit_vl_request = any(k in p_low for k in ("谷", "渓谷", "川", "河", "valley", "canyon", "river", "gorge"))
    is_full_map_city = any(k in p_low for k in full_city_keywords)
    if any(k in p_low for k in ("東西", "東と西", "east and west", "east-west", "west to east")):
        orientation = "EAST_WEST"
    elif any(k in p_low for k in ("南北", "北と南", "north and south", "north-south")):
        orientation = "NORTH_SOUTH"

    # 1. 起伏・ディテールパラメータ（AIの設計仕様をそのまま反映）
    relief = float(raw_data.get("relief_level", 1.0 if is_full_map_city else 3.0))
    if is_full_map_city and not explicit_mt_request:
        relief = 1.0
    relief = _clamp(relief, 1.0, 5.0)
    ridge_sharpness = _clamp(float(raw_data.get("ridge_sharpness", 0.55)), 0.0, 1.0)
    noise_factor = _clamp(float(raw_data.get("noise_scale_factor", 1.0)), 0.25, 4.0)
    water_level = raw_data.get("water_level")
    if water_level is not None:
        try:
            water_level = float(water_level)
        except (TypeError, ValueError):
            water_level = None

    # relief_level 1..5 -> 40km/20kmスケールに見合う圧倒的な高低差を確保
    if is_40km:
        relief_heights = [15.0, 200.0, 320.0, 480.0, 650.0]
        mountain_height = 900.0 + (relief - 1.0) * 175.0   # 900m 〜 1,600m
        valley_depth = 600.0 + (relief - 1.0) * 100.0      # 600m 〜 1,000m
    else:
        relief_heights = [10.0, 140.0, 220.0, 330.0, 450.0]
        mountain_height = 600.0 + (relief - 1.0) * 125.0   # 600m 〜 1,100m
        valley_depth = 400.0 + (relief - 1.0) * 75.0       # 400m 〜 700m
    idx_f = relief - 1.0
    i0 = min(3, int(idx_f))
    frac = idx_f - i0
    terrain_height = relief_heights[i0] * (1.0 - frac) + relief_heights[i0 + 1] * frac
    if is_full_map_city and not explicit_mt_request:
        terrain_height = 5.0

    # ユーザー明示プリセットがある場合のみ範囲を尊重して調和させる
    if preset == "FLAT":
        terrain_height = min(terrain_height, 25.0)
    elif preset == "HILLS":
        terrain_height = _clamp(terrain_height, 200.0 if is_40km else 140.0, 360.0 if is_40km else 260.0)
    elif preset == "MOUNTAINS":
        terrain_height = max(terrain_height, 420.0 if is_40km else 300.0)

    # 40km時 3,500m / 3,300m 規模の広い裾野を確保し「細いミミズ状」を防ぐ
    mountain_radius = 1750.0 * scale_f
    valley_radius = 1650.0 * scale_f
    base_noise = 0.00024 if is_40km else 0.00042
    noise_scale = _clamp(
        base_noise * noise_factor,
        0.00015 if is_40km else 0.00025,
        0.00035 if is_40km else 0.00065,
    )

    # 2. ゾーン解釈と空間生成
    zones = raw_data.get("zones")
    if not isinstance(zones, list) or not zones:
        zones = _default_zones_for_archetype(archetype, orientation)

    rng = random.Random(active_seed)
    seed_offset = rng.randint(1, 50000)
    noise_offset = (
        rng.uniform(-4000.0, 4000.0),
        rng.uniform(-4000.0, 4000.0),
        rng.uniform(-400.0, 400.0),
    )
    mountains = []
    valleys = []
    has_city = False
    city_center = [0.0, 0.0, 0.0]
    city_scale = 1.0
    city_zones = []
    city_bound = bound * 0.78

    p_low_city = (prompt or "").lower()
    wants_city_in_prompt = (not p_low_city.strip()) or any(
        k in p_low_city for k in (
            "街", "都市", "町", "村", "ビル", "建物", "住宅", "市街", "都心", "集落", "基地",
            "city", "town", "village", "urban", "metropolis", "building", "settlement", "downtown",
        )
    )

    for z_idx, zone in enumerate(zones):
        if not isinstance(zone, dict):
            continue
        z_type = str(zone.get("type", "")).upper().strip()
        region = str(zone.get("region", "CENTER")).upper().strip()

        if z_type in ("CITY", "TOWN", "METROPOLIS", "SETTLEMENT") and wants_city_in_prompt:
            has_city = True
            raw_sc = float(zone.get("scale", 8.0 if is_full_map_city else 1.0))
            if is_full_map_city:
                sc = 8.0
            else:
                sc = _clamp(raw_sc, 0.7, 1.45)
            if region in ("EAST_WEST", "EAST_TO_WEST", "WEST_TO_EAST"):
                for r_sub, cx_sub in (("WEST", -bound * 0.55), ("EAST", bound * 0.55)):
                    cz_pt = [_clamp(cx_sub, -city_bound, city_bound), 0.0, 0.0]
                    city_zones.append({"center": cz_pt, "scale": sc, "region": r_sub})
                city_center = list(city_zones[0]["center"])
            elif region in ("NORTH_SOUTH", "NORTH_TO_SOUTH", "SOUTH_TO_NORTH"):
                for r_sub, cy_sub in (("NORTH", bound * 0.55), ("SOUTH", -bound * 0.55)):
                    cz_pt = [0.0, _clamp(cy_sub, -city_bound, city_bound), 0.0]
                    city_zones.append({"center": cz_pt, "scale": sc, "region": r_sub})
                city_center = list(city_zones[0]["center"])
            else:
                cx, cy = _resolve_region_center(region, bound)
                cz_pt = [_clamp(cx, -city_bound, city_bound), _clamp(cy, -city_bound, city_bound), 0.0]
                city_zones.append({"center": cz_pt, "scale": sc, "region": region})
                city_center = list(cz_pt)
            city_scale = max(city_scale, sc)

    # プロンプトで「東西に街」「東と西」が指定されているのに単一都市しか無い場合は東西2拠点に拡張
    if any(k in p_low for k in ("東西に街", "東西に都市", "東と西", "東西の街", "east and west")) and len(city_zones) <= 1 and not is_full_map_city:
        has_city = True
        sc_ew = max(1.1, city_scale)
        city_zones = [
            {"center": [-bound * 0.55, 0.0, 0.0], "scale": sc_ew, "region": "WEST"},
            {"center": [bound * 0.55, 0.0, 0.0], "scale": sc_ew, "region": "EAST"},
        ]
        city_center = [0.0, 0.0, 0.0]
        orientation = "EAST_WEST"

    if is_full_map_city:
        has_city = True
        city_scale = 8.0
        city_center = [0.0, 0.0, 0.0]
        if not city_zones:
            city_zones = [{"center": [0.0, 0.0, 0.0], "scale": 8.0, "region": "CENTER"}]
        else:
            for cz in city_zones:
                cz["scale"] = 8.0

    for z_idx, zone in enumerate(zones):
        if not isinstance(zone, dict):
            continue
        z_type = str(zone.get("type", "")).upper().strip()
        region = str(zone.get("region", "CENTER")).upper().strip()
        if z_type in ("CITY", "TOWN", "METROPOLIS", "SETTLEMENT"):
            continue
        if is_full_map_city and not explicit_mt_request and z_type in ("MOUNTAIN_RANGE", "MOUNTAIN", "RIDGE", "VOLCANO"):
            continue
        if is_full_map_city and not explicit_vl_request and z_type in ("VALLEY", "CANYON", "RIVER_VALLEY", "GORGE", "CRATER"):
            continue
        if False:
            pass

        elif z_type in ("MOUNTAIN_RANGE", "MOUNTAIN", "RIDGE", "VOLCANO"):
            h_scale = _clamp(float(zone.get("height_scale", 1.0)), 0.4, 2.5)
            w_scale = _clamp(float(zone.get("width_scale", 1.0)), 0.65, 2.5)

            if region in ("PERIMETER", "RING", "SURROUNDING"):
                ring_r = bound * 0.72
                mt_pts = _build_ring_feature_spline(
                    (city_center[0] * 0.3, city_center[1] * 0.3),
                    ring_r,
                    bound,
                    num_pts=14,
                    height_scale=h_scale,
                    width_scale=w_scale,
                    seed=seed_offset + 10 + z_idx * 7,
                )
                mountains.append(mt_pts)

                # 外周リングからも 3〜4 本の支脈を外側に向かって Y/T字分岐（X字交差禁止）
                num_spurs = rng.randint(3, 4)
                for sp_i in range(num_spurs):
                    pt_idx = max(1, min(len(mt_pts) - 2, int((0.15 + 0.70 * sp_i / max(1, num_spurs - 1)) * (len(mt_pts) - 1))))
                    root_pt = mt_pts[pt_idx]
                    rx, ry = root_pt["co"][0], root_pt["co"][1]
                    root_tilt = root_pt["tilt"]
                    out_ang = math.atan2(ry - city_center[1] * 0.3, rx - city_center[0] * 0.3) + rng.uniform(-0.35, 0.35)
                    branch_len = rng.uniform(2200.0, 3600.0) * scale_f
                    bx = _clamp(rx + math.cos(out_ang) * branch_len, -bound, bound)
                    by = _clamp(ry + math.sin(out_ang) * branch_len, -bound, bound)
                    mountains.append(_build_winding_feature_spline(
                        [rx, ry, 0.0], [bx, by, 0.0], bound, num_pts=5, meander_amp=0.10,
                        height_scale=h_scale * rng.uniform(0.55, 0.80),
                        width_scale=max(0.75, w_scale * 0.80),
                        seed=seed_offset + 100 + sp_i * 19,
                        taper_ends=True, start_tilt=root_tilt, end_tilt=-0.80,
                    ))
            else:
                # 1. 主脈（1〜2本）
                p_start, p_end = _resolve_region_span(region, bound, orientation, is_mountain=True)
                mt_pts = _build_winding_feature_spline(
                    p_start,
                    p_end,
                    bound,
                    num_pts=8,
                    meander_amp=0.14,
                    height_scale=h_scale,
                    width_scale=w_scale,
                    seed=seed_offset + 20 + z_idx * 13,
                )
                mountains.append(mt_pts)

                dx = p_end[0] - p_start[0]
                dy = p_end[1] - p_start[1]
                seg_l = max(1.0, math.hypot(dx, dy))

                # 2. 平行な第2主脈（大規模時・交差しないよう外側へ十分離す）
                if w_scale >= 1.15 or h_scale >= 1.25:
                    nx, ny = -dy / seg_l, dx / seg_l
                    shift = 3400.0 * scale_f
                    mid_x = (p_start[0] + p_end[0]) * 0.5
                    mid_y = (p_start[1] + p_end[1]) * 0.5
                    if (mid_x + nx * shift) ** 2 + (mid_y + ny * shift) ** 2 < mid_x ** 2 + mid_y ** 2:
                        nx, ny = -nx, -ny
                    sub_s = [_clamp(p_start[0] * 0.78 + nx * shift, -bound, bound), _clamp(p_start[1] * 0.78 + ny * shift, -bound, bound), 0.0]
                    sub_e = [_clamp(p_end[0] * 0.78 + nx * shift, -bound, bound), _clamp(p_end[1] * 0.78 + ny * shift, -bound, bound), 0.0]
                    mountains.append(_build_winding_feature_spline(
                        sub_s, sub_e, bound, num_pts=6, meander_amp=0.11,
                        height_scale=h_scale * 0.80,
                        width_scale=max(0.85, w_scale * 0.85),
                        seed=seed_offset + 50 + z_idx * 17,
                    ))

                # 3. 主脈を突き抜けず、制御点から外側片側へ 35°〜65° で Y/T字分岐する支脈（3〜5本）
                num_spurs = rng.randint(3, 5)
                for sp_i in range(num_spurs):
                    pt_idx = max(1, min(len(mt_pts) - 2, int((0.16 + 0.68 * sp_i / max(1, num_spurs - 1)) * (len(mt_pts) - 1))))
                    root_pt = mt_pts[pt_idx]
                    rx, ry = root_pt["co"][0], root_pt["co"][1]
                    root_tilt = root_pt["tilt"]
                    prev_pt = mt_pts[pt_idx - 1]["co"]
                    next_pt = mt_pts[pt_idx + 1]["co"]
                    local_ang = math.atan2(next_pt[1] - prev_pt[1], next_pt[0] - prev_pt[0])
                    side_sign = 1.0 if (sp_i % 2 == 0) else -1.0
                    branch_ang = local_ang + side_sign * rng.uniform(0.61, 1.13)  # 35°〜65°
                    branch_len = rng.uniform(2600.0, 4400.0) * scale_f
                    bx = _clamp(rx + math.cos(branch_ang) * branch_len, -bound, bound)
                    by = _clamp(ry + math.sin(branch_ang) * branch_len, -bound, bound)
                    # 都市中心へ突っ込む向きなら反対側へ分岐
                    if has_city and math.hypot(bx - city_center[0], by - city_center[1]) < 3000.0 * scale_f:
                        branch_ang = local_ang - side_sign * rng.uniform(0.61, 1.13)
                        bx = _clamp(rx + math.cos(branch_ang) * branch_len, -bound, bound)
                        by = _clamp(ry + math.sin(branch_ang) * branch_len, -bound, bound)
                    mountains.append(_build_winding_feature_spline(
                        [rx, ry, 0.0], [bx, by, 0.0], bound,
                        num_pts=5, meander_amp=0.10,
                        height_scale=h_scale * rng.uniform(0.55, 0.78),
                        width_scale=max(0.65, w_scale * rng.uniform(0.65, 0.85)),
                        seed=seed_offset + 140 + z_idx * 31 + sp_i * 11,
                        taper_ends=True, start_tilt=root_tilt, end_tilt=-0.80,
                    ))

            # 4. 周辺の独立峰・丘陵群（既存山脈と交差しない位置に 3〜5本）
            num_peaks = rng.randint(3, 5)
            for pk_i in range(num_peaks):
                ang_pk = rng.uniform(0.0, 2.0 * math.pi)
                dist_pk = rng.uniform(bound * 0.45, bound * 0.84)
                px_c = city_center[0] + math.cos(ang_pk) * dist_pk
                py_c = city_center[1] + math.sin(ang_pk) * dist_pk
                if has_city and math.hypot(px_c - city_center[0], py_c - city_center[1]) < 3600.0 * scale_f:
                    continue
                too_close = any(
                    math.hypot(px_c - mp["co"][0], py_c - mp["co"][1]) < 2600.0 * scale_f
                    for mt_list in mountains for mp in mt_list
                )
                if too_close:
                    continue
                pk_dir = ang_pk + rng.uniform(-0.7, 0.7)
                pk_len = rng.uniform(1600.0, 2800.0) * scale_f
                s_pk = [_clamp(px_c - math.cos(pk_dir) * pk_len * 0.5, -bound, bound), _clamp(py_c - math.sin(pk_dir) * pk_len * 0.5, -bound, bound), 0.0]
                e_pk = [_clamp(px_c + math.cos(pk_dir) * pk_len * 0.5, -bound, bound), _clamp(py_c + math.sin(pk_dir) * pk_len * 0.5, -bound, bound), 0.0]
                mountains.append(_build_winding_feature_spline(
                    s_pk, e_pk, bound, num_pts=4, meander_amp=0.08,
                    height_scale=h_scale * rng.uniform(0.45, 0.70),
                    width_scale=rng.uniform(0.65, 0.90),
                    seed=seed_offset + 260 + z_idx * 43 + pk_i * 17,
                    taper_ends=True,
                ))

        elif z_type in ("VALLEY", "CANYON", "RIVER_VALLEY", "GORGE", "CRATER"):
            d_scale = _clamp(float(zone.get("depth_scale", 1.0)), 0.3, 2.5)
            w_scale = _clamp(float(zone.get("width_scale", 1.0)), 0.3, 2.5)
            p_start, p_end = _resolve_region_span(region, bound, orientation, is_mountain=False)
            vl_pts = _build_winding_feature_spline(
                p_start,
                p_end,
                bound,
                num_pts=9,
                meander_amp=0.16,
                height_scale=d_scale,
                width_scale=w_scale,
                seed=seed_offset + 70 + z_idx * 11,
                taper_ends=False,
            )
            valleys.append(vl_pts)

            # 本流の制御点から外側片側へ 35°〜65° で Y/T字合流する支流（2〜4本、X字交差禁止）
            num_tribs = rng.randint(2, 4)
            for tr_i in range(num_tribs):
                pt_idx = max(1, min(len(vl_pts) - 2, int((0.18 + 0.64 * tr_i / max(1, num_tribs - 1)) * (len(vl_pts) - 1))))
                root_pt = vl_pts[pt_idx]
                jx, jy = root_pt["co"][0], root_pt["co"][1]
                root_tilt = root_pt["tilt"]
                prev_pt = vl_pts[pt_idx - 1]["co"]
                next_pt = vl_pts[pt_idx + 1]["co"]
                local_ang = math.atan2(next_pt[1] - prev_pt[1], next_pt[0] - prev_pt[0])
                side_v = 1.0 if (tr_i % 2 == 0) else -1.0
                t_ang = local_ang + side_v * rng.uniform(0.61, 1.13)
                t_len = rng.uniform(3200.0, 5600.0) * scale_f
                tx = _clamp(jx + math.cos(t_ang) * t_len, -bound, bound)
                ty = _clamp(jy + math.sin(t_ang) * t_len, -bound, bound)
                valleys.append(_build_winding_feature_spline(
                    [jx, jy, 0.0], [tx, ty, 0.0], bound,
                    num_pts=6, meander_amp=0.12,
                    height_scale=d_scale * rng.uniform(0.55, 0.80),
                    width_scale=max(0.60, w_scale * rng.uniform(0.60, 0.85)),
                    seed=seed_offset + 340 + z_idx * 29 + tr_i * 13,
                    taper_ends=True, start_tilt=root_tilt, end_tilt=-0.80,
                ))

    # 2.5 非都市エリアが単調な平面にならないよう、既存山脈と交差しない丘陵群（80m〜250m級）と補助谷を追加
    if preset != "FLAT" and not is_full_map_city:
        num_hills = rng.randint(4, 6)
        for h_i in range(num_hills):
            ang_h = (2.0 * math.pi * h_i / num_hills) + rng.uniform(-0.35, 0.35)
            dist_h = rng.uniform(bound * 0.45, bound * 0.85)
            hx = city_center[0] + math.cos(ang_h) * dist_h
            hy = city_center[1] + math.sin(ang_h) * dist_h
            if has_city and math.hypot(hx - city_center[0], hy - city_center[1]) < 3600.0 * scale_f:
                continue
            too_close = any(
                math.hypot(hx - mp["co"][0], hy - mp["co"][1]) < 2400.0 * scale_f
                for mt_list in mountains for mp in mt_list
            )
            if too_close:
                continue
            h_dir = ang_h + rng.uniform(-0.8, 0.8)
            h_len = rng.uniform(2200.0, 3800.0) * scale_f
            hs = [_clamp(hx - math.cos(h_dir) * h_len * 0.5, -bound, bound), _clamp(hy - math.sin(h_dir) * h_len * 0.5, -bound, bound), 0.0]
            he = [_clamp(hx + math.cos(h_dir) * h_len * 0.5, -bound, bound), _clamp(hy + math.sin(h_dir) * h_len * 0.5, -bound, bound), 0.0]
            mountains.append(_build_winding_feature_spline(
                hs, he, bound, num_pts=5, meander_amp=0.10,
                height_scale=rng.uniform(0.25, 0.42),
                width_scale=rng.uniform(0.85, 1.25),
                seed=seed_offset + 500 + h_i * 23,
                taper_ends=True,
            ))

        if not valleys:
            # 谷が1本も無い場合も地形の陰影を作るため本流＋Y字支流を生成
            v_ang = rng.uniform(0.0, math.pi)
            vs = [_clamp(-math.cos(v_ang) * bound * 0.85, -bound, bound), _clamp(-math.sin(v_ang) * bound * 0.85, -bound, bound), 0.0]
            ve = [_clamp(math.cos(v_ang) * bound * 0.85, -bound, bound), _clamp(math.sin(v_ang) * bound * 0.85, -bound, bound), 0.0]
            main_v = _build_winding_feature_spline(
                vs, ve, bound, num_pts=8, meander_amp=0.16,
                height_scale=0.75, width_scale=0.85,
                seed=seed_offset + 610, taper_ends=False,
            )
            valleys.append(main_v)
            for tr_i in range(2):
                pt_idx = 2 if tr_i == 0 else 5
                root_pt = main_v[pt_idx]
                jx, jy = root_pt["co"][0], root_pt["co"][1]
                side_v = 1.0 if tr_i == 0 else -1.0
                t_ang = v_ang + side_v * rng.uniform(0.65, 1.0)
                tx = _clamp(jx + math.cos(t_ang) * bound * 0.50, -bound, bound)
                ty = _clamp(jy + math.sin(t_ang) * bound * 0.50, -bound, bound)
                valleys.append(_build_winding_feature_spline(
                    [jx, jy, 0.0], [tx, ty, 0.0], bound,
                    num_pts=5, meander_amp=0.12,
                    height_scale=0.55, width_scale=0.68,
                    seed=seed_offset + 630 + tr_i * 17,
                    taper_ends=True, start_tilt=root_pt["tilt"], end_tilt=-0.80,
                ))

    if is_full_map_city and not explicit_mt_request:
        mountains = []
    if is_full_map_city and not explicit_vl_request:
        valleys = []

    # 3. 道路網の構築（ProceduralCityGenerator 用シード幹線 + 都市外独立道路）
    city_seed_roads, extra_roads, extra_metadata = _build_road_network(
        topology=road_topology,
        orientation=orientation,
        has_city=has_city,
        city_center=city_center,
        city_scale=city_scale,
        bound=bound,
        scale_f=scale_f,
        rng=rng,
    )

    city_grade_radius = (bound * 1.15 if is_full_map_city else (3800.0 * _clamp(city_scale, 0.7, 1.5))) if has_city else 0.0
    city_style = detect_city_style(prompt=prompt, archetype=archetype, seed=active_seed)

    # 水系（海・海岸線・河川）のコンパイル
    ocean_cfg = None
    rivers = []
    zones_list = raw_data.get("zones", []) if isinstance(raw_data, dict) else []
    p_low = (prompt or "").lower()

    for idx_z, z in enumerate(zones_list):
        if not isinstance(z, dict):
            continue
        z_type = str(z.get("type", "")).upper().strip()
        z_reg = str(z.get("region", "SOUTH")).upper().strip()

        if z_type in ("COASTLINE", "OCEAN", "SEA"):
            if water_level is None:
                water_level = 0.0
            valid_ocean_regs = ("NORTH", "SOUTH", "EAST", "WEST", "NORTH_EAST", "NORTH_WEST", "SOUTH_EAST", "SOUTH_WEST", "ISLAND", "PERIMETER")
            ocean_cfg = {
                "region": z_reg if z_reg in valid_ocean_regs else ("ISLAND" if any(k in p_low for k in ("島", "孤島", "離島", "island", "atoll")) else "SOUTH"),
                "depth": float(z.get("depth_scale", 1.0)) * 75.0,
                "shore_offset": float(z.get("shore_offset", 0.32)),
            }
        elif z_type == "RIVER":
            p_s, p_e = _resolve_region_span(z_reg, bound, orientation=orientation, is_mountain=False)
            w_scale = _clamp(float(z.get("width_scale", 1.0)), 0.4, 3.0)
            d_scale = _clamp(float(z.get("depth_scale", 1.0)), 0.4, 3.0)
            r_pts = _build_winding_feature_spline(
                p_s,
                p_e,
                bound=bound,
                num_pts=14,
                meander_amp=0.18,
                height_scale=1.0,
                width_scale=w_scale,
                seed=active_seed + 300 + idx_z * 19,
                taper_ends=False,
                start_tilt=0.0,
                end_tilt=0.0,
            )
            rivers.append({
                "pts": r_pts,
                "width": 120.0 * w_scale,
                "depth": 18.0 * d_scale,
            })

    # プロンプトやアーキタイプに海/川/島が含まれる場合の自動補完
    is_island_prompt = any(k in p_low for k in ("島", "孤島", "離島", "island", "atoll", "archipelago"))
    if ocean_cfg is None and (
        str(archetype).upper() == "COASTAL_RIDGE"
        or water_level is not None
        or is_island_prompt
        or any(k in p_low for k in ("海", "海岸", "ocean", "sea", "coast", "beach", "bay"))
    ):
        if water_level is None:
            water_level = 0.0
        ocean_region = "ISLAND" if is_island_prompt else "SOUTH"
        if not is_island_prompt:
            if any(k in p_low for k in ("北の海", "北側が海")):
                ocean_region = "NORTH"
            elif any(k in p_low for k in ("東の海", "東側が海")):
                ocean_region = "EAST"
            elif any(k in p_low for k in ("西の海", "西側が海")):
                ocean_region = "WEST"
        ocean_cfg = {"region": ocean_region, "depth": 80.0, "shore_offset": 0.32}

    if not rivers and any(k in p_low for k in ("川", "河川", "大河", "渓流", "river", "stream")):
        p_s, p_e = _resolve_region_span("NORTH_TO_SOUTH", bound, orientation=orientation, is_mountain=False)
        r_pts = _build_winding_feature_spline(
            p_s, p_e, bound=bound, num_pts=14, meander_amp=0.18,
            seed=active_seed + 313, taper_ends=False, start_tilt=0.0, end_tilt=0.0,
        )
        rivers.append({"pts": r_pts, "width": 120.0, "depth": 18.0})
    has_tunnels = (
        bool(mountains)
        or bool(raw_data.get("has_tunnels", False))
        or (str(road_topology).upper() == "TUNNEL_HIGHWAY")
        or (str(archetype).upper() == "RIDGE_DIVIDE")
        or any(k in (prompt or "").lower() for k in ("トンネル", "地下", "貫通", "tunnel", "underground"))
    )

    print(
        f"[Blueprint Debug] archetype={archetype}, orientation={orientation}, "
        f"is_full_map_city={is_full_map_city}, city_zones={city_zones}, "
        f"num_mountains={len(mountains)}, num_valleys={len(valleys)}"
    )

    return {
        "seed": active_seed,
        "city_style": city_style,
        "has_tunnels": has_tunnels,
        "prompt": prompt,
        "noise_offset": noise_offset,
        "city_grade_radius": city_grade_radius,
        "terrain_size_x": size_x,
        "terrain_size_y": size_y,
        "terrain_height": terrain_height,
        "noise_scale": noise_scale,
        "ridge_sharpness": ridge_sharpness,
        "mountain_height": mountain_height,
        "mountain_radius": mountain_radius,
        "valley_depth": valley_depth,
        "valley_radius": valley_radius,
        "water_level": water_level,
        "ocean": ocean_cfg,
        "rivers": rivers,
        "has_city": has_city,
        "city_center": city_center,
        "city_scale": city_scale,
        "city_zones": city_zones,
        "is_full_map_city": is_full_map_city,
        "orientation": orientation,
        "mountains": mountains,
        "valleys": valleys,
        "roads": city_seed_roads,
        "extra_roads": extra_roads,
        "extra_road_metadata": extra_metadata,
        "road_metadata": [],
        "archetype": archetype,
        "road_topology": road_topology,
    }


def generate_city_lots(roads, road_metadata, city_center, city_scale=1.0, size_x=40000.0):
    """
    40km / 20km オープンワールドの俯瞰カメラからも街並み・ビル群として明確に視認できる
    スケール（高さ 30m〜180m、幅 25m〜60m、都市半径 2km〜5km）の建物ロットを生成する。
    """
    if not roads or not city_center:
        return []

    scale_f = size_x / 20000.0
    cx, cy = float(city_center[0]), float(city_center[1])
    city_radius = _clamp(2200.0 * (1.0 + (scale_f - 1.0) * 0.45) * city_scale, 2000.0, 5000.0)
    rng = random.Random(2026)

    # 道路セグメントの構築（衝突判定用）
    road_segments = []
    for idx, spline in enumerate(roads):
        if len(spline) < 2:
            continue
        meta = road_metadata[idx] if idx < len(road_metadata) else {}
        is_main = meta.get("is_main", False)
        is_cyclic = meta.get("cyclic", False)
        half_w = 14.0 if is_main else 8.0
        n_pts = len(spline)
        seg_count = n_pts if is_cyclic else n_pts - 1
        for j in range(seg_count):
            p1 = spline[j]
            p2 = spline[(j + 1) % n_pts]
            road_segments.append((p1[0], p1[1], p2[0], p2[1], half_w))

    def collides_with_road(lx, ly, bw, bd, angle):
        hw = bw * 0.5
        hh = bd * 0.5
        b_rad = math.hypot(hw, hh)
        for x1, y1, x2, y2, r_hw in road_segments:
            clearance = r_hw + 6.0
            dx, dy = x2 - x1, y2 - y1
            len_sq = dx * dx + dy * dy
            if len_sq < 1e-6:
                continue
            t = _clamp(((lx - x1) * dx + (ly - y1) * dy) / len_sq, 0.0, 1.0)
            px, py = x1 + t * dx, y1 + t * dy
            if (lx - px) ** 2 + (ly - py) ** 2 < (clearance + b_rad * 0.85) ** 2:
                return True
        return False

    lots = []
    for idx, spline in enumerate(roads):
        if len(spline) < 2:
            continue
        meta = road_metadata[idx] if idx < len(road_metadata) else {}
        is_main = meta.get("is_main", False)
        is_cyclic = meta.get("cyclic", False)
        road_half_w = 14.0 if is_main else 8.0
        step_dist = 85.0 if is_main else 70.0

        n_pts = len(spline)
        seg_count = n_pts if is_cyclic else n_pts - 1
        for j in range(seg_count):
            p1 = spline[j]
            p2 = spline[(j + 1) % n_pts]
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            seg_len = math.hypot(dx, dy)
            if seg_len < 30.0:
                continue

            dir_x, dir_y = dx / seg_len, dy / seg_len
            norm_x, norm_y = -dir_y, dir_x
            road_angle = math.atan2(dir_y, dir_x)
            num_steps = max(1, int(seg_len / step_dist))

            for s in range(num_steps):
                t = (s + 0.5) / num_steps
                mx = p1[0] + dir_x * (t * seg_len)
                my = p1[1] + dir_y * (t * seg_len)
                dist_c = math.hypot(mx - cx, my - cy)
                if dist_c > city_radius:
                    continue

                for side in (-1, 1):
                    density = max(0.30, 1.0 - (dist_c / city_radius) * 0.60)
                    if rng.random() > density:
                        continue

                    if dist_c < city_radius * 0.35:
                        # 都心・超高層エリア
                        bw = rng.uniform(35.0, 60.0)
                        bd = rng.uniform(30.0, 52.0)
                        bh = rng.uniform(95.0, 180.0)
                        b_type = "SKYSCRAPER"
                    elif dist_c < city_radius * 0.70:
                        # 中高層ビジネスエリア
                        bw = rng.uniform(30.0, 50.0)
                        bd = rng.uniform(26.0, 44.0)
                        bh = rng.uniform(50.0, 105.0)
                        b_type = "MIDRISE"
                    else:
                        # 外縁・低中層エリア
                        bw = rng.uniform(25.0, 42.0)
                        bd = rng.uniform(25.0, 38.0)
                        bh = rng.uniform(30.0, 58.0)
                        b_type = "LOWRISE"

                    offset_d = road_half_w + bd * 0.5 + rng.uniform(10.0, 18.0)
                    lx = mx + norm_x * (side * offset_d)
                    ly = my + norm_y * (side * offset_d)
                    ang = road_angle + rng.uniform(-0.05, 0.05)

                    b_rad = math.hypot(bw * 0.5, bd * 0.5)
                    if any((lx - eb["x"]) ** 2 + (ly - eb["y"]) ** 2 < (b_rad + eb["_r"] + 8.0) ** 2 for eb in lots):
                        continue
                    if collides_with_road(lx, ly, bw, bd, ang):
                        continue

                    lots.append({
                        "x": lx,
                        "y": ly,
                        "w": bw,
                        "h": bd,
                        "z_height": bh,
                        "angle": ang,
                        "type": b_type,
                        "_r": b_rad,
                    })

    return lots


def detect_city_style(prompt="", archetype="", seed=0):
    """プロンプトと地形アーキタイプから都市レイアウトスタイル (GRID/RADIAL/ORGANIC/LINEAR) を決定"""
    p_low = (prompt or "").lower()
    if any(k in p_low for k in ("細長", "街道", "谷沿", "川沿", "海岸", "linear", "corridor", "ribbon", "coastal", "river")):
        return "LINEAR"
    if any(k in p_low for k in ("格子", "碁盤", "マンハッタン", "ニューヨーク", "grid", "manhattan", "modern")):
        return "GRID"
    if any(k in p_low for k in ("放射", "環状", "城塞", "パリ", "radial", "ring", "hub", "citadel")):
        return "RADIAL"
    if any(k in p_low for k in ("有機", "迷宮", "中世", "自然", "村", "organic", "medieval", "village")):
        return "ORGANIC"

    arch = (archetype or "").upper()
    if arch in ("VALLEY_CORRIDOR", "COASTAL_BAY", "CANYON_PASS"):
        return "LINEAR"

    # 明確な指定がない場合はシード値に応じてスタイルを毎回変化させる
    styles = ("ORGANIC", "RADIAL", "GRID", "LINEAR")
    return styles[abs(int(seed)) % len(styles)]


def route_road_around_mountains(
    pts,
    mountains,
    mountain_radius,
    allow_mountain_pass=False,
    is_cyclic=False,
    clamp_limit=18000.0,
):
    """
    道路スプラインの各制御点を山脈スプライン (Mountains) との最短距離に基づき
    山麓の等高線ライン (Mountain Radius * 1.15) へ外側押し出し・平滑化し、
    山を突っ切らず山裾に沿って蛇行させる。
    """
    if not pts or len(pts) < 2 or not mountains or mountain_radius <= 0.0:
        return pts

    def _extract_mt_xyr(pt):
        if isinstance(pt, dict):
            co = pt.get("co", [0.0, 0.0, 0.0])
            return float(co[0]), float(co[1]), float(pt.get("radius", 1.0))
        return float(pt[0]), float(pt[1]), (float(pt[3]) if len(pt) >= 4 else 1.0)

    # 山脈セグメントを事前構築: (x1, y1, r1, x2, y2, r2)
    mt_segs = []
    for mt in mountains:
        if not mt or len(mt) < 2:
            continue
        for j in range(len(mt) - 1):
            x1, y1, ra = _extract_mt_xyr(mt[j])
            x2, y2, rb = _extract_mt_xyr(mt[j + 1])
            mt_segs.append((x1, y1, ra, x2, y2, rb))

    if not mt_segs:
        return pts

    def closest_mountain_info(px, py):
        best_d = 1e18
        best_nx, best_ny = 0.0, 1.0
        best_eff_r = float(mountain_radius)
        for x1, y1, ra, x2, y2, rb in mt_segs:
            dx = x2 - x1
            dy = y2 - y1
            len_sq = dx * dx + dy * dy
            if len_sq < 1e-6:
                t = 0.0
                cx_m, cy_m = x1, y1
            else:
                t = _clamp(((px - x1) * dx + (py - y1) * dy) / len_sq, 0.0, 1.0)
                cx_m = x1 + t * dx
                cy_m = y1 + t * dy
            vx = px - cx_m
            vy = py - cy_m
            d = math.hypot(vx, vy)
            if d < best_d:
                best_d = d
                r_scale = ra + (rb - ra) * t
                best_eff_r = float(mountain_radius) * max(0.35, r_scale)
                if d > 1e-4:
                    best_nx, best_ny = vx / d, vy / d
                else:
                    seg_l = max(1.0, math.sqrt(len_sq))
                    best_nx, best_ny = -dy / seg_l, dx / seg_l
        return best_d, best_nx, best_ny, best_eff_r

    routed = []
    n_pts = len(pts)
    prev_nx, prev_ny = None, None
    for idx, p in enumerate(pts):
        px, py = float(p[0]), float(p[1])
        pz = float(p[2]) if len(p) >= 3 else 0.0
        d, nx, ny, eff_r = closest_mountain_info(px, py)

        inner_r = eff_r * 1.10
        target_r = eff_r * 1.15

        if d < inner_r:
            if prev_nx is not None and (nx * prev_nx + ny * prev_ny) < 0.0:
                # 山脈の尾根を跨いだ際に法線が180度反転して90度クランクが生じるのを防ぎ、同じ側へ一貫して迂回させる
                nx, ny = -nx, -ny
                push = target_r + d
            else:
                push = target_r - d
            prev_nx, prev_ny = nx, ny

            if allow_mountain_pass:
                # 峠道が明示された場合は九十九折れの蛇行オフセットのみ加え、完全迂回はしない
                switchback = math.sin(idx * 0.45) * min(160.0, eff_r * 0.12)
                px = _clamp(px + nx * switchback, -clamp_limit, clamp_limit)
                py = _clamp(py + ny * switchback, -clamp_limit, clamp_limit)
            else:
                # 山の麓（Mountain Radius * 1.15 付近）へ滑らかに押し出す
                blend = _clamp((inner_r - d) / max(1.0, eff_r * 0.20), 0.25, 1.0)
                px = _clamp(px + nx * push * blend, -clamp_limit, clamp_limit)
                py = _clamp(py + ny * push * blend, -clamp_limit, clamp_limit)
        else:
            prev_nx, prev_ny = None, None

        routed.append([px, py, pz])

    # 単一パイプライン (40mアンカー -> Chaikin 2回 -> ラプラシアン緩和 <=12度 -> 15mリサンプリング)
    return smooth_and_resample_road(
        routed,
        spacing=15.0,
        chaikin_iters=2,
        max_turn_deg=12.0,
        min_dist=5.0,
        is_cyclic=is_cyclic,
        clamp_limit=clamp_limit,
    )
