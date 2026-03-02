# ============================================================
# Trạng thái Robot | RobotState
# ============================================================
from config.settings import MAX_STUCK


class RobotState:
    def __init__(self, name, color, sub=6):
        self.name = name
        self.color = color
        self.x = 0; self.y = 0; self.heading = 'N'
        self.SUB = sub
        self.sx = self.x * self.SUB
        self.sy = self.y * self.SUB
        self.step_cnt = 0
        self.step_backlog = 0
        self.state = "IDLE"
        self.target_node = None
        self.future_delivery_logical_id = None
        self.current_job_pickup = None
        self.path_queue = []
        self.wait_timer = 0
        self.paused = False
        self.manual_override = False
        self.delivered_count = 0
        self.has_planned = False         # Theo dõi xem robot có đang theo plan CA* không
        self.stuck_counter = 0           # check robot kẹt để phát hiện nghẽn
        self.last_position = None
        self.MAX_STUCK = MAX_STUCK       # Optimized: faster replan when stuck
        # Mới: cho hardware mode
        self.alive = False               # Robot có online không
        self.wait_robot = False          # Flow control: True = đang chờ BATCH_DONE
        self.last_rfid_event = None      # RFID event gần nhất

    def sync_sub_from_grid(self):
        self.sx = self.x * self.SUB
        self.sy = self.y * self.SUB

    def reset(self):
        self.x = 0; self.y = 0; self.heading = 'N'
        self.sx = 0; self.sy = 0
        self.step_backlog = 0
        self.path_queue.clear()
        self.state = "IDLE"
        self.target_node = None
        self.future_delivery_logical_id = None
        self.current_job_pickup = None
        self.wait_timer = 0
        self.paused = False
        self.manual_override = False
        self.delivered_count = 0
        self.has_planned = False
        self.stuck_counter = 0
        self.last_position = None
