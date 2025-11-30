from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, 
                             QPushButton, QLineEdit, QFrame, QFormLayout, QLabel)
from PyQt6.QtCore import Qt, pyqtSignal

class ChatWindow(QWidget):
    def __init__(self, parent_widget, pet_core):
        super().__init__()
        self.main_widget = parent_widget # 用于定位
        self.core = pet_core             # 用于逻辑调用
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Chat")
        self.resize(300, 350)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)

        self.container = QFrame()
        self.container.setObjectName("container")
        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(15, 15, 15, 15)

        style_sheet = """
            QFrame#container {
                background-color: rgba(173, 216, 230, 230); 
                border-radius: 20px;
                border: 2px solid rgba(255, 255, 255, 100);
            }
            QTextEdit {
                background-color: rgba(255, 255, 255, 150);
                border: none;
                border-radius: 10px;
                font-family: "Microsoft YaHei", sans-serif;
                font-size: 14px;
                color: #000000;
                padding: 10px;
            }
            QLineEdit {
                background-color: rgba(255, 255, 255, 255);
                border: 2px solid rgba(135, 206, 235, 200);
                border-radius: 15px;
                padding: 8px;
                font-family: "Microsoft YaHei", sans-serif;
                font-size: 13px;
                color: #000000;
            }
            QPushButton {
                background-color: #4682B4; 
                color: white;
                border-radius: 15px;
                padding: 8px 15px;
                font-weight: bold;
                font-family: "Microsoft YaHei", sans-serif;
            }
            QPushButton:hover {
                background-color: #5F9EA0;
            }
            QPushButton:pressed {
                background-color: #4169E1;
            }
        """
        self.setStyleSheet(style_sheet)

        self.chat_history = QTextEdit()
        self.chat_history.setReadOnly(True)
        container_layout.addWidget(self.chat_history)

        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("和我说说话吧...")
        self.input_field.returnPressed.connect(self.send_message)
        
        self.send_btn = QPushButton("发送")
        self.send_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.send_btn.clicked.connect(self.send_message)

        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn)
        
        container_layout.addLayout(input_layout)
        layout.addWidget(self.container)
        self.setLayout(layout)

    def update_position(self):
        if self.isVisible():
            pet_geo = self.main_widget.geometry()
            target_x = pet_geo.x() + pet_geo.width() - 50 
            target_y = pet_geo.y() + 20 
            self.move(target_x, target_y)

    def send_message(self):
        text = self.input_field.text().strip()
        if not text: return

        self.chat_history.append(f"<div style='color:#003366; margin-bottom:5px;'><b>你:</b> {text}</div>")
        self.input_field.clear()
        self.chat_history.append("<div style='color:#555555; font-style:italic; font-size:12px;'>正在思考...</div>")
        sb = self.chat_history.verticalScrollBar()
        sb.setValue(sb.maximum())

        # 调用 Core 发送消息
        self.core.start_chat(text)

    def receive_reply(self, reply):
        self.chat_history.append(f"<div style='color:#000000; margin-bottom:10px; margin-top:5px;'><b>桌宠:</b> {reply}</div>")
        sb = self.chat_history.verticalScrollBar()
        sb.setValue(sb.maximum())

class InitSetupWindow(QWidget):
    submission_signal = pyqtSignal(dict)

    def __init__(self, parent_widget):
        super().__init__()
        self.main_widget = parent_widget
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("初次见面 - 信息登记")
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.setStyleSheet("""
            QWidget#main_frame {
                background-color: rgba(255, 250, 240, 240); 
                border-radius: 15px;
                border: 2px solid #FFD700;
            }
            QLabel {
                font-family: "Microsoft YaHei";
                color: #555;
                font-size: 13px;
                font-weight: bold;
            }
            QLabel#title {
                font-size: 16px;
                color: #FF8C00;
                margin-bottom: 10px;
            }
            QLineEdit {
                border: 1px solid #FFD700;
                border-radius: 5px;
                padding: 5px;
                background-color: white;
                color: #333;
            }
            QPushButton {
                background-color: #FF8C00; 
                color: white;
                border-radius: 15px;
                padding: 8px;
                font-weight: bold;
                font-family: "Microsoft YaHei";
            }
            QPushButton:hover { background-color: #FFA500; }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        self.frame = QFrame()
        self.frame.setObjectName("main_frame")
        frame_layout = QVBoxLayout(self.frame)
        frame_layout.setContentsMargins(20, 20, 20, 20)

        title = QLabel("✨ 初次见面请多关照 ✨")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(title)
        
        desc = QLabel("为了更好地陪伴你，请告诉我关于你的一些信息吧！")
        desc.setWordWrap(True)
        desc.setStyleSheet("font-weight: normal; font-size: 12px; margin-bottom: 10px;")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        frame_layout.addWidget(desc)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("例如：主人、学长...")
        form_layout.addRow("我该怎么称呼你？", self.name_edit)

        self.birth_edit = QLineEdit()
        self.birth_edit.setPlaceholderText("例如：1月1日")
        form_layout.addRow("你的生日是哪天？", self.birth_edit)

        self.job_edit = QLineEdit()
        self.job_edit.setPlaceholderText("例如：学生, 程序员...")
        form_layout.addRow("你是做什么的？", self.job_edit)

        self.hobby_edit = QLineEdit()
        self.hobby_edit.setPlaceholderText("例如：画画, 发呆...")
        form_layout.addRow("有什么喜欢的事？", self.hobby_edit)

        frame_layout.addLayout(form_layout)

        self.submit_btn = QPushButton("提交信息 (Submit)")
        self.submit_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.submit_btn.clicked.connect(self.submit_info)
        frame_layout.addWidget(self.submit_btn)
        frame_layout.addStretch()
        layout.addWidget(self.frame)
        
        self.adjustSize()

    def submit_info(self):
        data = {
            "称呼": self.name_edit.text().strip(),
            "生日": self.birth_edit.text().strip(),
            "职业": self.job_edit.text().strip(),
            "爱好": self.hobby_edit.text().strip()
        }
        self.submission_signal.emit(data)
        self.hide()

    def update_position(self):
        if self.isVisible():
            pet_geo = self.main_widget.geometry()
            target_x = int(pet_geo.x() + (pet_geo.width() - self.width()) // 2)
            target_y = int(pet_geo.y() - self.height() - 20)
            if target_y < 0: 
                target_y = int(pet_geo.y() + pet_geo.height() + 20)
            self.move(target_x, target_y)