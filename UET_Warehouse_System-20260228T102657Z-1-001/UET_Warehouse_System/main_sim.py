# ============================================================
# UET | NCKH 2026 | Entry Point — MÔ PHỎNG
# Chạy mô phỏng trên PC (hành vi giống file monolithic gốc)
# ============================================================
import sys
import os

# Thêm thư mục gốc của project vào path để import đúng
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import tkinter as tk
from config.settings import GRID_N, SUB, REMOVE_NODES
from algorithms.traffic import TrafficManager
from algorithms.coop_astar import CooperativePlanner
from core.robot_proxy import SimulationProxy
from core.fleet_manager import FleetManager
from ui.dashboard import WarehouseDashboard


def main():
    # 1. Khởi tạo Algorithms
    traffic_mgr = TrafficManager(GRID_N, REMOVE_NODES)
    coop_planner = CooperativePlanner(GRID_N, traffic_mgr)

    # 2. Khởi tạo Core (SIMULATION mode)
    sim_proxy = SimulationProxy()
    fleet = FleetManager(GRID_N, traffic_mgr, coop_planner, sim_proxy, sub=SUB)

    # 3. Khởi tạo UI
    root = tk.Tk()
    dashboard = WarehouseDashboard(root, fleet)

    # 4. Chạy mainloop
    root.mainloop()


if __name__ == "__main__":
    main()
