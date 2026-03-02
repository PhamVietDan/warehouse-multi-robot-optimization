# ============================================================
# Fleet Manager | Bộ não trung tâm điều phối
# Tách từ RobotSimulationApp._server_logic_tick()
# ============================================================
import random
import heapq
import time

from config.settings import (
    PICKUP_NODES, CONFIG_DELIVERY_LOCATIONS, DELIVERY_NODES,
    REMOVE_NODES, SKIP_COLS, SKIP_ROWS,
    WAIT_TIMER_PICK, WAIT_TIMER_DROP, TEST_DURATION,
    RFID_DELIVERY_MAP,
)
from core.robot_state import RobotState
from algorithms.pso_allocator import PSO_TaskAllocator


class FleetManager:
    """Bộ não trung tâm: quản lý trạng thái robot + state machine điều phối.
    
    Chứa toàn bộ logic từ _server_logic_tick() gốc, nhưng không phụ thuộc
    vào Tkinter hay bất kỳ UI framework nào.
    """

    def __init__(self, grid_n, traffic_mgr, coop_planner, robot_proxy, sub=10):
        self.grid_n = grid_n
        self.traffic_mgr = traffic_mgr
        self.coop_manager = coop_planner
        self.proxy = robot_proxy
        self.SUB = sub
        self.robots = {}
        self.tick_counter = 0
        self.is_running = False
        self.is_benchmark_mode = False
        self.start_time = None
        self.TEST_DURATION = TEST_DURATION
        # === HARDWARE MODE ===
        # Khi True: KHÔNG pop/execute commands từ path_queue
        # Để pump_queues gửi TOÀN BỘ batch, vị trí chỉ update từ STEP feedback
        # Giống cách SEVER (1).py hoạt động — không có internal simulation
        self.hardware_mode = False

        # === RFID DELIVERY TRACKING ===
        self.rfid_delivery_log = []       # Lịch sử: [{robot, uid, cell, time}, ...]
        self.rfid_cell_count = {}         # cell_id → số lần giao
        self.rfid_total_delivered = 0     # Tổng hàng xác nhận qua RFID

    # ============================================================
    # XỬ LÝ RFID — Xác nhận giao hàng
    # ============================================================
    def handle_rfid_scan(self, robot_name, uid):
        """Xử lý khi robot quét được thẻ RFID tại ô giao hàng.
        
        Returns:
            dict hoặc None: Thông tin ô giao hàng nếu UID hợp lệ
        """
        info = RFID_DELIVERY_MAP.get(uid)
        if not info:
            return None

        cell_id = info["cell"]
        coord = info["coord"]
        cell_name = info["name"]

        # Tăng đếm
        self.rfid_cell_count[cell_id] = self.rfid_cell_count.get(cell_id, 0) + 1
        self.rfid_total_delivered += 1

        # Ghi log
        record = {
            "robot": robot_name,
            "uid": uid,
            "cell": cell_id,
            "coord": coord,
            "name": cell_name,
            "time": time.time(),
            "count": self.rfid_cell_count[cell_id],
        }
        self.rfid_delivery_log.append(record)

        # Cập nhật trạng thái robot nếu đang ở DROPPING/TO_DELIVERY
        if robot_name in self.robots:
            r = self.robots[robot_name]
            r.delivered_count += 1
            r.last_rfid_event = record

        return record

    # ============================================================
    # SETUP ROBOTS
    # ============================================================
    def setup_robots(self, count):
        self.robots.clear()
        self.tick_counter = 0
        self.coop_manager.reservations.clear()
        valid_spawns = []
        for x in range(self.grid_n):
            for y in range(self.grid_n):
                if (x, y) not in REMOVE_NODES:
                    if x not in SKIP_COLS or y not in SKIP_ROWS:
                        valid_spawns.append((x, y))
        random.shuffle(valid_spawns)
        for i in range(count):
            if not valid_spawns: break
            sx, sy = valid_spawns.pop()
            name = f"ESP{i+1:02d}"
            color = "#1D86FE"
            heading = 'N'
            if sx in self.traffic_mgr.COLS_UP: heading = 'N'
            elif sx in self.traffic_mgr.COLS_DOWN: heading = 'S'
            elif sy in self.traffic_mgr.ROWS_RIGHT: heading = 'E'
            elif sy in self.traffic_mgr.ROWS_LEFT: heading = 'W'
            r = RobotState(name, color, sub=self.SUB)
            r.x, r.y, r.heading = sx, sy, heading
            r.sync_sub_from_grid()
            # Khởi tạo reservation tại vị trí ban đầu để tránh robot khác spawn đè lên
            self.coop_manager.reservations[(sx, sy, 0)] = name
            self.robots[name] = r

    # ============================================================
    # Lộ phí (Dùng BFS Cache cho PSO)
    # ============================================================
    def get_path_cost(self, start_pose, target_xy):
        return self.coop_manager.get_heuristic(start_pose, target_xy)

    # ============================================================
    # CHỌN ĐIỂM TỐI ƯU (1 địa chỉ 3 điểm giao, chọn điểm gần nhất)
    # ============================================================
    def resolve_best_delivery_node(self, logical_id, robot_instance):
        candidates = CONFIG_DELIVERY_LOCATIONS.get(logical_id, [])
        if not candidates:
            return None
        occupied_targets = set()
        for name, r in self.robots.items():
            if name == robot_instance.name: continue
            # Them ca vi tri hien tai cua robot
            occupied_targets.add((r.x, r.y))
            if r.target_node:
                occupied_targets.add(r.target_node)
        # Uu tien cac diem chua ai chon lam dich va chua co robot o do
        available = [pos for pos in candidates if pos not in occupied_targets]
        if not available: available = candidates
        best_node = None
        min_cost = float('inf')
        start_pose = (robot_instance.x, robot_instance.y, robot_instance.heading)
        for pos in available:
            # Dung BFS heuristic tinh nhanh
            cost = self.coop_manager.get_heuristic(start_pose, pos)
            if cost < min_cost:
                min_cost = cost
                best_node = pos
        return best_node if best_node else candidates[0]

    # ============================================================
    # HELPER: Ước tính thời gian block
    # ============================================================
    def _estimate_blocking_time(self, x, y, heading, robot_name):
        """Ước tính thời gian chờ robot đang block phía trước"""
        DIR = {'N': (0, 1), 'E': (1, 0), 'S': (0, -1), 'W': (-1, 0)}
        dx, dy = DIR.get(heading, (0, 0))
        front_x, front_y = x + dx, y + dy
        # Tìm robot đang ở vị trí phía trước
        for name, r in self.robots.items():
            if name == robot_name:
                continue
            if (r.x, r.y) == (front_x, front_y):
                # Nếu robot đang PICKING/DROPPING, trả về wait_timer còn lại
                if r.state in ["PICKING", "DROPPING"]:
                    return r.wait_timer + 2  # +2 cho buffer di chuyển
                # Nếu robot đang di chuyển hoặc chờ, ước tính ngắn
                elif r.path_queue:
                    return min(len(r.path_queue), 5)  # Tối đa 5 tick
                else:
                    return 3  # Default ngắn
        # Không có robot block trực tiếp, kiểm tra reservation
        for t_offset in range(1, 10):
            key = (front_x, front_y, self.tick_counter + t_offset)
            if key not in self.coop_manager.reservations:
                return t_offset  # Thời gian đến khi ô trống
        return 15  # Default nếu không xác định được

    def _is_adjacent_blocked_by_working(self, r, robot_name):
        """Kiểm tra: đích đến CÓ ngay sát bên VÀ đang bị robot PICKING/DROPPING chắn.
        
        Nếu True → robot nên ĐỨNG YÊN CHỜ — KHÔNG replan, KHÔNG xoay.
        Đây là fix chính cho lỗi xoay 4 hướng.
        
        Returns:
            int: Số tick cần chờ (0 nếu không bị chắn)
        """
        if not r.target_node:
            return 0
        tx, ty = r.target_node
        dist = abs(r.x - tx) + abs(r.y - ty)
        # Chỉ xử lý khi đích ở cách 1-2 ô
        if dist > 2:
            return 0
        # Tìm robot đang PICKING/DROPPING tại đích hoặc trên đường đến đích
        for other_name, other_r in self.robots.items():
            if other_name == robot_name:
                continue
            if (other_r.x, other_r.y) == (tx, ty) and other_r.state in ["PICKING", "DROPPING"]:
                return other_r.wait_timer + 3  # Chờ nó xong + buffer
            # Cũng check nếu robot chắn nằm GIỮA mình và đích (dist=2)
            if dist == 1:  # Chắn ngay phía trước
                dx, dy = tx - r.x, ty - r.y
                if (other_r.x, other_r.y) == (r.x + dx, r.y + dy):
                    if other_r.state in ["PICKING", "DROPPING"]:
                        return other_r.wait_timer + 3
        return 0

    def _has_free_neighbor(self, cx, cy, check_time):
        """Check nhanh xem có ô nào xung quanh trống tại check_time không"""
        moves = [(0,1), (0,-1), (1,0), (-1,0)]
        for dx, dy in moves:
            nx, ny = cx + dx, cy + dy
            # Check basic traffic limits
            allowed, _ = self.traffic_mgr.is_valid_move((cx, cy), (nx, ny))
            if allowed:
                # Check reservation
                if (nx, ny, check_time) not in self.coop_manager.reservations:
                    return True
        return False

    def _attempt_escape(self, r, robot_name):
        """Cố gắng tìm bất kỳ ô trống nào để thoát kẹt.
        KHÔNG escape nếu đích đến ngay sát bên — đợi hiệu quả hơn.
        """
        # === FIX: Không escape nếu target ngay cạnh bên ===
        if r.target_node:
            dist = abs(r.x - r.target_node[0]) + abs(r.y - r.target_node[1])
            if dist <= 2:
                return False  # Đừng chạy đi, đợi ở đây
        moves = [(0,1), (0,-1), (1,0), (-1,0)]
        # Ngẫu nhiên hóa để tránh 2 robot cùng escape vào 1 ô
        random.shuffle(moves)
        for dx, dy in moves:
            nx, ny = r.x + dx, r.y + dy
            # Check luật giao thông
            allowed, penalty = self.traffic_mgr.is_valid_move((r.x, r.y), (nx, ny))
            if allowed:
                # Check xem ô có trống tại t+1 không
                if (nx, ny, self.tick_counter + 1) not in self.coop_manager.reservations:
                    # Tìm thấy lối thoát! Di chuyển ngay
                    # Tự tạo path 1 bước
                    if dx == 0 and dy == 1: head = 'N'
                    elif dx == 0 and dy == -1: head = 'S'
                    elif dx == 1 and dy == 0: head = 'E'
                    else: head = 'W'
                    # Nếu cần xoay
                    cmds = []
                    if r.heading != head:
                        # Logic xoay đơn giản: Xoay đến khi đúng hướng
                        if (r.heading == 'N' and head == 'S') or \
                           (r.heading == 'S' and head == 'N') or \
                           (r.heading == 'E' and head == 'W') or \
                           (r.heading == 'W' and head == 'E'):
                           # Ngược hướng, xoay 2 lần (L, L)
                           cmds = ['L', 'L']
                        elif (r.heading == 'N' and head == 'W') or \
                             (r.heading == 'W' and head == 'S') or \
                             (r.heading == 'S' and head == 'E') or \
                             (r.heading == 'E' and head == 'N'):
                             cmds = ['L']
                        else:
                             cmds = ['R']

                    cmds.append('F')
                    # Update path queue
                    r.path_queue = cmds

                    # Reserve path escape
                    self.coop_manager.clear_reservation(robot_name, self.tick_counter, (r.x, r.y))
                    # Reserve wait/turn ticks + move tick
                    t = self.tick_counter
                    # Reserve hiện tại
                    self.coop_manager.reservations[(r.x, r.y, t)] = robot_name
                    t += 1
                    for _ in range(len(cmds)-1): # Turns don't change pos
                        self.coop_manager.reservations[(r.x, r.y, t)] = robot_name
                        t += 1
                    # Move step
                    self.coop_manager.reservations[(nx, ny, t)] = robot_name

                    r.stuck_counter = 0 # Reset stuck
                    return True
        return False

    # ============================================================
    # LOGIC TRUNG TÂM ĐIỀU PHỐI (cho CA*)
    # Tương đương _server_logic_tick() trong file gốc
    # ============================================================
    def update_tick(self):
        """Gọi mỗi logic tick. Trả về dict thông tin cho UI nếu cần.
        
        Returns:
            dict hoặc None: Thông tin benchmark kết thúc nếu có
        """
        if not self.is_running:
            return None

        self.tick_counter += 1
        result = None

        if self.is_benchmark_mode:
            elapsed = time.time() - self.start_time
            remaining = max(0, self.TEST_DURATION - elapsed)
            if elapsed >= self.TEST_DURATION:
                self.is_running = False
                total_delivered = sum(r.delivered_count for r in self.robots.values())
                result = {
                    'event': 'benchmark_done',
                    'total_delivered': total_delivered,
                    'elapsed': elapsed,
                    'remaining': 0,
                }
                return result
            else:
                result = {
                    'event': 'benchmark_tick',
                    'remaining': remaining,
                    'elapsed': elapsed,
                }
        else:
            # Timer tăng dần cho chế độ chạy bình thường
            elapsed = time.time() - self.start_time
            result = {
                'event': 'normal_tick',
                'elapsed': elapsed,
            }

        # Dọn dẹp reservation cũ MỖI TICK để giải quyết tắc nghẽn nhanh hơn
        self.coop_manager.clear_old_reservations(self.tick_counter - 2)

        # Kiem tra va cham: phat hien robot trung toa do
        positions = {}
        for name, r in self.robots.items():
            grid_pos = (r.x, r.y)
            if grid_pos in positions:
                other_name = positions[grid_pos]
                pass
            else:
                positions[grid_pos] = name

        # Sắp xếp robot để xử lý: 1. Ưu tiên robot đang giao hàng (TO_DELIVERY) để giải phóng đường
        # 2. Ưu tiên robot có số ID thấp hơn (ESP01 > ESP02 > ...)
        def get_robot_priority(item):
            name, r = item
            state_priority = 0 if r.state == "TO_DELIVERY" else (1 if r.state == "DROPPING" else 2)
            try:
                robot_num = int(name.replace("ESP", ""))
            except:
                robot_num = 99
            return (state_priority, robot_num)

        sorted_robots = sorted(self.robots.items(), key=get_robot_priority)
        for name, r in sorted_robots:
            if r.paused or r.step_backlog > 0: continue
            # === HARDWARE: Robot chưa online → KHÔNG xử lý ===
            # Tránh tính path từ vị trí START_POSE khi robot thật ở vị trí khác
            if not r.alive:
                continue
            # === HARDWARE MODE: Robot đang chờ BATCH_DONE từ phần cứng ===
            # KHÔNG replan, KHÔNG execute, KHÔNG chạm vào robot này
            if r.wait_robot:
                # Chỉ giữ reservation vị trí hiện tại
                self.coop_manager.reservations[(r.x, r.y, self.tick_counter)] = name
                self.coop_manager.reservations[(r.x, r.y, self.tick_counter + 1)] = name
                continue
            if r.wait_timer > 0:
                # Dam bao khong co robot khac den vi tri nay trong thoi gian cho
                for t_offset in range(r.wait_timer + 2):
                    self.coop_manager.reservations[(r.x, r.y, self.tick_counter + t_offset)] = name
                r.wait_timer -= 1
                continue

            # Kiểm tra robot có bị stuck không
            current_pos = (r.x, r.y)
            if r.last_position == current_pos:
                r.stuck_counter += 1
            else:
                r.stuck_counter = 0
                r.last_position = current_pos

            # Nếu robot bị stuck quá lâu và có path_queue, force replan
            if r.stuck_counter >= r.MAX_STUCK and r.path_queue:
                # Xóa path cũ và xóa reservation
                r.path_queue.clear()
                self.coop_manager.clear_reservation(name, self.tick_counter, (r.x, r.y))
                # Giữ reservation vị trí hiện tại
                self.coop_manager.reservations[(r.x, r.y, self.tick_counter)] = name
                self.coop_manager.reservations[(r.x, r.y, self.tick_counter + 1)] = name
                r.stuck_counter = 0

            # Nếu stuck > 25 ticks (1.25s) mà không có path, force về IDLE để lấy mục tiêu mới
            if r.stuck_counter >= 25 and not r.path_queue and r.state not in ["IDLE", "PICKING", "DROPPING", "TO_DELIVERY"]:
                r.state = "IDLE"
                r.target_node = None
                r.current_job_pickup = None
                r.future_delivery_logical_id = None
                self.coop_manager.clear_reservation(name, self.tick_counter, (r.x, r.y))
                self.coop_manager.reservations[(r.x, r.y, self.tick_counter)] = name
                self.coop_manager.reservations[(r.x, r.y, self.tick_counter + 1)] = name
                r.stuck_counter = 0

            # 1. Xử lý di chuyển theo kế hoạch CA*
            if r.path_queue:
                # EARLY-EXIT: Nếu đã đến đích, dừng lại ngay
                if r.target_node and (r.x, r.y) == r.target_node:
                    r.path_queue.clear()
                    self.coop_manager.clear_reservation(name, self.tick_counter, (r.x, r.y))
                    self.coop_manager.reservations[(r.x, r.y, self.tick_counter)] = name
                    self.coop_manager.reservations[(r.x, r.y, self.tick_counter + 1)] = name
                    # Không continue - để state machine xử lý arrival
                elif self.hardware_mode:
                    # === HARDWARE MODE ===
                    # KHÔNG pop, KHÔNG execute_command
                    # Để path_queue nguyên vẹn cho pump_queues gửi batch
                    # Vị trí CHỈ update từ STEP/POS feedback (giống SEVER)
                    self.coop_manager.reservations[(r.x, r.y, self.tick_counter)] = name
                    self.coop_manager.reservations[(r.x, r.y, self.tick_counter + 1)] = name
                    continue
                else:
                    cmd = r.path_queue.pop(0)
                    if cmd == 'WAIT':
                        wait_count = 1
                        for next_cmd in r.path_queue:
                            if next_cmd == 'WAIT':
                                wait_count += 1
                            else:
                                break
                        if wait_count >= 30:
                            r.path_queue.clear()
                            self.coop_manager.clear_reservation(name, self.tick_counter, (r.x, r.y))
                            self.coop_manager.reservations[(r.x, r.y, self.tick_counter)] = name
                            self.coop_manager.reservations[(r.x, r.y, self.tick_counter + 1)] = name
                        else:
                            self.coop_manager.reservations[(r.x, r.y, self.tick_counter)] = name
                            self.coop_manager.reservations[(r.x, r.y, self.tick_counter + 1)] = name
                            continue
                    else:
                        self.proxy.execute_command(r, cmd, name, self.robots, self.tick_counter, self.coop_manager)
                        continue

            # 2. State Machine
            if r.manual_override:
                # Manual override logic giữ nguyên
                continue

            # TRANG THAI: IDLE (Tim hang)
            if r.state == "IDLE":
                pso = PSO_TaskAllocator((r.x, r.y, r.heading), r.heading, self.robots, self.coop_manager, name)
                best_scenario = pso.run()
                pickup = best_scenario['pickup']
                future_l_id = best_scenario['logical_id']
                if pickup:
                    r.target_node = pickup
                    r.future_delivery_logical_id = future_l_id
                    r.current_job_pickup = pickup
                    if (r.x, r.y) == pickup:
                        r.state = "PICKING"
                        r.wait_timer = 0 # logic
                    else:
                        # [CA* PLANNING]
                        self.coop_manager.clear_reservation(name, self.tick_counter, (r.x, r.y))
                        path, states = self.coop_manager.find_path_space_time((r.x, r.y, r.heading), pickup, self.tick_counter, name)
                        if path is not None:
                            r.path_queue = path
                            # Đặt chỗ bao gồm vị trí xuất phát
                            start_pos = (r.x, r.y, r.heading, self.tick_counter)
                            self.coop_manager.reserve_path(name, states, 0, start_pos)
                            r.state = "TO_PICKUP"
                        else:
                            # Thử ngay các pickup khác - chỉ khi có lối thoát
                            found_alt = False
                            has_exit = self._has_free_neighbor(r.x, r.y, self.tick_counter + 1)

                            if has_exit:
                                for alt_pickup in PICKUP_NODES:
                                    if alt_pickup == pickup:
                                        continue
                                    alt_path, alt_states = self.coop_manager.find_path_space_time((r.x, r.y, r.heading), alt_pickup, self.tick_counter, name)
                                    if alt_path is not None:
                                        r.path_queue = alt_path
                                        r.target_node = alt_pickup
                                        r.current_job_pickup = alt_pickup
                                        start_pos = (r.x, r.y, r.heading, self.tick_counter)
                                        self.coop_manager.reserve_path(name, alt_states, 0, start_pos)
                                        r.state = "TO_PICKUP"
                                        found_alt = True
                                        break
                            if not found_alt:
                                r.path_queue = ['WAIT']
                                self.coop_manager.reservations[(r.x, r.y, self.tick_counter)] = name
                                self.coop_manager.reservations[(r.x, r.y, self.tick_counter + 1)] = name
                                self.coop_manager.reservations[(r.x, r.y, self.tick_counter + 2)] = name

            # TRẠNG THÁI: TO_PICKUP
            elif r.state == "TO_PICKUP":
                # Đã đến đích
                if (r.x, r.y) == r.target_node:
                    r.state = "PICKING"
                    r.wait_timer = WAIT_TIMER_PICK
                else:
                    # === FIX SPINNING: Check đích có bị robot PICKING/DROPPING chắn ===
                    adjacent_wait = self._is_adjacent_blocked_by_working(r, name)
                    if adjacent_wait > 0:
                        # Đích ngay sát + có robot đang làm việc → ĐỨNG YÊN, KHÔNG replan
                        wait_ticks = min(adjacent_wait, 25)
                        r.path_queue = ['WAIT'] * wait_ticks
                        for t_off in range(wait_ticks + 2):
                            self.coop_manager.reservations[(r.x, r.y, self.tick_counter + t_off)] = name
                        continue  # Bỏ qua toàn bộ replan bên dưới

                    # Nếu hết path mà chưa đến đích -> replan
                    self.coop_manager.clear_reservation(name, self.tick_counter, (r.x, r.y))
                    path, states = self.coop_manager.find_path_space_time((r.x, r.y, r.heading), r.target_node, self.tick_counter, name)
                    if path is not None:
                        r.path_queue = path
                        start_pos = (r.x, r.y, r.heading, self.tick_counter)
                        self.coop_manager.reserve_path(name, states, 0, start_pos)
                    else:
                        # Ước tính thời gian chờ robot đang block
                        blocking_time = self._estimate_blocking_time(r.x, r.y, r.heading, name)
                        # Tìm alternative pickup tốt nhất - chỉ khi có lối thoát
                        best_alt_path = None
                        best_alt_pickup = None
                        best_alt_states = None
                        best_alt_len = float('inf')
                        has_exit = self._has_free_neighbor(r.x, r.y, self.tick_counter + 1)
                        if has_exit:
                            for alt_pickup in PICKUP_NODES:
                                if alt_pickup == r.target_node:
                                    continue
                                alt_path, alt_states = self.coop_manager.find_path_space_time((r.x, r.y, r.heading), alt_pickup, self.tick_counter, name)
                                if alt_path is not None and len(alt_path) < best_alt_len:
                                    best_alt_len = len(alt_path)
                                    best_alt_path = alt_path
                                    best_alt_pickup = alt_pickup
                                    best_alt_states = alt_states
                        # Ưu tiên chờ: robot thật di chuyển chậm nên đợi thường hiệu quả hơn
                        # chuyển sang pickup khác. Ngưỡng 25 ticks ~ 1.25s thực tế.
                        if blocking_time <= best_alt_len or blocking_time <= 25:
                            # Chờ đủ thời gian để robot chắn rời đi
                            wait_ticks = min(blocking_time + 2, 25)
                            r.path_queue = ['WAIT'] * wait_ticks
                            for t_offset in range(wait_ticks + 2):
                                self.coop_manager.reservations[(r.x, r.y, self.tick_counter + t_offset)] = name
                        elif best_alt_path is not None:
                            r.path_queue = best_alt_path
                            r.target_node = best_alt_pickup
                            r.current_job_pickup = best_alt_pickup
                            start_pos = (r.x, r.y, r.heading, self.tick_counter)
                            self.coop_manager.reserve_path(name, best_alt_states, 0, start_pos)
                        else:
                            r.path_queue = ['WAIT']
                            self.coop_manager.reservations[(r.x, r.y, self.tick_counter)] = name
                            self.coop_manager.reservations[(r.x, r.y, self.tick_counter + 1)] = name
                            self.coop_manager.reservations[(r.x, r.y, self.tick_counter + 2)] = name

            # TRẠNG THÁI: PICKING -> Chuyển sang TO_DELIVERY
            elif r.state == "PICKING":
                l_id = r.future_delivery_logical_id
                if l_id is None: l_id = random.choice(list(CONFIG_DELIVERY_LOCATIONS.keys()))
                real_delivery_node = self.resolve_best_delivery_node(l_id, r)
                # [CA* PLANNING] Giữ lại reservation vị trí hiện tại khi lập kế hoạch
                self.coop_manager.clear_reservation(name, self.tick_counter, (r.x, r.y))
                # OPTIMIZATION: Check nhanh xem có lối thoát không trước khi gọi A*
                has_exit = self._has_free_neighbor(r.x, r.y, self.tick_counter + 1)
                path = None
                states = None
                if has_exit:
                    path, states = self.coop_manager.find_path_space_time(
                        (r.x, r.y, r.heading), real_delivery_node, self.tick_counter, name
                    )
                if path is not None:
                    r.path_queue = path
                    # Đặt chỗ bao gồm vị trí xuất phát
                    start_pos = (r.x, r.y, r.heading, self.tick_counter)
                    self.coop_manager.reserve_path(name, states, 0, start_pos)
                    r.target_node = real_delivery_node
                    r.state = "TO_DELIVERY"
                else:
                    # Không tìm được đường ngay hoặc bị vây kín - chờ ngắn 1 tick
                    r.path_queue = ['WAIT']
                    r.target_node = real_delivery_node
                    r.state = "TO_DELIVERY"
                    # Giữ reservation vị trí hiện tại
                    self.coop_manager.reservations[(r.x, r.y, self.tick_counter)] = name
                    self.coop_manager.reservations[(r.x, r.y, self.tick_counter + 1)] = name
                    self.coop_manager.reservations[(r.x, r.y, self.tick_counter + 2)] = name

            # TRẠNG THÁI: TO_DELIVERY
            elif r.state == "TO_DELIVERY":
                if (r.x, r.y) == r.target_node:
                    r.state = "DROPPING"
                    r.wait_timer = WAIT_TIMER_DROP
                else:
                    # === FIX SPINNING: Check đích có bị robot PICKING/DROPPING chắn ===
                    adjacent_wait = self._is_adjacent_blocked_by_working(r, name)
                    if adjacent_wait > 0:
                        # Đích ngay sát + có robot đang làm việc → ĐỨNG YÊN, KHÔNG replan
                        wait_ticks = min(adjacent_wait, 25)
                        r.path_queue = ['WAIT'] * wait_ticks
                        for t_off in range(wait_ticks + 2):
                            self.coop_manager.reservations[(r.x, r.y, self.tick_counter + t_off)] = name
                        continue  # Bỏ qua toàn bộ replan bên dưới

                    # Nếu hết path mà chưa đến đích, replan
                    self.coop_manager.clear_reservation(name, self.tick_counter, (r.x, r.y))
                    # OPTIMIZATION: Check nhanh neighbor
                    has_exit = self._has_free_neighbor(r.x, r.y, self.tick_counter + 1)
                    path = None
                    states = None

                    if has_exit:
                        path, states = self.coop_manager.find_path_space_time(
                            (r.x, r.y, r.heading), r.target_node, self.tick_counter, name
                        )
                    if path is not None:
                        r.path_queue = path
                        start_pos = (r.x, r.y, r.heading, self.tick_counter)
                        self.coop_manager.reserve_path(name, states, 0, start_pos)
                    else:
                        # OPTIMIZATION: Nếu không có lối thoát, skip alternative search
                        # Chỉ tìm alternative khi có ít nhất 1 ô trống xung quanh
                        found_alternative = False

                        if has_exit:
                            # Thử tìm delivery node thay thế cùng logical ID
                            l_id = r.future_delivery_logical_id
                            if l_id and l_id in CONFIG_DELIVERY_LOCATIONS:
                                for alt_delivery in CONFIG_DELIVERY_LOCATIONS[l_id]:
                                    if alt_delivery == r.target_node:
                                        continue
                                    alt_path, alt_states = self.coop_manager.find_path_space_time(
                                        (r.x, r.y, r.heading), alt_delivery, self.tick_counter, name
                                    )
                                    if alt_path is not None:
                                        r.path_queue = alt_path
                                        r.target_node = alt_delivery
                                        start_pos = (r.x, r.y, r.heading, self.tick_counter)
                                        self.coop_manager.reserve_path(name, alt_states, 0, start_pos)
                                        found_alternative = True
                                        break
                            # Nếu vẫn không tìm được, thử TỐI ĐA 3 logical_id khác
                            if not found_alternative:
                                alt_count = 0
                                for other_l_id in CONFIG_DELIVERY_LOCATIONS.keys():
                                    if other_l_id == l_id:
                                        continue
                                    if alt_count >= 3:  # Giới hạn 3 logical_id
                                        break
                                    alt_count += 1
                                    for alt_delivery in CONFIG_DELIVERY_LOCATIONS[other_l_id]:
                                        alt_path, alt_states = self.coop_manager.find_path_space_time(
                                            (r.x, r.y, r.heading), alt_delivery, self.tick_counter, name
                                        )
                                        if alt_path is not None:
                                            r.path_queue = alt_path
                                            r.target_node = alt_delivery
                                            r.future_delivery_logical_id = other_l_id
                                            start_pos = (r.x, r.y, r.heading, self.tick_counter)
                                            self.coop_manager.reserve_path(name, alt_states, 0, start_pos)
                                            found_alternative = True
                                            break
                                    if found_alternative:
                                        break

                        if not found_alternative:
                            escaped = False
                            if r.stuck_counter > 5:
                                escaped = self._attempt_escape(r, name)
                            if not escaped:
                                # Chờ ngắn 1 tick để thử lại
                                r.path_queue = ['WAIT']
                                self.coop_manager.reservations[(r.x, r.y, self.tick_counter)] = name
                                self.coop_manager.reservations[(r.x, r.y, self.tick_counter + 1)] = name
                                self.coop_manager.reservations[(r.x, r.y, self.tick_counter + 2)] = name

            # TRẠNG THÁI: DROPPING
            elif r.state == "DROPPING":
                r.delivered_count += 1
                r.state = "IDLE"
                r.target_node = None
                r.future_delivery_logical_id = None
                r.current_job_pickup = None
                # Xóa reservation cũ nhưng giữ vị trí hiện tại để chuẩn bị cho chu trình mới
                self.coop_manager.clear_reservation(name, self.tick_counter, (r.x, r.y))
                # Đặt chỗ vị trí hiện tại cho tick tiếp theo
                self.coop_manager.reservations[(r.x, r.y, self.tick_counter)] = name
                self.coop_manager.reservations[(r.x, r.y, self.tick_counter + 1)] = name

        return result

    # ============================================================
    # PATHFINDING CŨ CHO MANUAL MODE
    # ============================================================
    def find_path_old(self, start_pose, target_xy):
        """Backup hàm A* cũ cho chế độ Manual"""
        sx, sy, sh = start_pose
        tx, ty = target_xy
        if (sx, sy) == (tx, ty): return []
        queue = []
        heapq.heappush(queue, (0, 0, sx, sy, sh, []))
        visited_costs = {}
        DIR = {'N': (0, 1), 'E': (1, 0), 'S': (0, -1), 'W': (-1, 0)}
        LEFT = {'N': 'W', 'W': 'S', 'S': 'E', 'E': 'N'}
        RIGHT = {'N': 'E', 'E': 'S', 'S': 'W', 'W': 'N'}
        while queue:
            _, cost, cx, cy, ch, path = heapq.heappop(queue)
            if (cx, cy) == (tx, ty): return path
            state = (cx, cy, ch)
            if state in visited_costs and visited_costs[state] <= cost: continue
            visited_costs[state] = cost
            dx, dy = DIR[ch]
            nx, ny = cx + dx, cy + dy
            allowed, penalty = self.traffic_mgr.is_valid_move((cx, cy), (nx, ny))
            if allowed:
                new_cost = cost + penalty
                heuristic = (abs(nx - tx) + abs(ny - ty))
                heapq.heappush(queue, (new_cost + heuristic, new_cost, nx, ny, ch, path + ['F']))
            nh = RIGHT[ch]; new_cost = cost + 2
            heapq.heappush(queue, (new_cost + abs(cx-tx)+abs(cy-ty), new_cost, cx, cy, nh, path + ['R']))
            nh = LEFT[ch]; new_cost = cost + 2
            heapq.heappush(queue, (new_cost + abs(cx-tx)+abs(cy-ty), new_cost, cx, cy, nh, path + ['L']))
        return None
