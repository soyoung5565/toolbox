"""
Screen Translator — 屏幕实时翻译覆盖
使用 MIMO v2.5 大模型进行 OCR + 翻译
参考：手机浏览器的AI网页翻译功能
"""

import sys
import os
import base64
import json
import time
import ctypes
from io import BytesIO

import requests
import mss
from PIL import Image

from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QFrame, QSizePolicy, QComboBox, QSpinBox,
    QScrollArea, QGridLayout, QShortcut,
)
from PyQt5.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QRect, QPoint, QSize,
)
from PyQt5.QtGui import (
    QPainter, QColor, QPen, QFont, QCursor, QKeySequence, QFontMetrics,
)

# ═══════════════════════════════════════════════════════════════
#  常量 & 配置
# ═══════════════════════════════════════════════════════════════

# 切到 minimax (MiniMax-M3 是 M3 模型最新款，支持视觉 OCR+翻译)
API_URL = "https://api.minimaxi.com/v1/chat/completions"
MODEL = "MiniMax-M3"  # best quality, supports vision+text

def _load_api_key():
    """Read API key from ~/.hermes/config.yaml (providers.minimax first, fallback mimo)."""
    import yaml
    config_path = os.path.join(os.path.expanduser("~"), ".hermes", "config.yaml")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        providers = cfg.get("providers", {})
        # 优先 minimax，没有再退到 mimo
        for name, prov in providers.items():
            if "minimax" in name.lower():
                return prov.get("api_key", "")
        for name, prov in providers.items():
            if "mimo" in name.lower():
                return prov.get("api_key", "")
    except Exception:
        pass
    return ""

API_KEY = _load_api_key()
if not API_KEY:
    print("⚠ 未找到 minimax/MIMO API Key，请检查 ~/.hermes/config.yaml")
    sys.exit(1)

TRANSLATE_PROMPTS = {
    "en→zh": "识别图片中的所有文字，翻译成简体中文。只输出翻译结果，保持原文排版顺序，不要添加任何解释。",
    "zh→en": "识别图片中的所有文字，翻译成英文。只输出翻译结果，保持原文排版顺序，不要添加任何解释。",
    "ja→zh": "识别图片中的所有日文文字，翻译成简体中文。只输出翻译结果，保持原文排版顺序，不要添加任何解释。",
    "ko→zh": "识别图片中的所有韩文文字，翻译成简体中文。只输出翻译结果，保持原文排版顺序，不要添加任何解释。",
    "auto→zh": "识别图片中的所有文字，如果已经是中文则原样输出，否则翻译成简体中文。只输出翻译结果，保持原文排版顺序，不要添加任何解释。",
}

MIN_INTERVAL = 3  # seconds, minimax 速率限制安全间隔 (token plan)
HANDLE_SIZE = 12  # resize handle pixel size
HANDLE_MARGIN = 6  # how far handles extend outside the region


# ═══════════════════════════════════════════════════════════════
#  Windows DPI 感知
# ═══════════════════════════════════════════════════════════════

def enable_dpi_awareness():
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════
#  屏幕截图（使用 mss，比 pyautogui 快 10 倍+）
# ═══════════════════════════════════════════════════════════════

_sct = mss.mss()

def capture_region(x, y, w, h):
    """Capture a screen region, return PIL Image."""
    monitor = {"left": x, "top": y, "width": w, "height": h}
    sct_img = _sct.grab(monitor)
    return Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")


# ═══════════════════════════════════════════════════════════════
#  翻译工作线程
# ═══════════════════════════════════════════════════════════════

class TranslateWorker(QThread):
    """Background thread: capture → OCR+translate via minimax → emit result."""
    result_ready = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._running = False
        self._region = (0, 0, 400, 300)
        self._prompt = TRANSLATE_PROMPTS["en→zh"]

    def configure(self, region, prompt):
        self._region = region
        self._prompt = prompt

    def stop(self):
        self._running = False

    def run(self):
        self._running = True
        while self._running:
            try:
                x, y, w, h = self._region
                if w < 20 or h < 20:
                    time.sleep(1)
                    continue

                img = capture_region(x, y, w, h)
                self._translate(img)
            except Exception as e:
                self.error_occurred.emit(str(e))
            time.sleep(MIN_INTERVAL)

    def _translate(self, img):
        # Resize for API (reduce payload, speed up)
        max_dim = 960
        if max(img.size) > max_dim:
            ratio = max_dim / max(img.size)
            img = img.resize(
                (int(img.width * ratio), int(img.height * ratio)),
                Image.LANCZOS
            )

        buf = BytesIO()
        img.save(buf, format="JPEG", quality=70)
        b64 = base64.b64encode(buf.getvalue()).decode()

        payload = json.dumps({
            "model": MODEL,
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": self._prompt},
                    {"type": "image_url", "image_url": {
                        "url": f"data:image/jpeg;base64,{b64}"
                    }}
                ]
            }],
            "max_tokens": 4096
        }).encode()

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}"
        }

        for attempt in range(3):
            try:
                resp = requests.post(
                    API_URL, headers=headers, data=payload, timeout=60
                )
                if resp.status_code == 200:
                    data = resp.json()
                    text = data["choices"][0]["message"]["content"]
                    if text and text.strip():
                        self.result_ready.emit(text.strip())
                    return
                elif resp.status_code == 429:
                    self.error_occurred.emit("Rate limited, waiting 30s...")
                    time.sleep(30)
                elif resp.status_code == 500:
                    if attempt < 2:
                        time.sleep(2)
                        continue
                    self.error_occurred.emit("Server error (500)")
                else:
                    self.error_occurred.emit(f"API {resp.status_code}")
                    return
            except requests.exceptions.Timeout:
                if attempt < 2:
                    time.sleep(2)
                    continue
                self.error_occurred.emit("API timeout")
            except Exception as e:
                self.error_occurred.emit(str(e))
                return


# ═══════════════════════════════════════════════════════════════
#  捕获区域（可拖动 + 可缩放）
# ═══════════════════════════════════════════════════════════════

class CaptureRegion(QWidget):
    """Transparent overlay for selecting/adjusting the screen capture area."""

    region_changed = pyqtSignal()  # emitted when user drags/resizes

    # Resize handle directions
    (DIR_NONE, DIR_TOP, DIR_BOTTOM, DIR_LEFT, DIR_RIGHT,
     DIR_TOP_LEFT, DIR_TOP_RIGHT, DIR_BOTTOM_LEFT, DIR_BOTTOM_RIGHT
     ) = range(9)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setGeometry(200, 200, 600, 400)

        self._resize_dir = self.DIR_NONE
        self._drag_start = None
        self._geo_start = None
        self._min_size = 100

        # Create resize handles
        self._handles = {}
        for direction in [
            self.DIR_TOP, self.DIR_BOTTOM, self.DIR_LEFT, self.DIR_RIGHT,
            self.DIR_TOP_LEFT, self.DIR_TOP_RIGHT,
            self.DIR_BOTTOM_LEFT, self.DIR_BOTTOM_RIGHT,
        ]:
            handle = QWidget(self)
            handle.setObjectName("resize_handle")
            handle.setFixedSize(HANDLE_SIZE, HANDLE_SIZE)
            handle.setCursor(self._handle_cursor(direction))
            handle.installEventFilter(self)
            self._handles[direction] = handle

        self._update_handle_positions()

    def _handle_cursor(self, d):
        cursors = {
            self.DIR_TOP: Qt.SizeVerCursor,
            self.DIR_BOTTOM: Qt.SizeVerCursor,
            self.DIR_LEFT: Qt.SizeHorCursor,
            self.DIR_RIGHT: Qt.SizeHorCursor,
            self.DIR_TOP_LEFT: Qt.SizeFDiagCursor,
            self.DIR_BOTTOM_RIGHT: Qt.SizeFDiagCursor,
            self.DIR_TOP_RIGHT: Qt.SizeBDiagCursor,
            self.DIR_BOTTOM_LEFT: Qt.SizeBDiagCursor,
        }
        return cursors.get(d, Qt.ArrowCursor)

    def _update_handle_positions(self):
        w, h = self.width(), self.height()
        s = HANDLE_SIZE
        m = HANDLE_MARGIN
        positions = {
            self.DIR_TOP: (w // 2 - s // 2, -m),
            self.DIR_BOTTOM: (w // 2 - s // 2, h - s + m),
            self.DIR_LEFT: (-m, h // 2 - s // 2),
            self.DIR_RIGHT: (w - s + m, h // 2 - s // 2),
            self.DIR_TOP_LEFT: (-m, -m),
            self.DIR_TOP_RIGHT: (w - s + m, -m),
            self.DIR_BOTTOM_LEFT: (-m, h - s + m),
            self.DIR_BOTTOM_RIGHT: (w - s + m, h - s + m),
        }
        for d, (hx, hy) in positions.items():
            self._handles[d].move(hx, hy)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_handle_positions()

    def eventFilter(self, obj, event):
        """Handle resize handle mouse events."""
        from PyQt5.QtCore import QEvent
        direction = None
        for d, handle in self._handles.items():
            if obj is handle:
                direction = d
                break

        if direction is not None:
            if event.type() == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                self._resize_dir = direction
                self._drag_start = QCursor.pos()
                self._geo_start = self.geometry()
                return True
            elif event.type() == QEvent.MouseButtonRelease:
                self._resize_dir = self.DIR_NONE
                self.region_changed.emit()
                return True

        return super().eventFilter(obj, event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._resize_dir = self.DIR_NONE
            self._drag_start = event.globalPos()
            self._geo_start = self.geometry()

    def mouseMoveEvent(self, event):
        if self._drag_start is None:
            return
        delta = event.globalPos() - self._drag_start
        geo = self._geo_start

        if self._resize_dir == self.DIR_NONE:
            # Drag to move
            self.move(geo.x() + delta.x(), geo.y() + delta.y())
        else:
            self._apply_resize(delta, geo)

    def mouseReleaseEvent(self, event):
        self._resize_dir = self.DIR_NONE
        self._drag_start = None
        self.region_changed.emit()

    def _apply_resize(self, delta, geo):
        x, y, w, h = geo.x(), geo.y(), geo.width(), geo.height()
        d = self._resize_dir
        min_s = self._min_size

        if d in (self.DIR_TOP, self.DIR_TOP_LEFT, self.DIR_TOP_RIGHT):
            new_h = max(min_s, h - delta.y())
            y = y + h - new_h
            h = new_h
        if d in (self.DIR_BOTTOM, self.DIR_BOTTOM_LEFT, self.DIR_BOTTOM_RIGHT):
            h = max(min_s, h + delta.y())
        if d in (self.DIR_LEFT, self.DIR_TOP_LEFT, self.DIR_BOTTOM_LEFT):
            new_w = max(min_s, w - delta.x())
            x = x + w - new_w
            w = new_w
        if d in (self.DIR_RIGHT, self.DIR_TOP_RIGHT, self.DIR_BOTTOM_RIGHT):
            w = max(min_s, w + delta.x())

        self.setGeometry(x, y, w, h)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Semi-transparent dark background
        painter.fillRect(self.rect(), QColor(30, 30, 30, 100))

        # Cyan border
        pen = QPen(QColor(0, 200, 255, 220), 2)
        painter.setPen(pen)
        painter.drawRect(self.rect().adjusted(1, 1, -1, -1))

        # Corner markers
        painter.setPen(QPen(QColor(0, 200, 255, 255), 3))
        corner_len = 20
        for (cx, cy, dx1, dy1, dx2, dy2) in [
            (0, 0, 1, 0, 0, 1),  # top-left
            (self.width(), 0, -1, 0, 0, 1),  # top-right
            (0, self.height(), 1, 0, 0, -1),  # bottom-left
            (self.width(), self.height(), -1, 0, 0, -1),  # bottom-right
        ]:
            painter.drawLine(cx, cy, cx + dx1 * corner_len, cy + dy1 * corner_len)
            painter.drawLine(cx, cy, cx + dx2 * corner_len, cy + dy2 * corner_len)

        # Label
        painter.setPen(QColor(0, 200, 255, 200))
        painter.setFont(QFont("Consolas", 9))
        label = f"翻译区域  {self.width()}×{self.height()}"
        painter.drawText(
            self.rect().adjusted(10, 10, -10, -10),
            Qt.AlignTop | Qt.AlignLeft | Qt.TextSingleLine,
            label
        )

        # Instructions
        painter.setPen(QColor(200, 200, 200, 140))
        painter.setFont(QFont("Microsoft YaHei", 8))
        painter.drawText(
            self.rect().adjusted(10, 28, -10, -10),
            Qt.AlignTop | Qt.AlignLeft | Qt.TextSingleLine,
            "拖动移动 · 边缘手柄缩放 · Ctrl+H 隐藏/显示"
        )


# ═══════════════════════════════════════════════════════════════
#  翻译覆盖层
# ═══════════════════════════════════════════════════════════════

class TranslationOverlay(QWidget):
    """Semi-transparent overlay that displays translated text."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._text = ""
        self._status = ""
        self.hide()

    def update_text(self, text):
        self._text = text
        self._status = ""
        self.update()
        self._auto_resize()

    def update_status(self, status):
        self._status = status
        self.update()

    def sync_position(self, capture_geo):
        """Position overlay to match capture region."""
        self.setGeometry(capture_geo)

    def _auto_resize(self):
        """Expand overlay height if text is too long."""
        if not self._text:
            return

        fm = QFontMetrics(QFont("Microsoft YaHei", 13))
        text_rect = fm.boundingRect(
            QRect(0, 0, self.width() - 30, 9999),
            Qt.TextWordWrap,
            self._text
        )
        needed = text_rect.height() + 50
        if needed > self.height():
            self.resize(self.width(), needed)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        # Dark semi-transparent background (60% opacity)
        painter.fillRect(self.rect(), QColor(20, 20, 20, 153))

        # Thin border
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))

        if self._text:
            # Title
            painter.setPen(QColor(0, 200, 255, 200))
            painter.setFont(QFont("Microsoft YaHei", 9, QFont.Bold))
            painter.drawText(
                self.rect().adjusted(12, 8, -12, -8),
                Qt.AlignTop | Qt.AlignLeft | Qt.TextSingleLine,
                "翻译结果"
            )

            # Translated text
            painter.setPen(QColor(255, 255, 255, 240))
            painter.setFont(QFont("Microsoft YaHei", 13))
            text_rect = self.rect().adjusted(12, 32, -12, -12)
            painter.drawText(
                text_rect,
                Qt.TextWordWrap,
                self._text
            )
        elif self._status:
            # Status message (loading, error)
            painter.setPen(QColor(255, 200, 0, 200))
            painter.setFont(QFont("Microsoft YaHei", 11))
            painter.drawText(
                self.rect().adjusted(12, 12, -12, -12),
                Qt.AlignCenter | Qt.TextWordWrap,
                self._status
            )
        else:
            # Waiting state
            painter.setPen(QColor(200, 200, 200, 120))
            painter.setFont(QFont("Microsoft YaHei", 11))
            painter.drawText(
                self.rect(),
                Qt.AlignCenter,
                "等待翻译..."
            )


# ═══════════════════════════════════════════════════════════════
#  控制面板
# ═══════════════════════════════════════════════════════════════

class ControlPanel(QWidget):
    """Main control window: start/stop translation, adjust settings."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("屏幕翻译器 — MiniMax M3")
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._drag_pos = None

        self.capture_region = CaptureRegion()
        self.overlay = TranslationOverlay()
        self.worker = TranslateWorker()
        self.worker.result_ready.connect(self._on_translation)
        self.worker.error_occurred.connect(self._on_error)

        self._setup_ui()
        self._setup_shortcuts()

        self.capture_region.region_changed.connect(self._on_region_changed)
        self.capture_region.show()
        self.overlay.show()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # Title bar
        title = QLabel("🌐 屏幕翻译器")
        title.setStyleSheet("color: #00c8ff; font-size: 15px; font-weight: bold; background: transparent;")
        layout.addWidget(title)

        # Language selector
        lang_row = QHBoxLayout()
        lang_label = QLabel("翻译方向:")
        lang_label.setStyleSheet("color: #ccc; background: transparent;")
        self.lang_combo = QComboBox()
        self.lang_combo.addItems(["en→zh", "zh→en", "ja→zh", "ko→zh", "auto→zh"])
        self.lang_combo.setStyleSheet("""
            QComboBox {
                background: #2a2a2a; color: #fff; border: 1px solid #555;
                padding: 4px 8px; border-radius: 4px; min-width: 100px;
            }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView {
                background: #2a2a2a; color: #fff; selection-background-color: #0066aa;
            }
        """)
        lang_row.addWidget(lang_label)
        lang_row.addWidget(self.lang_combo)
        layout.addLayout(lang_row)

        # Interval slider
        int_row = QHBoxLayout()
        int_label = QLabel("刷新间隔:")
        int_label.setStyleSheet("color: #ccc; background: transparent;")
        self.interval_slider = QSlider(Qt.Horizontal)
        self.interval_slider.setRange(MIN_INTERVAL, 15)
        self.interval_slider.setValue(4)
        self.interval_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                background: #444; height: 6px; border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #00c8ff; width: 16px; height: 16px;
                margin: -5px 0; border-radius: 8px;
            }
        """)
        self.interval_label = QLabel("4 秒")
        self.interval_label.setStyleSheet("color: #aaa; min-width: 35px; background: transparent;")
        self.interval_slider.valueChanged.connect(
            lambda v: self.interval_label.setText(f"{v} 秒")
        )
        int_row.addWidget(int_label)
        int_row.addWidget(self.interval_slider)
        int_row.addWidget(self.interval_label)
        layout.addLayout(int_row)

        # Buttons
        btn_row = QHBoxLayout()

        self.btn_start = QPushButton("▶ 开始翻译")
        self.btn_start.setStyleSheet("""
            QPushButton {
                background: #006633; color: #fff; border: none;
                padding: 8px 16px; border-radius: 6px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background: #008844; }
        """)
        self.btn_start.clicked.connect(self._toggle_translation)

        self.btn_hide = QPushButton("👁 隐藏")
        self.btn_hide.setStyleSheet("""
            QPushButton {
                background: #444; color: #ccc; border: none;
                padding: 8px 12px; border-radius: 6px; font-size: 12px;
            }
            QPushButton:hover { background: #555; }
        """)
        self.btn_hide.clicked.connect(self._toggle_visibility)

        self.btn_close = QPushButton("✕")
        self.btn_close.setStyleSheet("""
            QPushButton {
                background: #661111; color: #ff6666; border: none;
                padding: 8px 10px; border-radius: 6px; font-size: 12px; max-width: 30px;
            }
            QPushButton:hover { background: #882222; }
        """)
        self.btn_close.clicked.connect(self._cleanup_and_exit)

        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_hide)
        btn_row.addWidget(self.btn_close)
        layout.addLayout(btn_row)

        # Status
        self.status_label = QLabel("就绪 — 调整区域后点击「开始翻译」")
        self.status_label.setStyleSheet("color: #888; font-size: 11px; background: transparent;")
        layout.addWidget(self.status_label)

        self.setFixedSize(360, 190)
        self.setStyleSheet("""
            QWidget {
                background: #1a1a1a;
                border: 1px solid #333;
                border-radius: 10px;
            }
        """)

        # Position near top-right
        screen = QApplication.primaryScreen().geometry()
        self.move(screen.width() - 400, 60)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+H"), self, self._toggle_visibility)
        QShortcut(QKeySequence("Ctrl+Q"), self, self._cleanup_and_exit)
        QShortcut(QKeySequence("Ctrl+S"), self, self._toggle_translation)

    # ─── Drag title bar ───

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._drag_pos and event.buttons() & Qt.LeftButton:
            self.move(event.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, event):
        self._drag_pos = None

    # ─── Translation control ───

    def _toggle_translation(self):
        if self.worker.isRunning():
            self._stop_translation()
        else:
            self._start_translation()

    def _start_translation(self):
        region = self.capture_region.geometry()
        prompt_key = self.lang_combo.currentText()
        prompt = TRANSLATE_PROMPTS.get(prompt_key, TRANSLATE_PROMPTS["en→zh"])
        interval = self.interval_slider.value()

        self.worker.configure(
            (region.x(), region.y(), region.width(), region.height()),
            prompt
        )
        self.worker.start()

        self.btn_start.setText("⏹ 停止翻译")
        self.btn_start.setStyleSheet("""
            QPushButton {
                background: #663300; color: #ffaa00; border: none;
                padding: 8px 16px; border-radius: 6px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background: #884400; }
        """)
        self.lang_combo.setEnabled(False)
        self.status_label.setText("翻译中... 每隔 {} 秒刷新".format(interval))
        self.overlay.update_status("正在翻译...")

    def _stop_translation(self):
        self.worker.stop()
        self.worker.wait(3000)

        self.btn_start.setText("▶ 开始翻译")
        self.btn_start.setStyleSheet("""
            QPushButton {
                background: #006633; color: #fff; border: none;
                padding: 8px 16px; border-radius: 6px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background: #008844; }
        """)
        self.lang_combo.setEnabled(True)
        self.status_label.setText("已停止")

    def _on_translation(self, text):
        geo = self.capture_region.geometry()
        self.overlay.sync_position(geo)
        self.overlay.update_text(text)
        self.status_label.setText(
            f"已翻译 · {time.strftime('%H:%M:%S')} · {len(text)} 字"
        )

    def _on_error(self, msg):
        self.status_label.setText(f"⚠ {msg}")
        self.overlay.update_status(f"⚠ {msg}")

    def _on_region_changed(self):
        """Sync overlay position when capture region moves/resizes."""
        geo = self.capture_region.geometry()
        self.overlay.sync_position(geo)
        if self.worker.isRunning():
            self.worker.configure(
                (geo.x(), geo.y(), geo.width(), geo.height()),
                self.worker._prompt
            )

    # ─── Visibility ───

    def _toggle_visibility(self):
        if self.capture_region.isVisible():
            self.capture_region.hide()
            self.overlay.hide()
            self.btn_hide.setText("👁 显示")
        else:
            self.capture_region.show()
            self.overlay.show()
            self.btn_hide.setText("👁 隐藏")

    def _cleanup_and_exit(self):
        self._stop_translation()
        self.capture_region.close()
        self.overlay.close()
        QApplication.quit()


# ═══════════════════════════════════════════════════════════════
#  启动
# ═══════════════════════════════════════════════════════════════

def main():
    enable_dpi_awareness()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # Dark tooltip style
    app.setStyleSheet("""
        QToolTip {
            background: #333; color: #fff; border: 1px solid #555;
            padding: 4px; border-radius: 3px;
        }
    """)

    panel = ControlPanel()
    panel.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
