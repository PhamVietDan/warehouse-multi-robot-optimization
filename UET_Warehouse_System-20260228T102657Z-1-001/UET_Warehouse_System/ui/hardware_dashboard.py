# ============================================================
# UET | NCKH 2026 | Hardware Dashboard
# Giao diện giám sát phần cứng — kế thừa UI mô phỏng
# + UART connection panel + Serial Monitor
# ============================================================
import tkinter as tk
from tkinter import ttk, messagebox
import queue
import re
import time

from config.settings import (
    GRID_N, SUB, PICKUP_NODES, CONFIG_DELIVERY_LOCATIONS,
    DELIVERY_NODES, REMOVE_NODES, BLUE_NODES,
    SKIP_COLS, SKIP_ROWS,
    LOGIC_INTERVAL_MS, ANIM_MS, UI_REFRESH_MS,
    MAX_ROBOTS, TEST_DURATION,
    RFID_DELIVERY_MAP,
)


class HardwareDashboard:
    """Giao diện Tkinter cho chế độ phần cứng.
    
    Giống WarehouseDashboard (simulation) + thêm:
    - Panel UART kết nối Gateway
    - Serial Monitor
    - Điều khiển thủ công gửi lệnh qua UART
    - Bảng tọa độ robot với trạng thái Online/Offline
    """

    def __init__(self, root, fleet_manager, gateway):
        self.root = root
        self.fleet = fleet_manager
        self.gateway = gateway
        self.root.title("HỆ THỐNG ROBOT KHO HÀNG THỰC TẾ | UET NCKH2026")
        self.root.state("zoomed")
        self.grid_n = GRID_N
        self.SUB = SUB
        self.cell = 55
        self.MARGIN = 40

        # Cấu hình vị trí ban đầu robot thật
        self.START_POSE = {
            "ESP1": (0, 0, 'N'),
            "ESP2": (2, 9, 'S'),
            "ESP3": (6, 0, 'N'),
            "ESP4": (8, 9, 'S'),
            "ESP5": (9, 0, 'N'),
        }

        # Pool màu robot
        self.COLOR_POOL = ["green", "red", "orange", "purple", "cyan",
                           "magenta", "brown", "darkgreen"]

        # === RFID tracking state ===
        # Ô nào đã giao hàng (cell_id → True) + flash toggle
        self.rfid_delivered_cells = {}    # cell_id → {"coord": (x,y), "flash": True}
        self.rfid_flash_on = True         # Toggle cho hiệu ứng chớp đỏ
        self.rfid_flash_count = {}        # cell_id → số lần chớp còn lại

        # ================= GUI LAYOUT =================
        self.main_pane = tk.PanedWindow(root, orient=tk.HORIZONTAL, sashwidth=6)
        self.main_pane.pack(fill="both", expand=True)

        # ================= LEFT: MAP =================
        self.frame_map = tk.Frame(self.main_pane, bg="white")
        self.main_pane.add(self.frame_map, minsize=500)

        size = (self.grid_n - 1) * self.cell + 2 * self.MARGIN
        self.canvas = tk.Canvas(self.frame_map, width=size, height=size, bg="white")
        self.canvas.pack(padx=10, pady=10)

        # Bảng giám sát trạm nhận hàng
        self.frame_pickup_info = tk.LabelFrame(self.frame_map, text="Giám sát Trạm Nhận Hàng",
                                                bg="white", padx=5, pady=5)
        self.frame_pickup_info.pack(fill="x", padx=10, pady=(0, 10))
        pk_cols = ("id", "coord", "status", "delivery_coord", "assigned_robot")
        self.tree_pickup = ttk.Treeview(self.frame_pickup_info, columns=pk_cols,
                                         show="headings", height=8)
        self.tree_pickup.heading("id", text="ID Trạm")
        self.tree_pickup.heading("coord", text="Tọa độ")
        self.tree_pickup.heading("status", text="Đơn hàng")
        self.tree_pickup.heading("delivery_coord", text="Tọa độ trả")
        self.tree_pickup.heading("assigned_robot", text="Robot")
        for col in pk_cols:
            self.tree_pickup.column(col, width=80, anchor="center")
        self.tree_pickup.pack(fill="both", expand=True)

        # Bảng giám sát RFID giao hàng
        self.frame_rfid_info = tk.LabelFrame(self.frame_map, text="RFID — Trạng thái Ô giao hàng",
                                              bg="white", padx=5, pady=5)
        self.frame_rfid_info.pack(fill="x", padx=10, pady=(0, 10))
        rfid_cols = ("cell", "coord", "uid", "status", "count", "last_robot")
        self.tree_rfid = ttk.Treeview(self.frame_rfid_info, columns=rfid_cols,
                                       show="headings", height=4)
        self.tree_rfid.heading("cell", text="Ô")
        self.tree_rfid.heading("coord", text="Tọa độ")
        self.tree_rfid.heading("uid", text="RFID UID")
        self.tree_rfid.heading("status", text="Trạng thái")
        self.tree_rfid.heading("count", text="Số lần giao")
        self.tree_rfid.heading("last_robot", text="Robot gần nhất")
        for col in rfid_cols:
            self.tree_rfid.column(col, width=90, anchor="center")
        self.tree_rfid.column("uid", width=110)
        self.tree_rfid.pack(fill="both", expand=True)
        self.lbl_rfid_total = tk.Label(self.frame_rfid_info,
                                        text="Tổng giao RFID: 0",
                                        font=("Arial", 10, "bold"), fg="#D32F2F", bg="white")
        self.lbl_rfid_total.pack(anchor="w", padx=5, pady=(3, 0))

        # ================= RIGHT: CONTROL PANEL =================
        self.frame_right = tk.Frame(self.main_pane)
        self.main_pane.add(self.frame_right, minsize=420)

        tk.Label(self.frame_right, text="ĐIỀU KHIỂN ROBOT THỰC TẾ | NCKH2026",
                 font=("Arial", 13, "bold"), fg="#333").pack(pady=5)
        self.lbl_timer = tk.Label(self.frame_right, text="Thời gian: 00:00:00",
                                   font=("Arial", 11, "bold"), fg="red")
        self.lbl_timer.pack(pady=2)

        # ============================================================
        # UART CONNECTION PANEL
        # ============================================================
        frame_uart = tk.LabelFrame(self.frame_right, text="UART Gateway", padx=10, pady=6)
        frame_uart.pack(fill="x", padx=10, pady=5)

        tk.Label(frame_uart, text="COM:").pack(side="left")
        self.entry_port = tk.Entry(frame_uart, width=10)
        self.entry_port.insert(0, "COM10")
        self.entry_port.pack(side="left", padx=5)

        self.btn_connect = tk.Button(frame_uart, text="Kết nối", bg="#4CAF50", fg="white",
                                      command=self.toggle_connection)
        self.btn_connect.pack(side="left", padx=5)

        tk.Button(frame_uart, text="Set Map", bg="#2196F3", fg="white",
                  command=self._set_pose_all).pack(side="left", padx=5)
        tk.Button(frame_uart, text="Reset Map", bg="#ff9800",
                  command=self.reset_map).pack(side="left", padx=5)

        # ============================================================
        # CHỌN ROBOT THAM GIA (theo tên)
        # ============================================================
        frame_select = tk.LabelFrame(self.frame_right, text="Chọn Robot tham gia", padx=5, pady=3)
        frame_select.pack(fill="x", padx=10, pady=3)
        self.robot_select_vars = {}
        for name in ["ESP1", "ESP2", "ESP3", "ESP4", "ESP5"]:
            var = tk.IntVar(value=1)  # Mặc định tất cả đều chọn
            self.robot_select_vars[name] = var
            tk.Checkbutton(frame_select, text=name, variable=var,
                           command=self._on_robot_selection_changed).pack(side="left", padx=5)

        # ============================================================
        # SYSTEM CONTROL
        # ============================================================
        frame_sys = tk.LabelFrame(self.frame_right, text="Hệ thống", padx=5, pady=5)
        frame_sys.pack(fill="x", padx=10, pady=5)

        f_btn = tk.Frame(frame_sys)
        f_btn.pack(fill="x", pady=3)
        self.btn_start = tk.Button(f_btn, text="KHỞI ĐỘNG HỆ THỐNG", bg="#4CAF50", fg="white",
                                    font=("Arial", 10, "bold"), height=2,
                                    command=self.toggle_system_start)
        self.btn_start.pack(side="left", fill="x", expand=True, padx=(0, 5))
        self.btn_test = tk.Button(f_btn, text="TEST 60s", bg="#FF9800", fg="white",
                                   font=("Arial", 10, "bold"), height=2,
                                   command=self.start_benchmark)
        self.btn_test.pack(side="left", padx=0)

        # ============================================================
        # ROBOT STATUS PANEL
        # ============================================================
        self.frame_pos = tk.LabelFrame(self.frame_right, text="Trạng thái Robot", padx=5, pady=5)
        self.frame_pos.pack(fill="both", expand=True, padx=10, pady=3)
        self.lbl_total = tk.Label(self.frame_pos, text="Tổng hàng đã giao: 0",
                                   font=("Arial", 11, "bold"), fg="blue")
        self.lbl_total.pack(anchor="w", padx=5, pady=(0, 3))

        columns = ("name", "online", "status", "pos", "target", "count")
        self.tree_monitor = ttk.Treeview(self.frame_pos, columns=columns,
                                          show="headings", height=8)
        self.tree_monitor.heading("name", text="Robot")
        self.tree_monitor.heading("online", text="Kết nối")
        self.tree_monitor.heading("status", text="Trạng thái")
        self.tree_monitor.heading("pos", text="Vị trí")
        self.tree_monitor.heading("target", text="Đích đến")
        self.tree_monitor.heading("count", text="Đã giao")
        self.tree_monitor.column("name", width=50, anchor="center")
        self.tree_monitor.column("online", width=50, anchor="center")
        self.tree_monitor.column("status", width=90, anchor="w")
        self.tree_monitor.column("pos", width=60, anchor="center")
        self.tree_monitor.column("target", width=60, anchor="center")
        self.tree_monitor.column("count", width=50, anchor="center")
        sb = ttk.Scrollbar(self.frame_pos, orient=tk.VERTICAL, command=self.tree_monitor.yview)
        self.tree_monitor.configure(yscroll=sb.set)
        sb.pack(side="right", fill="y")
        self.tree_monitor.pack(fill="both", expand=True)

        # ============================================================
        # MANUAL CONTROL — GO TO (Giống SEVER)
        # ============================================================
        self.frame_goto = tk.LabelFrame(self.frame_right,
                                         text="Điều khiển thủ công (Chọn xe cần chạy)",
                                         padx=5, pady=5)
        self.frame_goto.pack(fill="x", padx=10, pady=3)

        self.goto_entries = {}
        self.chk_vars = {}
        target_list = ["ESP1", "ESP2", "ESP3", "ESP4", "ESP5"]
        default_pos = {"ESP1": "(0,3)", "ESP2": "(10,10)", "ESP3": "(6,0)",
                        "ESP4": "(8,9)", "ESP5": "(9,0)"}

        self.frame_goto.columnconfigure(0, weight=1)
        self.frame_goto.columnconfigure(1, weight=1)
        self.frame_goto.columnconfigure(2, weight=1)

        for i, name in enumerate(target_list):
            row, col = i // 3, i % 3
            f = tk.Frame(self.frame_goto)
            f.grid(row=row, column=col, padx=1, pady=2, sticky="w")

            var = tk.IntVar(value=1)
            self.chk_vars[name] = var
            tk.Checkbutton(f, variable=var).pack(side="left", padx=0)
            lbl_color = self.COLOR_POOL[i % len(self.COLOR_POOL)]
            tk.Label(f, text=name, fg=lbl_color,
                     font=("Arial", 8, "bold")).pack(side="left")
            entry = tk.Entry(f, width=7)
            entry.insert(0, default_pos.get(name, "(0,0)"))
            entry.pack(side="left", padx=2)
            self.goto_entries[name] = entry
            tk.Button(f, text="Go", width=2, bg="#f0f0f0", font=("Arial", 8),
                      command=lambda n=name: self._send_goto(n)).pack(side="left")

        final_row = (len(target_list) // 3) + 1
        tk.Button(self.frame_goto, text=" GO SELECTED ", bg="#E2AA11", fg="white",
                  font=("Arial", 9, "bold"),
                  command=self._send_goto_all).grid(row=final_row, column=0,
                                                     columnspan=3, sticky="ew", pady=(3, 0))

        # ============================================================
        # SERIAL MONITOR
        # ============================================================
        frame_serial = tk.LabelFrame(self.frame_right, text="Serial Monitor")
        frame_serial.pack(fill="both", expand=True, padx=10, pady=3)

        self.serial_text = tk.Text(frame_serial, bg="black", fg="#00ff66",
                                    insertbackground="white", height=8)
        self.serial_text.pack(fill="both", expand=True)
        self.serial_text.config(state="disabled")

        f_serial_btn = tk.Frame(frame_serial)
        f_serial_btn.pack(fill="x")
        tk.Button(f_serial_btn, text="Xóa Serial",
                  command=self._clear_serial).pack(side="right", padx=3, pady=2)

        # ============================================================
        # KHỞI TẠO ROBOTS THẬT
        # ============================================================
        self._init_hardware_robots()

        # ============================================================
        # CALLBACKS: SNAP POSITION NGAY KHI NHẬN FEEDBACK (không delay)
        # ============================================================
        self.gateway._on_pos_update = self._on_hw_pos_update
        self.gateway._on_turn = self._on_hw_turn
        self.gateway._on_step = self._on_hw_step
        self.gateway._on_batch_done = lambda t: None  # pump_queues called internally
        self.gateway._on_rfid = self._on_hw_rfid

        # ============================================================
        # TIMERS
        # ============================================================
        self.draw_map()
        self.draw_robot()

        self.ANIM_MS = ANIM_MS
        self.LOGIC_MS = LOGIC_INTERVAL_MS
        self.root.after(self.ANIM_MS, self._anim_tick)
        self.root.after(self.LOGIC_MS, self._logic_tick_wrapper)
        self.root.after(UI_REFRESH_MS, self._refresh_status)
        self.root.after(20, self._ui_pump)
        self.root.after(400, self._rfid_flash_tick)   # Timer chớp đỏ RFID

    # ============================================================
    # INIT ROBOTS (vị trí ban đầu theo START_POSE)
    # ============================================================
    def _init_hardware_robots(self):
        """Khởi tạo 5 robot với vị trí START_POSE (không random như simulation)."""
        from core.robot_state import RobotState
        self.fleet.robots.clear()
        self.fleet.tick_counter = 0
        self.fleet.coop_manager.reservations.clear()

        for i, (name, (x, y, h)) in enumerate(self.START_POSE.items()):
            color = "#1D86FE"  # Giống mô phỏng — 1 màu cho tất cả
            r = RobotState(name, color, sub=self.SUB)
            r.x, r.y, r.heading = x, y, h
            r.sync_sub_from_grid()
            # Thêm field wait_robot cho hardware flow control
            r.wait_robot = False
            r.alive = False  # Chờ tín hiệu từ robot thật
            self.fleet.coop_manager.reservations[(x, y, 0)] = name
            self.fleet.robots[name] = r

        # Liên kết gateway với robots dict
        self.gateway.set_robots(self.fleet.robots)

    def _on_robot_selection_changed(self):
        """Callback khi user tick/untick robot. Pause robot bị bỏ chọn."""
        for name, var in self.robot_select_vars.items():
            if name in self.fleet.robots:
                r = self.fleet.robots[name]
                if var.get() == 0:
                    # Robot bị bỏ chọn → pause, không tham gia hệ thống
                    r.paused = True
                else:
                    r.paused = False
        self.draw_robot()

    # ============================================================
    # UART CONNECTION (giống toggle_connection trong SEVER)
    # ============================================================
    def toggle_connection(self):
        if not self.gateway.is_connected():
            port = self.entry_port.get().strip()
            if self.gateway.connect(port):
                self.btn_connect.config(text="Ngắt", bg="#f44336")
                # Tự động set pose sau 500ms
                self.root.after(500, self._set_pose_all)
            else:
                messagebox.showerror("Lỗi", f"Không kết nối được {port}")
        else:
            self.gateway.disconnect()
            self.btn_connect.config(text="Kết nối", bg="#4CAF50")

    def _set_pose_all(self):
        self.gateway.set_pose_all(self.START_POSE, delay_callback=self.root.after)

    # ============================================================
    # SYSTEM CONTROL
    # ============================================================
    def toggle_system_start(self):
        # === GUARD: Phải kết nối UART mới cho chạy ===
        if not self.gateway.is_connected():
            messagebox.showwarning("Chưa kết nối", "Phải kết nối UART Gateway trước khi chạy!\nRobot thật cần đồng bộ realtime.")
            return
        self.fleet.is_benchmark_mode = False
        self.fleet.is_running = not self.fleet.is_running
        if self.fleet.is_running:
            self.fleet.start_time = time.time()
            self.btn_start.config(text="ĐANG CHẠY (NHẤN ĐỂ DỪNG)", bg="#F44336")
        else:
            self.lbl_timer.config(text="Thời gian: 00:00:00")
            self.btn_start.config(text="KHỞI ĐỘNG HỆ THỐNG", bg="#4CAF50")

    def start_benchmark(self):
        # === GUARD: Phải kết nối UART mới cho chạy ===
        if not self.gateway.is_connected():
            messagebox.showwarning("Chưa kết nối", "Phải kết nối UART Gateway trước khi test!")
            return
        for r in self.fleet.robots.values():
            r.delivered_count = 0
        self.fleet.is_benchmark_mode = True
        self.fleet.start_time = time.time()
        self.fleet.is_running = True
        self.btn_start.config(text="ĐANG TEST 60s...", bg="#FF9800")

    # ============================================================
    # LOGIC TICK (gọi FleetManager + pump lệnh qua UART)
    # ============================================================
    def _logic_tick_wrapper(self):
        result = self.fleet.update_tick()
        if result:
            if result['event'] == 'benchmark_done':
                self.btn_start.config(text="KHỞI ĐỘNG HỆ THỐNG", bg="#4CAF50")
                self.lbl_timer.config(text="KẾT THÚC TEST 60s!")
                messagebox.showinfo("KẾT QUẢ", f"TỔNG HÀNG: {result['total_delivered']}")
            elif result['event'] == 'benchmark_tick':
                self.lbl_timer.config(text=f"Còn: {int(result['remaining'])}s / {TEST_DURATION}s")
            elif result['event'] == 'normal_tick':
                e = result['elapsed']
                self.lbl_timer.config(text=f"Thời gian: {int(e//3600):02d}:"
                                           f"{int((e%3600)//60):02d}:{int(e%60):02d}")

        # Sau mỗi logic tick, pump lệnh ra UART
        if self.gateway.is_connected():
            self.gateway.pump_queues()

        self.root.after(self.LOGIC_MS, self._logic_tick_wrapper)

    # ============================================================
    # UI PUMP (đọc log từ gateway.ui_q → hiển thị Serial Monitor)
    # ============================================================
    def _ui_pump(self):
        try:
            while True:
                msg = self.gateway.ui_q.get_nowait()
                self.serial_text.config(state="normal")
                self.serial_text.insert(tk.END, msg + "\n")
                self.serial_text.see(tk.END)
                self.serial_text.config(state="disabled")
        except queue.Empty:
            pass
        self.root.after(20, self._ui_pump)

    def _clear_serial(self):
        self.serial_text.config(state="normal")
        self.serial_text.delete("1.0", tk.END)
        self.serial_text.config(state="disabled")

    # ============================================================
    # MANUAL CONTROL — GO TO (giống SEVER)
    # ============================================================
    def _send_goto(self, target_name):
        # === GUARD: Phải kết nối UART ===
        if not self.gateway.is_connected():
            messagebox.showwarning("Chưa kết nối", "Phải kết nối UART Gateway trước!")
            return
        if target_name not in self.goto_entries:
            return
        # === Check robot alive (giống multi_robot_server) ===
        if target_name in self.fleet.robots and not self.fleet.robots[target_name].alive:
            self.gateway._log(f"BỎ QUA {target_name}: Chưa online (OFFLINE).")
            return
        xy_str = self.goto_entries[target_name].get()
        m = re.search(r'\(?\s*(-?\d+)\s*,\s*(-?\d+)\s*\)?', xy_str)
        if not m:
            self.gateway._log(f"ERR: sai định dạng tọa độ '{xy_str}'")
            return

        x, y = int(m.group(1)), int(m.group(2))
        if target_name not in self.fleet.robots:
            self.gateway._log(f"ERR: {target_name} không tồn tại")
            return

        r = self.fleet.robots[target_name]
        path = self.fleet.find_path_old((r.x, r.y, r.heading), (x, y))
        if not path:
            self.gateway._log(f"{target_name}: KHÔNG TÌM THẤY ĐƯỜNG ĐẾN ({x},{y})")
            return

        r.path_queue = path
        r.wait_robot = False
        self.gateway._log(f"PLAN: {target_name} -> ({x},{y}) [{len(path)} bước]")
        self.gateway.pump_queues()

    def _send_goto_all(self):
        # === GUARD: Phải kết nối UART ===
        if not self.gateway.is_connected():
            messagebox.showwarning("Chưa kết nối", "Phải kết nối UART Gateway trước!")
            return
        count = 0
        self.gateway._log(">>> ĐANG TÍNH TOÁN PATH CHO CÁC XE ĐÃ CHỌN...")
        for name in ["ESP1", "ESP2", "ESP3", "ESP4", "ESP5"]:
            if name in self.chk_vars and self.chk_vars[name].get() == 0:
                continue
            if name in self.goto_entries:
                xy_str = self.goto_entries[name].get()
                m = re.search(r'\(?\s*(-?\d+)\s*,\s*(-?\d+)\s*\)?', xy_str)
                if not m:
                    continue
                x, y = int(m.group(1)), int(m.group(2))
                if name not in self.fleet.robots:
                    continue
                r = self.fleet.robots[name]
                path = self.fleet.find_path_old((r.x, r.y, r.heading), (x, y))
                if path:
                    r.path_queue = path
                    r.wait_robot = False
                    count += 1
        if count > 0:
            self.gateway._log(f">>> KÍCH HOẠT {count} ROBOT!")
            self.gateway.pump_queues()
        else:
            self.gateway._log(">>> KHÔNG CÓ XE NÀO ĐƯỢC CHỌN HOẶC LỖI.")


    # ============================================================
    # RESET MAP
    # ============================================================
    def reset_map(self):
        for name, (x, y, h) in self.START_POSE.items():
            if name in self.fleet.robots:
                r = self.fleet.robots[name]
                r.reset()
                r.x, r.y, r.heading = x, y, h
                r.wait_robot = False
                r.sync_sub_from_grid()

        self.draw_map()
        self.draw_robot()

        # Nếu đang kết nối, gửi vị trí xuống robot thật
        if self.gateway.is_connected():
            self.root.after(200, self._set_pose_all)

    # ============================================================
    # DRAWING (giống WarehouseDashboard)
    # ============================================================
    def draw_map(self):
        self.canvas.delete("all")
        off = self.MARGIN
        traffic = self.fleet.traffic_mgr
        for x in range(self.grid_n):
            if x not in SKIP_COLS:
                cx = off + x * self.cell
                self.canvas.create_line(cx, off, cx, off + (self.grid_n - 1) * self.cell,
                                         width=2, fill="#e0e0e0")
                if x in traffic.COLS_DOWN:
                    self.canvas.create_text(cx, off - 15, text="↓", fill="gray",
                                             font=("Arial", 10, "bold"))
                elif x in traffic.COLS_UP:
                    self.canvas.create_text(cx, off + (self.grid_n - 1) * self.cell + 15,
                                             text="↑", fill="gray", font=("Arial", 10, "bold"))
        for y in range(self.grid_n):
            if y not in SKIP_ROWS:
                cy = off + (self.grid_n - 1 - y) * self.cell
                self.canvas.create_line(off, cy, off + (self.grid_n - 1) * self.cell, cy,
                                         width=2, fill="#e0e0e0")
                if y in traffic.ROWS_LEFT:
                    self.canvas.create_text(off + (self.grid_n - 1) * self.cell + 15, cy,
                                             text="←", fill="gray", font=("Arial", 10, "bold"))
                elif y in traffic.ROWS_RIGHT:
                    self.canvas.create_text(off - 15, cy, text="→", fill="gray",
                                             font=("Arial", 10, "bold"))
        rr = 7
        # Tập hợp các ô RFID đang chớp đỏ hoặc đã giao
        rfid_flash_coords = set()
        rfid_delivered_coords = set()
        for cell_id, info in self.rfid_delivered_cells.items():
            coord = info["coord"]
            if info["flash"]:
                rfid_flash_coords.add(coord)
            else:
                rfid_delivered_coords.add(coord)

        # Ánh xạ tọa độ → số ô RFID (1-36) để hiển thị trên map
        coord_to_cell = {}
        for uid, info in RFID_DELIVERY_MAP.items():
            coord_to_cell[info["coord"]] = info["cell"]

        for l_id, coords in CONFIG_DELIVERY_LOCATIONS.items():
            for (dx, dy) in coords:
                cx = off + dx * self.cell
                cy = off + (self.grid_n - 1 - dy) * self.cell
                # Số ô RFID (1-36) thay vì số địa chỉ (1-12)
                cell_num = coord_to_cell.get((dx, dy), l_id)

                # Kiểm tra ô này có phải RFID delivery cell không
                if (dx, dy) in rfid_flash_coords:
                    # Đang chớp → xen kẽ đỏ / trắng
                    if self.rfid_flash_on:
                        fill_color = "#FF1744"
                        outline_color = "#D50000"
                        text_color = "white"
                    else:
                        fill_color = "white"
                        outline_color = "#FF1744"
                        text_color = "#FF1744"
                    self.canvas.create_rectangle(cx - 9, cy - 9, cx + 9, cy + 9,
                                                  fill=fill_color, outline=outline_color, width=3)
                    self.canvas.create_text(cx, cy, text=str(cell_num),
                                             font=("Arial", 7, "bold"), fill=text_color)
                elif (dx, dy) in rfid_delivered_coords:
                    # Đã giao (hết chớp) → đỏ cố định
                    self.canvas.create_rectangle(cx - 9, cy - 9, cx + 9, cy + 9,
                                                  fill="#FF1744", outline="#D50000", width=2)
                    self.canvas.create_text(cx, cy, text="✓",
                                             font=("Arial", 8, "bold"), fill="white")
                else:
                    # Ô bình thường
                    self.canvas.create_rectangle(cx - 7, cy - 7, cx + 7, cy + 7,
                                                  fill="#AAF4B7", outline="green", width=1)
                    self.canvas.create_text(cx, cy, text=str(cell_num),
                                             font=("Arial", 7), fill="black")
        for x in range(self.grid_n):
            for y in range(self.grid_n):
                cx = off + x * self.cell
                cy = off + (self.grid_n - 1 - y) * self.cell
                if (x, y) in BLUE_NODES:
                    self.canvas.create_oval(cx - rr, cy - rr, cx + rr, cy + rr,
                                             fill="#4287f5", outline="blue")
                    try:
                        idx = PICKUP_NODES.index((x, y)) + 1
                        self.canvas.create_text(cx, cy, text=str(idx),
                                                 font=("Arial", 7, "bold"), fill="white")
                    except:
                        pass
                elif (x, y) not in DELIVERY_NODES and (x not in SKIP_COLS or y not in SKIP_ROWS):
                    self.canvas.create_oval(cx - 2, cy - 2, cx + 2, cy + 2, fill="black")

    def draw_robot(self):
        """Vẽ robot — giống simulation. CHỈ hiển thị robot ONLINE + ĐƯỢC CHỌN."""
        for name in self.fleet.robots:
            self.canvas.delete(f"robot_{name}")
        for name, r in self.fleet.robots.items():
            # === Chỉ vẽ robot alive + được chọn ===
            if not r.alive:
                continue
            if name in self.robot_select_vars and self.robot_select_vars[name].get() == 0:
                continue

            x = r.sx / r.SUB
            y = r.sy / r.SUB
            cx = self.MARGIN + x * self.cell
            cy = self.MARGIN + (self.grid_n - 1 - y) * self.cell
            size = 14
            outline_w = 0; outline_color = "black"; stipple = ""
            if r.state in ["PICKING", "DROPPING"]:
                outline_color = "#41CEC4"
                outline_w = 4
            if r.paused:
                outline_w = 4; stipple = "gray50"; outline_color = "black"
            # Vẽ thân Robot
            self.canvas.create_rectangle(cx - size, cy - size, cx + size, cy + size,
                                          fill=r.color, outline=outline_color,
                                          width=outline_w, stipple=stipple,
                                          tags=f"robot_{name}")
            if r.state in ["TO_DELIVERY", "DROPPING"]:
                cargo_sz = 9
                self.canvas.create_rectangle(cx - cargo_sz, cy - cargo_sz,
                                              cx + cargo_sz, cy + cargo_sz,
                                              fill="#E1720A", outline="black",
                                              tags=f"robot_{name}")
            short_name = name.replace("ESP", "")
            self.canvas.create_text(cx, cy, text=short_name, font=("Arial", 9, "bold"),
                                     fill="white", tags=f"robot_{name}")
            tri = {
                'N': [cx, cy-size-8, cx-6, cy-size, cx+6, cy-size],
                'E': [cx+size+8, cy, cx+size, cy-6, cx+size, cy+6],
                'S': [cx, cy+size+8, cx-6, cy+size, cx+6, cy+size],
                'W': [cx-size-8, cy, cx-size, cy-6, cx-size, cy+6],
            }
            self.canvas.create_polygon(tri[r.heading], fill="blue", outline="blue",
                                        tags=f"robot_{name}")

    # ============================================================
    # HARDWARE CALLBACKS: CẬP NHẬT VỊ TRÍ NGAY LẬP TỨC (không animation delay)
    # Giống SEVER (1).py: feedback từ robot → cập nhật → vẽ lại
    # ============================================================
    def _on_hw_step(self, target, heading, count):
        """STEP từ robot thật — tích lũy sub-steps, di chuyển khi đủ 1 ô."""
        if target not in self.fleet.robots:
            return
        r = self.fleet.robots[target]
        old_x, old_y = r.x, r.y
        old_cnt = r.step_cnt
        r.heading = heading
        HW_SUB = 6
        dx, dy = {'N': (0, 1), 'E': (1, 0), 'S': (0, -1), 'W': (-1, 0)}[heading]
        
        # Tích lũy sub-steps
        r.step_cnt += count
        moved = False
        while r.step_cnt >= HW_SUB:
            r.step_cnt -= HW_SUB
            r.x += dx
            r.y += dy
            moved = True
        r.sync_sub_from_grid()
        
        # DEBUG: log mỗi STEP trong Serial Monitor
        self.gateway._log(
            f"[HW_STEP] {target} h={heading} cnt={count} "
            f"step_cnt:{old_cnt}->{r.step_cnt} "
            f"pos:({old_x},{old_y})->({r.x},{r.y}) "
            f"{'MOVED!' if moved else ''}"
        )
        self.root.after(0, self.draw_robot)

    def _on_hw_pos_update(self, target, x, y, heading):
        """POS/POSACK: đồng bộ vị trí chính xác từ robot."""
        if target not in self.fleet.robots:
            return
        r = self.fleet.robots[target]
        r.x, r.y, r.heading = x, y, heading
        r.sync_sub_from_grid()
        r.step_backlog = 0  # Reset animation
        r.step_cnt = 0
        self.root.after(0, self.draw_robot)

    def _on_hw_turn(self, target, direction):
        """Đổi hướng ngay lập tức."""
        self.root.after(0, self.draw_robot)

    # ============================================================
    # RFID CALLBACK — Khi robot quét thẻ RFID tại ô giao hàng
    # ============================================================
    def _on_hw_rfid(self, target, uid):
        """Xử lý RFID scan: đánh dấu đã giao + kích hoạt chớp đỏ."""
        record = self.fleet.handle_rfid_scan(target, uid)
        if record:
            cell_id = record["cell"]
            coord = record["coord"]
            # Đánh dấu ô đã giao → bắt đầu chớp đỏ
            self.rfid_delivered_cells[cell_id] = {"coord": coord, "flash": True}
            self.rfid_flash_count[cell_id] = 6  # Chớp 3 lần (6 toggle = 3 on/off)
            self.gateway._log(
                f">>> ĐÃ GIAO HÀNG! {target} tại {record['name']} {coord} "
                f"(lần {record['count']})"
            )
        else:
            self.gateway._log(f">>> RFID KHÔNG NHẬN DIỆN: {uid} từ {target}")
        # Vẽ lại map + cập nhật bảng RFID
        self.root.after(0, self.draw_map)
        self.root.after(0, self.draw_robot)
        self.root.after(0, self._refresh_rfid_table)

    def _rfid_flash_tick(self):
        """Timer chớp đỏ cho các ô đã giao hàng qua RFID."""
        self.rfid_flash_on = not self.rfid_flash_on
        need_redraw = False
        expired = []
        for cell_id, info in self.rfid_delivered_cells.items():
            if info["flash"]:
                need_redraw = True
                # Giảm bộ đếm chớp
                if cell_id in self.rfid_flash_count:
                    self.rfid_flash_count[cell_id] -= 1
                    if self.rfid_flash_count[cell_id] <= 0:
                        expired.append(cell_id)
        # Ô hết chớp → trở lại bình thường (xanh)
        for cell_id in expired:
            del self.rfid_delivered_cells[cell_id]
            del self.rfid_flash_count[cell_id]
        if need_redraw:
            self.draw_map()
            self.draw_robot()
        self.root.after(400, self._rfid_flash_tick)

    def _refresh_rfid_table(self):
        """Cập nhật bảng RFID trên UI."""
        for item in self.tree_rfid.get_children():
            self.tree_rfid.delete(item)
        for uid, info in RFID_DELIVERY_MAP.items():
            cell_id = info["cell"]
            coord = info["coord"]
            count = self.fleet.rfid_cell_count.get(cell_id, 0)
            # Tìm robot gần nhất giao tại ô này
            last_robot = "--"
            for record in reversed(self.fleet.rfid_delivery_log):
                if record["cell"] == cell_id:
                    last_robot = record["robot"]
                    break
            if count > 0:
                status = "✅ ĐÃ GIAO"
            else:
                status = "⏳ Chờ giao"
            self.tree_rfid.insert("", "end", values=(
                info["name"], f"({coord[0]},{coord[1]})",
                uid, status, count, last_robot
            ))
        self.lbl_rfid_total.config(
            text=f"Tổng giao RFID: {self.fleet.rfid_total_delivered}"
        )

    # ============================================================
    # ANIMATION (giữ cho backup, chầu lẽ của sub-pixel)
    # ============================================================
    def _anim_tick(self):
        """Xử lý phần lẻ sub-pixel (nếu có). Phần lớn đã được snap trực tiếp."""
        any_change = False
        for name, r in self.fleet.robots.items():
            if r.step_backlog > 0:
                r.step_backlog -= 1
                self._apply_one_step(name)
                any_change = True
        if any_change:
            self.draw_robot()
        self.root.after(self.ANIM_MS, self._anim_tick)

    # ============================================================
    # STATUS REFRESH
    # ============================================================
    def _refresh_status(self):
        for item in self.tree_monitor.get_children():
            self.tree_monitor.delete(item)
        STATE_MAP = {"IDLE": "Chờ lệnh", "TO_PICKUP": "Đi lấy hàng",
                      "PICKING": "Đang bốc...", "TO_DELIVERY": "Đi giao hàng",
                      "DROPPING": "Đang trả..."}
        total = 0
        for name in sorted(self.fleet.robots.keys()):
            r = self.fleet.robots[name]
            st = STATE_MAP.get(r.state, r.state)
            if r.paused:
                st = "TẠM DỪNG"
            elif r.wait_timer > 0:
                st += f" ({r.wait_timer})"
            total += r.delivered_count
            online = "✅" if r.alive else "❌"
            pos = f"({r.x},{r.y})"
            tgt = f"({r.target_node[0]},{r.target_node[1]})" if r.target_node else "--"
            self.tree_monitor.insert("", "end",
                                      values=(name, online, st, pos, tgt, r.delivered_count))
        self.lbl_total.config(text=f"Tổng hàng đã giao: {total}")

        # Cập nhật bảng RFID
        self._refresh_rfid_table()

        # Bảng pickup
        for item in self.tree_pickup.get_children():
            self.tree_pickup.delete(item)
        pickup_map = {}
        for name, r in self.fleet.robots.items():
            if r.current_job_pickup:
                pickup_map[r.current_job_pickup] = {
                    'robot': name,
                    'zone': f"Điểm trả {r.future_delivery_logical_id}" if r.future_delivery_logical_id else "?",
                    'delivery': str(r.target_node) if r.state in ["TO_DELIVERY", "DROPPING"] else "--"
                }
        for i, node in enumerate(PICKUP_NODES):
            data = pickup_map.get(node)
            self.tree_pickup.insert("", "end", values=(
                f"Trạm {i+1}", str(node),
                data['zone'] if data else "Đợi hàng",
                data['delivery'] if data else "--",
                data['robot'] if data else "Trống"
            ))

        self.root.after(UI_REFRESH_MS, self._refresh_status)
