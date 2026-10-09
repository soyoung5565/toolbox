"""
地平线6 (Forza Horizon 6) AFK 刷技能点脚本
============================================
功能：循环执行固定键鼠操作，在指定地图里自动刷技能点
热键：F9 = 开始/暂停，F10 = 退出
输入：Windows SendInput 底层 API，不注入游戏进程
"""

import ctypes
import time
import threading
import sys
import json
import os

# ============================================================
# Windows SendInput API - 底层键盘模拟
# ============================================================
PUL = ctypes.POINTER(ctypes.c_ulong)

class KeyBdInput(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL),
    ]

class HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_ushort),
        ("wParamH", ctypes.c_ushort),
    ]

class MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", PUL),
    ]

class Input_I(ctypes.Union):
    _fields_ = [
        ("ki", KeyBdInput),
        ("mi", MouseInput),
        ("hi", HardwareInput),
    ]

class Input(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("ii", Input_I),
    ]

# 常量
INPUT_KEYBOARD = 1
KEYEVENTF_SCANCODE = 0x0008
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_EXTENDEDKEY = 0x0001

# 常用键的 Scan Code
SCAN_CODES = {
    'W': 0x11, 'A': 0x1E, 'S': 0x1F, 'D': 0x20,
    'SPACE': 0x39, 'ENTER': 0x1C, 'ESC': 0x01,
    'SHIFT': 0x2A, 'CTRL': 0x1D, 'ALT': 0x38,
    'UP': 0x48, 'DOWN': 0x50, 'LEFT': 0x4B, 'RIGHT': 0x4D,
    '1': 0x02, '2': 0x03, '3': 0x04, '4': 0x05, '5': 0x06,
}

# VK codes for hotkeys
VK_F9 = 0x78
VK_F10 = 0x79
VK_F11 = 0x7A

def get_async_key_state(vk):
    return ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000

def press_key(scancode, duration=0.05):
    """按下并释放一个键（通过 scan code）"""
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, scancode, KEYEVENTF_SCANCODE, 0, ctypes.pointer(extra))
    x = Input(INPUT_KEYBOARD, ii_)
    ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
    time.sleep(duration)
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, scancode, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, ctypes.pointer(extra))
    x = Input(INPUT_KEYBOARD, ii_)
    ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

def hold_key(scancode):
    """按住一个键不放"""
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, scancode, KEYEVENTF_SCANCODE, 0, ctypes.pointer(extra))
    x = Input(INPUT_KEYBOARD, ii_)
    ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

def release_key(scancode):
    """释放一个按住的键"""
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, scancode, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, ctypes.pointer(extra))
    x = Input(INPUT_KEYBOARD, ii_)
    ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

# ============================================================
# 默认循环脚本 - 适配大多数刷技能点场景
# ============================================================
# 根据你的地图/路线修改这里
DEFAULT_LOOP = {
    "name": "默认环形路线",
    "description": "一直加速 + 周期性左转，适合椭圆/环形赛道",
    "steps": [
        # 每一步: (动作类型, 参数)
        # hold:    按住按键, 参数 = (键名, 持续秒数)
        # press:   短按按键, 参数 = (键名, 按下时长秒数)
        # wait:    等待,     参数 = 秒数
        ("hold",    "W",    0.5),     # 持续加速
        ("hold",    "A",    0.3),     # 稍微左转
        ("hold",    "W",    0.5),     # 继续加速
        ("wait",    0.1),            # 短暂停顿
        ("hold",    "W",    0.5),     # 持续加速
        ("hold",    "A",    0.3),     # 稍微左转
        ("hold",    "W",    0.8),     # 直道加速
        ("wait",    0.1),
    ],
}

# ============================================================
# 主控制类
# ============================================================
class FH6AFK:
    def __init__(self, loop_config=None):
        self.running = False      # 是否正在执行循环
        self.paused = True        # 是否暂停
        self.loop = loop_config or DEFAULT_LOOP
        self.cycle_count = 0      # 已完成循环次数
        self.start_time = None
        self._stop_event = threading.Event()
        self._worker = None

    def print_banner(self):
        print("=" * 52)
        print("   地平线6 AFK 刷技能点脚本")
        print("=" * 52)
        print(f"   当前路线: {self.loop['name']}")
        print(f"   说明: {self.loop['description']}")
        print("-" * 52)
        print("   F9  = 开始 / 暂停")
        print("   F10 = 退出程序")
        print("   F11 = 显示状态")
        print("-" * 52)
        print("   请先切到游戏窗口，然后按 F9 开始")
        print("=" * 52)
        print()

    def print_status(self):
        elapsed = ""
        if self.start_time:
            secs = int(time.time() - self.start_time)
            h, m, s = secs // 3600, (secs % 3600) // 60, secs % 60
            elapsed = f"{h:02d}:{m:02d}:{s:02d}"
        state = "运行中" if not self.paused else "已暂停"
        print(f"\r  [{state}] 循环: {self.cycle_count} 次 | 运行时间: {elapsed}    ", end="", flush=True)

    def execute_step(self, step):
        """执行单个步骤"""
        action = step[0]
        if action == "hold":
            key_name, duration = step[1], step[2]
            sc = SCAN_CODES.get(key_name.upper())
            if sc is None:
                return
            hold_key(sc)
            # 分段 sleep 以便快速响应暂停/停止
            elapsed = 0
            while elapsed < duration:
                if self._stop_event.is_set() or self.paused:
                    release_key(sc)
                    return
                time.sleep(min(0.05, duration - elapsed))
                elapsed += 0.05
            release_key(sc)

        elif action == "press":
            key_name, duration = step[1], step[2]
            sc = SCAN_CODES.get(key_name.upper())
            if sc is None:
                return
            press_key(sc, duration)

        elif action == "wait":
            duration = step[1]
            elapsed = 0
            while elapsed < duration:
                if self._stop_event.is_set() or self.paused:
                    return
                time.sleep(min(0.05, duration - elapsed))
                elapsed += 0.05

    def run_loop(self):
        """循环执行脚本（在工作线程中运行）"""
        # 给用户 3 秒切换到游戏窗口
        print("\n  3 秒后开始，请切到游戏...")
        for i in range(3, 0, -1):
            if self._stop_event.is_set():
                return
            print(f"  {i}...", end="", flush=True)
            time.sleep(1)
        print(" GO!\n")

        self.start_time = time.time()

        while not self._stop_event.is_set():
            if self.paused:
                time.sleep(0.1)
                continue

            for step in self.loop["steps"]:
                if self._stop_event.is_set() or self.paused:
                    break
                self.execute_step(step)

            if not self.paused and not self._stop_event.is_set():
                self.cycle_count += 1
                self.print_status()

    def start(self):
        """启动工作线程"""
        self.running = True
        self.paused = False
        self._stop_event.clear()
        self._worker = threading.Thread(target=self.run_loop, daemon=True)
        self._worker.start()

    def toggle_pause(self):
        if not self.running:
            self.start()
        else:
            self.paused = not self.paused
            if not self.paused:
                print("\n  ▶ 继续运行")
            else:
                print("\n  ⏸ 已暂停")

    def stop(self):
        self._stop_event.set()
        self.running = False

    def main_loop(self):
        """主循环 - 监听热键"""
        self.print_banner()

        while True:
            # F9 - 开始/暂停
            if get_async_key_state(VK_F9):
                self.toggle_pause()
                time.sleep(0.3)  # 防抖

            # F10 - 退出
            if get_async_key_state(VK_F10):
                print("\n\n  退出中...")
                self.stop()
                break

            # F11 - 状态
            if get_async_key_state(VK_F11):
                self.print_status()
                time.sleep(0.3)

            time.sleep(0.05)


# ============================================================
# 自定义路线配置
# ============================================================
def load_custom_config(path):
    """从 JSON 文件加载自定义路线"""
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def create_example_config():
    """生成一个示例配置文件"""
    example = {
        "name": "自定义路线",
        "description": "根据你的地图修改 steps",
        "steps": [
            ["hold", "W", 2.0],
            ["hold", "A", 0.5],
            ["hold", "W", 1.0],
            ["hold", "D", 0.5],
            ["wait", 0.2],
            ["press", "SPACE", 0.1],
            ["hold", "W", 3.0]
        ],
        "_注释": {
            "hold": ["键名", "按住秒数"],
            "press": ["键名", "按下秒数"],
            "wait": ["等待秒数"],
            "可用键": "W A S D SPACE SHIFT CTRL UP DOWN LEFT RIGHT 1-5"
        }
    }
    config_path = os.path.join(os.path.dirname(__file__), "my_route.json")
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(example, f, ensure_ascii=False, indent=2)
    print(f"  已生成示例配置: {config_path}")
    print("  编辑后运行: python fh6_afk.py --config my_route.json")
    return config_path


# ============================================================
# 入口
# ============================================================
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="地平线6 AFK 刷技能点")
    parser.add_argument("--config", "-c", help="自定义路线 JSON 配置文件路径")
    parser.add_argument("--example", action="store_true", help="生成示例配置文件")
    args = parser.parse_args()

    if args.example:
        create_example_config()
        sys.exit(0)

    loop_config = None
    if args.config:
        if not os.path.exists(args.config):
            print(f"  配置文件不存在: {args.config}")
            sys.exit(1)
        loop_config = load_custom_config(args.config)
        print(f"  已加载配置: {args.config}")

    afk = FH6AFK(loop_config)
    try:
        afk.main_loop()
    except KeyboardInterrupt:
        afk.stop()
        print("\n  已退出")
