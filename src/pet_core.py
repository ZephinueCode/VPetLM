import random
import time
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

from src.vlm_utils import LLMClient, CoderClient
from src.memory_utils import MemoryManager
from src.parameters import ANIMATION_PATH, ANIMATION_CONFIG
from src.pet_workers import ChatWorker, ActiveChatWorker, CoderWorker, SummaryWorker

def safe_print(text):
    try:
        print(text)
    except Exception:
        pass

class PetCore(QObject):
    """
    桌宠的核心数据与逻辑类。
    负责管理：数值状态、记忆、LLM客户端、业务逻辑循环。
    不包含：UI绘制、窗口移动、动画帧刷新。
    """
    # 信号定义
    stats_changed = pyqtSignal(dict)       # 数值变化时发出
    animation_requested = pyqtSignal(list, dict, object, bool) # 请求播放动画
    chat_reply_received = pyqtSignal(str)  # 收到回复文本
    
    # 需要 UI 响应的事件
    show_chat_window_signal = pyqtSignal()
    show_init_window_signal = pyqtSignal()
    ready_to_exit_signal = pyqtSignal() # 准备好退出了
    
    def __init__(self):
        super().__init__()
        
        # 1. 初始化基础设施
        self.memory_manager = MemoryManager()
        self.settings = self.memory_manager.load_settings()
        self.llm_client = LLMClient()
        self.coder_client = CoderClient()

        # 2. 加载或初始化状态
        default_stats = {
            "hunger": 0, "thirst": 0, "fatigue": 0, 
            "boredom": 0, "intimacy": 0, "capability": 0, "mood": 50
        }
        saved_stats = self.memory_manager.load_status()
        self.stats = saved_stats if saved_stats else default_stats
        
        # [新增] 初始化时间信息到 stats 中 (保存量)
        self._update_current_time()
        
        # 3. 运行时状态
        self.current_role_state = "idle"  # idle, working, sleeping, talking, walking, code
        self.tick_counter = 0
        
        # 新增：最后一次互动时间戳
        self.last_interaction_time = time.time()
        # [新增] 下一次主动搭话检查的时间点
        self._reset_next_chat_check_time()
        
        # 4. 启动逻辑循环 (1秒一次)
        self.logic_timer = QTimer(self)
        self.logic_timer.timeout.connect(self._on_logic_tick)
        self.logic_timer.start(1000)

        # 5. 延迟检查初次见面
        QTimer.singleShot(1500, self.check_first_encounter)

        # Worker 引用
        self.active_worker = None
        self.summary_worker = None

    def reload_settings(self, new_settings):
        """重新加载设置"""
        self.settings = new_settings
        self.llm_client.update_config(new_settings)
        self.coder_client.update_config(new_settings)
        # 重新检查是否满足初次见面（比如刚配置好Key）
        self.check_first_encounter()

    def _update_current_time(self):
        """更新当前时间字符串到 stats 中"""
        now_str = datetime.now().strftime("%Y年%m月%d日%H点%M分")
        self.stats['current_time'] = now_str

    def _get_time_aware_persona(self):
        """获取带有时间信息的人设 Prompt"""
        # 确保时间是最新的
        self._update_current_time()
        base_persona = self.settings.get("persona", "")
        # 将时间信息追加到 System Prompt 中
        return f"{base_persona}\n现在是{self.stats['current_time']}。"

    def _reset_next_chat_check_time(self):
        """重置下一次主动搭话检查时间（在互动结束后的下一个周期）"""
        interval = self.settings.get("active_chat_interval", 60)
        self.next_chat_check_time = time.time() + interval

    def check_first_encounter(self):
        """检查是否初次见面"""
        if self.memory_manager.is_fresh_start():
            if self.llm_client.is_ready():
                safe_print("[Core] Detected fresh start & API ready. Starting Init Process.")
                self.start_init_process()
            else:
                safe_print("[Core] Detected fresh start but API not ready.")
                # 这里可以通过信号通知UI弹出设置，但为了简化，留给UI层的主动检查逻辑

    def start_init_process(self):
        self.current_role_state = "talking"
        self.animation_requested.emit(ANIMATION_PATH.ACTION_CONT_TALK, ANIMATION_CONFIG.CONFIG_ACTION_CONT, None, True)
        
        # 初始化时使用带有时间的 Persona
        persona = self._get_time_aware_persona()
        self.active_worker = ActiveChatWorker(self.llm_client, self.stats, persona, mode="intro")
        self.active_worker.reply_signal.connect(self._on_init_reply)
        self.active_worker.start()

    def _on_init_reply(self, reply, action_data):
        safe_print(f"[Init Reply] {reply}")
        # 先显示窗口，再发内容，确保 UI 能接收
        self.show_chat_window_signal.emit()
        self.chat_reply_received.emit(reply)
        
        self.current_role_state = "idle"
        # 播放待机动画
        self.reset_idle_animation()
        # 更新互动时间
        self.last_interaction_time = time.time()
        self._reset_next_chat_check_time()
        
        # 延迟3秒弹出信息登记窗口，确保用户有时间阅读自我介绍
        QTimer.singleShot(3000, self.show_init_window_signal.emit)

    def handle_init_submission(self, data):
        """处理用户提交的初始化信息"""
        added_info = []
        mapping = {"称呼": "称呼", "生日": "生日", "职业": "职业", "爱好": "爱好"}
        for key, val in data.items():
            if val:
                info_str = f"用户{mapping[key]}是：{val}"
                self.memory_manager.add_memory(info_str)
                added_info.append(f"{key}({val})")
        
        if added_info:
            prompt = f"用户填写了个人信息卡：{', '.join(added_info)}。请用开心的语气表示记住了，并问好。"
            self.start_chat(prompt)

    def start_chat(self, text):
        """开始一段对话"""
        self.current_role_state = "talking"
        self.animation_requested.emit(ANIMATION_PATH.ACTION_CONT_TALK, ANIMATION_CONFIG.CONFIG_ACTION_CONT, None, True)
        
        # 普通对话使用带有时间的 Persona
        persona = self._get_time_aware_persona()
        self.active_worker = ChatWorker(self.llm_client, text, self.stats, persona)
        self.active_worker.reply_signal.connect(self._on_chat_finished)
        self.active_worker.start()

    def _on_chat_finished(self, reply, action_data):
        safe_print(f"[Chat Reply] {reply}")
        self.show_chat_window_signal.emit()
        self.chat_reply_received.emit(reply)
        self.process_llm_action(action_data)
        
        if self.current_role_state == "talking":
             self.current_role_state = "idle"
             self.reset_idle_animation()
        
        # 对话结束，更新最后互动时间，并推迟下一次检查
        self.last_interaction_time = time.time()
        self._reset_next_chat_check_time()

    def start_active_chat(self):
        """触发主动搭话"""
        self.current_role_state = "talking"
        self.animation_requested.emit(ANIMATION_PATH.ACTION_CONT_TALK, ANIMATION_CONFIG.CONFIG_ACTION_CONT, None, True)
        
        # 主动搭话也包含时间信息
        persona = self._get_time_aware_persona()
        self.active_worker = ActiveChatWorker(self.llm_client, self.stats, persona, mode="active")
        self.active_worker.reply_signal.connect(self._on_chat_finished)
        self.active_worker.start()

    # --- 退出流程 ---
    def start_exit_process(self):
        """退出程序前的再见流程"""
        safe_print("[Core] Starting Exit Process...")
        self.current_role_state = "talking"
        self.animation_requested.emit(ANIMATION_PATH.ACTION_CONT_TALK, ANIMATION_CONFIG.CONFIG_ACTION_CONT, None, True)
        
        # 1. 启动后台总结 (不阻塞)
        self.summary_worker = SummaryWorker(self.llm_client)
        self.summary_worker.start()
        
        # 2. 保存数值
        self.memory_manager.save_status(self.stats)

        # 3. 启动告别对话
        # 告别时通常也需要知道时间（比如“很晚了，早点睡”）
        persona = self._get_time_aware_persona()
        self.active_worker = ActiveChatWorker(self.llm_client, self.stats, persona, mode="goodbye")
        self.active_worker.reply_signal.connect(self._on_goodbye_reply)
        self.active_worker.start()

    def _on_goodbye_reply(self, reply, action_data):
        safe_print(f"[Goodbye] {reply}")
        self.show_chat_window_signal.emit()
        self.chat_reply_received.emit(reply)
        
        # 播放个动作
        self.animation_requested.emit(ANIMATION_PATH.ACTION_CONT_SLEEP, ANIMATION_CONFIG.CONFIG_ACTION_CONT, None, True)
        
        # 延迟3秒后通知 UI 彻底关闭
        QTimer.singleShot(2000, self.ready_to_exit_signal.emit)

    def interact(self, action_type):
        """处理用户交互指令 (eat, sleep, etc.)"""
        if action_type == "eat":
            self.current_role_state = "idle"
            self.stats['hunger'] = max(0, self.stats['hunger'] - 20)
            self.stats['intimacy'] += 0.01
            self.stats['mood'] += 2
            self.animation_requested.emit(ANIMATION_PATH.ACTION_SING_EAT, ANIMATION_CONFIG.CONFIG_ACTION_SING, None, True)
        elif action_type == "drink":
            self.current_role_state = "idle"
            self.stats['thirst'] = max(0, self.stats['thirst'] - 20)
            self.stats['intimacy'] += 0.01
            self.stats['mood'] += 1
            self.animation_requested.emit(ANIMATION_PATH.ACTION_SING_DRINK, ANIMATION_CONFIG.CONFIG_ACTION_SING, None, True)
        elif action_type == "play":
            self.current_role_state = "play"
            self.animation_requested.emit(ANIMATION_PATH.ACTION_CONT_PLAY, ANIMATION_CONFIG.CONFIG_ACTION_CONT, None, True)
        elif action_type == "work":
            self.current_role_state = "work"
            self.animation_requested.emit(ANIMATION_PATH.ACTION_CONT_WORK, ANIMATION_CONFIG.CONFIG_ACTION_CONT, None, True)
        elif action_type == "sleep":
            self.current_role_state = "sleep"
            self.animation_requested.emit(ANIMATION_PATH.ACTION_CONT_SLEEP, ANIMATION_CONFIG.CONFIG_ACTION_CONT, None, True)
        elif action_type == "code":
            self.current_role_state = "code"
            self.animation_requested.emit(ANIMATION_PATH.ACTION_CONT_CODE, ANIMATION_CONFIG.CONFIG_ACTION_CONT, None, True)
        
        self.stats_changed.emit(self.stats)
        self.last_interaction_time = time.time()
        self._reset_next_chat_check_time()

    def process_llm_action(self, action_data):
        """处理 LLM 返回的 JSON 指令"""
        if not action_data: return
        safe_print(f"[Core] Processing Action: {action_data}")
        
        if "adjust" in action_data:
            for key, val in action_data["adjust"].items():
                if key in self.stats:
                    self.stats[key] = max(0, min(100, self.stats[key] + val))
            self.stats_changed.emit(self.stats)

        if "animate" in action_data:
            anim_key = action_data["animate"]
            if hasattr(ANIMATION_PATH, anim_key):
                paths = getattr(ANIMATION_PATH, anim_key)
                config = ANIMATION_CONFIG.CONFIG_EMOTION_SING
                self.current_role_state = "emotion"
                self.animation_requested.emit(paths, config, None, True)

    def process_touch(self, part, touch_type):
        """
        处理触摸逻辑
        touch_type: "gentle" (单击), "stroke" (双击), "pat" (三击)
        """
        smart_touch = self.settings.get("smart_touch", True)
        
        # 映射中文描述
        type_map = {
            "gentle": "轻轻触摸了",
            "stroke": "温柔抚摸了",
            "pat": "用力揉了揉"
        }
        action_desc = type_map.get(touch_type, "触摸了")
        
        if smart_touch:
            prompt = f"*用户{action_desc}你的{part}。*"
            self.start_chat(prompt)
        else:
            # 普通逻辑（这里根据力度简单区分数值反馈）
            if part == "脑袋":
                self.animation_requested.emit(ANIMATION_PATH.EMOTION_SING_ENJOY, ANIMATION_CONFIG.CONFIG_EMOTION_SING, None, True)
                add_mood = 0.5 if touch_type == "stroke" else 0.2
                self.stats["mood"] = min(100, self.stats["mood"] + add_mood)
            elif part == "胸":
                self.animation_requested.emit(ANIMATION_PATH.EMOTION_SING_BLUSH, ANIMATION_CONFIG.CONFIG_EMOTION_SING, None, True)
                sub_mood = 0.2 if touch_type == "pat" else 0.1
                self.stats["mood"] = max(0, self.stats["mood"] - sub_mood)
            elif part in ["肚子", "手"]:
                self.animation_requested.emit(ANIMATION_PATH.EMOTION_SING_HAPPY, ANIMATION_CONFIG.CONFIG_EMOTION_SING, None, True)
                self.stats["mood"] = min(100, self.stats["mood"] + 0.2)
            elif part in ["大腿", "脚"]:
                self.animation_requested.emit(ANIMATION_PATH.EMOTION_SING_ANGRY, ANIMATION_CONFIG.CONFIG_EMOTION_SING, None, True)
                self.stats["mood"] = max(0, self.stats["mood"] - 0.5)
            
            self.current_role_state = "emotion"
            self.stats_changed.emit(self.stats)
        
        self.last_interaction_time = time.time()
        self._reset_next_chat_check_time()

    def _on_logic_tick(self):
        """每秒执行一次的数值逻辑"""
        self.tick_counter += 1
        self._update_current_time() # 每一跳都更新时间
        
        state = self.current_role_state
        
        # 简单的数值变化
        if state == "work":
            self.stats["fatigue"] = min(100, self.stats["fatigue"] + 0.1)
            self.stats["boredom"] = min(100, self.stats["boredom"] + 0.05)
            self.stats["mood"] = max(0, self.stats["mood"] - 0.01)
        elif state == "sleep":
            self.stats["fatigue"] = max(0, self.stats["fatigue"] - 0.1)
        elif state == "play":
            self.stats["boredom"] = max(0, self.stats["boredom"] - 0.1)
            self.stats["fatigue"] = min(100, self.stats["fatigue"] + 0.05)
            self.stats["mood"] = min(100, self.stats["mood"] + 0.02)
        elif state == "code":
            self.stats["capability"] = min(100, self.stats["capability"] + 0.001)
            self.stats["fatigue"] = min(100, self.stats["fatigue"] + 0.1)
            self.stats["mood"] = max(0, self.stats["mood"] - 0.02)
        if state != "sleep":
            self.stats["hunger"] = min(100, self.stats["hunger"] + 0.01)
            self.stats["thirst"] = min(100, self.stats["thirst"] + 0.01)

        # 检查自动行为
        if state == "idle":
            self._check_autonomous_actions()

    def _check_autonomous_actions(self):
        """主动搭话检查逻辑：到达预定时间点后触发一次随机判定"""
        current_time = time.time()
        chat_prob = self.settings.get("active_chat_probability", 0.2)
        interval = self.settings.get("active_chat_interval", 60)
        
        # 如果当前时间超过了下一次检查时间
        if current_time >= self.next_chat_check_time:
            # 尝试随机触发
            if random.random() < chat_prob:
                self.start_active_chat()
            else:
                # 触发失败，重置下一次检查时间（当前时间 + 间隔）
                # 注意：这里用 current_time 加上 interval，而不是基于旧的 check_time
                # 这样可以避免因程序卡顿导致的连续触发
                self.next_chat_check_time = current_time + interval

    def reset_idle_animation(self):
        """通知 UI 恢复待机动画"""
        self.animation_requested.emit([], {}, None, False) # 特殊约定

    def save_data(self):
        """保存数据 (仅用于非正常退出时的备份，正常退出走 start_exit_process)"""
        self.memory_manager.save_status(self.stats)
        self.llm_client.summarize_session()