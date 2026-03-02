# ============================================================
# UET | NCKH 2026 | Entry Point — PHẦN CỨNG
# Điều khiển robot thật qua ESP32 Gateway + UART
# ============================================================
"""
Cách chạy:
    pip install pyserial
    python main_hardware.py
    
Giao diện sẽ hiện ra:
1. Nhập COM port (VD: COM8)
2. Nhấn "Kết nối" → kết nối Gateway ESP32
3. Robot sẽ tự đồng bộ vị trí (SET MAP)
4. Nhấn "KHỞI ĐỘNG HỆ THỐNG" để chạy tự động
5. Hoặc dùng panel "Điều khiển thủ công" để gửi lệnh riêng
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
from config.settings import GRID_N, SUB, REMOVE_NODES
from algorithms.traffic import TrafficManager
from algorithms.coop_astar import CooperativePlanner
from core.robot_proxy import SimulationProxy
from core.fleet_manager import FleetManager
from comms.serial_gateway import SerialGateway
from ui.hardware_dashboard import HardwareDashboard


def main():
    # 1. Khởi tạo Algorithms (DÙNG CHUNG với simulation!)
    traffic_mgr = TrafficManager(GRID_N, REMOVE_NODES)
    coop_planner = CooperativePlanner(GRID_N, traffic_mgr)

    # 2. FleetManager
    # hardware_mode=True: KHÔNG execute command nội bộ
    # Vị trí robot CHỈ update từ STEP/POS feedback qua UART (giống SEVER)
    sim_proxy = SimulationProxy()
    fleet = FleetManager(GRID_N, traffic_mgr, coop_planner, sim_proxy, sub=SUB)
    fleet.hardware_mode = True  # ← QUAN TRỌNG: tắt internal simulation

    # 3. Serial Gateway (UART)
    gateway = SerialGateway()

    # 4. UI
    root = tk.Tk()
    dashboard = HardwareDashboard(root, fleet, gateway)

    # 5. Chạy
    root.mainloop()


if __name__ == "__main__":
    main()
