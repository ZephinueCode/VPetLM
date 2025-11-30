from PyQt6.QtCore import QThread, pyqtSignal

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
        if self.client and self.client.is_ready():
            reply, action = self.client.chat(self.text, self.stats, self.persona)
            self.reply_signal.emit(reply, action)
        else:
            self.reply_signal.emit("请先在设置中配置 API Key 哦！", {})

# --- 2. 主动聊天线程 ---
class ActiveChatWorker(QThread):
    reply_signal = pyqtSignal(str, dict)

    def __init__(self, client, current_stats, persona, mode="active"):
        super().__init__()
        self.client = client
        self.stats = current_stats
        self.persona = persona
        self.mode = mode # 'active', 'intro', or 'goodbye'

    def run(self):
        if self.client and self.client.is_ready():
            reply, action = "", {}
            
            if self.mode == "intro":
                reply, action = self.client.get_self_introduction(self.persona)
            elif self.mode == "goodbye":
                reply, action = self.client.get_goodbye_message(self.persona, self.stats)
            else:
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
        if self.client and self.client.is_ready():
            reply, action = self.client.chat(self.text, self.stats, self.persona)
            self.reply_signal.emit(reply, action)

# --- 4. 总结线程 (新增) ---
class SummaryWorker(QThread):
    """后台默默执行总结，不阻塞退出流程"""
    def __init__(self, client):
        super().__init__()
        self.client = client

    def run(self):
        if self.client and self.client.is_ready():
            self.client.summarize_session()