from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, 
                             QLabel, QPushButton, QDoubleSpinBox, QSpinBox, 
                             QFormLayout, QFrame, QSizePolicy, QCheckBox, QGroupBox, QLineEdit, QMessageBox, QScrollArea)
from PyQt6.QtCore import Qt, pyqtSignal, QThread
from PyQt6.QtGui import QFont, QIcon

try:
    from src.vlm_utils import get_total_usage
except ImportError:
    from vlm_utils import get_total_usage

# 尝试导入 OpenAI 用于检测
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

class ApiCheckWorker(QThread):
    """后台线程：检查 API 连接状态"""
    result_signal = pyqtSignal(str, str) # msg, color

    def __init__(self, api_key, base_url, model_name, check_type="connection"):
        super().__init__()
        self.api_key = api_key
        self.base_url = base_url
        self.model_name = model_name
        self.check_type = check_type

    def run(self):
        if not OpenAI:
            self.result_signal.emit("错误: 未安装 openai 库", "red")
            return
        
        try:
            client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            
            if self.check_type == "connection":
                models = client.models.list()
                self.result_signal.emit(f"Base URL 连接成功 (模型数: {len(models.data)})", "green")
            
            elif self.check_type == "chat":
                client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": "Hi"}],
                    max_tokens=5
                )
                self.result_signal.emit(f"Chat 模型 '{self.model_name}' 可用", "green")
            
            elif self.check_type == "coder":
                client.chat.completions.create(
                    model=self.model_name,
                    messages=[{"role": "user", "content": "print('hello')"}],
                    max_tokens=5
                )
                self.result_signal.emit(f"Coder 模型 '{self.model_name}' 可用", "green")

        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg:
                self.result_signal.emit("401 Unauthorized (Key错误)", "red")
            elif "404" in error_msg:
                self.result_signal.emit(f"404: 模型 '{self.model_name}' 不存在", "red")
            else:
                self.result_signal.emit(f"错误: {error_msg[:30]}...", "red")

class SettingsWindow(QWidget):
    settings_saved = pyqtSignal(dict) 

    def __init__(self, current_settings, parent_pet=None):
        super().__init__()
        self.settings = current_settings.copy()
        self.pet = parent_pet 
        self.api_worker = None
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Settings")
        self.resize(500, 640) # 限制高度为 640
        
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.setStyleSheet("""
            QWidget#main_frame {
                background-color: rgba(255, 255, 255, 245); 
                border-radius: 15px;
                border: 1px solid #dcdcdc;
            }
            QLabel { font-family: "Microsoft YaHei"; color: #333; font-size: 13px; }
            QLabel#title { font-size: 16px; font-weight: bold; color: #2c3e50; }
            QTextEdit, QLineEdit {
                background-color: #ffffff;
                border: 1px solid #87CEEB;
                border-radius: 5px;
                padding: 5px;
                font-family: "Microsoft YaHei";
                font-size: 13px;
                color: #000000;
            }
            QDoubleSpinBox, QSpinBox {
                padding: 5px;
                border: 1px solid #87CEEB;
                border-radius: 5px;
                background: white;
                color: #000000;
            }
            QGroupBox {
                border: 1px solid #ccc;
                border-radius: 5px;
                margin-top: 10px;
                font-weight: bold;
                color: #555;
            }
            QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 3px; }
            QPushButton {
                background-color: #4682B4; color: white; border-radius: 5px; padding: 6px 12px; font-weight: bold;
            }
            QPushButton:hover { background-color: #5F9EA0; }
            QPushButton#cancel_btn { background-color: #FF6B6B; }
            QPushButton#cancel_btn:hover { background-color: #FF5252; }
            QPushButton.check-btn { background-color: #FFA500; padding: 4px 8px; font-size: 11px; }
            QPushButton.check-btn:hover { background-color: #FF8C00; }
            QPushButton#danger_btn {
                background-color: #FF6B6B;
                font-size: 12px;
                padding: 5px 10px;
            }
            QPushButton#danger_btn:hover {
                background-color: #FF5252;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
        """)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # 主容器
        self.frame = QFrame()
        self.frame.setObjectName("main_frame")
        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(15, 15, 15, 15)
        frame_layout.setSpacing(10)

        # 1. 标题 (固定)
        title_label = QLabel("系统设置 (System Config)")
        title_label.setObjectName("title")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(title_label)

        # --- 滚动区域开始 ---
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 5, 0) # 右侧留一点空间给滚动条
        scroll_layout.setSpacing(10)

        # 2. 基础人设
        scroll_layout.addWidget(QLabel("基础人设 (Persona):"))
        self.persona_edit = QTextEdit()
        self.persona_edit.setPlainText(self.settings.get("persona", ""))
        self.persona_edit.setMinimumHeight(200) # 设置最小高度确保容易输入
        scroll_layout.addWidget(self.persona_edit)

        # 3. API 设置
        api_group = QGroupBox("API 配置")
        api_layout = QFormLayout(api_group)
        api_layout.setSpacing(8)

        self.api_key_edit = QLineEdit(self.settings.get("api_key", ""))
        self.api_key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("sk-...")
        api_layout.addRow("API Key:", self.api_key_edit)

        base_url_layout = QHBoxLayout()
        self.base_url_edit = QLineEdit(self.settings.get("base_url", ""))
        btn_check_base = QPushButton("检查")
        btn_check_base.setProperty("class", "check-btn")
        btn_check_base.clicked.connect(lambda: self.check_api("connection"))
        base_url_layout.addWidget(self.base_url_edit)
        base_url_layout.addWidget(btn_check_base)
        api_layout.addRow("Base URL:", base_url_layout)

        model_layout = QHBoxLayout()
        self.model_name_edit = QLineEdit(self.settings.get("model_name", ""))
        btn_check_model = QPushButton("检查")
        btn_check_model.setProperty("class", "check-btn")
        btn_check_model.clicked.connect(lambda: self.check_api("chat"))
        model_layout.addWidget(self.model_name_edit)
        model_layout.addWidget(btn_check_model)
        api_layout.addRow("Chat Model:", model_layout)

        coder_layout = QHBoxLayout()
        self.coder_model_edit = QLineEdit(self.settings.get("coder_model_name", ""))
        btn_check_coder = QPushButton("检查")
        btn_check_coder.setProperty("class", "check-btn")
        btn_check_coder.clicked.connect(lambda: self.check_api("coder"))
        coder_layout.addWidget(self.coder_model_edit)
        coder_layout.addWidget(btn_check_coder)
        api_layout.addRow("Coder Model:", coder_layout)
        
        self.api_status_label = QLabel("Ready")
        self.api_status_label.setStyleSheet("color: gray; font-size: 11px;")
        self.api_status_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        api_layout.addRow(self.api_status_label)

        scroll_layout.addWidget(api_group)

        # 4. 行为与数值设置
        settings_container = QWidget()
        form_layout = QFormLayout(settings_container)
        form_layout.setSpacing(5)
        form_layout.setContentsMargins(0, 0, 0, 0)

        size_layout = QHBoxLayout()
        current_size = self.settings.get("pet_size", [320, 320])
        self.width_spin = QSpinBox()
        self.width_spin.setRange(100, 1000); self.width_spin.setValue(current_size[0]); self.width_spin.setSuffix("px")
        self.height_spin = QSpinBox()
        self.height_spin.setRange(100, 1000); self.height_spin.setValue(current_size[1]); self.height_spin.setSuffix("px")
        size_layout.addWidget(QLabel("W:")); size_layout.addWidget(self.width_spin)
        size_layout.addWidget(QLabel("H:")); size_layout.addWidget(self.height_spin)
        form_layout.addRow("尺寸:", size_layout)

        self.action_prob_spin = QDoubleSpinBox()
        self.action_prob_spin.setRange(0.0, 1.0); self.action_prob_spin.setSingleStep(0.01)
        self.action_prob_spin.setValue(self.settings.get("action_probability", 0.02))
        form_layout.addRow("行动概率/s:", self.action_prob_spin)

        chat_layout = QHBoxLayout()
        self.active_chat_prob_spin = QDoubleSpinBox()
        self.active_chat_prob_spin.setRange(0.0, 1.0); self.active_chat_prob_spin.setSingleStep(0.05)
        self.active_chat_prob_spin.setValue(self.settings.get("active_chat_probability", 0.2))
        self.active_chat_interval_spin = QSpinBox()
        self.active_chat_interval_spin.setRange(10, 3600); self.active_chat_interval_spin.setValue(self.settings.get("active_chat_interval", 60))
        chat_layout.addWidget(self.active_chat_prob_spin); chat_layout.addWidget(QLabel("间隔(s):")); chat_layout.addWidget(self.active_chat_interval_spin)
        form_layout.addRow("主动搭话:", chat_layout)

        self.smart_touch_check = QCheckBox("启用智能触摸互动 (消耗Token)")
        self.smart_touch_check.setChecked(self.settings.get("smart_touch", True))
        form_layout.addRow("互动:", self.smart_touch_check)

        scroll_layout.addWidget(settings_container)

        # 5. 记忆管理区域
        mem_group = QGroupBox("记忆管理 (Memory)")
        mem_layout = QHBoxLayout(mem_group)
        
        btn_clear_recent = QPushButton("清空中期记忆")
        btn_clear_recent.setObjectName("danger_btn")
        btn_clear_recent.clicked.connect(self.clear_recent_memory)
        
        btn_reset_long = QPushButton("重置长期记忆")
        btn_reset_long.setObjectName("danger_btn")
        btn_reset_long.clicked.connect(self.reset_long_term_memory)
        
        mem_layout.addWidget(btn_clear_recent)
        mem_layout.addWidget(btn_reset_long)
        
        scroll_layout.addWidget(mem_group)

        scroll_area.setWidget(scroll_content)
        frame_layout.addWidget(scroll_area)
        # --- 滚动区域结束 ---

        # 6. 费用统计 (固定)
        usage_layout = QHBoxLayout()
        self.usage_label = QLabel("Loading usage...")
        self.usage_label.setStyleSheet("color: #666; font-size: 12px;")
        refresh_btn = QPushButton("刷新")
        refresh_btn.setProperty("class", "check-btn")
        refresh_btn.setFixedWidth(50)
        refresh_btn.clicked.connect(self.update_usage_display)
        usage_layout.addWidget(self.usage_label)
        usage_layout.addStretch()
        usage_layout.addWidget(refresh_btn)
        frame_layout.addLayout(usage_layout)
        
        # 7. 底部按钮 (固定)
        btn_layout = QHBoxLayout()
        save_btn = QPushButton("保存并生效")
        save_btn.clicked.connect(self.save_settings)
        cancel_btn = QPushButton("取消")
        cancel_btn.setObjectName("cancel_btn")
        cancel_btn.clicked.connect(self.hide)
        btn_layout.addStretch()
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(save_btn)
        frame_layout.addLayout(btn_layout)

        main_layout.addWidget(self.frame)
        self.update_usage_display()

    def update_position(self):
        if self.isVisible() and self.pet:
            pet_geo = self.pet.geometry()
            target_x = pet_geo.x() - self.width() - 10
            if target_x < 0: target_x = pet_geo.x() + pet_geo.width() + 10
            target_y = pet_geo.y()
            self.move(target_x, target_y)

    def update_usage_display(self):
        tokens = get_total_usage()
        cost = (tokens / 1_000_000) * 3.0
        self.usage_label.setText(f"本次消耗: {tokens:,} tokens | 预估: ${cost:.4f}")

    def check_api(self, check_type):
        key = self.api_key_edit.text().strip()
        base = self.base_url_edit.text().strip()
        model = self.model_name_edit.text().strip() if check_type == "chat" else self.coder_model_edit.text().strip()
        
        self.api_status_label.setText(f"正在检查 {check_type}...")
        self.api_status_label.setStyleSheet("color: blue;")
        
        self.api_worker = ApiCheckWorker(key, base, model, check_type)
        self.api_worker.result_signal.connect(self.on_api_check_result)
        self.api_worker.start()

    def on_api_check_result(self, msg, color):
        self.api_status_label.setText(msg)
        self.api_status_label.setStyleSheet(f"color: {color};")

    def clear_recent_memory(self):
        if not self.pet: return
        reply = QMessageBox.question(self, "确认", "确定要清空所有中期记忆（对话摘要）吗？\n这将导致桌宠忘记之前的聊天上下文。",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.pet.memory_manager.clear_recent_memories()
            QMessageBox.information(self, "成功", "中期记忆已清空。")

    def reset_long_term_memory(self):
        if not self.pet: return
        reply = QMessageBox.question(self, "警告", "确定要重置长期记忆吗？\n这将清除所有用户画像和关系进度，重置为陌生人！此操作不可逆。",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if reply == QMessageBox.StandardButton.Yes:
            self.pet.memory_manager.reset_long_term_memories()
            QMessageBox.information(self, "成功", "长期记忆已重置为默认状态。")

    def save_settings(self):
        new_settings = {
            "persona": self.persona_edit.toPlainText().strip(),
            "api_key": self.api_key_edit.text().strip(),
            "base_url": self.base_url_edit.text().strip(),
            "model_name": self.model_name_edit.text().strip(),
            "coder_model_name": self.coder_model_edit.text().strip(),
            "pet_size": [self.width_spin.value(), self.height_spin.value()],
            "action_probability": self.action_prob_spin.value(),
            "active_chat_probability": self.active_chat_prob_spin.value(),
            "active_chat_interval": self.active_chat_interval_spin.value(),
            "smart_touch": self.smart_touch_check.isChecked()
        }
        self.settings_saved.emit(new_settings)
        self.hide()