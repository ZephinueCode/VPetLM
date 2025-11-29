import sys
import os
import time
import random
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QMenu, QVBoxLayout, 
                             QHBoxLayout, QTextEdit, QPushButton, QLineEdit, QFrame)
from PyQt6.QtCore import Qt, QPoint, QTimer, QPropertyAnimation, QEasingCurve, QThread, pyqtSignal
from PyQt6.QtGui import QPixmap, QMouseEvent, QAction, QFont, QColor, QPalette

# 导入配置
try:
    from src.parameters import ANIMATION_PATH, ANIMATION_CONFIG
    from src.vlm_utils import LLMClient, CoderClient 
    from src.memory_utils import MemoryManager
    from src.coding_utils import CodingWindow 
    from src.settings_ui import SettingsWindow 
except ImportError:
    from parameters import ANIMATION_PATH, ANIMATION_CONFIG
    from vlm_utils import LLMClient, CoderClient
    from memory_utils import MemoryManager
    from coding_utils import CodingWindow
    from settings_ui import SettingsWindow

# --- 1. 常规聊天线程 ---
class ChatWorker(QThread):
    reply_signal = pyqtSignal(str, dict)

    def __init__(self, client, text, current_stats, persona):
        super().__init__()
        self.client = client
        self.text = text
        self.stats = current_stats
        self.persona = persona

    def run(self):
        if self.client:
            reply, action = self.client.chat(self.text, self.stats, self.persona)
            self.reply_signal.emit(reply, action)
        else:
            self.reply_signal.emit("错误：LLM客户端未初始化", {})

# --- 2. 主动聊天线程 ---
class ActiveChatWorker(QThread):
    reply_signal = pyqtSignal(str, dict)

    def __init__(self, client, current_stats, persona):
        super().__init__()
        self.client = client
        self.stats = current_stats
        self.persona = persona

    def run(self):
        if self.client:
            reply, action = self.client.initiate_conversation(self.stats, self.persona)
            if reply: 
                self.reply_signal.emit(reply, action)

# --- 3. 编程聊天线程 ---
class CoderWorker(QThread):
    reply_signal = pyqtSignal(str, dict)

    def __init__(self, client, text, stats, persona):
        super().__init__()
        self.client = client
        self.text = text
        self.stats = stats
        self.persona = persona

    def run(self):
        if self.client:
            reply, action = self.client.chat(self.text, self.stats, self.persona)
            self.reply_signal.emit(reply, action)

# --- 聊天窗口 ---
class ChatWindow(QWidget):
    def __init__(self, parent_pet):
        super().__init__()
        self.pet = parent_pet
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
            pet_geo = self.pet.geometry()
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

        self.pet.start_chat_process(text)

    def receive_reply(self, reply):
        self.chat_history.append(f"<div style='color:#000000; margin-bottom:10px; margin-top:5px;'><b>桌宠:</b> {reply}</div>")
        sb = self.chat_history.verticalScrollBar()
        sb.setValue(sb.maximum())

# --- 桌面宠物主类 ---
class DesktopPet(QWidget):
    def __init__(self, image_path=None, target_size=(320, 320), parent=None):
        super().__init__(parent)
        
        self.llm_client = LLMClient()
        self.coder_client = CoderClient() 
        self.memory_manager = MemoryManager()

        # 1. 加载设置
        self.settings = self.memory_manager.load_settings()
        self.target_size = tuple(self.settings.get("pet_size", [320, 320]))

        # 2. 状态初始化
        default_stats = {
            "hunger": 0, "thirst": 0, "fatigue": 0, 
            "boredom": 0, "intimacy": 0, "capability": 0, "mood": 50
        }
        saved_stats = self.memory_manager.load_status()
        if saved_stats:
            self.stats = saved_stats
            print("Loaded saved stats:", self.stats)
        else:
            self.stats = default_stats
            print("Using default stats")

        self.current_role_state = "idle" 
        self.current_direction = "right" 
        self.tick_counter = 0            

        # 触摸统计 [timestamp1, timestamp2, ...]
        self.touch_history = []

        self.current_frames = []      
        self.current_frame_index = 0  
        self.current_config = {}      
        self.anim_start_time = 0      
        self.anim_queue = []          
        
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._update_frame)

        self.logic_timer = QTimer(self)
        self.logic_timer.timeout.connect(self._update_stats_logic)
        self.logic_timer.start(1000) 

        # 拖拽/点击 区分逻辑
        self.is_dragging = False
        self.is_potential_drag = False # 新增：潜在拖拽状态
        self.press_start_pos = QPoint()
        self.drag_offset = QPoint()
        
        self.pos_anim = QPropertyAnimation(self, b"pos")

        self.chat_window = None 
        self.coding_window = None 
        self.settings_window = None
        
        self.active_chat_worker = None 
        self.chat_worker = None

        self.init_ui()
        self.play_idle_animation()

    def init_ui(self):
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | 
            Qt.WindowType.WindowStaysOnTopHint | 
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.label = QLabel(self)
        self.move(200, 200)

    # --- 鼠标与触摸逻辑核心 ---
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            # 记录初始按下位置，用于判断是否移动了足够距离成为拖拽
            self.press_start_pos = event.globalPosition().toPoint()
            self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            
            self.is_potential_drag = True  # 标记可能开始拖拽
            self.is_dragging = False       # 尚未确认为拖拽
            
            # 停止任何正在进行的物理掉落动画
            if self.pos_anim.state() == QPropertyAnimation.State.Running:
                self.pos_anim.stop()
            
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() & Qt.MouseButton.LeftButton:
            current_pos = event.globalPosition().toPoint()
            
            # 检查移动距离是否超过阈值 (例如 5px)
            if self.is_potential_drag and (current_pos - self.press_start_pos).manhattanLength() > 5:
                self.is_dragging = True
                self.is_potential_drag = False # 确认为拖拽，不再是潜在状态
                # 开始播放拖拽动画
                self.play_animation(ANIMATION_PATH.MOVEMENT_CONT_DRAG, ANIMATION_CONFIG.CONFIG_MOVEMENT_CONT)
            
            if self.is_dragging:
                # 执行拖拽移动
                new_pos = current_pos - self.drag_offset
                self.move(new_pos)
            
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_dragging:
                # 拖拽结束：执行掉落逻辑
                self.is_dragging = False
                self._handle_drop()
            elif self.is_potential_drag:
                # 未触发拖拽：认定为点击/触摸
                self.is_potential_drag = False
                # 传入相对于窗口的坐标进行判定
                self.handle_touch(event.position())
            
            event.accept()

    def _handle_drop(self):
        """处理拖拽释放后的掉落"""
        screen_geo = self.screen().geometry()
        screen_height = screen_geo.height()
        current_y = self.y()
        drop_percentage = random.uniform(0.10, 0.20)
        drop_distance = int(screen_height * drop_percentage)
        max_y = screen_height - self.height() - 60
        target_y = min(current_y + drop_distance, max_y)
        if target_y - current_y < 10:
            self._on_drop_finished()
            return
        self.play_animation(ANIMATION_PATH.MOVEMENT_CONT_FALL, ANIMATION_CONFIG.CONFIG_MOVEMENT_CONT, clear_queue=True)
        self.pos_anim.setDuration(500)
        self.pos_anim.setStartValue(self.pos())
        self.pos_anim.setEndValue(QPoint(self.x(), target_y))
        self.pos_anim.setEasingCurve(QEasingCurve.Type.OutBounce)
        try: self.pos_anim.finished.disconnect()
        except TypeError: pass
        self.pos_anim.finished.connect(self._on_drop_finished)
        self.pos_anim.start()

    def handle_touch(self, local_pos):
        """处理触摸逻辑"""
        # 防堆积逻辑
        if self.current_role_state == "talking":
            print("Ignored touch: Pet is busy.")
            return

        # 1. 细化区域判定
        # 获取点击位置在 Widget 中的相对坐标比例 (0.0 - 1.0)
        x_ratio = local_pos.x() / self.width()
        y_ratio = local_pos.y() / self.height()
        
        part = "身体" # 默认兜底

        # 纵向判定优先
        if y_ratio < 0.35:
            part = "脑袋"
        elif y_ratio < 0.7:
            # 胸部和肚子区域，检查左右是否为手
            # 假设手在身体两侧，占比左右各 25%
            if x_ratio < 0.2 or x_ratio > 0.8:
                part = "手"
            elif y_ratio < 0.55:
                part = "胸"
            else:
                part = "肚子"
        elif y_ratio < 0.85:
            part = "大腿"
        else:
            part = "脚"
        
        # 2. 更新滑动计数器
        current_time = time.time()
        self.touch_history.append(current_time)
        # 清理 60秒前的数据
        self.touch_history = [t for t in self.touch_history if current_time - t <= 60]
        touch_count = len(self.touch_history)
        
        print(f"Touched {part} (x={x_ratio:.2f}, y={y_ratio:.2f}). Count in last min: {touch_count}")

        # 3. 根据设置决定行为
        smart_touch = self.settings.get("smart_touch", True)
        
        if smart_touch:
            # 智能互动：发送 Prompt 给 LLM
            prompt_text = f"*用户刚才触摸了你的{part}。这是一分钟内用户第{touch_count}次触摸你。*"
            # 使用专用流程，强制弹出窗口
            self.start_touch_chat_process(prompt_text)
        else:
            # 普通互动：直接播放动画和数值反馈
            if part == "脑袋":
                # 摸头: 享受/开心
                self.play_animation(ANIMATION_PATH.EMOTION_SING_ENJOY, ANIMATION_CONFIG.CONFIG_EMOTION_SING)
                if touch_count < 3: self.stats["mood"] = min(100, self.stats["mood"] + 0.1)
            elif part == "胸":
                # 摸胸: 害羞
                self.play_animation(ANIMATION_PATH.EMOTION_SING_BLUSH, ANIMATION_CONFIG.CONFIG_EMOTION_SING)
                if touch_count < 3: self.stats["mood"] = min(100, self.stats["intimacy"] - 0.1)
            elif part == "肚子":
                # 摸肚子: 开心
                self.play_animation(ANIMATION_PATH.EMOTION_SING_HAPPY, ANIMATION_CONFIG.CONFIG_EMOTION_SING)
                if touch_count < 3: self.stats["mood"] = min(100, self.stats["mood"] + 0.1)
            elif part == "手":
                # 牵手: 开心
                self.play_animation(ANIMATION_PATH.EMOTION_SING_HAPPY, ANIMATION_CONFIG.CONFIG_EMOTION_SING)
            elif part in ["大腿", "脚"]:
                # 摸腿/脚: 生气或不适
                self.play_animation(ANIMATION_PATH.EMOTION_SING_ANGRY, ANIMATION_CONFIG.CONFIG_EMOTION_SING)
                if touch_count < 3: self.stats["mood"] = max(0, self.stats["mood"] - 0.2)
            
            # 标记状态为 emotion (短暂展示后回 idle)
            self.current_role_state = "emotion"

    def start_touch_chat_process(self, text):
        """智能触摸互动专用流程"""
        print("DEBUG: Triggering Smart Touch Chat...")
        self.current_role_state = "talking"
        self.play_animation(ANIMATION_PATH.ACTION_CONT_TALK, ANIMATION_CONFIG.CONFIG_ACTION_CONT)
        
        persona = self.settings.get("persona", "")
        # 复用 ChatWorker
        self.chat_worker = ChatWorker(self.llm_client, text, self.stats, persona)
        self.chat_worker.reply_signal.connect(self.finish_touch_chat_process)
        self.chat_worker.start()

    def finish_touch_chat_process(self, reply, action_data):
        """触摸互动的回调：强制显示窗口"""
        if self.chat_window is None:
            self.chat_window = ChatWindow(self)
        
        # 强制显示并置顶
        if not self.chat_window.isVisible():
            self.chat_window.show()
            self.chat_window.update_position()
            self.chat_window.raise_()
        
        # 显示回复
        self.chat_window.receive_reply(reply)
        
        # 复用通用的完成逻辑来处理动作（但不重复显示文本）
        self.finish_chat_process(None, action_data)

    # --- 设置窗口逻辑 ---
    def open_settings_window(self):
        if self.settings_window is None:
            self.settings_window = SettingsWindow(self.settings, self)
            self.settings_window.settings_saved.connect(self.apply_settings)
        self.settings_window.show()
        self.settings_window.update_position() 
        self.settings_window.raise_()
        self.settings_window.activateWindow()

    def apply_settings(self, new_settings):
        print("Applying new settings:", new_settings)
        self.settings = new_settings
        self.memory_manager.save_settings(new_settings)
        
        # 核心：更新 LLM 客户端的配置
        self.llm_client.update_config(new_settings)
        self.coder_client.update_config(new_settings)
        
        new_size = tuple(new_settings.get("pet_size", [320, 320]))
        if new_size != self.target_size:
            self.target_size = new_size
            if self.current_frames:
                self._render_image(self.current_frames[self.current_frame_index % len(self.current_frames)])

    def moveEvent(self, event):
        super().moveEvent(event)
        if self.chat_window and self.chat_window.isVisible():
            self.chat_window.update_position()
        if self.settings_window and self.settings_window.isVisible():
            self.settings_window.update_position()

    def closeEvent(self, event):
        print("正在退出程序...")
        if self.logic_timer.isActive(): self.logic_timer.stop()
        if self.anim_timer.isActive(): self.anim_timer.stop()
        if self.pos_anim.state() == QPropertyAnimation.State.Running: self.pos_anim.stop()

        if self.active_chat_worker and self.active_chat_worker.isRunning():
            self.active_chat_worker.terminate()
            self.active_chat_worker.wait()
        
        if self.chat_worker and self.chat_worker.isRunning():
            self.chat_worker.terminate()
            self.chat_worker.wait()

        self.hide()
        if self.chat_window: self.chat_window.hide()
        if self.coding_window: self.coding_window.hide()
        if self.settings_window: self.settings_window.hide()
        
        QApplication.processEvents()

        print("正在后台保存数据...")
        try:
            self.memory_manager.save_status(self.stats)
            if self.llm_client:
                print("正在整理记忆 (这可能需要几秒钟)...")
                self.llm_client.summarize_session()
        except Exception as e:
            print(f"Error saving memories on exit: {e}")

        print("再见！")
        event.accept()
        sys.exit(0)

    def _update_stats_logic(self):
        if not self.isVisible(): return
        state = self.current_role_state
        self.tick_counter += 1

        if state == "work":
            self.stats["capability"] = min(40, self.stats["capability"] + 0.01)
            self.stats["fatigue"] = min(100, self.stats["fatigue"] + 0.2)
            self.stats["boredom"] = min(100, self.stats["boredom"] + 0.2)
        elif state == "code":
            self.stats["capability"] = min(60, self.stats["capability"] + 0.02)
            self.stats["fatigue"] = min(100, self.stats["fatigue"] + 0.4)
            self.stats["boredom"] = max(0, self.stats["boredom"] - 0.05)
        elif state == "sleep":
            self.stats["fatigue"] = max(0, self.stats["fatigue"] - 2.0)
        elif state == "play":
            self.stats["boredom"] = max(0, self.stats["boredom"] - 2.0)
            self.stats["fatigue"] = min(100, self.stats["fatigue"] + 0.2)
            self.stats["mood"] = min(100, self.stats["mood"] + 0.1)
        
        if state != "sleep":
            self.stats["hunger"] = min(100, self.stats["hunger"] + 0.01)
            self.stats["thirst"] = min(100, self.stats["thirst"] + 0.01)

        if state == "idle":
            active_chat_interval = self.settings.get("active_chat_interval", 60)
            active_chat_prob = self.settings.get("active_chat_probability", 0.2)
            
            if self.tick_counter % active_chat_interval == 0:
                if random.random() < active_chat_prob:
                    self.start_active_chat_process()
                    return 

            action_prob = self.settings.get("action_probability", 0.02)
            if random.random() < action_prob:
                self.start_autonomous_walk()
            
            elif self.tick_counter % 60 == 0:
                if self.stats['boredom'] > 50 or self.stats['fatigue'] > 50:
                    if random.random() < 0.1:
                        if self.stats['fatigue'] > self.stats['boredom']:
                            self.interact("sleep")
                        else:
                            self.interact("play")
            elif self.tick_counter % 15 == 0:
                new_direction = random.choice(["left", "right"])
                if new_direction != self.current_direction:
                    self.current_direction = new_direction
                    self.play_idle_animation()

    def start_active_chat_process(self):
        print("DEBUG: Triggering Active Chat...")
        self.current_role_state = "talking"
        self.play_animation(ANIMATION_PATH.ACTION_CONT_TALK, ANIMATION_CONFIG.CONFIG_ACTION_CONT)
        
        persona = self.settings.get("persona", "")
        self.active_chat_worker = ActiveChatWorker(self.llm_client, self.stats, persona)
        self.active_chat_worker.reply_signal.connect(self.finish_active_chat_process)
        self.active_chat_worker.start()

    def finish_active_chat_process(self, reply, action_data):
        if self.chat_window is None:
            self.chat_window = ChatWindow(self)
        if not self.chat_window.isVisible():
            self.chat_window.show()
            self.chat_window.update_position()
            self.chat_window.raise_()
        self.chat_window.receive_reply(reply)
        self.finish_chat_process(None, action_data)

    def start_autonomous_walk(self):
        self.current_role_state = "walking"
        distance = random.randint(50, 150)
        screen_geo = self.screen().geometry()
        current_x = self.x()
        target_x = current_x
        if self.current_direction == "left":
            target_x = max(0, current_x - distance)
            self.play_animation(ANIMATION_PATH.MOVEMENT_CONT_LEFT, ANIMATION_CONFIG.CONFIG_MOVEMENT_CONT)
        else:
            target_x = min(screen_geo.width() - self.width(), current_x + distance)
            self.play_animation(ANIMATION_PATH.MOVEMENT_CONT_RIGHT, ANIMATION_CONFIG.CONFIG_MOVEMENT_CONT)
        actual_distance = abs(target_x - current_x)
        if actual_distance < 5:
            self.current_role_state = "idle"
            self.play_idle_animation()
            return
        self.pos_anim.setDuration(int(actual_distance * 10)) 
        self.pos_anim.setStartValue(self.pos())
        self.pos_anim.setEndValue(QPoint(target_x, self.y()))
        self.pos_anim.setEasingCurve(QEasingCurve.Type.Linear)
        try: self.pos_anim.finished.disconnect()
        except TypeError: pass
        self.pos_anim.finished.connect(self._on_walk_finished)
        self.pos_anim.start()

    def _on_walk_finished(self):
        if self.current_role_state == "walking":
            self.current_role_state = "idle"
            self.play_idle_animation()

    def play_idle_animation(self):
        if self.current_direction == "left":
            self.play_animation(ANIMATION_PATH.BASIC_CONT_LEFT, ANIMATION_CONFIG.CONFIG_BASIC_CONT)
        else:
            self.play_animation(ANIMATION_PATH.BASIC_CONT_RIGHT, ANIMATION_CONFIG.CONFIG_BASIC_CONT)

    def play_animation(self, image_paths, config, next_anim=None, clear_queue=True):
        if clear_queue: self.anim_queue = []
        if next_anim: self.anim_queue.append(next_anim)
        if not image_paths: return
        self.current_frames = image_paths
        self.current_config = config
        self.current_frame_index = 0
        self.anim_start_time = time.time()
        fps = config.get("fps", 5.0)
        interval = int(1000 / fps) if fps > 0 else 1000
        self.anim_timer.start(interval)
        self._update_frame()

    def _update_frame(self):
        if not self.current_frames: return
        idx = self.current_frame_index
        if idx >= len(self.current_frames):
            if self.current_config.get("loop", False): idx = idx % len(self.current_frames)
            else: idx = len(self.current_frames) - 1
        path = self.current_frames[idx]
        self._render_image(path)
        is_sing = not self.current_config.get("loop", False)
        if is_sing:
            duration = self.current_config.get("duration", 2.0)
            elapsed = time.time() - self.anim_start_time
            if elapsed > duration:
                self._on_animation_finished()
                return
        self.current_frame_index += 1

    def _on_animation_finished(self):
        if self.anim_queue:
            next_paths, next_conf = self.anim_queue.pop(0)
            self.play_animation(next_paths, next_conf, clear_queue=False)
        else:
            self.current_role_state = "idle"
            self.play_idle_animation()

    def _render_image(self, path):
        if not os.path.exists(path): path = os.path.join(os.getcwd(), path)
        if os.path.exists(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull() and self.target_size:
                pixmap = pixmap.scaled(self.target_size[0], self.target_size[1],
                    Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
                self.label.setPixmap(pixmap)
                self.resize(pixmap.width(), pixmap.height())
                self.label.resize(pixmap.width(), pixmap.height())

    def toggle_chat_window(self):
        if self.chat_window is None: self.chat_window = ChatWindow(self)
        if self.chat_window.isVisible(): self.chat_window.hide()
        else:
            self.chat_window.show()
            self.chat_window.update_position()
            self.chat_window.raise_()
            self.chat_window.activateWindow()

    def start_chat_process(self, text):
        self.current_role_state = "talking"
        self.play_animation(ANIMATION_PATH.ACTION_CONT_TALK, ANIMATION_CONFIG.CONFIG_ACTION_CONT)
        
        persona = self.settings.get("persona", "")
        self.chat_worker = ChatWorker(self.llm_client, text, self.stats, persona)
        self.chat_worker.reply_signal.connect(self.finish_chat_process)
        self.chat_worker.start()

    def finish_chat_process(self, reply, action_data):
        if reply and self.chat_window:
            self.chat_window.receive_reply(reply)
        if action_data:
            print(f"Executing LLM Action: {action_data}")
            if "adjust" in action_data:
                for key, val in action_data["adjust"].items():
                    if key in self.stats:
                        self.stats[key] = max(0, min(100, self.stats[key] + val))
            if "animate" in action_data:
                anim_key = action_data["animate"]
                if hasattr(ANIMATION_PATH, anim_key):
                    paths = getattr(ANIMATION_PATH, anim_key)
                    config = ANIMATION_CONFIG.CONFIG_EMOTION_SING
                    self.current_role_state = "emotion"
                    self.play_animation(paths, config)
                    return 
            if "update_relationship" in action_data: 
                print(f"Relationship Updated via Action: {action_data['update_relationship']}")

        self.current_role_state = "idle"
        self.play_idle_animation()

    def open_coding_window(self):
        if self.coding_window is None:
            self.coding_window = CodingWindow(self.coder_client, lambda: self.stats)
            self.coding_window.get_persona = lambda: self.settings.get("persona", "")
            self.coding_window.action_signal.connect(self.handle_coding_action)
            
        if not self.coding_window.isVisible():
            self.coding_window.start_session()
            print("Entering Coding Mode...")
            self.current_role_state = "code"
            self.play_animation(ANIMATION_PATH.ACTION_CONT_CODE, ANIMATION_CONFIG.CONFIG_ACTION_CONT)
        else:
            self.coding_window.raise_()
            self.coding_window.activateWindow()

    def handle_coding_action(self, action_data):
        if "animate" in action_data:
            anim_key = action_data["animate"]
            if hasattr(ANIMATION_PATH, anim_key):
                paths = getattr(ANIMATION_PATH, anim_key)
                if "SING" in anim_key:
                    config = ANIMATION_CONFIG.CONFIG_EMOTION_SING
                    self.current_role_state = "emotion" 
                else:
                    config = ANIMATION_CONFIG.CONFIG_ACTION_CONT
                    self.current_role_state = "code"
                self.play_animation(paths, config)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        s = self.stats
        status_text = f"饿{int(s['hunger'])} 渴{int(s['thirst'])} 累{int(s['fatigue'])} 能{int(s['capability'])}"
        status_action = QAction(status_text, self)
        status_action.setEnabled(False)
        menu.addAction(status_action)
        menu.addSeparator()

        action_chat = QAction("对话开关 (Chat)", self)
        action_chat.triggered.connect(self.toggle_chat_window)
        menu.addAction(action_chat)
        
        action_code_mode = QAction("编程模式 (Coding Mode)", self)
        action_code_mode.triggered.connect(self.open_coding_window)
        menu.addAction(action_code_mode)
        
        action_settings = QAction("系统设置 (Settings)", self)
        action_settings.triggered.connect(self.open_settings_window)
        menu.addAction(action_settings)

        menu.addSeparator()

        actions = [
            ("投喂零食 (Eat)", "eat"),
            ("给水喝 (Drink)", "drink"),
            ("一起玩 (Play)", "play"),
            ("去工作 (Work)", "work"),
            ("去睡觉 (Sleep)", "sleep"),
            ("写代码 (Code Animation)", "code") 
        ]
        
        for name, type_ in actions:
            act = QAction(name, self)
            act.triggered.connect(lambda checked, t=type_: self.interact(t))
            menu.addAction(act)
        
        menu.addSeparator()
        action_quit = QAction("退出程序", self)
        action_quit.triggered.connect(self.close) 
        menu.addAction(action_quit)

        menu.exec(event.globalPos())

    def interact(self, action_type):
        print(f"Interact: {action_type}")
        if self.pos_anim.state() == QPropertyAnimation.State.Running:
            self.pos_anim.stop()
            try: self.pos_anim.finished.disconnect()
            except TypeError: pass

        if action_type == "eat":
            self.current_role_state = "idle"
            self.stats['hunger'] = max(0, self.stats['hunger'] - 20)
            self.stats['intimacy'] += 5
            self.stats['mood'] += 2
            self.play_animation(ANIMATION_PATH.ACTION_SING_EAT, ANIMATION_CONFIG.CONFIG_ACTION_SING)
        elif action_type == "drink":
            self.current_role_state = "idle"
            self.stats['thirst'] = max(0, self.stats['thirst'] - 20)
            self.stats['intimacy'] += 5
            self.stats['mood'] += 1
            self.play_animation(ANIMATION_PATH.ACTION_SING_DRINK, ANIMATION_CONFIG.CONFIG_ACTION_SING)
        elif action_type == "play":
            self.current_role_state = "play"
            self.play_animation(ANIMATION_PATH.ACTION_CONT_PLAY, ANIMATION_CONFIG.CONFIG_ACTION_CONT)
        elif action_type == "work":
            self.current_role_state = "work"
            self.play_animation(ANIMATION_PATH.ACTION_CONT_WORK, ANIMATION_CONFIG.CONFIG_ACTION_CONT)
        elif action_type == "sleep":
            self.current_role_state = "sleep"
            self.play_animation(ANIMATION_PATH.ACTION_CONT_SLEEP, ANIMATION_CONFIG.CONFIG_ACTION_CONT)
        elif action_type == "code":
            self.current_role_state = "code"
            self.play_animation(ANIMATION_PATH.ACTION_CONT_CODE, ANIMATION_CONFIG.CONFIG_ACTION_CONT)

    def _on_drop_finished(self):
        anim_stand = (ANIMATION_PATH.MOVEMENT_SING_STAND, ANIMATION_CONFIG.CONFIG_MOVEMENT_SING)
        self.play_animation(ANIMATION_PATH.MOVEMENT_SING_LAND, ANIMATION_CONFIG.CONFIG_MOVEMENT_SING, next_anim=anim_stand)