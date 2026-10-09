"""地平线6 AI 看护宏 v5
====================
录制宏 → 参考截图 → AI 视觉监控 → 智能纠正 → 继续循环
v5: 鼠标点击采用 OpenCV 模板匹配（借鉴 March7Assistant），告别硬编码坐标

核心流程：
  1. 录制键鼠宏（正常循环操作）
  2. 录制过程中采集参考截图（正常状态的样子）
  3. 回放时定期截图，传给 AI 大模型判断"还在正常刷吗"
  4. 偏差时 AI 分析原因，选择纠正动作执行
  5. 纠正后继续循环

热键：F7=录制鼠标位置+截取模板  F8=纠正宏录制  F9=主宏录制  F10=回放  F11=退出
"""

import keyboard
import mouse
import time
import threading
import json
import os
import sys
import base64
import io
import copy
import ctypes
import ctypes.wintypes
from datetime import datetime
from collections import deque

# 截图 / 视觉
import mss
import numpy as np
import cv2

# API 调用
import urllib.request
import urllib.error

# GUI
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ============================================================
# Windows API - 鼠标精准控制
# ============================================================
user32 = ctypes.windll.user32

def get_cursor_pos():
    pt = ctypes.wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y

def set_cursor_pos(x, y):
    user32.SetCursorPos(int(x), int(y))

# ============================================================
# 屏幕截图工具
# ============================================================
class ScreenCapture:
    def __init__(self):
        self.region = None  # None = 全屏

    def set_region(self, region):
        if region:
            self.region = {"left": region[0], "top": region[1],
                           "width": region[2], "height": region[3]}
        else:
            self.region = None

    def capture(self):
        """截图，返回 PIL Image（每次新建 mss 实例，线程安全）"""
        from PIL import Image
        with mss.mss() as sct:
            if self.region:
                img = sct.grab(self.region)
            else:
                img = sct.grab(sct.monitors[1])
        return Image.frombytes("RGB", img.size, img.rgb, "raw", "BGRX")

    def capture_base64(self, quality=70):
        """截图并返回 base64 JPEG"""
        img = self.capture()
        w, h = img.size
        if w > 1280:
            ratio = 1280 / w
            img = img.resize((1280, int(h * ratio)))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

    def capture_video_base64(self, duration=3, fps=4):
        """录一段短视频，返回 base64 MP4（用于 API 视频分析）
        duration: 录制秒数
        fps: 帧率（低帧率减小文件）
        """
        import subprocess
        import tempfile

        tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
        tmp_path = tmp.name
        tmp.close()

        try:
            # 用 FFmpeg 录制屏幕（gdigrab 是 Windows 屏幕捕获）
            cmd = [
                "ffmpeg", "-y",
                "-f", "gdigrab",
                "-framerate", str(fps),
                "-t", str(duration),
                "-i", "desktop",
                "-vf", "scale=960:-1",  # 960px 保证清晰度
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-crf", "23",  # 更高画质
                "-pix_fmt", "yuv420p",
                tmp_path
            ]

            result = subprocess.run(
                cmd, capture_output=True, timeout=duration + 10
            )

            if result.returncode != 0:
                raise Exception(f"FFmpeg 录制失败: {result.stderr.decode('utf-8', errors='replace')[:200]}")

            # 读取并编码为 base64
            with open(tmp_path, "rb") as f:
                video_data = f.read()

            # 检查文件大小（MIMO 限制 300MB）
            size_mb = len(video_data) / 1024 / 1024
            if size_mb > 200:
                raise Exception(f"视频文件太大: {size_mb:.1f}MB")

            return base64.b64encode(video_data).decode("utf-8"), size_mb

        finally:
            try:
                os.unlink(tmp_path)
            except:
                pass

    def capture_and_save(self, path):
        """截图保存到文件"""
        img = self.capture()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        img.save(path, quality=85)
        return path

    def capture_template_region(self, center_x, center_y, size=120):
        """截取屏幕指定位置周围的区域作为模板图像
        返回: numpy array (RGB), 或 None
        """
        try:
            half = size // 2
            with mss.mss() as sct:
                monitor = sct.monitors[1]  # 主屏幕
                region = {
                    "left": max(0, center_x - half),
                    "top": max(0, center_y - half),
                    "width": size,
                    "height": size
                }
                img = sct.grab(region)
                arr = np.array(Image.frombytes("RGB", img.size, img.rgb, "raw", "BGRX"))
                return arr
        except Exception:
            return None

# ============================================================
# 模板匹配器 - 借鉴 March7Assistant 的图像匹配方案
# ============================================================
class TemplateMatcher:
    """用 OpenCV 模板匹配替代硬编码坐标，实现精准点击"""

    def __init__(self, templates_dir):
        self.templates_dir = templates_dir
        os.makedirs(templates_dir, exist_ok=True)

    def find_template(self, template_path, confidence=0.7):
        """在当前屏幕上查找模板图像
        返回: (center_x, center_y) 屏幕绝对坐标, 或 None
        """
        if not os.path.exists(template_path):
            return None

        template = cv2.imread(template_path)
        if template is None:
            return None

        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        tw, th = template_gray.shape[::-1]

        # 截取全屏
        with mss.mss() as sct:
            screenshot = np.array(sct.grab(sct.monitors[1]))
        screen_gray = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2GRAY)

        # 多尺度匹配（兼容不同分辨率/DPI）
        best_val = 0
        best_loc = None
        best_scale = 1.0

        for scale in [1.0, 0.9, 1.1, 0.8, 1.2]:
            if scale != 1.0:
                sw = int(tw * scale)
                sh = int(th * scale)
                if sw < 10 or sh < 10:
                    continue
                scaled = cv2.resize(template_gray, (sw, sh))
            else:
                scaled = template_gray
                sw, sh = tw, th

            if sw > screen_gray.shape[1] or sh > screen_gray.shape[0]:
                continue

            result = cv2.matchTemplate(screen_gray, scaled, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val > best_val:
                best_val = max_val
                best_loc = max_loc
                best_scale = scale

        if best_val >= confidence and best_loc:
            sw = int(tw * best_scale)
            sh = int(th * best_scale)
            cx = best_loc[0] + sw // 2
            cy = best_loc[1] + sh // 2
            return cx, cy

        return None

    def save_template(self, name, img_array):
        """保存模板图像到文件
        name: 模板名（不含路径）
        img_array: numpy array (RGB)
        返回: 保存的文件路径
        """
        path = os.path.join(self.templates_dir, f"{name}.png")
        # RGB → BGR for OpenCV imwrite
        bgr = cv2.cvtColor(img_array, cv2.COLOR_RGB2BGR)
        cv2.imwrite(path, bgr)
        return path

# ============================================================
# AI 视觉分析器
# ============================================================
class AIVisionAnalyzer:
    def __init__(self, config):
        self.config = config
        self.api_base = config.get("api_base", "")
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "gpt-4o")
        self.max_tokens = config.get("max_tokens", 500)
        self.last_analysis = ""
        self.last_result = None
        self.reference = config.get("reference", {})

    def update_config(self, config):
        self.config = config
        self.api_base = config.get("api_base", "")
        self.api_key = config.get("api_key", "")
        self.model = config.get("model", "gpt-4o")
        self.max_tokens = config.get("max_tokens", 500)
        self.reference = config.get("reference", {})

    def _build_system_prompt(self):
        """根据 reference 配置构建详细的系统 prompt"""
        ref = self.reference
        if not ref:
            return ("你是游戏挂机监控AI。判断截图是否正常。"
                    "返回JSON: {status, description, correction}")

        lines = [
            f"你是《{ref.get('game', '地平线6')}》挂机监控AI。",
            f"当前挂机场景：{ref.get('description', '')}",
            f"赛道类型：{ref.get('track_type', '')}",
            f"车辆：{ref.get('vehicle', '')}",
            "",
            "## 核心检测要点（最重要）：",
            "1. **奖杯检测**：正常行驶时画面中应该能看到奖杯状的可撞击物体。如果奖杯不见了，说明可能退出了赛事、赛事异常、或车严重跑偏。",
            "2. **两侧景物**：正常行驶时两侧景物应该对称/一致。如果两侧景物完全不同，说明车跑偏了。",
            "3. **进度条**：左上角的进度百分比应该持续增长。如果长时间不变说明卡住了。",
            "",
            "## 正常状态：",
            "- 车辆沿直线赛道行驶，两侧景物对称",
            "- 画面中能看到奖杯状可撞击物体",
            "- HUD进度百分比从0%持续增长到100%",
            "- 速度稳定在90-115 km/h",
            "- 技能乘数随撞击上升",
            "",
            "## 异常状态：",
            "- 奖杯不见了 → 可能退出了赛事或赛事出了问题",
            "- 两侧景物完全不同 → 车跑偏了",
            "- 进度百分比长时间不变 → 卡住了",
            "- 速度为0 → 车停了/卡墙了",
            "- 出现菜单/对话框/加载画面 → 循环中断",
            "- 画面全黑/冻结 → 游戏崩溃",
            "",
            "## 可选纠正动作（全部纯键盘操作，不用鼠标）：",
            "- restart_race: 按ESC退出赛事并重新开始（退出赛事、游戏崩溃、循环中断时用）",
            "- reverse_and_turn: 倒车(S)→转向(A)→加速(W)（车卡住、轻微跑偏时用）",
            "- pause_resume: 按ESC暂停再恢复（游戏卡死时用）",
            "- enter_menu: 按ESC进入游戏菜单（用于需要进入菜单界面进行后续操作时）",
            "- none: 不需要纠正",
            "",
            "如果有录制的纠正宏可用，也可以使用宏名称作为 correction 值。",
            "",
            "## 返回格式：",
            "返回JSON，包含：",
            "- status: \"ok\"（正常）或 \"deviation\"（异常）",
            "- description: 当前状态简要描述（必须包含：奖杯是否可见、两侧景物是否对称、进度条状态）",
            "- correction: 建议的纠正动作名",
            "- reason: 为什么选择这个纠正动作（一句话）",
            "只返回JSON，不要其他文字。"]

        return "\n".join(lines)

    def analyze(self, current_b64, ref_b64=None, ref_description=""):
        """
        发送截图给 AI 分析
        返回: {"status": "ok" | "deviation", "description": "...", "correction": "纠正动作名"}
        """
        if not self.api_base or not self.api_key or self.api_key == "YOUR_API_KEY_HERE":
            return {"status": "error", "description": "API 未配置"}

        system_prompt = self._build_system_prompt()

        messages = [{"role": "system", "content": system_prompt}]

        # 用户消息（带图片）
        user_content = []
        if ref_b64:
            user_content.append({"type": "text", "text": "以下是正常运行时的参考截图："})
            user_content.append({"type": "image_url", "image_url": {
                "url": f"data:image/jpeg;base64,{ref_b64}"}})
            user_content.append({"type": "text", "text": "以下是当前截图，请判断是否正常："})
        else:
            user_content.append({"type": "text", "text": "以下是当前游戏截图，请判断是否在正常挂机状态："})

        user_content.append({"type": "image_url", "image_url": {
            "url": f"data:image/jpeg;base64,{current_b64}"}})

        messages.append({"role": "user", "content": user_content})

        try:
            result = self._call_api(messages)
            self.last_analysis = result
            # 尝试解析 JSON
            parsed = self._parse_json(result)
            self.last_result = parsed
            return parsed
        except Exception as e:
            return {"status": "error", "description": str(e)}

    def quick_check(self, current_b64):
        """
        快速检查（不带参考图，更省 token）
        """
        if not self.api_base or not self.api_key or self.api_key == "YOUR_API_KEY_HERE":
            return {"status": "error", "description": "API 未配置"}

        system_prompt = self._build_system_prompt()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{current_b64}"}},
                {"type": "text", "text": "当前游戏截图："}
            ]}
        ]

        try:
            result = self._call_api(messages)
            self.last_analysis = result
            parsed = self._parse_json(result)
            self.last_result = parsed
            return parsed
        except Exception as e:
            return {"status": "error", "description": str(e)}

    def _call_api(self, messages, timeout=30):
        """调用 OpenAI 兼容 API"""
        url = f"{self.api_base.rstrip('/')}/chat/completions"
        payload = json.dumps({
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens
        }).encode("utf-8")

        req = urllib.request.Request(url, data=payload, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key}")

        resp = urllib.request.urlopen(req, timeout=timeout)
        data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]

    def analyze_video(self, video_b64, video_size_mb=0):
        """
        发送短视频给 AI 分析（MIMO 原生视频理解）
        返回: {"status": "ok" | "deviation", "description": "...", "correction": "...", "reason": "..."}
        """
        if not self.api_base or not self.api_key or self.api_key == "YOUR_API_KEY_HERE":
            return {"status": "error", "description": "API 未配置"}

        system_prompt = self._build_system_prompt()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [
                {"type": "text", "text": f"以下是{video_size_mb:.1f}MB的游戏录屏（约3-5秒），请分析当前状态："},
                {"type": "video_url", "video_url": {"url": f"data:video/mp4;base64,{video_b64}"}},
                {"type": "text", "text": "请分析这段视频，判断游戏是否在正常挂机状态。返回JSON。"}
            ]}
        ]

        try:
            result = self._call_api(messages, timeout=60)  # 视频分析需要更长时间
            self.last_analysis = result
            parsed = self._parse_json(result)
            self.last_result = parsed
            return parsed
        except Exception as e:
            return {"status": "error", "description": str(e)}

    def _parse_json(self, text):
        """从 AI 回复中提取 JSON"""
        text = text.strip()
        # 去掉 markdown 代码块
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()
        try:
            return json.loads(text)
        except:
            # 尝试找 JSON 部分
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except:
                    pass
            return {"status": "error", "description": f"AI回复解析失败: {text[:200]}"}

# ============================================================
# 纠正动作执行器
# ============================================================
class CorrectionEngine:
    def __init__(self):
        self.corrections = {}  # 名称 → 动作定义（旧的 config 格式）
        self.macros = {}       # 名称 → 事件列表（录制的宏）
        self.executing = False
        self.matcher = None    # TemplateMatcher 实例（由外部注入）

    def load_corrections(self, corrections_dict):
        self.corrections = corrections_dict

    def load_macro(self, name, events, description=""):
        """加载一个录制的纠正宏"""
        self.macros[name] = {
            "events": events,
            "description": description,
            "event_count": len(events)
        }

    def load_macros_from_dir(self, directory):
        """从目录加载所有纠正宏文件"""
        if not os.path.exists(directory):
            return
        for fname in os.listdir(directory):
            if fname.endswith(".json"):
                path = os.path.join(directory, fname)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    name = os.path.splitext(fname)[0]
                    events = data.get("events", [])
                    desc = data.get("name", name)
                    self.macros[name] = {
                        "events": events,
                        "description": desc,
                        "event_count": len(events),
                        "path": path
                    }
                except:
                    pass

    def get_available_corrections(self):
        """返回所有可用的纠正动作名称"""
        names = list(self.corrections.keys())
        names.extend(self.macros.keys())
        return names

    def execute(self, correction_name, log_callback=None):
        """执行指定的纠正动作（优先用录制的宏）"""
        # 先查录制的宏
        if correction_name in self.macros:
            return self._execute_macro(correction_name, log_callback)

        # 再查 config 定义的动作
        if correction_name in self.corrections:
            return self._execute_steps(correction_name, log_callback)

        if log_callback:
            log_callback(f"[纠正] 未知动作: {correction_name}")
        return False

    def _execute_macro(self, name, log_callback=None):
        """回放一个录制的宏"""
        macro = self.macros[name]
        events = macro["events"]
        desc = macro.get("description", name)

        if log_callback:
            log_callback(f"[纠正] 回放宏: {desc} ({len(events)}事件)")

        self.executing = True

        # 计算绝对时间戳
        timestamps = []
        t = 0.0
        for event in events:
            t += event.get("delay", 0)
            timestamps.append(t)

        start = time.perf_counter()
        for idx, event in enumerate(events):
            if not self.executing:
                break

            target = timestamps[idx]
            while True:
                if not self.executing:
                    break
                remaining = target - (time.perf_counter() - start)
                if remaining <= 0:
                    break
                if remaining > 0.002:
                    time.sleep(remaining * 0.8)
                while (time.perf_counter() - start) < target:
                    if not self.executing:
                        break

            if not self.executing:
                break

            self._play_event(event, log_callback)

        self.executing = False
        if log_callback:
            log_callback(f"[纠正] 宏回放完成")
        return True

    def _play_event(self, event, log_callback=None):
        """回放单个事件"""
        try:
            etype = event["type"]
            if etype == "key_down":
                keyboard.press(event["key"])
            elif etype == "key_up":
                keyboard.release(event["key"])
            elif etype == "mouse_click":
                # 优先使用模板匹配定位
                matched = False
                if event.get("template") and self.matcher:
                    tpl_path = os.path.join(self.matcher.templates_dir, event["template"])
                    pos = self.matcher.find_template(tpl_path)
                    if pos:
                        x, y = pos
                        set_cursor_pos(x, y)
                        matched = True
                        if log_callback:
                            log_callback(f"  模板匹配定位: ({x},{y})")
                # 模板匹配失败，回退到录制坐标
                if not matched:
                    x, y = event.get("x", 0), event.get("y", 0)
                    set_cursor_pos(x, y)
                    if log_callback:
                        log_callback(f"  回退坐标定位: ({x},{y})")
                time.sleep(0.05)
                btn = event.get("button", "left")
                if event.get("down", True):
                    mouse.press(button=btn)
                else:
                    mouse.release(button=btn)
            elif etype == "mouse_move":
                set_cursor_pos(event["x"], event["y"])
            elif etype == "mouse_wheel":
                mouse.wheel(delta=event.get("delta", 0))
        except Exception as e:
            if log_callback:
                log_callback(f"  事件执行失败: {e}")

    def _execute_steps(self, correction_name, log_callback=None):
        """执行 config 中定义的步骤序列"""
        correction = self.corrections[correction_name]
        steps = correction.get("steps", [])
        desc = correction.get("description", correction_name)

        if log_callback:
            log_callback(f"[纠正] 执行: {desc} ({len(steps)}步)")

        self.executing = True
        for i, step in enumerate(steps):
            if not self.executing:
                break
            try:
                self._execute_step(step, log_callback)
            except Exception as e:
                if log_callback:
                    log_callback(f"[纠正] 步骤{i+1}失败: {e}")

        self.executing = False
        if log_callback:
            log_callback(f"[纠正] 完成")
        return True

    def stop(self):
        self.executing = False

    def _execute_step(self, step, log_callback=None):
        action = step.get("action", "")
        delay_after = step.get("delay_after", 0.3)

        if action == "press":
            key = step["key"]
            keyboard.press(key)
            time.sleep(step.get("duration", 0.05))
            keyboard.release(key)
            if log_callback:
                log_callback(f"  按键: {key}")

        elif action == "hold":
            key = step["key"]
            duration = step.get("duration", 1.0)
            keyboard.press(key)
            time.sleep(duration)
            keyboard.release(key)
            if log_callback:
                log_callback(f"  按住: {key} ({duration}s)")

        elif action == "click":
            x, y = step["x"], step["y"]
            btn = step.get("button", "left")
            set_cursor_pos(x, y)
            time.sleep(0.1)
            mouse.click(button=btn)
            if log_callback:
                log_callback(f"  点击: ({x},{y}) {btn}")

        elif action == "move":
            x, y = step["x"], step["y"]
            set_cursor_pos(x, y)
            if log_callback:
                log_callback(f"  移动: ({x},{y})")

        elif action == "wait":
            duration = step.get("duration", 1.0)
            time.sleep(duration)
            if log_callback:
                log_callback(f"  等待: {duration}s")

        time.sleep(delay_after)

# ============================================================
# 宏录制器
# ============================================================
class MacroRecorder:
    def __init__(self):
        self.events = []
        self.recording = False
        self.playing = False
        self._stop_play = threading.Event()
        self._pause_play = threading.Event()
        self._pause_play.set()
        self.play_thread = None
        self.record_start_time = 0
        self._last_event_time = 0
        self.record_count = 0
        self.play_count = 0
        self.record_mouse = True
        self.matcher = None  # TemplateMatcher 实例（由外部注入）

    def start_record(self):
        if self.playing:
            return
        self.events = []
        self.record_count = 0
        self.recording = True
        self.record_start_time = time.time()
        self._last_event_time = self.record_start_time

        # 键盘录制（所有宏都用）
        def on_key(e):
            if not self.recording or e.name in ('f8', 'f9', 'f10', 'f11'):
                return
            now = time.time()
            self.events.append({
                "type": "key_down" if e.event_type == "down" else "key_up",
                "key": e.name, "scan_code": e.scan_code,
                "delay": round(now - self._last_event_time, 4)
            })
            self._last_event_time = now
            self.record_count += 1

        keyboard.hook(on_key)

    def stop_record(self):
        self.recording = False
        keyboard.unhook_all()
        mouse.unhook_all()

    def start_play(self, loop_count=1, speed=1.0, loop_gap=0):
        if self.recording or not self.events:
            return
        self.playing = True
        self._stop_play.clear()
        self._pause_play.set()
        self.play_count = 0
        self.play_thread = threading.Thread(
            target=self._play_loop, args=(loop_count, speed, loop_gap), daemon=True)
        self.play_thread.start()

    def stop_play(self):
        self._stop_play.set()
        self.playing = False
        for k in ['w', 'a', 's', 'd', 'space', 'shift', 'ctrl']:
            try:
                keyboard.release(k)
            except:
                pass

    def pause_play(self):
        self._pause_play.clear()
        for k in ['w', 'a', 's', 'd', 'space', 'shift', 'ctrl']:
            try:
                keyboard.release(k)
            except:
                pass

    def resume_play(self):
        self._pause_play.set()

    def _play_loop(self, loop_count, speed, loop_gap):
        timestamps = []
        t = 0.0
        for event in self.events:
            t += event.get("delay", 0)
            timestamps.append(t)

        i = 0
        while not self._stop_play.is_set():
            if loop_count > 0 and i >= loop_count:
                break
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
                    remaining = target - (time.perf_counter() - loop_start)
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
                if loop_gap > 0 and (loop_count == 0 or i < loop_count):
                    gap_end = time.perf_counter() + loop_gap
                    while time.perf_counter() < gap_end:
                        if self._stop_play.is_set():
                            break
                        time.sleep(0.1)

        self.playing = False

    def _play_event(self, event):
        try:
            etype = event["type"]
            if etype == "key_down":
                keyboard.press(event["key"])
            elif etype == "key_up":
                keyboard.release(event["key"])
            elif etype == "mouse_click":
                # 优先使用模板匹配定位
                matched = False
                if event.get("template") and self.matcher:
                    tpl_path = os.path.join(self.matcher.templates_dir, event["template"])
                    pos = self.matcher.find_template(tpl_path)
                    if pos:
                        x, y = pos
                        set_cursor_pos(x, y)
                        matched = True
                # 模板匹配失败，回退到录制坐标
                if not matched:
                    x, y = event.get("x", 0), event.get("y", 0)
                    set_cursor_pos(x, y)
                time.sleep(0.05)
                if event["down"]:
                    mouse.press(button=event["button"])
                else:
                    mouse.release(button=event["button"])
            elif etype == "mouse_wheel":
                mouse.wheel(delta=event["delta"])
        except:
            pass

    def save_macro(self, path):
        data = {"version": 4, "name": os.path.splitext(os.path.basename(path))[0],
                "event_count": len(self.events),
                "record_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "events": self.events}
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_macro(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        self.events = data.get("events", [])
        return data.get("name", ""), len(self.events)

# ============================================================
# AI 看护协调器 - 把所有组件串起来
# ============================================================
class AIGuardian:
    """协调 宏回放 + 截图 + AI分析 + 纠正执行"""

    def __init__(self, recorder, config):
        self.recorder = recorder
        self.screen = ScreenCapture()
        # AI 配置需要包含 reference 部分
        ai_config = config.get("ai", {})
        ai_config["reference"] = config.get("reference", {})
        self.ai = AIVisionAnalyzer(ai_config)
        self.corrections = CorrectionEngine()
        self.corrections.load_corrections(config.get("corrections", {}))

        # 模板匹配器
        self.templates_dir = r"D:\FH6_AFK\templates"
        self.matcher = TemplateMatcher(self.templates_dir)
        # 注入到录制器和纠正引擎
        self.recorder.matcher = self.matcher
        self.corrections.matcher = self.matcher

        # 加载纠正宏目录
        self.correction_dir = r"D:\FH6_AFK\corrections"
        os.makedirs(self.correction_dir, exist_ok=True)
        self.corrections.load_macros_from_dir(self.correction_dir)

        # 参考截图
        self.ref_screenshots = []     # [(timestamp, PIL.Image, base64)]
        self.ref_description = ""     # 用户对正常状态的描述

        # 监控状态
        self.monitoring = False
        self._stop_monitor = threading.Event()
        self._monitor_thread = None

        # 统计
        self.check_count = 0
        self.deviation_count = 0
        self.correction_count = 0
        self.last_check_time = 0
        self.last_status = "未启动"

        # 设置
        self.check_interval = config.get("monitor", {}).get("check_interval", 8)
        self.deviation_threshold = config.get("monitor", {}).get("deviation_threshold", 3)
        self.auto_correct = config.get("monitor", {}).get("auto_correct", True)
        self.screenshot_region = config.get("monitor", {}).get("screenshot_region")

        if self.screenshot_region:
            self.screen.set_region(self.screenshot_region)

        # 日志回调
        self.log_callback = None

    def update_config(self, config):
        ai_config = config.get("ai", {})
        ai_config["reference"] = config.get("reference", {})
        self.ai.update_config(ai_config)
        self.corrections.load_corrections(config.get("corrections", {}))
        self.check_interval = config.get("monitor", {}).get("check_interval", 8)
        self.deviation_threshold = config.get("monitor", {}).get("deviation_threshold", 3)
        self.auto_correct = config.get("monitor", {}).get("auto_correct", True)

    def add_ref_screenshot(self, description=""):
        """手动添加一张参考截图"""
        try:
            img_b64 = self.screen.capture_base64()
            img_pil = self.screen.capture()
            ts = time.time()
            self.ref_screenshots.append((ts, img_pil, img_b64))
            if description:
                self.ref_description = description
            return len(self.ref_screenshots)
        except Exception as e:
            return 0

    def clear_ref_screenshots(self):
        self.ref_screenshots = []
        self.ref_description = ""

    def start_monitoring(self):
        """启动 AI 看护监控"""
        if self.monitoring:
            return
        self.monitoring = True
        self._stop_monitor.clear()
        self.check_count = 0
        self.deviation_count = 0
        self.correction_count = 0
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop_monitoring(self):
        self._stop_monitor.set()
        self.monitoring = False
        self.corrections.stop()

    def _log(self, msg):
        if self.log_callback:
            self.log_callback(msg)

    def _monitor_loop(self):
        self._log("[AI看护] 启动监控...")
        consecutive_deviations = 0

        # 等一下让回放先稳定
        time.sleep(3)

        while not self._stop_monitor.is_set():
            # 等待检查间隔
            for _ in range(int(self.check_interval * 10)):
                if self._stop_monitor.is_set():
                    break
                time.sleep(0.1)
            if self._stop_monitor.is_set():
                break

            if not self.recorder.playing:
                self._log("[AI看护] 回放已停止，暂停监控")
                break

            self._log(f"[AI看护] 第{self.check_count + 1}次检查（录制3秒视频...）...")

            try:
                video_b64, video_size = self.screen.capture_video_base64(duration=3, fps=4)
                self._log(f"[AI看护] 视频录制完成 ({video_size:.1f}MB)，发送给AI分析...")
            except Exception as e:
                self._log(f"[AI看护] 视频录制失败: {type(e).__name__}: {e}")
                continue

            self.check_count += 1
            self.last_check_time = time.time()

            # AI 分析视频
            result = self.ai.analyze_video(video_b64, video_size)

            status = result.get("status", "error")
            desc = result.get("description", "")
            correction = result.get("correction", "none")

            self.last_status = f"{'✅' if status == 'ok' else '⚠'} {desc}"

            if status == "ok":
                self._log(f"[AI看护] ✅ 正常: {desc}")
                consecutive_deviations = 0
            elif status == "deviation":
                consecutive_deviations += 1
                self.deviation_count += 1
                self._log(f"[AI看护] ⚠ 偏差({consecutive_deviations}/{self.deviation_threshold}): {desc}")

                if consecutive_deviations >= self.deviation_threshold:
                    consecutive_deviations = 0
                    if self.auto_correct and correction and correction != "none":
                        self._log(f"[AI看护] 触发纠正: {correction}")
                        # 暂停宏回放
                        self.recorder.pause_play()
                        time.sleep(0.5)
                        # 执行纠正
                        ok = self.corrections.execute(correction, log_callback=self._log)
                        if ok:
                            self.correction_count += 1
                        # 恢复宏回放
                        time.sleep(1.0)
                        self.recorder.resume_play()
                    else:
                        self._log(f"[AI看护] 偏差确认但未自动纠正 (auto_correct={'开' if self.auto_correct else '关'}, correction={correction})")
            else:
                self._log(f"[AI看护] ❌ 分析异常: {desc}")

        self._log("[AI看护] 监控已停止")
        self.monitoring = False

# ============================================================
# GUI
# ============================================================
class GuardianApp:
    def __init__(self):
        self.config_path = r"D:\FH6_AFK\config.json"
        self.config = self._load_config()

        self.recorder = MacroRecorder()
        self.guardian = AIGuardian(self.recorder, self.config)

        self.macro_dir = r"D:\FH6_AFK\macros"
        self.ref_dir = r"D:\FH6_AFK\references"
        os.makedirs(self.macro_dir, exist_ok=True)
        os.makedirs(self.ref_dir, exist_ok=True)

        self.root = tk.Tk()
        self.root.title("地平线6 AI 看护宏 v5")
        self.root.geometry("620x820")
        self.root.resizable(False, False)
        self.root.configure(bg="#1a1a2e")

        self._build_gui()
        self._bind_hotkeys()
        self._start_status_update()

    def _load_config(self):
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _save_config(self):
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.config, f, ensure_ascii=False, indent=2)

    def _build_gui(self):
        bg = "#1a1a2e"
        fg = "#e0e0e0"
        accent = "#e94560"

        # 标题
        tk.Label(self.root, text="🎮 地平线6 AI 看护宏", font=("Microsoft YaHei", 16, "bold"),
                 bg=bg, fg=accent).pack(pady=(10, 2))
        tk.Label(self.root, text="录制 → 回放 → AI视觉监控 → 智能纠正 → 继续循环",
                 font=("Microsoft YaHei", 9), bg=bg, fg="#888").pack()

        # 热键
        hf = tk.Frame(self.root, bg="#16213e", highlightthickness=1, highlightbackground="#333")
        hf.pack(padx=12, fill="x", pady=(5, 8))
        tk.Label(hf, text="F8=纠正宏录制  F9=主宏录制  F10=回放  F11=退出",
                 font=("Consolas", 10), bg="#16213e", fg="#00d2ff").pack(pady=5)

        # 状态栏
        self.status_var = tk.StringVar(value="就绪")
        self.detail_var = tk.StringVar(value="")
        sf = tk.Frame(self.root, bg=bg)
        sf.pack(padx=12, fill="x", pady=(0, 5))
        self.status_label = tk.Label(sf, textvariable=self.status_var,
                                      font=("Microsoft YaHei", 12, "bold"), bg=bg, fg="#4ecca3")
        self.status_label.pack()
        tk.Label(sf, textvariable=self.detail_var, font=("Consolas", 9), bg=bg, fg=fg).pack()

        # Notebook (标签页)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background=bg, borderwidth=0)
        style.configure("TNotebook.Tab", background="#16213e", foreground=fg,
                         padding=[12, 4], font=("Microsoft YaHei", 9))
        style.map("TNotebook.Tab",
                   background=[("selected", "#0f3460")],
                   foreground=[("selected", "#00d2ff")])

        notebook = ttk.Notebook(self.root)
        notebook.pack(padx=12, fill="both", expand=True, pady=(0, 8))

        # ---- Tab 1: 宏录制 ----
        tab_macro = tk.Frame(notebook, bg=bg)
        notebook.add(tab_macro, text="  宏录制  ")

        btn_style = {"font": ("Microsoft YaHei", 10, "bold"), "bd": 0, "cursor": "hand2",
                     "height": 1, "relief": "flat"}

        row = tk.Frame(tab_macro, bg=bg)
        row.pack(fill="x", padx=10, pady=8)
        self.btn_record = tk.Button(row, text="⏺ 录制 (F9)", bg="#e94560", fg="white",
                                     command=self.toggle_record, width=14, **btn_style)
        self.btn_record.pack(side="left", padx=(0, 5), expand=True, fill="x")
        self.btn_play = tk.Button(row, text="▶ 回放 (F10)", bg="#0f3460", fg="white",
                                   command=self.toggle_play, width=14, **btn_style)
        self.btn_play.pack(side="left", expand=True, fill="x")

        row2 = tk.Frame(tab_macro, bg=bg)
        row2.pack(fill="x", padx=10, pady=3)
        tk.Button(row2, text="💾 保存宏", bg="#16213e", fg="#4ecca3",
                  command=self.save_macro, width=14, **btn_style).pack(side="left", padx=(0, 5), expand=True, fill="x")
        tk.Button(row2, text="📂 加载宏", bg="#16213e", fg="#4ecca3",
                  command=self.load_macro, width=14, **btn_style).pack(side="left", expand=True, fill="x")

        # 回放设置
        pf = tk.LabelFrame(tab_macro, text=" 回放设置 ", font=("Microsoft YaHei", 9),
                            bg=bg, fg=fg, bd=1, relief="groove")
        pf.pack(fill="x", padx=10, pady=8)

        pr1 = tk.Frame(pf, bg=bg)
        pr1.pack(fill="x", padx=8, pady=3)
        tk.Label(pr1, text="循环次数 (0=无限):", font=("Microsoft YaHei", 9), bg=bg, fg=fg).pack(side="left")
        self.loop_var = tk.StringVar(value="0")
        tk.Spinbox(pr1, from_=0, to=9999, textvariable=self.loop_var, width=6,
                   font=("Consolas", 10), bg="#16213e", fg=fg, buttonbackground="#16213e",
                   relief="flat").pack(side="right")

        pr2 = tk.Frame(pf, bg=bg)
        pr2.pack(fill="x", padx=8, pady=3)
        tk.Label(pr2, text="循环间隔 (秒):", font=("Microsoft YaHei", 9), bg=bg, fg=fg).pack(side="left")
        self.gap_var = tk.StringVar(value="5")
        tk.Spinbox(pr2, from_=0, to=60, increment=0.5, textvariable=self.gap_var, width=6,
                   font=("Consolas", 10), bg="#16213e", fg=fg, buttonbackground="#16213e",
                   relief="flat").pack(side="right")

        pr3 = tk.Frame(pf, bg=bg)
        pr3.pack(fill="x", padx=8, pady=3)
        tk.Label(pr3, text="回放速度:", font=("Microsoft YaHei", 9), bg=bg, fg=fg).pack(side="left")
        self.speed_var = tk.DoubleVar(value=1.0)
        self.speed_label = tk.Label(pr3, text="1.0x", font=("Consolas", 10), bg=bg, fg="#00d2ff", width=5)
        self.speed_label.pack(side="right")
        tk.Scale(pr3, from_=0.1, to=3.0, resolution=0.1, orient="horizontal",
                 variable=self.speed_var, bg=bg, fg=fg, highlightthickness=0,
                 troughcolor="#16213e", activebackground="#e94560", length=200,
                 command=lambda v: self.speed_label.config(text=f"{float(v):.1f}x")
                 ).pack(side="right", padx=(0, 5))

        # 录制鼠标选项
        pr4 = tk.Frame(pf, bg=bg)
        pr4.pack(fill="x", padx=8, pady=(3, 6))
        self.mouse_var = tk.BooleanVar(value=True)
        tk.Checkbutton(pr4, text="录制鼠标（F7=记录鼠标位置+截取模板，回放时自动匹配）",
                        variable=self.mouse_var, bg=bg, fg=fg,
                        selectcolor="#16213e", activebackground=bg,
                        font=("Microsoft YaHei", 9),
                        command=lambda: setattr(self.recorder, 'record_mouse', self.mouse_var.get())
                        ).pack(side="left")

        # ---- Tab 2: 参考截图 ----
        tab_ref = tk.Frame(notebook, bg=bg)
        notebook.add(tab_ref, text="  参考截图  ")

        tk.Label(tab_ref, text="参考状态已从视频分析自动加载（见下方摘要）",
                 font=("Microsoft YaHei", 9), bg=bg, fg="#888").pack(padx=10, pady=(8, 5), anchor="w")

        # 显示已加载的参考状态摘要
        ref_info = self.config.get("reference", {})
        if ref_info:
            summary_text = f"场景: {ref_info.get('description', '未设置')}\n"
            summary_text += f"赛道: {ref_info.get('track_type', '未设置')}\n"
            summary_text += f"车辆: {ref_info.get('vehicle', '未设置')}\n"
            summary_text += f"正常状态: {', '.join(ref_info.get('normal_states', {}).keys())}\n"
            summary_text += f"异常状态: {', '.join(ref_info.get('abnormal_states', {}).keys())}"
            summary_label = tk.Label(tab_ref, text=summary_text, font=("Consolas", 9),
                                     bg="#0f0f23", fg="#4ecca3", justify="left", anchor="w",
                                     padx=8, pady=6)
            summary_label.pack(fill="x", padx=10, pady=(0, 8))

        ref_btns = tk.Frame(tab_ref, bg=bg)
        ref_btns.pack(fill="x", padx=10, pady=3)
        tk.Button(ref_btns, text="📷 拍摄参考截图", bg="#0f3460", fg="white",
                  command=self.capture_ref, width=14, **btn_style).pack(side="left", padx=(0, 5))
        tk.Button(ref_btns, text="🎬 从视频导入", bg="#8e44ad", fg="white",
                  command=self.import_ref_video, width=14, **btn_style).pack(side="left", padx=(0, 5))
        tk.Button(ref_btns, text="🗑 清除", bg="#16213e", fg="#e94560",
                  command=self.clear_ref, width=8, **btn_style).pack(side="left")

        # 参考描述
        tk.Label(tab_ref, text="正常状态描述（帮助AI理解什么是'正常'）:",
                 font=("Microsoft YaHei", 9), bg=bg, fg=fg).pack(padx=10, pady=(10, 2), anchor="w")
        self.ref_desc_var = tk.StringVar(value="")
        tk.Entry(tab_ref, textvariable=self.ref_desc_var, font=("Microsoft YaHei", 9),
                 bg="#16213e", fg=fg, insertbackground=fg, relief="flat"
                 ).pack(fill="x", padx=10, pady=(0, 5))

        # 参考截图列表
        self.ref_list_var = tk.StringVar(value="已拍摄: 0 张参考截图")
        tk.Label(tab_ref, textvariable=self.ref_list_var, font=("Consolas", 10),
                 bg=bg, fg="#4ecca3").pack(padx=10, pady=5, anchor="w")

        # ---- Tab 3: 纠正宏 ----
        tab_corr = tk.Frame(notebook, bg=bg)
        notebook.add(tab_corr, text="  纠正宏  ")

        tk.Label(tab_corr, text="录制纠正宏（支持键盘+鼠标点击），AI 会根据情况选择执行",
                 font=("Microsoft YaHei", 9), bg=bg, fg="#888").pack(padx=10, pady=(8, 5), anchor="w")

        # 纠正宏名称输入
        name_frame = tk.Frame(tab_corr, bg=bg)
        name_frame.pack(fill="x", padx=10, pady=3)
        tk.Label(name_frame, text="宏名称:", font=("Microsoft YaHei", 9), bg=bg, fg=fg).pack(side="left")
        self.corr_name_var = tk.StringVar(value="enter_menu")
        tk.Entry(name_frame, textvariable=self.corr_name_var, font=("Consolas", 10),
                 bg="#16213e", fg=fg, insertbackground=fg, relief="flat", width=20
                 ).pack(side="left", padx=5)

        # 录制按钮
        corr_btns = tk.Frame(tab_corr, bg=bg)
        corr_btns.pack(fill="x", padx=10, pady=3)
        self.btn_corr_record = tk.Button(corr_btns, text="⏺ 录制纠正宏 (F8)", bg="#e67e22", fg="white",
                                          command=self.toggle_corr_record,
                                          font=("Microsoft YaHei", 10, "bold"), bd=0, relief="flat",
                                          cursor="hand2", width=18)
        self.btn_corr_record.pack(side="left", padx=(0, 5))
        tk.Button(corr_btns, text="🗑 删除选中", bg="#16213e", fg="#e94560",
                  command=self.delete_corr_macro,
                  font=("Microsoft YaHei", 10), bd=0, relief="flat",
                  cursor="hand2", width=12).pack(side="left")

        # 纠正宏列表
        self.corr_listbox = tk.Listbox(tab_corr, bg="#0f0f23", fg="#4ecca3",
                                        font=("Consolas", 10), relief="flat", bd=0,
                                        selectbackground="#0f3460", selectforeground="#00d2ff",
                                        height=8)
        self.corr_listbox.pack(fill="both", padx=10, pady=5, expand=True)
        self._refresh_corr_list()

        # 纠正宏录制状态
        self.corr_record_status = tk.StringVar(value="")
        tk.Label(tab_corr, textvariable=self.corr_record_status, font=("Consolas", 9),
                 bg=bg, fg="#e67e22").pack(padx=10, anchor="w")

        # ---- Tab 4: AI 看护 ----
        tab_ai = tk.Frame(notebook, bg=bg)
        notebook.add(tab_ai, text="  AI 看护  ")

        # API 设置
        api_frame = tk.LabelFrame(tab_ai, text=" AI API 设置 ", font=("Microsoft YaHei", 9),
                                   bg=bg, fg=fg, bd=1, relief="groove")
        api_frame.pack(fill="x", padx=10, pady=(8, 5))

        ar1 = tk.Frame(api_frame, bg=bg)
        ar1.pack(fill="x", padx=8, pady=3)
        tk.Label(ar1, text="API地址:", font=("Microsoft YaHei", 9), bg=bg, fg=fg, width=8).pack(side="left")
        self.api_base_var = tk.StringVar(value=self.config.get("ai", {}).get("api_base", ""))
        tk.Entry(ar1, textvariable=self.api_base_var, font=("Consolas", 9),
                 bg="#0f0f23", fg=fg, insertbackground=fg, relief="flat").pack(side="left", fill="x", expand=True)

        ar2 = tk.Frame(api_frame, bg=bg)
        ar2.pack(fill="x", padx=8, pady=3)
        tk.Label(ar2, text="API密钥:", font=("Microsoft YaHei", 9), bg=bg, fg=fg, width=8).pack(side="left")
        self.api_key_var = tk.StringVar(value=self.config.get("ai", {}).get("api_key", ""))
        tk.Entry(ar2, textvariable=self.api_key_var, font=("Consolas", 9), show="*",
                 bg="#0f0f23", fg=fg, insertbackground=fg, relief="flat").pack(side="left", fill="x", expand=True)

        ar3 = tk.Frame(api_frame, bg=bg)
        ar3.pack(fill="x", padx=8, pady=(3, 6))
        tk.Label(ar3, text="模型:", font=("Microsoft YaHei", 9), bg=bg, fg=fg, width=8).pack(side="left")
        self.model_var = tk.StringVar(value=self.config.get("ai", {}).get("model", "gpt-4o"))
        tk.Entry(ar3, textvariable=self.model_var, font=("Consolas", 9),
                 bg="#0f0f23", fg=fg, insertbackground=fg, relief="flat").pack(side="left", fill="x", expand=True)
        tk.Button(ar3, text="保存API", bg="#0f3460", fg="white",
                  command=self._save_api_config, font=("Microsoft YaHei", 8), relief="flat"
                  ).pack(side="right", padx=(5, 0))
        tk.Button(ar3, text="🔌 测试连接", bg="#27ae60", fg="white",
                  command=self._test_api, font=("Microsoft YaHei", 8), relief="flat"
                  ).pack(side="right", padx=(5, 0))

        # 监控设置
        mon_frame = tk.LabelFrame(tab_ai, text=" 监控设置 ", font=("Microsoft YaHei", 9),
                                   bg=bg, fg=fg, bd=1, relief="groove")
        mon_frame.pack(fill="x", padx=10, pady=5)

        mr1 = tk.Frame(mon_frame, bg=bg)
        mr1.pack(fill="x", padx=8, pady=3)
        tk.Label(mr1, text="检查间隔 (秒):", font=("Microsoft YaHei", 9), bg=bg, fg=fg).pack(side="left")
        self.check_interval_var = tk.StringVar(value=str(self.config.get("monitor", {}).get("check_interval", 60)))
        tk.Spinbox(mr1, from_=15, to=300, textvariable=self.check_interval_var, width=6,
                   font=("Consolas", 10), bg="#16213e", fg=fg, buttonbackground="#16213e",
                   relief="flat").pack(side="left", padx=(5, 15))
        tk.Label(mr1, text="偏差阈值 (次):", font=("Microsoft YaHei", 9), bg=bg, fg=fg).pack(side="left")
        self.dev_thresh_var = tk.StringVar(value=str(self.config.get("monitor", {}).get("deviation_threshold", 3)))
        tk.Spinbox(mr1, from_=1, to=10, textvariable=self.dev_thresh_var, width=6,
                   font=("Consolas", 10), bg="#16213e", fg=fg, buttonbackground="#16213e",
                   relief="flat").pack(side="left", padx=(5, 0))

        mr2 = tk.Frame(mon_frame, bg=bg)
        mr2.pack(fill="x", padx=8, pady=(3, 6))
        self.auto_correct_var = tk.BooleanVar(value=self.config.get("monitor", {}).get("auto_correct", True))
        tk.Checkbutton(mr2, text="自动纠正", variable=self.auto_correct_var, bg=bg, fg=fg,
                        selectcolor="#16213e", activebackground=bg, font=("Microsoft YaHei", 9)
                        ).pack(side="left")

        # 启动/停止看护
        guard_btns = tk.Frame(tab_ai, bg=bg)
        guard_btns.pack(fill="x", padx=10, pady=8)
        self.btn_guard = tk.Button(guard_btns, text="🛡 启动AI看护 + 回放", bg="#e94560", fg="white",
                                    command=self.toggle_guard, font=("Microsoft YaHei", 11, "bold"),
                                    bd=0, relief="flat", cursor="hand2", height=2)
        self.btn_guard.pack(fill="x")

        # AI 分析日志
        tk.Label(tab_ai, text="AI 分析记录:", font=("Microsoft YaHei", 9), bg=bg, fg="#888"
                 ).pack(padx=10, anchor="w", pady=(5, 0))
        self.ai_log_var = tk.StringVar(value="等待启动...")
        tk.Label(tab_ai, textvariable=self.ai_log_var, font=("Consolas", 9), bg=bg, fg="#00d2ff",
                 wraplength=580, justify="left").pack(padx=10, anchor="w")

        # ---- 日志区（共享）----
        tk.Label(self.root, text="日志", font=("Microsoft YaHei", 9), bg=bg, fg="#888").pack(anchor="w", padx=12)
        log_frame = tk.Frame(self.root, bg=bg)
        log_frame.pack(padx=12, fill="both", expand=True, pady=(2, 8))
        self.log_text = tk.Text(log_frame, height=6, bg="#0f0f23", fg="#4ecca3",
                                 font=("Consolas", 9), relief="flat", bd=0,
                                 insertbackground="#4ecca3", state="disabled", wrap="word")
        scrollbar = tk.Scrollbar(log_frame, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self.log_text.pack(side="left", fill="both", expand=True)

    def _bind_hotkeys(self):
        keyboard.add_hotkey('f8', lambda: self.root.after(0, self.toggle_corr_record), suppress=False)
        keyboard.add_hotkey('f9', lambda: self.root.after(0, self.toggle_record), suppress=False)
        keyboard.add_hotkey('f10', lambda: self.root.after(0, self.toggle_play), suppress=False)
        keyboard.add_hotkey('f11', lambda: self.root.after(0, self._on_close), suppress=False)

    def _log(self, msg):
        # 写入日志文件（供外部监控）
        try:
            with open(r"D:\FH6_AFK\guardian.log", "a", encoding="utf-8") as f:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                f.write(f"[{ts}] {msg}\n")
        except:
            pass
        # 显示在 GUI
        def _do():
            self.log_text.configure(state="normal")
            ts = datetime.now().strftime("%H:%M:%S")
            self.log_text.insert("end", f"[{ts}] {msg}\n")
            lines = self.log_text.get("1.0", "end").split("\n")
            if len(lines) > 60:
                self.log_text.delete("1.0", f"{len(lines)-60}.0")
            self.log_text.see("end")
            self.log_text.configure(state="disabled")
        self.root.after(0, _do)

    def _save_api_config(self):
        self.config.setdefault("ai", {})
        # 只在有值时更新，防止覆盖
        base = self.api_base_var.get().strip()
        key = self.api_key_var.get().strip()
        model = self.model_var.get().strip()
        if base:
            self.config["ai"]["api_base"] = base
        if key:
            self.config["ai"]["api_key"] = key
        if model:
            self.config["ai"]["model"] = model
        self._save_config()
        self.guardian.update_config(self.config)
        self._log("API 配置已保存")

    def _test_api(self):
        """测试 API 连接"""
        self._save_api_config()
        self._log("正在测试 API 连接...")

        def _do_test():
            try:
                base = self.api_base_var.get().rstrip("/")
                key = self.api_key_var.get()
                model = self.model_var.get()

                # 先测试 models 端点
                url = f"{base}/models"
                req = urllib.request.Request(url, method="GET")
                req.add_header("Authorization", f"Bearer {key}")
                try:
                    resp = urllib.request.urlopen(req, timeout=10)
                    self.root.after(0, lambda: self._log(f"✅ 模型列表接口: HTTP {resp.status}"))
                except urllib.error.HTTPError as e:
                    self.root.after(0, lambda: self._log(f"⚠ 模型列表: HTTP {e.code} ({e.reason})"))
                except Exception as e:
                    self.root.after(0, lambda: self._log(f"⚠ 模型列表: {e}"))

                # 测试 chat completions（发一条最简消息）
                url2 = f"{base}/chat/completions"
                payload = json.dumps({
                    "model": model,
                    "messages": [{"role": "user", "content": "回复OK两个字"}],
                    "max_tokens": 10
                }).encode("utf-8")
                req2 = urllib.request.Request(url2, data=payload, method="POST")
                req2.add_header("Content-Type", "application/json")
                req2.add_header("Authorization", f"Bearer {key}")

                t0 = time.time()
                resp2 = urllib.request.urlopen(req2, timeout=15)
                elapsed = time.time() - t0
                data = json.loads(resp2.read().decode("utf-8"))
                reply = data["choices"][0]["message"]["content"].strip()
                self.root.after(0, lambda: self._log(
                    f"✅ 聊天接口: HTTP {resp2.status} | {elapsed:.1f}s | 模型:{model} | 回复:\"{reply}\""))
                self.root.after(0, lambda: self._log("🎉 API 连接正常，可以使用 AI 看护"))

            except urllib.error.HTTPError as e:
                body = ""
                try:
                    body = e.read().decode("utf-8")[:200]
                except:
                    pass
                self.root.after(0, lambda: self._log(f"❌ API 错误: HTTP {e.code} | {body}"))
            except Exception as e:
                self.root.after(0, lambda: self._log(f"❌ 连接失败: {e}"))

        threading.Thread(target=_do_test, daemon=True).start()

    def _start_status_update(self):
        if self.recorder.recording:
            self.status_var.set("⏺ 录制中")
            self.status_label.config(fg="#e94560")
            self.btn_record.config(text="⏹ 停止", bg="#c0392b")
            self.detail_var.set(f"事件: {self.recorder.record_count}")
        elif self.recorder.playing:
            self.status_var.set("▶ 回放中")
            self.status_label.config(fg="#00d2ff")
            self.btn_play.config(text="⏹ 停止", bg="#c0392b")
            lc = int(self.loop_var.get())
            p = self.recorder.play_count
            t = "∞" if lc == 0 else str(lc)
            extra = ""
            if self.guardian.monitoring:
                extra = f" | AI: {self.guardian.check_count}检/{self.guardian.deviation_count}偏/{self.guardian.correction_count}纠"
            self.detail_var.set(f"事件:{len(self.recorder.events)} 循环:{p}/{t}{extra}")
        elif self.guardian.monitoring:
            self.status_var.set("🛡 AI看护中")
            self.status_label.config(fg="#f39c12")
            self.btn_guard.config(text="⏹ 停止看护+回放", bg="#c0392b")
            self.detail_var.set(self.guardian.last_status)
        else:
            self.status_var.set("就绪")
            self.status_label.config(fg="#4ecca3")
            self.btn_record.config(text="⏺ 录制 (F9)", bg="#e94560")
            self.btn_play.config(text="▶ 回放 (F10)", bg="#0f3460")
            self.btn_guard.config(text="🛡 启动AI看护 + 回放", bg="#e94560")
            n = len(self.recorder.events)
            self.detail_var.set(f"事件: {n}" + (f" | 上次: {self.recorder.play_count}次" if self.recorder.play_count else ""))

        # 更新参考截图数
        n_ref = len(self.guardian.ref_screenshots)
        self.ref_list_var.set(f"已拍摄: {n_ref} 张参考截图")

        # AI 日志
        if self.guardian.ai.last_result:
            r = self.guardian.ai.last_result
            self.ai_log_var.set(f"上次: {r.get('status','?')} - {r.get('description','')[:80]}")

        self.root.after(200, self._start_status_update)

    def toggle_record(self):
        if self.recorder.playing or self.guardian.monitoring:
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
                self._log("没有可回放的事件")
                return
            lc = int(self.loop_var.get())
            sp = self.speed_var.get()
            gp = float(self.gap_var.get())
            self._log(f"回放: {len(self.recorder.events)}事件 {'无限' if lc==0 else lc}循环 {sp:.1f}x 间隔{gp}s")
            self._log("3秒后开始...")
            self.root.after(3000, lambda: self.recorder.start_play(lc, sp, gp))

    def toggle_guard(self):
        if self.guardian.monitoring:
            self.guardian.stop_monitoring()
            self.recorder.stop_play()
            self._log("AI看护 + 回放 已停止")
        else:
            if not self.recorder.events:
                self._log("请先录制宏")
                return

            # 更新配置
            self._save_api_config()
            self.config.setdefault("monitor", {})
            self.config["monitor"]["check_interval"] = int(self.check_interval_var.get())
            self.config["monitor"]["deviation_threshold"] = int(self.dev_thresh_var.get())
            self.config["monitor"]["auto_correct"] = self.auto_correct_var.get()
            self._save_config()
            self.guardian.update_config(self.config)

            # 更新参考描述
            self.guardian.ref_description = self.ref_desc_var.get()

            lc = int(self.loop_var.get())
            sp = self.speed_var.get()
            gp = float(self.gap_var.get())

            self._log(f"启动AI看护: 每{self.guardian.check_interval}秒检查, "
                      f"偏差{self.guardian.deviation_threshold}次触发纠正")
            self._log("3秒后开始回放+监控...")

            self.guardian.log_callback = self._log

            def start():
                self.root.after(0, lambda: self._log("3秒后开始，请切到游戏..."))
                time.sleep(3)
                self.root.after(0, lambda: self._log("正在启动回放..."))
                self.recorder.start_play(lc, sp, gp)
                if not self.recorder.playing:
                    self.root.after(0, lambda: self._log("❌ 回放启动失败，请检查是否已录制宏"))
                    return
                self.root.after(0, lambda: self._log("回放已启动，2秒后启动AI监控..."))
                time.sleep(2)
                self.guardian.start_monitoring()

            threading.Thread(target=start, daemon=True).start()

    # ---- 纠正宏管理 ----

    def _refresh_corr_list(self):
        """刷新纠正宏列表"""
        self.corr_listbox.delete(0, "end")
        corr_dir = r"D:\FH6_AFK\corrections"
        if os.path.exists(corr_dir):
            for fname in sorted(os.listdir(corr_dir)):
                if fname.endswith(".json"):
                    name = os.path.splitext(fname)[0]
                    path = os.path.join(corr_dir, fname)
                    try:
                        with open(path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        n_events = len(data.get("events", []))
                        desc = data.get("name", name)
                        self.corr_listbox.insert("end", f"{name}  ({n_events}事件)  {desc}")
                    except:
                        self.corr_listbox.insert("end", f"{name}  (读取失败)")

    def toggle_corr_record(self):
        """录制/停止纠正宏"""
        if self.recorder.playing or self.guardian.monitoring:
            return
        if self.recorder.recording:
            self.recorder.stop_record()
            name = self.corr_name_var.get().strip()
            if not name:
                name = f"macro_{int(time.time())}"
            corr_dir = r"D:\FH6_AFK\corrections"
            os.makedirs(corr_dir, exist_ok=True)
            path = os.path.join(corr_dir, f"{name}.json")
            data = {
                "version": 4,
                "name": name,
                "event_count": len(self.recorder.events),
                "record_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "events": self.recorder.events
            }
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self._log(f"纠正宏已保存: {name} ({len(self.recorder.events)}事件)")
            self.corr_record_status.set(f"已保存: {name}")
            self.guardian.corrections.load_macro(name, self.recorder.events, name)
            self._refresh_corr_list()
            # 解除 F7 绑定
            try:
                keyboard.remove_hotkey('f7')
            except:
                pass
        else:
            name = self.corr_name_var.get().strip()
            self._log(f"开始录制纠正宏: {name or '未命名'}")
            self._log("  键盘正常录 | F7=记录鼠标位置+截取模板 | F8=停止")
            self.corr_record_status.set("录制中... F7=鼠标位置+模板 F8=停止")
            self.recorder.start_record()
            # 绑定 F7 为鼠标位置记录
            keyboard.add_hotkey('f7', self._record_mouse_position, suppress=True)

    def delete_corr_macro(self):
        """删除选中的纠正宏"""
        sel = self.corr_listbox.curselection()
        if not sel:
            return
        item = self.corr_listbox.get(sel[0])
        name = item.split("  ")[0]
        path = os.path.join(r"D:\FH6_AFK\corrections", f"{name}.json")
        if os.path.exists(path):
            os.remove(path)
            self._log(f"已删除纠正宏: {name}")
            if name in self.guardian.corrections.macros:
                del self.guardian.corrections.macros[name]
            self._refresh_corr_list()

    def _record_mouse_position(self):
        """F7 按下时记录当前鼠标位置为左键点击，并截取模板图像"""
        if not self.recorder.recording:
            return
        pt = ctypes.wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        now = time.time()

        # 截取点击位置周围的模板图像
        template_filename = None
        tpl_img = self.guardian.screen.capture_template_region(pt.x, pt.y, size=120)
        if tpl_img is not None:
            tpl_name = f"click_{len(self.recorder.events)}_{int(now)}"
            template_filename = f"{tpl_name}.png"
            self.guardian.matcher.save_template(tpl_name, tpl_img)

        event = {
            "type": "mouse_click", "button": "left",
            "down": True, "x": pt.x, "y": pt.y,
            "delay": round(now - self.recorder._last_event_time, 4)
        }
        if template_filename:
            event["template"] = template_filename

        self.recorder.events.append(event)
        self.recorder._last_event_time = now
        self.recorder.record_count += 1
        tpl_info = f" + 模板({template_filename})" if template_filename else ""
        self._log(f"  🖱 鼠标左键位置: ({pt.x}, {pt.y}){tpl_info}")

    def capture_ref(self):
        n = self.guardian.add_ref_screenshot(self.ref_desc_var.get())
        self._log(f"拍摄参考截图 #{n}")
        # 保存一份到文件
        if self.guardian.ref_screenshots:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(self.ref_dir, f"ref_{ts}.jpg")
            self.guardian.ref_screenshots[-1][1].save(path, quality=85)
            self._log(f"已保存: {path}")

    def import_ref_video(self):
        """从视频文件中抽取关键帧作为参考截图"""
        path = filedialog.askopenfilename(
            title="选择参考视频",
            filetypes=[("视频文件", "*.mp4 *.avi *.mkv *.mov *.wmv"), ("所有文件", "*.*")]
        )
        if not path:
            return

        self._log(f"正在从视频提取参考帧: {os.path.basename(path)}...")

        def _extract():
            try:
                import cv2
                cap = cv2.VideoCapture(path)
                if not cap.isOpened():
                    self.root.after(0, lambda: self._log("❌ 无法打开视频"))
                    return

                fps = cap.get(cv2.CAP_PROP_FPS)
                total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                duration = total / fps if fps > 0 else 0

                # 每 2 秒抽一帧，最多 15 帧
                interval = max(2.0, duration / 15)
                frame_times = [i * interval for i in range(int(duration / interval))]
                if not frame_times:
                    frame_times = [0]

                self.root.after(0, lambda: self._log(
                    f"视频: {duration:.1f}秒, {fps:.1f}fps, 抽取{len(frame_times)}帧"))

                count = 0
                from PIL import Image
                for t in frame_times:
                    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
                    ret, frame = cap.read()
                    if not ret:
                        continue
                    # BGR → RGB → PIL
                    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    img = Image.fromarray(rgb)
                    # 缩小
                    w, h = img.size
                    if w > 1280:
                        ratio = 1280 / w
                        img = img.resize((1280, int(h * ratio)))
                    # 存入 guardian
                    import io
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=80)
                    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
                    self.guardian.ref_screenshots.append((t, img, b64))
                    count += 1
                    # 保存文件
                    ts_str = f"{int(t//60):02d}{int(t%60):02d}"
                    save_path = os.path.join(self.ref_dir, f"ref_video_{ts_str}.jpg")
                    img.save(save_path, quality=85)

                cap.release()
                self.root.after(0, lambda: self._log(
                    f"✅ 从视频提取了 {count} 张参考帧，已保存到 {self.ref_dir}"))

                # 自动生成描述（如果有参考截图）
                if self.guardian.ref_screenshots and not self.ref_desc_var.get():
                    self.root.after(0, lambda: self.ref_desc_var.set(
                        f"正常循环状态（来自视频 {os.path.basename(path)}）"))

            except Exception as e:
                self.root.after(0, lambda: self._log(f"❌ 视频提取失败: {e}"))

        threading.Thread(target=_extract, daemon=True).start()

    def clear_ref(self):
        self.guardian.clear_ref_screenshots()
        self._log("已清除所有参考截图")

    def save_macro(self):
        if not self.recorder.events:
            self._log("没有可保存的事件")
            return
        path = filedialog.asksaveasfilename(
            initialdir=self.macro_dir, defaultextension=".json",
            filetypes=[("宏文件", "*.json")], title="保存宏")
        if path:
            self.recorder.save_macro(path)
            self._log(f"已保存: {os.path.basename(path)}")

    def load_macro(self):
        if self.recorder.recording or self.recorder.playing:
            return
        path = filedialog.askopenfilename(
            initialdir=self.macro_dir, filetypes=[("宏文件", "*.json")], title="加载宏")
        if path:
            name, count = self.recorder.load_macro(path)
            self._log(f"已加载: {name} ({count}事件)")

    def run(self):
        # 启动时自动加载主宏
        default_macro = r"D:\FH6_AFK\macros\刷技术点.json"
        if os.path.exists(default_macro):
            name, count = self.recorder.load_macro(default_macro)
            self._log(f"自动加载主宏: {name} ({count}事件)")
        # 加载纠正宏到引擎
        self.guardian.corrections.load_macros_from_dir(r"D:\FH6_AFK\corrections")
        self._refresh_corr_list()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        if self.recorder.recording:
            self.recorder.stop_record()
        if self.recorder.playing:
            self.recorder.stop_play()
        if self.guardian.monitoring:
            self.guardian.stop_monitoring()
        keyboard.unhook_all()
        mouse.unhook_all()
        self.root.destroy()


if __name__ == "__main__":
    for d in [r"D:\FH6_AFK\macros", r"D:\FH6_AFK\references", r"D:\FH6_AFK\templates"]:
        os.makedirs(d, exist_ok=True)
    app = GuardianApp()
    app.run()
