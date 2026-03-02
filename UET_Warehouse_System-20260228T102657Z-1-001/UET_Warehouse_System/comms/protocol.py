# ============================================================
# PROTOCOL | Định nghĩa gói tin giao tiếp
# ============================================================
"""
Giao thức giao tiếp giữa PC Server và ESP32 Gateway

PC → Gateway (qua Serial UART):
    "ESP01 FFLRF\\n"      → Gửi batch lệnh di chuyển đến robot ESP01
    "ESP01 POS,3,5,N\\n"  → Set vị trí cho robot ESP01

Gateway → PC (qua Serial UART):
    "@1,BATCH_DONE"       → Robot 1 hoàn thành batch lệnh
    "@1,RFID,TAG123"      → Robot 1 quét được RFID tag
    "@1,POS,3,5,N"        → Robot 1 báo vị trí hiện tại
    "@1,POSACK,3,5,N"     → Robot 1 xác nhận đã set vị trí
    "@1,STEP,E,1"         → Robot 1 đã di chuyển 1 bước hướng E
    "@1,TURN,L"           → Robot 1 đã xoay trái
    "@1,DONE"             → Robot 1 hoàn thành 1 lệnh đơn lẻ
"""

import re


def parse_master_line(line):
    """Parse 1 dòng từ Gateway, trả về (target, payload).
    
    Args:
        line: Chuỗi raw từ Serial (VD: "@1,STEP,E,1" hoặc "ESP1 STEP,E,1")
        
    Returns:
        tuple: (target_name, payload) - VD: ("ESP1", "STEP,E,1")
    """
    s = line.strip()
    if not s:
        return "SYS", ""

    # @1,STEP,E,1
    if s.startswith("@"):
        try:
            head, payload = s[1:].split(",", 1)
            rid = int(head)
            if rid <= 0:
                return "SYS", payload.strip()
            return f"ESP{rid}", payload.strip()
        except:
            return "SYS", s

    # E1 STEP,E,1 | ESP1 STEP,E,1 | C1 STEP,E,1 | E1:STEP,E,1
    m = re.match(r'^([A-Za-z]{1,3})\s*(\d+)\s*[:\s,|-]*\s*(.*)$', s)
    if m:
        prefix = m.group(1).upper()
        rid = int(m.group(2))
        payload = m.group(3).strip()

        if prefix in {"E", "C", "ESP"}:
            if rid <= 0:
                return "SYS", payload
            return f"ESP{rid}", payload

    # fallback
    return "ESP1", s


def build_command(robot_name, commands):
    """Tạo chuỗi lệnh gửi xuống Gateway.
    
    Args:
        robot_name: VD "ESP01"
        commands: List lệnh VD ['F', 'F', 'L']
        
    Returns:
        str: VD "ESP01 FFL\\n"
    """
    cmd_str = "".join(commands)
    return f"{robot_name} {cmd_str}\n"


def build_set_pose(robot_name, x, y, heading):
    """Tạo lệnh set vị trí.
    
    Args:
        robot_name: VD "ESP01"
        x, y: Tọa độ grid
        heading: Hướng ('N', 'E', 'S', 'W')
        
    Returns:
        str: VD "ESP01 POS,3,5,N\\n"
    """
    return f"{robot_name} POS,{x},{y},{heading}\n"
