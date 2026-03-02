# ============================================================
# PSO OPTIMIZER | PSO_TaskAllocator
# (thuật toán của Đăng_chưa update fitness)
# ============================================================
import random
from config.settings import PICKUP_NODES, CONFIG_DELIVERY_LOCATIONS


class PSO_TaskAllocator:
    def __init__(self, current_pos, current_heading, robots_dict, coop_manager, caller_name=None):
        # THAY ĐỔI DUY NHẤT: nhận robots_dict và coop_manager trực tiếp
        # thay vì app_instance
        self.robots = robots_dict
        self.coop_manager = coop_manager
        self.start_pos = current_pos
        self.caller_name = caller_name  # Ten robot dang goi PSO
        self.pickup_options = PICKUP_NODES
        self.logical_ids = list(CONFIG_DELIVERY_LOCATIONS.keys())
        self.scenarios = []
        for p_node in self.pickup_options:
            l_id = random.choice(self.logical_ids)
            self.scenarios.append({'pickup': p_node, 'logical_id': l_id})
        self.num_particles = 15   # Optimized: increased for better PSO exploration
        self.iterations = 5
        self.w = 0.5
        self.c1 = 1.5
        self.c2 = 1.5
        self.min_val = 0
        self.max_val = len(self.pickup_options) - 0.01
        self.particles = []
        for _ in range(self.num_particles):
            pos = random.uniform(self.min_val, self.max_val)
            self.particles.append({'pos': pos, 'vel': random.uniform(-1, 1), 'best_pos': pos, 'best_cost': float('inf'), 'current_cost': float('inf')})
        self.global_best_pos = self.particles[0]['pos']
        self.global_best_cost = float('inf')
        self.cost_cache = {}

    def calculate_fitness(self, float_index):
        idx = int(float_index)
        if idx < 0: idx = 0
        if idx >= len(self.pickup_options): idx = len(self.pickup_options) - 1
        if idx in self.cost_cache: return self.cost_cache[idx]
        scenario = self.scenarios[idx]
        pickup = scenario['pickup']
        l_id = scenario['logical_id']
        # Kiem tra xem pickup nay co robot khac dang den hoac dang o khong (moi them)
        occupied_penalty = 0
        for rname, r in self.robots.items():
            # Bo qua robot dang goi PSO
            if rname == self.caller_name:
                continue
            # Neu robot khac dang o pickup nay hoac dang di den pickup nay
            if (r.x, r.y) == pickup:
                occupied_penalty = 99999  # Pickup da co robot
                break
            if r.target_node == pickup and r.state in ["TO_PICKUP", "PICKING"]:
                occupied_penalty = 99999  # Pickup da co robot dang den
                break
        # Su dung BFS heuristic de uoc luong nhanh thay vi A* full
        path1_len = self.coop_manager.get_heuristic(self.start_pos, pickup)
        candidates = CONFIG_DELIVERY_LOCATIONS[l_id]
        min_path2 = 99999
        # Uoc luong huong tam thoi tai diem pickup (lay huong Bac 'N' de tinh toan don gian)
        sim_start_state = (pickup[0], pickup[1], 'N')

        for delivery_phys in candidates:
            p_len = self.coop_manager.get_heuristic(sim_start_state, delivery_phys)
            if p_len < min_path2:
                min_path2 = p_len

        total_cost = path1_len + min_path2 + occupied_penalty
        self.cost_cache[idx] = total_cost
        return total_cost

    def run(self):
        for i in range(self.iterations):
            for p in self.particles:
                cost = self.calculate_fitness(p['pos'])
                p['current_cost'] = cost
                if cost < p['best_cost']:
                    p['best_cost'] = cost; p['best_pos'] = p['pos']
                if cost < self.global_best_cost:
                    self.global_best_cost = cost; self.global_best_pos = p['pos']

            for p in self.particles:
                r1 = random.random(); r2 = random.random()
                vel_cognitive = self.c1 * r1 * (p['best_pos'] - p['pos'])
                vel_social = self.c2 * r2 * (self.global_best_pos - p['pos'])
                p['vel'] = self.w * p['vel'] + vel_cognitive + vel_social
                p['pos'] += p['vel']
                if p['pos'] < self.min_val: p['pos'] = self.min_val
                if p['pos'] > self.max_val: p['pos'] = self.max_val
        best_idx = int(self.global_best_pos)
        if best_idx < 0: best_idx = 0
        if best_idx >= len(self.pickup_options): best_idx = len(self.pickup_options) - 1
        return self.scenarios[best_idx]
