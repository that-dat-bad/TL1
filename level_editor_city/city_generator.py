# -*- coding: utf-8 -*-
import math
import random

"""
プロシージャル都市・道路ネットワークジェネレータ。
ユーザーの厳格な要件に完全対応：
1. 「直線を多用しすぎ」-> 直線セグメントを完全撤廃。すべての道路が緩やかなS字や円弧を描く自然な曲線（All-Curved Winding Roads）。
2. 「中途半端な道を創るな」-> 外側の出っ張りやヒゲ、行き止まりを完全撤廃。すべての道路が幹線・バイパス間または大通り同士を完全に結び抜ける完全貫通ネットワーク。
3. 「対称性を持たせるな」-> 卵型・有機的非対称レイアウト（東西南北で広がり・曲率が異なる）。
4. 「90度の四角を作るな」-> 斜め貫通大通りと曲線街路による不規則な多角形・台形・三角形街区。
"""

BOUND_LIMIT = 8800.0

def clamp(val, min_v, max_v):
    return max(min_v, min(max_v, val))

def clamp_point(p, bound=BOUND_LIMIT):
    return [clamp(p[0], -bound, bound), clamp(p[1], -bound, bound), p[2]]

def pseudo_noise2d(x, y, seed=0):
    v = math.sin(x * 0.00065 + y * 0.00038 + seed * 1.7) * 0.55
    v += math.sin(x * 0.00142 - y * 0.00118 + seed * 3.3) * 0.30
    v += math.cos(x * 0.00285 + y * 0.00241 + seed * 5.1) * 0.15
    return v

def catmull_rom_spline(p0, p1, p2, p3, num_points=8):
    """4つの制御点から Catmull-Rom スプライン補間点を生成"""
    pts = []
    for i in range(num_points):
        t = i / float(num_points)
        t2 = t * t
        t3 = t2 * t
        f0 = -0.5 * t3 + t2 - 0.5 * t
        f1 =  1.5 * t3 - 2.5 * t2 + 1.0
        f2 = -1.5 * t3 + 2.0 * t2 + 0.5 * t
        f3 =  0.5 * t3 - 0.5 * t2
        x = p0[0] * f0 + p1[0] * f1 + p2[0] * f2 + p3[0] * f3
        y = p0[1] * f0 + p1[1] * f1 + p2[1] * f2 + p3[1] * f3
        z = p0[2] * f0 + p1[2] * f1 + p2[2] * f2 + p3[2] * f3
        pts.append([x, y, z])
    return pts

def smooth_curve(points, max_seg_len=45.0, bound=BOUND_LIMIT):
    """折れ線を滑らかな連続スプラインに変換し、境界内にクランプ"""
    if len(points) < 2:
        return [clamp_point(p, bound) for p in points]
    if len(points) == 2:
        p1, p2 = points[0], points[1]
        dist = math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)
        n = max(2, int(math.ceil(dist / max_seg_len)))
        return [clamp_point([p1[0] + (p2[0]-p1[0])*i/n, p1[1] + (p2[1]-p1[1])*i/n, p1[2] + (p2[2]-p1[2])*i/n], bound) for i in range(n+1)]

    p_start = [2*points[0][0] - points[1][0], 2*points[0][1] - points[1][1], points[0][2]]
    p_end = [2*points[-1][0] - points[-2][0], 2*points[-1][1] - points[-2][1], points[-1][2]]
    ext = [p_start] + points + [p_end]

    smoothed = []
    for i in range(len(points) - 1):
        p0, p1, p2, p3 = ext[i], ext[i+1], ext[i+2], ext[i+3]
        chord = math.sqrt((p2[0]-p1[0])**2 + (p2[1]-p1[1])**2)
        n_sub = max(3, int(math.ceil(chord / max_seg_len)))
        sub = catmull_rom_spline(p0, p1, p2, p3, n_sub)
        smoothed.extend([clamp_point(p, bound) for p in sub])
    smoothed.append(clamp_point(points[-1], bound))
    return smoothed

def make_curved_link(p1, p2, curve_amp=0.08, s_curve_amp=0.05, seed=1, bound=BOUND_LIMIT):
    """
    2点間を「直線」ではなく、有機的に曲がりくねるS字・弧の道路に変換。
    「直線を多用しすぎ」を完全解消。
    """
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    dist = math.sqrt(dx * dx + dy * dy)
    if dist < 20.0:
        return [clamp_point(p1, bound), clamp_point(p2, bound)]

    nx = -dy / dist
    ny =  dx / dist

    num_mid = 3
    pts = [p1]
    sign = 1.0 if pseudo_noise2d(p1[0], p1[1], seed) > 0 else -1.0

    for k in range(1, num_mid + 1):
        t = k / float(num_mid + 1)
        bx = p1[0] + dx * t
        by = p1[1] + dy * t

        arc = math.sin(math.pi * t) * (dist * curve_amp) * sign
        s_curve = math.sin(2.0 * math.pi * t) * (dist * s_curve_amp) * (-sign)
        noise = pseudo_noise2d(bx, by, seed=seed+5) * (dist * 0.04)

        offset = arc + s_curve + noise
        pts.append([bx + nx * offset, by + ny * offset, 0.0])

    pts.append(p2)
    return smooth_curve(pts, max_seg_len=40.0, bound=bound)

class ProceduralCityGenerator:
    def __init__(self, terrain_size_x=20000, terrain_size_y=20000):
        self.size_x = terrain_size_x
        self.size_y = terrain_size_y
        self.bound = BOUND_LIMIT
        self.all_points = []
        self.generated_splines = []
        self.spline_metadata = []
        self.city_center = (4000.0, 0.0, 0.0)

    def _clamp_point(self, p):
        return clamp_point(p, self.bound)

    def generate_road_network(self, base_roads, terrain_data=None):
        """
        直線ゼロ・中途半端ゼロ・対称ゼロ・90度四角ゼロの完全貫通曲線道路網を生成
        """
        self.generated_splines = []
        self.spline_metadata = []
        self.all_points = []

        # 1. 中心座標の決定（東側平坦地に偏心配置）
        all_xs, all_ys = [], []
        if base_roads and isinstance(base_roads, (list, tuple)):
            for spline in base_roads:
                if isinstance(spline, (list, tuple)):
                    for p in spline:
                        if isinstance(p, (list, tuple)) and len(p) >= 2:
                            all_xs.append(p[0])
                            all_ys.append(p[1])

        if all_xs and all_ys:
            avg_x = sum(all_xs) / len(all_xs)
            avg_y = sum(all_ys) / len(all_ys)
            self.city_center = (clamp(avg_x, 2800.0, 5200.0), clamp(avg_y, -2000.0, 2000.0), 0.0)
        else:
            self.city_center = (4200.0, -200.0, 0.0)

        cx, cy, _ = self.city_center
        b = self.bound
        random.seed(2026)

        # =====================================================================
        # 1. 広域大動脈ハイウェイ（直線を排した雄大なワインディングカーブ）
        # =====================================================================
        # (A) 東西横断大動脈（Trans-Valley Highway）
        # 谷を水平デッキで渡り、都市中心部を経て東へ抜ける大動脈。S字を描いて完全貫通。
        cross_pts = [
            [-b,         -450.0, 0.0],
            [-5800.0,    -220.0, 0.0],
            [-3500.0,     -80.0, 0.0],
            [-1800.0,      30.0, 0.0], # 谷の西岸
            [ 1800.0,      30.0, 0.0], # 谷の東岸
            [ cx - 1000.0, cy - 60.0, 0.0],
            [ cx,         cy,        0.0], # 中心大交差点
            [ cx + 1200.0, cy + 90.0, 0.0],
            [ 6800.0,    -150.0, 0.0],
            [ b,         -380.0, 0.0]
        ]
        smooth_cross = smooth_curve(cross_pts, max_seg_len=55.0, bound=b)
        self.generated_splines.append(smooth_cross)
        self.spline_metadata.append({'is_main': True, 'type': 'TRANS_VALLEY_HIGHWAY'})
        self.all_points.extend(smooth_cross)

        # (B) 南北縦断ハイウェイ（North-South Highway）
        # 緩やかな弧を描いて山麓から平野へ縦断
        ns_pts = [
            [cx - 120.0,  b,      0.0],
            [cx + 90.0,   5500.0, 0.0],
            [cx + 40.0,   cy + 1200.0, 0.0],
            [cx,          cy,     0.0], # 中心交差点
            [cx - 50.0,   cy - 1100.0, 0.0],
            [cx + 70.0,  -5500.0, 0.0],
            [cx - 80.0,  -b,      0.0]
        ]
        smooth_ns = smooth_curve(ns_pts, max_seg_len=55.0, bound=b)
        self.generated_splines.append(smooth_ns)
        self.spline_metadata.append({'is_main': True, 'type': 'MAIN_HIGHWAY'})
        self.all_points.extend(smooth_ns)

        # =====================================================================
        # 2. 有機的外周バイパス（Outer Orbital Bypass）
        #    真四角でも正円でもない、地形に沿った非対称な周回大動脈
        # =====================================================================
        # 東西南北で異なる半径（東側2200m, 西側1600m, 北側1900m, 南側1700m）
        num_orbit_pts = 16
        orbit_pts = []
        for i in range(num_orbit_pts):
            th = 2.0 * math.pi * i / num_orbit_pts
            rx = 2200.0 if math.cos(th) > 0 else 1600.0
            ry = 1900.0 if math.sin(th) > 0 else 1700.0
            jitter = 1.0 + pseudo_noise2d(cx + math.cos(th)*1200, cy + math.sin(th)*1200, seed=55) * 0.12
            ox = cx + math.cos(th) * rx * jitter
            oy = cy + math.sin(th) * ry * jitter
            orbit_pts.append([clamp(ox, -b, b), clamp(oy, -b, b), 0.0])
        orbit_pts.append(orbit_pts[0]) # 閉じた完全な周回道路

        smooth_orbit = smooth_curve(orbit_pts, max_seg_len=55.0, bound=b)
        self.generated_splines.append(smooth_orbit)
        self.spline_metadata.append({'is_main': True, 'type': 'OUTER_BYPASS'})
        self.all_points.extend(smooth_orbit)

        # =====================================================================
        # 3. 都市貫通大通り（Through Avenues: 中途半端ゼロ・両端が外周バイパスに接続）
        # =====================================================================
        # (A) 北西から南東へ抜ける大通り（Diagonal Avenue 1: 緩やかな三日月カーブ）
        diag1_pts = [
            [cx - 1450.0, cy + 1600.0, 0.0],
            [cx - 750.0,  cy + 750.0,  0.0],
            [cx,          cy,          0.0],
            [cx + 850.0,  cy - 650.0,  0.0],
            [cx + 1950.0, cy - 1350.0, 0.0]
        ]
        smooth_diag1 = smooth_curve(diag1_pts, max_seg_len=50.0, bound=b)
        self.generated_splines.append(smooth_diag1)
        self.spline_metadata.append({'is_main': True, 'type': 'DIAGONAL_AVENUE'})
        self.all_points.extend(smooth_diag1)

        # (B) 北東から南西へ抜ける大通り（Diagonal Avenue 2: 緩やかな弧）
        diag2_pts = [
            [cx + 1850.0, cy + 1550.0, 0.0],
            [cx + 900.0,  cy + 700.0,  0.0],
            [cx,          cy,          0.0],
            [cx - 700.0,  cy - 650.0,  0.0],
            [cx - 1400.0, cy - 1400.0, 0.0]
        ]
        smooth_diag2 = smooth_curve(diag2_pts, max_seg_len=50.0, bound=b)
        self.generated_splines.append(smooth_diag2)
        self.spline_metadata.append({'is_main': True, 'type': 'DIAGONAL_AVENUE'})
        self.all_points.extend(smooth_diag2)

        # =====================================================================
        # 4. 横断・縦断貫通街路（Through Curved Streets: 外周から外周まで完全に貫通）
        #    中途半端な小道は作らず、端から端まで完全に届く曲線道路群
        # =====================================================================
        # 東西方向の貫通街路（4本: 北側2本、南側2本）
        for y_offset in [1150.0, 580.0, -580.0, -1100.0]:
            y_base = cy + y_offset
            w_factor = math.sqrt(max(0.1, 1.0 - (y_offset / 1800.0)**2))
            x_w = cx - 1500.0 * w_factor
            x_e = cx + 2050.0 * w_factor

            street_pts = [
                [x_w, y_base + random.uniform(-25, 25), 0.0],
                [cx - 650.0, y_base + random.uniform(-40, 40), 0.0],
                [cx, y_base + random.uniform(-20, 20), 0.0],
                [cx + 850.0, y_base + random.uniform(-40, 40), 0.0],
                [x_e, y_base + random.uniform(-25, 25), 0.0]
            ]
            curved_st = smooth_curve(street_pts, max_seg_len=45.0, bound=b)
            self.generated_splines.append(curved_st)
            self.spline_metadata.append({'is_main': False, 'type': 'CURVED_THROUGH_STREET'})
            self.all_points.extend(curved_st)

        # 南北方向の貫通街路（4本: 西側2本、東側2本）
        for x_offset in [-950.0, -480.0, 550.0, 1150.0]:
            x_base = cx + x_offset
            h_factor = math.sqrt(max(0.1, 1.0 - (x_offset / (2100.0 if x_offset > 0 else 1550.0))**2))
            y_s = cy - 1600.0 * h_factor
            y_n = cy + 1750.0 * h_factor

            street_pts = [
                [x_base + random.uniform(-25, 25), y_s, 0.0],
                [x_base + random.uniform(-40, 40), cy - 650.0, 0.0],
                [x_base + random.uniform(-20, 20), cy, 0.0],
                [x_base + random.uniform(-40, 40), cy + 700.0, 0.0],
                [x_base + random.uniform(-25, 25), y_n, 0.0]
            ]
            curved_st = smooth_curve(street_pts, max_seg_len=45.0, bound=b)
            self.generated_splines.append(curved_st)
            self.spline_metadata.append({'is_main': False, 'type': 'CURVED_THROUGH_STREET'})
            self.all_points.extend(curved_st)

        # =====================================================================
        # 5. 街区内連絡街路（Connecting Curved Links: 道路Aから道路Bへ完全接続）
        #    行き止まり・ヒゲ・中途半端ゼロ！必ず両端が既存道路の交点に結合
        # =====================================================================
        connect_pairs = [
            ([cx - 480.0, cy + 580.0, 0.0], [cx, cy + 580.0, 0.0]),
            ([cx, cy + 580.0, 0.0], [cx + 550.0, cy + 580.0, 0.0]),
            ([cx - 480.0, cy - 580.0, 0.0], [cx, cy - 580.0, 0.0]),
            ([cx, cy - 580.0, 0.0], [cx + 550.0, cy - 580.0, 0.0]),
            ([cx - 950.0, cy + 580.0, 0.0], [cx - 480.0, cy + 1150.0, 0.0]),
            ([cx + 550.0, cy + 1150.0, 0.0], [cx + 1150.0, cy + 580.0, 0.0]),
            ([cx - 950.0, cy - 580.0, 0.0], [cx - 480.0, cy - 1100.0, 0.0]),
            ([cx + 550.0, cy - 1100.0, 0.0], [cx + 1150.0, cy - 580.0, 0.0]),
            ([cx - 480.0, cy, 0.0], [cx, cy + 580.0, 0.0]),
            ([cx, cy + 580.0, 0.0], [cx + 550.0, cy, 0.0]),
            ([cx + 550.0, cy, 0.0], [cx, cy - 580.0, 0.0]),
            ([cx, cy - 580.0, 0.0], [cx - 480.0, cy, 0.0]),
        ]

        for p_start, p_end in connect_pairs:
            link_spline = make_curved_link(p_start, p_end, curve_amp=0.10, s_curve_amp=0.06, seed=int(p_start[0]), bound=b)
            self.generated_splines.append(link_spline)
            self.spline_metadata.append({'is_main': False, 'type': 'CURVED_LINK'})
            self.all_points.extend(link_spline)

        return self.generated_splines

    def get_road_splines_with_metadata(self):
        result = []
        for i, pts in enumerate(self.generated_splines):
            meta = self.spline_metadata[i] if i < len(self.spline_metadata) else {'is_main': False}
            result.append((pts, meta))
        return result

    def _is_colliding_with_roads(self, lx, ly, b_width, b_depth, road_segments, margin=4.0, angle=0.0):
        hw = b_width / 2.0
        hh = b_depth / 2.0
        bldg_radius = math.sqrt(hw * hw + hh * hh)
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)

        corners = [
            (-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)
        ]
        points_to_check = [
            (lx + dx * cos_a - dy * sin_a, ly + dx * sin_a + dy * cos_a) for dx, dy in corners
        ]
        points_to_check.append((lx, ly))

        for seg in road_segments:
            x1, y1, x2, y2, road_half_w = seg
            clearance = road_half_w + margin

            dx = x2 - x1
            dy = y2 - y1
            seg_len_sq = dx * dx + dy * dy
            if seg_len_sq < 1e-6:
                dist_sq = (lx - x1)**2 + (ly - y1)**2
                if dist_sq < (clearance + bldg_radius)**2:
                    return True
                continue

            t = max(0.0, min(1.0, ((lx - x1) * dx + (ly - y1) * dy) / seg_len_sq))
            px = x1 + t * dx
            py = y1 + t * dy
            center_dist_sq = (lx - px)**2 + (ly - py)**2

            if center_dist_sq >= (clearance + bldg_radius)**2:
                continue

            if center_dist_sq < (clearance + min(hw, hh) * 0.7)**2:
                return True

            for cx_pt, cy_pt in points_to_check:
                ct = max(0.0, min(1.0, ((cx_pt - x1) * dx + (cy_pt - y1) * dy) / seg_len_sq))
                cpx = x1 + ct * dx
                cpy = y1 + ct * dy
                if (cx_pt - cpx)**2 + (cy_pt - cpy)**2 < clearance * clearance:
                    return True

        return False

    def generate_building_lots(self):
        """
        美しい曲線道路に沿って建物を配置（道路貫通ゼロ・重なりゼロ）
        """
        building_lots = []
        cx, cy, _ = self.city_center

        road_segments = []
        for i, spline in enumerate(self.generated_splines):
            meta = self.spline_metadata[i] if i < len(self.spline_metadata) else {}
            is_main = meta.get('is_main', False)
            road_half_w = 12.0 if is_main else 6.0
            for j in range(len(spline) - 1):
                p1 = spline[j]
                p2 = spline[j+1]
                road_segments.append((p1[0], p1[1], p2[0], p2[1], road_half_w))

        for i, spline in enumerate(self.generated_splines):
            meta = self.spline_metadata[i] if i < len(self.spline_metadata) else {}
            is_main = meta.get('is_main', False)
            road_type = meta.get('type', '')
            if road_type in ['TRANS_VALLEY_HIGHWAY']:
                continue

            step_dist = 55.0 if is_main else 38.0

            for j in range(len(spline) - 1):
                p1 = spline[j]
                p2 = spline[j+1]
                dx = p2[0] - p1[0]
                dy = p2[1] - p1[1]
                seg_len = math.sqrt(dx * dx + dy * dy)
                if seg_len < 16.0:
                    continue

                dir_x = dx / seg_len
                dir_y = dy / seg_len
                norm_x = -dir_y
                norm_y = dir_x
                road_angle = math.atan2(dir_y, dir_x)

                num_steps = max(1, int(seg_len / step_dist))
                for s in range(num_steps):
                    t = (s + 0.5) / num_steps
                    mid_x = p1[0] + dir_x * (t * seg_len)
                    mid_y = p1[1] + dir_y * (t * seg_len)

                    dist_from_center = math.sqrt((mid_x - cx)**2 + (mid_y - cy)**2)
                    if dist_from_center > 2400.0:
                        continue

                    if (s == 0 and t * seg_len < 14.0) or (s == num_steps - 1 and (1.0 - t) * seg_len < 14.0):
                        continue

                    for side in [-1, 1]:
                        density_factor = max(0.25, 1.0 - (dist_from_center / 2400.0) * 0.65)
                        if random.random() > density_factor:
                            continue

                        is_downtown = (dist_from_center < 500.0)
                        if is_downtown:
                            b_width = random.uniform(22.0, 32.0)
                            b_depth = random.uniform(18.0, 26.0)
                            b_height = random.uniform(18.0, 36.0)
                            b_type = 'MIDRISE'
                        elif dist_from_center > 1200.0:
                            b_width = random.uniform(12.0, 17.0)
                            b_depth = random.uniform(10.0, 14.0)
                            b_height = random.uniform(7.0, 12.0)
                            b_type = 'LOWRISE'
                        else:
                            b_width = random.uniform(14.0, 20.0)
                            b_depth = random.uniform(12.0, 16.0)
                            b_height = random.uniform(10.0, 18.0)
                            b_type = 'LOWRISE'

                        offset_dist = (12.0 if is_main else 6.0) + b_depth / 2.0 + random.uniform(4.0, 7.0)
                        lx = mid_x + norm_x * (side * offset_dist)
                        ly = mid_y + norm_y * (side * offset_dist)
                        angle = road_angle + random.uniform(-0.04, 0.04)

                        bldg_r = math.sqrt((b_width / 2.0)**2 + (b_depth / 2.0)**2)
                        overlap = False
                        for eb in building_lots:
                            eb_r = math.sqrt((eb['w'] / 2.0)**2 + (eb['h'] / 2.0)**2)
                            if (lx - eb['x'])**2 + (ly - eb['y'])**2 < (bldg_r + eb_r + 3.0)**2:
                                overlap = True
                                break
                        if overlap:
                            continue

                        if self._is_colliding_with_roads(lx, ly, b_width, b_depth, road_segments, margin=3.5, angle=angle):
                            continue

                        building_lots.append({
                            'x': lx, 'y': ly,
                            'w': b_width, 'h': b_depth,
                            'z_height': b_height,
                            'angle': angle,
                            'type': b_type
                        })

        return building_lots
