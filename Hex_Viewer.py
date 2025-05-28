import sys
import os
import sqlite3
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                            QFileDialog, QScrollArea, QLabel, QPushButton, QMessageBox,
                            QSplitter, QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView,
                            QFrame, QLineEdit)
from PyQt5.QtCore import Qt, QSettings, QFileInfo, QSize, QPoint
from PyQt5.QtGui import QColor, QFont, QIcon, QBrush, QColor

class ProjectInfo:
    """项目信息元数据（集中管理所有项目相关信息）"""
    VERSION = "3.9.0"
    BUILD_DATE = "2025-05-26"
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


class HexViewer(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{ProjectInfo.NAME} {ProjectInfo.VERSION} (Build: {ProjectInfo.BUILD_DATE})")
        # self.setWindowIcon(QIcon("icon.ico"))
        self.setMinimumSize(800, 600)
        
        # 初始化设置
        self.settings = QSettings("HexViewer", "MultiFileHexCompare")
        self.last_dir = self.settings.value("last_dir", "", str)
        
        # 初始化数据库
        self.init_db()
        
        # 设置图标
        if os.path.exists("icon.ico"):
            self.setWindowIcon(QIcon("icon.ico"))
        
        # 创建UI
        self.init_ui()
        
        # 加载上次的设置
        self.load_settings()
    
    def init_db(self):
        self.db_conn = sqlite3.connect("hexviewer_settings.db")
        self.db_cursor = self.db_conn.cursor()
        
        # 创建设置表
        self.db_cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)
        
        # 创建文件历史表
        self.db_cursor.execute("""
        CREATE TABLE IF NOT EXISTS file_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE,
            last_opened TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        self.db_conn.commit()
    
    def init_ui(self):
        # 主窗口部件
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        # 主布局
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(5, 5, 5, 5)
        main_layout.setSpacing(5)
        
        # 顶部按钮栏
        button_layout = QHBoxLayout()
        button_layout.setSpacing(5)
        
        self.open_button = QPushButton("打开文件")
        self.open_button.clicked.connect(self.open_files)
        button_layout.addWidget(self.open_button)
        
        self.clear_button = QPushButton("清除所有")
        self.clear_button.clicked.connect(self.clear_all)
        button_layout.addWidget(self.clear_button)
        
        self.compare_button = QPushButton("开始比对")
        self.compare_button.clicked.connect(self.compare_files)
        self.compare_button.setEnabled(False)
        button_layout.addWidget(self.compare_button)
        
        self.edit_button = QPushButton("编辑模式")
        self.edit_button.setCheckable(True)
        self.edit_button.clicked.connect(self.toggle_edit_mode)
        button_layout.addWidget(self.edit_button)
    
        # 新添加的多基准比对按钮
        self.multi_compare_button = QPushButton("多基准比对")
        self.multi_compare_button.clicked.connect(self.compare_multiple_files)
        self.multi_compare_button.setEnabled(False)
        button_layout.addWidget(self.multi_compare_button)
    
        button_layout.addStretch()
        
        main_layout.addLayout(button_layout)
        
        # 主分割器
        self.main_splitter = QSplitter(Qt.Vertical)
        
        # 文件列表区域
        self.file_list_widget = QTableWidget()
        self.file_list_widget.setColumnCount(3)
        self.file_list_widget.setHorizontalHeaderLabels(["文件名", "大小", "路径"])
        self.file_list_widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.file_list_widget.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.file_list_widget.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.file_list_widget.verticalHeader().setVisible(False)
        self.file_list_widget.setSelectionMode(QTableWidget.SingleSelection)
        self.file_list_widget.setSelectionBehavior(QTableWidget.SelectRows)
        self.file_list_widget.itemSelectionChanged.connect(self.file_selected)
        
        # 十六进制显示区域
        self.hex_scroll = QScrollArea()
        self.hex_scroll.setWidgetResizable(True)
        
        self.hex_container = QWidget()
        self.hex_layout = QHBoxLayout(self.hex_container)
        self.hex_layout.setContentsMargins(5, 5, 5, 5)
        self.hex_layout.setSpacing(10)
        
        self.hex_scroll.setWidget(self.hex_container)
        
        # 添加到分割器
        self.main_splitter.addWidget(self.file_list_widget)
        self.main_splitter.addWidget(self.hex_scroll)
        
        # 设置分割器初始比例
        self.main_splitter.setSizes([100, 500])
        
        main_layout.addWidget(self.main_splitter)
        
        # 状态栏
        self.status_bar = self.statusBar()
        self.status_label = QLabel("就绪")
        self.status_bar.addWidget(self.status_label)
        
        # 存储文件数据
        self.file_data = {}
        self.current_file_index = -1
        self.hex_views = {}
        self.scroll_areas = {}
        self.byte_widgets = {}  # 存储字节编辑控件
        
        # 滚动条同步相关
        self.scroll_bars = []
        self.h_scroll_bars = []
        self.scroll_sync_enabled = True
        self.edit_mode = False
    
    def load_settings(self):
        # 恢复窗口大小和位置
        size = self.settings.value("window_size", QSize(800, 600))
        self.resize(size)
        
        pos = self.settings.value("window_position")
        if pos:
            self.move(pos)
        
        # 恢复分割器位置
        splitter_sizes = self.settings.value("splitter_sizes")
        if splitter_sizes:
            self.main_splitter.setSizes([int(size) for size in splitter_sizes])
    
    def save_settings(self):
        # 保存窗口大小和位置
        self.settings.setValue("window_size", self.size())
        self.settings.setValue("window_position", self.pos())
        
        # 保存分割器位置
        self.settings.setValue("splitter_sizes", self.main_splitter.sizes())
        
        # 保存最后访问的目录
        self.settings.setValue("last_dir", self.last_dir)
    
    def open_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择要比对的文件", 
            self.last_dir,
            "所有文件 (*.*)"
        )
        
        if not files:
            return
        
        self.last_dir = os.path.dirname(files[0])
        
        for file_path in files:
            self.add_file(file_path)
        
        if len(files) > 1:
            self.compare_button.setEnabled(True)
    
    def add_file(self, file_path):
        try:
            file_info = QFileInfo(file_path)
            file_name = file_info.fileName()
            file_size = file_info.size()
            
            # 检查是否已添加
            for i in range(self.file_list_widget.rowCount()):
                if self.file_list_widget.item(i, 2).text() == file_path:
                    return
            
            # 添加到文件列表
            row = self.file_list_widget.rowCount()
            self.file_list_widget.insertRow(row)
            
            self.file_list_widget.setItem(row, 0, QTableWidgetItem(file_name))
            self.file_list_widget.setItem(row, 1, QTableWidgetItem(self.format_size(file_size)))
            self.file_list_widget.setItem(row, 2, QTableWidgetItem(file_path))
            
            # 读取文件内容
            with open(file_path, 'rb') as f:
                content = f.read()
                self.file_data[file_path] = bytearray(content)
            
            # 添加到数据库历史记录
            self.db_cursor.execute(
                "INSERT OR REPLACE INTO file_history (file_path) VALUES (?)",
                (file_path,)
            )
            self.db_conn.commit()
            
            # 创建十六进制视图
            self.create_hex_view(file_path)
        
            # 更新按钮状态
            if len(self.file_data) > 1:
                self.compare_button.setEnabled(True)
            if len(self.file_data) > 2:
                self.multi_compare_button.setEnabled(True)

        except Exception as e:
            QMessageBox.warning(self, "错误", f"无法打开文件 {file_path}:\n{str(e)}")
    
    def format_size(self, size):
        # 格式化文件大小显示
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.2f} {unit}"
            size /= 1024.0
        return f"{size:.2f} TB"
    
    def file_selected(self):
        try:
            selected = self.file_list_widget.selectedItems()
            if not selected or len(selected) < 3:  # 确保有3列数据
                return
            
            row = selected[0].row()
            file_path_item = self.file_list_widget.item(row, 2)
            if not file_path_item:
                return
                
            file_path = file_path_item.text()
            if not file_path or file_path not in self.file_data:
                return
            
            # 滚动到对应的十六进制视图
            if file_path in self.hex_views:
                self.hex_scroll.ensureWidgetVisible(self.hex_views[file_path])
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"文件选择处理失败: {str(e)}")

    def create_hex_view(self, file_path):
        try:
            file_name = os.path.basename(file_path)
            content = self.file_data.get(file_path, bytearray())
            
            if not isinstance(content, bytearray):
                raise ValueError(f"文件内容不是字节数组类型: {file_path}")
            
            # 创建文件视图容器
            file_view = QFrame()
            file_view.setFrameShape(QFrame.StyledPanel)
            file_view_layout = QVBoxLayout(file_view)
            file_view_layout.setContentsMargins(5, 5, 5, 5)
            file_view_layout.setSpacing(5)
            
            # 添加文件名标签
            file_label = QLabel(file_name)
            file_label.setAlignment(Qt.AlignCenter)
            file_label.setStyleSheet("font-weight: bold;")
            file_view_layout.addWidget(file_label)
            
            # 创建滚动区域
            scroll_area = QScrollArea()
            scroll_area.setWidgetResizable(True)
            self.scroll_areas[file_path] = scroll_area
            
            # 获取滚动条并添加到列表
            v_scroll_bar = scroll_area.verticalScrollBar()
            h_scroll_bar = scroll_area.horizontalScrollBar()
            self.scroll_bars.append(v_scroll_bar)
            self.h_scroll_bars.append(h_scroll_bar)
            
            # 连接滚动信号
            v_scroll_bar.valueChanged.connect(self.sync_v_scroll_bars)
            h_scroll_bar.valueChanged.connect(self.sync_h_scroll_bars)

            # 创建十六进制显示容器
            hex_container = QWidget()
            hex_layout = QVBoxLayout(hex_container)
            hex_layout.setContentsMargins(5, 5, 5, 5)
            hex_layout.setSpacing(0)
            
            # 固定宽度字体
            font = QFont("Courier New", 10)
            
            # 每行显示16字节
            bytes_per_line = 16
            total_lines = (len(content) + bytes_per_line - 1) // bytes_per_line
            
            # 创建地址列
            for line in range(total_lines):
                offset = line * bytes_per_line
                line_end = min(offset + bytes_per_line, len(content))
                
                # 行布局
                line_widget = QWidget()
                line_layout = QHBoxLayout(line_widget)
                line_layout.setContentsMargins(0, 0, 0, 0)
                line_layout.setSpacing(10)
                
                # 地址显示
                addr_label = QLabel(f"{offset:08X}")
                addr_label.setFont(font)
                addr_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                addr_label.setFixedWidth(80)
                line_layout.addWidget(addr_label)
                
                # 十六进制显示区域
                hex_display = QWidget()
                hex_sub_layout = QHBoxLayout(hex_display)
                hex_sub_layout.setContentsMargins(0, 0, 0, 0)
                hex_sub_layout.setSpacing(5)
                
                for i in range(bytes_per_line):
                    pos = offset + i
                    if pos < len(content):
                        byte = content[pos]
                        
                        if self.edit_mode:
                            # 编辑模式下使用QLineEdit
                            byte_edit = QLineEdit(f"{byte:02X}")
                            byte_edit.setFont(font)
                            byte_edit.setAlignment(Qt.AlignCenter)
                            byte_edit.setFixedWidth(25)
                            byte_edit.setMaxLength(2)
                            byte_edit.textEdited.connect(lambda text, p=pos, fp=file_path: self.update_byte(text, p, fp))
                            hex_sub_layout.addWidget(byte_edit)
                            
                            # 保存编辑控件引用
                            if file_path not in self.byte_widgets:
                                self.byte_widgets[file_path] = {}
                            self.byte_widgets[file_path][pos] = byte_edit
                        else:
                            # 查看模式下使用QLabel
                            byte_label = QLabel(f"{byte:02X}")
                            byte_label.setFont(font)
                            byte_label.setAlignment(Qt.AlignCenter)
                            byte_label.setFixedWidth(20)
                            
                            # 标记差异的背景色
                            byte_label.setAutoFillBackground(True)
                            palette = byte_label.palette()
                            palette.setColor(byte_label.backgroundRole(), Qt.white)
                            byte_label.setPalette(palette)
                            
                            hex_sub_layout.addWidget(byte_label)
                    else:
                        # 填充空白
                        empty_label = QLabel("  ")
                        empty_label.setFont(font)
                        hex_sub_layout.addWidget(empty_label)
                
                line_layout.addWidget(hex_display)
                
                # ASCII显示区域
                ascii_display = QWidget()
                ascii_layout = QHBoxLayout(ascii_display)
                ascii_layout.setContentsMargins(0, 0, 0, 0)
                ascii_layout.setSpacing(0)
                
                for i in range(bytes_per_line):
                    pos = offset + i
                    if pos < len(content):
                        char = content[pos]
                        if 32 <= char <= 126:
                            char_label = QLabel(chr(char))
                        else:
                            char_label = QLabel(".")
                        char_label.setFont(font)
                        char_label.setAlignment(Qt.AlignCenter)
                        char_label.setFixedWidth(12)
                        
                        # 标记差异的背景色
                        char_label.setAutoFillBackground(True)
                        palette = char_label.palette()
                        palette.setColor(char_label.backgroundRole(), Qt.white)
                        char_label.setPalette(palette)
                        
                        ascii_layout.addWidget(char_label)
                    else:
                        # 填充空白
                        empty_label = QLabel(" ")
                        empty_label.setFont(font)
                        ascii_layout.addWidget(empty_label)
                
                line_layout.addWidget(ascii_display)
                line_layout.addStretch()
                
                # 添加行部件
                hex_layout.addWidget(line_widget)
            
            hex_layout.addStretch()
            
            scroll_area.setWidget(hex_container)
            file_view_layout.addWidget(scroll_area)
            
            # 添加到主布局
            self.hex_layout.addWidget(file_view)
            self.hex_views[file_path] = file_view
            
            # 保存当前文件索引
            self.current_file_index = self.file_list_widget.currentRow()
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"创建十六进制视图失败: {str(e)}")

    def update_byte(self, text, pos, file_path):
        """更新字节数据"""
        try:
            if len(text) == 2:
                byte = int(text, 16)
                self.file_data[file_path][pos] = byte
                
                # 更新ASCII显示
                self.update_ascii_display(file_path, pos)
        except ValueError:
            pass
    
    def update_ascii_display(self, file_path, pos):
        """更新ASCII显示"""
        if file_path in self.hex_views:
            file_view = self.hex_views[file_path]
            scroll_area = file_view.findChild(QScrollArea)
            if scroll_area:
                hex_widget = scroll_area.widget()
                if hex_widget:
                    # 找到对应的行
                    line = pos // 16
                    line_widget = hex_widget.findChild(QWidget, f"line_{line}")
                    if line_widget and line_widget.layout():
                        # 获取ASCII显示区域
                        ascii_item = line_widget.layout().itemAt(2)
                        if ascii_item:
                            ascii_widget = ascii_item.widget()
                            if ascii_widget and ascii_widget.layout():
                                char_pos = pos % 16
                                item = ascii_widget.layout().itemAt(char_pos)
                                if item:
                                    char_label = item.widget()
                                    if isinstance(char_label, QLabel):
                                        byte = self.file_data[file_path][pos]
                                        if 32 <= byte <= 126:
                                            char_label.setText(chr(byte))
                                        else:
                                            char_label.setText(".")

    def toggle_edit_mode(self):
        """切换编辑模式"""
        self.edit_mode = not self.edit_mode
        self.edit_button.setChecked(self.edit_mode)
        
        if self.edit_mode:
            self.status_label.setText("编辑模式已启用")
        else:
            self.status_label.setText("编辑模式已禁用")
        
        # 重新创建所有十六进制视图
        for file_path in list(self.hex_views.keys()):
            self.recreate_hex_view(file_path)
    
    def recreate_hex_view(self, file_path):
        """重新创建十六进制视图"""
        if file_path in self.hex_views:
            # 移除旧视图
            old_view = self.hex_views[file_path]
            self.hex_layout.removeWidget(old_view)
            old_view.setParent(None)
            old_view.deleteLater()
            
            # 创建新视图
            self.create_hex_view(file_path)

    def clear_all(self):
        # 清除所有十六进制视图
        for i in reversed(range(self.hex_layout.count())): 
            widget = self.hex_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        
        self.hex_views.clear()
        self.scroll_areas.clear()
        self.byte_widgets.clear()
        self.file_list_widget.setRowCount(0)
        self.file_data.clear()
        self.compare_button.setEnabled(False)
        self.scroll_bars = []
        self.h_scroll_bars = []
        self.edit_mode = False
        self.edit_button.setChecked(False)
        self.multi_compare_button.setEnabled(False)

    def compare_files(self):
        if len(self.file_data) < 2:
            QMessageBox.warning(self, "警告", "至少需要两个文件进行比对")
            return
        
        try:
            # 获取所有文件内容
            files = list(self.file_data.items())
            base_file_path, base_content = files[0]
            other_files = files[1:]
            
            # 找到最大长度
            max_len = len(base_content)
            for file_path, content in other_files:
                if len(content) > max_len:
                    max_len = len(content)
            
            # 比较差异
            differences = {}
            for i in range(max_len):
                if i >= len(base_content):
                    # 基础文件比当前文件短
                    byte_diff = True
                else:
                    base_byte = base_content[i]
                    byte_diff = False
                    
                    for file_path, content in other_files:
                        if i >= len(content) or content[i] != base_byte:
                            byte_diff = True
                            break
                
                if byte_diff:
                    differences[i] = True
            
            # 在所有视图中高亮差异
            for file_path, file_view in self.hex_views.items():
                scroll_area = file_view.findChild(QScrollArea)
                if not scroll_area:
                    continue
                    
                hex_widget = scroll_area.widget()
                if not hex_widget:
                    continue
                
                # 遍历所有行
                for line_widget in hex_widget.findChildren(QWidget):
                    if not line_widget or not line_widget.layout():
                        continue
                    
                    # 获取地址
                    addr_item = line_widget.layout().itemAt(0)
                    if not addr_item:
                        continue
                        
                    addr_label = addr_item.widget()
                    if not isinstance(addr_label, QLabel):
                        continue
                    
                    try:
                        offset = int(addr_label.text(), 16)
                    except:
                        continue
                    
                    # 检查这一行是否有差异
                    has_diff = False
                    for i in range(16):
                        pos = offset + i
                        if pos in differences:
                            has_diff = True
                            break
                    
                    if has_diff:
                        # 高亮整行
                        line_widget.setAutoFillBackground(True)
                        palette = line_widget.palette()
                        palette.setColor(line_widget.backgroundRole(), QColor(255, 255, 200))
                        line_widget.setPalette(palette)
                        
                        # 高亮具体差异字节
                        hex_sub_item = line_widget.layout().itemAt(1)
                        if hex_sub_item:
                            hex_sub_widget = hex_sub_item.widget()
                            if hex_sub_widget and hex_sub_widget.layout():
                                for i in range(hex_sub_widget.layout().count()):
                                    item = hex_sub_widget.layout().itemAt(i)
                                    if item:
                                        widget = item.widget()
                                        if isinstance(widget, (QLabel, QLineEdit)):
                                            pos = offset + i
                                            if pos in differences:
                                                palette = widget.palette()
                                                palette.setColor(widget.backgroundRole(), QColor(255, 200, 200))
                                                widget.setPalette(palette)
                        
                        # 高亮ASCII部分
                        ascii_item = line_widget.layout().itemAt(2)
                        if ascii_item:
                            ascii_widget = ascii_item.widget()
                            if ascii_widget and ascii_widget.layout():
                                for i in range(ascii_widget.layout().count()):
                                    item = ascii_widget.layout().itemAt(i)
                                    if item:
                                        char_label = item.widget()
                                        if isinstance(char_label, QLabel):
                                            pos = offset + i
                                            if pos in differences:
                                                palette = char_label.palette()
                                                palette.setColor(char_label.backgroundRole(), QColor(255, 200, 200))
                                                char_label.setPalette(palette)
            
            self.status_label.setText(f"比对完成，共发现 {len(differences)} 处差异")
        
        except Exception as e:
            QMessageBox.critical(self, "错误", f"比对过程中发生错误: {str(e)}")


    def closeEvent(self, event):
        self.save_settings()
        self.db_conn.close()
        event.accept()

    def sync_v_scroll_bars(self, value):
        """同步垂直滚动条位置和内容视图"""
        if not self.scroll_sync_enabled:
            return
            
        # 获取发送信号的滚动条
        sender = self.sender()
        
        # 阻塞所有滚动条信号以避免递归
        self.scroll_sync_enabled = False
        
        # 同步所有垂直滚动条位置
        for scroll_bar in self.scroll_bars:
            if scroll_bar != sender:
                scroll_bar.setValue(value)
        
        # 解除信号阻塞
        self.scroll_sync_enabled = True

    def sync_h_scroll_bars(self, value):
        """同步水平滚动条位置和内容视图"""
        if not self.scroll_sync_enabled:
            return
            
        # 获取发送信号的滚动条
        sender = self.sender()
        
        # 阻塞所有滚动条信号以避免递归
        self.scroll_sync_enabled = False
        
        # 同步所有水平滚动条位置
        for scroll_bar in self.h_scroll_bars:
            if scroll_bar != sender:
                scroll_bar.setValue(value)
        
        # 解除信号阻塞
        self.scroll_sync_enabled = True

    def compare_multiple_files(self):
        """比对三个及以上文件的共同差异"""
        if len(self.file_data) < 3:
            QMessageBox.warning(self, "警告", "至少需要三个文件进行多基准比对")
            return
        
        try:
            # 获取所有文件内容
            files = list(self.file_data.items())
            
            # 找到最大长度
            max_len = max(len(content) for _, content in files)
            
            # 比较差异 - 找出所有文件中不相同的字节位置
            differences = {}
            for i in range(max_len):
                # 收集所有文件在该位置的字节值
                byte_values = set()
                for file_path, content in files:
                    if i < len(content):
                        byte_values.add(content[i])
                    else:
                        byte_values.add(None)  # 表示文件比最短的文件长
                
                # 如果有超过1个不同的值，则标记为差异
                if len(byte_values) > 1:
                    differences[i] = True
            
            # 高亮差异
            self.highlight_differences(differences)
            
            self.status_label.setText(f"多基准比对完成，共发现 {len(differences)} 处差异")
            
        except Exception as e:
            QMessageBox.critical(self, "错误", f"多基准比对过程中发生错误: {str(e)}")

    def highlight_differences(self, differences):
        """高亮显示差异位置（重构后的通用方法）"""
        for file_path, file_view in self.hex_views.items():
            scroll_area = file_view.findChild(QScrollArea)
            if not scroll_area:
                continue
                
            hex_widget = scroll_area.widget()
            if not hex_widget:
                continue
            
            # 遍历所有行
            for line_widget in hex_widget.findChildren(QWidget):
                if not line_widget or not line_widget.layout():
                    continue
                
                # 获取地址
                addr_item = line_widget.layout().itemAt(0)
                if not addr_item:
                    continue
                    
                addr_label = addr_item.widget()
                if not isinstance(addr_label, QLabel):
                    continue
                
                try:
                    offset = int(addr_label.text(), 16)
                except:
                    continue
                
                # 检查这一行是否有差异
                has_diff = False
                for i in range(16):
                    pos = offset + i
                    if pos in differences:
                        has_diff = True
                        break
                
                if has_diff:
                    # 高亮整行
                    line_widget.setAutoFillBackground(True)
                    palette = line_widget.palette()
                    palette.setColor(line_widget.backgroundRole(), QColor(255, 255, 200))
                    line_widget.setPalette(palette)
                    
                    # 高亮具体差异字节
                    hex_sub_item = line_widget.layout().itemAt(1)
                    if hex_sub_item:
                        hex_sub_widget = hex_sub_item.widget()
                        if hex_sub_widget and hex_sub_widget.layout():
                            for i in range(hex_sub_widget.layout().count()):
                                item = hex_sub_widget.layout().itemAt(i)
                                if item:
                                    widget = item.widget()
                                    if isinstance(widget, (QLabel, QLineEdit)):
                                        pos = offset + i
                                        if pos in differences:
                                            palette = widget.palette()
                                            palette.setColor(widget.backgroundRole(), QColor(255, 200, 200))
                                            widget.setPalette(palette)
                    
                    # 高亮ASCII部分
                    ascii_item = line_widget.layout().itemAt(2)
                    if ascii_item:
                        ascii_widget = ascii_item.widget()
                        if ascii_widget and ascii_widget.layout():
                            for i in range(ascii_widget.layout().count()):
                                item = ascii_widget.layout().itemAt(i)
                                if item:
                                    char_label = item.widget()
                                    if isinstance(char_label, QLabel):
                                        pos = offset + i
                                        if pos in differences:
                                            palette = char_label.palette()
                                            palette.setColor(char_label.backgroundRole(), QColor(255, 200, 200))
                                            char_label.setPalette(palette)



if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 设置中文字体
    font = app.font()
    font.setFamily("Microsoft YaHei")
    app.setFont(font)
    
    window = HexViewer()
    window.show()
    sys.exit(app.exec_())