"""
地平线6 宏录制器 v3 (Macro Recorder + Vision)
==============================================
录制键鼠操作 → 循环回放 → 视觉看护自动矫正

功能：
  - 录制/回放键鼠操作
  - 设置循环间隔（加载等待）
  - 视觉看护：截图对比检测卡住，自动矫正后继续
  - 矫正策略：倒车 → 转向 → 重新加速

热键：
  F9  = 录制 / 停止录制
  F10 = 回放 / 停止回放
  F11 = 退出程序
"""

import keyboard
import mouse
import time
import threading
import json
import os
import sys
import cv2
import numpy as np
import mss
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ============================================================
# 视觉看护 - 截图 + 卡住检测 + 自动矫正
# ============================================================
class VisionWatchdog:
    """在回放期间截图监控，检测卡住并自动矫正"""

    def __init__(self):
        self.enabled = False
        self.check_interval = 3.0     # 每隔几秒检查一次
        self.stuck_threshold = 5.0    # 像素差异低于此值认为画面没变
        self.stuck_count = 0          # 连续画面没变的次数
        self.stuck_limit = 3          # 连续 N 次没变 → 判定卡住
        self.monitor_region = None    # 截图区域 None=全屏
        self._stop = threading.Event()
        self._thread = None
        self._prev_frame = None
        self.on_stuck = None          # 卡住时的回调
        self.log_callback = None      # 日志回调

        # 统计
        self.total_checks = 0
        self.stuck_events = 0

    def start(self, recovery_callback, log_callback=None):
        self.enabled = True
        self._stop.clear()
        self._prev_frame = None
        self.stuck_count = 0
        self.total_checks = 0
        self.stuck_events = 0
        self.on_stuck = recovery_callback
        self.log_callback = log_callback
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        self.enabled = False

    def _log(self, msg):
        if self.log_callback:
            self.log_callback(msg)

    def _capture(self):
        """截取屏幕，返回灰度小图"""
        with mss.mss() as sct:
            if self.monitor_region:
                img = np.array(sct.grab(self.monitor_region))
            else:
                img = np.array(sct.grab(sct.monitors[1]))  # 主显示器
        # BGRA → 灰度
        gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
        # 缩小到 160x90 加速比较
        small = cv2.resize(gray, (160, 90))
        return small

    def _compare(self, frame1, frame2):
        """比较两帧的平均像素差异，返回差异值"""
        diff = cv2.absdiff(frame1, frame2)
        return np.mean(diff)

    def _watch_loop(self):
        """监控主循环"""
        # 等几秒让回放先开始
        time.sleep(2)

        while not self._stop.is_set():
            if self._stop.is_set():
                break

            try:
                current = self._capture()
            except Exception as e:
                self._log(f"[视觉] 截图失败: {e}")
                time.sleep(self.check_interval)
                continue

            self.total_checks += 1

            if self._prev_frame is not None:
                diff = self._compare(self._prev_frame, current)

                if diff < self.stuck_threshold:
                    self.stuck_count += 1
                    self._log(f"[视觉] 画面几乎没变 (差异={diff:.1f}, 连续第{self.stuck_count}次)")
                else:
                    if self.stuck_count > 0:
                        self._log(f"[视觉] 画面有变化 (差异={diff:.1f})，重置计数")
                    self.stuck_count = 0

                # 连续 N 次没变 → 卡住了
                if self.stuck_count >= self.stuck_limit:
                    self.stuck_events += 1
                    self._log(f"[视觉] ⚠ 检测到卡住！(第{self.stuck_events}次)")
                    self.stuck_count = 0
                    if self.on_stuck:
                        self.on_stuck()

            self._prev_frame = current
            time.sleep(self.check_interval)


# ============================================================
# 自动矫正策略
# ============================================================
class RecoveryStrategy:
    """卡住时的矫正操作"""

    def __init__(self):
        self.strategies = [
            self._reverse_and_turn,
            self._hard_brake_turn,
            self._pause_unpause,
        ]
        self.current_idx = 0

    def execute(self, log_callback=None):
        """执行当前矫正策略，返回 True=尝试了矫正"""
        if self.current_idx >= len(self.strategies):
            self.current_idx = 0  # 循环回第一个

        strategy = self.strategies[self.current_idx]
        name = strategy.__doc__ or "未知"
        if log_callback:
            log_callback(f"[矫正] 执行策略: {name}")

        strategy()
        self.current_idx += 1
        return True

    def reset(self):
        self.current_idx = 0

    @staticmethod
    def _reverse_and_turn():
        """倒车 + 转向"""
        # 倒车
        keyboard.press('s')
        time.sleep(1.5)
        keyboard.release('s')
        time.sleep(0.1)
        # 转向
        keyboard.press('a')
        time.sleep(0.8)
        keyboard.release('a')
        time.sleep(0.1)
        # 重新加速
        keyboard.press('w')
        time.sleep(2.0)
        keyboard.release('w')

    @staticmethod
    def _hard_brake_turn():
        """刹车 + 大幅转向"""
        # 刹车
        keyboard.press('s')
        time.sleep(0.5)
        keyboard.release('s')
        time.sleep(0.1)
        # 大幅转向（用更长时间）
        keyboard.press('d')
        time.sleep(1.2)
        keyboard.release('d')
        time.sleep(0.1)
        # 加速
        keyboard.press('w')
        time.sleep(2.5)
        keyboard.release('w')

    @staticmethod
    def _pause_unpause():
        """暂停/恢复游戏（ESC连按）"""
        keyboard.press('escape')
        time.sleep(0.1)
        keyboard.release('escape')
        time.sleep(1.0)
        keyboard.press('escape')
        time.sleep(0.1)
        keyboard.release('escape')
        time.sleep(1.5)


# ============================================================
# 宏录制器核心
# ============================================================
class MacroRecorder:
    def __init__(self):
        self.events = []
        self.recording = False
        self.playing = False
        self._stop_play = threading.Event()
        self._pause_play = threading.Event()
        self._pause_play.set()  # 默认不暂停
        self.play_thread = None
        self.record_start_time = 0
        self._last_event_time = 0

        self.record_count = 0
        self.play_count = 0
        self.record_mouse = True

        # 视觉看护
        self.vision = VisionWatchdog()
        self.recovery = RecoveryStrategy()

    # ---- 录制 ----
    def start_record(self):
        if self.playing:
            return
        self.events = []
        self.record_count = 0
        self.recording = True
        self.record_start_time = time.time()
        self._last_event_time = self.record_start_time

        def on_key(e):
            if not self.recording:
                return
            if e.name in ('f9', 'f10', 'f11'):
                return
            now = time.time()
            delay = now - self._last_event_time
            self._last_event_time = now
            event_type = "key_down" if e.event_type == "down" else "key_up"
            self.events.append({
                "type": event_type,
                "key": e.name,
                "scan_code": e.scan_code,
                "delay": round(delay, 4)
            })
            self.record_count += 1

        keyboard.hook(on_key)

        if self.record_mouse:
            def on_mouse_click(e):
                if not self.recording:
                    return
                if isinstance(e, mouse.ButtonEvent):
                    now = time.time()
                    delay = now - self._last_event_time
                    self._last_event_time = now
                    self.events.append({
                        "type": "mouse_click",
                        "button": e.button,
                        "down": (e.event_type == "down"),
                        "x": e.x, "y": e.y,
                        "delay": round(delay, 4)
                    })
                    self.record_count += 1
                elif isinstance(e, mouse.WheelEvent):
                    now = time.time()
                    delay = now - self._last_event_time
                    self._last_event_time = now
                    self.events.append({
                        "type": "mouse_wheel",
                        "delta": e.delta,
                        "x": e.x, "y": e.y,
                        "delay": round(delay, 4)
                    })
                    self.record_count += 1

            mouse.hook(on_mouse_click)

    def stop_record(self):
        self.recording = False
        keyboard.unhook_all()
        mouse.unhook_all()

    # ---- 回放 ----
    def start_play(self, loop_count=1, speed=1.0, loop_gap=0, vision_enabled=False):
        if self.recording or not self.events:
            return
        self.playing = True
        self._stop_play.clear()
        self._pause_play.set()
        self.play_count = 0
        self.recovery.reset()
        self.play_thread = threading.Thread(
            target=self._play_loop,
            args=(loop_count, speed, loop_gap, vision_enabled),
            daemon=True
        )
        self.play_thread.start()

    def stop_play(self):
        self._stop_play.set()
        self.playing = False
        self.vision.stop()
        for key_name in ['w', 'a', 's', 'd', 'space', 'shift', 'ctrl']:
            try:
                keyboard.release(key_name)
            except:
                pass

    def pause_play(self):
        """暂停回放（矫正时用）"""
        self._pause_play.clear()
        # 释放所有按键
        for key_name in ['w', 'a', 's', 'd', 'space', 'shift', 'ctrl']:
            try:
                keyboard.release(key_name)
            except:
                pass

    def resume_play(self):
        """恢复回放"""
        self._pause_play.set()

    def _on_stuck_detected(self):
        """视觉检测到卡住时的回调"""
        self.pause_play()
        self.recovery.execute(log_callback=self._log_ref)
        self.resume_play()

    def _play_loop(self, loop_count, speed, loop_gap, vision_enabled):
        """回放循环"""
        self._log_ref = None  # 由 GUI 设置

        # 预计算绝对时间戳
        timestamps = []
        t = 0.0
        for event in self.events:
            t += event.get("delay", 0)
            timestamps.append(t)

        # 启动视觉看护
        if vision_enabled and self.vision.enabled:
            self.vision.start(
                recovery_callback=self._on_stuck_detected,
                log_callback=self._log_ref
            )

        i = 0
        while not self._stop_play.is_set():
            if loop_count > 0 and i >= loop_count:
                break

            # 等待恢复（如果被暂停了）
            self._pause_play.wait()
            if self._stop_play.is_set():
                break

            loop_start = time.perf_counter()

            for idx, event in enumerate(self.events):
                if self._stop_play.is_set():
                    break
                self._pause_play.wait()
                if self._stop_play.is_set():
                    break

                target = timestamps[idx] / speed

                while True:
                    if self._stop_play.is_set():
                        break
                    self._pause_play.wait()
                    now = time.perf_counter() - loop_start
                    remaining = target - now
                    if remaining <= 0:
                        break
                    if remaining > 0.002:
                        time.sleep(remaining * 0.8)
                    while (time.perf_counter() - loop_start) < target:
                        if self._stop_play.is_set():
                            break

                if self._stop_play.is_set():
                    break

                self._play_event(event)

            if not self._stop_play.is_set():
                i += 1
                self.play_count = i

                # 循环间隔（加载等待）
                if loop_gap > 0 and (loop_count == 0 or i < loop_count):
                    if self._log_ref:
                        self._log_ref(f"[回放] 循环 {i} 完成，等待 {loop_gap}s 加载...")
                    gap_end = time.perf_counter() + loop_gap
                    while time.perf_counter() < gap_end:
                        if self._stop_play.is_set():
                            break
                        time.sleep(0.1)

        self.playing = False
        self.vision.stop()

    def _play_event(self, event):
        etype = event["type"]
        try:
            if etype == "key_down":
                keyboard.press(event["key"])
            elif etype == "key_up":
                keyboard.release(event["key"])
            elif etype == "mouse_click":
                if event["down"]:
                    mouse.press(button=event["button"])
                else:
                    mouse.release(button=event["button"])
            elif etype == "mouse_wheel":
                mouse.wheel(delta=event["delta"])
        except:
            pass

    # ---- 保存/加载 ----
    def save_macro(self, path):
        data = {
            "version": 3,
            "name": os.path.splitext(os.path.basename(path))[0],
            "event_count": len(self.events),
            "record_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "events": self.events
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_macro(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.events = data.get("events", [])
        return data.get("name", ""), len(self.events)


# ============================================================
# GUI 界面
# ============================================================
class MacroApp:
    def __init__(self):
        self.recorder = MacroRecorder()
        self.macro_dir = r"D:\FH6_AFK\macros"
        os.makedirs(self.macro_dir, exist_ok=True)

        self.root = tk.Tk()
        self.root.title("地平线6 宏录制器 v3")
        self.root.geometry("560x720")
        self.root.resizable(False, False)
        self.root.configure(bg="#1a1a2e")

        self._build_gui()
        self._bind_hotkeys()
        self._start_status_update()

    def _build_gui(self):
        bg = "#1a1a2e"
        fg = "#e0e0e0"
        accent = "#e94560"

        # 标题
        tk.Label(self.root, text="🎮 地平线6 宏录制器", font=("Microsoft YaHei", 18, "bold"),
                 bg=bg, fg=accent).pack(pady=(12, 3))
        tk.Label(self.root, text="录制 → 回放 → 视觉看护 → 自动矫正",
                 font=("Microsoft YaHei", 9), bg=bg, fg="#888").pack(pady=(0, 8))

        # 热键
        hint_frame = tk.Frame(self.root, bg="#16213e", highlightthickness=1, highlightbackground="#333")
        hint_frame.pack(padx=15, fill="x", pady=(0, 8))
        tk.Label(hint_frame, text="F9=录制/停止  F10=回放/停止  F11=退出",
                 font=("Consolas", 10), bg="#16213e", fg="#00d2ff").pack(pady=6)

        # 状态
        self.status_var = tk.StringVar(value="就绪")
        self.count_var = tk.StringVar(value="事件: 0")
        self.time_var = tk.StringVar(value="")

        sf = tk.Frame(self.root, bg=bg)
        sf.pack(padx=15, fill="x", pady=(0, 5))
        self.status_label = tk.Label(sf, textvariable=self.status_var,
                                      font=("Microsoft YaHei", 14, "bold"), bg=bg, fg="#4ecca3")
        self.status_label.pack()
        tk.Label(sf, textvariable=self.count_var, font=("Consolas", 10), bg=bg, fg=fg).pack()
        tk.Label(sf, textvariable=self.time_var, font=("Consolas", 9), bg=bg, fg="#888").pack()

        ttk.Separator(self.root, orient="horizontal").pack(fill="x", padx=15, pady=5)

        # 按钮
        btn_style = {"font": ("Microsoft YaHei", 10, "bold"), "bd": 0, "cursor": "hand2",
                     "width": 12, "height": 1, "relief": "flat"}

        r1 = tk.Frame(self.root, bg=bg)
        r1.pack(padx=15, fill="x", pady=3)
        self.btn_record = tk.Button(r1, text="⏺ 录制 (F9)", bg="#e94560", fg="white",
                                     command=self.toggle_record, **btn_style)
        self.btn_record.pack(side="left", padx=(0, 8), expand=True, fill="x")
        self.btn_play = tk.Button(r1, text="▶ 回放 (F10)", bg="#0f3460", fg="white",
                                   command=self.toggle_play, **btn_style)
        self.btn_play.pack(side="left", expand=True, fill="x")

        r2 = tk.Frame(self.root, bg=bg)
        r2.pack(padx=15, fill="x", pady=3)
        tk.Button(r2, text="💾 保存宏", bg="#16213e", fg="#4ecca3",
                  command=self.save_macro, **btn_style).pack(side="left", padx=(0, 8), expand=True, fill="x")
        tk.Button(r2, text="📂 加载宏", bg="#16213e", fg="#4ecca3",
                  command=self.load_macro, **btn_style).pack(side="left", expand=True, fill="x")

        ttk.Separator(self.root, orient="horizontal").pack(fill="x", padx=15, pady=8)

        # ---- 回放设置 ----
        settings = tk.LabelFrame(self.root, text=" 回放设置 ", font=("Microsoft YaHei", 9),
                                  bg=bg, fg=fg, bd=1, relief="groove")
        settings.pack(padx=15, fill="x", pady=(0, 5))

        # 循环次数
        sr1 = tk.Frame(settings, bg=bg)
        sr1.pack(fill="x", padx=10, pady=3)
        tk.Label(sr1, text="循环次数 (0=无限):", font=("Microsoft YaHei", 9), bg=bg, fg=fg).pack(side="left")
        self.loop_var = tk.StringVar(value="0")
        tk.Spinbox(sr1, from_=0, to=9999, textvariable=self.loop_var, width=8,
                   font=("Consolas", 10), bg="#16213e", fg=fg, buttonbackground="#16213e",
                   relief="flat").pack(side="right")

        # 循环间隔
        sr2 = tk.Frame(settings, bg=bg)
        sr2.pack(fill="x", padx=10, pady=3)
        tk.Label(sr2, text="循环间隔 (秒):", font=("Microsoft YaHei", 9), bg=bg, fg=fg).pack(side="left")
        self.gap_var = tk.StringVar(value="5")
        tk.Spinbox(sr2, from_=0, to=60, increment=0.5, textvariable=self.gap_var, width=8,
                   font=("Consolas", 10), bg="#16213e", fg=fg, buttonbackground="#16213e",
                   relief="flat").pack(side="right")

        # 速度
        sr3 = tk.Frame(settings, bg=bg)
        sr3.pack(fill="x", padx=10, pady=3)
        tk.Label(sr3, text="回放速度:", font=("Microsoft YaHei", 9), bg=bg, fg=fg).pack(side="left")
        self.speed_var = tk.DoubleVar(value=1.0)
        self.speed_label = tk.Label(sr3, text="1.0x", font=("Consolas", 10), bg=bg, fg="#00d2ff", width=5)
        self.speed_label.pack(side="right")
        tk.Scale(sr3, from_=0.1, to=3.0, resolution=0.1, orient="horizontal",
                 variable=self.speed_var, bg=bg, fg=fg, highlightthickness=0,
                 troughcolor="#16213e", activebackground="#e94560", length=220,
                 command=lambda v: self.speed_label.config(text=f"{float(v):.1f}x")
                 ).pack(side="right", padx=(0, 5))

        # 录制鼠标
        sr4 = tk.Frame(settings, bg=bg)
        sr4.pack(fill="x", padx=10, pady=(3, 6))
        self.mouse_var = tk.BooleanVar(value=True)
        tk.Checkbutton(sr4, text="录制鼠标", variable=self.mouse_var, bg=bg, fg=fg,
                        selectcolor="#16213e", activebackground=bg, font=("Microsoft YaHei", 9),
                        command=lambda: setattr(self.recorder, 'record_mouse', self.mouse_var.get())
                        ).pack(side="left")

        ttk.Separator(self.root, orient="horizontal").pack(fill="x", padx=15, pady=5)

        # ---- 视觉看护设置 ----
        vision_frame = tk.LabelFrame(self.root, text=" 👁 视觉看护（检测卡住自动矫正）",
                                      font=("Microsoft YaHei", 9), bg=bg, fg=fg, bd=1, relief="groove")
        vision_frame.pack(padx=15, fill="x", pady=(0, 5))

        vr1 = tk.Frame(vision_frame, bg=bg)
        vr1.pack(fill="x", padx=10, pady=3)
        self.vision_var = tk.BooleanVar(value=False)
        tk.Checkbutton(vr1, text="启用视觉看护", variable=self.vision_var, bg=bg, fg="#e94560",
                        selectcolor="#16213e", activebackground=bg, font=("Microsoft YaHei", 9, "bold")
                        ).pack(side="left")

        vr2 = tk.Frame(vision_frame, bg=bg)
        vr2.pack(fill="x", padx=10, pady=3)
        tk.Label(vr2, text="检查间隔 (秒):", font=("Microsoft YaHei", 9), bg=bg, fg=fg).pack(side="left")
        self.check_interval_var = tk.StringVar(value="3")
        tk.Spinbox(vr2, from_=1, to=30, textvariable=self.check_interval_var, width=6,
                   font=("Consolas", 10), bg="#16213e", fg=fg, buttonbackground="#16213e",
                   relief="flat").pack(side="left", padx=(5, 15))
        tk.Label(vr2, text="卡住判定 (次):", font=("Microsoft YaHei", 9), bg=bg, fg=fg).pack(side="left")
        self.stuck_limit_var = tk.StringVar(value="3")
        tk.Spinbox(vr2, from_=1, to=20, textvariable=self.stuck_limit_var, width=6,
                   font=("Consolas", 10), bg="#16213e", fg=fg, buttonbackground="#16213e",
                   relief="flat").pack(side="left", padx=(5, 0))

        vr3 = tk.Frame(vision_frame, bg=bg)
        vr3.pack(fill="x", padx=10, pady=(3, 6))
        tk.Label(vr3, text="检测灵敏度:", font=("Microsoft YaHei", 9), bg=bg, fg=fg).pack(side="left")
        self.sensitivity_var = tk.DoubleVar(value=5.0)
        self.sens_label = tk.Label(vr3, text="5.0", font=("Consolas", 10), bg=bg, fg="#00d2ff", width=4)
        self.sens_label.pack(side="right")
        tk.Scale(vr3, from_=1.0, to=20.0, resolution=0.5, orient="horizontal",
                 variable=self.sensitivity_var, bg=bg, fg=fg, highlightthickness=0,
                 troughcolor="#16213e", activebackground="#e94560", length=180,
                 command=lambda v: self.sens_label.config(text=f"{float(v):.1f}")
                 ).pack(side="right", padx=(0, 5))

        ttk.Separator(self.root, orient="horizontal").pack(fill="x", padx=15, pady=5)

        # ---- 日志 ----
        tk.Label(self.root, text="日志", font=("Microsoft YaHei", 9), bg=bg, fg="#888").pack(anchor="w", padx=15)

        log_frame = tk.Frame(self.root, bg=bg)
        log_frame.pack(padx=15, fill="both", expand=True, pady=(2, 10))

        self.log_text = tk.Text(log_frame, height=8, bg="#0f0f23", fg="#4ecca3",
                                 font=("Consolas", 9), relief="flat", bd=0,
                                 insertbackground="#4ecca3", state="disabled", wrap="word")
        scrollbar = tk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)

    def _bind_hotkeys(self):
        keyboard.add_hotkey('f9', lambda: self.root.after(0, self.toggle_record), suppress=False)
        keyboard.add_hotkey('f10', lambda: self.root.after(0, self.toggle_play), suppress=False)
        keyboard.add_hotkey('f11', lambda: self.root.after(0, self._on_close), suppress=False)

    def _log(self, msg):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n")
        lines = self.log_text.get("1.0", "end").split("\n")
        if len(lines) > 50:
            self.log_text.delete("1.0", f"{len(lines)-50}.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _start_status_update(self):
        if self.recorder.recording:
            self.status_var.set("⏺ 录制中...")
            self.status_label.config(fg="#e94560")
            self.btn_record.config(text="⏹ 停止录制", bg="#c0392b")
            self.count_var.set(f"已录制: {self.recorder.record_count} 个事件")
            elapsed = time.time() - self.recorder.record_start_time
            m, s = divmod(int(elapsed), 60)
            self.time_var.set(f"录制时间: {m:02d}:{s:02d}")
        elif self.recorder.playing:
            self.status_var.set("▶ 回放中...")
            self.status_label.config(fg="#00d2ff")
            self.btn_play.config(text="⏹ 停止回放", bg="#c0392b")
            loop_count = int(self.loop_var.get())
            played = self.recorder.play_count
            total = f"∞" if loop_count == 0 else str(loop_count)
            extra = ""
            if self.recorder.vision.enabled:
                extra = f" | 视觉: {self.recorder.vision.total_checks}次检测, {self.recorder.vision.stuck_events}次矫正"
            self.count_var.set(f"事件: {len(self.recorder.events)} | 循环: {played}/{total}{extra}")
            self.time_var.set("")
        else:
            self.status_var.set("就绪")
            self.status_label.config(fg="#4ecca3")
            self.btn_record.config(text="⏺ 录制 (F9)", bg="#e94560")
            self.btn_play.config(text="▶ 回放 (F10)", bg="#0f3460")
            n = len(self.recorder.events)
            pc = self.recorder.play_count
            self.count_var.set(f"事件: {n}" + (f" | 上次: {pc}次循环" if pc else ""))
            self.time_var.set("")

        self.root.after(100, self._start_status_update)

    def toggle_record(self):
        if self.recorder.playing:
            return
        if self.recorder.recording:
            self.recorder.stop_record()
            self._log(f"停止录制，共 {len(self.recorder.events)} 个事件")
        else:
            self._log("开始录制... (F9 停止)")
            self.recorder.start_record()

    def toggle_play(self):
        if self.recorder.recording:
            return
        if self.recorder.playing:
            self.recorder.stop_play()
            self._log("停止回放")
        else:
            if not self.recorder.events:
                self._log("没有可回放的事件，请先录制或加载宏")
                return

            # 应用视觉看护设置
            vision_enabled = self.vision_var.get()
            if vision_enabled:
                self.recorder.vision.enabled = True
                self.recorder.vision.check_interval = float(self.check_interval_var.get())
                self.recorder.vision.stuck_limit = int(self.stuck_limit_var.get())
                self.recorder.vision.stuck_threshold = self.sensitivity_var.get()
                self._log(f"[视觉] 已启用: 每{self.recorder.vision.check_interval}秒检查, "
                          f"连续{self.recorder.vision.stuck_limit}次不变=卡住, "
                          f"灵敏度={self.recorder.vision.stuck_threshold}")
            else:
                self.recorder.vision.enabled = False

            loop_count = int(self.loop_var.get())
            speed = self.speed_var.get()
            loop_gap = float(self.gap_var.get())

            self._log(f"开始回放: {len(self.recorder.events)}事件, "
                      f"{'无限' if loop_count == 0 else loop_count}循环, "
                      f"{speed:.1f}x速度, 间隔{loop_gap}s")
            self._log("3秒后开始，请切到游戏...")

            # 设置日志回调
            self.recorder._log_ref = self._log

            self.root.after(3000, lambda: self.recorder.start_play(
                loop_count, speed, loop_gap, vision_enabled
            ))

    def save_macro(self):
        if not self.recorder.events:
            messagebox.showinfo("提示", "没有可保存的事件")
            return
        path = filedialog.asksaveasfilename(
            initialdir=self.macro_dir, defaultextension=".json",
            filetypes=[("宏文件", "*.json")], title="保存宏文件"
        )
        if path:
            self.recorder.save_macro(path)
            self._log(f"已保存: {os.path.basename(path)} ({len(self.recorder.events)} 事件)")

    def load_macro(self):
        if self.recorder.recording or self.recorder.playing:
            return
        path = filedialog.askopenfilename(
            initialdir=self.macro_dir, filetypes=[("宏文件", "*.json")], title="加载宏文件"
        )
        if path:
            name, count = self.recorder.load_macro(path)
            self._log(f"已加载: {name} ({count} 事件)")

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        if self.recorder.recording:
            self.recorder.stop_record()
        if self.recorder.playing:
            self.recorder.stop_play()
        keyboard.unhook_all()
        mouse.unhook_all()
        self.root.destroy()


if __name__ == "__main__":
    os.makedirs(r"D:\FH6_AFK\macros", exist_ok=True)
    app = MacroApp()
    app.run()
