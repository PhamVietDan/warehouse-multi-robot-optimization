# ============================================================
# COOPERATIVE A* | CooperativePlanner
# ============================================================
import heapq
from collections import deque


class CooperativePlanner:
    def __init__(self, grid_n, traffic_mgr):
        self.grid_n = grid_n
        self.traffic_mgr = traffic_mgr
        # Reservation Table: Key=(x, y, t), Value=RobotName
        self.reservations = {}
        # Cache BFS: Key=(start_tuple, end_tuple), Value=Distance
        # Để tiết kiệm mem, chỉ cache các điểm quan trọng hoặc tính lazy
        self.bfs_cache = {}
        self.all_nodes = [(x,y) for x in range(grid_n) for y in range(grid_n)]
        # Pre-compute BFS cho toàn map (vì map nhỏ 11x11)
        self.precompute_all_pairs()

    def precompute_all_pairs(self):
        # Tính khoảng cách thực tế từ mọi ô đến mọi ô dựa trên luật giao thông dùng tính heuristic
        for start_node in self.all_nodes:
            self._bfs_from_source(start_node)

    def _bfs_from_source(self, start_node):
        q = deque([(start_node, 0)])
        visited = {start_node: 0}
        while q:
            (cx, cy), dist = q.popleft()
            self.bfs_cache[(start_node, (cx, cy))] = dist
            # Lấy hàng xóm hợp lệ theo luật giao thông
            neighbors = self.traffic_mgr.get_valid_neighbors(cx, cy)
            for (nx, ny), _ in neighbors:
                if (nx, ny) not in visited:
                    visited[(nx, ny)] = dist + 1
                    q.append(((nx, ny), dist + 1))
        # Fill các điểm không đến được bằng vô cực
        for target in self.all_nodes:
            if (start_node, target) not in self.bfs_cache:
                self.bfs_cache[(start_node, target)] = 9999

    def get_heuristic(self, start_pose, target_xy):
        # start_pose có thể là (x,y,h) hoặc (x,y)
        sx, sy = start_pose[0], start_pose[1]
        return self.bfs_cache.get(((sx, sy), target_xy), abs(sx - target_xy[0]) + abs(sy - target_xy[1]))

    def clear_reservation(self, robot_name, keep_current_time=None, keep_pos=None):
        # Xóa các đặt chỗ cũ của robot này để replan, giữ lại reservation cho vị trí hiện tại nếu được chỉ định
        keys_to_remove = [k for k, v in self.reservations.items() if v == robot_name]
        for k in keys_to_remove:
            if keep_current_time is not None and keep_pos is not None:
                # Giữ lại reservation cho vị trí hiện tại và các tick kế tiếp (đang di chuyển)
                if k[0] == keep_pos[0] and k[1] == keep_pos[1] and k[2] >= keep_current_time:
                    continue
            del self.reservations[k]

    def clear_old_reservations(self, current_time):
        """Xóa các reservations đã hết hạn (tick cũ) để tránh memory leak và giữ lookup nhanh"""
        keys_to_remove = [k for k in self.reservations if k[2] < current_time]
        for k in keys_to_remove:
            del self.reservations[k]

    def reserve_path(self, robot_name, path_states, start_time, start_pos=None):
        # Đặt chỗ cho vị trí xuất phát nếu được cung cấp
        if start_pos:
            sx, sy, sh, st = start_pos
            self.reservations[(sx, sy, st)] = robot_name
        for (x, y, h, t) in path_states:
            self.reservations[(x, y, t)] = robot_name
        # Đặt chỗ cho thời gian thao tác (Dừng 1s = 2 ticks)
        if path_states:
            last_x, last_y, _, last_t = path_states[-1]
            STEPS_WAIT = 2
            for i in range(1, STEPS_WAIT + 1):
                self.reservations[(last_x, last_y, last_t + i)] = robot_name

    def find_path_space_time(self, start_pose, target_xy, current_time, robot_name, max_depth=200):
        sx, sy, sh = start_pose
        # Nếu đích đến không thể tiếp cận (do luật giao thông), trả về None ngay
        if self.get_heuristic((sx, sy), target_xy) >= 9999:
            return None
        # Priority Queue: (f_score, g_score, x, y, heading, t, path_cmds, path_states)
        queue = [(0, 0, sx, sy, sh, current_time, [], [])]
        visited = {} # Visited: (x, y, heading, t)-> g_score
        DIR = {'N': (0, 1), 'E': (1, 0), 'S': (0, -1), 'W': (-1, 0)}
        LEFT = {'N': 'W', 'W': 'S', 'S': 'E', 'E': 'N'}
        RIGHT = {'N': 'E', 'E': 'S', 'S': 'W', 'W': 'N'}
        best_path = None
        min_h = float('inf')
        while queue:
            f, g, cx, cy, ch, ct, path, states = heapq.heappop(queue)
            if g > max_depth:
                continue
            # Check đích
            if (cx, cy) == target_xy:
                # Kiểm tra xem đích có trống không?
                is_safe = True
                for i in range(1, 5):
                    if (cx, cy, ct + i) in self.reservations:
                        is_safe = False; break
                if is_safe:
                    return path, states
            state_key = (cx, cy, ch, ct)
            if state_key in visited and visited[state_key] <= g:
                continue
            visited[state_key] = g
            # --- OPTION 1: DI CHUYỂN (MOVE) ---
            dx, dy = DIR[ch]
            nx, ny = cx + dx, cy + dy
            # Check luật giao thông
            allowed, penalty = self.traffic_mgr.is_valid_move((cx, cy), (nx, ny))
            if allowed:
                # Kiểm tra: Ô đích (nx, ny) phải trống tại t+1
                if (nx, ny, ct + 1) not in self.reservations:
                    new_g = g + penalty
                    h = self.get_heuristic((nx, ny), target_xy)
                    new_f = new_g + h
                    new_cmds = path + ['F']
                    new_states = states + [(nx, ny, ch, ct + 1)]
                    heapq.heappush(queue, (new_f, new_g, nx, ny, ch, ct + 1, new_cmds, new_states))
            # --- OPTION 2: XOAY (TURN) ---
            # Xoay tốn 1 nhịp thời gian
            for turn_cmd, next_h in [('L', LEFT[ch]), ('R', RIGHT[ch])]:
                if (cx, cy, ct + 1) not in self.reservations:
                    new_g = g + 1 # Optimized: lower turn penalty for flexibility
                    h = self.get_heuristic((cx, cy), target_xy)
                    new_f = new_g + h
                    new_cmds = path + [turn_cmd]
                    new_states = states + [(cx, cy, next_h, ct + 1)]
                    heapq.heappush(queue, (new_f, new_g, cx, cy, next_h, ct + 1, new_cmds, new_states))
            # --- OPTION 3: ĐỨNG CHỜ (WAIT) ---
            # Nếu phía trước tắc, robot có thể chọn đứng yên
            if (cx, cy, ct + 1) not in self.reservations:
                new_g = g + 1
                h = self.get_heuristic((cx, cy), target_xy)
                # Phạt nhẹ lệnh WAIT để ưu tiên di chuyển nếu có thể
                new_f = new_g + h + 0.5
                new_cmds = path + ['WAIT']
                new_states = states + [(cx, cy, ch, ct + 1)]
                heapq.heappush(queue, (new_f, new_g, cx, cy, ch, ct + 1, new_cmds, new_states))
        return None, None
