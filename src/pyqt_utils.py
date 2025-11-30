import sys
import os
import time
import random
from PyQt6.QtWidgets import (QApplication, QWidget, QLabel, QMenu, QMessageBox)
from PyQt6.QtCore import Qt, QPoint, QTimer, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QPixmap, QMouseEvent, QAction

# 导入
try:
    from src.parameters import ANIMATION_PATH, ANIMATION_CONFIG
    from src.pet_core import PetCore
    from src.pet_windows import ChatWindow, InitSetupWindow
    from src.coding_utils import CodingWindow 
    from src.settings_ui import SettingsWindow 
except ImportError:
    from parameters import ANIMATION_PATH, ANIMATION_CONFIG
    from pet_core import PetCore
    from pet_windows import ChatWindow, InitSetupWindow
    from coding_utils import CodingWindow
    from settings_ui import SettingsWindow

class DesktopPet(QWidget):
    def __init__(self, target_size=(320, 320), parent=None):
        super().__init__(parent)
        
        # 1. 初始化核心逻辑 (Model/Controller)
        self.core = PetCore()
        
        # 2. 连接 Core 信号
        self.core.stats_changed.connect(self.on_stats_changed)
        self.core.animation_requested.connect(self.play_animation)
        self.core.chat_reply_received.connect(self.on_chat_reply)
        self.core.show_chat_window_signal.connect(self.show_chat_window)
        self.core.show_init_window_signal.connect(self.show_init_window)
        self.core.ready_to_exit_signal.connect(self.force_quit) # 新增：彻底退出
        
        # 3. UI 初始化
        self.target_size = tuple(self.core.settings.get("pet_size", target_size))
        self.current_direction = "right"
        self.init_ui()
        
        # 4. 动画状态
        self.current_frames = []      
        self.current_frame_index = 0  
        self.current_config = {}      
        self.anim_start_time = 0      
        self.anim_queue = []          
        
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._update_frame)
        
        # 5. 交互状态
        self.is_dragging = False
        self.is_potential_drag = False
        self.press_start_pos = QPoint()
        self.drag_offset = QPoint()
        self.pos_anim = QPropertyAnimation(self, b"pos")
        
        # [新增] 触摸连击检测
        self.click_count = 0
        self.click_timer = QTimer(self)
        self.click_timer.setSingleShot(True)
        self.click_timer.setInterval(300) # 300ms 连击判定窗口
        self.click_timer.timeout.connect(self._on_click_timer_timeout)
        self.last_click_pos = QPoint()

        # 6. 子窗口
        self.chat_window = None 
        self.coding_window = None 
        self.settings_window = None
        self.init_setup_window = None
        
        # 7. 退出标志位
        self.is_exiting = False

        # 启动默认动画
        self.play_idle_animation()
        
        # 自主行走逻辑 (View层)
        self.walk_check_timer = QTimer(self)
        self.walk_check_timer.timeout.connect(self._check_view_autonomous_behavior)
        self.walk_check_timer.start(1000)

    def init_ui(self):
        QApplication.instance().setQuitOnLastWindowClosed(False)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.label = QLabel(self)
        self.move(200, 200)

    # --- 信号响应槽 ---
    def on_stats_changed(self, new_stats):
        pass

    def on_chat_reply(self, reply):
        if self.chat_window:
            self.chat_window.receive_reply(reply)

    def _ensure_chat_window_created(self):
        if self.chat_window is None:
            self.chat_window = ChatWindow(self, self.core)

    def show_chat_window(self):
        self._ensure_chat_window_created()
        if not self.chat_window.isVisible():
            self.chat_window.show()
            self.chat_window.update_position()
            self.chat_window.raise_()

    def show_init_window(self):
        if self.init_setup_window is None:
            self.init_setup_window = InitSetupWindow(self)
            self.init_setup_window.submission_signal.connect(self.core.handle_init_submission)
        self.init_setup_window.show()
        self.init_setup_window.update_position()
        self.init_setup_window.raise_()

    def force_quit(self):
        """Core 通知可以彻底关闭了"""
        self.is_exiting = True # 跳过拦截
        self.close()

    # --- 动画逻辑 ---
    def play_animation(self, image_paths, config, next_anim=None, clear_queue=True):
        if not image_paths and not clear_queue:
             self.play_idle_animation()
             return

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
            self.play_idle_animation()

    def play_idle_animation(self):
        if self.current_direction == "left":
            self.play_animation(ANIMATION_PATH.BASIC_CONT_LEFT, ANIMATION_CONFIG.CONFIG_BASIC_CONT)
        else:
            self.play_animation(ANIMATION_PATH.BASIC_CONT_RIGHT, ANIMATION_CONFIG.CONFIG_BASIC_CONT)

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

    # --- 输入事件 ---
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.press_start_pos = event.globalPosition().toPoint()
            self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.is_potential_drag = True
            self.is_dragging = False
            if self.pos_anim.state() == QPropertyAnimation.State.Running:
                self.pos_anim.stop()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent):
        if event.buttons() & Qt.MouseButton.LeftButton:
            current_pos = event.globalPosition().toPoint()
            if self.is_potential_drag and (current_pos - self.press_start_pos).manhattanLength() > 5:
                self.is_dragging = True
                self.is_potential_drag = False
                self.play_animation(ANIMATION_PATH.MOVEMENT_CONT_DRAG, ANIMATION_CONFIG.CONFIG_MOVEMENT_CONT)
            if self.is_dragging:
                self.move(current_pos - self.drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_dragging:
                self.is_dragging = False
                self._handle_drop()
            elif self.is_potential_drag:
                self.is_potential_drag = False
                # [核心修改] 启动/累加 连击定时器
                self.click_count += 1
                self.last_click_pos = event.position() # 记录最后点击位置
                # 重新启动定时器 (重置倒计时)
                self.click_timer.start()
                
            event.accept()

    def _on_click_timer_timeout(self):
        """连击判定结束，执行逻辑"""
        count = self.click_count
        self.click_count = 0 # 重置
        
        if count == 0: return
        
        # 传递给 touch handler
        self.handle_touch(self.last_click_pos, count)

    def handle_touch(self, local_pos, click_count_now):
        if self.core.current_role_state == "talking": return

        x_ratio = local_pos.x() / self.width()
        y_ratio = local_pos.y() / self.height()
        
        part = "身体"
        if y_ratio < 0.35: part = "脑袋"
        elif y_ratio < 0.7:
            if x_ratio < 0.35 or x_ratio > 0.65: part = "手" # 调整手判定范围
            elif y_ratio < 0.55: part = "胸"
            else: part = "肚子"
        elif y_ratio < 0.85: part = "大腿"
        else: part = "脚"
        
        # 判定触摸类型
        touch_type = "gentle"
        if click_count_now == 2:
            touch_type = "stroke"
        elif click_count_now >= 3:
            touch_type = "pat"
            
        print(f"Touch: {part}, Count: {click_count_now}, Type: {touch_type}")
        
        # 调用核心逻辑处理
        self.core.process_touch(part, touch_type)

    def _handle_drop(self):
        screen_height = self.screen().geometry().height()
        current_y = self.y()
        drop_distance = int(screen_height * random.uniform(0.1, 0.2))
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

    def _on_drop_finished(self):
        anim_stand = (ANIMATION_PATH.MOVEMENT_SING_STAND, ANIMATION_CONFIG.CONFIG_MOVEMENT_SING)
        self.play_animation(ANIMATION_PATH.MOVEMENT_SING_LAND, ANIMATION_CONFIG.CONFIG_MOVEMENT_SING, next_anim=anim_stand)

    # --- 自主行为 View 实现 ---
    def _check_view_autonomous_behavior(self):
        if self.core.current_role_state == "idle":
             action_prob = self.core.settings.get("action_probability", 0.02)
             if random.random() < action_prob:
                 self.start_autonomous_walk()

    def start_autonomous_walk(self):
        self.core.current_role_state = "walking"
        distance = random.randint(50, 150)
        screen_geo = self.screen().geometry()
        current_x = self.x()
        
        if self.current_direction == "left":
            target_x = max(0, current_x - distance)
            self.play_animation(ANIMATION_PATH.MOVEMENT_CONT_LEFT, ANIMATION_CONFIG.CONFIG_MOVEMENT_CONT)
        else:
            target_x = min(screen_geo.width() - self.width(), current_x + distance)
            self.play_animation(ANIMATION_PATH.MOVEMENT_CONT_RIGHT, ANIMATION_CONFIG.CONFIG_MOVEMENT_CONT)
            
        actual_distance = abs(target_x - current_x)
        if actual_distance < 5:
            self.core.current_role_state = "idle"
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
        self.core.current_role_state = "idle"
        self.play_idle_animation()

    # --- 窗口管理 ---
    def toggle_chat_window(self):
        self._ensure_chat_window_created()
        if self.chat_window.isVisible():
            self.chat_window.hide()
        else: 
            self.chat_window.show()
            self.chat_window.update_position()
            self.chat_window.raise_()
            self.chat_window.activateWindow()

    def open_settings_window(self):
        if self.settings_window is None:
            self.settings_window = SettingsWindow(self.core.settings, self)
            self.settings_window.settings_saved.connect(self.core.reload_settings)
        self.settings_window.show()
        self.settings_window.update_position()
        self.settings_window.raise_()

    def open_coding_window(self):
        if self.coding_window is None:
            self.coding_window = CodingWindow(self.core.coder_client, lambda: self.core.stats)
            self.coding_window.get_persona = lambda: self.core.settings.get("persona", "")
            self.coding_window.action_signal.connect(self.core.process_llm_action)
        
        if not self.coding_window.isVisible():
            self.coding_window.start_session()
            self.core.interact("code")
        else:
            self.coding_window.raise_()

    # --- 上下文菜单 ---
    def contextMenuEvent(self, event):
        menu = QMenu(self)
        s = self.core.stats
        status_text = f"饿{int(s['hunger'])} 渴{int(s['thirst'])} 累{int(s['fatigue'])} 能{int(s['capability'])}"
        menu.addAction(status_text).setEnabled(False)
        menu.addSeparator()

        menu.addAction("对话开关 (Chat)", self.toggle_chat_window)
        menu.addAction("编程模式 (Coding)", self.open_coding_window)
        menu.addAction("系统设置 (Settings)", self.open_settings_window)
        menu.addSeparator()

        actions = [("投喂 (Eat)", "eat"), ("喝水 (Drink)", "drink"), ("玩耍 (Play)", "play"), 
                   ("工作 (Work)", "work"), ("睡觉 (Sleep)", "sleep"), ("写代码 (Code)", "code")]
        for name, key in actions:
            menu.addAction(name, lambda k=key: self.core.interact(k))
        
        menu.addSeparator()
        menu.addAction("退出程序", self.close) # 触发 closeEvent -> start_exit_process
        menu.exec(event.globalPos())

    def moveEvent(self, event):
        super().moveEvent(event)
        for w in [self.chat_window, self.settings_window, self.init_setup_window]:
            if w and w.isVisible(): w.update_position()

    def closeEvent(self, event):
        """
        拦截关闭事件，执行优雅退出流程。
        """
        if self.is_exiting:
            event.accept()
            # 确保子线程退出
            QApplication.quit()
        else:
            event.ignore()
            # 启动退出流程
            self.core.start_exit_process()