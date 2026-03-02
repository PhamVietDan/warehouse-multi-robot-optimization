# ============================================================
# Serial Gateway Controller | Giao tiếp UART với ESP32 Gateway
# Kế thừa logic từ SEVER (1).py - RobotControllerApp
# ============================================================
import serial
import threading
import queue
import time
import re

from comms.protocol import parse_master_line


class SerialGateway:
    """Quản lý kết nối UART với ESP32 Gateway.
    
    Kế thừa trực tiếp logic từ SEVER (1).py:
    - toggle_connection: Kết nối/ngắt Serial
    - read_serial: Thread đọc data liên tục
    - pump_queues: Gửi batch lệnh cho từng robot
    - _parse_master_line: Parse tin nhắn từ Gateway
    - set_pose: Gửi vị trí đến robot
    """

    def __init__(self):
        self.ser = None
        self.connected = False
        self.reading = False
        # Queue an toàn cho Tkinter thread
        self.ui_q = queue.Queue()
        # Callbacks
        self._on_serial_log = None       # callback(msg: str)
        self._on_robot_online = None     # callback(target: str)
        self._on_step = None             # callback(target, heading, count)
        self._on_pos_update = None       # callback(target, x, y, heading)
        self._on_batch_done = None       # callback(target: str)
        self._on_turn = None             # callback(target, direction)
        self._on_rfid = None             # callback(target, uid: str)
        # Reference to robots dict (set by main_hardware)
        self.robots = None

    def set_robots(self, robots_dict):
        """Liên kết với dict robots từ FleetManager."""
        self.robots = robots_dict

    # ============================================================
    # KẾT NỐI / NGẮT SERIAL (giống toggle_connection trong SEVER)
    # ============================================================
    def connect(self, port, baudrate=115200):
        """Kết nối UART. Return True nếu thành công."""
        try:
            self.ser = serial.Serial(port, baudrate, timeout=1)
            self.connected = True
            self.reading = True
            threading.Thread(target=self._read_loop, daemon=True).start()
            self._log(f">>> CONNECTED to {port}")
            return True
        except Exception as e:
            self._log(f"ERR: Không kết nối được: {e}")
            return False

    def disconnect(self):
        """Ngắt kết nối."""
        self.connected = False
        self.reading = False
        if self.ser:
            try:
                self.ser.close()
            except:
                pass
        self._log(">>> DISCONNECTED")

    def is_connected(self):
        return self.connected and self.ser is not None

    # ============================================================
    # GỬI LỆNH (kế thừa từ pump_queues + _send_raw_line)
    # ============================================================
    def send_raw_line(self, cmd):
        """Gửi 1 dòng raw qua Serial. Giống _send_raw_line trong SEVER."""
        if not cmd:
            return
        if self.ser and self.connected:
            try:
                self.ser.write((cmd + "\n").encode())
                self._log(f">>> {cmd}")
            except Exception as e:
                self._log(f"ERR Send: {e}")
        else:
            self._log("ERR: CHƯA KẾT NỐI UART")

    def send_batch(self, robot_name, commands):
        """Gửi batch lệnh đến 1 robot. Giống pump_queues logic trong SEVER.
        
        Args:
            robot_name: VD "ESP1"
            commands: List lệnh VD ['F', 'F', 'L']
        """
        if not self.ser or not self.connected:
            self._log("ERR: CHƯA KẾT NỐI UART")
            return False
        if not commands:
            return False
        try:
            full_cmd = "".join(commands)
            msg = f"{robot_name} {full_cmd}\n"
            self.ser.write(msg.encode())
            self._log(f">>> SENT BATCH: {robot_name} {full_cmd}")
            return True
        except Exception as e:
            self._log(f"ERR Send: {e}")
            return False

    def pump_queues(self):
        """Gửi lệnh cho tất cả robot có path_queue. Giống pump_queues trong SEVER.
        
        Duyệt từng robot, xe nào rảnh (wait_robot=False) + có lệnh → gửi batch.
        """
        if not self.ser or not self.connected:
            return
        if not self.robots:
            return
        for name, r in self.robots.items():
            # Nếu robot đang bận chờ BATCH_DONE → bỏ qua
            if hasattr(r, 'wait_robot') and r.wait_robot:
                continue
            # Nếu có lệnh trong queue
            if r.path_queue:
                # Lọc bỏ WAIT (robot thật không hiểu WAIT)
                hw_cmds = [c for c in r.path_queue if c in ('F', 'L', 'R')]
                if hw_cmds:
                    success = self.send_batch(name, hw_cmds)
                    if success and hasattr(r, 'wait_robot'):
                        r.wait_robot = True  # Khóa robot, chờ BATCH_DONE
                r.path_queue.clear()

    def set_pose(self, target, x, y, heading):
        """Gửi lệnh set vị trí. Giống set_pose trong SEVER."""
        h = str(heading).strip().upper()
        if h not in ('N', 'E', 'S', 'W'):
            return
        self.send_raw_line(f"{target} POS,{x},{y},{h}")

    def set_pose_all(self, start_poses, delay_callback=None):
        """Gửi vị trí ban đầu tất cả robot. Giống set_pose_all_from_start.
        
        Args:
            start_poses: Dict {"ESP1": (x, y, h), ...}
            delay_callback: Hàm root.after(ms, func) để delay giữa các gói
        """
        if not self.is_connected():
            self._log("ERR: CHƯA KẾT NỐI UART")
            return
        items = list(start_poses.items())
        self._log(">>> SETMAP START (sending START_POSE...)")

        def send_i(i=0):
            if i >= len(items):
                self._log(">>> SETMAP DONE (START_POSE -> ALL)")
                return
            name, (x, y, h) = items[i]
            self.set_pose(name, x, y, h)
            if delay_callback:
                delay_callback(60, lambda: send_i(i + 1))
            else:
                time.sleep(0.06)
                send_i(i + 1)

        send_i(0)

    # ============================================================
    # ĐỌC SERIAL (kế thừa từ read_serial trong SEVER)
    # ============================================================
    def _read_loop(self):
        """Thread đọc Serial liên tục. Logic giống read_serial trong SEVER."""
        try:
            self.ser.timeout = 0.05
        except:
            pass

        while self.reading and self.connected:
            try:
                line = self.ser.readline()
                if not line:
                    continue

                s = line.decode("ascii", errors="replace").strip("\r\n")
                if not s:
                    continue

                # Log raw data
                self._log(s)

                target, payload = parse_master_line(s)

                # Auto-detect robot online
                if target.startswith("ESP") and self.robots is not None:
                    if target in self.robots:
                        r = self.robots[target]
                        if hasattr(r, 'alive') and not r.alive:
                            r.alive = True
                            self._log(f">>> PHÁT HIỆN KẾT NỐI: {target} (ONLINE)")
                            if self._on_robot_online:
                                self._on_robot_online(target)

                if not target.startswith("ESP"):
                    continue
                if self.robots and target not in self.robots:
                    continue

                # --- XỬ LÝ GÓI TIN (giống SEVER) ---
                # STEP: robot báo đã di chuyển
                if payload.startswith("STEP"):
                    parts = payload.split(",")
                    if len(parts) >= 2:
                        h = parts[1].strip()
                        if h in ('N', 'E', 'S', 'W'):
                            cnt = 1
                            if len(parts) >= 3:
                                try: cnt = max(1, min(50, int(parts[2])))
                                except: cnt = 1
                            # Heading/position update giờ do callback xử lý
                            # (tránh double-update khi dashboard có _on_hw_step)
                            if not self._on_step:
                                # Fallback: nếu không có callback, update trực tiếp
                                if self.robots and target in self.robots:
                                    r = self.robots[target]
                                    r.heading = h
                                    r.step_backlog += cnt
                            else:
                                self._on_step(target, h, cnt)

                # POS/POSACK: robot xác nhận vị trí
                elif payload.startswith("POS") or payload.startswith("POSACK"):
                    try:
                        _, xs, ys, hs = payload.split(",")
                        x, y = int(xs), int(ys)
                        hs = hs.strip()
                        if hs in ('N', 'E', 'S', 'W'):
                            if self.robots and target in self.robots:
                                r = self.robots[target]
                                r.x, r.y, r.heading = x, y, hs
                                r.sync_sub_from_grid()
                            if self._on_pos_update:
                                self._on_pos_update(target, x, y, hs)
                    except:
                        pass

                # TURN: robot báo đã xoay
                elif payload.startswith("TURN"):
                    parts = payload.split(",", 1)
                    d = 'R'
                    if len(parts) == 2:
                        d = parts[1].strip().upper()
                        if d not in ('L', 'R'): d = 'R'
                    LEFT = {'N': 'W', 'W': 'S', 'S': 'E', 'E': 'N'}
                    RIGHT = {'N': 'E', 'E': 'S', 'S': 'W', 'W': 'N'}
                    if self.robots and target in self.robots:
                        r = self.robots[target]
                        if d == 'L':
                            r.heading = LEFT.get(r.heading, r.heading)
                        else:
                            r.heading = RIGHT.get(r.heading, r.heading)
                    if self._on_turn:
                        self._on_turn(target, d)

                # BATCH_DONE: robot hoàn thành toàn bộ batch lệnh
                elif payload.startswith("BATCH_DONE"):
                    self._log(f">>> {target} ĐÃ CHẠY XONG HẾT LỆNH!")
                    if self.robots and target in self.robots:
                        r = self.robots[target]
                        if hasattr(r, 'wait_robot'):
                            r.wait_robot = False
                    if self._on_batch_done:
                        self._on_batch_done(target)
                    # Kiểm tra xem còn lệnh nào cần gửi không
                    self.pump_queues()

                # RFID / HT: robot quét được thẻ RFID
                # ESP32 gửi dạng: @1,RFID,<UID> hoặc @1,HT,<UID>
                elif payload.startswith("RFID") or payload.startswith("HT"):
                    parts = payload.split(",", 1)
                    uid = ""
                    if len(parts) >= 2:
                        uid = parts[1].strip().replace(" ", "").upper()
                    self._log(f">>> {target} RFID SCANNED: {uid}")
                    if self._on_rfid:
                        self._on_rfid(target, uid)

                # DONE: xong 1 bước nhỏ (KHÔNG mở khóa)
                elif payload.startswith("DONE"):
                    pass

            except:
                time.sleep(0.02)

    # ============================================================
    # INTERNAL LOG
    # ============================================================
    def _log(self, msg):
        """Đẩy log vào queue an toàn cho Tkinter."""
        try:
            self.ui_q.put_nowait(msg)
        except:
            pass
        if self._on_serial_log:
            try:
                self._on_serial_log(msg)
            except:
                pass
