import sys
import os
import sqlite3
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                            QFileDialog, QFrame, QLabel, QPushButton, QMessageBox,
                            QSplitter, QTableWidget, QTableWidgetItem, QHeaderView,
                            QLineEdit, QAbstractItemView, QAbstractScrollArea,
                            QMenu, QSlider)
from PySide6.QtCore import Qt, QSettings, QFileInfo, QSize, Signal, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QFontMetrics, QAction, QKeySequence


class ProjectInfo:
    """项目信息元数据（集中管理所有项目相关信息）"""
    VERSION = "4.8.0"
    BUILD_DATE = "2026-08-07"
    # BUILD_DATE = datetime.now().strftime("%Y-%m-%d")  # 修改为动态获取当前日期
    AUTHOR = "杜玛"
    LICENSE = "MIT"
    COPYRIGHT = "© 永久 杜玛"
    URL = "https://github.com/duma520"
    MAINTAINER_EMAIL = "不提供"
    NAME = "多文件十六进制比对工具"
    DESCRIPTION = "多文件十六进制比对工具，支持多文件同时打开和比对，提供编辑模式和差异高亮显示。支持多基准比对模式。"
    HELP_TEXT = """
使用说明:

"""


    @classmethod
    def get_metadata(cls) -> dict:
        """获取主要元数据字典"""
        return {
            'version': cls.VERSION,
            'author': cls.AUTHOR,
            'license': cls.LICENSE,
            'url': cls.URL
        }


    @classmethod
    def get_header(cls) -> str:
        """生成标准化的项目头信息"""
        return f"{cls.NAME} {cls.VERSION} | {cls.LICENSE} License | {cls.URL}"

# 马卡龙色系定义
class MacaronColors:
    # 粉色系
    SAKURA_PINK = '#FFB7CE'  # 樱花粉
    ROSE_PINK = '#FF9AA2'    # 玫瑰粉
    # 蓝色系
    SKY_BLUE = '#A2E1F6'     # 天空蓝
    LILAC_MIST = '#E6E6FA'   # 淡丁香
    # 绿色系
    MINT_GREEN = '#B5EAD7'   # 薄荷绿
    APPLE_GREEN = '#D4F1C7'  # 苹果绿
    # 黄色/橙色系
    LEMON_YELLOW = '#FFEAA5' # 柠檬黄
    BUTTER_CREAM = '#FFF8B8' # 奶油黄
    PEACH_ORANGE = '#FFDAC1' # 蜜桃橙
    # 紫色系
    LAVENDER = '#C7CEEA'     # 薰衣草紫
    TARO_PURPLE = '#D8BFD8'  # 香芋紫
    # 中性色
    CARAMEL_CREAM = '#F0E6DD' # 焦糖奶霜


# ============================================================
# 差异导航条 — 可视化差异分布，点击快速跳转
# ============================================================
class DiffNavigatorBar(QWidget):
    """差异分布概览条：用色块标注差异位置，点击跳转"""
    clicked = Signal(int)  # 发出目标字节偏移量

    def __init__(self, parent=None):
        super().__init__(parent)
        self._total_bytes = 0
        self._diff_positions = set()
        self.setFixedHeight(22)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("差异分布概览 — 点击跳转到差异位置")

    def set_data(self, total_bytes, diff_set):
        self._total_bytes = max(total_bytes, 1)
        self._diff_positions = diff_set or set()
        self.update()

    def paintEvent(self, event):
        if self._total_bytes == 0:
            return
        painter = QPainter(self)
        w = self.width()
        h = self.height()

        # 背景
        painter.fillRect(0, 0, w, h, QColor(240, 240, 240))

        if not self._diff_positions:
            painter.setPen(QColor(150, 150, 150))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "无差异")
            return

        # 用色块绘制差异分布（合并连续差异为块）
        sorted_diffs = sorted(self._diff_positions)
        scale = w / self._total_bytes

        blocks = []
        start = sorted_diffs[0]
        end = sorted_diffs[0]
        for p in sorted_diffs[1:]:
            if p <= end + 15:  # 相邻差异合并
                end = p
            else:
                blocks.append((start, end))
                start = end = p
        blocks.append((start, end))

        for s, e in blocks:
            x1 = int(s * scale)
            x2 = int((e + 1) * scale)
            painter.fillRect(x1, 2, max(x2 - x1, 2), h - 4, QColor(255, 120, 100))

        # 边框
        painter.setPen(QColor(180, 180, 180))
        painter.drawRect(0, 0, w - 1, h - 1)

    def mousePressEvent(self, event):
        if self._total_bytes == 0:
            return
        x = event.position().x()
        ratio = x / self.width()
        target = int(ratio * self._total_bytes)
        # 找最近的差异位置
        if self._diff_positions:
            diffs = sorted(self._diff_positions)
            nearest = min(diffs, key=lambda d: abs(d - target))
            self.clicked.emit(nearest)
        super().mousePressEvent(event)


# ============================================================
# 高性能十六进制视图组件 — 使用 QPainter 直接绘制，不创建大量 Widget
# ============================================================
class HexViewWidget(QAbstractScrollArea):
    """使用QPainter直接绘制十六进制视图，只渲染可见行，解决大文件卡顿问题"""

    BYTES_PER_LINE = 16
    CHAR_WIDTH = 9      # 等宽字体每字符近似宽度
    LINE_HEIGHT = 19    # 行高
    MARGIN = 5

    # 布局常量（在 __init__ 中根据字体实际计算）
    ADDR_CHARS = 8  # 地址列字符数

    # 颜色定义
    COLOR_BG = QColor(255, 255, 255)
    COLOR_ADDR = QColor(100, 100, 100)
    COLOR_HEX = QColor(0, 0, 0)
    COLOR_ASCII = QColor(0, 0, 80)
    COLOR_DIFF_LINE = QColor(255, 255, 210)
    COLOR_DIFF_BYTE = QColor(255, 200, 200)
    COLOR_SELECTION = QColor(180, 210, 255)

    byte_changed = Signal(int, int)  # pos, new_byte

    def __init__(self, file_path, data, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self.data = data  # bytearray 引用
        self._edit_mode = False
        self._diff_positions = set()  # 差异字节位置集合
        self._cursor_pos = -1  # 光标所在字节位置
        self._edit_widget = None
        self._editing_pos = -1
        self._undo_stack = []  # [(pos, old_byte), ...]

        # 字体设置
        self._font = QFont("Courier New", 10)
        self._fm = QFontMetrics(self._font)
        self._char_w = self._fm.horizontalAdvance("0")
        self._line_h = self._fm.height() + 4

        # 预计算各列宽度
        self._addr_w = self._char_w * (self.ADDR_CHARS + 2)
        self._hex_byte_w = self._char_w * 2
        self._hex_gap = self._char_w
        self._ascii_char_w = self._char_w
        self._section_gap = self._char_w * 3

        # 总行数
        self._total_lines = max(1, (len(data) + self.BYTES_PER_LINE - 1) // self.BYTES_PER_LINE)

        # 计算内容总宽度
        self._content_w = (self.MARGIN * 2 + self._addr_w + self._section_gap
                           + (self._hex_byte_w + self._hex_gap) * self.BYTES_PER_LINE
                           + self._section_gap + self._ascii_char_w * self.BYTES_PER_LINE)

        # 滚动条
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._update_scroll_range()

        # 追踪鼠标
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)

        # 接收焦点（键盘导航用）
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _update_scroll_range(self):
        """更新滚动条范围"""
        vp_h = self.viewport().height()
        visible_lines = max(1, vp_h // self._line_h)
        v_max = max(0, self._total_lines - visible_lines)
        self.verticalScrollBar().setRange(0, v_max)
        self.verticalScrollBar().setPageStep(visible_lines)
        self.verticalScrollBar().setSingleStep(1)

        vp_w = self.viewport().width()
        h_max = max(0, self._content_w - vp_w)
        self.horizontalScrollBar().setRange(0, h_max)
        self.horizontalScrollBar().setPageStep(vp_w)
        self.horizontalScrollBar().setSingleStep(self._char_w)

    # ---- 公开接口 ----
    @property
    def edit_mode(self):
        return self._edit_mode

    @edit_mode.setter
    def edit_mode(self, enabled):
        self._edit_mode = enabled
        if not enabled:
            self._finish_editing()
        self.viewport().update()

    def set_diff_positions(self, positions):
        """设置差异位置集合，触发重绘"""
        self._diff_positions = set(positions) if positions else set()
        self.viewport().update()

    def set_cursor_pos(self, pos):
        """设置光标位置"""
        self._cursor_pos = pos
        self.viewport().update()

    def goto_offset(self, offset):
        """跳转到指定字节偏移量"""
        offset = max(0, min(offset, len(self.data) - 1))
        self._cursor_pos = offset
        line = offset // self.BYTES_PER_LINE
        self.verticalScrollBar().setValue(line)
        self.viewport().update()

    def get_sorted_diffs(self):
        """返回排序后的差异位置列表"""
        return sorted(self._diff_positions) if self._diff_positions else []

    def set_zoom(self, font_size):
        """设置缩放级别（字体大小 6~24）"""
        font_size = max(6, min(24, font_size))
        self._font = QFont("Courier New", font_size)
        self._fm = QFontMetrics(self._font)
        self._char_w = self._fm.horizontalAdvance("0")
        self._line_h = self._fm.height() + 4
        # 重新计算布局
        self._addr_w = self._char_w * (self.ADDR_CHARS + 2)
        self._hex_byte_w = self._char_w * 2
        self._hex_gap = self._char_w
        self._ascii_char_w = self._char_w
        self._section_gap = self._char_w * 3
        self._content_w = (self.MARGIN * 2 + self._addr_w + self._section_gap
                           + (self._hex_byte_w + self._hex_gap) * self.BYTES_PER_LINE
                           + self._section_gap + self._ascii_char_w * self.BYTES_PER_LINE)
        self._update_scroll_range()
        self.viewport().update()

    # ---- QAbstractScrollArea 重写 ----
    def viewportEvent(self, event):
        if event.type() == event.Type.Wheel:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                # Ctrl+滚轮 → 缩放
                delta = event.angleDelta().y()
                current_size = self._font.pointSize()
                new_size = current_size + (1 if delta > 0 else -1)
                self.set_zoom(new_size)
                return True
            delta = event.angleDelta().y()
            sb = self.verticalScrollBar()
            step = max(1, sb.pageStep() // 10)
            sb.setValue(sb.value() - (delta // 120) * step)
            return True
        return super().viewportEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_scroll_range()
        self.viewport().update()

    def scrollContentsBy(self, dx, dy):
        self.viewport().scroll(dx, dy)
        self.viewport().update()

    def paintEvent(self, event):
        painter = QPainter(self.viewport())
        painter.setFont(self._font)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        vp_rect = self.viewport().rect()
        scroll_x = self.horizontalScrollBar().value()

        first_line = self.verticalScrollBar().value()
        visible_lines = max(1, vp_rect.height() // self._line_h) + 1
        last_line = min(first_line + visible_lines, self._total_lines)

        # 背景
        painter.fillRect(vp_rect, self.COLOR_BG)

        # 每行绘制
        for line_idx in range(first_line, last_line):
            y = self.MARGIN + (line_idx - first_line) * self._line_h
            offset = line_idx * self.BYTES_PER_LINE

            # 检查该行是否有差异字节
            has_diff = any((offset + i) in self._diff_positions for i in range(self.BYTES_PER_LINE))

            # 行背景
            if has_diff:
                painter.fillRect(0, y, vp_rect.width() + scroll_x, self._line_h, self.COLOR_DIFF_LINE)

            # ----- 地址列 -----
            addr_x = self.MARGIN - scroll_x
            painter.setPen(self.COLOR_ADDR)
            painter.drawText(addr_x, y, self._addr_w, self._line_h,
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             f"{offset:08X}")

            # ----- 十六进制列 -----
            hex_x = self.MARGIN + self._addr_w + self._section_gap - scroll_x
            for i in range(self.BYTES_PER_LINE):
                pos = offset + i
                bx = hex_x + i * (self._hex_byte_w + self._hex_gap)

                if pos >= len(self.data):
                    break

                byte_val = self.data[pos]

                # 差异背景
                if pos in self._diff_positions:
                    painter.fillRect(bx - 1, y, self._hex_byte_w + 2, self._line_h, self.COLOR_DIFF_BYTE)

                # 光标高亮
                if pos == self._cursor_pos:
                    painter.fillRect(bx - 1, y, self._hex_byte_w + 2, self._line_h, self.COLOR_SELECTION)

                painter.setPen(self.COLOR_HEX)
                painter.drawText(bx, y, self._hex_byte_w, self._line_h,
                                 Qt.AlignmentFlag.AlignCenter, f"{byte_val:02X}")

            # ----- ASCII 列 -----
            ascii_x = hex_x + self.BYTES_PER_LINE * (self._hex_byte_w + self._hex_gap) + self._section_gap
            for i in range(self.BYTES_PER_LINE):
                pos = offset + i
                ax = ascii_x + i * self._ascii_char_w

                if pos >= len(self.data):
                    break

                byte_val = self.data[pos]
                ch = chr(byte_val) if 32 <= byte_val <= 126 else "."

                if pos in self._diff_positions:
                    painter.fillRect(ax, y, self._ascii_char_w, self._line_h, self.COLOR_DIFF_BYTE)

                if pos == self._cursor_pos:
                    painter.fillRect(ax, y, self._ascii_char_w, self._line_h, self.COLOR_SELECTION)

                painter.setPen(self.COLOR_ASCII)
                painter.drawText(ax, y, self._ascii_char_w, self._line_h,
                                 Qt.AlignmentFlag.AlignCenter, ch)

        # 文件尾部空白区域
        end_y = self.MARGIN + (last_line - first_line) * self._line_h
        if end_y < vp_rect.height():
            painter.fillRect(0, end_y, vp_rect.width(), vp_rect.height() - end_y, self.COLOR_BG)

    # ---- 鼠标事件 ----
    def _hit_test(self, pos):
        """根据视口坐标计算命中的字节位置，返回 (byte_position, section) 或 (-1, None)"""
        scroll_x = self.horizontalScrollBar().value()
        first_line = self.verticalScrollBar().value()
        x = pos.x() + scroll_x
        line_idx = first_line + (pos.y() - self.MARGIN) // self._line_h

        if line_idx < 0 or line_idx >= self._total_lines:
            return -1, None

        hex_x = self.MARGIN + self._addr_w + self._section_gap
        byte_idx = int((x - hex_x) / (self._hex_byte_w + self._hex_gap))
        if 0 <= byte_idx < self.BYTES_PER_LINE:
            byte_pos = line_idx * self.BYTES_PER_LINE + byte_idx
            if byte_pos < len(self.data):
                return byte_pos, "hex"

        ascii_x = hex_x + self.BYTES_PER_LINE * (self._hex_byte_w + self._hex_gap) + self._section_gap
        ascii_idx = int((x - ascii_x) / self._ascii_char_w)
        if 0 <= ascii_idx < self.BYTES_PER_LINE:
            byte_pos = line_idx * self.BYTES_PER_LINE + ascii_idx
            if byte_pos < len(self.data):
                return byte_pos, "ascii"

        return -1, None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            byte_pos, _ = self._hit_test(event.position().toPoint())
            if byte_pos >= 0:
                self._cursor_pos = byte_pos
                self.viewport().update()
                if self._edit_mode:
                    self._start_editing(byte_pos)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)

    # ---- 键盘事件 ----
    def keyPressEvent(self, event):
        if self._edit_widget and self._edit_widget.isVisible():
            super().keyPressEvent(event)
            return

        moved = False
        if event.key() == Qt.Key.Key_Down:
            self._cursor_pos = min(self._cursor_pos + self.BYTES_PER_LINE, len(self.data) - 1)
            moved = True
        elif event.key() == Qt.Key.Key_Up:
            self._cursor_pos = max(self._cursor_pos - self.BYTES_PER_LINE, 0)
            moved = True
        elif event.key() == Qt.Key.Key_Right:
            self._cursor_pos = min(self._cursor_pos + 1, len(self.data) - 1)
            moved = True
        elif event.key() == Qt.Key.Key_Left:
            self._cursor_pos = max(self._cursor_pos - 1, 0)
            moved = True
        elif event.key() == Qt.Key.Key_PageDown:
            visible = max(1, self.viewport().height() // self._line_h)
            self._cursor_pos = min(self._cursor_pos + visible * self.BYTES_PER_LINE, len(self.data) - 1)
            moved = True
        elif event.key() == Qt.Key.Key_PageUp:
            visible = max(1, self.viewport().height() // self._line_h)
            self._cursor_pos = max(self._cursor_pos - visible * self.BYTES_PER_LINE, 0)
            moved = True

        if moved:
            self._ensure_cursor_visible()
            self.viewport().update()

        super().keyPressEvent(event)

    def _ensure_cursor_visible(self):
        """确保光标所在行可见"""
        if self._cursor_pos < 0:
            return
        line = self._cursor_pos // self.BYTES_PER_LINE
        sb = self.verticalScrollBar()
        first = sb.value()
        visible = max(1, self.viewport().height() // self._line_h)
        if line < first:
            sb.setValue(line)
        elif line >= first + visible:
            sb.setValue(line - visible + 1)

    # ---- 编辑模式 ----
    def _start_editing(self, byte_pos):
        """在指定字节位置显示一个 QLineEdit 进行编辑"""
        self._finish_editing()

        self._editing_pos = byte_pos
        byte_val = self.data[byte_pos]

        # 计算编辑框位置
        line = byte_pos // self.BYTES_PER_LINE
        col = byte_pos % self.BYTES_PER_LINE
        first_line = self.verticalScrollBar().value()
        y = self.MARGIN + (line - first_line) * self._line_h
        scroll_x = self.horizontalScrollBar().value()
        hex_x = self.MARGIN + self._addr_w + self._section_gap
        x = hex_x + col * (self._hex_byte_w + self._hex_gap) - scroll_x

        edit = QLineEdit(f"{byte_val:02X}", self.viewport())
        edit.setFont(self._font)
        edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        edit.setFixedSize(self._hex_byte_w + 4, self._line_h)
        edit.setMaxLength(2)
        edit.move(x - 2, y)
        edit.selectAll()
        edit.setFocus()
        edit.editingFinished.connect(self._on_edit_finished)
        edit.installEventFilter(self)

        self._edit_widget = edit
        edit.show()

    def _finish_editing(self):
        """结束编辑"""
        if self._edit_widget:
            self._edit_widget.removeEventFilter(self)
            self._edit_widget.deleteLater()
            self._edit_widget = None
        self._editing_pos = -1

    def _on_edit_finished(self):
        """编辑完成回调"""
        if not self._edit_widget or self._editing_pos < 0:
            return
        text = self._edit_widget.text().strip().upper()
        try:
            if len(text) == 2:
                new_byte = int(text, 16)
                old_byte = self.data[self._editing_pos]
                if new_byte != old_byte:
                    self._undo_stack.append((self._editing_pos, old_byte))
                    self.data[self._editing_pos] = new_byte
                    self.byte_changed.emit(self._editing_pos, new_byte)
        except ValueError:
            pass
        self._finish_editing()
        self.viewport().update()

    def undo(self):
        """撤销上一次编辑"""
        if not self._undo_stack:
            return False
        pos, old_byte = self._undo_stack.pop()
        self.data[pos] = old_byte
        self._cursor_pos = pos
        self._ensure_cursor_visible()
        self.viewport().update()
        self.byte_changed.emit(pos, old_byte)
        return True

    def eventFilter(self, obj, event):
        """拦截编辑框的 Escape 键"""
        if obj == self._edit_widget and event.type() == event.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self._finish_editing()
                self.viewport().update()
                return True
        return super().eventFilter(obj, event)


class HexViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{ProjectInfo.NAME} {ProjectInfo.VERSION} (Build: {ProjectInfo.BUILD_DATE})")
        self.setMinimumSize(900, 650)

        # 支持拖放文件
        self.setAcceptDrops(True)

        # 初始化数据库
        self.init_db()

        # 设置图标
        if os.path.exists("icon.ico"):
            self.setWindowIcon(QIcon("icon.ico"))

        # 创建UI（先显示窗口，再延迟加载设置以加速启动）
        self.init_ui()

        # 延迟加载设置 — 让窗口先出现
        QTimer.singleShot(50, self.load_settings)

        # 焦点模式状态
        self._focused_file = None
        self._hidden_frames = []  # 焦点模式下隐藏的帧
        self._zoom_level = 10

    def init_db(self):
        self.db_conn = sqlite3.connect("hexviewer_settings.db")
        self.db_cursor = self.db_conn.cursor()

        self.db_cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)

        self.db_cursor.execute("""
        CREATE TABLE IF NOT EXISTS file_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE,
            last_opened TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        self.db_conn.commit()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)

        # ---- 顶部按钮栏 ----
        button_layout = QHBoxLayout()
        button_layout.setSpacing(4)

        self.open_button = QPushButton("📂 打开文件")
        self.open_button.clicked.connect(self.open_files)
        button_layout.addWidget(self.open_button)

        self.clear_button = QPushButton("🗑 清除所有")
        self.clear_button.clicked.connect(self.clear_all)
        button_layout.addWidget(self.clear_button)

        button_layout.addWidget(self._make_separator())

        self.compare_button = QPushButton("🔍 开始比对")
        self.compare_button.clicked.connect(self.compare_files)
        self.compare_button.setEnabled(False)
        button_layout.addWidget(self.compare_button)

        self.multi_compare_button = QPushButton("🔎 多基准比对")
        self.multi_compare_button.clicked.connect(self.compare_multiple_files)
        self.multi_compare_button.setEnabled(False)
        button_layout.addWidget(self.multi_compare_button)

        button_layout.addWidget(self._make_separator())

        # 差异导航
        self.prev_diff_button = QPushButton("◀ 上一差异")
        self.prev_diff_button.clicked.connect(self._goto_prev_diff)
        self.prev_diff_button.setEnabled(False)
        self.prev_diff_button.setToolTip("跳转到上一个差异位置 (Shift+F3)")
        button_layout.addWidget(self.prev_diff_button)

        self.next_diff_button = QPushButton("下一差异 ▶")
        self.next_diff_button.clicked.connect(self._goto_next_diff)
        self.next_diff_button.setEnabled(False)
        self.next_diff_button.setToolTip("跳转到下一个差异位置 (F3)")
        button_layout.addWidget(self.next_diff_button)

        self.diff_count_label = QLabel("")
        self.diff_count_label.setStyleSheet("color: #CC3300; font-weight: bold; padding: 0 5px;")
        button_layout.addWidget(self.diff_count_label)

        button_layout.addWidget(self._make_separator())

        # 跳转到偏移量
        goto_label = QLabel("跳转:")
        button_layout.addWidget(goto_label)
        self.goto_input = QLineEdit()
        self.goto_input.setPlaceholderText("十六进制偏移")
        self.goto_input.setFixedWidth(100)
        self.goto_input.setMaxLength(16)
        self.goto_input.returnPressed.connect(self._goto_offset)
        button_layout.addWidget(self.goto_input)
        goto_btn = QPushButton("Go")
        goto_btn.setFixedWidth(35)
        goto_btn.clicked.connect(self._goto_offset)
        button_layout.addWidget(goto_btn)

        button_layout.addWidget(self._make_separator())

        # 同步滚动开关
        self.sync_scroll_button = QPushButton("🔗 同步滚动: 开")
        self.sync_scroll_button.setCheckable(True)
        self.sync_scroll_button.setChecked(True)
        self.sync_scroll_button.toggled.connect(self._toggle_sync_scroll)
        self.sync_scroll_button.setToolTip("切换滚动同步 (Ctrl+Y)")
        button_layout.addWidget(self.sync_scroll_button)

        button_layout.addWidget(self._make_separator())

        self.edit_button = QPushButton("✏ 编辑模式")
        self.edit_button.setCheckable(True)
        self.edit_button.clicked.connect(self.toggle_edit_mode)
        button_layout.addWidget(self.edit_button)

        self.undo_button = QPushButton("↩ 撤销")
        self.undo_button.clicked.connect(self._undo_last_edit)
        self.undo_button.setEnabled(False)
        self.undo_button.setToolTip("撤销上一次编辑 (Ctrl+Z)")
        button_layout.addWidget(self.undo_button)

        self.save_button = QPushButton("💾 保存文件")
        self.save_button.clicked.connect(self.save_current_file)
        self.save_button.setEnabled(False)
        button_layout.addWidget(self.save_button)

        button_layout.addStretch()
        main_layout.addLayout(button_layout)

        # ---- 缩放控制栏 ----
        zoom_layout = QHBoxLayout()
        zoom_layout.setSpacing(4)

        self.focus_button = QPushButton("🔍 聚焦查看")
        self.focus_button.setCheckable(True)
        self.focus_button.toggled.connect(self._toggle_focus_mode)
        self.focus_button.setToolTip("双击文件列表也可切换聚焦模式")
        zoom_layout.addWidget(self.focus_button)

        zoom_layout.addStretch()

        zoom_label = QLabel("缩放:")
        zoom_layout.addWidget(zoom_label)
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(6, 24)
        self.zoom_slider.setValue(10)
        self.zoom_slider.setFixedWidth(120)
        self.zoom_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.zoom_slider.setTickInterval(2)
        self.zoom_slider.valueChanged.connect(self._on_zoom_changed)
        self.zoom_slider.setToolTip("缩放 (Ctrl+滚轮)")
        zoom_layout.addWidget(self.zoom_slider)
        self.zoom_label_val = QLabel("10pt")
        self.zoom_label_val.setFixedWidth(35)
        zoom_layout.addWidget(self.zoom_label_val)

        main_layout.addLayout(zoom_layout)

        # ---- 主分割器 ----
        self.main_splitter = QSplitter(Qt.Orientation.Vertical)

        # 文件列表（支持右键菜单）
        self.file_list_widget = QTableWidget()
        self.file_list_widget.setColumnCount(3)
        self.file_list_widget.setHorizontalHeaderLabels(["文件名", "大小", "路径"])
        self.file_list_widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.file_list_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.file_list_widget.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.file_list_widget.verticalHeader().setVisible(False)
        self.file_list_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.file_list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.file_list_widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.file_list_widget.itemSelectionChanged.connect(self.file_selected)
        self.file_list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.file_list_widget.customContextMenuRequested.connect(self._file_list_context_menu)
        self.file_list_widget.cellDoubleClicked.connect(self._on_file_double_clicked)

        # 十六进制视图容器（左右并排显示）
        self.hex_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.hex_splitter.setHandleWidth(3)

        self.main_splitter.addWidget(self.file_list_widget)
        self.main_splitter.addWidget(self.hex_splitter)
        self.main_splitter.setSizes([100, 500])
        main_layout.addWidget(self.main_splitter)

        # ---- 差异导航条 ----
        self.diff_navigator = DiffNavigatorBar()
        self.diff_navigator.clicked.connect(self._on_navigator_clicked)
        self.diff_navigator.setVisible(False)
        main_layout.addWidget(self.diff_navigator)

        # ---- 状态栏 ----
        self.status_bar = self.statusBar()
        self.status_label = QLabel("就绪 | 支持拖放文件 | F3/Shift+F3 导航差异")
        self.status_bar.addWidget(self.status_label)

        # ---- 数据存储 ----
        self.file_data = {}        # file_path -> bytearray
        self.hex_widgets = {}      # file_path -> HexViewWidget
        self.file_paths = []       # 保持添加顺序
        self.edit_mode = False
        self._scroll_sync_enabled = True
        self._scroll_sync_blocked = False
        self._diff_set = set()     # 当前差异集
        self._current_diff_index = -1  # 当前导航到的差异索引

        # ---- 键盘快捷键 ----
        self._setup_shortcuts()

    def _make_separator(self):
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedWidth(2)
        return sep

    def _setup_shortcuts(self):
        # F3: 下一差异
        a_next = QAction("下一差异", self)
        a_next.setShortcut(QKeySequence(Qt.Key.Key_F3))
        a_next.triggered.connect(self._goto_next_diff)
        self.addAction(a_next)

        # Shift+F3: 上一差异
        a_prev = QAction("上一差异", self)
        a_prev.setShortcut(QKeySequence(Qt.Modifier.SHIFT | Qt.Key.Key_F3))
        a_prev.triggered.connect(self._goto_prev_diff)
        self.addAction(a_prev)

        # Ctrl+G: 跳转到偏移量
        a_goto = QAction("跳转偏移", self)
        a_goto.setShortcut(QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_G))
        a_goto.triggered.connect(self._focus_goto_input)
        self.addAction(a_goto)

        # Ctrl+Y: 切换同步滚动
        a_sync = QAction("切换同步滚动", self)
        a_sync.setShortcut(QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Y))
        a_sync.triggered.connect(lambda: self.sync_scroll_button.toggle())
        self.addAction(a_sync)

        # Ctrl+Z: 撤销编辑
        a_undo = QAction("撤销编辑", self)
        a_undo.setShortcut(QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Z))
        a_undo.triggered.connect(self._undo_last_edit)
        self.addAction(a_undo)

    # ======================== 设置持久化 ========================
    def load_settings(self):
        if not hasattr(self, 'settings'):
            self.settings = QSettings("HexViewer", "MultiFileHexCompare")
        self.last_dir = self.settings.value("last_dir", "", str)
        size = self.settings.value("window_size", QSize(900, 650))
        self.resize(size)
        pos = self.settings.value("window_position")
        if pos:
            self.move(pos)
        splitter_sizes = self.settings.value("splitter_sizes")
        if splitter_sizes:
            self.main_splitter.setSizes([int(s) for s in splitter_sizes])

    def save_settings(self):
        if not hasattr(self, 'settings'):
            return
        self.settings.setValue("window_size", self.size())
        self.settings.setValue("window_position", self.pos())
        self.settings.setValue("splitter_sizes", self.main_splitter.sizes())
        self.settings.setValue("last_dir", self.last_dir)

    # ======================== 文件操作 ========================
    def open_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择要比对的文件", self.last_dir, "所有文件 (*.*)")
        if not files:
            return
        self.last_dir = os.path.dirname(files[0])
        for fp in files:
            self.add_file(fp)
        self._update_button_states()

    def add_file(self, file_path):
        try:
            # 去重
            for i in range(self.file_list_widget.rowCount()):
                if self.file_list_widget.item(i, 2).text() == file_path:
                    return

            file_info = QFileInfo(file_path)
            file_name = file_info.fileName()
            file_size = file_info.size()

            # 读取文件（大文件流式读取优化：先读头部快速反馈，再异步……这里保持读取全量到内存）
            with open(file_path, 'rb') as f:
                content = bytearray(f.read())

            self.file_data[file_path] = content
            self.file_paths.append(file_path)

            # 文件列表
            row = self.file_list_widget.rowCount()
            self.file_list_widget.insertRow(row)
            self.file_list_widget.setItem(row, 0, QTableWidgetItem(file_name))
            self.file_list_widget.setItem(row, 1, QTableWidgetItem(self.format_size(file_size)))
            self.file_list_widget.setItem(row, 2, QTableWidgetItem(file_path))

            # 数据库记录
            self.db_cursor.execute(
                "INSERT OR REPLACE INTO file_history (file_path) VALUES (?)", (file_path,))
            self.db_conn.commit()

            # 创建高性能十六进制视图
            self._create_hex_widget(file_path)

        except Exception as e:
            QMessageBox.warning(self, "错误", f"无法打开文件 {file_path}:\n{str(e)}")

    def _create_hex_widget(self, file_path):
        """创建 HexViewWidget 并添加到左右并排布局中"""
        file_name = os.path.basename(file_path)
        content = self.file_data[file_path]

        hex_widget = HexViewWidget(file_path, content)
        hex_widget.edit_mode = self.edit_mode

        # 滚动同步
        hex_widget.verticalScrollBar().valueChanged.connect(
            lambda v, fp=file_path: self._sync_scroll(fp, v))
        hex_widget.byte_changed.connect(self._on_byte_changed)

        self.hex_widgets[file_path] = hex_widget

        # 包装到带标签和边框的列容器中
        col_frame = QFrame()
        col_frame.setFrameShape(QFrame.Shape.StyledPanel)
        col_frame.setFrameShadow(QFrame.Shadow.Sunken)
        col_frame.setObjectName(file_path)  # 用于后续查找
        col_layout = QVBoxLayout(col_frame)
        col_layout.setContentsMargins(0, 0, 0, 0)
        col_layout.setSpacing(0)

        file_label = QLabel(file_name)
        file_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        file_label.setStyleSheet(
            "font-weight: bold; padding: 3px; background: #E8E8E8;")
        file_label.setCursor(Qt.CursorShape.PointingHandCursor)
        file_label.setToolTip("点击切换聚焦 / 返回对比视图")
        file_label.mousePressEvent = lambda event, fp=file_path: self._on_label_clicked(fp)
        col_layout.addWidget(file_label)
        col_layout.addWidget(hex_widget)

        self.hex_splitter.addWidget(col_frame)

        # 均分列宽
        self._distribute_splitter()

        # 应用当前缩放级别
        hex_widget.set_zoom(self._zoom_level)

    def _sync_scroll(self, source_fp, value):
        """同步所有 HexViewWidget 的垂直滚动条"""
        if self._scroll_sync_blocked or not self._scroll_sync_enabled:
            return
        self._scroll_sync_blocked = True
        for fp, hw in self.hex_widgets.items():
            if fp != source_fp:
                hw.verticalScrollBar().setValue(value)
        self._scroll_sync_blocked = False

    # ======================== 分屏均分 ========================
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._distribute_splitter()

    def _distribute_splitter(self):
        """自动均分左右列宽（非焦点模式时）"""
        if self._focused_file:
            return
        n = self.hex_splitter.count()
        if n > 0 and self.hex_splitter.width() > 0:
            w = self.hex_splitter.width() // n
            self.hex_splitter.setSizes([w] * n)

    # ======================== 聚焦模式 ========================
    def _toggle_focus_mode(self, checked):
        """切换聚焦模式：只显示选中文件 / 显示全部"""
        if checked:
            # 进入聚焦模式
            selected = self.file_list_widget.selectedItems()
            if not selected or len(selected) < 3:
                self.focus_button.setChecked(False)
                QMessageBox.information(self, "提示", "请先在文件列表中选中一个文件")
                return
            row = selected[0].row()
            fp_item = self.file_list_widget.item(row, 2)
            if not fp_item:
                self.focus_button.setChecked(False)
                return
            self._enter_focus_mode(fp_item.text())
        else:
            self._exit_focus_mode()

    def _enter_focus_mode(self, file_path):
        """进入聚焦模式：隐藏其他列，只显示目标文件"""
        # 先选中文件列表对应行（让用户知道当前聚焦哪个文件）
        for row in range(self.file_list_widget.rowCount()):
            item = self.file_list_widget.item(row, 2)
            if item and item.text() == file_path:
                self.file_list_widget.blockSignals(True)
                self.file_list_widget.selectRow(row)
                self.file_list_widget.blockSignals(False)
                break

        self._focused_file = file_path
        self._hidden_frames = []
        for i in range(self.hex_splitter.count()):
            frame = self.hex_splitter.widget(i)
            if isinstance(frame, QFrame) and frame.objectName() != file_path:
                self._hidden_frames.append(frame)
                frame.hide()

        self.focus_button.setChecked(True)
        self.focus_button.setText("📋 返回对比")
        fn = os.path.basename(file_path)
        self.status_label.setText(f"聚焦模式: {fn} | 点击标题或「返回对比」恢复")

    def _exit_focus_mode(self):
        """退出聚焦模式：恢复所有列"""
        self._focused_file = None

        # 恢复所有隐藏的帧
        for frame in self._hidden_frames:
            frame.show()
            # 强制刷新内部 HexViewWidget
            hw = frame.findChild(HexViewWidget)
            if hw:
                hw._update_scroll_range()
                hw.viewport().update()

        self._hidden_frames = []
        self.focus_button.setChecked(False)
        self.focus_button.setText("🔍 聚焦查看")
        self.status_label.setText("对比视图 | F3/Shift+F3 导航差异")

        # 延迟均分列宽 — 等 show() 生效后再分配
        QTimer.singleShot(0, self._distribute_splitter)

    # ======================== 缩放控制 ========================
    def _on_zoom_changed(self, value):
        self._zoom_level = value
        self.zoom_label_val.setText(f"{value}pt")
        for hw in self.hex_widgets.values():
            hw.set_zoom(value)

    def file_selected(self):
        """文件列表选中 → 高亮对应列边框"""
        try:
            selected = self.file_list_widget.selectedItems()
            if not selected or len(selected) < 3:
                self.save_button.setEnabled(False)
                self._unhighlight_all_frames()
                return

            row = selected[0].row()
            file_path_item = self.file_list_widget.item(row, 2)
            if not file_path_item:
                self.save_button.setEnabled(False)
                self._unhighlight_all_frames()
                return

            file_path = file_path_item.text()
            self.save_button.setEnabled(self.edit_mode and file_path in self.file_data)

            # 高亮对应列（只改边框线宽，不影响内部样式）
            self._unhighlight_all_frames()
            for i in range(self.hex_splitter.count()):
                frame = self.hex_splitter.widget(i)
                if isinstance(frame, QFrame) and frame.objectName() == file_path:
                    frame.setLineWidth(3)
                    frame.setStyleSheet(
                        "QFrame { border: 2px solid #3399FF; }")
                    break

        except Exception as e:
            QMessageBox.critical(self, "错误", f"文件选择处理失败: {str(e)}")
            self.save_button.setEnabled(False)

    def _unhighlight_all_frames(self):
        """重置所有列边框为默认样式"""
        for i in range(self.hex_splitter.count()):
            frame = self.hex_splitter.widget(i)
            if isinstance(frame, QFrame):
                frame.setLineWidth(1)
                frame.setStyleSheet("")

    def _on_file_double_clicked(self, row, _col):
        """双击文件列表 → 切换聚焦模式"""
        fp_item = self.file_list_widget.item(row, 2)
        if not fp_item:
            return
        file_path = fp_item.text()
        self._toggle_label_focus(file_path)

    def _on_label_clicked(self, file_path):
        """点击文件标题 → 切换聚焦模式"""
        self._toggle_label_focus(file_path)

    def _toggle_label_focus(self, file_path):
        """通用聚焦切换"""
        if self._focused_file == file_path:
            self._exit_focus_mode()
        elif self._focused_file:
            self._enter_focus_mode(file_path)
        else:
            self._enter_focus_mode(file_path)

    # ======================== 撤销编辑 ========================
    def _undo_last_edit(self):
        """撤销所有视图中的上一次编辑"""
        undone = False
        for hw in self.hex_widgets.values():
            if hw.undo():
                undone = True
        if undone:
            self.status_label.setText("已撤销上一次编辑")
        self.undo_button.setEnabled(
            any(len(hw._undo_stack) > 0 for hw in self.hex_widgets.values()))

    # ======================== 编辑模式 ========================
    def toggle_edit_mode(self):
        self.edit_mode = not self.edit_mode
        self.edit_button.setChecked(self.edit_mode)
        self.save_button.setEnabled(self.edit_mode and bool(self.file_data))
        self.undo_button.setEnabled(self.edit_mode and any(
            len(hw._undo_stack) > 0 for hw in self.hex_widgets.values()))
        self.status_label.setText("编辑模式已启用" if self.edit_mode else "编辑模式已禁用")

        for hw in self.hex_widgets.values():
            hw.edit_mode = self.edit_mode

    def _on_byte_changed(self, pos, new_byte):
        """字节被编辑后更新撤销按钮状态"""
        self.undo_button.setEnabled(True)

    # ======================== 比对逻辑 ========================
    def compare_files(self):
        """双文件比对（以第一个文件为基准）"""
        if len(self.file_data) < 2:
            QMessageBox.warning(self, "警告", "至少需要两个文件进行比对")
            return

        try:
            files = list(self.file_data.items())
            _, base_content = files[0]

            max_len = max(len(c) for _, c in files)
            differences = set()
            for i in range(max_len):
                base_byte = base_content[i] if i < len(base_content) else None
                for _, content in files[1:]:
                    other_byte = content[i] if i < len(content) else None
                    if other_byte != base_byte:
                        differences.add(i)
                        break

            self._apply_diff_results(differences)

        except Exception as e:
            QMessageBox.critical(self, "错误", f"比对过程中发生错误: {str(e)}")

    def compare_multiple_files(self):
        """多基准比对（三个及以上文件）"""
        if len(self.file_data) < 3:
            QMessageBox.warning(self, "警告", "至少需要三个文件进行多基准比对")
            return

        try:
            files = list(self.file_data.items())
            max_len = max(len(c) for _, c in files)

            differences = set()
            for i in range(max_len):
                byte_values = set()
                for _, content in files:
                    byte_values.add(content[i] if i < len(content) else None)
                if len(byte_values) > 1:
                    differences.add(i)

            self._apply_diff_results(differences)

        except Exception as e:
            QMessageBox.critical(self, "错误", f"多基准比对过程中发生错误: {str(e)}")

    def _apply_diff_results(self, differences):
        """统一应用比对结果：更新视图、导航条、状态"""
        self._diff_set = differences
        max_len = max(len(c) for c in self.file_data.values()) if self.file_data else 0

        for hw in self.hex_widgets.values():
            hw.set_diff_positions(differences)

        # 差异导航条
        if differences:
            self.diff_navigator.set_data(max_len, differences)
            self.diff_navigator.setVisible(True)
        else:
            self.diff_navigator.setVisible(False)

        # 差异计数和导航按钮
        n = len(differences)
        self.diff_count_label.setText(f"{n} 处差异")
        has_diff = n > 0
        self.next_diff_button.setEnabled(has_diff)
        self.prev_diff_button.setEnabled(has_diff)
        self._current_diff_index = -1

        # 跳转到第一个差异
        if has_diff:
            self._goto_next_diff()

        self.status_label.setText(f"比对完成，共发现 {n} 处差异")

    # ======================== 差异导航 ========================
    def _get_sorted_diffs(self):
        return sorted(self._diff_set) if self._diff_set else []

    def _goto_next_diff(self):
        diffs = self._get_sorted_diffs()
        if not diffs:
            return
        if self._current_diff_index < len(diffs) - 1:
            self._current_diff_index += 1
        else:
            self._current_diff_index = 0
        self._jump_to_diff(diffs[self._current_diff_index])

    def _goto_prev_diff(self):
        diffs = self._get_sorted_diffs()
        if not diffs:
            return
        if self._current_diff_index > 0:
            self._current_diff_index -= 1
        else:
            self._current_diff_index = len(diffs) - 1
        self._jump_to_diff(diffs[self._current_diff_index])

    def _jump_to_diff(self, offset):
        """所有视图跳转到指定差异位置"""
        for hw in self.hex_widgets.values():
            hw.goto_offset(offset)
        line = offset // 16
        self.status_label.setText(
            f"差异 {self._current_diff_index + 1}/{len(self._diff_set)}  @ 0x{offset:08X} (行 {line})")

    def _on_navigator_clicked(self, offset):
        """差异导航条点击 → 跳转"""
        diffs = self._get_sorted_diffs()
        if diffs:
            self._current_diff_index = diffs.index(offset) if offset in self._diff_set else 0
        self._jump_to_diff(offset)

    def _toggle_sync_scroll(self, checked):
        self._scroll_sync_enabled = checked
        self.sync_scroll_button.setText("🔗 同步滚动: 开" if checked else "🔓 同步滚动: 关")

    def _focus_goto_input(self):
        self.goto_input.setFocus()
        self.goto_input.selectAll()

    def _goto_offset(self):
        """跳转到用户输入的十六进制偏移"""
        text = self.goto_input.text().strip()
        if not text:
            return
        try:
            offset = int(text, 16)
            for hw in self.hex_widgets.values():
                hw.goto_offset(offset)
            self.status_label.setText(f"已跳转到 0x{offset:08X}")
        except ValueError:
            QMessageBox.warning(self, "错误", f"无效的十六进制偏移: {text}")

    # ======================== 右键菜单 ========================
    def _file_list_context_menu(self, pos):
        """文件列表右键菜单"""
        item = self.file_list_widget.itemAt(pos)
        if not item:
            return

        row = item.row()
        fp_item = self.file_list_widget.item(row, 2)
        if not fp_item:
            return
        file_path = fp_item.text()

        menu = QMenu(self)

        act_remove = menu.addAction("❌ 移除文件")
        menu.addSeparator()
        act_remove_all = menu.addAction("🗑 移除其他文件")

        action = menu.exec(self.file_list_widget.viewport().mapToGlobal(pos))

        if action == act_remove:
            self._remove_file(file_path)
        elif action == act_remove_all:
            self._remove_other_files(file_path)

    def _remove_file(self, file_path):
        """移除单个文件"""
        if file_path not in self.file_data:
            return

        # 从文件列表移除
        for row in range(self.file_list_widget.rowCount()):
            item = self.file_list_widget.item(row, 2)
            if item and item.text() == file_path:
                self.file_list_widget.removeRow(row)
                break

        # 从并排视图移除
        for i in range(self.hex_splitter.count()):
            frame = self.hex_splitter.widget(i)
            if isinstance(frame, QFrame) and frame.objectName() == file_path:
                frame.setParent(None)
                frame.deleteLater()
                break

        self.file_data.pop(file_path, None)
        self.hex_widgets.pop(file_path, None)
        if file_path in self.file_paths:
            self.file_paths.remove(file_path)

        self._update_button_states()
        self.status_label.setText(f"已移除: {os.path.basename(file_path)}")

    def _remove_other_files(self, keep_path):
        """移除除指定文件外的所有文件"""
        to_remove = [fp for fp in list(self.file_data.keys()) if fp != keep_path]
        for fp in to_remove:
            self._remove_file(fp)

    # ======================== 拖放支持 ========================
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        for url in urls:
            file_path = url.toLocalFile()
            if os.path.isfile(file_path):
                self.add_file(file_path)
        self._update_button_states()

    # ======================== 保存 ========================
    def save_current_file(self):
        try:
            selected = self.file_list_widget.selectedItems()
            if not selected or len(selected) < 3:
                QMessageBox.warning(self, "警告", "请先选择一个文件")
                return

            row = selected[0].row()
            file_path_item = self.file_list_widget.item(row, 2)
            if not file_path_item:
                return

            file_path = file_path_item.text()
            if file_path not in self.file_data:
                return

            reply = QMessageBox.question(
                self, "确认保存",
                f"确定要保存对 {os.path.basename(file_path)} 的修改吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.No:
                return

            # 备份
            backup_path = file_path + ".bak"
            if os.path.exists(file_path):
                try:
                    if os.path.exists(backup_path):
                        os.remove(backup_path)
                    os.rename(file_path, backup_path)
                except Exception as e:
                    QMessageBox.warning(self, "警告", f"无法创建备份文件: {str(e)}")
                    return

            try:
                with open(file_path, 'wb') as f:
                    f.write(self.file_data[file_path])

                file_size = os.path.getsize(file_path)
                self.file_list_widget.item(row, 1).setText(self.format_size(file_size))
                self.status_label.setText(f"文件 {os.path.basename(file_path)} 保存成功")
                QMessageBox.information(self, "成功", "文件保存成功")

            except Exception as e:
                if os.path.exists(backup_path):
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                        os.rename(backup_path, file_path)
                    except:
                        pass
                QMessageBox.critical(self, "错误", f"保存文件失败: {str(e)}")
                self.status_label.setText("文件保存失败")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存过程中发生错误: {str(e)}")
            self.status_label.setText("保存过程中发生错误")

    # ======================== 辅助方法 ========================
    def format_size(self, size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} TB"

    def _update_button_states(self):
        n = len(self.file_data)
        self.compare_button.setEnabled(n >= 2)
        self.multi_compare_button.setEnabled(n >= 3)
        self.save_button.setEnabled(self.edit_mode and n > 0)

    def clear_all(self):
        # 先退出聚焦模式
        if self._focused_file:
            self._exit_focus_mode()

        # 清除并排布局中的所有列
        while self.hex_splitter.count() > 0:
            w = self.hex_splitter.widget(0)
            w.setParent(None)
            w.deleteLater()

        self.hex_widgets.clear()
        self.file_data.clear()
        self.file_paths.clear()
        self._diff_set.clear()
        self._current_diff_index = -1
        self.file_list_widget.setRowCount(0)
        self.compare_button.setEnabled(False)
        self.multi_compare_button.setEnabled(False)
        self.next_diff_button.setEnabled(False)
        self.prev_diff_button.setEnabled(False)
        self.diff_count_label.setText("")
        self.diff_navigator.setVisible(False)
        self.edit_mode = False
        self.edit_button.setChecked(False)
        self.save_button.setEnabled(False)
        self.status_label.setText("就绪 | 支持拖放文件 | F3/Shift+F3 导航差异")

    def closeEvent(self, event):
        self.save_settings()
        self.db_conn.close()
        event.accept()


# ============================================================
# 入口
# ============================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)

    font = app.font()
    font.setFamily("Microsoft YaHei")
    app.setFont(font)

    window = HexViewer()
    window.show()
    sys.exit(app.exec())