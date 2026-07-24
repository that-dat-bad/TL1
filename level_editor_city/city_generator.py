# -*- coding: utf-8 -*-
import math
import random
import mathutils

class RoadAgent:
    def __init__(self, position, direction, lifetime):
        self.pos = mathutils.Vector(position)
        self.dir = mathutils.Vector(direction).normalized()
        self.lifetime = lifetime
        self.spline = [self.pos.copy()]
        # パラメータ
        self.step_length = 10.0 # 1ステップの距離
        self.snap_radius = 15.0  # 既存道路へのスナップ判定距離
        self.branch_prob = 0.1   # 枝分かれする確率
        self.turn_prob = 0.2     # 曲がる確率
        self.turn_angle = math.radians(90) # 曲がる角度（グリッド状なら90度）
        self.wander_angle = math.radians(10) # わずかなうねりの許容範囲

class ProceduralCityGenerator:
    def __init__(self, terrain_size_x=200, terrain_size_y=200):
        self.size_x = terrain_size_x
        self.size_y = terrain_size_y
        self.kd_tree = None
        self.all_points = []
        self.agents = []
        self.generated_splines = []

    def _build_kdtree(self):
        size = len(self.all_points)
        self.kd_tree = mathutils.kdtree.KDTree(size)
        for i, p in enumerate(self.all_points):
            self.kd_tree.insert(p, i)
        self.kd_tree.balance()

    def generate_road_network(self, base_roads):
        """
        AIが生成した幹線道路 (base_roads) を起点にして、枝道を生成する
        base_roads: [[[x,y,z], ...], ...]
        """
        # 既存道路の点を登録（衝突判定用に2m間隔で密に補間する）
        for spline in base_roads:
            self.generated_splines.append(spline)
            for i in range(len(spline) - 1):
                p1 = mathutils.Vector(spline[i])
                p2 = mathutils.Vector(spline[i+1])
                dist = (p2 - p1).length
                steps = max(1, int(dist / 2.0))
                for step in range(steps):
                    t = step / steps
                    self.all_points.append(p1.lerp(p2, t))
            if spline:
                self.all_points.append(mathutils.Vector(spline[-1]))
        
        if not self.all_points:
            return base_roads

        self._build_kdtree()

        # 幹線道路からエージェント（枝道）を発生させる
        for spline in base_roads:
            if len(spline) < 2:
                continue
            
            # 各セグメント間でランダムにエージェントをスポーン
            for i in range(len(spline) - 1):
                p1 = mathutils.Vector(spline[i])
                p2 = mathutils.Vector(spline[i+1])
                
                # セグメントの長さ
                dist = (p2 - p1).length
                num_spawns = int(dist / 40.0) # 40m間隔くらいで発生判定
                
                forward = (p2 - p1).normalized()
                right = mathutils.Vector((-forward.y, forward.x, 0)) # 垂直方向
                
                for _ in range(num_spawns):
                    if random.random() < 0.6: # 60%の確率で枝道を出す
                        t = random.random()
                        spawn_pos = p1.lerp(p2, t)
                        # 右か左か
                        spawn_dir = right if random.random() < 0.5 else -right
                        
                        agent = RoadAgent(spawn_pos, spawn_dir, lifetime=random.randint(5, 15))
                        self.agents.append(agent)

        # エージェントの成長シミュレーション
        self._simulate_growth()

        return self.generated_splines

    def _simulate_growth(self):
        while self.agents:
            agent = self.agents.pop(0)
            
            while agent.lifetime > 0:
                # ゆらぎ（自然な曲がり）
                wander = random.uniform(-agent.wander_angle, agent.wander_angle)
                rot = mathutils.Matrix.Rotation(wander, 3, 'Z')
                agent.dir = (rot @ agent.dir).normalized()
                
                # グリッド的な直角ターンの判定
                if random.random() < agent.turn_prob:
                    turn = agent.turn_angle if random.random() < 0.5 else -agent.turn_angle
                    rot = mathutils.Matrix.Rotation(turn, 3, 'Z')
                    agent.dir = (rot @ agent.dir).normalized()

                # 前進
                new_pos = agent.pos + agent.dir * agent.step_length
                
                # 境界チェック
                if abs(new_pos.x) > self.size_x / 2.0 or abs(new_pos.y) > self.size_y / 2.0:
                    break

                # 衝突・交差点チェック（KDTreeで最寄りの既存道路ポイントを探す）
                co, index, dist = self.kd_tree.find(new_pos)
                if co and dist < agent.snap_radius:
                    # スナップして終了（交差点形成）
                    agent.spline.append(co.copy())
                    break
                else:
                    # 中間点もKDTree用に登録する（2m間隔）
                    p1 = agent.pos
                    p2 = new_pos
                    dist = (p2 - p1).length
                    steps = max(1, int(dist / 2.0))
                    for step in range(steps):
                        t = step / steps
                        self.all_points.append(p1.lerp(p2, t))
                    self.all_points.append(p2.copy())
                    
                    agent.spline.append(new_pos.copy())
                    agent.pos = new_pos
                    
                    self._build_kdtree()

                    # 枝分かれ判定
                    if random.random() < agent.branch_prob:
                        branch_dir = mathutils.Vector((-agent.dir.y, agent.dir.x, 0))
                        if random.random() < 0.5:
                            branch_dir = -branch_dir
                        
                        new_agent = RoadAgent(new_pos, branch_dir, lifetime=random.randint(3, 8))
                        self.agents.append(new_agent)

                agent.lifetime -= 1

            if len(agent.spline) >= 2:
                # mathutils.Vector をリストに変換
                list_spline = [[p.x, p.y, p.z] for p in agent.spline]
                self.generated_splines.append(list_spline)

    def generate_building_lots(self):
        """
        BSP（二分空間分割）を用いて、道路の空きスペースに建物の敷地（ロット）を生成する
        """
        class Block:
            def __init__(self, x, y, width, height):
                self.x, self.y = x, y
                self.width, self.height = width, height
                self.left, self.right = None, None

        def bsp_subdivide(block, depth, max_depth):
            if depth >= max_depth:
                return [block]
                
            split_vert = random.random() < 0.5
            if block.width > block.height * 1.5:
                split_vert = True
            elif block.height > block.width * 1.5:
                split_vert = False
                
            if split_vert:
                if block.width < 30.0: return [block]
                split_ratio = random.uniform(0.4, 0.6)
                w1 = block.width * split_ratio
                block.left = Block(block.x, block.y, w1, block.height)
                block.right = Block(block.x + w1, block.y, block.width - w1, block.height)
            else:
                if block.height < 30.0: return [block]
                split_ratio = random.uniform(0.4, 0.6)
                h1 = block.height * split_ratio
                block.left = Block(block.x, block.y, block.width, h1)
                block.right = Block(block.x, block.y + h1, block.width, block.height - h1)
                
            return bsp_subdivide(block.left, depth+1, max_depth) + bsp_subdivide(block.right, depth+1, max_depth)

        # 全体を覆う初期ブロック
        root = Block(-self.size_x/2, -self.size_y/2, self.size_x, self.size_y)
        blocks = bsp_subdivide(root, 0, 6)
        
        # --- Step 3: ボロノイ分割・発展シミュレーション（中心地の決定） ---
        num_centers = random.randint(1, 3)
        city_centers = []
        if self.all_points:
            for _ in range(num_centers):
                # 道路上のランダムな点を中心地（駅・商業施設）とする
                city_centers.append(random.choice(self.all_points))
        else:
            city_centers.append(mathutils.Vector((0, 0, 0)))
        # ------------------------------------------------------------------
        
        building_lots = []
        for b in blocks:
            # ブロックをさらに小さなロット（敷地）に分割
            lot_size = random.uniform(10.0, 20.0)
            cols = max(1, int(b.width / lot_size))
            rows = max(1, int(b.height / lot_size))
            
            lot_w = b.width / cols
            lot_h = b.height / rows
            
            for c in range(cols):
                for r in range(rows):
                    lot_x = b.x + c * lot_w + lot_w / 2
                    lot_y = b.y + r * lot_h + lot_h / 2
                    
                    # 道路からの距離チェック（KDTreeで衝突判定）
                    lot_vec = mathutils.Vector((lot_x, lot_y, 0))
                    co, index, dist = self.kd_tree.find(lot_vec)
                    
                    # 道路から一定以上離れていれば建築許可
                    if dist > 8.0:
                        
                        # --- ボロノイ的距離判定と地価計算 ---
                        min_center_dist = float('inf')
                        for center in city_centers:
                            d = (lot_vec - center).length
                            if d < min_center_dist:
                                min_center_dist = d
                                
                        # 影響範囲はマップサイズの1/3程度
                        max_influence = max(self.size_x, self.size_y) / 3.0
                        # 0.0 ~ 1.0 の地価スコア（中心に近いほど高い）
                        land_value = 1.0 - min(min_center_dist / max_influence, 1.0)
                        land_value += random.uniform(-0.1, 0.2) # ランダムなノイズ
                        # -----------------------------------
                        
                        bw = lot_w * random.uniform(0.6, 0.9)
                        bh = lot_h * random.uniform(0.6, 0.9)
                        
                        if land_value > 0.8:
                            # 都心：高層ビル
                            height = random.uniform(40.0, 100.0)
                        elif land_value > 0.4:
                            # 商業・中層住宅地
                            height = random.uniform(15.0, 40.0)
                        elif land_value > 0.1:
                            # 郊外：低層住宅地
                            height = random.uniform(5.0, 15.0)
                        else:
                            # 境界付近や遠方：一定確率で公園（建築しない）か極低層
                            if random.random() < 0.5:
                                continue # 空き地にする
                            height = random.uniform(3.0, 8.0)
                        
                        building_lots.append({
                            'x': lot_x, 'y': lot_y,
                            'w': bw, 'h': bh,
                            'z_height': height
                        })
                        
        return building_lots
