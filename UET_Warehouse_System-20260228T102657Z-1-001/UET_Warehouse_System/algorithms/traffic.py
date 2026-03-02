# ============================================================
# QUẢN LÝ GIAO THÔNG | TrafficManager
# ============================================================
from config.settings import SKIP_COLS, SKIP_ROWS


class TrafficManager:
    def __init__(self, grid_n, obstacles):
        self.grid_n = grid_n
        self.obstacles = obstacles
        # LUẬT GIAO THÔNG
        self.COLS_DOWN = {0, 3, 6, 9}
        self.COLS_UP = {1, 4, 7, 10}
        self.ROWS_RIGHT = {0, 3, 6, 9}
        self.ROWS_LEFT = {1, 4, 7, 10}

    def is_valid_move(self, curr_pos, next_pos):
        cx, cy = curr_pos
        nx, ny = next_pos
        if not (0 <= nx < self.grid_n and 0 <= ny < self.grid_n) or next_pos in self.obstacles:
            return False, 0
        # Xác định hướng di chuyển
        dirs = {(0,1): 'N', (0,-1): 'S', (1,0): 'E', (-1,0): 'W'}
        direction = dirs.get((nx-cx, ny-cy))
        if not direction: return False, 0
        # Kiểm tra cột/hàng bị chặn
        if direction in 'NS' and cx in SKIP_COLS: return False, 0
        if direction in 'EW' and cy in SKIP_ROWS: return False, 0
        # Kiểm tra luật giao thông
        allowed = {'N': cx in self.COLS_UP, 'S': cx in self.COLS_DOWN,
                   'E': cy in self.ROWS_RIGHT, 'W': cy in self.ROWS_LEFT}
        return (True, 1) if allowed[direction] else (False, 0)

    def get_valid_neighbors(self, cx, cy):
        valid = []
        moves = {'N': (0,1), 'S':(0,-1), 'E':(1,0), 'W':(-1,0)}
        for d, (dx, dy) in moves.items():
            nx, ny = cx + dx, cy + dy
            allowed, _ = self.is_valid_move((cx, cy), (nx, ny))
            if allowed:
                valid.append(((nx, ny), d))
        return valid
