# ============================================================
# Robot Proxy | Abstract Interface
# Cho phép cùng FleetManager điều khiển cả robot ảo (SIM)
# lẫn robot thật (Hardware)
# ============================================================
from abc import ABC, abstractmethod


class RobotProxy(ABC):
    """Interface thống nhất cho mô phỏng và phần cứng."""

    @abstractmethod
    def send_commands(self, robot_name, commands):
        """Gửi chuỗi lệnh [F, L, R, WAIT] đến robot.
        
        Args:
            robot_name: Tên robot (VD: 'ESP01')
            commands: List lệnh, VD: ['F', 'L', 'F', 'F']
        """
        pass

    @abstractmethod
    def execute_command(self, robot_state, cmd, robot_name, robots_dict, tick_counter, coop_manager):
        """Thực thi 1 lệnh đơn lẻ cho robot.
        
        Returns:
            bool: True nếu thành công
        """
        pass


class SimulationProxy(RobotProxy):
    """Proxy cho chế độ mô phỏng: execute nội bộ giống file gốc."""

    def send_commands(self, robot_name, commands):
        # Trong simulation, lệnh được xử lý trực tiếp qua path_queue
        # Không cần gửi qua serial
        pass

    def execute_command(self, r, cmd, robot_name, robots_dict, tick_counter, coop_manager):
        """Thực thi lệnh — logic cải tiến từ _execute_command() gốc.
        
        FIX: Khi va chạm với robot đang PICKING/DROPPING, chèn WAIT thay vì
        xóa toàn bộ path → tránh vòng lặp xoay liên tục.
        """
        if cmd == 'F':
            dx, dy = {'N': (0, 1), 'E': (1, 0), 'S': (0, -1), 'W': (-1, 0)}[r.heading]
            new_x, new_y = r.x + dx, r.y + dy
            # Kiem tra truc tiep xem vi tri moi co robot khac khong
            for other_name, other_r in robots_dict.items():
                if other_name == robot_name:
                    continue
                # Kiem tra vi tri grid cua robot khac
                if (other_r.x, other_r.y) == (new_x, new_y):
                    # === FIX SPINNING BUG ===
                    # Nếu robot chắn đang PICKING/DROPPING → chờ nó xong thay vì xóa path
                    if other_r.state in ["PICKING", "DROPPING"]:
                        wait_needed = other_r.wait_timer + 2  # +2 buffer di chuyển
                        wait_needed = max(wait_needed, 2)
                        wait_needed = min(wait_needed, 25)  # Cap tối đa 25 ticks
                        # Chèn WAIT + giữ lại lệnh F và phần path còn lại
                        r.path_queue.insert(0, 'F')  # Thêm lại lệnh F vừa bị pop
                        for _ in range(wait_needed):
                            r.path_queue.insert(0, 'WAIT')
                    else:
                        # Robot chắn đang di chuyển → chờ ngắn rồi replan
                        r.path_queue.clear()
                        r.path_queue = ['WAIT', 'WAIT', 'WAIT']
                    # Giữ reservation tại chỗ
                    for t_off in range(5):
                        coop_manager.reservations[(r.x, r.y, tick_counter + t_off)] = robot_name
                    return False
            r.x = new_x; r.y = new_y; r.step_backlog = r.SUB
            # Cap nhat reservation cho vi tri moi
            coop_manager.reservations[(r.x, r.y, tick_counter)] = robot_name
            coop_manager.reservations[(r.x, r.y, tick_counter + 1)] = robot_name
            return True
        elif cmd in ['L', 'R']:
            if cmd == 'L': r.heading = {'N': 'W', 'W': 'S', 'S': 'E', 'E': 'N'}[r.heading]
            else: r.heading = {'N': 'E', 'E': 'S', 'S': 'W', 'W': 'N'}[r.heading]
            r.step_backlog = 3
            return True
        return True
